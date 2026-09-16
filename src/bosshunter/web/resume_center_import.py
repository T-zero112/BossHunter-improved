"""Import old resume content into structured resume-center drafts."""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from bosshunter.web import resume_center
from bosshunter.web.resume_description_format import format_entry_description_lines
from bosshunter.web.resume_import_ai import enhance_resume_import_with_ai
from bosshunter.web.resume_text import sanitize_resume_text


SECTION_LABELS: dict[str, tuple[str, str]] = {
	"education": ("教育背景", r"教育|学历|校园教育|教育背景"),
	"skill": ("技能证书", r"专业技能|职业技能|技能证书|技能|技术栈|专业能力|科研能力|计算机能力|语言能力|证书"),
	"project": ("项目经历", r"项目"),
	"work": ("实习 / 工作经历", r"工作|实习|任职|职业"),
	"academic": ("学术成果", r"论文|专利|学术|科研成果|发表|著作权"),
	"campus": ("校园与实践经历", r"校园|学生工作|社团|实践"),
	"award": ("荣誉奖项", r"荣誉|奖项|奖励证书|获奖"),
	"self_evaluation": ("综合评价", r"综合评价|自我评价|个人评价|个人简介|简介|优势|个人优势"),
}
IGNORED_SECTION_RE = re.compile(r"科研经历|研究经历|课题经历|课题项目")

HEADING_RE = re.compile(r"^(#{1,6})\s*(.+?)\s*$")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?86[-\s]?)?1[3-9]\d{9}(?!\d)")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
URL_RE = re.compile(r"https?://[^\s)）]+")
DATE_RANGE_RE = re.compile(r"((?:20\d{2}|19\d{2})[./年-]?\d{0,2})\s*(?:[-至到~—]+)\s*((?:20\d{2}|19\d{2}|至今|现在|今)[./年-]?\d{0,2})")


def build_resume_import_preview(filename: str, markdown: str, config: dict | None = None) -> dict[str, Any]:
	text = sanitize_resume_text(markdown)
	lines = _clean_lines(text)
	if not lines:
		raise ValueError("未解析到可导入的简历文字")
	blocks = _section_blocks(lines)
	profile = {
		"basics": _extract_basics(lines),
		"contacts": _extract_contacts(text),
		"education": [],
		"skills": [],
		"preferences": {},
	}
	sections: list[dict[str, Any]] = []
	warnings: list[str] = []
	for raw_title, raw_lines in blocks:
		raw_section_type = _classify_section(raw_title)
		for section_type, section_lines in _semantic_section_groups(raw_section_type, raw_lines):
			if section_type == "education":
				education_items = _parse_education(section_lines)
				if education_items:
					profile["education"].extend(education_items)
				else:
					supplement = _education_supplement(section_lines)
					if supplement:
						existing = _text(profile.get("preferences", {}).get("education_supplement"))
						profile["preferences"]["education_supplement"] = _join_detail(existing, supplement)
			elif section_type == "__ignore__":
				continue
			elif section_type == "skill":
				entries = _parse_skill_entries(section_lines)
				if entries:
					_append_import_section(sections, "skill", "技能证书", entries)
			elif section_type == "award":
				entries = _parse_award_entries(section_lines)
				if entries:
					_append_import_section(sections, "award", "荣誉奖项", entries)
			elif section_type == "self_evaluation":
				entries = _parse_evaluation_entries(section_lines)
				if entries:
					_append_import_section(sections, "self_evaluation", "综合评价", entries)
			elif section_type == "academic":
				entries = _parse_academic_entries(section_lines, section_title=raw_title)
				if entries:
					_append_import_section(sections, "academic", "学术成果", entries)
			elif section_type:
				title_hints = _extract_project_title_hints(lines) if section_type == "project" else []
				entries = _parse_entries(raw_title, section_lines, section_type, title_hints=title_hints)
				if entries:
					label = SECTION_LABELS.get(section_type, (raw_title or "导入模块", ""))[0]
					_append_import_section(sections, section_type, label, entries)
			else:
				warnings.append(f"未识别模块：{raw_title or '未命名内容'}")

	used_full_text_education_fallback = False
	if not profile["education"]:
		profile["education"].extend(_parse_education(lines))
		used_full_text_education_fallback = True
	if profile["education"] and profile["preferences"].get("education_supplement") and not used_full_text_education_fallback:
		supplement = _text(profile["preferences"].pop("education_supplement"))
		profile["education"][0]["detail"] = _join_detail(profile["education"][0].get("detail", ""), supplement)
	profile["skills"] = _unique_texts(profile["skills"])[:80]
	stats = {
		"education": len(profile["education"]),
		"skills": len(profile["skills"]),
		"sections": len(sections),
		"entries": sum(len(section["entries"]) for section in sections),
		"materials": sum(len(entry["materials"]) for section in sections for entry in section["entries"]),
	}
	if not any(stats.values()) and not any(profile["basics"].values()) and not any(profile["contacts"].values()):
		raise ValueError("未能从旧简历中识别出可导入内容")
	draft = {
		"source_filename": filename,
		"profile": profile,
		"sections": sections,
		"stats": stats,
		"warnings": warnings[:8],
		"preview_excerpt": "\n".join(lines[:18]),
	}
	return enhance_resume_import_with_ai(filename, markdown, draft, config)


def _append_import_section(sections: list[dict[str, Any]], section_type: str, title: str, entries: list[dict[str, Any]]) -> None:
	for section in sections:
		if section.get("section_type") == section_type:
			section_entries = section.get("entries")
			if isinstance(section_entries, list):
				section_entries.extend(entries)
			return
	sections.append({"section_type": section_type, "title": title, "summary": "", "entries": entries})


def apply_resume_import_draft(conn: sqlite3.Connection, draft: dict[str, Any]) -> dict[str, Any]:
	if not isinstance(draft, dict):
		raise ValueError("导入草稿必须是对象")
	profile_patch = draft.get("profile")
	sections = draft.get("sections")
	if not isinstance(profile_patch, dict) or not isinstance(sections, list):
		raise ValueError("导入草稿格式不正确")

	current = resume_center.get_profile(conn)
	merged_profile = _merge_profile(current, profile_patch)
	resume_center.update_profile(conn, merged_profile)
	existing_sections = resume_center.list_sections(conn)
	sections_by_type = {section["section_type"]: section for section in existing_sections}
	created_sections = 0
	created_entries = 0
	created_materials = 0
	for section_index, section in enumerate(sections):
		if not isinstance(section, dict):
			continue
		section_type = _safe_section_type(section.get("section_type"))
		title = _text(section.get("title")) or SECTION_LABELS.get(section_type, ("导入模块", ""))[0]
		target_section = sections_by_type.get(section_type)
		if target_section is None:
			target_section = resume_center.create_section(
				conn,
				{
					"section_type": section_type,
					"title": title,
					"summary": _text(section.get("summary"))[:2000],
					"sort_order": 80 + section_index * 10,
					"metadata": {"source": "resume_import"},
				},
			)
			sections_by_type[section_type] = target_section
			created_sections += 1
		entries = section.get("entries") if isinstance(section.get("entries"), list) else []
		existing_count = len(target_section.get("entries") or [])
		for entry_index, entry in enumerate(entries):
			if not isinstance(entry, dict):
				continue
			title_text = _text(entry.get("title"))[:160] or f"导入经历 {entry_index + 1}"
			entry_metadata = {"source": "resume_import"}
			if isinstance(entry.get("metadata"), dict):
				entry_metadata.update(entry["metadata"])
			created_entry = resume_center.create_entry(
				conn,
				{
					"section_id": target_section["id"],
					"entry_type": section_type,
					"title": title_text,
					"organization": _text(entry.get("organization"))[:160],
					"role": _text(entry.get("role"))[:160],
					"start_date": _text(entry.get("start_date"))[:40],
					"end_date": _text(entry.get("end_date"))[:40],
					"description": _text(entry.get("description"))[:4000],
					"sort_order": (existing_count + entry_index) * 10,
					"metadata": entry_metadata,
				},
			)
			created_entries += 1
			materials = entry.get("materials") if isinstance(entry.get("materials"), list) else []
			for material_index, material in enumerate(materials):
				content = _text(material.get("content") if isinstance(material, dict) else material)[:4000]
				if not content:
					continue
				resume_center.create_material(
					conn,
					{
						"entry_id": created_entry["id"],
						"material_type": "bullet",
						"content": content,
						"sort_order": material_index * 10,
						"metadata": {"source": "resume_import"},
					},
				)
				created_materials += 1
	return {
		"success": True,
		"imported": {
			"sections": created_sections,
			"entries": created_entries,
			"materials": created_materials,
			"education": len(merged_profile.get("education", [])) - len(current.get("education", [])),
			"skills": len(merged_profile.get("skills", [])) - len(current.get("skills", [])),
		},
		"profile": resume_center.get_profile(conn),
		"sections": resume_center.list_sections(conn),
	}


