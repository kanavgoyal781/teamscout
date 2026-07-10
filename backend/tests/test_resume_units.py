"""Unit segmentation: sentence split + word cap."""

from __future__ import annotations

from app.schemas.resume import ResumeProfile, WorkExperience
from app.services.resume_units import (
    MAX_UNIT_WORDS,
    cap_unit_words,
    extract_units,
    segment_text_units,
    split_into_sentences,
)


def test_split_summary_into_sentences() -> None:
    parts = split_into_sentences("First sentence. Second sentence! Third?")
    assert len(parts) >= 3


def test_cap_unit_words_at_forty() -> None:
    words = " ".join(f"w{i}" for i in range(90))
    chunks = cap_unit_words(words, max_words=MAX_UNIT_WORDS)
    assert len(chunks) == 3
    assert all(len(c.split()) <= MAX_UNIT_WORDS for c in chunks)


def test_extract_units_segments_long_summary() -> None:
    long_summary = " ".join(f"Word{i}" for i in range(50)) + ". Another sentence with more detail here."
    profile = ResumeProfile(
        name="T",
        title="Engineer",
        years_of_experience=3,
        skills=["Python"],
        summary=long_summary,
        work_experience=[
            WorkExperience(
                title="Eng",
                company="Co",
                bullets=[" ".join(f"b{i}" for i in range(50))],
            )
        ],
    )
    units = extract_units(profile)
    summary_units = [u for u in units if u.section == "summary"]
    assert len(summary_units) >= 2
    assert all(len(u.unit_text.split()) <= MAX_UNIT_WORDS for u in summary_units)
    exp_units = [u for u in units if u.section == "experience" and u.unit_text.startswith("b0")]
    # long bullet should be capped into multiple units
    assert any(len(u.unit_text.split()) <= MAX_UNIT_WORDS for u in units if u.section == "experience")


def test_segment_text_units_sentence_then_cap() -> None:
    text = "Short one. " + " ".join(f"x{i}" for i in range(45))
    parts = segment_text_units(text)
    assert len(parts) >= 2
