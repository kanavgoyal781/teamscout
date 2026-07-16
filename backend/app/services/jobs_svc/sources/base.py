"""JobSource protocol + FetchCriteria."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from sqlalchemy.orm import Session

from app.schemas.jobs import Job, SearchParams, SourceCounts
from app.schemas.resume import ResumeProfile

SourceQuality = str
_STOP = frozenset(
    {
        "a",
        "an",
        "and",
        "or",
        "the",
        "of",
        "in",
        "on",
        "at",
        "for",
        "to",
        "with",
        "jr",
        "sr",
        "i",
        "ii",
        "iii",
        "remote",
        "hybrid",
        "onsite",
        "full",
        "time",
        "part",
        "contract",
        "jobs",
        "job",
        "role",
        "position",
    }
)
_ROLE_EXPAND: dict[str, tuple[str, ...]] = {
    "software": ("swe", "sde", "backend", "frontend", "fullstack", "full", "stack", "programmer"),
    "engineer": ("swe", "sde"),
    "developer": ("swe", "programmer"),
    "data": ("scientist", "analytics", "ml"),
    "scientist": ("data", "ml"),
    "machine": ("learning", "ml", "ai"),
    "learning": ("ml", "machine"),
    "ml": ("machine", "learning", "ai"),
    "ai": ("ml", "machine"),
    "backend": ("swe",),
    "frontend": ("swe",),
    "fullstack": ("full", "stack"),
    "full": ("stack", "fullstack"),
    "stack": ("fullstack",),
}


@dataclass
class FetchCriteria:
    profile: ResumeProfile
    params: SearchParams
    queries: list[str] = field(default_factory=list)

    def _tokenize(self, raw: str) -> list[str]:
        out = []
        for tok in raw.lower().replace("/", " ").replace("-", " ").split():
            t = tok.strip(".,;:()[]#+")
            if len(t) >= 2 and t not in _STOP:
                out.append(t)
        return out

    def role_tokens(self) -> list[str]:
        seen: set[str] = set()
        for raw in [self.profile.title or "", *self.queries]:
            for t in self._tokenize(raw):
                seen.add(t)
                for exp in _ROLE_EXPAND.get(t, ()):
                    if exp not in _STOP:
                        seen.add(exp)
        return list(seen)

    def skill_terms(self) -> list[str]:
        out, seen = [], set()
        for skill in self.profile.skills[:8]:
            s = (skill or "").strip()
            if len(s) >= 2 and s.lower() not in seen:
                seen.add(s.lower())
                out.append(s)
        return out

    def title_terms(self) -> list[str]:
        return self.role_tokens() + [s.lower() for s in self.skill_terms()]


@runtime_checkable
class JobSource(Protocol):
    name: str
    cost_free: bool
    source_quality: SourceQuality

    def is_configured(self) -> bool: ...
    def is_enabled_for(self, criteria: FetchCriteria) -> bool: ...
    def fetch(self, criteria: FetchCriteria, db: Session | None = None) -> list[Job]: ...


@dataclass
class SourceFetchOutcome:
    name: str
    jobs: list[Job] = field(default_factory=list)
    counts: SourceCounts = field(default_factory=SourceCounts)
    error: str | None = None
