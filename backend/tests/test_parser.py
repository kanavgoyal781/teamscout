import io
from unittest.mock import patch

import pytest
from docx import Document

from app.errors import ValidationError
from app.schemas.resume import ResumeProfile, WorkExperience
from app.services import parser
from tests.conftest import SAMPLE_PDF


def _make_docx(text: str) -> bytes:
    document = Document()
    document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_extract_docx_text() -> None:
    payload = _make_docx("Jane Doe\nSenior Backend Engineer\nPython, FastAPI")
    text = parser.extract_text("resume.docx", payload)
    assert "Backend Engineer" in text
    assert "Python" in text


def test_extract_pdf_text() -> None:
    text = parser.extract_text("resume.pdf", SAMPLE_PDF.read_bytes())
    assert "Backend Engineer" in text
    assert "Python" in text


def test_rejects_unsupported_extension() -> None:
    with pytest.raises(ValidationError):
        parser.extract_text("resume.txt", b"hello")


def test_parse_resume_text_uses_llm_json() -> None:
    profile = ResumeProfile(
        name="Jane Doe",
        title="Senior Backend Engineer",
        years_of_experience=8,
        location="San Francisco, CA",
        skills=["Python", "FastAPI"],
        work_experience=[
            WorkExperience(title="Backend Engineer", company="Acme", bullets=["Built APIs"])
        ],
        summary="Backend specialist",
    )
    with patch("app.services.parser.llm.complete_json", return_value=profile) as mocked:
        parsed = parser.parse_resume_text("raw resume text")
    mocked.assert_called_once()
    assert parsed.title == "Senior Backend Engineer"
    assert "Python" in parsed.skills


def test_content_hash_is_stable() -> None:
    data = b"same-content"
    assert parser.content_hash(data) == parser.content_hash(data)
    assert parser.content_hash(data) != parser.content_hash(b"other")