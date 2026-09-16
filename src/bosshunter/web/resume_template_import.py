"""User-template import draft helpers for the resume center."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from bosshunter.web import resume_center
from bosshunter.web.resume_text import sanitize_resume_text


SECTION_HINT_RE = re.compile(r"教育|技能|项目|工作|实习|科研|论文|荣誉|证书|自我评价|个人评价")


def build_template_import_preview(filename: str, markdown: str) -> dict[str, Any]:
	text = sanitize_resume_text(markdown)
	lines = [line.strip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
	if not lines:
		raise ValueError("未解析到可识别的模板文字")
	section_count = sum(1 for line in lines if SECTION_HINT_RE.search(line) and len(line) <= 24)
	bullet_count = sum(1 for line in lines if re.match(r"^\s*(?:[-*+•·●]|[0-9]+[.、])\s+", line))
	short_line_count = sum(1 for line in lines if len(line) <= 18)
	contact_count = sum(1 for line in lines if re.search(r"电话|手机|邮箱|微信|GitHub|github|LinkedIn|个人网站", line))
	base_template = "compact-two-column" if short_line_count >= 6 and contact_count >= 2 else "classic-single"
	if section_count <= 2 and bullet_count >= 6:
		base_template = "classic-single"
	return {
		"name": f"{Path(filename).stem or '用户模板'}模板",
		"source_filename": filename,
		"base_template": base_template,
		"template_type": "imported-doc",
		"detected": {
			"sections": section_count,
			"bullets": bullet_count,
			"short_lines": short_line_count,
			"contacts": contact_count,
		},
		"layout": {
			"base_template": base_template,
			"source_filename": filename,
			"detected_sections": section_count,
		},
		"style": {
			"import_method": "text_structure",
			"notes": "根据旧模板文字结构生成的模板草稿，后续可继续人工细化。",
		},
		"preview_excerpt": "\n".join(lines[:16]),
		"warnings": ["当前版本会复用内置稳定布局，不承诺像素级还原原模板。"],
	}


def create_template_from_import_draft(conn: sqlite3.Connection, draft: dict[str, Any]) -> dict[str, Any]:
	if not isinstance(draft, dict):
		raise ValueError("模板草稿必须是对象")
	name = str(draft.get("name") or "").strip()
	if not name:
		raise ValueError("模板名称不能为空")
	layout = draft.get("layout") if isinstance(draft.get("layout"), dict) else {}
	style = draft.get("style") if isinstance(draft.get("style"), dict) else {}
	base_template = str(draft.get("base_template") or layout.get("base_template") or "classic-single").strip()
	if base_template not in {"classic-single", "compact-two-column"}:
		base_template = "classic-single"
	layout = {**layout, "base_template": base_template}
	return resume_center.create_template(
		conn,
		{
			"name": name,
			"template_type": str(draft.get("template_type") or "imported-doc"),
			"source_type": "user",
			"layout": layout,
			"style": style,
			"is_active": True,
		},
	)