def _clean_lines(text: str) -> list[str]:
	result: list[str] = []
	for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
		line = re.sub(r"\s+", " ", raw).strip()
		if line:
			result.append(line)
	return result


def _section_blocks(lines: list[str]) -> list[tuple[str, list[str]]]:
	blocks: list[tuple[str, list[str]]] = []
	current_title = "基本信息"
	current_lines: list[str] = []
	for line in lines:
		heading = HEADING_RE.match(line)
		if heading:
			heading_title = heading.group(2).strip()
			if _classify_section(heading_title) is None and heading_title not in {"基本信息", "个人信息", "联系方式"}:
				current_lines.append(heading_title)
				continue
			if current_lines:
				blocks.append((current_title, current_lines))
			current_title = heading_title
			current_lines = []
			continue
		if _looks_like_section_title(line):
			if current_lines:
				blocks.append((current_title, current_lines))
			current_title = _strip_bullet(line)
			current_lines = []
			continue
		current_lines.append(line)
	if current_lines:
		blocks.append((current_title, current_lines))
	return blocks


def _looks_like_section_title(line: str) -> bool:
	text = _strip_bullet(line).strip("：:")
	compact = _compact_text(text)
	if len(compact) > 18:
		return False
	if re.search(r"[:：]", text) and compact not in _exact_section_titles():
		return False
	if re.search(r"[。；;，,]", text) and compact not in _exact_section_titles():
		return False
	return _classify_section(text) is not None


def _classify_section(title: str) -> str | None:
	text = _strip_bullet(title).strip("：: ")
	compact = _compact_text(text)
	if compact in {"基本信息", "个人信息", "联系方式"}:
		return None
	exact = _exact_section_titles()
	if compact in exact:
		return exact[compact]
	for section_type, (_, pattern) in SECTION_LABELS.items():
		if re.search(pattern, compact):
			return section_type
	if IGNORED_SECTION_RE.search(compact):
		return "__ignore__"
	return None


def _extract_basics(lines: list[str]) -> dict[str, str]:
	basics: dict[str, str] = {}
	key_map = {
		"姓名": "name",
		"性别": "gender",
		"出生日期": "birth_date",
		"出生年月": "birth_date",
		"生日": "birth_date",
		"籍贯": "native_place",
		"政治面貌": "political_status",
	}
	for line in lines[:40]:
		for label, key in key_map.items():
			match = re.search(rf"{_spaced_label_pattern(label)}\s*[:：]\s*([^\s|｜，,；;]+)", line)
			if match:
				basics.setdefault(key, match.group(1).strip())
	for line in lines[:10]:
		candidate = _strip_bullet(HEADING_RE.sub(r"\2", line))
		if not candidate or EMAIL_RE.search(candidate) or PHONE_RE.search(candidate) or URL_RE.search(candidate):
			continue
		if _classify_section(candidate) is not None:
			continue
		if len(candidate) <= 12 and not re.search(r"大学|学院|硕士|本科|博士|工程|机器人|专业|经历|项目", candidate):
			basics.setdefault("name", candidate)
			break
	return basics


def _extract_contacts(text: str) -> dict[str, str]:
	contacts: dict[str, str] = {}
	phone = PHONE_RE.search(text)
	email = EMAIL_RE.search(text)
	if phone:
		contacts["phone"] = phone.group(0)
	if email:
		contacts["email"] = email.group(0)
	for url in URL_RE.findall(text):
		lower = url.lower()
		if "github.com" in lower:
			contacts.setdefault("github", url)
		else:
			contacts.setdefault("website", url)
	return contacts


def _parse_education(lines: list[str]) -> list[dict[str, str]]:
	line_items: list[dict[str, str]] = []
	pending_degrees: list[str] = []
	current_index: int | None = None
	for line in lines:
		text = _strip_bullet(line)
		if not text:
			continue
		if _looks_like_section_title(text) and _classify_section(text) == "education":
			current_index = 0 if line_items else None
			continue
		degree_label = _degree_from_stage_label(text)
		if degree_label:
			pending_degrees.append(degree_label)
			continue
		item = _education_item_from_chunk(text)
		if item:
			if pending_degrees and not item.get("degree"):
				item["degree"] = pending_degrees.pop(0)
			line_items.append(item)
			current_index = len(line_items) - 1
			continue
		if current_index is not None and (_is_education_supplement(text) or _is_education_honor(text)):
			target_index = len(line_items) - 1 if _is_education_honor(text) and len(line_items) > 1 else current_index
			line_items[target_index]["detail"] = _join_detail(line_items[target_index].get("detail", ""), text)
	if line_items:
		return line_items[:10]
	text = " ".join(_strip_bullet(line) for line in lines)
	items: list[dict[str, str]] = []
	chunks = _split_long_section(lines)
	for chunk in chunks or [text]:
		chunk = " ".join(chunk) if isinstance(chunk, list) else str(chunk)
		item = _education_item_from_chunk(chunk)
		if item:
			items.append(item)
	if items:
		_apply_education_supplements(items, lines)
	return items[:10]


def _education_supplements(lines: list[str]) -> tuple[str, str]:
	current_values: list[str] = []
	honor_values: list[str] = []
	for line in lines:
		text = _strip_bullet(line)
		if not text:
			continue
		if _education_item_from_chunk(text):
			continue
		if _is_education_honor(text):
			honor_values.append(text)
		elif _is_education_supplement(text):
			current_values.append(text)
	return "；".join(_unique_texts(current_values))[:600], "；".join(_unique_texts(honor_values))[:600]


def _education_supplement(lines: list[str]) -> str:
	current, honors = _education_supplements(lines)
	return _join_detail(current, honors)


def _apply_education_supplements(items: list[dict[str, str]], lines: list[str]) -> None:
	current, honors = _education_supplements(lines)
	if current:
		items[0]["detail"] = _join_detail(items[0].get("detail", ""), current)
	if honors:
		target = items[-1] if len(items) > 1 else items[0]
		target["detail"] = _join_detail(target.get("detail", ""), honors)


