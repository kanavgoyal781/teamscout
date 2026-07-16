from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.workspace import workspace_or_system
from app.db.models import Resume, ResumeUnit
from app.schemas.resume import ResumeProfile
from app.services import embeddings

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
MAX_UNIT_WORDS = 40
SEGMENTER_VERSION = "2"  # bump → invalidates units_content_hash (lazy re-index)
MIN_ALPHA_DENSITY = 0.40
MIN_FRAGMENT_WORDS = 4


@dataclass(frozen=True)
class ResumeUnitData:
    unit_text: str
    section: str
    unit_hash: str
    embedding: list[float] | None = None


def unit_hash(text: str, section: str) -> str:
    return hashlib.sha256(f"{section}\n{text.strip()}".encode()).hexdigest()


def units_stamp(units: list[ResumeUnitData]) -> str:
    payload = f"{SEGMENTER_VERSION}:" + "".join(u.unit_hash for u in units)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def profile_units_stamp(profile: ResumeProfile) -> str:
    return units_stamp(extract_units(profile))


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def alphabetic_density(text: str) -> float:
    if not text:
        return 0.0
    return sum(1 for c in text if c.isalpha()) / len(text)


def is_junk_fragment(text: str, *, section: str = "") -> bool:
    cleaned = " ".join((text or "").split()).strip()
    if not cleaned:
        return True
    if (section or "").strip().lower() in {"skills", "title"}:
        return len(cleaned) < 1
    if alphabetic_density(cleaned) < MIN_ALPHA_DENSITY:
        return True
    words = cleaned.split()
    if " at " in cleaned.lower() and len(words) >= 2:
        return False
    if cleaned[0].islower() and len(words) < 6:
        return True
    if len(words) < MIN_FRAGMENT_WORDS and not cleaned[0].isupper():
        return True
    return False


def split_into_sentences(text: str) -> list[str]:
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    parts = [p.strip() for p in _SENTENCE_SPLIT.split(cleaned) if p and p.strip()]
    return parts or [cleaned]


def cap_unit_words(text: str, *, max_words: int = MAX_UNIT_WORDS) -> list[str]:
    cleaned = " ".join((text or "").split()).strip()
    if not cleaned:
        return []
    words = cleaned.split()
    if len(words) <= max_words:
        return [cleaned]
    return [
        " ".join(words[i : i + max_words]).strip() for i in range(0, len(words), max_words) if words[i : i + max_words]
    ]


def segment_text_units(text: str, *, max_words: int = MAX_UNIT_WORDS, section: str = "experience") -> list[str]:
    merged: list[str] = []
    for sentence in split_into_sentences(text):
        for chunk in cap_unit_words(sentence, max_words=max_words):
            if not chunk:
                continue
            if is_junk_fragment(chunk, section=section):
                if merged:
                    merged[-1] = f"{merged[-1]} {chunk}".strip()
                continue
            merged.append(chunk)
    return [u for u in merged if not is_junk_fragment(u, section=section)]


def extract_units(profile: ResumeProfile) -> list[ResumeUnitData]:
    units: list[ResumeUnitData] = []
    seen: set[str] = set()

    def add(section: str, text: str) -> None:
        cleaned = " ".join((text or "").split()).strip()
        if len(cleaned) < 2 or is_junk_fragment(cleaned, section=section):
            return
        key = f"{section}:{cleaned.lower()}"
        if key in seen:
            return
        seen.add(key)
        units.append(ResumeUnitData(unit_text=cleaned, section=section, unit_hash=unit_hash(cleaned, section)))

    def add_segmented(section: str, text: str) -> None:
        for part in segment_text_units(text, section=section):
            add(section, part)

    if profile.title.strip():
        add("title", profile.title)
    if profile.summary.strip():
        add_segmented("summary", profile.summary.strip())
    for skill in profile.skills:
        add("skills", skill)
    for role in profile.work_experience:
        header_bits = [b for b in (role.title, role.company) if b and b.strip()]
        if header_bits:
            add("experience", " at ".join(header_bits))
        for bullet in role.bullets:
            add_segmented("experience", bullet)
    return units


