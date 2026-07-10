"""Feedback capture schemas (thumbs + implicit apply/find-team)."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

FeedbackKind = Literal[
    "thumbs_up",
    "thumbs_down",
    "apply_click",
    "find_team_click",
    "compose_opened",
]
FeedbackTargetType = Literal["job_match", "resume_pick", "contact"]
_HEX = re.compile(r"^[a-fA-F0-9]{8,64}$")
class FeedbackCreate(BaseModel):
    kind: FeedbackKind
    target_type: FeedbackTargetType
    target_id: str = Field(min_length=1, max_length=128)
    secondary_id: str | None = Field(default=None, max_length=128)
    profile_hash: str | None = Field(default=None, max_length=64)
    jd_hash: str | None = Field(default=None, max_length=64)
    score_shown: float | None = Field(default=None, ge=0, le=100)
    @field_validator("profile_hash", "jd_hash", mode="before")
    @classmethod
    def _hex_hash(cls, v: object) -> object:
        if v is None or v == "":
            return None
        if not isinstance(v, str) or not _HEX.match(v):
            raise ValueError("must be 8–64 hex characters")
        return v.lower()
    @field_validator("score_shown", mode="before")
    @classmethod
    def _finite_score(cls, v: object) -> object:
        if v is None or v == "":
            return None
        f = float(v)  # type: ignore[arg-type]
        if f != f or f in (float("inf"), float("-inf")):  # NaN/inf
            raise ValueError("score_shown must be finite")
        return f
class FeedbackResponse(BaseModel):
    id: str
    kind: str
    target_type: str
    target_id: str
    created_at: str | None = None