def _join_detail(existing: str, supplement: str) -> str:
	parts = [part for part in [existing.strip(), supplement.strip()] if part]
	return "；".join(_unique_texts(parts))[:600]


def _education_item_from_chunk(chunk: str) -> dict[str, str]:
	if not ("大学" in chunk or "学院" in chunk):
		return {}
	if re.search(r"荣誉|竞赛|获奖|奖项|大学生|奖学金|励志|挑战杯|证书", chunk) and not re.search(r"(?:大学|学院)[（(]", chunk):
		return {}
	item: dict[str, str] = {}
	date = DATE_RANGE_RE.search(chunk)
	if date:
		item["start_date"] = _normalize_date(date.group(1))
		item["end_date"] = _normalize_date(date.group(2))
	parts = [part.strip() for part in re.split(r"\s[-–—]\s| - ", re.sub(DATE_RANGE_RE, "", chunk)) if part.strip()]
	if len(parts) >= 3 and ("大学" in parts[0] or "学院" in parts[0]):
		item["school"] = parts[0]
		item["major"] = parts[1]
		degree_part = parts[2]
		degree = re.search(r"(博士|硕士|本科|大专|研究生)", degree_part)
		if degree:
			item["degree"] = degree.group(1)
	school = re.search(r"([\u4e00-\u9fa5A-Za-z0-9·（）()]{2,40}(?:大学|学院)(?:（[^）]+）|\([^)]*\))?)", chunk)
	if school and not item.get("school"):
		item["school"] = _strip_degree_parenthetical(school.group(1))
	degree = re.search(r"(博士|硕士|本科|大专|研究生|学士)", chunk)
	if degree and not item.get("degree"):
		item["degree"] = "本科" if degree.group(1) == "学士" else degree.group(1)
	major = re.search(r"([\u4e00-\u9fa5A-Za-z0-9]+专业)", chunk)
	if major and not item.get("major"):
		item["major"] = major.group(1).replace("专业", "")
	if item.get("school") and not item.get("major"):
		remainder = re.sub(DATE_RANGE_RE, "", chunk)
		remainder = remainder.replace(item["school"], "")
		remainder = re.sub(r"[（(](?:博士|硕士研究生|硕士|本科|学士|大专|研究生)[）)]", " ", remainder)
		remainder = re.sub(r"(?:博士|硕士研究生|硕士|本科|学士|大专|研究生)", " ", remainder)
		candidates = [
			part.strip(" -，,；;|")
			for part in re.split(r"\s{2,}|\s[-–—]\s| - |\|", remainder)
			if part.strip(" -，,；;|")
		]
		for candidate in candidates:
			if len(candidate) <= 30 and not re.search(r"GPA|主修|研究方向|课程|荣誉|奖学金", candidate):
				item["major"] = candidate
				break
	detail = _education_detail_from_chunk(chunk, item)
	if detail:
		item["detail"] = detail[:600]
	return item if item.get("school") or item.get("major") or item.get("degree") else {}


def _education_detail_from_chunk(chunk: str, item: dict[str, str]) -> str:
	detail = re.sub(DATE_RANGE_RE, "", chunk)
	for key in ("school", "major", "degree"):
		value = _text(item.get(key))
		if value:
			detail = detail.replace(value, " ")
	if item.get("school"):
		detail = detail.replace(_strip_degree_parenthetical(_text(item.get("school"))), " ")
	detail = re.sub(r"[（(](?:博士|硕士研究生|硕士|本科|学士|大专|研究生)[）)]", " ", detail)
	detail = re.sub(r"(?:博士|硕士研究生|硕士|本科|学士|大专|研究生)", " ", detail)
	detail = re.sub(r"\s+", " ", detail).strip(" -，,；;|")
	return detail if _is_education_supplement(detail) or re.search(r"GPA|主修|研究方向|专业前|排名|课程", detail) else ""


def _parse_skill_entries(lines: list[str]) -> list[dict[str, Any]]:
	grouped = _group_skill_items(lines)
	entries: list[dict[str, Any]] = []
	for category, values in grouped:
		if not values:
			continue
		entries.append(
			{
				"title": _skill_category_label(category),
				"organization": "",
				"role": "",
				"start_date": "",
				"end_date": "",
				"description": "",
				"metadata": {"skill_category": category},
				"materials": [{"content": value} for value in values[:40]],
			}
		)
	return entries[:12]


SKILL_CATEGORY_ORDER = [
	"language",
	"programming_data",
	"mechanical_design",
	"simulation_analysis",
	"automation_control",
	"experiment_equipment",
	"office_tools",
	"professional_certificate",
	"professional_tools",
	"other",
]


SKILL_CATEGORY_LABELS = {
	"language": "语言能力",
	"programming_data": "编程与数据能力",
	"mechanical_design": "机械设计与建模",
	"simulation_analysis": "仿真与分析",
	"automation_control": "自动化与控制",
	"experiment_equipment": "实验与设备能力",
	"office_tools": "办公与通用工具",
	"professional_certificate": "职业证书",
	"professional_tools": "专业工具",
	"other": "其他技能",
}


def _skill_category_label(category: str) -> str:
	return SKILL_CATEGORY_LABELS.get(category, "其他技能")


def _group_skill_items(lines: list[str]) -> list[tuple[str, list[str]]]:
	grouped: dict[str, list[str]] = {category: [] for category in SKILL_CATEGORY_ORDER}
	for line in lines:
		text = _strip_bullet(line)
		if not text or _is_award_concept(text):
			continue
		for label_category, content in _skill_labeled_segments(text):
			for item in _skill_items_from_text(content):
				category = _classify_skill_item(item, label_category)
				cleaned = _clean_skill_item(item)
				if cleaned and cleaned not in grouped[category]:
					grouped[category].append(cleaned)
	return [(category, grouped[category]) for category in SKILL_CATEGORY_ORDER if grouped[category]]


SKILL_INLINE_LABEL_RE = re.compile(
	r"(语言能力|英语能力|普通话|计算机能力|专业工具|其他证书|编程能力|数据库|办公软件|"
	r"机械与建模|机械设计|自动化与控制|实践技能|实验技能|专业技能|职业技能|科研能力|其他技能)\s*[:：]",
	flags=re.IGNORECASE,
)


def _skill_labeled_segments(text: str) -> list[tuple[str, str]]:
	value = _strip_bullet(text)
	matches = list(SKILL_INLINE_LABEL_RE.finditer(value))
	if not matches:
		return [("", _strip_concept_label(value))]
	segments: list[tuple[str, str]] = []
	if matches[0].start() > 0:
		prefix = value[: matches[0].start()].strip(" ，,；;")
		if prefix:
			segments.append(("", prefix))
	for index, match in enumerate(matches):
		content_start = match.end()
		content_end = matches[index + 1].start() if index + 1 < len(matches) else len(value)
		content = value[content_start:content_end].strip(" ，,；;")
		if content:
			segments.append((_classify_skill_label(_compact_text(match.group(1))), content))
	return segments or [("", _strip_concept_label(value))]


