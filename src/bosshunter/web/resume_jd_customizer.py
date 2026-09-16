"""Create resume versions from a job description without inventing facts."""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from bosshunter.web import resume_center


IMPORTANT_TERMS = [
	"ros1", "ros2", "ros", "python", "pytorch", "lerobot", "vla", "llm", "openai", "prompt",
	"agent", "多agent", "大模型", "机器人", "机械臂", "机械爪", "控制", "抓取", "感知", "识别",
	"视觉", "运动", "导航", "标定", "采集", "测试", "调试", "仿真", "硬件", "嵌入式", "c++",
	"cuda", "深度学习", "机器学习", "pdf", "ppt", "数据分析",
]


def create_resume_version_for_job(
	conn: sqlite3.Connection,
	job: dict[str, Any],
	*,
	template_id: str | None = None,
	version_name: str | None = None,
) -> dict[str, Any]:
	sections = resume_center.list_sections(conn)
	templates = resume_center.list_templates(conn)
	selected_template = template_id or (templates[0]["id"] if templates else "classic-single")
	jd_text = " ".join(str(job.get(key) or "") for key in ("title", "company", "jd", "score_reason"))
	selected_section_ids: set[str] = set()
	selected_entry_ids: set[str] = set()
	selected_material_ids: set[str] = set()
	match_rows: list[dict[str, Any]] = []

	for section in sections:
		if not section.get("visible", True):
			continue
		for entry in section.get("entries") or []:
			if not entry.get("visible", True):
				continue
			entry_score = _match_score(jd_text, " ".join([
				str(section.get("title") or ""),
				str(entry.get("title") or ""),
				str(entry.get("description") or ""),
				str(entry.get("organization") or ""),
				str(entry.get("role") or ""),
			]))
			matched_materials: list[tuple[dict[str, Any], int]] = []
			for material in entry.get("materials") or []:
				if not material.get("visible", True):
					continue
				material_score = _material_score(jd_text, material)
				if material_score > 0:
					matched_materials.append((material, material_score))
			if entry_score > 0 or matched_materials:
				selected_section_ids.add(section["id"])
				selected_entry_ids.add(entry["id"])
				for material, _ in sorted(matched_materials, key=lambda item: item[1], reverse=True)[:8]:
					selected_material_ids.add(material["id"])
				match_rows.append({
					"section": section.get("title") or section.get("section_type"),
					"entry": entry.get("title"),
					"score": entry_score + sum(score for _, score in matched_materials),
					"materials": len(matched_materials),
				})

	if not selected_material_ids:
		for section in sections:
			if not section.get("visible", True):
				continue
			selected_section_ids.add(section["id"])
			for entry in section.get("entries") or []:
				if not entry.get("visible", True):
					continue
				selected_entry_ids.add(entry["id"])
				for material in entry.get("materials") or []:
					if material.get("visible", True):
						selected_material_ids.add(material["id"])
		fallback = True
	else:
		fallback = False

	name = version_name or _default_version_name(job)
	version = resume_center.create_version(
		conn,
		{
			"name": name[:160],
			"target_job_id": str(job.get("id") or ""),
			"target_company": str(job.get("company") or ""),
			"target_title": str(job.get("title") or ""),
			"template_id": selected_template,
			"selected_section_ids": sorted(selected_section_ids),
			"selected_entry_ids": sorted(selected_entry_ids),
			"selected_material_ids": sorted(selected_material_ids),
			"status": "draft",
		},
	)
	return {
		"success": True,
		"version": version,
		"match_summary": {
			"fallback_used": fallback,
			"matched_entries": len(match_rows),
			"selected_sections": len(selected_section_ids),
			"selected_entries": len(selected_entry_ids),
			"selected_materials": len(selected_material_ids),
			"top_matches": sorted(match_rows, key=lambda item: item["score"], reverse=True)[:8],
		},
	}


def _default_version_name(job: dict[str, Any]) -> str:
	company = str(job.get("company") or "目标公司").strip()
	title = str(job.get("title") or "目标岗位").strip()
	return f"{company}_{title}_定制简历"


def _material_score(jd_text: str, material: dict[str, Any]) -> int:
	score = _match_score(jd_text, str(material.get("content") or ""))
	for field in ("tags", "jd_keywords"):
		values = material.get(field) if isinstance(material.get(field), list) else []
		for value in values:
			token = str(value or "").strip().lower()
			if token and token in jd_text.lower():
				score += 4
	return score


def _match_score(jd_text: str, candidate_text: str) -> int:
	jd_lower = jd_text.lower()
	candidate_lower = candidate_text.lower()
	score = 0
	for term in IMPORTANT_TERMS:
		if term.lower() in jd_lower and term.lower() in candidate_lower:
			score += 3
	for token in _keywords(candidate_text):
		if token.lower() in jd_lower:
			score += 1
	return score


def _keywords(text: str) -> set[str]:
	result = set(re.findall(r"[A-Za-z][A-Za-z0-9+#.\-]{1,24}", text))
	for token in re.findall(r"[\u4e00-\u9fa5]{2,12}", text):
		if any(term in token for term in ("项目", "系统", "机器人", "机械", "控制", "感知", "识别", "抓取", "采集", "测试", "调试", "大模型", "简历")):
			result.add(token)
	return result
