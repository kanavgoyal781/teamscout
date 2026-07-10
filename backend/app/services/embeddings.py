import hashlib
import json
import math
import httpx
from sqlalchemy.exc import SQLAlchemyError
from app.core.config import settings
from app.core.env_utils import is_set
from app.core.http_timeouts import default_timeout, embeddings_batch_timeout
from app.core.logging import get_logger
from app.db.models import EmbeddingCache
from app.db.session import SessionLocal, ensure_db
from app.errors import ServiceFailingError, ServiceNotConfiguredError
from app.services import observability
logger = get_logger(__name__)
def embeddings_endpoint() -> str:
    """Resolve embeddings POST URL."""
    if is_set(settings.EMBEDDINGS_API):
        base = (settings.EMBEDDINGS_API or "").rstrip("/")
    elif is_set(settings.LLM_API_BASE):
        base = (settings.LLM_API_BASE or "").rstrip("/")
    else:
        return ""
    if base.endswith("/embeddings"):
        return base
    return f"{base}/embeddings"
def _require_embeddings_config() -> None:
    if not is_set(settings.EMBEDDINGS_API_KEY):
        raise ServiceNotConfiguredError("Embeddings", "EMBEDDINGS_API_KEY")
    if not embeddings_endpoint():
        raise ServiceNotConfiguredError("Embeddings", "EMBEDDINGS_API")
def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]
def _cache_key(text: str) -> str:
    raw = f"{settings.EMBEDDINGS_MODEL}\n{text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