def _classify_skill_label(label: str) -> str:
	if re.search(r"语言|英语|普通话", label):
		return "language"
	if re.search(r"编程|数据|数据库|开发", label):
		return "programming_data"
	if re.search(r"机械|建模|制图|设计", label):
		return "mechanical_design"
	if re.search(r"仿真|有限元|分析", label):
		return "simulation_analysis"
	if re.search(r"自动化|控制|电气|机器人|运动控制", label):
		return "automation_control"
	if re.search(r"实验|实践|设备|测试", label):
		return "experiment_equipment"
	if re.search(r"办公|Office|软件", label, flags=re.IGNORECASE):
		return "office_tools"
	if re.search(r"证书|资格", label):
		return "professional_certificate"
	if re.search(r"专业工具|工具|其他", label):
		return "professional_tools"
	return ""


def _skill_items_from_text(text: str) -> list[str]:
	value = _strip_concept_label(text)
	value = re.sub(r"\s+", " ", value).strip()
	if not value:
		return []
	parts = [
		part.strip()
		for part in re.split(r"[；;，,、|]+|\s{2,}", value)
		if part.strip()
	]
	if not parts:
		return []
	result: list[str] = []
	for part in parts:
		result.extend(_split_skill_compound(part))
	return [item for item in result if item]


def _split_skill_compound(text: str) -> list[str]:
	value = _clean_skill_item(text)
	if not value:
		return []
	certificates = re.findall(r"(?:CET[-\s]?[46]|普通话[一二三四]级[甲乙]?等?|计算机[一二三四]级|教师资格证|雅思\s*\d+(?:\.\d+)?)", value, flags=re.IGNORECASE)
	if len(certificates) >= 2:
		return [_normalize_skill_token(item) for item in certificates]
	tools = re.findall(
		r"\b(?:Python|Java|C\+\+|MATLAB|LaTeX|Pandas|NumPy|Matplotlib|SQL|MySQL|Git|PyCharm|"
		r"SolidWorks|Solidworks|AutoCAD|CAD|UG|Rhino|ANSYS|Ansys|Fluent|Abaqus|Workbench|"
		r"KUKA|KUKASimpro|WorkVisual|EPLAN|STM32|PLC|MTS|Office|Excel|Word|PowerPoint|PPT|ROS|PyTorch|OpenCV)\b",
		value,
		flags=re.IGNORECASE,
	)
	extras: list[str] = []
	for pattern in ("数据处理", "数据可视化", "工程制图", "三维建模", "装配图", "有限元", "气动设备", "试验机"):
		if pattern in value:
			extras.append(pattern)
	items = [_normalize_skill_token(item) for item in [*tools, *extras]]
	if items and (len(items) >= 2 or re.search(r"软件|工具|办公", value, flags=re.IGNORECASE)):
		return _unique_texts(items)
	return [value]


def _clean_skill_item(text: str) -> str:
	value = _strip_bullet(text)
	value = re.sub(r"^(?:熟悉|熟练使用|熟练|精通|掌握|具备|了解|通过|能够|有)\s*", "", value)
	value = re.sub(r"(?:等(?:办公|三维绘图|二维绘图|有限元仿真)?软件(?:基础使用)?|等工具|等实验设备|能力)$", "", value)
	value = re.sub(r"\s+", " ", value).strip(" ：:，,；;。.")
	return value


def _normalize_skill_token(text: str) -> str:
	value = re.sub(r"\s+", " ", str(text or "")).strip()
	upper_map = {
		"solidworks": "SolidWorks",
		"ansys": "ANSYS",
		"cet 4": "CET-4",
		"cet 6": "CET-6",
		"cet-4": "CET-4",
		"cet-6": "CET-6",
		"ppt": "PowerPoint",
	}
	return upper_map.get(value.lower(), value)


def _classify_skill_item(item: str, label_category: str = "") -> str:
	text = _compact_text(item)
	if re.search(r"CET[-\s]?[46]|英语|普通话|雅思|托福|TOEFL|IELTS", item, flags=re.IGNORECASE):
		return "language"
	if re.search(r"教师资格证|资格证|计算机[一二三四]级|证书", item):
		return "professional_certificate"
	if re.search(
		r"Python|Java|C\+\+|MATLAB|Pandas|NumPy|Matplotlib|SQL|MySQL|Git|PyCharm|"
		r"PyTorch|OpenCV|LeRobot|HuggingFace|Rerun|数据库|数据处理|可视化|编程|开发",
		item,
		flags=re.IGNORECASE,
	):
		return "programming_data"
	if re.search(r"SolidWorks|Solidworks|AutoCAD|CAD|UG|Rhino|制图|工程图|三维建模|二维|装配图|机械建模|机械设计", item, flags=re.IGNORECASE):
		return "mechanical_design"
	if re.search(r"ANSYS|Ansys|Fluent|Abaqus|Workbench|有限元|仿真|力学", item, flags=re.IGNORECASE):
		return "simulation_analysis"
	if re.search(r"KUKA|KUKASimpro|WorkVisual|EPLAN|STM32|PLC|ROS|伺服|传感器|气动|自动化|控制|电气", item, flags=re.IGNORECASE):
		return "automation_control"
	if re.search(r"MTS|试验机|实验|测试|设备|数据采集", item, flags=re.IGNORECASE):
		return "experiment_equipment"
	if re.search(r"Office|Excel|Word|PowerPoint|PPT|办公", item, flags=re.IGNORECASE):
		return "office_tools"
	return label_category or ("other" if text else "other")


def _parse_award_entries(lines: list[str]) -> list[dict[str, Any]]:
	entries: list[dict[str, Any]] = []
	for line in _award_lines(lines):
		text = _strip_bullet(line)
		if not text:
			continue
		for award in _split_award_items(text):
			start_date, title = _award_date_and_title(award)
			entries.append(
				{
					"title": title[:160],
					"organization": "",
					"role": "",
					"start_date": start_date,
					"end_date": "",
					"description": "",
					"materials": [],
				}
			)
	return entries[:40]


def _award_lines(lines: list[str]) -> list[str]:
	result: list[str] = []
	for line in lines:
		text = _strip_bullet(line)
		if not text:
			continue
		if result and re.fullmatch(r"(?:19|20)\d{2}\.", result[-1]) and re.match(r"\d{1,2}\b", text):
			result[-1] = f"{result[-1]}{text}"
			continue
		if result and ((result[-1].endswith("竞") and text.startswith("赛")) or (result[-1].endswith("比") and text.startswith("赛"))):
			result[-1] = f"{result[-1]}{text}"
			continue
		result.append(text)
	return result


def _split_award_items(text: str) -> list[str]:
	parts = [
		part.strip()
		for part in re.split(r"\s+(?=(?:19|20)\d{2}[./]\d{1,2}\s)", text)
		if part.strip()
	]
	items: list[str] = []
	for part in parts or [text]:
		items.extend(_split_award_stage_tail(part))
	return items


def _award_date_and_title(text: str) -> tuple[str, str]:
	match = re.match(r"^((?:19|20)\d{2}[./年]\d{1,2})\s+(.+)$", text)
	if match:
		return _normalize_date(match.group(1)), _clean_award_title(match.group(2))
	return "", _clean_award_title(text)


def _split_award_stage_tail(text: str) -> list[str]:
	match = re.search(
		r"\s+(?=(?:本科|研究生|硕士|博士|大学|高中|初中)阶段\s*[^，。；;]{2,40}(?:奖|优秀|称号|荣誉|先进|标兵|毕业生))",
		text,
	)
	if not match:
		return [text.strip()]
	return [part.strip() for part in (text[: match.start()], text[match.start() :]) if part.strip()]


