"""Listwise LLM rerank: permutation validation + rank→score + token budgets."""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, Field


class ListwiseItem(BaseModel):
    job_id: str
    reason: str = ""


class ListwiseResponse(BaseModel):
    ranking: list[ListwiseItem] = Field(default_factory=list)


class PermutationError(ValueError):
    """Ranking is not a true permutation of expected ids."""


def validate_permutation(ranking_ids: list[str], expected_ids: list[str]) -> list[str]:
    expected = list(expected_ids)
    expected_set = set(expected)
    if len(expected) != len(expected_set):
        raise PermutationError("expected_ids contain duplicates")
    if not expected:
        if ranking_ids:
            raise PermutationError("unexpected ids for empty expected set")
        return []
    cleaned = [(rid or "").strip() for rid in ranking_ids]
    if any(not c for c in cleaned):
        raise PermutationError("empty job_id in ranking")
    seen: set[str] = set()
    ordered: list[str] = []
    for rid in cleaned:
        if rid not in expected_set:
            raise PermutationError(f"hallucinated id: {rid}")
        if rid in seen:
            raise PermutationError(f"duplicate id: {rid}")
        seen.add(rid)
        ordered.append(rid)
    missing = expected_set - seen
    if missing:
        raise PermutationError(f"missing ids: {sorted(missing)}")
    if len(ordered) != len(expected):
        raise PermutationError("length mismatch after validation")
    return ordered


def parse_listwise_ranking(payload: Any, expected_ids: list[str]) -> list[tuple[str, str]]:
    if isinstance(payload, ListwiseResponse):
        items = payload.ranking
    elif isinstance(payload, dict):
        raw = payload.get("ranking")
        if not isinstance(raw, list):
            raise PermutationError("missing ranking array")
        items = [ListwiseItem.model_validate(x) for x in raw]
    else:
        raise PermutationError("invalid listwise payload type")
    ordered = validate_permutation([it.job_id for it in items], expected_ids)
    by_id = {it.job_id.strip(): (it.reason or "").strip() for it in items}
    return [(jid, by_id.get(jid, "")) for jid in ordered]


def position_to_score(rank: int, n: int) -> float:
    """0-based rank → 0–100 fit. Best=100, last=0 when n>1."""
    if n <= 0:
        return 0.0
    if n == 1:
        return 100.0
    return round(100.0 * (n - 1 - rank) / (n - 1), 4)


def ranks_to_fit_scores(ordered_ids: list[str]) -> dict[str, float]:
    n = len(ordered_ids)
    return {jid: position_to_score(i, n) for i, jid in enumerate(ordered_ids)}


LEGACY_POINTWISE_BATCH = 6
LEGACY_POINTWISE_PER_JOB = 200
LEGACY_POINTWISE_BASE = 500
LEGACY_POINTWISE_FLOOR = 1400
LEGACY_RERANK_TOP_N = 30


def legacy_pointwise_token_budget(*, top_n: int = LEGACY_RERANK_TOP_N, prompt_cap: int = 4000) -> int:
    n_batches = max(1, math.ceil(top_n / LEGACY_POINTWISE_BATCH))
    per = min(
        prompt_cap,
        max(LEGACY_POINTWISE_FLOOR, LEGACY_POINTWISE_BASE + LEGACY_POINTWISE_PER_JOB * LEGACY_POINTWISE_BATCH),
    )
    return n_batches * per


def listwise_token_budget(*, n_jobs: int = 15, prompt_cap: int = 2000) -> int:
    return min(prompt_cap, max(800, 400 + 80 * n_jobs))