def _cache_get(content_hash: str) -> list[float] | None:
    ensure_db()
    session = SessionLocal()
    try:
        row = session.query(EmbeddingCache).filter(EmbeddingCache.content_hash == content_hash).one_or_none()
        if row is None:
            return None
        data = json.loads(row.embedding_json)
        if isinstance(data, list):
            return [float(x) for x in data]
        return None
    except (SQLAlchemyError, json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("embedding_cache.get_failed", error=str(exc))
        return None
    finally:
        session.close()
def _cache_put(content_hash: str, vector: list[float]) -> None:
    ensure_db()
    session = SessionLocal()
    try:
        existing = session.query(EmbeddingCache).filter(EmbeddingCache.content_hash == content_hash).one_or_none()
        payload = json.dumps(vector)
        if existing is not None:
            existing.embedding_json = payload
            existing.model = settings.EMBEDDINGS_MODEL
            session.add(existing)
        else:
            session.add(
                EmbeddingCache(
                    content_hash=content_hash,
                    model=settings.EMBEDDINGS_MODEL,
                    embedding_json=payload,
                )
            )
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        logger.warning("embedding_cache.put_failed", error=str(exc))
    finally:
        session.close()
def _parse_single_embedding(data: object) -> list[float]:
    vec: list[float] | None = None
    if isinstance(data, dict):
        if isinstance(data.get("data"), list) and data["data"]:
            item = data["data"][0]
            if isinstance(item, dict) and isinstance(item.get("embedding"), list):
                vec = [float(x) for x in item["embedding"]]
        elif isinstance(data.get("embedding"), list):
            vec = [float(x) for x in data["embedding"]]
    if not vec:
        raise ServiceFailingError("Embeddings", "unexpected response format")
    return _normalize(vec)
def embed(text: str) -> list[float]:
    if not text or not text.strip():
        raise ValueError("text must be non-empty")
    _require_embeddings_config()
    key = _cache_key(text)
    cached = _cache_get(key)
    est_tokens = observability.approx_token_count(text)
    if cached is not None:
        with observability.traced_call(
            "embed",
            model=settings.EMBEDDINGS_MODEL,
            check_llm_ceiling=False,
        ) as trace:
            trace.input_tokens = est_tokens
            trace.output_tokens = 0
            trace.cost_usd = 0.0
            trace.cache_hit = True
            return cached
    headers = {
        "Authorization": f"Bearer {settings.EMBEDDINGS_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"input": text, "model": settings.EMBEDDINGS_MODEL}
    with observability.traced_call(
        "embed",
        model=settings.EMBEDDINGS_MODEL,
        check_llm_ceiling=True,
        estimated_cost_usd=observability.estimate_embedding_cost_usd(input_tokens=est_tokens),
    ) as trace:
        try:
            with httpx.Client(timeout=default_timeout()) as client:
                response = client.post(embeddings_endpoint(), headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            logger.warning("embeddings.http_error", error=type(exc).__name__)
            raise ServiceFailingError("Embeddings", "upstream request failed") from exc
        vec = _parse_single_embedding(data)
        usage = data.get("usage") if isinstance(data, dict) else None
        if isinstance(usage, dict) and usage.get("total_tokens") is not None:
            trace.input_tokens = int(usage["total_tokens"])
        else:
            trace.input_tokens = est_tokens
        trace.output_tokens = 0
        trace.cost_usd = observability.estimate_embedding_cost_usd(input_tokens=trace.input_tokens)
        trace.cache_hit = False
        _cache_put(key, vec)
        return vec
def embed_batch(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    for text in texts:
        if not text or not text.strip():
            raise ValueError("text must be non-empty")
    _require_embeddings_config()
    keys = [_cache_key(t) for t in texts]
    results: list[list[float] | None] = [None] * len(texts)
    miss_indices: list[int] = []
    for i, key in enumerate(keys):
        cached = _cache_get(key)
        if cached is not None:
            results[i] = cached
        else:
            miss_indices.append(i)
    hit_count = len(texts) - len(miss_indices)
    for _ in range(hit_count):
        with observability.traced_call("embed", model=settings.EMBEDDINGS_MODEL) as trace:
            trace.cache_hit = True
            trace.cost_usd = 0.0
            trace.input_tokens = 0
            trace.output_tokens = 0
    if not miss_indices:
        return [v for v in results if v is not None]
    miss_texts = [texts[i] for i in miss_indices]
    est_tokens = sum(observability.approx_token_count(t) for t in miss_texts)
    headers = {
        "Authorization": f"Bearer {settings.EMBEDDINGS_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"input": miss_texts, "model": settings.EMBEDDINGS_MODEL}
    with observability.traced_call(
        "embed",
        model=settings.EMBEDDINGS_MODEL,
        check_llm_ceiling=True,
        estimated_cost_usd=observability.estimate_embedding_cost_usd(input_tokens=est_tokens),
    ) as trace:
        try:
            with httpx.Client(timeout=embeddings_batch_timeout()) as client:
                response = client.post(embeddings_endpoint(), headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            logger.warning("embeddings.http_error", error=type(exc).__name__)
            raise ServiceFailingError("Embeddings", "upstream request failed") from exc
        if not isinstance(data, dict) or not isinstance(data.get("data"), list):
            raise ServiceFailingError("Embeddings", "unexpected response format")
        rows = sorted(data["data"], key=lambda item: item.get("index", 0))
        vectors: list[list[float]] = []
        for item in rows:
            if not isinstance(item, dict) or not isinstance(item.get("embedding"), list):
                raise ServiceFailingError("Embeddings", "unexpected response format")
            vectors.append(_normalize([float(x) for x in item["embedding"]]))
        if len(vectors) != len(miss_texts):
            raise ServiceFailingError("Embeddings", "embedding count mismatch")
        usage = data.get("usage") if isinstance(data, dict) else None
        if isinstance(usage, dict) and usage.get("total_tokens") is not None:
            trace.input_tokens = int(usage["total_tokens"])
        else:
            trace.input_tokens = est_tokens
        trace.output_tokens = 0
        trace.cost_usd = observability.estimate_embedding_cost_usd(input_tokens=trace.input_tokens)
        trace.cache_hit = False
        for idx, vec in zip(miss_indices, vectors, strict=True):
            results[idx] = vec
            _cache_put(keys[idx], vec)
    return [v for v in results if v is not None]