def _clean_award_title(text: str) -> str:
	return re.sub(r"^(?:本科|研究生|硕士|博士|大学|高中|初中)阶段\s*", "", text.strip())


def _parse_evaluation_entries(lines: list[str]) -> list[dict[str, Any]]:
	values = [_strip_bullet(line) for line in lines if _strip_bullet(line)]
	if not values:
		return []
	return [
		{
			"title": "综合评价",
			"organization": "",
			"role": "",
			"start_date": "",
			"end_date": "",
			"description": _join_wrapped_lines(values)[:1800],
			"materials": [],
		}
	]


def _parse_academic_entries(lines: list[str], *, section_title: str = "") -> list[dict[str, Any]]:
	entries: list[dict[str, Any]] = []
	current_kind = ""
	pending_author = _author_hint(section_title)
	for chunk in _split_academic_chunks(lines):
		cleaned = [_strip_bullet(HEADING_RE.sub(r"\2", line)) for line in chunk if _strip_bullet(HEADING_RE.sub(r"\2", line))]
		if not cleaned:
			continue
		heading = cleaned[0].strip("：: ")
		if re.fullmatch(r"论文|论文成果|发表论文", heading):
			current_kind = "论文"
			cleaned = cleaned[1:]
			if not cleaned:
				continue
		if re.fullmatch(r"专利|授权专利|申请专利", heading):
			current_kind = "专利"
			cleaned = cleaned[1:]
			if not cleaned:
				continue
		author_hint = _author_hint(" ".join(cleaned))
		if author_hint:
			pending_author = author_hint
			if _is_author_hint_only(" ".join(cleaned)):
				continue
		joined = " ".join(cleaned)
		kind = "专利" if ("专利" in joined and "论文" not in joined) else current_kind or "论文"
		entry = _academic_entry_from_lines(cleaned, kind, pending_author=pending_author)
		if entry:
			entries.append(entry)
			pending_author = ""
	return entries[:20]


def _split_academic_chunks(lines: list[str]) -> list[list[str]]:
	chunks: list[list[str]] = []
	current: list[str] = []
	for line in lines:
		raw_text = _strip_bullet(HEADING_RE.sub(r"\2", line))
		for text in _split_academic_numbered_items(raw_text):
			if not text:
				continue
			if re.match(r"^能力沉淀\s*", text):
				if current:
					chunks.append(current)
					current = []
				continue
			if current and current[-1].rstrip().endswith("-") and re.match(r"^[A-Za-z]", text):
				joiner = " " if re.match(r"^(?:and|or)\b", text, flags=re.IGNORECASE) else ""
				current[-1] = f"{current[-1].rstrip()}{joiner}{text}"
				continue
			is_new_result = bool(
				re.match(r"^(?:已发表|已录用|在投|投稿中|录用|发表|论文名称|文章名称|论文题目|专利名称)\b", text)
				or _has_academic_number_prefix(text)
				or _looks_like_academic_result_start(text)
			)
			if is_new_result and current:
				chunks.append(current)
				current = []
			current.append(text)
	if current:
		chunks.append(current)
	return chunks


def _split_academic_numbered_items(text: str) -> list[str]:
	cleaned = _strip_bullet(text)
	if not cleaned:
		return []
	return [
		part.strip()
		for part in re.split(r"\s+(?=[（(]\d{1,2}[）)])", cleaned)
		if part.strip()
	]


def _has_academic_number_prefix(text: str) -> bool:
	return bool(re.match(r"^[（(]\d{1,2}[）)]\s*", _strip_bullet(text)))


def _looks_like_academic_result_start(text: str) -> bool:
	value = _strip_bullet(text)
	if not value:
		return False
	if re.match(r"^[\"“]", value):
		return True
	if re.match(r"^(?:[A-Z][A-Za-z'\-]+,\s*[A-Z]\.;\s*)+[A-Z][A-Za-z'\-]+,\s*[A-Z]\.\s+", value):
		return True
	if re.search(r"\[(?:J|C|D|P|M)\]", value, flags=re.IGNORECASE):
		return True
	return bool(re.search(r"[（(][^）)]*(?:SCI|EI|JCR|已发表|已录用|在投|投稿中|一作|二作)[^）)]*[）)]\s*$", value, flags=re.IGNORECASE))


def _author_hint(text: str) -> str:
	match = re.search(r"以(.{1,12}?作者)身份", text)
	if match:
		return match.group(1)
	if "第一作者" in text:
		return "第一作者"
	if "第二作者" in text:
		return "第二作者"
	if re.search(r"(?<!共同)一作", text):
		return "第一作者"
	if re.search(r"(?<!共同)二作", text):
		return "第二作者"
	if re.search(r"共同(?:一作|第一作者)", text):
		return "共同第一作者"
	return ""


def _is_author_hint_only(text: str) -> bool:
	value = _strip_bullet(text)
	if not value:
		return False
	if len(value) > 40:
		return False
	if re.search(r"\[(?:J|C|D|P|M)\]|Journal|Conference|Proceedings|Environment|System|Control", value, flags=re.IGNORECASE):
		return False
	return bool(re.search(r"作者|一作|二作|发明人", value))


def _academic_entry_from_lines(lines: list[str], kind: str, *, pending_author: str = "") -> dict[str, Any] | None:
	text = " ".join(lines)
	fields: dict[str, str] = {}
	_status, status_title = _academic_status_and_title(text)
	if _status:
		fields["status"] = _status
		text = status_title
	field_patterns = {
		"title": r"(?:论文名称|文章名称|论文题目|专利名称|名称)\s*[:：]\s*([^；;，,\n]+)",
		"status": r"(?:状态|发表状态|专利状态)\s*[:：]\s*([^；;，,\n]+)",
		"journal": r"(?:期刊名称|期刊|会议|发表期刊)\s*[:：]\s*([^；;，,\n]+)",
		"patent_type": r"(?:专利类型|类型)\s*[:：]\s*([^；;，,\n]+)",
		"authors": r"(?:作者情况|作者|发明人)\s*[:：]\s*([^；;\n]+)",
	}
	for key, pattern in field_patterns.items():
		match = re.search(pattern, text)
		if match:
			fields[key] = match.group(1).strip()
	quoted = re.search(r"[\"“]\s*(.+?)\s*[\"”]\s*[,，.。]?\s*(.*)", text)
	if quoted:
		fields.setdefault("title", re.sub(r"\s+", " ", quoted.group(1)).strip())
		remainder = quoted.group(2).strip(" ，,。. ")
		if kind != "专利" and remainder:
			year_match = re.search(r"(?:19|20)\d{2}", remainder)
			if year_match:
				fields.setdefault("time", year_match.group(0))
			status_match = re.search(r"[（(]([^）)]+)[）)]", remainder)
			if status_match:
				fields.setdefault("status", status_match.group(1).strip())
			journal = re.sub(r"[（(][^）)]+[）)]", "", remainder)
			journal = re.sub(r",?\s*(?:19|20)\d{2}\.?\s*$", "", journal).strip(" ，,。. ")
			if journal:
				fields.setdefault("journal", journal)
	plain_fields = _plain_academic_fields(text)
	for key, value in plain_fields.items():
		fields.setdefault(key, value)
	if pending_author:
		fields.setdefault("authors", pending_author)
	if "第一作者" in text:
		fields.setdefault("authors", "第一作者")
	elif "第二作者" in text:
		fields.setdefault("authors", "第二作者")

	title = fields.get("title") or _strip_academic_prefix(text or lines[0])
	if not title or re.fullmatch(r"论文|专利|学术成果", title):
		return None
	fields = _normalize_academic_result_fields(fields)
	status = fields.get("status", "")
	if kind == "专利":
		organization = fields.get("patent_type", "")
		role = fields.get("authors", "")
	else:
		organization = fields.get("journal", "")
		role = fields.get("authors", "")
	metadata = {"result_type": kind}
	if fields.get("indexing"):
		metadata["indexing"] = fields["indexing"]
	return {
		"title": title[:160],
		"organization": organization[:160],
		"role": role[:160],
		"start_date": fields.get("time", "")[:40],
		"end_date": status[:40],
		"description": "",
		"metadata": metadata,
		"materials": [] if quoted else [{"content": line} for line in lines[1:8] if line],
	}


