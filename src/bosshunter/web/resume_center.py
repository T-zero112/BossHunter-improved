"""Structured resume-center storage helpers.

The resume center is a local source-of-truth for profile facts and reusable
materials. It is intentionally separate from ``config.profile.resume_path`` so
the existing upload/scoring/delivery flow keeps working while the new resume
DIY surface is built out.
"""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any
from uuid import uuid4

from bosshunter.web.resume_description_format import format_entry_description_text


PROFILE_ID = 1
SECTION_TYPES = {
	"summary",
	"education",
	"project",
	"work",
	"research",
	"skill",
	"academic",
	"campus",
	"award",
	"certificate",
	"self_evaluation",
	"custom",
}
MATERIAL_TYPES = {"bullet", "metric", "keyword", "evidence", "summary"}
TEMPLATE_SOURCES = {"builtin", "user"}
VERSION_STATUSES = {"draft", "ready", "archived"}
PHOTO_OWNER_TYPE = "profile"
PHOTO_OWNER_ID = "1"
PHOTO_ASSET_TYPE = "photo"


def _id(prefix: str) -> str:
	return f"{prefix}_{uuid4().hex[:12]}"


def _loads(value: str | None, fallback: Any) -> Any:
	try:
		return json.loads(value or "")
	except (TypeError, json.JSONDecodeError):
		return fallback


def _dumps(value: Any, field: str, expected: type) -> str:
	if value is None:
		value = [] if expected is list else {}
	if not isinstance(value, expected):
		label = "数组" if expected is list else "对象"
		raise ValueError(f"{field} 必须是{label}")
	return json.dumps(value, ensure_ascii=False)


def _text(value: Any, field: str, *, required: bool = False, max_len: int = 2000) -> str:
	if value is None:
		value = ""
	if not isinstance(value, str):
		raise ValueError(f"{field} 必须是字符串")
	value = value.strip()
	if required and not value:
		raise ValueError(f"{field} 不能为空")
	if len(value) > max_len:
		raise ValueError(f"{field} 过长，请控制在 {max_len} 字以内")
	return value


def _int(value: Any, field: str, *, default: int = 0, min_value: int | None = None, max_value: int | None = None) -> int:
	if value is None:
		return default
	if isinstance(value, bool) or not isinstance(value, int):
		raise ValueError(f"{field} 必须是整数")
	if min_value is not None and value < min_value:
		raise ValueError(f"{field} 不能小于 {min_value}")
	if max_value is not None and value > max_value:
		raise ValueError(f"{field} 不能大于 {max_value}")
	return value


def _bool_int(value: Any, field: str, *, default: bool = True) -> int:
	if value is None:
		return 1 if default else 0
	if not isinstance(value, bool):
		raise ValueError(f"{field} 必须是布尔值")
	return 1 if value else 0


def _string_list(value: Any, field: str) -> list[str]:
	if value is None:
		return []
	if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
		raise ValueError(f"{field} 必须是字符串数组")
	return [item for item in value if item.strip()]


def ensure_profile(conn: sqlite3.Connection) -> None:
	conn.execute("INSERT OR IGNORE INTO resume_profiles (id) VALUES (?)", (PROFILE_ID,))
	conn.commit()


def _profile_row(row: sqlite3.Row) -> dict[str, Any]:
	return {
		"id": row["id"],
		"basics": _loads(row["basics_json"], {}),
		"contacts": _loads(row["contacts_json"], {}),
		"education": _loads(row["education_json"], []),
		"skills": _loads(row["skills_json"], []),
		"preferences": _loads(row["preferences_json"], {}),
		"created_at": row["created_at"],
		"updated_at": row["updated_at"],
	}


def get_profile(conn: sqlite3.Connection) -> dict[str, Any]:
	ensure_profile(conn)
	row = conn.execute("SELECT * FROM resume_profiles WHERE id = ?", (PROFILE_ID,)).fetchone()
	return _profile_row(row)


