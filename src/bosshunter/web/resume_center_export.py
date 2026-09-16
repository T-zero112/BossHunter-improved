"""PDF export helpers for structured resume versions."""

from __future__ import annotations

import html
import re
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable

from bosshunter.web.resume_text import sanitize_resume_text
from bosshunter.web.resume_upload import safe_resume_filename


PdfRenderer = Callable[[str, Path], bool]


def _text(value: Any) -> str:
	return str(value or "").strip()


def _profile_value(profile: dict[str, Any], group: str, key: str) -> str:
	values = profile.get(group)
	if not isinstance(values, dict):
		return ""
	return _text(values.get(key))


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
				material
				for material in entry.get("materials") or []
				if isinstance(material, dict)
				and (not selected_material_ids or _text(material.get("id")) in selected_material_ids)
			]
			if _text(entry.get("description")) or materials:
				entries.append({**entry, "materials": materials})
		if _text(section.get("summary")) or entries:
			result.append({**section, "entries": entries})
	return result


def _section_title(section: dict[str, Any]) -> str:
	return _text(section.get("title")) or {
		"education": "教育背景",
		"project": "项目经历",
		"work": "实习 / 工作经历",
		"academic": "学术成果",
		"campus": "校园与实践经历",
		"award": "荣誉奖项",
		"skill": "技能证书",
		"certificate": "技能证书",
		"self_evaluation": "综合评价",
	}.get(_text(section.get("section_type")), "自定义模块")


def _safe_html(value: Any) -> str:
	return html.escape(_text(value), quote=True)


class _RichHtmlSanitizer(HTMLParser):
	_ALLOWED_TAGS = {"b", "strong", "i", "em", "u", "a", "ol", "ul", "li", "div", "p", "br", "span", "img", "h2", "h3", "font"}
	_ALLOWED_STYLES = {"color", "font-size", "text-align"}

	def __init__(self) -> None:
		super().__init__(convert_charrefs=True)
		self.parts: list[str] = []

	def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
		tag = tag.lower()
		if tag not in self._ALLOWED_TAGS:
			return
		safe_attrs: list[str] = []
		for name, raw_value in attrs:
			name = name.lower()
			value = str(raw_value or "")
			if tag == "a" and name == "href" and re.match(r"^(https?:|mailto:|#)", value, flags=re.IGNORECASE):
				safe_attrs.append(f'href="{html.escape(value, quote=True)}"')
				safe_attrs.append('target="_blank"')
			elif tag == "img" and name == "src" and re.match(r"^(https?:|data:image/)", value, flags=re.IGNORECASE):
				safe_attrs.append(f'src="{html.escape(value, quote=True)}"')
			elif tag == "img" and name == "alt":
				safe_attrs.append(f'alt="{html.escape(value, quote=True)}"')
			elif tag == "font" and name in {"color", "size"} and re.match(r"^[#\w\s.-]{1,32}$", value):
				safe_attrs.append(f'{name}="{html.escape(value, quote=True)}"')
			elif name == "style":
				style = _safe_rich_style(value)
				if style:
					safe_attrs.append(f'style="{html.escape(style, quote=True)}"')
		attr_text = f" {' '.join(safe_attrs)}" if safe_attrs else ""
		self.parts.append(f"<{tag}{attr_text}>")

	def handle_endtag(self, tag: str) -> None:
		tag = tag.lower()
		if tag in self._ALLOWED_TAGS and tag not in {"br", "img"}:
			self.parts.append(f"</{tag}>")

	def handle_data(self, data: str) -> None:
		self.parts.append(html.escape(data, quote=False))


def _safe_rich_style(value: str) -> str:
	result: list[str] = []
	for part in str(value or "").split(";"):
		if ":" not in part:
			continue
		prop, raw = [item.strip().lower() for item in part.split(":", 1)]
		if prop not in _RichHtmlSanitizer._ALLOWED_STYLES or re.search(r"[<>()]", raw):
			continue
		if prop == "font-size" and not re.match(r"^\d{1,2}px$|^[1-7]$", raw):
			continue
		if prop == "text-align" and raw not in {"left", "center", "right", "justify"}:
			continue
		if prop == "color" and not re.match(r"^#[0-9a-f]{3,8}$|^[a-z]+$|^rgb(a)?\([\d\s,.%]+\)$", raw, flags=re.IGNORECASE):
			continue
		result.append(f"{prop}: {raw}")
	return "; ".join(result)


def _looks_like_html(value: str) -> bool:
	return bool(re.search(r"</?[a-z][^>]*>", str(value or ""), flags=re.IGNORECASE))


def _rich_html(value: Any) -> str:
	text = _text(value)
	if not text:
		return ""
	if not _looks_like_html(text):
		return _safe_html(text).replace("\n", "<br>")
	parser = _RichHtmlSanitizer()
	parser.feed(text)
	return "".join(parser.parts)


def _markdown_escape(value: Any) -> str:
	return _text(value).replace("\r\n", "\n").replace("\r", "\n")


def _filename_part(value: str) -> str:
	return "".join("_" if char in r'\/:*?"<>|' else char for char in value).strip(" ._") or "简历"


def _photo_uri(version: dict[str, Any], show_photo: bool) -> str:
	if not show_photo:
		return ""
	snapshot = version.get("profile_snapshot") if isinstance(version.get("profile_snapshot"), dict) else {}
	photo = snapshot.get("photo") if isinstance(snapshot.get("photo"), dict) else None
	if not photo:
		return ""
	path = Path(_text(photo.get("path")))
	if not path.is_file():
		return ""
	return path.resolve().as_uri()


def _entry_metadata_value(entry: dict[str, Any], key: str) -> str:
	metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
	return _text(metadata.get(key))


def _entry_meta_text(section: dict[str, Any], entry: dict[str, Any], *, include_date: bool = False) -> str:
	parts = [_text(entry.get("organization")), _text(entry.get("role"))]
	if _text(section.get("section_type")) == "academic":
		parts.append(_entry_metadata_value(entry, "indexing"))
	if include_date:
		date_text = " - ".join(part for part in [_text(entry.get("start_date")), _text(entry.get("end_date"))] if part)
		parts.append(date_text)
	return " · ".join(part for part in parts if part)


