"""Semantic formatting helpers for imported resume descriptions."""

from __future__ import annotations

import re


ACTION_PREFIX_RE = re.compile(
	r"^(?:实现|解决|完成|负责|参与|搭建|构建|开发|设计|优化|训练|部署|采集|控制|编写|测试|分析|建立|提出|集成|验证|调研|推进|维护|整理|归档|协助|主导|独立|配合)"
)
DATE_RANGE_PREFIX_RE = re.compile(r"^(?:19|20)\d{2}[./年-]?\d{0,2}\s*(?:[-至到~—]+)\s*(?:(?:19|20)\d{2}|至今|现在|今)[./年-]?\d{0,2}")
STRUCTURED_LABEL_RE = re.compile(
	r"(?:技术栈|工具环境|开发环境|运行环境|技术路线|项目背景|项目目标|项目职责|主要职责|工作内容|核心工作|"
	r"项目内容|项目成果|核心成果|成果产出|项目亮点|技术亮点|核心亮点|项目难点|技术难点|核心难点|"
	r"问题定位|解决方案|优化方案|实现方案|整体架构|系统架构|平台架构|多\s*Agent\s*架构|模型架构|"
	r"端到端生成|端到端流程|工程化优化|工程优化|性能优化|流程优化|数据处理|数据分析|用户洞察|"
	r"用户洞察与分析|业务分析|模型训练|模型部署|测试验证)"
)


def format_entry_description_lines(lines: list[str], section_type: str) -> str:
	"""Merge PDF-wrapped lines while preserving semantic breaks in experience text."""
	cleaned = [_clean_line(line) for line in lines if _clean_line(line)]
	if section_type not in {"project", "work"}:
		return _join_wrapped_lines(cleaned)
	return format_entry_description_text("\n".join(cleaned))


def format_entry_description_text(text: str) -> str:
	"""Normalize a project/work description into readable semantic lines."""
	lines = _expand_inline_boundaries(str(text or ""))
	result = ""
	for raw in lines:
		line = _clean_line(raw)
		if not line:
			continue
		if not result:
			result = line
			continue
		if _should_keep_line_break(raw, line, result):
			result = f"{result}\n{line}"
		else:
			result = f"{result}{line}"
	return result.strip()


def _expand_inline_boundaries(text: str) -> list[str]:
	lines: list[str] = []
	for raw in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
		line = _clean_line(raw)
		if not line:
			continue
		line = re.sub(
			r"(?<=[A-Za-z0-9)）.;；。!?！？])\s*(?=(?:实现|解决|完成|负责|参与|搭建|构建|开发|设计|优化|训练|部署|采集|控制|测试|建立|提出|集成|验证|调研|推进|维护|整理|归档|协助|主导|独立|配合)[\u4e00-\u9fffA-Za-z0-9])",
			"\n",
			line,
		)
		line = _split_inline_structured_labels(line)
		lines.extend(part for part in line.split("\n") if _clean_line(part))
	return lines


def _split_inline_structured_labels(text: str) -> str:
	breaks: list[int] = []
	for match in re.finditer(r"[：:](?=\s*\S)", text):
		colon_index = match.start()
		label_start = _inline_colon_label_start(text, colon_index)
		if label_start < 0:
			continue
		label = text[label_start:colon_index].strip()
		content = text[match.end() : _next_inline_boundary(text, match.end())].strip()
		prefix = text[:label_start]
		if _looks_like_colon_heading(label, content, prefix):
			breaks.append(label_start)
	if not breaks:
		return text
	result = ""
	index = 0
	for start in sorted(set(breaks)):
		if start <= index:
			continue
		result += text[index:start].rstrip()
		result += "\n"
		index = start
	result += text[index:].lstrip(" ；;")
	result = re.sub(r"\n\s+", "\n", result)
	return result


def _inline_colon_label_start(text: str, colon_index: int) -> int:
	left = text[:colon_index].rstrip()
	if not left:
		return -1
	boundary = max(left.rfind(mark) for mark in "\n。；;!?！？")
	segment_start = boundary + 1
	segment = left[segment_start:].strip()
	if not segment:
		return -1
	if _colon_label_shape_ok(segment):
		return segment_start + left[segment_start:].find(segment)
	for candidate in _trailing_label_candidates(segment):
		if _colon_label_shape_ok(candidate):
			return segment_start + segment.rfind(candidate)
	match = STRUCTURED_LABEL_RE.search(segment)
	if match:
		return segment_start + match.start()
	return -1


def _trailing_label_candidates(segment: str) -> list[str]:
	parts = [part for part in re.split(r"[\s/]+", segment.strip()) if part]
	candidates: list[str] = []
	for size in range(1, min(3, len(parts)) + 1):
		candidate = " ".join(parts[-size:]).strip()
		if candidate and candidate not in candidates:
			candidates.append(candidate)
	return candidates


def _next_inline_boundary(text: str, start: int) -> int:
	candidates = [index for index in (text.find(mark, start) for mark in "\n。；;!?！？") if index >= 0]
	return min(candidates) if candidates else len(text)


