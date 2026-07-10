"""Feedback capture schemas (thumbs + implicit apply/find-team)."""
from __future__ import annotations
import re
from typing import Literal
from pydantic import BaseModel, Field, field_validator
FeedbackKind = Literal["thumbs_up", "thumbs_down", "apply_click", "find_team_click"]
FeedbackTargetType = Literal["job_match", "resume_pick"]
_HEX = re.compile(r"^[a-fA-F0-9]{8,64}$")
_SCORE_COMPONENT_KEYS = frozenset({
    "llm", "rrf", "skills", "recency", "experience", "requirements", "cross_encoder",
})
_LLM_KEYS = frozenset({"llm"})  # 0–100 scale; others 0–1
class FeedbackCreate(BaseModel):
    kind: FeedbackKind
    target_type: FeedbackTargetType
    target_id: str = Field(min_length=1, max_length=128)
    secondary_id: str | None = Field(default=None, max_length=128)
    profile_hash: str | None = Field(default=None, max_length=64)
    jd_hash: str | None = Field(default=None, max_length=64)
    score_shown: float | None = Field(default=None, ge=0, le=100)
    shown_rank: int | None = Field(default=None, ge=0, le=10_000)
    score_components: dict[str, float] | None = None
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
    @field_validator("score_components", mode="before")
    @classmethod
    def _sanitize_components(cls, v: object) -> object:
        if v is None or v == "":
            return None
        if not isinstance(v, dict):
            raise ValueError("score_components must be an object")
        if len(v) > 16:
            raise ValueError("score_components has too many keys")
        out: dict[str, float] = {}
        for raw_k, raw_val in v.items():
            key = str(raw_k).strip().lower()
            if key not in _SCORE_COMPONENT_KEYS:
                continue
            try:
                f = float(raw_val)  # type: ignore[arg-type]
            except (TypeError, ValueError) as exc:
                raise ValueError(f"score_components.{key} must be numeric") from exc
            if f != f or f in (float("inf"), float("-inf")):
                raise ValueError(f"score_components.{key} must be finite")
            if key in _LLM_KEYS:
                out[key] = max(0.0, min(100.0, f))
            else:
                if f > 1.0:
                    f = f / 100.0
                out[key] = max(0.0, min(1.0, f))
        return out or None
class FeedbackResponse(BaseModel):
    id: str
    kind: str
    target_type: str
    target_id: str
    created_at: str | None = None
