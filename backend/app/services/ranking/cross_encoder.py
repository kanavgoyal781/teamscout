from __future__ import annotations

import re

import httpx

from app.core.config import settings
from app.core.env_utils import is_set
from app.core.http_timeouts import default_timeout
from app.core.logging import get_logger
from app.errors import ServiceFailingError, ServiceNotConfiguredError
from app.services import observability
from app.services.ranking.math import normalize_scores

logger = get_logger(__name__)
_INFER = "https://api.deepinfra.com/v1/inference"
_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")


def _validated_model() -> str:
    model = (settings.RERANKER_MODEL or "").strip()
    if not model or not _MODEL_RE.match(model) or ".." in model:
        raise ServiceNotConfiguredError("CrossEncoder", "RERANKER_MODEL")
    return model


def _require() -> None:
    if not is_set(settings.EMBEDDINGS_API_KEY):
        raise ServiceNotConfiguredError("CrossEncoder", "EMBEDDINGS_API_KEY")
    _validated_model()


def reranker_endpoint() -> str:
    return f"{_INFER}/{_validated_model()}"


def normalize_cross_encoder_scores(raw: list[float]) -> list[float]:
    if not raw:
        return []
    d = {str(i): float(v) for i, v in enumerate(raw)}
    n = normalize_scores(d)
    return [n[str(i)] for i in range(len(raw))]


def _parse_scores(data: object, n_docs: int) -> list[float]:
    if not isinstance(data, dict) or not isinstance(data.get("scores"), list):
        raise ServiceFailingError("CrossEncoder", "unexpected response format")
    scores = data["scores"]
    if len(scores) != n_docs:
        raise ServiceFailingError("CrossEncoder", f"scores length mismatch: expected {n_docs}")
    try:
        return [float(x) for x in scores]
    except (TypeError, ValueError) as exc:
        raise ServiceFailingError("CrossEncoder", "non-numeric scores") from exc


def cross_encode(query: str, documents: list[str]) -> list[float]:
    if not query or not query.strip():
        raise ServiceFailingError("CrossEncoder", "query must be non-empty")
    if not documents:
        return []
    if any(not d or not str(d).strip() for d in documents):
        raise ServiceFailingError("CrossEncoder", "documents must be non-empty")
    _require()
    model = settings.RERANKER_MODEL or ""
    est = observability.approx_token_count(query) + sum(observability.approx_token_count(d) for d in documents)
    headers = {"Authorization": f"Bearer {settings.EMBEDDINGS_API_KEY}", "Content-Type": "application/json"}
    payload = {"queries": [query], "documents": list(documents)}
    with observability.traced_call(
        "cross_encode",
        model=model,
        check_llm_ceiling=True,
        estimated_cost_usd=observability.estimate_embedding_cost_usd(input_tokens=est),
    ) as trace:
        try:
            with httpx.Client(timeout=default_timeout()) as client:
                r = client.post(reranker_endpoint(), headers=headers, json=payload)
                r.raise_for_status()
                data = r.json()
        except httpx.HTTPError as exc:
            logger.warning("cross_encoder.http_error", error=type(exc).__name__)
            raise ServiceFailingError("CrossEncoder", "upstream request failed") from exc
        raw = _parse_scores(data, len(documents))
        usage = data.get("usage") if isinstance(data, dict) else None
        trace.input_tokens = (
            int(usage["total_tokens"]) if isinstance(usage, dict) and usage.get("total_tokens") is not None else est
        )
        trace.output_tokens = 0
        trace.cost_usd = observability.estimate_embedding_cost_usd(input_tokens=trace.input_tokens)
        trace.cache_hit = False
        out = normalize_cross_encoder_scores(raw)
        logger.info("cross_encoder.scored", n_docs=len(documents), model=model)
        return out


def cross_encode_ids(query: str, id_texts: list[tuple[str, str]]) -> dict[str, float]:
    if not id_texts:
        return {}
    ids = [i for i, _ in id_texts]
    scores = cross_encode(query, [t for _, t in id_texts])
    return {i: s for i, s in zip(ids, scores, strict=True)}
