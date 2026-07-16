"""Live ranking param snapshot + config hash (shared by feedback + experiments)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.core.config import settings

DEFAULT_MMR_LAMBDA = 0.75
DEFAULT_USE_MMR = True
DEFAULT_EXPANSION = True
DEFAULT_TOURNAMENT_THRESHOLD = 0.05
RESULT_PARAM_KEYS = (
    "weights",
    "rrf_k",
    "mmr_lambda",
    "use_mmr",
    "expansion",
    "tournament_threshold",
    "recency_half_life_days",
    "rerank_top_n",
    "search_results_top_n",
    "use_cross_encoder",
    "cross_encoder_shortlist",
    "llm_listwise",
    "cross_encoder_pool",
    "llm_rerank_top_n",
    "direct_ats_boost",
)


def live_ranking_params() -> dict[str, Any]:
    return {
        "weights": {
            "llm": settings.RANKING_WEIGHT_LLM,
            "rrf": settings.RANKING_WEIGHT_RRF,
            "skills": settings.RANKING_WEIGHT_SKILLS,
            "recency": settings.RANKING_WEIGHT_RECENCY,
            "experience": settings.RANKING_WEIGHT_EXPERIENCE,
            "requirements": settings.RANKING_WEIGHT_REQUIREMENTS,
            "cross_encoder": settings.RANKING_WEIGHT_CROSS_ENCODER,
        },
        "rrf_k": settings.RRF_K,
        "mmr_lambda": DEFAULT_MMR_LAMBDA,
        "use_mmr": DEFAULT_USE_MMR,
        "expansion": DEFAULT_EXPANSION,
        "tournament_threshold": DEFAULT_TOURNAMENT_THRESHOLD,
        "recency_half_life_days": settings.RECENCY_HALF_LIFE_DAYS,
        "rerank_top_n": settings.RERANK_TOP_N,
        "search_results_top_n": settings.SEARCH_RESULTS_TOP_N,
        "use_cross_encoder": settings.RANKING_USE_CROSS_ENCODER,
        "cross_encoder_shortlist": settings.CROSS_ENCODER_SHORTLIST,
        "llm_listwise": settings.RANKING_LLM_LISTWISE,
        "cross_encoder_pool": settings.CROSS_ENCODER_POOL,
        "llm_rerank_top_n": settings.LLM_RERANK_TOP_N,
        "direct_ats_boost": float(settings.RANKING_DIRECT_ATS_BOOST),
    }


def ranking_config_hash(params: dict[str, Any] | None = None) -> str:
    payload = params if params is not None else live_ranking_params()
    body = {k: payload[k] for k in RESULT_PARAM_KEYS if k in payload}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