def _strip_academic_prefix(value: str) -> str:
	text = re.sub(r"^(?:科研成果|论文名称|文章名称|论文题目|专利名称|名称)\s*[:：]\s*", "", value).strip()
	return re.sub(r"^[（(]\d{1,2}[）)]\s*", "", text).strip()


def _plain_academic_fields(text: str) -> dict[str, str]:
	value = _strip_academic_prefix(text)
	if not value:
		return {}
	value, status, authors, indexing = _split_academic_tail_metadata(value)
	fields: dict[str, str] = {}
	if status:
		fields["status"] = status
	if authors:
		fields["authors"] = authors
	if indexing:
		fields["indexing"] = indexing
	fields.update(_author_prefixed_academic_fields(value))
	marker = re.search(r"\[(?:J|C|D|P|M)\]\.?\s*", value, flags=re.IGNORECASE)
	if marker:
		title = value[: marker.start()].strip(" ，,。. ")
		journal = value[marker.end() :].strip(" ，,。. ")
		year_match = re.search(r"(?:19|20)\d{2}", journal)
		if year_match:
			fields.setdefault("time", year_match.group(0))
		journal = re.sub(r"\.?\s*(?:19|20)\d{2}\.?\s*$", "", journal).strip(" ，,。. ")
		if title:
			fields["title"] = re.sub(r"\s+", " ", title)
		if journal:
			fields["journal"] = re.sub(r"\s+", " ", journal)
	elif not fields.get("title") and _has_academic_number_prefix(text):
		fields["title"] = re.sub(r"\s+", " ", value).strip(" ，,。. ")
	return fields


def _split_academic_tail_metadata(text: str) -> tuple[str, str, str, str]:
	match = re.match(r"^(.+?)[（(]([^）)]+)[）)]\s*$", text)
	if not match:
		return text, "", "", ""
	body = match.group(1).strip()
	meta = _normalize_academic_status_text(match.group(2))
	authors = _author_hint(meta)
	status = re.sub(r"共同(?:一作|第一作者)|第一作者|第二作者|一作|二作|通讯作者", "", meta, flags=re.IGNORECASE)
	status = re.sub(r"\s+", " ", status).strip(" ，,；;")
	status, indexing, time = _split_academic_status_indexing(status)
	return body, status or time, authors, indexing


def _author_prefixed_academic_fields(text: str) -> dict[str, str]:
	match = re.match(
		r"^((?:[A-Z][A-Za-z'\-]+,\s*[A-Z]\.;\s*)+[A-Z][A-Za-z'\-]+,\s*[A-Z]\.)\s+(.+)$",
		text,
	)
	if not match:
		return {}
	fields: dict[str, str] = {"authors": re.sub(r"\s+", " ", match.group(1)).strip()}
	body = match.group(2).strip()
	year_match = re.search(r",\s*((?:19|20)\d{2})\.?\s*$", body)
	if year_match:
		fields["time"] = year_match.group(1)
		body = body[: year_match.start()].strip(" ，,。. ")
	venue_match = re.search(r"\s((?:19|20)\d{2}\s+\d+(?:st|nd|rd|th)?\s+.+)$", body, flags=re.IGNORECASE)
	if venue_match:
		fields["title"] = re.sub(r"\s+", " ", body[: venue_match.start()].strip(" ，,。. "))
		fields["journal"] = re.sub(r"\s+", " ", venue_match.group(1).strip(" ，,。. "))
	return {key: value for key, value in fields.items() if value}


def _normalize_academic_result_fields(fields: dict[str, str]) -> dict[str, str]:
	result = dict(fields)
	status, indexing, time = _split_academic_status_indexing(result.get("status", ""))
	if status:
		result["status"] = status
	else:
		result.pop("status", None)
	if indexing:
		result["indexing"] = _join_academic_indexing(result.get("indexing", ""), indexing)
	if time and not result.get("time"):
		result["time"] = time
	return result


def _split_academic_status_indexing(text: str) -> tuple[str, str, str]:
	value = _normalize_academic_status_text(text)
	if not value:
		return "", "", ""
	year_match = re.fullmatch(r"(?:19|20)\d{2}", value)
	if year_match:
		return "", "", value
	state = ""
	for candidate in ("已发表", "已录用", "在投", "投稿中", "录用", "发表", "申请中", "已授权", "已公开"):
		if candidate in value:
			state = candidate
			break
	indexing_matches: list[str] = []
	for pattern in (
		r"JCR\s*[一二三四1234]\s*区",
		r"SCI\s*[一二三四1234]\s*区?",
		r"SSCI",
		r"CSSCI",
		r"SCI",
		r"EI",
		r"IEEE",
	):
		for match in re.findall(pattern, value, flags=re.IGNORECASE):
			normalized = _normalize_academic_status_text(match)
			normalized = re.sub(r"\s+", " ", normalized).strip()
			if normalized and normalized not in indexing_matches:
				indexing_matches.append(normalized)
	if state:
		return state, "；".join(indexing_matches), ""
	if indexing_matches:
		return "", "；".join(indexing_matches), ""
	return value, "", ""


def _join_academic_indexing(existing: str, extra: str) -> str:
	values = []
	for value in re.split(r"[；;、,，]+", f"{existing}；{extra}"):
		item = value.strip()
		if item and item not in values:
			values.append(item)
	return "；".join(values)


def _normalize_academic_status_text(text: str) -> str:
	value = _text(text)
	value = re.sub(r"\bsci\b", "SCI", value, flags=re.IGNORECASE)
	value = re.sub(r"\bei\b", "EI", value, flags=re.IGNORECASE)
	return value


def _academic_status_and_title(text: str) -> tuple[str, str]:
	value = _text(text)
	match = re.match(r"^(已发表|已录用|在投|投稿中|录用|发表)(?:[（(]([^）)]+)[）)])?\s*(.+)$", value)
	if not match:
		return "", value
	status = match.group(1)
	if match.group(2):
		status = f"{status}（{match.group(2)}）"
	return status, match.group(3).strip()


def _join_wrapped_lines(lines: list[str]) -> str:
	result = ""
	for raw in lines:
		line = _strip_bullet(raw)
		if not line:
			continue
		if not result:
			result = line
			continue
		if result.endswith(("\n", "。", "；", ";", "：", ":")) or _is_bullet(raw):
			result = f"{result}\n{line}"
		else:
			result = f"{result}{line}"
	return result


