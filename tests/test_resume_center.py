import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

import yaml

from bosshunter.db import get_db, insert_job
from bosshunter.web import resume_center, server
from bosshunter.web.resume_center_export import (
	export_resume_version_pdf,
	resume_version_filename,
	resume_version_html,
	resume_version_markdown,
	resume_version_markdown_filename,
)
from bosshunter.web.resume_center_import import apply_resume_import_draft, build_resume_import_preview
from bosshunter.web.resume_description_format import format_entry_description_text
from bosshunter.web.resume_jd_customizer import create_resume_version_for_job
from bosshunter.web.resume_photo_extract import extract_resume_photo
from bosshunter.web.resume_template_import import build_template_import_preview, create_template_from_import_draft
from bosshunter.web.resume_upload import docx_to_markdown
from bosshunter.web.reactive_resume import build_reactive_resume_data


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 3000


def make_docx_with_media(document_text: str, media: dict[str, bytes] | None = None) -> bytes:
	body = "".join(f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>" for line in document_text.splitlines() if line)
	document_xml = (
		'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
		'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
		f"<w:body>{body}</w:body>"
		"</w:document>"
	)
	buffer = io.BytesIO()
	with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
		archive.writestr("word/document.xml", document_xml)
		for name, content in (media or {}).items():
			archive.writestr(f"word/media/{name}", content)
	return buffer.getvalue()


def make_docx_with_bold_paragraph(title: str, body: str) -> bytes:
	document_xml = (
		'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
		'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
		"<w:body>"
		f"<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>{title}</w:t></w:r></w:p>"
		f"<w:p><w:r><w:t>{body}</w:t></w:r></w:p>"
		"</w:body>"
		"</w:document>"
	)
	buffer = io.BytesIO()
	with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
		archive.writestr("word/document.xml", document_xml)
	return buffer.getvalue()


class ResumeCenterStoreTests(unittest.TestCase):
	def test_init_creates_resume_center_tables_and_builtin_templates(self):
		with tempfile.TemporaryDirectory() as tmp:
			conn = get_db(Path(tmp) / "bosshunter.db")

			tables = {
				row["name"]
				for row in conn.execute(
					"SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE 'resume_%'"
				).fetchall()
			}
			templates = resume_center.list_templates(conn)

			self.assertIn("resume_profiles", tables)
			self.assertIn("resume_sections", tables)
			self.assertIn("resume_versions", tables)
			self.assertEqual({item["source_type"] for item in templates}, {"builtin"})
			self.assertGreaterEqual(len(templates), 2)
			conn.close()

	def test_profile_section_entry_material_round_trip_and_cascade_delete(self):
		with tempfile.TemporaryDirectory() as tmp:
			conn = get_db(Path(tmp) / "bosshunter.db")

			profile = resume_center.update_profile(
				conn,
				{
					"basics": {"name": "张三", "degree": "机械工程硕士"},
					"contacts": {"email": "zhangsan@example.com"},
					"education": [{"school": "昆明理工大学"}],
					"skills": ["Python", "ROS1"],
					"preferences": {"target": "机器人"},
				},
			)
			section = resume_center.create_section(
				conn,
				{"section_type": "project", "title": "项目经历", "sort_order": 10},
			)
			entry = resume_center.create_entry(
				conn,
				{
					"section_id": section["id"],
					"title": "三爪机械爪控制",
					"organization": "实验室",
					"description": "控制机械爪开合并完成调试。",
				},
			)
			material = resume_center.create_material(
				conn,
				{
					"entry_id": entry["id"],
					"content": "基于 ROS1 编写机械爪开合控制节点。",
					"tags": ["ROS1", "机械爪"],
					"jd_keywords": ["机器人控制"],
					"strength": 4,
				},
			)

			sections = resume_center.list_sections(conn)
			self.assertEqual(profile["basics"]["name"], "张三")
			self.assertEqual(sections[0]["entries"][0]["materials"][0]["id"], material["id"])

			resume_center.delete_section(conn, section["id"])
			self.assertEqual(conn.execute("SELECT COUNT(*) AS cnt FROM resume_entries").fetchone()["cnt"], 0)
			self.assertEqual(conn.execute("SELECT COUNT(*) AS cnt FROM resume_materials").fetchone()["cnt"], 0)
			conn.close()

	def test_resume_version_snapshots_profile_and_material_selection(self):
		with tempfile.TemporaryDirectory() as tmp:
			conn = get_db(Path(tmp) / "bosshunter.db")
			resume_center.update_profile(conn, {"basics": {"name": "旧名字"}})
			section = resume_center.create_section(conn, {"section_type": "project", "title": "项目经历"})
			entry = resume_center.create_entry(conn, {"section_id": section["id"], "title": "LeRobot 抓取"})
			material = resume_center.create_material(conn, {"entry_id": entry["id"], "content": "完成 VLA 抓取实验。"})

			version = resume_center.create_version(
				conn,
				{
					"name": "机器人岗位版本",
					"target_company": "示例公司",
					"target_title": "机器人工程师",
					"selected_material_ids": [material["id"]],
					"template_id": "classic-single",
				},
			)
			resume_center.update_profile(conn, {"basics": {"name": "新名字"}})
			saved = resume_center.get_version(conn, version["id"])

			self.assertEqual(saved["profile_snapshot"]["profile"]["basics"]["name"], "旧名字")
			self.assertEqual(saved["selected_material_ids"], [material["id"]])
			self.assertEqual(saved["profile_snapshot"]["template"]["id"], "classic-single")
			conn.close()

	def test_resume_version_tracks_selected_sections_entries_and_duplicate_snapshot(self):
		with tempfile.TemporaryDirectory() as tmp:
			conn = get_db(Path(tmp) / "bosshunter.db")
			section = resume_center.create_section(conn, {"section_type": "project", "title": "项目经历"})
			entry = resume_center.create_entry(conn, {"section_id": section["id"], "title": "ROS1 机械爪"})
			material = resume_center.create_material(conn, {"entry_id": entry["id"], "content": "控制三爪机械爪开合。"})
			version = resume_center.create_version(
				conn,
				{
					"name": "控制岗版本",
					"selected_section_ids": [section["id"]],
					"selected_entry_ids": [entry["id"]],
					"selected_material_ids": [material["id"]],
				},
			)
			copy = resume_center.duplicate_version(conn, version["id"], {"name": "控制岗版本复制"})

			self.assertEqual(version["selected_section_ids"], [section["id"]])
			self.assertEqual(version["selected_entry_ids"], [entry["id"]])
			self.assertEqual(copy["name"], "控制岗版本复制")
			self.assertEqual(copy["profile_snapshot"], version["profile_snapshot"])
			conn.close()

	def test_profile_photo_asset_round_trip(self):
		with tempfile.TemporaryDirectory() as tmp:
			conn = get_db(Path(tmp) / "bosshunter.db")
			photo = resume_center.save_profile_photo(conn, str(Path(tmp) / "photo.png"), "image/png", 1234)

			self.assertEqual(photo["asset_type"], "photo")
			self.assertEqual(photo["mime_type"], "image/png")
			self.assertEqual(photo["file_size"], 1234)
			deleted = resume_center.delete_profile_photo(conn)
			self.assertEqual(deleted["id"], "profile_photo")
			self.assertIsNone(resume_center.get_profile_photo(conn))
			conn.close()

	def test_resume_photo_extractor_reads_docx_embedded_image(self):
		content = make_docx_with_media("李雷\n项目经历\n机械臂抓取", {"image1.png": PNG_BYTES})

		photo = extract_resume_photo("old_resume.docx", content, max_bytes=5 * 1024 * 1024)

		self.assertIsNotNone(photo)
		self.assertEqual(photo.mime_type, "image/png")
		self.assertEqual(photo.content, PNG_BYTES)
		self.assertEqual(photo.suffix, ".png")

	def test_resume_version_export_builds_safe_pdf_from_snapshot(self):
		with tempfile.TemporaryDirectory() as tmp:
			conn = get_db(Path(tmp) / "bosshunter.db")
			resume_center.update_profile(
				conn,
				{
					"basics": {"name": "张三/机器人", "school": "昆明理工大学", "degree": "27届硕士"},
					"contacts": {"email": "zhangsan@example.com"},
					"education": [],
					"skills": ["ROS1"],
					"preferences": {},
				},
			)
			section = resume_center.create_section(conn, {"section_type": "project", "title": "项目经历"})
			entry = resume_center.create_entry(conn, {"section_id": section["id"], "title": "三爪机械爪"})
			material = resume_center.create_material(conn, {"entry_id": entry["id"], "content": "控制机械爪开合。"})
			version = resume_center.create_version(
				conn,
				{
					"name": "机器人/控制岗",
					"template_id": "classic-single",
					"selected_section_ids": [section["id"]],
					"selected_entry_ids": [entry["id"]],
					"selected_material_ids": [material["id"]],
				},
			)
			seen_html = {}

			def fake_renderer(html_text, output_path):
				seen_html["html"] = html_text
				output_path.write_bytes(b"%PDF-1.4\n% fake\n")
				return True

			path = export_resume_version_pdf(version, Path(tmp) / "exports", renderer=fake_renderer)

			self.assertTrue(path.is_file())
			self.assertEqual(path.suffix, ".pdf")
			self.assertNotIn("/", path.name)
			self.assertIn("张三_机器人_机器人_控制岗", path.name)
			self.assertIn("三爪机械爪", seen_html["html"])
			self.assertIn("控制机械爪开合", seen_html["html"])
			self.assertTrue(resume_version_filename(version).endswith(".pdf"))
			conn.close()

	def test_reactive_resume_export_uses_source_renderer_bridge(self):
		version = {
			"name": "Reactive 版本",
			"template_id": "reactive-azurill",
			"profile_snapshot": {
				"profile": {"basics": {"name": "李雷"}, "contacts": {}, "education": [], "skills": []},
				"sections": [],
				"template": {"id": "reactive-azurill"},
			},
		}

		def fake_reactive_renderer(version_arg, output_path, **kwargs):
			output_path.write_bytes(b"%PDF-1.4\n% reactive\n")
			self.assertEqual(version_arg, version)
			self.assertEqual(kwargs["template_id"], "reactive-azurill")
			return True

		with tempfile.TemporaryDirectory() as tmp, patch(
			"bosshunter.web.reactive_resume.render_reactive_resume_pdf",
			side_effect=fake_reactive_renderer,
		) as renderer:
			path = export_resume_version_pdf(version, Path(tmp) / "exports")
			self.assertTrue(path.is_file())

		renderer.assert_called_once()

	def test_build_reactive_resume_data_maps_resume_center_sections(self):
		version = {
			"name": "Reactive 版本",
			"template_id": "reactive-azurill",
			"profile_snapshot": {
				"profile": {
					"basics": {"name": "李雷", "degree": "27届硕士", "school": "昆明理工大学"},
					"contacts": {"email": "lilei@example.com", "phone": "13800000000"},
					"education": [
						{"school": "昆明理工大学", "major": "机械工程", "degree": "硕士", "detail": "研究方向：机器人"}
					],
					"skills": ["Python"],
					"preferences": {},
				},
				"sections": [
					{
						"id": "sec_project",
						"section_type": "project",
						"title": "项目经历",
						"summary": "",
						"entries": [
							{
								"title": "三爪机械爪控制",
								"start_date": "2025.01",
								"end_date": "2025.06",
								"description": "完成 ROS1 控制节点。",
								"materials": [{"content": "完成串口通信与抓取调试。"}],
							}
						],
					},
					{
						"id": "sec_skill",
						"section_type": "skill",
						"title": "技能证书",
						"summary": "",
						"entries": [{"title": "机器人开发", "description": "", "materials": [{"content": "ROS1"}]}],
					},
				],
			},
		}

		data = build_reactive_resume_data(version, template_id="reactive-azurill")

		self.assertEqual(data["metadata"]["template"], "azurill")
		self.assertEqual(data["basics"]["name"], "李雷")
		self.assertEqual(data["sections"]["education"]["items"][0]["school"], "昆明理工大学")
		self.assertEqual(data["sections"]["projects"]["items"][0]["name"], "三爪机械爪控制")
		self.assertIn("完成串口通信", data["sections"]["projects"]["items"][0]["description"])
		self.assertEqual(data["sections"]["skills"]["items"][0]["name"], "核心技能")
		self.assertEqual(data["sections"]["skills"]["items"][1]["name"], "机器人开发")
		self.assertIn("ROS1", data["sections"]["skills"]["items"][1]["keywords"])

	def test_resume_version_html_supports_two_column_template(self):
		version = {
			"name": "双栏版本",
			"template_id": "compact-two-column",
			"selected_section_ids": [],
			"selected_entry_ids": [],
			"selected_material_ids": [],
			"profile_snapshot": {
				"profile": {"basics": {"name": "李雷"}, "contacts": {}, "education": [], "skills": ["Python"]},
				"sections": [],
				"template": {"id": "compact-two-column"},
			},
		}
		html_text = resume_version_html(version)

		self.assertIn("two-column", html_text)
		self.assertIn("李雷", html_text)

	def test_resume_version_html_renders_reactive_template_variant(self):
		version = {
			"name": "外部模板版本",
			"template_id": "reactive-chikorita",
			"selected_section_ids": [],
			"selected_entry_ids": [],
			"selected_material_ids": [],
			"profile_snapshot": {
				"profile": {
					"basics": {"name": "李雷", "gender": "男"},
					"contacts": {"email": "lilei@example.com"},
					"education": [{"school": "昆明理工大学", "major": "机械工程", "degree": "硕士"}],
					"skills": ["Python"],
				},
				"sections": [
					{
						"id": "sec_project",
						"section_type": "project",
						"title": "项目经历",
						"summary": "",
						"entries": [{"title": "机器人项目", "description": "完成控制调试。", "materials": []}],
					}
				],
				"template": {
					"id": "reactive-chikorita",
					"layout": {"base_template": "compact-two-column"},
					"style": {"accent": "#7C93B5"},
				},
			},
		}

		html_text = resume_version_html(version)

		self.assertIn("reactive-template", html_text)
		self.assertIn("reactive-chikorita", html_text)
		self.assertIn("sidebar-solid", html_text)
		self.assertIn("header-main", html_text)
		self.assertIn("机器人项目", html_text)

	def test_resume_version_html_renders_azurill_source_layout(self):
		version = {
			"name": "Azurill 版本",
			"template_id": "reactive-azurill",
			"selected_section_ids": [],
			"selected_entry_ids": [],
			"selected_material_ids": [],
			"target_title": "机器人工程师",
			"profile_snapshot": {
				"profile": {
					"basics": {"name": "李雷", "gender": "男"},
					"contacts": {"email": "lilei@example.com", "phone": "13800000000"},
					"education": [{"school": "昆明理工大学", "major": "机械工程", "degree": "硕士"}],
					"skills": ["Python"],
				},
				"sections": [
					{
						"id": "sec_project",
						"section_type": "project",
						"title": "项目经历",
						"summary": "",
						"entries": [{"title": "机器人项目", "description": "完成控制调试。", "materials": []}],
					}
				],
				"template": {
					"id": "reactive-azurill",
					"layout": {"base_template": "compact-two-column"},
					"style": {"accent": "#3B82F6"},
				},
			},
		}

		html_text = resume_version_html(version)

		self.assertIn("azurill-source", html_text)
		self.assertIn("source-contact-row", html_text)
		self.assertIn("azurill-content-row", html_text)
		self.assertIn("azurill-sidebar", html_text)
		self.assertIn("azurill-main", html_text)
		self.assertIn("azurill-timeline-line", html_text)
		self.assertIn("azurill-timeline-dot", html_text)
		self.assertIn("azurill-timeline-content", html_text)
		self.assertIn("机器人工程师", html_text)

	def test_resume_version_html_renders_bronzor_source_layout(self):
		version = {
			"name": "Bronzor 版本",
			"template_id": "reactive-bronzor",
			"selected_section_ids": [],
			"selected_entry_ids": [],
			"selected_material_ids": [],
			"target_title": "机器人工程师",
			"profile_snapshot": {
				"profile": {
					"basics": {"name": "李雷"},
					"contacts": {"email": "lilei@example.com"},
					"education": [{"school": "昆明理工大学", "major": "机械工程", "degree": "硕士"}],
					"skills": ["Python"],
				},
				"sections": [
					{
						"id": "sec_project",
						"section_type": "project",
						"title": "项目经历",
						"summary": "",
						"entries": [{"title": "机器人项目", "description": "完成控制调试。", "materials": []}],
					}
				],
				"template": {
					"id": "reactive-bronzor",
					"layout": {"base_template": "compact-two-column"},
					"style": {"accent": "#4B5563"},
				},
			},
		}

		html_text = resume_version_html(version)

		self.assertIn("bronzor-source", html_text)
		self.assertIn("source-contact-row", html_text)
		self.assertIn("bronzor-section", html_text)
		self.assertIn("bronzor-section-items", html_text)
		self.assertNotIn("reactive-template reactive-bronzor sidebar-right", html_text)
		self.assertIn("机器人项目", html_text)

	def test_resume_version_html_renders_rendercv_template_variant(self):
		version = {
			"name": "RenderCV 版本",
			"template_id": "rendercv-harvard",
			"selected_section_ids": [],
			"selected_entry_ids": [],
			"selected_material_ids": [],
			"profile_snapshot": {
				"profile": {
					"basics": {"name": "李雷"},
					"contacts": {"email": "lilei@example.com"},
					"education": [{"school": "昆明理工大学", "major": "机械工程", "degree": "硕士"}],
					"skills": ["Python"],
				},
				"sections": [],
				"template": {
					"id": "rendercv-harvard",
					"layout": {"base_template": "classic-single"},
					"style": {"accent": "#7F1D1D"},
				},
			},
		}

		html_text = resume_version_html(version)

		self.assertIn("rendercv-template", html_text)
		self.assertIn("rendercv-harvard", html_text)
		self.assertIn("Times New Roman", html_text)
		self.assertIn("教育背景", html_text)

	def test_resume_version_markdown_builds_scoring_source_text(self):
		version = {
			"id": "ver_1234567890",
			"name": "机器人控制岗",
			"target_company": "示例公司",
			"target_title": "机器人工程师",
			"selected_section_ids": ["sec_project"],
			"selected_entry_ids": ["entry_gripper"],
			"selected_material_ids": ["mat_ros"],
			"profile_snapshot": {
				"profile": {
					"basics": {
						"name": "张三/机器人",
						"school": "昆明理工大学",
						"major": "机械工程",
						"degree": "27届硕士",
					},
					"contacts": {"email": "zhangsan@example.com"},
					"education": [{"school": "昆明理工大学", "major": "机械工程", "degree": "硕士"}],
					"skills": ["Python", "ROS1"],
					"preferences": {"self_evaluation": "关注机器人控制与感知。"},
				},
				"sections": [
					{
						"id": "sec_project",
						"section_type": "project",
						"title": "项目经历",
						"summary": "",
						"entries": [
							{
								"id": "entry_gripper",
								"title": "三爪机械爪",
								"organization": "实验室",
								"role": "控制开发",
								"description": "完成机械爪开合控制。",
								"materials": [
									{"id": "mat_ros", "content": "基于 ROS1 编写机械爪开合控制节点。"},
									{"id": "mat_unused", "content": "不应出现在当前版本。"},
								],
							}
						],
					}
				],
			},
		}

		markdown = resume_version_markdown(version)

		self.assertIn("# 张三/机器人", markdown)
		self.assertIn("目标：示例公司 · 机器人工程师", markdown)
		self.assertIn("## 教育背景", markdown)
		self.assertIn("## 技能证书", markdown)
		self.assertIn("### 三爪机械爪", markdown)
		self.assertIn("基于 ROS1 编写机械爪开合控制节点", markdown)
		self.assertNotIn("不应出现在当前版本", markdown)
		self.assertTrue(resume_version_markdown_filename(version).endswith(".md"))

	def test_resume_import_preview_and_confirm_append_structured_facts(self):
		markdown = """# 张三
昆明理工大学 机械工程专业 27届硕士
手机：13800138000 邮箱：zhangsan@example.com

## 专业技能
- Python、ROS1、PyTorch

## 项目经历
### 三爪机械爪
2024.03-2024.06 实验室 控制开发
完成机械爪开合控制与抓取调试。
- 基于 ROS1 编写机械爪开合控制节点。
- 记录抓取测试数据并分析问题。
"""
		draft = build_resume_import_preview("old.md", markdown)

		self.assertEqual(draft["profile"]["basics"]["name"], "张三")
		self.assertEqual(draft["profile"]["contacts"]["email"], "zhangsan@example.com")
		self.assertEqual(draft["profile"]["skills"], [])
		self.assertEqual(draft["stats"]["entries"], 3)
		self.assertTrue(any(section["section_type"] == "skill" for section in draft["sections"]))

		with tempfile.TemporaryDirectory() as tmp:
			conn = get_db(Path(tmp) / "bosshunter.db")
			resume_center.update_profile(conn, {"basics": {"name": "张三"}, "contacts": {}, "education": [], "skills": [], "preferences": {}})
			result = apply_resume_import_draft(conn, draft)
			sections = resume_center.list_sections(conn)
			profile = resume_center.get_profile(conn)

			self.assertTrue(result["success"])
			self.assertEqual(profile["skills"], [])
			project_section = next(section for section in sections if section["section_type"] == "project")
			skill_section = next(section for section in sections if section["section_type"] == "skill")
			self.assertEqual(project_section["entries"][0]["title"], "三爪机械爪")
			self.assertIn("基于 ROS1 编写机械爪开合控制节点。", project_section["entries"][0]["description"])
			self.assertIn("记录抓取测试数据并分析问题。", project_section["entries"][0]["description"])
			self.assertEqual(project_section["entries"][0]["materials"], [])
			self.assertEqual(skill_section["title"], "技能证书")
			skill_materials = [material["content"] for entry in skill_section["entries"] for material in entry["materials"]]
			self.assertIn("ROS1", skill_materials)
			conn.close()

	def test_import_groups_varied_skill_wording_by_semantic_category(self):
		draft = build_resume_import_preview(
			"old.pdf",
			"""李四

## 奖励证书
CET6；校三等奖学金（2024-2025）；校二等奖学金（2025-2026）

## 科研能力
机械与建模：精通 SolidWorks、CAD、Rhino 等机械建模设计软件；熟悉 ANSYS Fluent 仿真软件
自动化与控制：精通 KUKA 编程软件 WorkVisual 以及 KUKASimpro；精通 EPLAN 电气绘图软件；熟悉 STM32 编程软件 CUBEIDE
实践技能：绘制机械制造加工图纸；熟练使用 MTS 疲劳拉伸试验机

## 专业技能
- 编程能力：熟悉 Python，掌握 Pandas、NumPy、Matplotlib，具备数据处理及可视化能力
- 办公软件：熟练使用 Excel、Word、PowerPoint
- 英语能力：CET-4、CET-6
""",
		)

		sections = {section["section_type"]: section for section in draft["sections"]}
		self.assertIn("award", sections)
		self.assertIn("skill", sections)
		award_titles = [entry["title"] for entry in sections["award"]["entries"]]
		self.assertTrue(any("校三等奖学金" in title for title in award_titles))
		self.assertTrue(any("校二等奖学金" in title for title in award_titles))
		skill_entries = {entry["title"]: [material["content"] for material in entry["materials"]] for entry in sections["skill"]["entries"]}
		self.assertIn("语言能力", skill_entries)
		self.assertIn("编程与数据能力", skill_entries)
		self.assertIn("机械设计与建模", skill_entries)
		self.assertIn("仿真与分析", skill_entries)
		self.assertIn("自动化与控制", skill_entries)
		self.assertIn("实验与设备能力", skill_entries)
		self.assertIn("办公与通用工具", skill_entries)
		self.assertIn("CET-4", skill_entries["语言能力"])
		self.assertIn("CET-6", skill_entries["语言能力"])
		self.assertIn("Python", skill_entries["编程与数据能力"])
		self.assertIn("Pandas", skill_entries["编程与数据能力"])
		self.assertIn("SolidWorks", skill_entries["机械设计与建模"])
		self.assertIn("ANSYS", skill_entries["仿真与分析"])
		self.assertIn("KUKA", skill_entries["自动化与控制"])
		self.assertIn("MTS", skill_entries["实验与设备能力"])
		self.assertIn("Excel", skill_entries["办公与通用工具"])

	def test_import_splits_pdf_table_style_skill_labels_on_same_line(self):
		draft = build_resume_import_preview(
			"old.pdf",
			"""王五

## 技能证书
语言能力：CET-4、CET-6；普通话二级甲等 专业工具：MATLAB、LaTeX、几何画板
计算机能力：全国计算机二级，熟练使用 Office 办公软件 其他证书：高级中学数学教师资格证
""",
		)

		skill = next(section for section in draft["sections"] if section["section_type"] == "skill")
		entries = {entry["title"]: [material["content"] for material in entry["materials"]] for entry in skill["entries"]}
		self.assertIn("语言能力", entries)
		self.assertIn("编程与数据能力", entries)
		self.assertIn("办公与通用工具", entries)
		self.assertIn("职业证书", entries)
		self.assertIn("专业工具", entries)
		self.assertIn("CET-4", entries["语言能力"])
		self.assertIn("CET-6", entries["语言能力"])
		self.assertTrue(any("普通话" in item for item in entries["语言能力"]))
		self.assertIn("MATLAB", entries["编程与数据能力"])
		self.assertIn("LaTeX", entries["专业工具"])
		self.assertIn("Office", entries["办公与通用工具"])
		self.assertTrue(any("教师资格证" in item for item in entries["职业证书"]))

	def test_docx_bold_project_name_becomes_import_entry_title(self):
		markdown = docx_to_markdown(make_docx_with_bold_paragraph("三爪机械爪控制系统", "完成机械爪开合控制与抓取调试。"))
		draft = build_resume_import_preview("old.docx", f"# 张三\n\n## 项目经历\n{markdown}")

		project = next(section for section in draft["sections"] if section["section_type"] == "project")
		self.assertEqual(project["entries"][0]["title"], "三爪机械爪控制系统")

	def test_project_description_preserves_stack_and_action_line_breaks(self):
		draft = build_resume_import_preview(
			"old.pdf",
			"""张三

## 项目经历
机械臂VLA抓取项目
技术栈： Python · PyTorch · LeRobot · ACT · HuggingFace Hub · Feetech SDK · OpenCV · 串口通信 · Rerun
实现机械臂硬件平台搭建与舵机层配置：基于飞特 STS3215 串行总线舵机，完成 12 个舵机中位校准。
解决双臂遥操作核心工程难题：深入调试串行总线通信不稳定问题。
""",
		)

		project = next(section for section in draft["sections"] if section["section_type"] == "project")
		self.assertEqual(project["entries"][0]["title"], "机械臂VLA抓取项目")
		description = project["entries"][0]["description"]
		self.assertIn("技术栈： Python", description)
		self.assertIn("Rerun\n实现机械臂硬件平台搭建", description)
		self.assertIn("中位校准。\n解决双臂遥操作核心工程难题", description)
		self.assertEqual(project["entries"][0]["materials"], [])

	def test_project_import_uses_original_long_description_as_main_summary(self):
		draft = build_resume_import_preview(
			"old.pdf",
			"""张三

## 项目经历
电商用户分析平台
技术栈： MySQL / Python / Pandas / Streamlit / Prophet 数据分析： 基于 Olist 约 10 万笔订单、9 张业务表搭建 MySQL 分析数据库，使用 JOIN、CTE、窗口函数等完成 GMV、品类、物流、用户评价等核心指标分析。用户分层： 使用 RFM 方法划分用户层级。
""",
		)

		project = next(section for section in draft["sections"] if section["section_type"] == "project")
		entry = project["entries"][0]
		self.assertEqual(entry["title"], "电商用户分析平台")
		self.assertIn("技术栈： MySQL / Python / Pandas / Streamlit / Prophet", entry["description"])
		self.assertIn("Prophet\n数据分析：", entry["description"])
		self.assertIn("指标分析。\n用户分层：", entry["description"])
		self.assertEqual(entry["materials"], [])

	def test_ai_project_description_is_semantically_reflowed(self):
		ai_response = json.dumps(
			{
				"profile": {"basics": {"name": "张三"}, "contacts": {}, "education": [], "skills": [], "preferences": {}},
				"sections": [
					{
						"section_type": "project",
						"title": "项目经历",
						"summary": "",
						"entries": [
							{
								"title": "机械臂VLA抓取项目",
								"organization": "",
								"role": "",
								"start_date": "",
								"end_date": "",
								"description": "工具环境：Python · PyTorch · LeRobot · ACT实现机械臂硬件平台搭建与舵机层配置。解决双臂遥操作核心工程难题。",
								"materials": [],
							}
						],
					}
				],
				"warnings": [],
			},
			ensure_ascii=False,
		)
		with patch("bosshunter.web.resume_import_ai.get_ai_api_key", return_value="key"), patch(
			"bosshunter.web.resume_import_ai.call_anthropic_text", return_value=ai_response
		):
			draft = build_resume_import_preview(
				"old.pdf",
				"张三\n\n## 项目经历\n机械臂VLA抓取项目\n工具环境：Python · PyTorch · LeRobot · ACT实现机械臂硬件平台搭建与舵机层配置。",
				config={"ai": {"resume_import_enabled": True, "api_key": "key"}},
			)

		project = next(section for section in draft["sections"] if section["section_type"] == "project")
		description = project["entries"][0]["description"]
		self.assertIn("工具环境：Python · PyTorch · LeRobot · ACT\n实现机械臂硬件平台搭建", description)
		self.assertIn("配置。\n解决双臂遥操作核心工程难题", description)

	def test_project_description_reflows_when_saved(self):
		with tempfile.TemporaryDirectory() as tmp:
			conn = get_db(Path(tmp) / "bosshunter.db")
			section = resume_center.create_section(conn, {"section_type": "project", "title": "项目经历"})
			entry = resume_center.create_entry(
				conn,
				{
					"section_id": section["id"],
					"title": "机械臂VLA抓取项目",
					"description": "技术栈： Python · PyTorch · LeRobot · ACT · Rerun 实现机械臂硬件平台搭建与舵机层配置。解决双臂遥操作核心工程难题。",
				},
			)

			self.assertIn("Rerun\n实现机械臂硬件平台搭建", entry["description"])
			self.assertIn("配置。\n解决双臂遥操作核心工程难题", entry["description"])
			updated = resume_center.update_entry(
				conn,
				entry["id"],
				{
					"description": "工具环境：Python · PyTorch · LeRobot · ACT实现机械臂硬件平台搭建与舵机层配置。解决双臂遥操作核心工程难题。",
				},
			)
			self.assertIn("ACT\n实现机械臂硬件平台搭建", updated["description"])
			conn.close()

	def test_project_description_splits_inline_structured_labels(self):
		with tempfile.TemporaryDirectory() as tmp:
			conn = get_db(Path(tmp) / "bosshunter.db")
			section = resume_center.create_section(conn, {"section_type": "project", "title": "项目经历"})
			entry = resume_center.create_entry(
				conn,
				{
					"section_id": section["id"],
					"title": "多Agent PPT生成系统",
					"description": "技术栈： Python / OpenAI API / JSON / python-pptx。多 Agent 架构： 基于 YAML 角色配置、Jinja2 模板与 JSON 结构化输出。端到端生成： 搭建 planner → layout_selector → editor → coder → executor 流水线。工程化优化： 集成 PDF 文档解析与 LLM 内容提炼。",
				},
			)

			self.assertIn("python-pptx。\n多 Agent 架构：", entry["description"])
			self.assertIn("结构化输出。\n端到端生成：", entry["description"])
			self.assertIn("流水线。\n工程化优化：", entry["description"])
			conn.close()

	def test_project_description_splits_business_analysis_labels_without_period(self):
		with tempfile.TemporaryDirectory() as tmp:
			conn = get_db(Path(tmp) / "bosshunter.db")
			section = resume_center.create_section(conn, {"section_type": "project", "title": "项目经历"})
			entry = resume_center.create_entry(
				conn,
				{
					"section_id": section["id"],
					"title": "电商数据分析项目",
					"description": "技术栈： MySQL / Python / Pandas / Streamlit / Prophet 数据分析： 基于 Olist 约 10 万笔订单、9 张业务表搭建 MySQL 分析数据库，使用 JOIN、CTE、窗口函数等完成 GMV、品类、物流、用户评价等核心指标分析。用户洞察： 通过 Cohort、RFM 等方法分析用户留存与分层。",
				},
			)

			self.assertIn("Prophet\n数据分析：", entry["description"])
			self.assertIn("指标分析。\n用户洞察：", entry["description"])
			conn.close()

	def test_project_description_splits_generic_colon_headings_without_wordlist(self):
		description = format_entry_description_text(
			"技术栈： Python / SQL / Tableau 用户分层： 使用 RFM 方法划分用户层级。增长复盘： 对转化漏斗进行定位并输出建议。"
		)

		self.assertIn("Tableau\n用户分层：", description)
		self.assertIn("用户层级。\n增长复盘：", description)

	def test_project_description_does_not_split_explanatory_colons(self):
		with tempfile.TemporaryDirectory() as tmp:
			conn = get_db(Path(tmp) / "bosshunter.db")
			section = resume_center.create_section(conn, {"section_type": "project", "title": "项目经历"})
			entry = resume_center.create_entry(
				conn,
				{
					"section_id": section["id"],
					"title": "多Agent PPT生成系统",
					"description": "技术栈： Python / OpenAI API / JSON / python-pptx。多 Agent 架构： 基于 YAML 角色配置，例如：planner、editor、coder 三类角色。端到端生成： 搭建流水线，失败原因：模型偶发输出非法 JSON 时会触发修复。",
				},
			)

			self.assertIn("python-pptx。\n多 Agent 架构：", entry["description"])
			self.assertIn("三类角色。\n端到端生成：", entry["description"])
			self.assertIn("例如：planner", entry["description"])
			self.assertNotIn("\n例如：", entry["description"])
			self.assertIn("失败原因：模型偶发输出非法 JSON", entry["description"])
			self.assertNotIn("\n失败原因：", entry["description"])
			self.assertNotIn("端到端生成：\n搭建", entry["description"])
			conn.close()

	def test_education_supplements_attach_to_matching_stage(self):
		draft = build_resume_import_preview(
			"old.md",
			"""# 张三
昆明理工大学 - 机械工程 - 硕士 2024.09 - 2027.06
齐鲁工业大学（山东省科学院） - 机械设计制造及其自动化 - 本科 2020.09 - 2024.06

## 教育背景
研究方向：机器人感知与智能识别
主修课程：机械原理，机械设计，数值分析
在校荣誉：第十三届全国大学生数学竞赛（非数学类）一等奖
""",
		)

		education = draft["profile"]["education"]
		self.assertIn("研究方向：机器人感知与智能识别", education[0]["detail"])
		self.assertIn("主修课程：机械原理", education[0]["detail"])
		self.assertNotIn("在校荣誉", education[0]["detail"])
		self.assertIn("在校荣誉：第十三届全国大学生数学竞赛", education[1]["detail"])

	def test_import_handles_spaced_pdf_headings_and_labeled_name(self):
		draft = build_resume_import_preview(
			"old.pdf",
			"""姓名：刘纪航 出生年月：2001年4月
学历：硕士研究生 电 话：15325580271
邮箱：614509068@qq.com 籍 贯：江苏连云港
教 育 背 景
昆明理工大学 （硕士研究生） 机械工程 2024.9-2027.6
主修课程：现代控制工程、现代设计理论
研究方向：轻量化异种材料铆接
台州学院（学士） 机械设计制造及其自动化 2022.9-2024.6
主修课程：机械原理、机械设计
项目经历
 乘用车镁合金薄板材料实心铆连接工艺试验（广州汽车集团合作项目） 2025.2-2025.8
开展镁合金薄板材料实心铆连接工艺试验。
奖 励 证 书
CET6；校三等奖学金（2024-2025）
职 业 技 能
熟悉Abaqus、Solidworks、AutoCAD。
自 我 评 价
本人工作态度认真，责任感强。
""",
		)

		self.assertEqual(draft["profile"]["basics"]["name"], "刘纪航")
		self.assertEqual(draft["profile"]["basics"]["birth_date"], "2001年4月")
		self.assertEqual(draft["profile"]["basics"]["native_place"], "江苏连云港")
		education = draft["profile"]["education"]
		self.assertEqual(education[0]["school"], "昆明理工大学")
		self.assertEqual(education[0]["degree"], "硕士")
		self.assertEqual(education[0]["major"], "机械工程")
		self.assertIn("主修课程：现代控制工程", education[0]["detail"])
		self.assertNotIn("昆明理工大学", education[0]["detail"])
		self.assertNotIn("机械工程", education[0]["detail"])
		self.assertEqual(education[1]["school"], "台州学院")
		self.assertEqual(education[1]["degree"], "本科")
		self.assertEqual(education[1]["major"], "机械设计制造及其自动化")
		sections = {section["section_type"]: section for section in draft["sections"]}
		self.assertIn("project", sections)
		self.assertIn("award", sections)
		self.assertIn("skill", sections)
		self.assertIn("self_evaluation", sections)
		self.assertEqual(sections["project"]["entries"][0]["title"], "乘用车镁合金薄板材料实心铆连接工艺试验（广州汽车集团合作项目）")
		self.assertNotIn("奖励证书", [entry["title"] for entry in sections["project"]["entries"]])
		award_titles = [entry["title"] for entry in sections["award"]["entries"]]
		self.assertTrue(any("校三等奖学金" in title for title in award_titles))
		skill_materials = [
			material["content"]
			for entry in sections["skill"]["entries"]
			for material in entry["materials"]
		]
		self.assertIn("CET6", skill_materials)
		self.assertTrue(any("Abaqus" in material for material in skill_materials))

	def test_import_handles_degree_lines_before_education_rows(self):
		draft = build_resume_import_preview(
			"old.pdf",
			"""李 颖
电话：15087232602
政治面貌：共青团员
邮箱：675200311@qq.com
教育背景
硕士研究生
本科
2024.09-2027.07 云南民族大学 应用数学
GPA 3.79/4.0  |  专业前 5 %  主修：高等概率论、泛函分析
2020.09-2024.07 云南民族大学 数学与应用数学
GPA 3.58/4.0  |  专业前 5%  主修：数学分析、高等代数、教育学原理
科研成果
已发表（IEEE） Robust Integral Sliding Mode Boundary Control.
荣誉奖项
2025.11 研究生学业奖学金二等奖
技能证书
语言能力：CET-4、CET-6
个人优势
数学本硕专业背景，逻辑分析能力较强。
""",
		)

		self.assertEqual(draft["profile"]["basics"]["name"], "李 颖")
		education = draft["profile"]["education"]
		self.assertEqual(education[0]["school"], "云南民族大学")
		self.assertEqual(education[0]["degree"], "硕士")
		self.assertEqual(education[0]["major"], "应用数学")
		self.assertIn("GPA 3.79", education[0]["detail"])
		self.assertNotIn("云南民族大学 应用数学", education[0]["detail"])
		self.assertEqual(education[1]["school"], "云南民族大学")
		self.assertEqual(education[1]["degree"], "本科")
		self.assertEqual(education[1]["major"], "数学与应用数学")
		self.assertIn("GPA 3.58", education[1]["detail"])
		self.assertIn("教育学原理", education[1]["detail"])
		self.assertNotIn("云南民族大学 数学与应用数学", education[1]["detail"])
		section_types = {section["section_type"] for section in draft["sections"]}
		self.assertIn("academic", section_types)
		self.assertIn("award", section_types)
		self.assertIn("skill", section_types)
		self.assertIn("self_evaluation", section_types)

	def test_import_routes_inline_academic_results_out_of_education(self):
		draft = build_resume_import_preview(
			"old.pdf",
			"""姓名：刘纪航

## 教育背景
昆明理工大学 （硕士研究生） 机械工程 2024.9-2027.6
主修课程：现代控制工程、现代设计理论
科研成果：（1）Study on Corrosion Failure of Steel/Aluminum Clinched Joints under Synergistic Salt Spray-Load Corrosion Environment（SCI 三区在投）
台州学院（学士） 机械设计制造及其自动化 2022.9-2024.6
""",
		)

		education_detail = " ".join(item.get("detail", "") for item in draft["profile"]["education"])
		self.assertNotIn("科研成果", education_detail)
		academic = next(section for section in draft["sections"] if section["section_type"] == "academic")
		self.assertIn("Study on Corrosion Failure", academic["entries"][0]["title"])
		self.assertNotIn("（1）", academic["entries"][0]["title"])
		self.assertEqual(academic["entries"][0]["end_date"], "在投")
		self.assertEqual(academic["entries"][0]["metadata"]["result_type"], "论文")
		self.assertIn("SCI", academic["entries"][0]["metadata"]["indexing"])
		self.assertIn("三区", academic["entries"][0]["metadata"]["indexing"])

	def test_import_splits_numbered_inline_academic_results(self):
		draft = build_resume_import_preview(
			"old.pdf",
			"""姓名：刘纪航

## 教育背景
昆明理工大学 （硕士研究生） 机械工程 2024.9-2027.6
科研成果：（1） Study on the Corrosion Failure of Steel/Aluminum Adhesively Bonded Self-Piercing Riveted Joints in a Synergistic Cl-
and HSO3-Environment[J]. Journal of Materials Engineering and Performance.(SCI一作）
（2）Study on Corrosion Failure of Steel/Aluminum Clinched Joints under Synergistic Salt Spray-Load Corrosion Environment（sci 三区在投）
台州学院（学士） 机械设计制造及其自动化 2022.9-2024.6
""",
		)

		academic = next(section for section in draft["sections"] if section["section_type"] == "academic")
		self.assertEqual(len(academic["entries"]), 2)
		self.assertEqual(
			academic["entries"][0]["title"],
			"Study on the Corrosion Failure of Steel/Aluminum Adhesively Bonded Self-Piercing Riveted Joints in a Synergistic Cl- and HSO3-Environment",
		)
		self.assertEqual(academic["entries"][0]["organization"], "Journal of Materials Engineering and Performance")
		self.assertEqual(academic["entries"][0]["role"], "第一作者")
		self.assertEqual(academic["entries"][0]["end_date"], "")
		self.assertEqual(academic["entries"][0]["metadata"]["indexing"], "SCI")
		self.assertEqual(
			academic["entries"][1]["title"],
			"Study on Corrosion Failure of Steel/Aluminum Clinched Joints under Synergistic Salt Spray-Load Corrosion Environment",
		)
		self.assertEqual(academic["entries"][1]["end_date"], "在投")
		self.assertIn("SCI", academic["entries"][1]["metadata"]["indexing"])
		self.assertIn("三区", academic["entries"][1]["metadata"]["indexing"])

	def test_import_uses_ai_structured_layer_when_configured(self):
		ai_response = json.dumps(
			{
				"profile": {
					"basics": {"name": "刘纪航"},
					"contacts": {"phone": "15325580271", "email": "614509068@qq.com"},
					"education": [
						{"school": "昆明理工大学", "major": "机械工程", "degree": "硕士研究生", "start_date": "2024.9", "end_date": "2027.6", "detail": ""}
					],
					"skills": ["Abaqus"],
					"preferences": {},
				},
				"sections": [
					{
						"section_type": "academic",
						"title": "学术成果",
						"summary": "",
						"entries": [
							{
								"title": "Study on the Corrosion Failure of Steel/Aluminum Adhesively Bonded Self-Piercing Riveted Joints in a Synergistic Cl- and HSO3-Environment",
								"organization": "Journal of Materials Engineering and Performance",
								"role": "第一作者",
								"start_date": "",
								"end_date": "SCI",
								"description": "",
								"materials": [],
							},
							{
								"title": "Study on Corrosion Failure of Steel/Aluminum Clinched Joints under Synergistic Salt Spray-Load Corrosion Environment",
								"organization": "",
								"role": "",
								"start_date": "",
								"end_date": "SCI 三区在投",
								"description": "",
								"materials": [],
							},
						],
					},
					{
						"section_type": "self_evaluation",
						"title": "综合评价",
						"summary": "",
						"entries": [
							{
								"title": "综合评价",
								"organization": "应清空",
								"role": "应清空",
								"start_date": "2025",
								"end_date": "今",
								"description": "具备材料试验与论文写作经验。",
								"materials": [],
							}
						],
					},
				],
				"warnings": [],
			},
			ensure_ascii=False,
		)
		with patch("bosshunter.web.resume_import_ai.get_ai_api_key", return_value="key"), patch(
			"bosshunter.web.resume_import_ai.call_anthropic_text", return_value=ai_response
		):
			draft = build_resume_import_preview(
				"old.pdf",
				"""刘纪航

## 教育背景
昆明理工大学 （硕士研究生） 机械工程 2024.9-2027.6
科研成果：（1）坏标题

## 自我评价
具备材料试验与论文写作经验。
""",
				config={"ai": {"resume_import_enabled": True, "api_key": "key"}},
			)

		academic = next(section for section in draft["sections"] if section["section_type"] == "academic")
		self.assertEqual(len(academic["entries"]), 2)
		self.assertNotIn("（1）", academic["entries"][0]["title"])
		self.assertEqual(academic["entries"][0]["organization"], "Journal of Materials Engineering and Performance")
		self.assertEqual(academic["entries"][0]["metadata"]["indexing"], "SCI")
		evaluation = next(section for section in draft["sections"] if section["section_type"] == "self_evaluation")
		self.assertEqual(evaluation["entries"][0]["organization"], "")
		self.assertEqual(evaluation["entries"][0]["role"], "")
		self.assertEqual(evaluation["entries"][0]["start_date"], "")
		self.assertEqual(evaluation["entries"][0]["end_date"], "")

	def test_import_splits_practice_entries_and_academic_status_items(self):
		draft = build_resume_import_preview(
			"old.pdf",
			"""李 颖

## 重点实践经历
2025-至今 课题组助理 • 协助票据分类整理、账目核对与资料归档。
• 按项目事项汇总日常材料。
2024.09-2026.06 研究生分会干事 • 参与学院学风建设、学术活动通知推送。
2025.09-2026.01 数学分析课程助教 • 批改本科课程作业。

## 科研成果
已发表（IEEE） Li, Y.; Xiong, L.; Zhang, H. Robust Integral Sliding Mode Boundary Control for Uncertain Time-Delay Semi-Markov Jump Reaction-
Diffusion Systems. 2026 38th Chinese Control and Decision Conference (CCDC), IEEE, 2026.
在投 Observer-Based Robust Sliding Mode Boundary Control for Uncertain Delayed Semi-Markovian Reaction-Diffusion Systems.
能力沉淀 研究过程中持续训练英文文献阅读、逻辑推导、数学建模与规范写作能力。

## 校园与社会实践
2021-2023 楚雄社区志愿者 参与社区便民公益活动。
2022.07-2022.08 学校资助宣传志愿者 寒暑假返乡宣传国家助学政策。
2020.09-2022.06 班级学习委员 对接任课教师与班级同学。
2021.07-2022.02 初高中数学私教辅导 根据对象差异梳理需求。
""",
		)

		campus = next(section for section in draft["sections"] if section["section_type"] == "campus")
		self.assertEqual(
			[entry["title"] for entry in campus["entries"]],
			["课题组助理", "研究生分会干事", "数学分析课程助教", "楚雄社区志愿者", "学校资助宣传志愿者", "班级学习委员", "初高中数学私教辅导"],
		)
		self.assertIn("协助票据分类整理", campus["entries"][0]["description"])
		academic = next(section for section in draft["sections"] if section["section_type"] == "academic")
		self.assertEqual(len(academic["entries"]), 2)
		self.assertIn("Robust Integral Sliding Mode Boundary Control", academic["entries"][0]["title"])
		self.assertIn("Observer-Based Robust Sliding Mode Boundary Control", academic["entries"][1]["title"])
		self.assertNotIn("已发表", academic["entries"][0]["title"])
		self.assertEqual(academic["entries"][0]["end_date"], "已发表")
		self.assertEqual(academic["entries"][0]["metadata"]["indexing"], "IEEE")
		self.assertEqual(academic["entries"][0]["start_date"], "2026")
		self.assertIn("2026 38th Chinese Control and Decision Conference", academic["entries"][0]["organization"])
		self.assertEqual(academic["entries"][1]["end_date"], "在投")
		self.assertFalse(any("能力沉淀" in entry["title"] for entry in academic["entries"]))

	def test_import_splits_award_date_and_clears_duplicate_description(self):
		draft = build_resume_import_preview(
			"old.pdf",
			"""李 颖

## 荣誉奖项
2025.
11 研究生学业奖学金二等奖（累计 2 次） 2025.11 “守学术初心·铸创新脊梁”科学道德与学风建设月征文比
赛一等奖
2023.11 2022-2023 学年云南民族大学优秀学生奖学金二等奖
2021.11 2020-2021 学年国家励志奖学金 本科阶段 省级优秀毕业生

## 个人优势
数学本硕专业背景，本科与研究生阶段均位列专业前 5%，数字敏感度、逻辑分析和快速学习能力较强。具备票据整理、账目核对、材料汇总
归档、活动会务、政策宣传、信息协调及志愿服务等实践经验。
""",
		)

		award = next(section for section in draft["sections"] if section["section_type"] == "award")
		self.assertEqual(award["entries"][0]["start_date"], "2025.11")
		self.assertEqual(award["entries"][0]["title"], "研究生学业奖学金二等奖（累计 2 次）")
		self.assertEqual(award["entries"][0]["description"], "")
		self.assertEqual(award["entries"][1]["start_date"], "2025.11")
		self.assertEqual(award["entries"][1]["title"], "“守学术初心·铸创新脊梁”科学道德与学风建设月征文比赛一等奖")
		self.assertEqual(award["entries"][3]["start_date"], "2021.11")
		self.assertEqual(award["entries"][3]["title"], "2020-2021 学年国家励志奖学金")
		self.assertEqual(award["entries"][4]["start_date"], "")
		self.assertEqual(award["entries"][4]["title"], "省级优秀毕业生")
		evaluation = next(section for section in draft["sections"] if section["section_type"] == "self_evaluation")
		self.assertIn("材料汇总归档", evaluation["entries"][0]["description"])
		self.assertNotIn("材料汇总\n归档", evaluation["entries"][0]["description"])

	def test_academic_import_splits_papers_and_patents(self):
		draft = build_resume_import_preview(
			"old.md",
			"""# 张三

## 学术成果
论文
论文名称：机器人感知与智能识别方法研究；状态：在投；期刊名称：机器人；作者情况：第一作者
专利
专利名称：一种三爪机械夹持装置；专利类型：发明专利；作者情况：第二发明人
""",
		)

		academic = next(section for section in draft["sections"] if section["section_type"] == "academic")
		self.assertEqual([entry["title"] for entry in academic["entries"]], ["机器人感知与智能识别方法研究", "一种三爪机械夹持装置"])
		self.assertEqual(academic["entries"][0]["organization"], "机器人")
		self.assertEqual(academic["entries"][1]["organization"], "发明专利")
		self.assertEqual(academic["entries"][0]["role"], "第一作者")
		self.assertEqual(academic["entries"][0]["end_date"], "在投")
		self.assertEqual(academic["entries"][0]["metadata"]["result_type"], "论文")
		self.assertEqual(academic["entries"][1]["metadata"]["result_type"], "专利")
		self.assertEqual(academic["entries"][0]["description"], "")

	def test_academic_import_parses_citation_year_status_and_indexing(self):
		draft = build_resume_import_preview(
			"old.pdf",
			"""# 李颖

## 学术成果
" Support-free fabrication of overhanging structures in laser powder directed energy deposition using hybrid planar and  non-planar slicing ", Rapid Prototyping Journal, 2026. (JCR一区)
Li, Y.; Xiong, L.; Zhang, H. Robust Integral Sliding Mode Boundary Control for Uncertain Time-Delay Semi-Markov Jump Reaction Diffusion Systems. 2026 38th Chinese Control and Decision Conference (CCDC), IEEE, 2026.
StudyontheCorrosionFailureof Steel/Aluminum Adhesively Bonded Self-Piercing Riveted Joints in a Synergistic Cl and HSO3-Environment[J]. Journal of Materials Engineering and Performance.(SCI一作）
StudyonCorrosion Failure of Steel/Aluminum Clinched Joints under Synergistic Salt Spray-Load Corrosion Environment（sci 三区在投）
""",
		)

		academic = next(section for section in draft["sections"] if section["section_type"] == "academic")
		self.assertEqual(len(academic["entries"]), 4)
		self.assertEqual(academic["entries"][0]["organization"], "Rapid Prototyping Journal")
		self.assertEqual(academic["entries"][0]["start_date"], "2026")
		self.assertEqual(academic["entries"][0]["end_date"], "")
		self.assertEqual(academic["entries"][0]["metadata"]["indexing"], "JCR一区")
		self.assertIn("Robust Integral", academic["entries"][1]["title"])
		self.assertIn("Chinese Control and Decision Conference", academic["entries"][1]["organization"])
		self.assertEqual(academic["entries"][1]["start_date"], "2026")
		self.assertEqual(academic["entries"][2]["role"], "第一作者")
		self.assertEqual(academic["entries"][2]["metadata"]["indexing"], "SCI")
		self.assertEqual(academic["entries"][3]["end_date"], "在投")
		self.assertIn("三区", academic["entries"][3]["metadata"]["indexing"])

	def test_template_import_creates_user_template_with_base_layout(self):
		draft = build_template_import_preview(
			"robot-template.md",
			"""姓名
电话
邮箱
教育经历
专业技能
项目经历
科研经历
荣誉证书
""",
		)
		self.assertEqual(draft["base_template"], "compact-two-column")
		with tempfile.TemporaryDirectory() as tmp:
			conn = get_db(Path(tmp) / "bosshunter.db")
			template = create_template_from_import_draft(conn, draft)

			self.assertEqual(template["source_type"], "user")
			self.assertEqual(template["layout"]["base_template"], "compact-two-column")
			conn.close()

	def test_deleting_user_template_detaches_existing_versions(self):
		with tempfile.TemporaryDirectory() as tmp:
			conn = get_db(Path(tmp) / "bosshunter.db")
			template = resume_center.create_template(
				conn,
				{
					"name": "导入模板",
					"template_type": "imported-doc",
					"source_type": "user",
					"layout": {"base_template": "classic-single"},
					"style": {},
				},
			)
			version = resume_center.create_version(conn, {"name": "模板版本", "template_id": template["id"]})

			resume_center.delete_template(conn, template["id"])
			saved = resume_center.get_version(conn, version["id"])

			self.assertIsNone(saved["template_id"])
			self.assertEqual(saved["profile_snapshot"]["template"]["id"], template["id"])
			conn.close()

	def test_jd_customizer_creates_version_from_matching_materials(self):
		with tempfile.TemporaryDirectory() as tmp:
			conn = get_db(Path(tmp) / "bosshunter.db")
			resume_center.update_profile(conn, {"basics": {"name": "张三"}, "contacts": {}, "education": [], "skills": [], "preferences": {}})
			section = resume_center.create_section(conn, {"section_type": "project", "title": "项目经历"})
			entry = resume_center.create_entry(conn, {"section_id": section["id"], "title": "三爪机械爪"})
			matched = resume_center.create_material(conn, {"entry_id": entry["id"], "content": "基于 ROS1 编写机械爪开合控制节点。", "tags": ["ROS1", "机器人控制"]})
			unmatched = resume_center.create_material(conn, {"entry_id": entry["id"], "content": "制作电商数据分析看板。", "tags": ["电商"]})
			job = {
				"id": "job-robot-1",
				"title": "机器人工程师",
				"company": "示例机器人",
				"jd": "负责 ROS1 机器人控制与机械爪抓取调试。",
			}

			result = create_resume_version_for_job(conn, job)

			self.assertTrue(result["success"])
			version = result["version"]
			self.assertIn(matched["id"], version["selected_material_ids"])
			self.assertNotIn(unmatched["id"], version["selected_material_ids"])
			self.assertEqual(version["target_job_id"], "job-robot-1")
			conn.close()

	def test_rejects_bad_json_shapes(self):
		with tempfile.TemporaryDirectory() as tmp:
			conn = get_db(Path(tmp) / "bosshunter.db")

			with self.assertRaises(ValueError):
				resume_center.update_profile(conn, {"basics": []})

			conn.close()


class ResumeCenterApiTests(unittest.TestCase):
	def setUp(self):
		self.original_base_dir = server.BASE_DIR

	def tearDown(self):
		server.set_base_dir(self.original_base_dir)

	def _request(self, path: str, method: str = "GET", json_body: dict | None = None):
		status_headers = {}
		if "?" in path:
			path_info, query_string = path.split("?", 1)
		else:
			path_info, query_string = path, ""

		def start_response(status, headers, exc_info=None):
			status_headers["status"] = status
			status_headers["headers"] = dict(headers)

		request_body = json.dumps(json_body).encode("utf-8") if json_body is not None else b""
		environ = {
			"REQUEST_METHOD": method,
			"PATH_INFO": path_info,
			"QUERY_STRING": query_string,
			"SERVER_NAME": "127.0.0.1",
			"SERVER_PORT": "8686",
			"wsgi.version": (1, 0),
			"wsgi.url_scheme": "http",
			"wsgi.input": io.BytesIO(request_body),
			"wsgi.errors": io.StringIO(),
			"wsgi.multithread": False,
			"wsgi.multiprocess": False,
			"wsgi.run_once": False,
		}
		if json_body is not None:
			environ["CONTENT_TYPE"] = "application/json"
			environ["CONTENT_LENGTH"] = str(len(request_body))

		result = server.app(environ, start_response)
		try:
			body = b"".join(
				chunk if isinstance(chunk, bytes) else chunk.encode("utf-8")
				for chunk in result
			).decode("utf-8")
		finally:
			close = getattr(result, "close", None)
			if callable(close):
				close()
		return status_headers["status"], status_headers["headers"], body

	def test_resume_center_api_profile_and_version_flow(self):
		with tempfile.TemporaryDirectory() as tmp:
			base_dir = Path(tmp)
			(base_dir / "config.yaml").write_text("{}\n", encoding="utf-8")
			server.set_base_dir(base_dir)

			status, _, body = self._request(
				"/api/resume/profile",
				method="PUT",
				json_body={"basics": {"name": "李雷"}, "contacts": {}, "education": [], "skills": [], "preferences": {}},
			)
			self.assertTrue(status.startswith("200"), body)
			self.assertEqual(json.loads(body)["basics"]["name"], "李雷")

			status, _, body = self._request(
				"/api/resume/versions",
				method="POST",
				json_body={"name": "默认版本", "template_id": "classic-single"},
			)
			self.assertTrue(status.startswith("201"), body)
			self.assertEqual(json.loads(body)["profile_snapshot"]["profile"]["basics"]["name"], "李雷")

			status, _, body = self._request("/api/resume/center")
			payload = json.loads(body)
			self.assertTrue(status.startswith("200"), body)
			self.assertEqual(payload["profile"]["basics"]["name"], "李雷")
			self.assertEqual(len(payload["versions"]), 1)

	def test_resume_center_api_reset_clears_user_resume_center_data(self):
		with tempfile.TemporaryDirectory() as tmp:
			base_dir = Path(tmp)
			(base_dir / "config.yaml").write_text("{}\n", encoding="utf-8")
			server.set_base_dir(base_dir)
			db = get_db(base_dir / "data" / "bosshunter.db")
			photo_path = base_dir / "data" / "resume_assets" / "profile_photo_test.png"
			photo_path.parent.mkdir(parents=True, exist_ok=True)
			photo_path.write_bytes(PNG_BYTES)
			resume_center.update_profile(db, {"basics": {"name": "李雷"}, "contacts": {"email": "lilei@example.com"}, "education": [{"school": "昆明理工大学"}], "skills": [], "preferences": {}})
			resume_center.save_profile_photo(db, str(photo_path), "image/png", len(PNG_BYTES))
			section = resume_center.create_section(db, {"section_type": "project", "title": "项目经历"})
			entry = resume_center.create_entry(db, {"section_id": section["id"], "title": "LeRobot 抓取"})
			resume_center.create_material(db, {"entry_id": entry["id"], "content": "完成抓取实验。"})
			resume_center.create_template(db, {"name": "用户模板", "template_type": "imported-doc", "source_type": "user"})
			resume_center.create_version(db, {"name": "测试版本", "template_id": "classic-single"})
			db.close()

			status, _, body = self._request("/api/resume/center/reset", method="POST")

			self.assertTrue(status.startswith("200"), body)
			payload = json.loads(body)
			self.assertTrue(payload["success"])
			self.assertFalse(photo_path.exists())
			center = payload["center"]
			self.assertEqual(center["profile"]["basics"], {})
			self.assertEqual(center["profile"]["education"], [])
			self.assertEqual(center["sections"], [])
			self.assertEqual(center["versions"], [])
			self.assertIsNone(center["photo"])
			self.assertEqual({item["source_type"] for item in center["templates"]}, {"builtin"})

	def test_resume_center_api_exports_version_pdf_download(self):
		with tempfile.TemporaryDirectory() as tmp:
			base_dir = Path(tmp)
			(base_dir / "config.yaml").write_text("{}\n", encoding="utf-8")
			server.set_base_dir(base_dir)
			db = get_db(base_dir / "data" / "bosshunter.db")
			resume_center.update_profile(db, {"basics": {"name": "李雷"}})
			version = resume_center.create_version(db, {"name": "测试版本", "template_id": "classic-single"})
			db.close()
			pdf_path = base_dir / "data" / "resume_exports" / "李雷_测试版本_20260912.pdf"
			pdf_path.parent.mkdir(parents=True, exist_ok=True)
			pdf_path.write_bytes(b"%PDF-1.4\n")

			with patch("bosshunter.web.server.export_resume_version_pdf", return_value=pdf_path):
				status, headers, body = self._request(f"/api/resume/export-pdf?version_id={version['id']}")

			self.assertTrue(status.startswith("200"), body)
			self.assertIn("application/pdf", headers.get("Content-Type", ""))
			self.assertIn("PDF", body)

	def test_resume_center_api_use_version_updates_active_resume_path(self):
		with tempfile.TemporaryDirectory() as tmp:
			base_dir = Path(tmp)
			(base_dir / "config.yaml").write_text("{}\n", encoding="utf-8")
			server.set_base_dir(base_dir)
			db = get_db(base_dir / "data" / "bosshunter.db")
			resume_center.update_profile(
				db,
				{
					"basics": {"name": "李雷", "school": "昆明理工大学", "degree": "27届硕士"},
					"contacts": {"email": "lilei@example.com"},
					"education": [],
					"skills": ["ROS1"],
					"preferences": {},
				},
			)
			section = resume_center.create_section(db, {"section_type": "project", "title": "项目经历"})
			entry = resume_center.create_entry(db, {"section_id": section["id"], "title": "三爪机械爪"})
			material = resume_center.create_material(db, {"entry_id": entry["id"], "content": "控制机械爪开合。"})
			version = resume_center.create_version(
				db,
				{
					"name": "机器人岗位版本",
					"selected_section_ids": [section["id"]],
					"selected_entry_ids": [entry["id"]],
					"selected_material_ids": [material["id"]],
				},
			)
			db.close()

			status, _, body = self._request(
				"/api/resume/use-version",
				method="POST",
				json_body={"version_id": version["id"]},
			)

			payload = json.loads(body)
			self.assertTrue(status.startswith("200"), body)
			self.assertTrue(payload["success"])
			resume_path = Path(payload["path"])
			self.assertTrue(resume_path.is_file())
			self.assertEqual(resume_path.suffix, ".md")
			self.assertIn("控制机械爪开合", resume_path.read_text(encoding="utf-8"))

			config = yaml.safe_load((base_dir / "config.yaml").read_text(encoding="utf-8"))
			self.assertEqual(config["profile"]["resume_path"], str(resume_path.resolve()))
			self.assertEqual(config["profile"]["resume_generation_source"], "resume_center_version")
			self.assertEqual(config["profile"]["resume_version_id"], version["id"])

			status, _, body = self._request("/api/resume")
			self.assertTrue(status.startswith("200"), body)
			self.assertIn("控制机械爪开合", json.loads(body)["content"])

	def test_resume_center_api_import_confirm_writes_draft_after_confirmation(self):
		with tempfile.TemporaryDirectory() as tmp:
			base_dir = Path(tmp)
			(base_dir / "config.yaml").write_text("{}\n", encoding="utf-8")
			server.set_base_dir(base_dir)
			draft = build_resume_import_preview(
				"old.md",
				"""# 李雷

## 专业技能
- ROS1

## 项目经历
### 机械臂抓取
- 完成示教数据采集。
""",
			)

			status, _, body = self._request(
				"/api/resume/import-confirm",
				method="POST",
				json_body={"draft": draft},
			)

			self.assertTrue(status.startswith("200"), body)
			payload = json.loads(body)
			self.assertTrue(payload["success"])
			self.assertEqual(payload["imported"]["entries"], 2)
			db = get_db(base_dir / "data" / "bosshunter.db")
			try:
				sections = resume_center.list_sections(db)
				project_section = next(section for section in sections if section["section_type"] == "project")
				self.assertEqual(project_section["entries"][0]["title"], "机械臂抓取")
			finally:
				db.close()

	def test_resume_center_api_import_confirm_promotes_photo_candidate(self):
		with tempfile.TemporaryDirectory() as tmp:
			base_dir = Path(tmp)
			(base_dir / "config.yaml").write_text("{}\n", encoding="utf-8")
			server.set_base_dir(base_dir)
			asset_dir = base_dir / "data" / "resume_assets"
			asset_dir.mkdir(parents=True, exist_ok=True)
			candidate_name = f"{server.RESUME_IMPORT_PHOTO_PREFIX}test.png"
			(asset_dir / candidate_name).write_bytes(PNG_BYTES)
			draft = build_resume_import_preview(
				"old.md",
				"""# 李雷

## 专业技能
- ROS1

## 项目经历
### 机械臂抓取
- 完成示教数据采集。
""",
			)
			draft["photo_candidate"] = {
				"filename": candidate_name,
				"mime_type": "image/png",
				"file_size": len(PNG_BYTES),
			}

			status, _, body = self._request(
				"/api/resume/import-confirm",
				method="POST",
				json_body={"draft": draft},
			)

			self.assertTrue(status.startswith("200"), body)
			payload = json.loads(body)
			self.assertTrue(payload["success"])
			self.assertEqual(payload["photo"]["mime_type"], "image/png")
			self.assertFalse((asset_dir / candidate_name).exists())

			status, _, body = self._request("/api/resume/photo")
			self.assertTrue(status.startswith("200"), body)
			photo = json.loads(body)
			self.assertEqual(photo["mime_type"], "image/png")
			self.assertTrue(Path(photo["path"]).is_file())

	def test_resume_center_api_customize_from_job_creates_version(self):
		with tempfile.TemporaryDirectory() as tmp:
			base_dir = Path(tmp)
			(base_dir / "config.yaml").write_text("{}\n", encoding="utf-8")
			server.set_base_dir(base_dir)
			db = get_db(base_dir / "data" / "bosshunter.db")
			resume_center.update_profile(db, {"basics": {"name": "李雷"}, "contacts": {}, "education": [], "skills": [], "preferences": {}})
			section = resume_center.create_section(db, {"section_type": "project", "title": "项目经历"})
			entry = resume_center.create_entry(db, {"section_id": section["id"], "title": "LeRobot 抓取"})
			material = resume_center.create_material(db, {"entry_id": entry["id"], "content": "使用 LeRobot 和 PyTorch 完成机械臂 VLA 抓取实验。"})
			insert_job(db, {
				"id": "job-vla-1",
				"title": "具身智能实习生",
				"company": "示例科技",
				"salary": "200-300元/天",
				"city": "北京",
				"experience": "不限",
				"education": "本科",
				"recruitment_type": "internship",
				"jd": "岗位需要 LeRobot、PyTorch、VLA 抓取项目经验。",
				"hr_name": "",
				"hr_title": "",
				"hr_active": "",
				"company_size": "",
				"company_industry": "",
				"url": "https://example.com/job",
			})
			db.close()

			status, _, body = self._request(
				"/api/resume/customize-from-job",
				method="POST",
				json_body={"job_id": "job-vla-1"},
			)

			self.assertTrue(status.startswith("201"), body)
			payload = json.loads(body)
			self.assertEqual(payload["version"]["target_job_id"], "job-vla-1")
			self.assertIn(material["id"], payload["version"]["selected_material_ids"])


if __name__ == "__main__":
	unittest.main()