def _looks_like_colon_heading(label: str, content: str, prefix: str) -> bool:
	value = _clean_line(label)
	if not _colon_label_shape_ok(value):
		return False
	if _is_explanatory_colon_label(value):
		return False
	if not _colon_content_shape_ok(content):
		return False
	if _is_strong_structured_label(value) or ACTION_PREFIX_RE.match(value):
		return True
	if _prefix_supports_inline_heading(prefix):
		return True
	return _generic_heading_label(value)


def _colon_label_shape_ok(label: str) -> bool:
	value = _clean_line(label)
	if not value:
		return False
	compact = re.sub(r"\s+", "", value)
	if not (2 <= len(compact) <= 14):
		return False
	if re.search(r"[。；;，,、()（）\[\]/：:]", value):
		return False
	if re.search(r"(?:的|了|和|与|及|并|将|在|为|是|通过|基于|使用|采用)$", value):
		return False
	return True


def _colon_content_shape_ok(content: str) -> bool:
	value = _clean_line(content)
	if not value:
		return False
	if len(value) < 6:
		return False
	if value in {"无", "暂无", "无。", "暂无。"}:
		return False
	return True


def _is_explanatory_colon_label(label: str) -> bool:
	value = re.sub(r"\s+", "", _clean_line(label))
	return value in {
		"例如",
		"比如",
		"其中",
		"原因",
		"说明",
		"备注",
		"注意",
		"包括",
		"如下",
		"表现",
		"结果",
		"失败原因",
		"具体包括",
		"主要包括",
	}


def _prefix_supports_inline_heading(prefix: str) -> bool:
	value = _clean_line(prefix)
	if not value:
		return True
	if value.endswith(("\n", "。", "；", ";", "!", "！", "?", "？")):
		return True
	return bool(re.search(r"[A-Za-z0-9)）]$", value))


def _generic_heading_label(label: str) -> bool:
	value = _clean_line(label)
	compact = re.sub(r"\s+", "", value)
	if re.search(r"(?:分析|洞察|分层|建模|清洗|治理|采集|训练|部署|验证|测试|优化|复盘|设计|开发|实现|产出|成果|难点|亮点|职责|背景|目标|流程|架构|方案|策略|指标|看板|平台|模块)$", compact):
		return True
	if re.search(r"(?:用户|数据|业务|模型|算法|系统|平台|功能|性能|工程|项目|技术|工具|流程|运营|产品)", compact) and len(compact) <= 10:
		return True
	return False


def _is_strong_structured_label(label: str) -> bool:
	value = _clean_line(label)
	if not value or re.search(r"[。；;，,、()（）\[\]/]", value):
		return False
	if value in {"例如", "比如", "其中", "原因", "说明", "备注", "注意", "包括", "如下", "表现", "结果"}:
		return False
	if STRUCTURED_LABEL_RE.fullmatch(value):
		return True
	if re.search(r"(?:架构|流程|生成|优化|职责|成果|亮点|难点|方案|环境|工具|平台|模型|算法|部署|验证|测试|数据|模块)$", value):
		return True
	return False


def _should_keep_line_break(raw: str, line: str, current: str) -> bool:
	if _is_bullet(raw):
		return True
	previous_line = current.rsplit("\n", 1)[-1]
	if _looks_like_structured_label(line):
		return True
	if _looks_like_structured_label(previous_line) and _looks_like_action_or_result(line):
		return True
	if DATE_RANGE_PREFIX_RE.match(previous_line) and _looks_like_action_or_result(line):
		return True
	if current.endswith(("\n", "。", "；", ";", "：", ":")):
		return True
	if _looks_like_action_or_result(line) and _previous_line_complete(previous_line):
		return True
	return False


def _join_wrapped_lines(lines: list[str]) -> str:
	result = ""
	for raw in lines:
		line = _clean_line(raw)
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


def _looks_like_structured_label(text: str) -> bool:
	line = _clean_line(text)
	match = re.match(r"^([^：:]{2,32})[：:]\s*\S+", line)
	if not match:
		return False
	label = match.group(1).strip()
	if re.search(r"[。；;，,、()（）\[\]]", label):
		return False
	if _is_strong_structured_label(label):
		return True
	if ACTION_PREFIX_RE.match(label):
		return True
	return not re.search(r"(?:的|了|和|与|及|并|将|在|为|是|通过)$", label)


def _looks_like_action_or_result(text: str) -> bool:
	return bool(ACTION_PREFIX_RE.match(_clean_line(text)))


def _previous_line_complete(text: str) -> bool:
	line = _clean_line(text)
	return bool(re.search(r"(?:[。；;!?！？]|[A-Za-z0-9)])$", line))


def _is_bullet(text: str) -> bool:
	return bool(re.match(r"^\s*(?:[-*+•·●▪◦‣]|\d{1,2}[.)、]|[（(]\d{1,2}[）)])\s+", str(text or "")))


def _clean_line(text: str) -> str:
	value = re.sub(r"\s+", " ", str(text or "")).strip()
	return re.sub(r"^(?:[-*+•·●▪◦‣]|\d{1,2}[.)、]|[（(]\d{1,2}[）)])\s*", "", value).strip()