def _parse_entries(section_title: str, lines: list[str], section_type: str, title_hints: list[str] | None = None) -> list[dict[str, Any]]:
	chunks = _split_entry_chunks(lines)
	if not chunks:
		return []
	entries: list[dict[str, Any]] = []
	for index, chunk_lines in enumerate(chunks):
		title = _entry_title(chunk_lines, section_title, index, title_hints=title_hints, section_type=section_type)
		date = DATE_RANGE_RE.search(" ".join(chunk_lines))
		bullets = [_strip_bullet(line) for line in chunk_lines if _is_bullet(line)]
		if section_type == "project":
			description_lines = _project_raw_description_lines(chunk_lines, title)
			materials: list[dict[str, str]] = []
		else:
			description_lines = [_strip_bullet(line) for line in chunk_lines if not _is_bullet(line)]
			if len(description_lines) > 1 and description_lines[0] == title:
				description_lines = description_lines[1:]
			elif description_lines:
				description_lines[0] = _entry_line_without_title(description_lines[0], title)
				description_lines = [line for line in description_lines if line]
			materials = [{"content": item} for item in _unique_texts(bullets)[:12]]
		description = format_entry_description_lines(description_lines, section_type).strip()[:1800]
		if not description and not materials:
			continue
		entry: dict[str, Any] = {
			"title": title[:160],
			"organization": "",
			"role": "",
			"start_date": _normalize_date(date.group(1)) if date else "",
			"end_date": _normalize_date(date.group(2)) if date else "",
			"description": description,
			"materials": materials,
		}
		entries.append(entry)
	return entries[:20]


def _project_raw_description_lines(lines: list[str], title: str) -> list[str]:
	result: list[str] = []
	for index, raw in enumerate(lines):
		text = _strip_bullet(HEADING_RE.sub(r"\2", raw))
		if not text:
			continue
		if index == 0:
			if text == title:
				continue
			if title and text.startswith(title):
				text = text[len(title):].strip(" -，,；;•")
				if not text:
					continue
		result.append(text)
	return result


def _split_entry_chunks(lines: list[str]) -> list[list[str]]:
	chunks: list[list[str]] = []
	current: list[str] = []
	for line in lines:
		is_stack_boundary = bool(
			re.match(r"^\s*技术栈\s*[:：]", _strip_bullet(line))
			and len(current) != 1
		)
		is_bullet_date_boundary = bool(current and _is_bullet(line) and DATE_RANGE_RE.search(line))
		is_date_boundary = bool(
			current
			and _line_starts_date_range(line)
			and not (len(current) == 1 and _looks_like_entry_heading(current[0]) and not _line_starts_date_range(current[0]))
		)
		is_heading = (
			bool(HEADING_RE.match(line))
			or (len(current) >= 2 and _looks_like_entry_heading(line))
			or (is_stack_boundary and current)
			or is_bullet_date_boundary
			or is_date_boundary
		)
		if is_heading and current:
			chunks.append(current)
			current = []
		current.append(HEADING_RE.sub(r"\2", line))
	if current:
		chunks.append(current)
	if len(chunks) == 1 and len(chunks[0]) > 12:
		return _split_long_section(chunks[0])
	return chunks


def _split_long_section(lines: list[str]) -> list[list[str]]:
	chunks: list[list[str]] = []
	current: list[str] = []
	for line in lines:
		if _line_starts_date_range(line) and current:
			chunks.append(current)
			current = []
		current.append(line)
	if current:
		chunks.append(current)
	return chunks


def _entry_title(lines: list[str], section_title: str, index: int, title_hints: list[str] | None = None, section_type: str = "") -> str:
	if title_hints and index < len(title_hints):
		return title_hints[index]
	if section_type == "project" and index == 0 and _section_title_is_project_entry_title(section_title):
		return _strip_bullet(section_title).strip("：: ")
	for line in lines[:3]:
		text = _strip_bullet(HEADING_RE.sub(r"\2", line))
		can_use_bullet_title = bool(_is_bullet(line) and DATE_RANGE_RE.search(text))
		if text and (can_use_bullet_title or not _is_bullet(line)) and not DATE_RANGE_RE.fullmatch(text) and not re.match(r"^技术栈\s*[:：]", text):
			return _clean_entry_title(text) or f"{section_title} {index + 1}"
	return f"{section_title} {index + 1}"


def _section_title_is_project_entry_title(section_title: str) -> bool:
	text = _strip_bullet(section_title).strip("：: ")
	if not text or text in {"项目", "项目经历", "项目经验", "重点项目", "项目实践"}:
		return False
	return _classify_section(text) == "project"


def _clean_entry_title(text: str) -> str:
	title = re.sub(DATE_RANGE_RE, "", text).strip(" -，,；;")
	if "•" in title:
		title = title.split("•", 1)[0]
	title = re.split(
		r"\s+(?=(?:参与|协助|根据|对接|前往|参加|开展|负责|寒暑假|批改|组织|独立|完成|进行))",
		title,
		maxsplit=1,
	)[0]
	return title.strip(" -，,；;•")


def _entry_line_without_title(line: str, title: str) -> str:
	text = re.sub(DATE_RANGE_RE, "", line).strip(" -，,；;")
	if title and text.startswith(title):
		text = text[len(title):].strip(" -，,；;•")
	return text


def _line_starts_date_range(line: str) -> bool:
	return bool(DATE_RANGE_RE.match(_strip_bullet(line)))


def _extract_project_title_hints(lines: list[str]) -> list[str]:
	project_index = next((index for index, line in enumerate(lines) if _classify_section(line) == "project"), -1)
	if project_index <= 0:
		return []
	start = 0
	for index in range(project_index - 1, -1, -1):
		if _looks_like_section_title(lines[index]):
			start = index + 1
			break
	candidates: list[str] = []
	for line in lines[start:project_index]:
		text = _strip_bullet(HEADING_RE.sub(r"\2", line)).strip("：: ")
		if not text or len(text) > 80:
			continue
		if DATE_RANGE_RE.search(text) or PHONE_RE.search(text) or EMAIL_RE.search(text):
			continue
		if re.match(r"^(研究方向|主修课程|在校荣誉|求职意向|技术栈)\s*[:：]", text):
			continue
		if "大学" in text or "学院" in text:
			continue
		if re.search(r"。|；|;|，", text):
			continue
		if re.search(r"系统|平台|分析|生成|采集|抓取|控制|识别|Agent|LeRobot|PPT", text, flags=re.IGNORECASE):
			candidates.append(text)
	return _unique_texts(candidates)[:20]


def _looks_like_entry_heading(line: str) -> bool:
	text = _strip_bullet(HEADING_RE.sub(r"\2", str(line)))
	if not text or _is_bullet(line) or len(text) > 36:
		return False
	if DATE_RANGE_RE.search(text):
		return True
	if re.search(r"[。；;，,：:]", text):
		return False
	if re.search(r"完成|负责|参与|实现|搭建|优化|分析|记录|使用|基于", text):
		return False
	return True


def _semantic_section_groups(section_type: str | None, lines: list[str]) -> list[tuple[str | None, list[str]]]:
	if not lines:
		return [(section_type, [])]
	if section_type == "education":
		return _partition_semantic_lines(lines, default_type="education", split_items=False)
	if section_type in {"skill", "award"}:
		return _partition_semantic_lines(lines, default_type=section_type, split_items=True)
	return [(section_type, lines)]


