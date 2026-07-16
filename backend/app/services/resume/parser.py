import hashlib
import io
from pathlib import Path
from zipfile import BadZipFile

import fitz
from docx import Document
from docx.opc.exceptions import PackageNotFoundError

from app.core.config import settings
from app.errors import ValidationError
from app.prompts import load_prompt
from app.schemas.resume import ResumeProfile
from app.services import llm

ALLOWED_EXTENSIONS = {".pdf", ".docx"}


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_text(filename: str, data: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            "Unsupported file type — upload PDF or DOCX",
            details={"allowed": sorted(ALLOWED_EXTENSIONS)},
        )
    max_bytes = settings.MAX_UPLOAD_BYTES
    if len(data) > max_bytes:
        raise ValidationError(
            f"File too large — max {max_bytes} bytes",
            details={"max_bytes": max_bytes, "size": len(data)},
        )
    if suffix == ".pdf":
        return _extract_pdf(data)
    return _extract_docx(data)


def _extract_pdf(data: bytes) -> str:
    try:
        with fitz.open(stream=data, filetype="pdf") as doc:
            parts = [page.get_text("text") for page in doc]
    except (fitz.FileDataError, fitz.EmptyFileError, ValueError, RuntimeError) as exc:
        raise ValidationError(f"Failed to read PDF: {exc}") from exc
    text = "\n".join(parts).strip()
    if not text:
        raise ValidationError("PDF contains no extractable text")
    return text


def _extract_docx(data: bytes) -> str:
    try:
        document = Document(io.BytesIO(data))
        parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    except (PackageNotFoundError, BadZipFile, KeyError, ValueError) as exc:
        raise ValidationError(f"Failed to read DOCX: {exc}") from exc
    text = "\n".join(parts).strip()
    if not text:
        raise ValidationError("DOCX contains no extractable text")
    return text


def parse_resume_text(text: str) -> ResumeProfile:
    if not text.strip():
        raise ValidationError("Resume text is empty")
    tmpl = load_prompt("resume_schema")
    return llm.complete_json(
        tmpl.body + text,
        ResumeProfile,
        system=tmpl.system or "You extract structured resume data. Return JSON only.",
        operation="parse_resume",
        prompt_meta=tmpl,
        max_tokens=int(tmpl.model_params.get("max_tokens") or settings.max_tokens_for_operation("parse_resume")),
    )


def parse_resume_file(filename: str, data: bytes) -> tuple[str, ResumeProfile]:
    file_hash = content_hash(data)
    text = extract_text(filename, data)
    profile = parse_resume_text(text)
    return file_hash, profile
