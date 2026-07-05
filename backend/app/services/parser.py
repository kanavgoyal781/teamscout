import hashlib
import io
from pathlib import Path
from zipfile import BadZipFile

import fitz
from docx import Document
from docx.opc.exceptions import PackageNotFoundError

from app.errors import ValidationError
from app.schemas.resume import ResumeProfile
from app.services import llm

ALLOWED_EXTENSIONS = {".pdf", ".docx"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

_RESUME_SCHEMA_PROMPT = """Extract a structured resume profile from the raw text below.

Return JSON with this shape:
{
  "name": "string",
  "title": "string",
  "years_of_experience": number,
  "location": "string",
  "skills": ["skill1", "skill2"],
  "work_experience": [{"title": "string", "company": "string", "bullets": ["string"]}],
  "summary": "string"
}

Rules:
- skills should be concise technology and domain keywords
- years_of_experience should be a reasonable numeric estimate
- work_experience bullets should be short achievement statements

Resume text:
"""


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_text(filename: str, data: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            "Unsupported file type — upload PDF or DOCX",
            details={"allowed": sorted(ALLOWED_EXTENSIONS)},
        )
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValidationError("File too large — max 10MB")

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
    return llm.complete_json(
        _RESUME_SCHEMA_PROMPT + text,
        ResumeProfile,
        system="You extract structured resume data. Return JSON only.",
    )


def parse_resume_file(filename: str, data: bytes) -> tuple[str, ResumeProfile]:
    file_hash = content_hash(data)
    text = extract_text(filename, data)
    profile = parse_resume_text(text)
    return file_hash, profile