def _profile_custom_bits(profile: dict[str, Any]) -> list[str]:
	basics = profile.get("basics") if isinstance(profile.get("basics"), dict) else {}
	values = basics.get("custom_fields")
	if not isinstance(values, list):
		return []
	result: list[str] = []
	for item in values:
		if not isinstance(item, dict):
			continue
		label = _text(item.get("label"))
		value = _text(item.get("value"))
		if label and value:
			result.append(f"{label}：{value}")
		elif value:
			result.append(value)
	return result


_REACTIVE_TEMPLATE_SPECS: dict[str, dict[str, str]] = {
	"reactive-azurill": {"sidebar": "left", "sidebar_bg": "none", "header": "full", "feature": "timeline"},
	"reactive-bronzor": {"sidebar": "right", "sidebar_bg": "none", "header": "full", "feature": "rule"},
	"reactive-chikorita": {"sidebar": "right", "sidebar_bg": "solid", "header": "main", "feature": "solid"},
	"reactive-ditgar": {"sidebar": "left", "sidebar_bg": "tint", "header": "sidebar", "feature": "cards"},
	"reactive-ditto": {"sidebar": "left", "sidebar_bg": "none", "header": "full", "feature": "timeline"},
	"reactive-gengar": {"sidebar": "left", "sidebar_bg": "tint", "header": "sidebar", "feature": "boxed"},
	"reactive-glalie": {"sidebar": "left", "sidebar_bg": "tint", "header": "sidebar", "feature": "clean"},
	"reactive-kakuna": {"sidebar": "right", "sidebar_bg": "none", "header": "full", "feature": "rail"},
	"reactive-lapras": {"sidebar": "right", "sidebar_bg": "none", "header": "full", "feature": "classic"},
	"reactive-leafish": {"sidebar": "right", "sidebar_bg": "none", "header": "full", "feature": "soft"},
	"reactive-meowth": {"sidebar": "left", "sidebar_bg": "none", "header": "full", "feature": "compact"},
	"reactive-onyx": {"sidebar": "right", "sidebar_bg": "none", "header": "full", "feature": "grid"},
	"reactive-pikachu": {"sidebar": "left", "sidebar_bg": "none", "header": "main", "feature": "accent-block"},
	"reactive-rhyhorn": {"sidebar": "right", "sidebar_bg": "none", "header": "full", "feature": "quiet"},
	"reactive-scizor": {"sidebar": "left", "sidebar_bg": "none", "header": "full", "feature": "caps"},
}

_RENDERCV_TEMPLATE_SPECS: dict[str, dict[str, str]] = {
	"rendercv-classic": {"feature": "classic", "density": "standard"},
	"rendercv-ember": {"feature": "ember", "density": "standard"},
	"rendercv-engineeringclassic": {"feature": "engineering-classic", "density": "compact"},
	"rendercv-engineeringresumes": {"feature": "engineering-resumes", "density": "compact"},
	"rendercv-harvard": {"feature": "harvard", "density": "standard"},
	"rendercv-ink": {"feature": "ink", "density": "compact"},
	"rendercv-moderncv": {"feature": "moderncv", "density": "standard"},
	"rendercv-opal": {"feature": "opal", "density": "standard"},
	"rendercv-sb2nov": {"feature": "sb2nov", "density": "compact"},
}


def _template_snapshot(version: dict[str, Any]) -> dict[str, Any]:
	snapshot = version.get("profile_snapshot") if isinstance(version.get("profile_snapshot"), dict) else {}
	template = snapshot.get("template") if isinstance(snapshot.get("template"), dict) else {}
	return template


def _template_raw_id(version: dict[str, Any], template_id: str | None = None) -> str:
	template = _template_snapshot(version)
	return template_id or _text(version.get("template_id")) or _text(template.get("id")) or "classic-single"


def _template_style(version: dict[str, Any], template_id: str | None = None) -> dict[str, Any]:
	template = _template_snapshot(version)
	style = template.get("style") if isinstance(template.get("style"), dict) else {}
	if style:
		return style
	if template_id:
		return {}
	return {}


def _template_layout(version: dict[str, Any]) -> dict[str, Any]:
	template = _template_snapshot(version)
	layout = template.get("layout") if isinstance(template.get("layout"), dict) else {}
	return layout


def _hex_color(value: Any, fallback: str = "#FF5A1F") -> str:
	text = _text(value)
	return text if re.match(r"^#[0-9a-f]{6}$", text, flags=re.IGNORECASE) else fallback


def _blend_with_white(hex_color: str, opacity: float) -> str:
	color = _hex_color(hex_color, "#2563EB").lstrip("#")
	channels = [int(color[index:index + 2], 16) for index in (0, 2, 4)]
	blended = [round(channel * opacity + 255 * (1 - opacity)) for channel in channels]
	return "#" + "".join(f"{channel:02X}" for channel in blended)


def _template_accent(version: dict[str, Any], template_id: str | None = None) -> str:
	raw_id = _template_raw_id(version, template_id)
	style = _template_style(version, template_id)
	defaults = {
		"classic-single": "#FF5A1F",
		"compact-two-column": "#2563EB",
		"rendercv-ink": "#000000",
		"rendercv-harvard": "#7F1D1D",
		"rendercv-opal": "#0F766E",
		"rendercv-ember": "#B45309",
	}
	return _hex_color(style.get("accent"), defaults.get(raw_id, "#2563EB"))


def _template_base(version: dict[str, Any], template_id: str | None) -> str:
	raw_template = _template_raw_id(version, template_id)
	if raw_template in {"classic-single", "compact-two-column"}:
		return raw_template
	if raw_template in _REACTIVE_TEMPLATE_SPECS:
		return "compact-two-column"
	if raw_template in _RENDERCV_TEMPLATE_SPECS:
		return "classic-single"
	layout = _template_layout(version)
	base = _text(layout.get("base_template"))
	return base if base in {"classic-single", "compact-two-column"} else "classic-single"


def _render_section(section: dict[str, Any]) -> str:
	entries_html: list[str] = []
	for entry in section.get("entries") or []:
		materials = entry.get("materials") or []
		materials_html = "".join(f"<li>{_rich_html(material.get('content'))}</li>" for material in materials)
		date_text = " - ".join(part for part in [_text(entry.get("start_date")), _text(entry.get("end_date"))] if part)
		meta_text = _entry_meta_text(section, entry)
		entries_html.append(
			f"""
			<div class="entry">
				<div class="entry-head">
					<strong>{_safe_html(entry.get("title"))}</strong>
					<span>{_safe_html(date_text)}</span>
				</div>
				{f'<div class="entry-meta">{_safe_html(meta_text)}</div>' if meta_text else ''}
				{f'<div class="rich-text">{_rich_html(entry.get("description"))}</div>' if _text(entry.get("description")) else ''}
				{f'<ul>{materials_html}</ul>' if materials_html else ''}
			</div>
			"""
		)
	return f"""
	<section class="section section-{_safe_html(_text(section.get("section_type")) or "custom")}">
		<h2>{_safe_html(_section_title(section))}</h2>
		{f'<div class="section-summary rich-text">{_rich_html(section.get("summary"))}</div>' if _text(section.get("summary")) else ''}
		{''.join(entries_html)}
	</section>
	"""


