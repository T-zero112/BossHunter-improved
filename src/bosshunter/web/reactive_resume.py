"""Reactive Resume renderer bridge for resume-center versions."""

from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4


REACTIVE_TEMPLATE_IDS = {
	"azurill",
	"bronzor",
	"chikorita",
	"ditgar",
	"ditto",
	"gengar",
	"glalie",
	"kakuna",
	"lapras",
	"leafish",
	"meowth",
	"onyx",
	"pikachu",
	"rhyhorn",
	"scizor",
}

SECTION_TITLES = {
	"summary": "综合评价",
	"education": "教育背景",
	"experience": "实习 / 工作经历",
	"projects": "项目经历",
	"skills": "技能证书",
	"awards": "荣誉奖项",
	"certifications": "技能证书",
	"publications": "学术成果",
	"volunteer": "校园与实践经历",
}


class ReactiveResumeRenderError(RuntimeError):
	"""Raised when the optional Reactive Resume renderer cannot produce a PDF."""


def reactive_template_name(template_id: str | None) -> str | None:
	text = _text(template_id)
	if text.startswith("reactive-"):
		text = text.removeprefix("reactive-")
	return text if text in REACTIVE_TEMPLATE_IDS else None


def is_reactive_template(template_id: str | None) -> bool:
	return reactive_template_name(template_id) is not None


def build_reactive_resume_data(
	version: dict[str, Any],
	*,
	template_id: str | None = None,
	show_photo: bool = True,
) -> dict[str, Any]:
	template = reactive_template_name(template_id or version.get("template_id")) or "azurill"
	snapshot = version.get("profile_snapshot") if isinstance(version.get("profile_snapshot"), dict) else {}
	profile = snapshot.get("profile") if isinstance(snapshot.get("profile"), dict) else {}
	basics = profile.get("basics") if isinstance(profile.get("basics"), dict) else {}
	contacts = profile.get("contacts") if isinstance(profile.get("contacts"), dict) else {}
	education = profile.get("education") if isinstance(profile.get("education"), list) else []
	profile_skills = profile.get("skills") if isinstance(profile.get("skills"), list) else []
	sections = _selected_sections(version)

	summary_content = _section_text(sections, "self_evaluation")
	reactive_sections = {
		"profiles": _empty_section(""),
		"experience": _entry_section("experience", _experience_items(sections)),
		"education": _entry_section("education", _education_items(education)),
		"projects": _entry_section("projects", _project_items(sections)),
		"skills": _skills_section(profile_skills, sections),
		"languages": _empty_section(""),
		"interests": _empty_section(""),
		"awards": _entry_section("awards", _award_items(sections)),
		"certifications": _entry_section("certifications", _certification_items(sections)),
		"publications": _entry_section("publications", _publication_items(sections)),
		"volunteer": _entry_section("volunteer", _volunteer_items(sections)),
		"references": _empty_section(""),
	}

	return {
		"picture": _picture(snapshot, show_photo),
		"basics": {
			"name": _text(basics.get("name")) or _text(version.get("name")) or "未命名",
			"headline": _headline(basics, profile),
			"email": _text(contacts.get("email")) or _text(basics.get("email")),
			"phone": _text(contacts.get("phone")) or _text(basics.get("phone")),
			"location": _text(basics.get("native_place")) or _text(basics.get("location")),
			"website": _website(_text(contacts.get("website")) or _text(basics.get("website"))),
			"customFields": _custom_fields(basics, contacts),
		},
		"summary": {
			"title": SECTION_TITLES["summary"],
			"icon": "article",
			"columns": 1,
			"hidden": not bool(summary_content),
			"showHeading": True,
			"keepTogether": False,
			"startOnNewPage": False,
			"content": _rich_html(summary_content),
		},
		"sections": reactive_sections,
		"customSections": [],
		"metadata": {
			"template": template,
			"layout": {
				"sidebarWidth": 30,
				"pages": [
					{
						"fullWidth": False,
						"main": ["summary", "education", "experience", "projects", "publications", "volunteer", "awards"],
						"sidebar": ["profiles", "skills", "certifications"],
					}
				],
			},
			"page": {
				"gapX": 12,
				"gapY": 8,
				"marginX": 16,
				"marginY": 16,
				"format": "a4",
				"locale": "zh-CN",
				"hideLinkUnderline": False,
				"hideIcons": False,
				"hideSectionIcons": False,
			},
			"design": {
				"level": {"icon": "star", "type": "hidden"},
				"colors": {
					"primary": "rgba(0, 91, 150, 1)",
					"text": "rgba(0, 0, 0, 1)",
					"background": "rgba(255, 255, 255, 1)",
				},
			},
			"typography": {
				"body": {"fontFamily": "Noto Sans SC", "fontWeights": ["400", "600"], "fontSize": 10, "lineHeight": 1.45},
				"heading": {"fontFamily": "Noto Sans SC", "fontWeights": ["600"], "fontSize": 12, "lineHeight": 1.35},
			},
			"notes": "",
			"styleRules": [],
		},
	}