def update_profile(conn: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
	if not isinstance(data, dict):
		raise ValueError("请求体必须是对象")
	ensure_profile(conn)
	conn.execute(
		"""
		UPDATE resume_profiles
		SET basics_json = ?, contacts_json = ?, education_json = ?, skills_json = ?,
			preferences_json = ?, updated_at = CURRENT_TIMESTAMP
		WHERE id = ?
		""",
		(
			_dumps(data.get("basics"), "basics", dict),
			_dumps(data.get("contacts"), "contacts", dict),
			_dumps(data.get("education"), "education", list),
			_dumps(data.get("skills"), "skills", list),
			_dumps(data.get("preferences"), "preferences", dict),
			PROFILE_ID,
		),
	)
	conn.commit()
	return get_profile(conn)


def _material_row(row: sqlite3.Row) -> dict[str, Any]:
	return {
		"id": row["id"],
		"entry_id": row["entry_id"],
		"material_type": row["material_type"],
		"content": row["content"],
		"evidence": row["evidence"],
		"tags": _loads(row["tags_json"], []),
		"jd_keywords": _loads(row["jd_keywords_json"], []),
		"strength": row["strength"],
		"visible": bool(row["visible"]),
		"sort_order": row["sort_order"],
		"metadata": _loads(row["metadata_json"], {}),
		"created_at": row["created_at"],
		"updated_at": row["updated_at"],
	}


def _entry_row(row: sqlite3.Row, materials: list[dict[str, Any]] | None = None) -> dict[str, Any]:
	result = {
		"id": row["id"],
		"section_id": row["section_id"],
		"entry_type": row["entry_type"],
		"title": row["title"],
		"organization": row["organization"],
		"role": row["role"],
		"start_date": row["start_date"],
		"end_date": row["end_date"],
		"description": row["description"],
		"visible": bool(row["visible"]),
		"sort_order": row["sort_order"],
		"metadata": _loads(row["metadata_json"], {}),
		"created_at": row["created_at"],
		"updated_at": row["updated_at"],
	}
	if materials is not None:
		result["materials"] = materials
	return result


def _section_row(row: sqlite3.Row, entries: list[dict[str, Any]] | None = None) -> dict[str, Any]:
	result = {
		"id": row["id"],
		"profile_id": row["profile_id"],
		"section_type": row["section_type"],
		"title": row["title"],
		"summary": row["summary"],
		"visible": bool(row["visible"]),
		"sort_order": row["sort_order"],
		"metadata": _loads(row["metadata_json"], {}),
		"created_at": row["created_at"],
		"updated_at": row["updated_at"],
	}
	if entries is not None:
		result["entries"] = entries
	return result


def list_sections(conn: sqlite3.Connection) -> list[dict[str, Any]]:
	ensure_profile(conn)
	section_rows = conn.execute(
		"SELECT * FROM resume_sections WHERE profile_id = ? ORDER BY sort_order, created_at",
		(PROFILE_ID,),
	).fetchall()
	entry_rows = conn.execute(
		"""
		SELECT e.* FROM resume_entries e
		JOIN resume_sections s ON s.id = e.section_id
		WHERE s.profile_id = ?
		ORDER BY e.sort_order, e.created_at
		""",
		(PROFILE_ID,),
	).fetchall()
	material_rows = conn.execute(
		"""
		SELECT m.* FROM resume_materials m
		JOIN resume_entries e ON e.id = m.entry_id
		JOIN resume_sections s ON s.id = e.section_id
		WHERE s.profile_id = ?
		ORDER BY m.sort_order, m.created_at
		""",
		(PROFILE_ID,),
	).fetchall()
	materials_by_entry: dict[str, list[dict[str, Any]]] = {}
	for row in material_rows:
		materials_by_entry.setdefault(row["entry_id"], []).append(_material_row(row))
	entries_by_section: dict[str, list[dict[str, Any]]] = {}
	for row in entry_rows:
		entries_by_section.setdefault(row["section_id"], []).append(_entry_row(row, materials_by_entry.get(row["id"], [])))
	return [_section_row(row, entries_by_section.get(row["id"], [])) for row in section_rows]


def create_section(conn: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
	if not isinstance(data, dict):
		raise ValueError("请求体必须是对象")
	ensure_profile(conn)
	section_type = _text(data.get("section_type", "custom"), "section_type", required=True, max_len=40)
	if section_type not in SECTION_TYPES:
		raise ValueError("section_type 无效")
	section_id = data.get("id") if isinstance(data.get("id"), str) and data.get("id").strip() else _id("sec")
	conn.execute(
		"""
		INSERT INTO resume_sections (
			id, profile_id, section_type, title, summary, visible, sort_order, metadata_json
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
		""",
		(
			section_id,
			PROFILE_ID,
			section_type,
			_text(data.get("title"), "title", required=True, max_len=120),
			_text(data.get("summary"), "summary", max_len=2000),
			_bool_int(data.get("visible"), "visible"),
			_int(data.get("sort_order"), "sort_order"),
			_dumps(data.get("metadata"), "metadata", dict),
		),
	)
	conn.commit()
	return get_section(conn, section_id)


def get_section(conn: sqlite3.Connection, section_id: str) -> dict[str, Any]:
	row = conn.execute("SELECT * FROM resume_sections WHERE id = ?", (section_id,)).fetchone()
	if row is None:
		raise KeyError("简历板块不存在")
	return _section_row(row, [])


def update_section(conn: sqlite3.Connection, section_id: str, data: dict[str, Any]) -> dict[str, Any]:
	if not isinstance(data, dict):
		raise ValueError("请求体必须是对象")
	current = get_section(conn, section_id)
	section_type = _text(data.get("section_type", current["section_type"]), "section_type", required=True, max_len=40)
	if section_type not in SECTION_TYPES:
		raise ValueError("section_type 无效")
	conn.execute(
		"""
		UPDATE resume_sections
		SET section_type = ?, title = ?, summary = ?, visible = ?, sort_order = ?,
			metadata_json = ?, updated_at = CURRENT_TIMESTAMP
		WHERE id = ?
		""",
		(
			section_type,
			_text(data.get("title", current["title"]), "title", required=True, max_len=120),
			_text(data.get("summary", current["summary"]), "summary", max_len=2000),
			_bool_int(data.get("visible", current["visible"]), "visible"),
			_int(data.get("sort_order", current["sort_order"]), "sort_order"),
			_dumps(data.get("metadata", current["metadata"]), "metadata", dict),
			section_id,
		),
	)
	conn.commit()
	return get_section(conn, section_id)


def delete_section(conn: sqlite3.Connection, section_id: str) -> None:
	get_section(conn, section_id)
	conn.execute("DELETE FROM resume_sections WHERE id = ?", (section_id,))
	conn.commit()


def create_entry(conn: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
	if not isinstance(data, dict):
		raise ValueError("请求体必须是对象")
	section_id = _text(data.get("section_id"), "section_id", required=True, max_len=80)
	section = get_section(conn, section_id)
	entry_id = data.get("id") if isinstance(data.get("id"), str) and data.get("id").strip() else _id("ent")
	description = _entry_description_for_save(data.get("description"), section.get("section_type"))
	conn.execute(
		"""
		INSERT INTO resume_entries (
			id, section_id, entry_type, title, organization, role, start_date, end_date,
			description, visible, sort_order, metadata_json
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		""",
		(
			entry_id,
			section_id,
			_text(data.get("entry_type", "experience"), "entry_type", required=True, max_len=40),
			_text(data.get("title"), "title", required=True, max_len=160),
			_text(data.get("organization"), "organization", max_len=160),
			_text(data.get("role"), "role", max_len=160),
			_text(data.get("start_date"), "start_date", max_len=40),
			_text(data.get("end_date"), "end_date", max_len=40),
			description,
			_bool_int(data.get("visible"), "visible"),
			_int(data.get("sort_order"), "sort_order"),
			_dumps(data.get("metadata"), "metadata", dict),
		),
	)
	conn.commit()
	return get_entry(conn, entry_id)


def get_entry(conn: sqlite3.Connection, entry_id: str) -> dict[str, Any]:
	row = conn.execute("SELECT * FROM resume_entries WHERE id = ?", (entry_id,)).fetchone()
	if row is None:
		raise KeyError("简历经历不存在")
	return _entry_row(row, [])


def update_entry(conn: sqlite3.Connection, entry_id: str, data: dict[str, Any]) -> dict[str, Any]:
	if not isinstance(data, dict):
		raise ValueError("请求体必须是对象")
	current = get_entry(conn, entry_id)
	if "section_id" in data:
		section_id = _text(data.get("section_id"), "section_id", required=True, max_len=80)
	else:
		section_id = current["section_id"]
	section = get_section(conn, section_id)
	description = _entry_description_for_save(data.get("description", current["description"]), section.get("section_type"))
	conn.execute(
		"""
		UPDATE resume_entries
		SET section_id = ?, entry_type = ?, title = ?, organization = ?, role = ?,
			start_date = ?, end_date = ?, description = ?, visible = ?, sort_order = ?,
			metadata_json = ?, updated_at = CURRENT_TIMESTAMP
		WHERE id = ?
		""",
		(
			section_id,
			_text(data.get("entry_type", current["entry_type"]), "entry_type", required=True, max_len=40),
			_text(data.get("title", current["title"]), "title", required=True, max_len=160),
			_text(data.get("organization", current["organization"]), "organization", max_len=160),
			_text(data.get("role", current["role"]), "role", max_len=160),
			_text(data.get("start_date", current["start_date"]), "start_date", max_len=40),
			_text(data.get("end_date", current["end_date"]), "end_date", max_len=40),
			description,
			_bool_int(data.get("visible", current["visible"]), "visible"),
			_int(data.get("sort_order", current["sort_order"]), "sort_order"),
			_dumps(data.get("metadata", current["metadata"]), "metadata", dict),
			entry_id,
		),
	)
	conn.commit()
	return get_entry(conn, entry_id)


def _entry_description_for_save(value: Any, section_type: Any) -> str:
	description = _text(value, "description", max_len=4000)
	if _looks_like_html(description):
		return description
	if str(section_type or "") in {"project", "work"}:
		return format_entry_description_text(description)[:4000]
	return description


def _looks_like_html(value: str) -> bool:
	return bool(re.search(r"</?[a-z][^>]*>", str(value or ""), flags=re.IGNORECASE))


def delete_entry(conn: sqlite3.Connection, entry_id: str) -> None:
	get_entry(conn, entry_id)
	conn.execute("DELETE FROM resume_entries WHERE id = ?", (entry_id,))
	conn.commit()


def create_material(conn: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
	if not isinstance(data, dict):
		raise ValueError("请求体必须是对象")
	entry_id = _text(data.get("entry_id"), "entry_id", required=True, max_len=80)
	get_entry(conn, entry_id)
	material_type = _text(data.get("material_type", "bullet"), "material_type", required=True, max_len=40)
	if material_type not in MATERIAL_TYPES:
		raise ValueError("material_type 无效")
	material_id = data.get("id") if isinstance(data.get("id"), str) and data.get("id").strip() else _id("mat")
	conn.execute(
		"""
		INSERT INTO resume_materials (
			id, entry_id, material_type, content, evidence, tags_json, jd_keywords_json,
			strength, visible, sort_order, metadata_json
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		""",
		(
			material_id,
			entry_id,
			material_type,
			_text(data.get("content"), "content", required=True, max_len=4000),
			_text(data.get("evidence"), "evidence", max_len=2000),
			_dumps(data.get("tags"), "tags", list),
			_dumps(data.get("jd_keywords"), "jd_keywords", list),
			_int(data.get("strength"), "strength", default=3, min_value=1, max_value=5),
			_bool_int(data.get("visible"), "visible"),
			_int(data.get("sort_order"), "sort_order"),
			_dumps(data.get("metadata"), "metadata", dict),
		),
	)
	conn.commit()
	return get_material(conn, material_id)


def get_material(conn: sqlite3.Connection, material_id: str) -> dict[str, Any]:
	row = conn.execute("SELECT * FROM resume_materials WHERE id = ?", (material_id,)).fetchone()
	if row is None:
		raise KeyError("简历素材不存在")
	return _material_row(row)


def update_material(conn: sqlite3.Connection, material_id: str, data: dict[str, Any]) -> dict[str, Any]:
	if not isinstance(data, dict):
		raise ValueError("请求体必须是对象")
	current = get_material(conn, material_id)
	if "entry_id" in data:
		entry_id = _text(data.get("entry_id"), "entry_id", required=True, max_len=80)
		get_entry(conn, entry_id)
	else:
		entry_id = current["entry_id"]
	material_type = _text(data.get("material_type", current["material_type"]), "material_type", required=True, max_len=40)
	if material_type not in MATERIAL_TYPES:
		raise ValueError("material_type 无效")
	conn.execute(
		"""
		UPDATE resume_materials
		SET entry_id = ?, material_type = ?, content = ?, evidence = ?, tags_json = ?,
			jd_keywords_json = ?, strength = ?, visible = ?, sort_order = ?,
			metadata_json = ?, updated_at = CURRENT_TIMESTAMP
		WHERE id = ?
		""",
		(
			entry_id,
			material_type,
			_text(data.get("content", current["content"]), "content", required=True, max_len=4000),
			_text(data.get("evidence", current["evidence"]), "evidence", max_len=2000),
			_dumps(data.get("tags", current["tags"]), "tags", list),
			_dumps(data.get("jd_keywords", current["jd_keywords"]), "jd_keywords", list),
			_int(data.get("strength", current["strength"]), "strength", default=3, min_value=1, max_value=5),
			_bool_int(data.get("visible", current["visible"]), "visible"),
			_int(data.get("sort_order", current["sort_order"]), "sort_order"),
			_dumps(data.get("metadata", current["metadata"]), "metadata", dict),
			material_id,
		),
	)
	conn.commit()
	return get_material(conn, material_id)


def delete_material(conn: sqlite3.Connection, material_id: str) -> None:
	get_material(conn, material_id)
	conn.execute("DELETE FROM resume_materials WHERE id = ?", (material_id,))
	conn.commit()


def _asset_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
	if row is None:
		return None
	return {
		"id": row["id"],
		"owner_type": row["owner_type"],
		"owner_id": row["owner_id"],
		"asset_type": row["asset_type"],
		"path": row["path"],
		"mime_type": row["mime_type"],
		"file_size": row["file_size"],
		"metadata": _loads(row["metadata_json"], {}),
		"created_at": row["created_at"],
	}


def get_profile_photo(conn: sqlite3.Connection) -> dict[str, Any] | None:
	row = conn.execute(
		"""
		SELECT * FROM resume_assets
		WHERE owner_type = ? AND owner_id = ? AND asset_type = ?
		ORDER BY created_at DESC
		LIMIT 1
		""",
		(PHOTO_OWNER_TYPE, PHOTO_OWNER_ID, PHOTO_ASSET_TYPE),
	).fetchone()
	return _asset_row(row)


def save_profile_photo(conn: sqlite3.Connection, path: str, mime_type: str, file_size: int) -> dict[str, Any]:
	if file_size <= 0:
		raise ValueError("照片文件为空")
	asset_id = "profile_photo"
	conn.execute(
		"""
		DELETE FROM resume_assets
		WHERE owner_type = ? AND owner_id = ? AND asset_type = ?
		""",
		(PHOTO_OWNER_TYPE, PHOTO_OWNER_ID, PHOTO_ASSET_TYPE),
	)
	conn.execute(
		"""
		INSERT INTO resume_assets (
			id, owner_type, owner_id, asset_type, path, mime_type, file_size, metadata_json
		) VALUES (?, ?, ?, ?, ?, ?, ?, '{}')
		""",
		(asset_id, PHOTO_OWNER_TYPE, PHOTO_OWNER_ID, PHOTO_ASSET_TYPE, path, mime_type, file_size),
	)
	conn.commit()
	photo = get_profile_photo(conn)
	if photo is None:
		raise ValueError("照片保存失败")
	return photo


def delete_profile_photo(conn: sqlite3.Connection) -> dict[str, Any] | None:
	photo = get_profile_photo(conn)
	conn.execute(
		"""
		DELETE FROM resume_assets
		WHERE owner_type = ? AND owner_id = ? AND asset_type = ?
		""",
		(PHOTO_OWNER_TYPE, PHOTO_OWNER_ID, PHOTO_ASSET_TYPE),
	)
	conn.commit()
	return photo


def _template_row(row: sqlite3.Row) -> dict[str, Any]:
	return {
		"id": row["id"],
		"name": row["name"],
		"template_type": row["template_type"],
		"source_type": row["source_type"],
		"layout": _loads(row["layout_json"], {}),
		"style": _loads(row["style_json"], {}),
		"preview_path": row["preview_path"],
		"is_active": bool(row["is_active"]),
		"created_at": row["created_at"],
		"updated_at": row["updated_at"],
	}


def list_templates(conn: sqlite3.Connection) -> list[dict[str, Any]]:
	rows = conn.execute(
		"SELECT * FROM resume_templates ORDER BY source_type = 'user', created_at, name"
	).fetchall()
	return [_template_row(row) for row in rows]


def get_template(conn: sqlite3.Connection, template_id: str | None) -> dict[str, Any] | None:
	if not template_id:
		return None
	row = conn.execute("SELECT * FROM resume_templates WHERE id = ?", (template_id,)).fetchone()
	if row is None:
		raise KeyError("简历模板不存在")
	return _template_row(row)


def create_template(conn: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
	if not isinstance(data, dict):
		raise ValueError("请求体必须是对象")
	source_type = _text(data.get("source_type", "user"), "source_type", required=True, max_len=20)
	if source_type not in TEMPLATE_SOURCES:
		raise ValueError("source_type 无效")
	if source_type == "builtin":
		raise ValueError("不能通过 API 新增内置模板")
	template_id = data.get("id") if isinstance(data.get("id"), str) and data.get("id").strip() else _id("tpl")
	conn.execute(
		"""
		INSERT INTO resume_templates (
			id, name, template_type, source_type, layout_json, style_json, preview_path, is_active
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
		""",
		(
			template_id,
			_text(data.get("name"), "name", required=True, max_len=120),
			_text(data.get("template_type", "custom"), "template_type", required=True, max_len=80),
			source_type,
			_dumps(data.get("layout"), "layout", dict),
			_dumps(data.get("style"), "style", dict),
			_text(data.get("preview_path"), "preview_path", max_len=500),
			_bool_int(data.get("is_active"), "is_active"),
		),
	)
	conn.commit()
	return get_template(conn, template_id) or {}


def delete_template(conn: sqlite3.Connection, template_id: str) -> None:
	template = get_template(conn, template_id)
	if template["source_type"] == "builtin":
		raise ValueError("内置模板不能删除")
	conn.execute("UPDATE resume_versions SET template_id = NULL WHERE template_id = ?", (template_id,))
	conn.execute("DELETE FROM resume_templates WHERE id = ?", (template_id,))
	conn.commit()


def _version_row(row: sqlite3.Row) -> dict[str, Any]:
	return {
		"id": row["id"],
		"name": row["name"],
		"target_job_id": row["target_job_id"],
		"target_company": row["target_company"],
		"target_title": row["target_title"],
		"template_id": row["template_id"],
		"profile_snapshot": _loads(row["profile_snapshot_json"], {}),
		"selected_section_ids": _loads(row["selected_section_ids_json"], []),
		"selected_entry_ids": _loads(row["selected_entry_ids_json"], []),
		"selected_material_ids": _loads(row["selected_material_ids_json"], []),
		"rendered_markdown": row["rendered_markdown"],
		"status": row["status"],
		"created_at": row["created_at"],
		"updated_at": row["updated_at"],
	}


def list_versions(conn: sqlite3.Connection) -> list[dict[str, Any]]:
	rows = conn.execute("SELECT * FROM resume_versions ORDER BY updated_at DESC, created_at DESC").fetchall()
	return [_version_row(row) for row in rows]


def get_version(conn: sqlite3.Connection, version_id: str) -> dict[str, Any]:
	row = conn.execute("SELECT * FROM resume_versions WHERE id = ?", (version_id,)).fetchone()
	if row is None:
		raise KeyError("简历版本不存在")
	return _version_row(row)


def _default_material_ids(sections: list[dict[str, Any]]) -> list[str]:
	ids: list[str] = []
	for section in sections:
		if not section.get("visible", True):
			continue
		for entry in section.get("entries", []):
			if not entry.get("visible", True):
				continue
			for material in entry.get("materials", []):
				if material.get("visible", True):
					ids.append(material["id"])
	return ids


def _default_section_ids(sections: list[dict[str, Any]]) -> list[str]:
	return [section["id"] for section in sections if section.get("visible", True)]


def _default_entry_ids(sections: list[dict[str, Any]]) -> list[str]:
	ids: list[str] = []
	for section in sections:
		if not section.get("visible", True):
			continue
		for entry in section.get("entries", []):
			if entry.get("visible", True):
				ids.append(entry["id"])
	return ids


def create_version(conn: sqlite3.Connection, data: dict[str, Any]) -> dict[str, Any]:
	if not isinstance(data, dict):
		raise ValueError("请求体必须是对象")
	sections = list_sections(conn)
	template_id = data.get("template_id")
	template = get_template(conn, template_id) if template_id else None
	selected_section_ids = data.get("selected_section_ids")
	if selected_section_ids is None:
		selected_section_ids = _default_section_ids(sections)
	else:
		selected_section_ids = _string_list(selected_section_ids, "selected_section_ids")
	selected_entry_ids = data.get("selected_entry_ids")
	if selected_entry_ids is None:
		selected_entry_ids = _default_entry_ids(sections)
	else:
		selected_entry_ids = _string_list(selected_entry_ids, "selected_entry_ids")
	selected_material_ids = data.get("selected_material_ids")
	if selected_material_ids is None:
		selected_material_ids = _default_material_ids(sections)
	else:
		selected_material_ids = _string_list(selected_material_ids, "selected_material_ids")
	status = _text(data.get("status", "draft"), "status", required=True, max_len=20)
	if status not in VERSION_STATUSES:
		raise ValueError("status 无效")
	version_id = data.get("id") if isinstance(data.get("id"), str) and data.get("id").strip() else _id("ver")
	snapshot = {
		"profile": get_profile(conn),
		"sections": sections,
		"template": template,
		"photo": get_profile_photo(conn),
		"selected_section_ids": selected_section_ids,
		"selected_entry_ids": selected_entry_ids,
		"selected_material_ids": selected_material_ids,
	}
	conn.execute(
		"""
		INSERT INTO resume_versions (
			id, name, target_job_id, target_company, target_title, template_id,
			profile_snapshot_json, selected_section_ids_json, selected_entry_ids_json,
			selected_material_ids_json, rendered_markdown, status
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		""",
		(
			version_id,
			_text(data.get("name"), "name", required=True, max_len=160),
			_text(data.get("target_job_id"), "target_job_id", max_len=100) or None,
			_text(data.get("target_company"), "target_company", max_len=160),
			_text(data.get("target_title"), "target_title", max_len=160),
			template_id,
			json.dumps(snapshot, ensure_ascii=False),
			json.dumps(selected_section_ids, ensure_ascii=False),
			json.dumps(selected_entry_ids, ensure_ascii=False),
			json.dumps(selected_material_ids, ensure_ascii=False),
			_text(data.get("rendered_markdown"), "rendered_markdown", max_len=50000),
			status,
		),
	)
	conn.commit()
	return get_version(conn, version_id)


def update_version(conn: sqlite3.Connection, version_id: str, data: dict[str, Any]) -> dict[str, Any]:
	if not isinstance(data, dict):
		raise ValueError("请求体必须是对象")
	current = get_version(conn, version_id)
	status = _text(data.get("status", current["status"]), "status", required=True, max_len=20)
	if status not in VERSION_STATUSES:
		raise ValueError("status 无效")
	selected_section_ids = _string_list(data.get("selected_section_ids", current["selected_section_ids"]), "selected_section_ids")
	selected_entry_ids = _string_list(data.get("selected_entry_ids", current["selected_entry_ids"]), "selected_entry_ids")
	selected_material_ids = _string_list(data.get("selected_material_ids", current["selected_material_ids"]), "selected_material_ids")
	template_id = data.get("template_id", current["template_id"])
	if template_id:
		get_template(conn, template_id)
	conn.execute(
		"""
		UPDATE resume_versions
		SET name = ?, target_job_id = ?, target_company = ?, target_title = ?,
			template_id = ?, selected_section_ids_json = ?, selected_entry_ids_json = ?,
			selected_material_ids_json = ?, rendered_markdown = ?, status = ?,
			updated_at = CURRENT_TIMESTAMP
		WHERE id = ?
		""",
		(
			_text(data.get("name", current["name"]), "name", required=True, max_len=160),
			_text(data.get("target_job_id", current["target_job_id"]), "target_job_id", max_len=100) or None,
			_text(data.get("target_company", current["target_company"]), "target_company", max_len=160),
			_text(data.get("target_title", current["target_title"]), "target_title", max_len=160),
			template_id,
			json.dumps(selected_section_ids, ensure_ascii=False),
			json.dumps(selected_entry_ids, ensure_ascii=False),
			json.dumps(selected_material_ids, ensure_ascii=False),
			_text(data.get("rendered_markdown", current["rendered_markdown"]), "rendered_markdown", max_len=50000),
			status,
			version_id,
		),
	)
	conn.commit()
	return get_version(conn, version_id)


def duplicate_version(conn: sqlite3.Connection, version_id: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
	current = get_version(conn, version_id)
	data = data or {}
	new_id = _id("ver")
	name = _text(data.get("name", f"{current['name']} 副本"), "name", required=True, max_len=160)
	conn.execute(
		"""
		INSERT INTO resume_versions (
			id, name, target_job_id, target_company, target_title, template_id,
			profile_snapshot_json, selected_section_ids_json, selected_entry_ids_json,
			selected_material_ids_json, rendered_markdown, status
		)
		SELECT ?, ?, target_job_id, target_company, target_title, template_id,
			profile_snapshot_json, selected_section_ids_json, selected_entry_ids_json,
			selected_material_ids_json, rendered_markdown, 'draft'
		FROM resume_versions
		WHERE id = ?
		""",
		(new_id, name, version_id),
	)
	conn.commit()
	return get_version(conn, new_id)


def delete_version(conn: sqlite3.Connection, version_id: str) -> None:
	get_version(conn, version_id)
	conn.execute("DELETE FROM resume_versions WHERE id = ?", (version_id,))
	conn.commit()


def reset_resume_center(conn: sqlite3.Connection) -> dict[str, Any]:
	"""Clear user-authored resume-center data while preserving builtin templates."""
	ensure_profile(conn)
	counts = {
		"materials": conn.execute("SELECT COUNT(*) AS cnt FROM resume_materials").fetchone()["cnt"],
		"entries": conn.execute("SELECT COUNT(*) AS cnt FROM resume_entries").fetchone()["cnt"],
		"sections": conn.execute("SELECT COUNT(*) AS cnt FROM resume_sections WHERE profile_id = ?", (PROFILE_ID,)).fetchone()["cnt"],
		"versions": conn.execute("SELECT COUNT(*) AS cnt FROM resume_versions").fetchone()["cnt"],
		"user_templates": conn.execute("SELECT COUNT(*) AS cnt FROM resume_templates WHERE source_type = 'user'").fetchone()["cnt"],
		"assets": conn.execute("SELECT COUNT(*) AS cnt FROM resume_assets").fetchone()["cnt"],
	}
	asset_paths = [
		row["path"]
		for row in conn.execute("SELECT path FROM resume_assets WHERE path != ''").fetchall()
	]
	conn.execute("DELETE FROM resume_materials")
	conn.execute("DELETE FROM resume_entries")
	conn.execute("DELETE FROM resume_sections WHERE profile_id = ?", (PROFILE_ID,))
	conn.execute("DELETE FROM resume_versions")
	conn.execute("DELETE FROM resume_templates WHERE source_type = 'user'")
	conn.execute("DELETE FROM resume_assets")
	conn.execute(
		"""
		UPDATE resume_profiles
		SET basics_json = '{}', contacts_json = '{}', education_json = '[]',
			skills_json = '[]', preferences_json = '{}', updated_at = CURRENT_TIMESTAMP
		WHERE id = ?
		""",
		(PROFILE_ID,),
	)
	conn.commit()
	return {"success": True, "deleted": counts, "asset_paths": asset_paths, "center": get_resume_center(conn)}


def get_resume_center(conn: sqlite3.Connection) -> dict[str, Any]:
	photo = get_profile_photo(conn)
	return {
		"profile": get_profile(conn),
		"photo": photo,
		"sections": list_sections(conn),
		"templates": list_templates(conn),
		"versions": list_versions(conn),
	}