def embed_units(units: list[ResumeUnitData]) -> list[ResumeUnitData]:
    if not units:
        return []
    texts = [u.unit_text for u in units]
    vectors = embeddings.embed_batch(texts)
    return [
        ResumeUnitData(
            unit_text=u.unit_text,
            section=u.section,
            unit_hash=u.unit_hash,
            embedding=_l2_normalize(vec) if vec is not None else None,
        )
        for u, vec in zip(units, vectors, strict=True)
    ]


def units_for_profile(profile: ResumeProfile, *, embed: bool = True) -> list[ResumeUnitData]:
    units = extract_units(profile)
    if embed and units:
        return embed_units(units)
    return units


def load_units_for_resume(db: Session, resume_id: str) -> list[ResumeUnitData]:
    rows = (
        db.query(ResumeUnit)
        .filter(ResumeUnit.resume_id == resume_id)
        .order_by(ResumeUnit.section, ResumeUnit.unit_hash)
        .all()
    )
    out: list[ResumeUnitData] = []
    for row in rows:
        emb: list[float] | None = None
        if row.embedding_json:
            try:
                data = json.loads(row.embedding_json)
                if isinstance(data, list) and data:
                    emb = _l2_normalize([float(x) for x in data])
            except (json.JSONDecodeError, TypeError, ValueError):
                emb = None
        out.append(
            ResumeUnitData(
                unit_text=row.unit_text,
                section=row.section,
                unit_hash=row.unit_hash,
                embedding=emb,
            )
        )
    return out


def persist_units(db: Session, resume_id: str, units: list[ResumeUnitData]) -> None:
    db.query(ResumeUnit).filter(ResumeUnit.resume_id == resume_id).delete()
    for u in units:
        db.add(
            ResumeUnit(
                workspace_id=workspace_or_system(),
                resume_id=resume_id,
                unit_text=u.unit_text,
                section=u.section,
                unit_hash=u.unit_hash,
                embedding_json=json.dumps(u.embedding) if u.embedding is not None else None,
            )
        )
    db.commit()


def index_resume_units(
    db: Session,
    resume_id: str,
    profile: ResumeProfile,
    *,
    force: bool = False,
) -> list[ResumeUnitData]:
    row = db.query(Resume).filter(Resume.id == resume_id).one_or_none()
    desired = extract_units(profile)
    stamp = units_stamp(desired)
    existing = load_units_for_resume(db, resume_id)
    complete = bool(existing) and all(u.embedding is not None for u in existing)
    if not force and complete and row is not None and row.units_content_hash == stamp:
        return existing
    if not force and complete and [u.unit_hash for u in existing] == [u.unit_hash for u in desired]:
        if row is not None and row.units_content_hash != stamp:
            row.units_content_hash = stamp
            db.add(row)
            db.commit()
        return existing
    by_hash = {u.unit_hash: u for u in existing if u.embedding is not None}
    reused = [by_hash[u.unit_hash] for u in desired if u.unit_hash in by_hash]
    to_embed = [u for u in desired if u.unit_hash not in by_hash]
    by_h = {u.unit_hash: u for u in reused + (embed_units(to_embed) if to_embed else [])}
    ordered = [by_h[u.unit_hash] for u in desired if u.unit_hash in by_h]
    persist_units(db, resume_id, ordered)
    if row is not None:
        row.units_content_hash = stamp
        db.add(row)
        db.commit()
    return ordered


def ensure_candidate_units(
    profile: ResumeProfile,
    *,
    db: Session | None = None,
    resume_id: str | None = None,
) -> list[ResumeUnitData]:
    if db is not None and resume_id:
        return index_resume_units(db, resume_id, profile, force=False)
    return units_for_profile(profile, embed=True)