def render_reactive_resume_pdf(
	version: dict[str, Any],
	output_path: Path,
	*,
	template_id: str | None = None,
	show_photo: bool = True,
	timeout: int = 90,
) -> bool:
	source_template = reactive_template_name(template_id or version.get("template_id"))
	if not source_template:
		return False
	root = _reactive_resume_root()
	script = root / "scripts" / "bosshunter-render-resume.ts"
	if not script.is_file():
		raise ReactiveResumeRenderError(f"Reactive Resume 渲染脚本不存在：{script}")
	if not (root / "node_modules").is_dir():
		raise ReactiveResumeRenderError("Reactive Resume 依赖未安装，请先在 external/resume-template-sources/reactive-resume 运行 pnpm install")

	payload = {"template": source_template, "data": build_reactive_resume_data(version, template_id=template_id, show_photo=show_photo)}
	with tempfile.TemporaryDirectory(prefix="bosshunter_reactive_") as temp_dir:
		input_path = Path(temp_dir) / "resume.json"
		input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
		output_path.parent.mkdir(parents=True, exist_ok=True)
		pnpm = _command_path("pnpm")
		command = [
			pnpm,
			"exec",
			"tsx",
			"--tsconfig",
			"scripts/bosshunter-tsconfig.json",
			"scripts/bosshunter-render-resume.ts",
			str(input_path),
			str(output_path),
		]
		try:
			completed = subprocess.run(
				command,
				cwd=root,
				check=False,
				capture_output=True,
				text=True,
				encoding="utf-8",
				errors="replace",
				timeout=timeout,
			)
		except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
			raise ReactiveResumeRenderError(f"Reactive Resume 渲染器不可用：{exc}") from exc
	if completed.returncode != 0:
		detail = (completed.stderr or completed.stdout or "").strip()
		raise ReactiveResumeRenderError(f"Reactive Resume 渲染失败：{detail[:1200]}")
	return output_path.is_file() and output_path.stat().st_size > 0


def _project_root() -> Path:
	return Path(__file__).resolve().parents[3]


def _reactive_resume_root() -> Path:
	return _project_root() / "external" / "resume-template-sources" / "reactive-resume"


def _command_path(command: str) -> str:
	resolved = shutil.which(command) or shutil.which(f"{command}.cmd")
	return resolved or command


def _text(value: Any) -> str:
	return str(value or "").strip()


def _id(prefix: str) -> str:
	return f"{prefix}-{uuid4().hex[:12]}"


def _website(url: str) -> dict[str, Any]:
	return {"url": url if re.match(r"^https?://", url, flags=re.IGNORECASE) else "", "label": url}


def _item_website(url: str = "") -> dict[str, Any]:
	website = _website(url)
	return {**website, "inlineLink": False}


def _period(start: Any, end: Any) -> str:
	return " - ".join(part for part in [_text(start), _text(end)] if part)


