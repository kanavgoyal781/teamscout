import math

import httpx

from app.core.config import settings
from app.core.env_utils import is_set
from app.errors import ServiceFailingError, ServiceNotConfiguredError


def _require_embeddings_config() -> None:
    if not is_set(settings.EMBEDDINGS_API_KEY):
        raise ServiceNotConfiguredError("Embeddings", "EMBEDDINGS_API_KEY")
    if not is_set(settings.EMBEDDINGS_API):
        raise ServiceNotConfiguredError("Embeddings", "EMBEDDINGS_API")


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def embed(text: str) -> list[float]:
    if not text or not text.strip():
        raise ValueError("text must be non-empty")

    _require_embeddings_config()

    headers = {
        "Authorization": f"Bearer {settings.EMBEDDINGS_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"input": text, "model": settings.EMBEDDINGS_MODEL}

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(settings.EMBEDDINGS_API, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        raise ServiceFailingError("Embeddings", str(exc)) from exc

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


def embed_batch(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    for text in texts:
        if not text or not text.strip():
            raise ValueError("text must be non-empty")

    _require_embeddings_config()

    headers = {
        "Authorization": f"Bearer {settings.EMBEDDINGS_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"input": texts, "model": settings.EMBEDDINGS_MODEL}

    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(settings.EMBEDDINGS_API, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        raise ServiceFailingError("Embeddings", str(exc)) from exc

    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        raise ServiceFailingError("Embeddings", "unexpected response format")

    rows = sorted(data["data"], key=lambda item: item.get("index", 0))
    vectors: list[list[float]] = []
    for item in rows:
        if not isinstance(item, dict) or not isinstance(item.get("embedding"), list):
            raise ServiceFailingError("Embeddings", "unexpected response format")
        vectors.append(_normalize([float(x) for x in item["embedding"]]))

    if len(vectors) != len(texts):
        raise ServiceFailingError("Embeddings", "embedding count mismatch")

    return vectors