def _render_education_block(education: list[Any]) -> str:
	education_html = "".join(
		f"""
		<div class="side-item">
			<strong>{_safe_html(_text(item.get('school')))}</strong>
			<p>{_safe_html(' · '.join(part for part in [_text(item.get('major')), _text(item.get('degree'))] if part))}</p>
			<p>{_safe_html(' - '.join(part for part in [_text(item.get('start_date')), _text(item.get('end_date'))] if part))}</p>
			{f'<div class="rich-text">{_rich_html(item.get("detail"))}</div>' if _text(item.get("detail")) else ''}
		</div>
		"""
		for item in education if isinstance(item, dict)
	)
	return f'<section class="side-section"><h3>教育背景</h3>{education_html}</section>' if education_html else ""


def _render_skills_block(skills: list[Any]) -> str:
	skills_html = "".join(f"<span>{_safe_html(skill)}</span>" for skill in skills if isinstance(skill, str) and skill.strip())
	return f'<section class="side-section"><h3>技能证书</h3><div class="skills">{skills_html}</div></section>' if skills_html else ""


def _profile_education_section(education: list[Any]) -> dict[str, Any]:
	entries: list[dict[str, Any]] = []
	for item in education:
		if not isinstance(item, dict):
			continue
		entries.append(
			{
				"title": _text(item.get("school")) or "教育经历",
				"organization": _text(item.get("major")),
				"role": _text(item.get("degree")),
				"start_date": _text(item.get("start_date")),
				"end_date": _text(item.get("end_date")),
				"description": _text(item.get("detail")),
				"materials": [],
			}
		)
	return {"section_type": "education-profile", "title": "教育背景", "summary": "", "entries": entries}


def _profile_skill_section(skills: list[Any]) -> dict[str, Any]:
	materials = [{"content": skill} for skill in skills if isinstance(skill, str) and skill.strip()]
	return {
		"section_type": "skill-profile",
		"title": "技能证书",
		"summary": "",
		"entries": [
			{
				"title": "技能证书",
				"organization": "",
				"role": "",
				"start_date": "",
				"end_date": "",
				"description": "",
				"materials": materials,
			}
		] if materials else [],
	}


def _contact_item(label: str, value: str) -> str:
	value = _text(value)
	if not value:
		return ""
	return f'<span class="contact-item"><span class="contact-icon">{_safe_html(label)}</span><span>{_safe_html(value)}</span></span>'


def _render_source_header(
	name: str,
	headline: str,
	header_bits: list[str],
	contact_bits: list[str],
	photo_html: str,
	*,
	class_name: str,
) -> str:
	email = contact_bits[1] if len(contact_bits) > 1 else ""
	phone = contact_bits[0] if contact_bits else ""
	info = " · ".join(part for part in header_bits if part)
	contacts = "".join(
		[
			_contact_item("@", email),
			_contact_item("T", phone),
			_contact_item("I", info),
		]
	)
	return f"""
	<header class="{class_name}">
		{photo_html}
		<div class="source-header-title">
			<div class="source-header-identity">
				<h1>{_safe_html(name)}</h1>
				{f'<p class="headline">{_safe_html(headline)}</p>' if headline else ''}
			</div>
		</div>
		{f'<div class="source-contact-row">{contacts}</div>' if contacts else ''}
	</header>
	"""


def _render_contact_block(header_bits: list[str], contact_bits: list[str]) -> str:
	lines = [
		_safe_html(" · ".join(part for part in header_bits if part)),
		_safe_html(" · ".join(part for part in contact_bits if part)),
	]
	content = "".join(f"<p>{line}</p>" for line in lines if line)
	return f'<section class="side-section"><h3>联系方式</h3>{content}</section>' if content else ""


def _render_resume_header(name: str, header_bits: list[str], contact_bits: list[str], target_text: str, photo_html: str, *, class_name: str = "") -> str:
	return f"""
	<header class="resume-header {class_name}">
		<div>
			<h1>{_safe_html(name)}</h1>
			<p>{_safe_html(' · '.join(part for part in header_bits if part))}</p>
			<p>{_safe_html(' · '.join(part for part in contact_bits if part))}</p>
			{f'<p class="target">目标：{_safe_html(target_text)}</p>' if target_text else ''}
		</div>
		{photo_html}
	</header>
	"""