def _rich_html(value: Any) -> str:
	text = _text(value)
	if not text:
		return ""
	if re.search(r"</?[a-z][^>]*>", text, flags=re.IGNORECASE):
		return text
	lines = [line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
	return "".join(f"<p>{html.escape(line)}</p>" for line in lines if line)


def _entry_description(entry: dict[str, Any], *, extra: list[str] | None = None) -> str:
	parts: list[str] = []
	if _text(entry.get("description")):
		parts.append(_rich_html(entry.get("description")))
	materials = [
		_text(material.get("content"))
		for material in entry.get("materials") or []
		if isinstance(material, dict) and _text(material.get("content"))
	]
	if extra:
		materials = [*extra, *materials]
	if materials:
		parts.append("<ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in materials) + "</ul>")
	return "".join(parts)


def _selected_sections(version: dict[str, Any]) -> list[dict[str, Any]]:
	snapshot = version.get("profile_snapshot") if isinstance(version.get("profile_snapshot"), dict) else {}
	sections = snapshot.get("sections") if isinstance(snapshot.get("sections"), list) else []
	selected_section_ids = version.get("selected_section_ids") or snapshot.get("selected_section_ids") or []
	selected_entry_ids = version.get("selected_entry_ids") or snapshot.get("selected_entry_ids") or []
	selected_material_ids = version.get("selected_material_ids") or snapshot.get("selected_material_ids") or []
	result: list[dict[str, Any]] = []
	for section in sections:
		if not isinstance(section, dict):
			continue
		section_id = _text(section.get("id"))
		if selected_section_ids and section_id not in selected_section_ids:
			continue
		entries: list[dict[str, Any]] = []
		for entry in section.get("entries") or []:
			if not isinstance(entry, dict):
				continue
			entry_id = _text(entry.get("id"))
			if selected_entry_ids and entry_id not in selected_entry_ids:
				continue
			materials = [
				material for material in entry.get("materials") or []
				if isinstance(material, dict) and (not selected_material_ids or _text(material.get("id")) in selected_material_ids)
			]
			if _text(entry.get("title")) or _text(entry.get("description")) or materials:
				entries.append({**entry, "materials": materials})
		if _text(section.get("summary")) or entries:
			result.append({**section, "entries": entries})
	return result


def _sections_by_type(sections: list[dict[str, Any]], *section_types: str) -> list[dict[str, Any]]:
	allowed = set(section_types)
	return [section for section in sections if _text(section.get("section_type")) in allowed]


def _section_text(sections: list[dict[str, Any]], section_type: str) -> str:
	lines: list[str] = []
	for section in _sections_by_type(sections, section_type):
		if _text(section.get("summary")):
			lines.append(_text(section.get("summary")))
		for entry in section.get("entries") or []:
			for value in [_text(entry.get("title")), _text(entry.get("description"))]:
				if value:
					lines.append(value)
			for material in entry.get("materials") or []:
				if isinstance(material, dict) and _text(material.get("content")):
					lines.append(_text(material.get("content")))
	return "\n".join(lines)


def _headline(basics: dict[str, Any], profile: dict[str, Any]) -> str:
	preferences = profile.get("preferences") if isinstance(profile.get("preferences"), dict) else {}
	return " · ".join(
		part for part in [
			_text(basics.get("degree")),
			_text(basics.get("school")),
			_text(preferences.get("target_title")) or _text(preferences.get("target")),
		] if part
	)


def _custom_fields(basics: dict[str, Any], contacts: dict[str, Any]) -> list[dict[str, str]]:
	fields: list[tuple[str, str]] = [
		("性别", _text(basics.get("gender"))),
		("出生日期", _text(basics.get("birth_date"))),
		("籍贯", _text(basics.get("native_place"))),
		("政治面貌", _text(basics.get("political_status"))),
	]
	for item in basics.get("custom_fields") or []:
		if isinstance(item, dict):
			label = _text(item.get("label"))
			value = _text(item.get("value"))
			if label and value:
				fields.append((label, value))
	if _text(contacts.get("wechat")):
		fields.append(("微信", _text(contacts.get("wechat"))))
	return [
		{"id": _id("field"), "icon": "info", "text": f"{label}：{value}", "link": ""}
		for label, value in fields if value
	]


def _picture(snapshot: dict[str, Any], show_photo: bool) -> dict[str, Any]:
	url = ""
	photo = snapshot.get("photo") if isinstance(snapshot.get("photo"), dict) else None
	if show_photo and photo:
		path = Path(_text(photo.get("path")))
		if path.is_file():
			url = path.resolve().as_uri()
	return {
		"hidden": not bool(url),
		"fit": "cover",
		"url": url,
		"size": 88,
		"rotation": 0,
		"aspectRatio": 1,
		"borderRadius": 4,
		"borderColor": "rgba(0, 0, 0, 0.15)",
		"borderWidth": 0,
		"shadowColor": "rgba(0, 0, 0, 0.15)",
		"shadowWidth": 0,
	}


def _empty_section(title: str) -> dict[str, Any]:
	return {
		"title": title,
		"icon": "none",
		"columns": 1,
		"hidden": True,
		"showHeading": True,
		"keepTogether": False,
		"startOnNewPage": False,
		"items": [],
	}


def _entry_section(kind: str, items: list[dict[str, Any]]) -> dict[str, Any]:
	return {
		"title": SECTION_TITLES[kind],
		"icon": "none",
		"columns": 1,
		"hidden": not items,
		"showHeading": True,
		"keepTogether": False,
		"startOnNewPage": False,
		"items": items,
	}


def _education_items(education: list[Any]) -> list[dict[str, Any]]:
	items: list[dict[str, Any]] = []
	for item in education:
		if not isinstance(item, dict):
			continue
		school = _text(item.get("school"))
		if not school:
			continue
		items.append(
			{
				"id": _id("edu"),
				"hidden": False,
				"school": school,
				"degree": _text(item.get("degree")),
				"area": _text(item.get("major")),
				"grade": _text(item.get("grade")),
				"location": _text(item.get("location")),
				"period": _period(item.get("start_date"), item.get("end_date")),
				"website": _item_website(),
				"description": _rich_html(item.get("detail")),
			}
		)
	return items


def _experience_items(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
	items: list[dict[str, Any]] = []
	for section in _sections_by_type(sections, "work"):
		for entry in section.get("entries") or []:
			items.append(
				{
					"id": _id("exp"),
					"hidden": False,
					"company": _text(entry.get("organization")) or _text(entry.get("title")) or "经历",
					"position": _text(entry.get("role")),
					"location": "",
					"period": _period(entry.get("start_date"), entry.get("end_date")),
					"website": _item_website(),
					"description": _entry_description(entry),
					"roles": [],
				}
			)
	return items


def _project_items(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
	items: list[dict[str, Any]] = []
	for section in _sections_by_type(sections, "project", "research"):
		for entry in section.get("entries") or []:
			items.append(
				{
					"id": _id("project"),
					"hidden": False,
					"name": _text(entry.get("title")) or "项目经历",
					"period": _period(entry.get("start_date"), entry.get("end_date")),
					"website": _item_website(),
					"description": _entry_description(entry),
				}
			)
	return items


def _publication_items(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
	items: list[dict[str, Any]] = []
	for section in _sections_by_type(sections, "academic"):
		for entry in section.get("entries") or []:
			metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
			extra = [
				part for part in [
					f"作者情况：{_text(entry.get('role'))}" if _text(entry.get("role")) else "",
					f"状态：{_text(entry.get('end_date'))}" if _text(entry.get("end_date")) else "",
					f"检索/分区：{_text(metadata.get('indexing'))}" if _text(metadata.get("indexing")) else "",
				] if part
			]
			items.append(
				{
					"id": _id("pub"),
					"hidden": False,
					"title": _text(entry.get("title")) or "学术成果",
					"publisher": _text(entry.get("organization")),
					"date": _text(entry.get("start_date")),
					"website": _item_website(),
					"description": _entry_description(entry, extra=extra),
				}
			)
	return items


def _award_items(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
	items: list[dict[str, Any]] = []
	for section in _sections_by_type(sections, "award"):
		for entry in section.get("entries") or []:
			items.append(
				{
					"id": _id("award"),
					"hidden": False,
					"title": _text(entry.get("title")) or "荣誉奖项",
					"awarder": _text(entry.get("organization")),
					"date": _period(entry.get("start_date"), entry.get("end_date")),
					"website": _item_website(),
					"description": _entry_description(entry),
				}
			)
	return items


def _certification_items(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
	items: list[dict[str, Any]] = []
	for section in _sections_by_type(sections, "certificate"):
		for entry in section.get("entries") or []:
			items.append(
				{
					"id": _id("cert"),
					"hidden": False,
					"title": _text(entry.get("title")) or "证书",
					"issuer": _text(entry.get("organization")),
					"date": _period(entry.get("start_date"), entry.get("end_date")),
					"website": _item_website(),
					"description": _entry_description(entry),
				}
			)
	return items


def _volunteer_items(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
	items: list[dict[str, Any]] = []
	for section in _sections_by_type(sections, "campus"):
		for entry in section.get("entries") or []:
			items.append(
				{
					"id": _id("vol"),
					"hidden": False,
					"organization": _text(entry.get("title")) or _text(entry.get("organization")) or "校园与实践经历",
					"location": "",
					"period": _period(entry.get("start_date"), entry.get("end_date")),
					"website": _item_website(),
					"description": _entry_description(entry),
				}
			)
	return items


def _skills_section(profile_skills: list[Any], sections: list[dict[str, Any]]) -> dict[str, Any]:
	grouped: dict[str, list[str]] = {}
	for skill in profile_skills:
		text = _text(skill)
		if text:
			grouped.setdefault("核心技能", []).append(text)
	for section in _sections_by_type(sections, "skill"):
		for entry in section.get("entries") or []:
			name = _text(entry.get("title")) or "技能"
			keywords = grouped.setdefault(name, [])
			if _text(entry.get("description")):
				keywords.append(_text(entry.get("description")))
			for material in entry.get("materials") or []:
				if isinstance(material, dict) and _text(material.get("content")):
					keywords.append(_text(material.get("content")))
	items = [
		{
			"id": _id("skill"),
			"hidden": False,
			"icon": "none",
			"iconColor": "",
			"name": name,
			"proficiency": "",
			"level": 0,
			"keywords": _unique(values),
		}
		for name, values in grouped.items()
		if name
	]
	return {
		"title": SECTION_TITLES["skills"],
		"icon": "none",
		"columns": 1,
		"layout": "default",
		"keywordLayout": "list",
		"hidden": not items,
		"showHeading": True,
		"keepTogether": False,
		"startOnNewPage": False,
		"items": items,
	}


def _unique(values: list[str]) -> list[str]:
	result: list[str] = []
	seen: set[str] = set()
	for value in values:
		key = re.sub(r"\s+", " ", value).strip().lower()
		if key and key not in seen:
			seen.add(key)
			result.append(value)
	return result