def _partition_semantic_lines(lines: list[str], *, default_type: str, split_items: bool) -> list[tuple[str, list[str]]]:
	grouped: dict[str, list[str]] = {}
	order: list[str] = []
	for line in lines:
		items = _semantic_items(line) if split_items else [_strip_bullet(line)]
		for item in items:
			text = _strip_bullet(item)
			if not text:
				continue
			concept = _classify_resume_concept(text, default_type=default_type)
			if concept not in order:
				order.append(concept)
			grouped.setdefault(concept, []).append(text if concept == "skill" else _strip_concept_label(text))
	return [(concept, grouped[concept]) for concept in order]


def _semantic_items(line: str) -> list[str]:
	text = _strip_bullet(line)
	if not text:
		return []
	return [
		part.strip()
		for part in re.split(r"[；;]+", text)
		if part.strip()
	]


def _classify_resume_concept(text: str, *, default_type: str) -> str:
	compact = _compact_text(text)
	if _is_academic_concept(text):
		return "academic"
	if _is_award_concept(text):
		return "award"
	if _is_skill_concept(text):
		return "skill"
	if default_type == "education" and (_is_education_supplement(text) or _education_item_from_chunk(text) or _degree_from_stage_label(text)):
		return "education"
	return default_type


def _is_academic_concept(text: str) -> bool:
	compact = _compact_text(text)
	if re.search(r"论文|专利|著作权|发表|在投|录用|见刊|SCI|EI|IEEE|Journal|Conference|CCDC|期刊|会议", text, flags=re.IGNORECASE):
		return True
	return bool(re.search(r"科研成果[:：]", compact))


def _is_award_concept(text: str) -> bool:
	if _is_skill_concept(text) and not re.search(r"奖学金|一等奖|二等奖|三等奖|优秀|获奖|竞赛|挑战杯|荣誉|表彰", text):
		return False
	return bool(re.search(r"奖学金|一等奖|二等奖|三等奖|优秀|获奖|竞赛|挑战杯|省级优秀毕业生|荣誉|表彰|奖项", text))


def _is_skill_concept(text: str) -> bool:
	return bool(
		re.search(
			r"CET[-\s]?[46]|英语|普通话|计算机[一二三四]级|教师资格证|资格证|证书|熟悉|熟练|"
			r"Python|Java|C\+\+|MATLAB|LaTeX|Office|Excel|Word|PPT|PowerPoint|"
			r"Solidworks|SolidWorks|AutoCAD|CAD|UG|Rhino|Abaqus|Ansys|ANSYS|Workbench|Fluent|"
			r"KUKA|EPLAN|STM32|PLC|MTS|ROS|PyTorch|OpenCV",
			text,
			flags=re.IGNORECASE,
		)
	)


def _strip_concept_label(text: str) -> str:
	return re.sub(
		r"^(?:科研成果|奖励证书|荣誉奖项|技能证书|职业技能|专业技能|科研能力|"
		r"语言能力|计算机能力|专业工具|其他证书|编程能力|数据库|办公软件|机械与建模|"
		r"自动化与控制|实践技能|其他技能)\s*[:：]\s*",
		"",
		text,
	).strip()


def _merge_profile(current: dict[str, Any], imported: dict[str, Any]) -> dict[str, Any]:
	basics = _merge_missing_dict(current.get("basics"), imported.get("basics"))
	contacts = _merge_missing_dict(current.get("contacts"), imported.get("contacts"))
	preferences = _merge_missing_dict(current.get("preferences"), imported.get("preferences"))
	education = list(current.get("education") if isinstance(current.get("education"), list) else [])
	for item in imported.get("education") if isinstance(imported.get("education"), list) else []:
		if isinstance(item, dict) and not _education_exists(education, item):
			education.append(item)
	skills = _unique_texts([
		*(current.get("skills") if isinstance(current.get("skills"), list) else []),
		*(imported.get("skills") if isinstance(imported.get("skills"), list) else []),
	])
	return {
		"basics": basics,
		"contacts": contacts,
		"education": education,
		"skills": skills,
		"preferences": preferences,
	}


def _merge_missing_dict(current: Any, imported: Any) -> dict[str, Any]:
	result = dict(current) if isinstance(current, dict) else {}
	if isinstance(imported, dict):
		for key, value in imported.items():
			if value and not result.get(key):
				result[key] = value
	return result


def _education_exists(existing: list[Any], item: dict[str, Any]) -> bool:
	school = _text(item.get("school"))
	major = _text(item.get("major"))
	return any(isinstance(old, dict) and _text(old.get("school")) == school and _text(old.get("major")) == major for old in existing)


def _safe_section_type(value: Any) -> str:
	text = _text(value) or "custom"
	return text if text in resume_center.SECTION_TYPES else "custom"


def _compact_text(value: str) -> str:
	return re.sub(r"\s+", "", str(value or ""))


def _spaced_label_pattern(label: str) -> str:
	return r"\s*".join(re.escape(char) for char in label)


def _exact_section_titles() -> dict[str, str]:
	return {
		"教育背景": "education",
		"教育经历": "education",
		"学历背景": "education",
		"项目经历": "project",
		"重点实践经历": "campus",
		"校园与社会实践": "campus",
		"校园与实践经历": "campus",
		"科研成果": "academic",
		"学术成果": "academic",
		"论文成果": "academic",
		"奖励证书": "award",
		"荣誉奖项": "award",
		"获奖情况": "award",
		"职业技能": "skill",
		"专业技能": "skill",
		"技能证书": "skill",
		"科研能力": "skill",
		"个人技能": "skill",
		"专业能力": "skill",
		"个人优势": "self_evaluation",
		"自我评价": "self_evaluation",
		"综合评价": "self_evaluation",
	}


def _degree_from_stage_label(value: str) -> str:
	text = _compact_text(value).strip("：:")
	if text in {"博士", "博士研究生"}:
		return "博士"
	if text in {"硕士", "硕士研究生", "研究生"}:
		return "硕士"
	if text in {"本科", "学士"}:
		return "本科"
	if text in {"大专", "专科"}:
		return "大专"
	return ""


def _is_education_honor(value: str) -> bool:
	return bool(re.match(r"^(在校荣誉|奖学金|获奖|荣誉奖项)\s*[:：]", _compact_text(value)))


def _is_education_supplement(value: str) -> bool:
	text = _compact_text(value)
	return bool(re.match(r"^(研究方向|主修课程|GPA|成绩排名|专业前|核心课程|相关课程|科研成果)\s*[:：]?", text))


def _strip_degree_parenthetical(value: str) -> str:
	return re.sub(r"[（(](?:博士|硕士研究生|硕士|本科|学士|大专|研究生)[）)]", "", value).strip()


def _text(value: Any) -> str:
	return str(value or "").strip()


def _strip_bullet(line: str) -> str:
	return re.sub(r"^\s*(?:[-*+•·●\uf06c]\s*|[0-9]{1,2}[.、]\s+)", "", str(line)).strip()


def _is_bullet(line: str) -> bool:
	return bool(re.match(r"^\s*(?:[-*+•·●\uf06c]\s*|[0-9]{1,2}[.、]\s+)", str(line)))


def _normalize_date(value: str) -> str:
	return str(value or "").strip().replace("年", ".").replace("月", "").replace("/", ".").strip(".- ")


def _unique_texts(values: list[Any]) -> list[str]:
	seen: set[str] = set()
	result: list[str] = []
	for value in values:
		text = _text(value)
		if not text:
			continue
		key = re.sub(r"\s+", "", text).lower()
		if key in seen:
			continue
		seen.add(key)
		result.append(text)
	return result