def _split_sidebar_sections(sections: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
	sidebar_types = {"skill", "certificate", "award", "self_evaluation"}
	sidebar_sections = [section for section in sections if _text(section.get("section_type")) in sidebar_types]
	main_sections = [section for section in sections if _text(section.get("section_type")) not in sidebar_types]
	return main_sections, sidebar_sections


def _render_azurill_template(
	version: dict[str, Any],
	*,
	template_id: str | None,
	name: str,
	header_bits: list[str],
	contact_bits: list[str],
	target_text: str,
	photo_html: str,
	education: list[Any],
	skills: list[Any],
	sections: list[dict[str, Any]],
) -> str:
	education_section = _profile_education_section(education)
	skill_section = _profile_skill_section(skills)
	main_sections, sidebar_sections = _split_sidebar_sections(sections)
	if education_section["entries"]:
		main_sections = [education_section, *main_sections]
	if skill_section["entries"]:
		sidebar_sections = [skill_section, *sidebar_sections]
	return f"""
	<div class="sheet source-template azurill-source" style="--accent: {_template_accent(version, template_id)};">
		{_render_source_header(name, target_text, header_bits, contact_bits, photo_html, class_name="source-header azurill-header")}
		<div class="azurill-content-row">
			<aside class="azurill-sidebar">
				{''.join(_render_section(section) for section in sidebar_sections)}
			</aside>
			<main class="azurill-main">
				{''.join(_render_azurill_main_section(section) for section in main_sections)}
			</main>
		</div>
	</div>
	"""


def _render_entry_content(section: dict[str, Any], entry: dict[str, Any]) -> str:
	materials = entry.get("materials") or []
	materials_html = "".join(f"<li>{_rich_html(material.get('content'))}</li>" for material in materials)
	date_text = " - ".join(part for part in [_text(entry.get("start_date")), _text(entry.get("end_date"))] if part)
	meta_text = _entry_meta_text(section, entry)
	return f"""
	<div class="entry-head">
		<strong>{_safe_html(entry.get("title"))}</strong>
		<span>{_safe_html(date_text)}</span>
	</div>
	{f'<div class="entry-meta">{_safe_html(meta_text)}</div>' if meta_text else ''}
	{f'<div class="rich-text">{_rich_html(entry.get("description"))}</div>' if _text(entry.get("description")) else ''}
	{f'<ul>{materials_html}</ul>' if materials_html else ''}
	"""


def _render_azurill_main_section(section: dict[str, Any]) -> str:
	entries = [entry for entry in section.get("entries") or [] if isinstance(entry, dict)]
	items = "".join(
		f"""
		<div class="azurill-timeline-item entry">
			<div class="azurill-timeline-marker"><span class="azurill-timeline-dot"></span></div>
			<div class="azurill-timeline-content">
				{_render_entry_content(section, entry)}
			</div>
		</div>
		"""
		for entry in entries
	)
	if not items and _text(section.get("summary")):
		items = f"""
		<div class="azurill-timeline-item entry">
			<div class="azurill-timeline-marker"><span class="azurill-timeline-dot"></span></div>
			<div class="azurill-timeline-content">
				<div class="section-summary rich-text">{_rich_html(section.get("summary"))}</div>
			</div>
		</div>
		"""
	return f"""
	<section class="section section-{_safe_html(_text(section.get("section_type")) or "custom")} azurill-section">
		<h2>{_safe_html(_section_title(section))}</h2>
		<div class="azurill-timeline-items">
			<div class="azurill-timeline-line"></div>
			{items}
		</div>
	</section>
	"""


def _render_bronzor_section(section: dict[str, Any]) -> str:
	return f"""
	<section class="bronzor-section section-{_safe_html(_text(section.get("section_type")) or "custom")}">
		<h2>{_safe_html(_section_title(section))}</h2>
		<div class="bronzor-section-items">
			{f'<div class="section-summary rich-text">{_rich_html(section.get("summary"))}</div>' if _text(section.get("summary")) else ''}
			{''.join(_render_section_entries(section))}
		</div>
	</section>
	"""


def _render_section_entries(section: dict[str, Any]) -> list[str]:
	entries_html: list[str] = []
	for entry in section.get("entries") or []:
		materials = entry.get("materials") or []
		materials_html = "".join(f"<li>{_rich_html(material.get('content'))}</li>" for material in materials)
		date_text = " - ".join(part for part in [_text(entry.get("start_date")), _text(entry.get("end_date"))] if part)
		meta_text = _entry_meta_text(section, entry)
		entries_html.append(
			f"""
			<div class="entry">
				<div class="entry-head">
					<strong>{_safe_html(entry.get("title"))}</strong>
					<span>{_safe_html(date_text)}</span>
				</div>
				{f'<div class="entry-meta">{_safe_html(meta_text)}</div>' if meta_text else ''}
				{f'<div class="rich-text">{_rich_html(entry.get("description"))}</div>' if _text(entry.get("description")) else ''}
				{f'<ul>{materials_html}</ul>' if materials_html else ''}
			</div>
			"""
		)
	return entries_html


def _render_bronzor_template(
	version: dict[str, Any],
	*,
	template_id: str | None,
	name: str,
	header_bits: list[str],
	contact_bits: list[str],
	target_text: str,
	photo_html: str,
	education: list[Any],
	skills: list[Any],
	sections: list[dict[str, Any]],
) -> str:
	education_section = _profile_education_section(education)
	skill_section = _profile_skill_section(skills)
	all_sections = [
		*(section for section in [education_section] if section["entries"]),
		*sections,
		*(section for section in [skill_section] if section["entries"]),
	]
	return f"""
	<div class="sheet source-template bronzor-source" style="--accent: {_template_accent(version, template_id)};">
		{_render_source_header(name, target_text, header_bits, contact_bits, photo_html, class_name="source-header bronzor-header")}
		<main class="bronzor-sections">
			{''.join(_render_bronzor_section(section) for section in all_sections)}
		</main>
	</div>
	"""


def _render_reactive_template(
	version: dict[str, Any],
	*,
	template_id: str | None,
	name: str,
	header_bits: list[str],
	contact_bits: list[str],
	target_text: str,
	photo_html: str,
	education: list[Any],
	skills: list[Any],
	sections: list[dict[str, Any]],
) -> str:
	raw_id = _template_raw_id(version, template_id)
	if raw_id == "reactive-azurill":
		return _render_azurill_template(
			version,
			template_id=template_id,
			name=name,
			header_bits=header_bits,
			contact_bits=contact_bits,
			target_text=target_text,
			photo_html=photo_html,
			education=education,
			skills=skills,
			sections=sections,
		)
	if raw_id == "reactive-bronzor":
		return _render_bronzor_template(
			version,
			template_id=template_id,
			name=name,
			header_bits=header_bits,
			contact_bits=contact_bits,
			target_text=target_text,
			photo_html=photo_html,
			education=education,
			skills=skills,
			sections=sections,
		)
	spec = _REACTIVE_TEMPLATE_SPECS.get(raw_id, _REACTIVE_TEMPLATE_SPECS["reactive-azurill"])
	main_sections, sidebar_sections = _split_sidebar_sections(sections)
	header_mode = spec["header"]
	sidebar_side = spec["sidebar"]
	sidebar_bg = spec["sidebar_bg"]
	feature = spec["feature"]
	full_header = _render_resume_header(name, header_bits, contact_bits, target_text, photo_html, class_name="header-full") if header_mode == "full" else ""
	main_header = _render_resume_header(name, header_bits, contact_bits, target_text, "", class_name="header-main-only") if header_mode == "main" else ""
	sidebar_header = _render_resume_header(name, header_bits, [], "", photo_html, class_name="header-sidebar-only") if header_mode == "sidebar" else ""
	sidebar_html = "".join(
		[
			sidebar_header,
			_render_contact_block(header_bits if header_mode == "sidebar" else [], contact_bits),
			_render_education_block(education),
			_render_skills_block(skills),
			"".join(_render_section(section) for section in sidebar_sections),
		]
	)
	main_html = "".join(_render_section(section) for section in main_sections)
	return f"""
	<div class="sheet two-column external-template reactive-template {raw_id} sidebar-{sidebar_side} sidebar-{sidebar_bg} header-{header_mode} feature-{feature}">
		{full_header}
		<div class="template-grid">
			<aside>{sidebar_html}</aside>
			<main>
				{main_header}
				{f'<p class="target target-inline">目标：{_safe_html(target_text)}</p>' if target_text and header_mode == "sidebar" else ''}
				{main_html}
			</main>
		</div>
	</div>
	"""


def _render_rendercv_template(
	version: dict[str, Any],
	*,
	template_id: str | None,
	name: str,
	header_bits: list[str],
	contact_bits: list[str],
	target_text: str,
	photo_html: str,
	education: list[Any],
	skills: list[Any],
	sections: list[dict[str, Any]],
) -> str:
	raw_id = _template_raw_id(version, template_id)
	spec = _RENDERCV_TEMPLATE_SPECS.get(raw_id, _RENDERCV_TEMPLATE_SPECS["rendercv-classic"])
	education_section = {"section_type": "education-profile", "title": "教育背景", "summary": "", "entries": []}
	for item in education:
		if not isinstance(item, dict):
			continue
		education_section["entries"].append(
			{
				"title": _text(item.get("school")),
				"organization": _text(item.get("major")),
				"role": _text(item.get("degree")),
				"start_date": _text(item.get("start_date")),
				"end_date": _text(item.get("end_date")),
				"description": _text(item.get("detail")),
				"materials": [],
			}
		)
	skill_section = {
		"section_type": "skill-profile",
		"title": "技能证书",
		"summary": "",
		"entries": [
			{
				"title": "技能证书",
				"organization": "",
				"role": "",
				"start_date": "",
				"end_date": "",
				"description": "",
				"materials": [{"content": skill} for skill in skills if isinstance(skill, str) and skill.strip()],
			}
		],
	}
	profile_sections = []
	if education_section["entries"]:
		profile_sections.append(education_section)
	if skill_section["entries"][0]["materials"]:
		profile_sections.append(skill_section)
	all_sections = [*profile_sections, *sections]
	return f"""
	<div class="sheet classic external-template rendercv-template {raw_id} rendercv-{spec["feature"]} density-{spec["density"]}">
		{_render_resume_header(name, header_bits, contact_bits, target_text, photo_html, class_name="rendercv-header")}
		{''.join(_render_section(section) for section in all_sections)}
	</div>
	"""


def resume_version_html(version: dict[str, Any], *, template_id: str | None = None, show_photo: bool = True) -> str:
	snapshot = version.get("profile_snapshot") if isinstance(version.get("profile_snapshot"), dict) else {}
	profile = snapshot.get("profile") if isinstance(snapshot.get("profile"), dict) else {}
	raw_template = _template_raw_id(version, template_id)
	template = _template_base(version, template_id)
	accent = _template_accent(version, template_id)
	accent_soft = _blend_with_white(accent, 0.13)
	sections = _selected_sections(version)
	photo_uri = _photo_uri(version, show_photo)
	name = _profile_value(profile, "basics", "name") or "未填写姓名"
	header_bits = [
		_profile_value(profile, "basics", "gender"),
		_profile_value(profile, "basics", "birth_date"),
		_profile_value(profile, "basics", "native_place"),
		_profile_value(profile, "basics", "political_status"),
		*_profile_custom_bits(profile),
	]
	contact_bits = [
		_profile_value(profile, "contacts", "phone"),
		_profile_value(profile, "contacts", "email"),
	]
	education = profile.get("education") if isinstance(profile.get("education"), list) else []
	skills = profile.get("skills") if isinstance(profile.get("skills"), list) else []
	target_text = " · ".join(part for part in [_text(version.get("target_company")), _text(version.get("target_title"))] if part)
	photo_html = f'<img class="photo" src="{photo_uri}" alt="简历照片">' if photo_uri else ""

	if raw_template in _REACTIVE_TEMPLATE_SPECS:
		body = _render_reactive_template(
			version,
			template_id=template_id,
			name=name,
			header_bits=header_bits,
			contact_bits=contact_bits,
			target_text=target_text,
			photo_html=photo_html,
			education=education,
			skills=skills,
			sections=sections,
		)
	elif raw_template in _RENDERCV_TEMPLATE_SPECS:
		body = _render_rendercv_template(
			version,
			template_id=template_id,
			name=name,
			header_bits=header_bits,
			contact_bits=contact_bits,
			target_text=target_text,
			photo_html=photo_html,
			education=education,
			skills=skills,
			sections=sections,
		)
	else:
		section_html = "".join(_render_section(section) for section in sections)
		two_column_sidebar = ""
		if template == "compact-two-column":
			education_html = "".join(
				f"<p>{_safe_html(' · '.join(part for part in [_text(item.get('school')), _text(item.get('major')), _text(item.get('degree'))] if part))}</p>"
				for item in education if isinstance(item, dict)
			)
			skills_html = "".join(f"<span>{_safe_html(skill)}</span>" for skill in skills if isinstance(skill, str))
			two_column_sidebar = f"""
			<aside>
				{photo_html}
				<h1>{_safe_html(name)}</h1>
				<p>{_safe_html(' · '.join(part for part in header_bits if part))}</p>
				<h3>联系方式</h3>
				<p>{_safe_html(' · '.join(part for part in contact_bits if part))}</p>
				{f'<h3>教育背景</h3>{education_html}' if education_html else ''}
				{f'<h3>技能证书</h3><div class="skills">{skills_html}</div>' if skills_html else ''}
			</aside>
			"""

		body = (
			f"""
			<div class="sheet two-column builtin-template" style="--accent: {accent};">
				{two_column_sidebar}
				<main>
					{f'<p class="target">目标：{_safe_html(target_text)}</p>' if target_text else ''}
					{section_html}
				</main>
			</div>
			"""
			if template == "compact-two-column"
			else f"""
			<div class="sheet classic builtin-template" style="--accent: {accent};">
				{_render_resume_header(name, header_bits, contact_bits, target_text, photo_html)}
				{section_html}
			</div>
			"""
		)
	return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
@page {{ size: A4; margin: 0; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: #fff; color: #1f1f1f; font-family: "Noto Sans CJK SC", "PingFang SC", "Microsoft YaHei", sans-serif; font-size: 10.6pt; line-height: 1.45; }}
.sheet {{ width: 210mm; min-height: 297mm; padding: 12mm 14mm; background: #fff; --accent: {accent}; --accent-soft: {accent_soft}; }}
.resume-header {{ display: flex; justify-content: space-between; gap: 10mm; border-bottom: .5pt solid #d8d8d8; padding-bottom: 6mm; margin-bottom: 5mm; }}
h1 {{ font-size: 24pt; line-height: 1.05; margin: 0 0 2mm; color: #111; }}
h2 {{ font-size: 12.2pt; margin: 5mm 0 2mm; padding-bottom: 1mm; border-bottom: .5pt solid #d8d8d8; color: #1f1f1f; }}
h3 {{ font-size: 10.5pt; margin: 4mm 0 1.5mm; padding-bottom: .7mm; border-bottom: .5pt solid #d8d8d8; }}
p {{ margin: 0 0 1.4mm; }}
ul {{ margin: 1mm 0 2mm; padding-left: 5mm; }}
li {{ margin-bottom: .8mm; }}
.rich-text div, .rich-text p {{ margin: 0 0 1mm; }}
.rich-text h2 {{ font-size: 10.8pt; margin: 1mm 0; padding: 0; border: 0; }}
.rich-text h3 {{ font-size: 10.2pt; margin: 1mm 0; padding: 0; border: 0; }}
.rich-text ul, .rich-text ol {{ margin: 1mm 0 1.5mm; padding-left: 5mm; }}
.rich-text img {{ max-width: 100%; max-height: 32mm; object-fit: contain; }}
font[size="2"] {{ font-size: 9pt; }}
font[size="3"] {{ font-size: 10.6pt; }}
font[size="4"] {{ font-size: 11.5pt; }}
font[size="5"] {{ font-size: 12.5pt; }}
font[size="6"] {{ font-size: 14pt; }}
.photo {{ width: 26mm; height: 32mm; object-fit: cover; }}
.section, .entry, li {{ break-inside: avoid; }}
.entry {{ margin-bottom: 3mm; }}
.entry-head {{ display: flex; justify-content: space-between; gap: 6mm; }}
.entry-head span, .entry-meta, .target {{ color: #555; font-size: 9.2pt; }}
.section-summary {{ color: #3f3f3f; }}
.two-column {{ display: grid; grid-template-columns: 48mm 1fr; gap: 8mm; }}
.builtin-template.two-column aside {{ border-right: .5pt solid #d8d8d8; padding-right: 6mm; }}
.two-column aside p {{ color: #555; font-size: 9pt; }}
.two-column .skills {{ display: flex; flex-wrap: wrap; gap: 1.5mm; }}
.two-column .skills span {{ border: .5pt solid #d8d8d8; padding: .7mm 1.4mm; font-size: 8.5pt; }}
.external-template {{ padding: 0; overflow: hidden; }}
.external-template .resume-header {{ border-bottom-color: var(--accent); }}
.external-template .template-grid {{ min-height: 297mm; display: grid; gap: 0; }}
.reactive-template {{ display: block; }}
.reactive-template .template-grid {{ grid-template-columns: 54mm 1fr; }}
.reactive-template.sidebar-right .template-grid {{ grid-template-columns: 1fr 54mm; }}
.reactive-template.sidebar-right aside {{ order: 2; border-left: .8pt solid #d9dde4; border-right: 0; }}
.reactive-template aside {{ padding: 11mm 7mm; border-right: .8pt solid #d9dde4; }}
.reactive-template main {{ padding: 11mm 13mm; }}
.reactive-template .header-full {{ margin: 0; padding: 10mm 13mm 7mm; border-bottom: 2pt solid var(--accent); }}
.reactive-template .header-main-only {{ margin-bottom: 6mm; border-bottom: 0; }}
.reactive-template .header-sidebar-only {{ display: block; border: 0; padding: 0 0 4mm; margin: 0; }}
.reactive-template .header-sidebar-only h1 {{ color: var(--accent); font-size: 20pt; }}
.reactive-template.sidebar-solid aside {{ background: var(--accent); color: #fff; border: 0; }}
.reactive-template.sidebar-solid aside h1,
.reactive-template.sidebar-solid aside h2,
.reactive-template.sidebar-solid aside h3,
.reactive-template.sidebar-solid aside p,
.reactive-template.sidebar-solid aside .entry-meta,
.reactive-template.sidebar-solid aside .entry-head span {{ color: #fff; }}
.reactive-template.sidebar-solid aside .skills span {{ border-color: rgba(255,255,255,.55); }}
.reactive-template.sidebar-tint aside {{ background: var(--accent-soft); }}
.reactive-template aside h3,
.reactive-template aside h2 {{ color: var(--accent); border-bottom: .8pt solid currentColor; font-size: 10pt; }}
.reactive-template aside .section {{ margin-bottom: 4mm; }}
.reactive-template aside .entry {{ margin-bottom: 2.4mm; }}
.reactive-template aside .entry-head {{ display: block; }}
.reactive-template aside .entry-head strong {{ display: block; }}
.reactive-template main h2 {{ color: var(--accent); border-bottom: 1.1pt solid var(--accent); letter-spacing: 0; }}
.reactive-template.feature-timeline main .section {{ border-left: 1pt solid var(--accent); padding-left: 4mm; }}
.reactive-template.feature-timeline main .entry {{ position: relative; }}
.reactive-template.feature-timeline main .entry::before {{ content: ""; position: absolute; left: -5.2mm; top: 1.8mm; width: 2.2mm; height: 2.2mm; border-radius: 50%; background: var(--accent); }}
.reactive-template.feature-rail main h2,
.reactive-template.feature-accent-block main h2 {{ border: 0; padding: 1.2mm 2mm; background: var(--accent); color: #fff; }}
.reactive-template.feature-cards main .entry,
.reactive-template.feature-boxed main .entry {{ border: .6pt solid #d8dce2; padding: 2.6mm; }}
.reactive-template.feature-grid main .section {{ display: grid; grid-template-columns: 30mm 1fr; gap: 3mm; }}
.reactive-template.feature-grid main h2 {{ grid-column: 1; border: 0; }}
.reactive-template.feature-grid main .entry,
.reactive-template.feature-grid main .section-summary {{ grid-column: 2; }}
.reactive-template.feature-caps main h2 {{ text-transform: uppercase; letter-spacing: .04em; color: #111; border-top: 1.2pt solid #111; border-bottom: 0; padding-top: 1.8mm; }}
.reactive-template.feature-soft main h2 {{ border: 0; color: #fff; background: var(--accent); display: inline-block; padding: 1mm 3mm; border-radius: 999px; }}
.reactive-template.feature-compact {{ font-size: 9.8pt; line-height: 1.36; }}
.rendercv-template {{ padding: 13mm 16mm; }}
.rendercv-template .resume-header {{ justify-content: center; text-align: center; border-bottom: .7pt solid #111; padding-bottom: 4mm; }}
.rendercv-template .resume-header .photo {{ display: none; }}
.rendercv-template h1 {{ font-size: 22pt; }}
.rendercv-template h2 {{ color: #111; border-bottom: .7pt solid #111; margin-top: 4mm; }}
.rendercv-template .entry-head strong {{ font-size: 10.8pt; }}
.rendercv-template.density-compact {{ font-size: 9.7pt; line-height: 1.32; }}
.rendercv-template.density-compact h1 {{ font-size: 20pt; }}
.rendercv-template.density-compact h2 {{ font-size: 11pt; margin-top: 3.5mm; }}
.rendercv-harvard {{ font-family: "Times New Roman", "Noto Serif CJK SC", serif; }}
.rendercv-harvard .resume-header {{ border-bottom: 1pt solid #111; }}
.rendercv-ember {{ border-top: 5mm solid var(--accent); }}
.rendercv-ember h2 {{ color: var(--accent); border-bottom-color: var(--accent); }}
.rendercv-engineering-classic,
.rendercv-engineering-resumes,
.rendercv-sb2nov {{ font-family: Arial, "Noto Sans CJK SC", sans-serif; }}
.rendercv-engineering-resumes h2,
.rendercv-sb2nov h2,
.rendercv-ink h2 {{ text-transform: uppercase; font-size: 10.5pt; }}
.rendercv-ink {{ --accent: #000000; }}
.rendercv-moderncv {{ border-left: 7mm solid var(--accent); padding-left: 12mm; }}
.rendercv-moderncv .resume-header {{ text-align: left; justify-content: space-between; border-bottom: 0; }}
.rendercv-moderncv h2 {{ color: var(--accent); border-bottom-color: var(--accent); }}
.rendercv-opal h2 {{ border: 0; color: var(--accent); padding-left: 2mm; border-left: 3mm solid var(--accent); }}
.rendercv-classic .resume-header p,
.rendercv-harvard .resume-header p,
.rendercv-ink .resume-header p,
.rendercv-sb2nov .resume-header p {{ margin-left: auto; margin-right: auto; }}
.source-template {{ display: block; padding: 16mm; }}
.source-header {{ display: flex; flex-direction: column; align-items: center; gap: 2.4mm; text-align: center; margin-bottom: 16mm; }}
.source-header .photo {{ width: 28mm; height: 28mm; border-radius: 999px; object-fit: cover; }}
.source-header h1 {{ font-size: 26pt; line-height: 1.05; margin: 0; }}
.source-header .headline {{ margin: 0; color: #4b5563; }}
.source-header-title,
.source-header-identity {{ display: flex; flex-direction: column; align-items: center; gap: 1.5mm; }}
.source-contact-row {{ display: flex; flex-wrap: wrap; justify-content: center; gap: 1.4mm 5mm; color: #333; font-size: 9.2pt; }}
.contact-item {{ display: inline-flex; align-items: center; gap: 1.2mm; }}
.contact-icon {{ display: inline-flex; align-items: center; justify-content: center; width: 3.6mm; height: 3.6mm; border: .7pt solid var(--accent); border-radius: 999px; color: var(--accent); font-size: 6.5pt; font-weight: 700; line-height: 1; }}
.azurill-source {{ padding: 16mm; }}
.azurill-header {{ margin-bottom: 16mm; }}
.azurill-content-row {{ display: grid; grid-template-columns: 30% 1fr; column-gap: 16mm; }}
.azurill-sidebar {{ display: flex; flex-direction: column; gap: 8mm; }}
.azurill-main {{ display: flex; flex-direction: column; gap: 8mm; }}
.azurill-source h2,
.azurill-source h3 {{ color: var(--accent); border-bottom: 0; padding: 0; margin: 0 0 2mm; }}
.azurill-source .section {{ margin: 0; }}
.azurill-source .section + .section {{ margin-top: 0; }}
.azurill-source .azurill-main .section {{ break-inside: avoid; }}
.azurill-timeline-items {{ position: relative; display: flex; flex-direction: column; gap: 3.2mm; }}
.azurill-timeline-line {{ position: absolute; top: 0; bottom: 0; left: 2mm; width: .35mm; background: var(--accent); }}
.azurill-timeline-item {{ display: grid; grid-template-columns: 4.4mm 1fr; column-gap: 3.2mm; position: relative; margin: 0; }}
.azurill-timeline-marker {{ display: flex; justify-content: center; align-items: flex-start; padding-top: 2.2mm; z-index: 1; }}
.azurill-timeline-dot {{ width: 2.8mm; height: 2.8mm; border-radius: 999px; border: .45mm solid var(--accent); background: #fff; display: block; }}
.azurill-timeline-content {{ min-width: 0; }}
.azurill-source .azurill-main .entry-head {{ align-items: baseline; }}
.azurill-source .azurill-sidebar .entry-head {{ display: block; }}
.azurill-source .azurill-sidebar .entry-head span {{ display: block; margin-top: .8mm; }}
.azurill-source .skills {{ display: flex; flex-direction: column; gap: 1.2mm; }}
.azurill-source .skills span {{ border: 0; border-left: 1.6mm solid var(--accent); padding: .6mm 0 .6mm 2mm; font-size: 9pt; }}
.bronzor-source {{ padding: 16mm; }}
.bronzor-header {{ margin-bottom: 16mm; }}
.bronzor-source .source-contact-row {{ column-gap: 7mm; }}
.bronzor-sections {{ display: flex; flex-direction: column; gap: 8mm; }}
.bronzor-section {{ display: grid; grid-template-columns: 30% 1fr; column-gap: 16mm; border-top: 1pt solid var(--accent); padding-top: 4mm; break-inside: avoid; }}
.bronzor-section h2 {{ width: auto; margin: 0; padding: 0; border: 0; color: var(--accent); font-size: 9.6pt; font-weight: 500; text-align: left; }}
.bronzor-section-items {{ min-width: 0; }}
.bronzor-section .entry {{ margin-bottom: 3.2mm; }}
.bronzor-section .entry:last-child {{ margin-bottom: 0; }}
.bronzor-section .entry-head {{ align-items: baseline; }}
.bronzor-section .entry-head strong {{ font-weight: 500; }}
</style>
</head>
<body><div style="--accent: {accent};">{body}</div></body>
</html>"""


def resume_version_filename(version: dict[str, Any], date: datetime | None = None) -> str:
	snapshot = version.get("profile_snapshot") if isinstance(version.get("profile_snapshot"), dict) else {}
	profile = snapshot.get("profile") if isinstance(snapshot.get("profile"), dict) else {}
	name = _filename_part(_profile_value(profile, "basics", "name") or "未填写姓名")
	version_name = _filename_part(_text(version.get("name")) or "简历版本")
	day = (date or datetime.now()).strftime("%Y%m%d")
	return safe_resume_filename(f"{name}_{version_name}_{day}.pdf")


def resume_version_markdown_filename(version: dict[str, Any]) -> str:
	snapshot = version.get("profile_snapshot") if isinstance(version.get("profile_snapshot"), dict) else {}
	profile = snapshot.get("profile") if isinstance(snapshot.get("profile"), dict) else {}
	name = _filename_part(_profile_value(profile, "basics", "name") or "未填写姓名")
	version_name = _filename_part(_text(version.get("name")) or "简历版本")
	version_id = _filename_part(_text(version.get("id"))[-8:] or "current")
	return safe_resume_filename(f"{name}_{version_name}_{version_id}_current.md")


def _append_list_block(lines: list[str], title: str, values: list[str]) -> None:
	values = [value for value in values if value]
	if not values:
		return
	lines.extend(["", f"## {title}"])
	lines.extend(f"- {value}" for value in values)


def resume_version_markdown(version: dict[str, Any]) -> str:
	rendered = _text(version.get("rendered_markdown"))
	if rendered:
		return sanitize_resume_text(rendered).rstrip() + "\n"

	snapshot = version.get("profile_snapshot") if isinstance(version.get("profile_snapshot"), dict) else {}
	profile = snapshot.get("profile") if isinstance(snapshot.get("profile"), dict) else {}
	sections = _selected_sections(version)
	name = _profile_value(profile, "basics", "name") or "未填写姓名"
	header_bits = [
		_profile_value(profile, "basics", "gender"),
		_profile_value(profile, "basics", "birth_date"),
		_profile_value(profile, "basics", "native_place"),
		_profile_value(profile, "basics", "political_status"),
		*_profile_custom_bits(profile),
	]
	contact_bits = [
		_profile_value(profile, "contacts", "phone"),
		_profile_value(profile, "contacts", "email"),
	]
	target_bits = [_text(version.get("target_company")), _text(version.get("target_title"))]
	lines = [f"# {name}"]
	if any(header_bits):
		lines.append(" · ".join(part for part in header_bits if part))
	if any(contact_bits):
		lines.append(" · ".join(part for part in contact_bits if part))
	if any(target_bits):
		lines.append(f"目标：{' · '.join(part for part in target_bits if part)}")

	education = profile.get("education") if isinstance(profile.get("education"), list) else []
	education_lines: list[str] = []
	for item in education:
		if not isinstance(item, dict):
			continue
		main = " · ".join(
			part for part in [
				_text(item.get("school")),
				_text(item.get("major")),
				_text(item.get("degree")),
				" - ".join(part for part in [_text(item.get("start_date")), _text(item.get("end_date"))] if part),
			] if part
		)
		detail = _text(item.get("detail"))
		if main and detail:
			education_lines.append(f"{main}：{detail}")
		elif main or detail:
			education_lines.append(main or detail)
	_append_list_block(lines, "教育背景", education_lines)

	skills = profile.get("skills") if isinstance(profile.get("skills"), list) else []
	_append_list_block(lines, "技能证书", [_text(skill) for skill in skills])

	preferences = profile.get("preferences") if isinstance(profile.get("preferences"), dict) else {}
	self_evaluation = _markdown_escape(preferences.get("self_evaluation"))
	if self_evaluation:
		lines.extend(["", "## 综合评价", self_evaluation])

	for section in sections:
		lines.extend(["", f"## {_section_title(section)}"])
		summary = _markdown_escape(section.get("summary"))
		if summary:
			lines.append(summary)
		for entry in section.get("entries") or []:
			title = _text(entry.get("title")) or "未命名经历"
			meta_text = _entry_meta_text(section, entry, include_date=True)
			lines.extend(["", f"### {title}"])
			if meta_text:
				lines.append(meta_text)
			description = _markdown_escape(entry.get("description"))
			if description:
				lines.append(description)
			for material in entry.get("materials") or []:
				content = _markdown_escape(material.get("content"))
				if content:
					lines.append(f"- {content}")

	return sanitize_resume_text("\n".join(lines).strip() + "\n")


def export_resume_version_pdf(
	version: dict[str, Any],
	output_dir: Path,
	*,
	template_id: str | None = None,
	show_photo: bool = True,
	renderer: PdfRenderer | None = None,
) -> Path:
	output_dir.mkdir(parents=True, exist_ok=True)
	filename = resume_version_filename(version)
	output_path = output_dir / filename
	if renderer is None:
		from bosshunter.web.reactive_resume import (
			ReactiveResumeRenderError,
			is_reactive_template,
			render_reactive_resume_pdf,
		)

		raw_template_id = _template_raw_id(version, template_id)
		if is_reactive_template(raw_template_id):
			try:
				if render_reactive_resume_pdf(version, output_path, template_id=raw_template_id, show_photo=show_photo):
					return output_path
			except ReactiveResumeRenderError as exc:
				raise RuntimeError(str(exc)) from exc

	html_text = resume_version_html(version, template_id=template_id, show_photo=show_photo)
	if renderer is None:
		from bosshunter.ai.resume import _render_pdf_via_cdp

		renderer = _render_pdf_via_cdp
	if not renderer(html_text, output_path):
		raise RuntimeError("PDF 导出失败，请确认 Browser Runtime 或 Chrome 调试连接可用")
	if not output_path.is_file() or output_path.stat().st_size <= 0:
		raise RuntimeError("PDF 导出失败，未生成有效文件")
	return output_path
