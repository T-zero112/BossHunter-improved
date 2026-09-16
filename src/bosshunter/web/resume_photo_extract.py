"""Best-effort extraction of profile photos embedded in resume files."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from pypdf import PdfReader
from pypdf.errors import PdfReadError


MIN_PROFILE_PHOTO_BYTES = 2048
SUPPORTED_PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass(frozen=True)
class ExtractedResumePhoto:
	content: bytes
	mime_type: str
	suffix: str
	source: str


def extract_resume_photo(filename: str, content: bytes, *, max_bytes: int) -> ExtractedResumePhoto | None:
	"""Return the most likely profile photo embedded in a DOCX/PDF resume."""
	suffix = Path(filename or "").suffix.lower()
	if suffix == ".docx":
		return _extract_docx_photo(content, max_bytes=max_bytes)
	if suffix == ".pdf":
		return _extract_pdf_photo(content, max_bytes=max_bytes)
	return None


def _extract_docx_photo(content: bytes, *, max_bytes: int) -> ExtractedResumePhoto | None:
	try:
		with ZipFile(BytesIO(content)) as archive:
			candidates = []
			for item in archive.infolist():
				name = item.filename.replace("\\", "/")
				if not name.startswith("word/media/"):
					continue
				if Path(name).suffix.lower() not in SUPPORTED_PHOTO_EXTENSIONS:
					continue
				if item.file_size < MIN_PROFILE_PHOTO_BYTES or item.file_size > max_bytes:
					continue
				try:
					image_content = archive.read(item)
				except (OSError, RuntimeError):
					continue
				photo = _photo_from_bytes(image_content, source=name)
				if photo:
					candidates.append(photo)
	except (BadZipFile, OSError, RuntimeError):
		return None
	if not candidates:
		return None
	return max(candidates, key=lambda photo: len(photo.content))


def _extract_pdf_photo(content: bytes, *, max_bytes: int) -> ExtractedResumePhoto | None:
	try:
		reader = PdfReader(BytesIO(content))
		if reader.is_encrypted:
			return None
	except (PdfReadError, OSError, TypeError, ValueError):
		return None

	candidates = []
	try:
		for page_index, page in enumerate(reader.pages):
			for image_index, image in enumerate(getattr(page, "images", []) or []):
				data = getattr(image, "data", None)
				if not isinstance(data, bytes):
					continue
				if len(data) < MIN_PROFILE_PHOTO_BYTES or len(data) > max_bytes:
					continue
				name = str(getattr(image, "name", "") or f"page-{page_index + 1}-image-{image_index + 1}")
				photo = _photo_from_bytes(data, source=name)
				if photo:
					candidates.append(photo)
	except Exception:
		return None
	if not candidates:
		return None
	return max(candidates, key=lambda photo: len(photo.content))


def _photo_from_bytes(content: bytes, *, source: str) -> ExtractedResumePhoto | None:
	if content.startswith(b"\xff\xd8"):
		return ExtractedResumePhoto(content=content, mime_type="image/jpeg", suffix=".jpg", source=source)
	if content.startswith(b"\x89PNG\r\n\x1a\n"):
		return ExtractedResumePhoto(content=content, mime_type="image/png", suffix=".png", source=source)
	if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
		return ExtractedResumePhoto(content=content, mime_type="image/webp", suffix=".webp", source=source)
	return None
