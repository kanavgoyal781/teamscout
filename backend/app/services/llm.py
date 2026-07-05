import json
import re
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError as PydanticValidationError

from app.core.config import settings
from app.core.env_utils import is_set
from app.errors import ServiceFailingError, ServiceNotConfiguredError

T = TypeVar("T", bound=BaseModel)


def _require_llm_config() -> None:
    if not is_set(settings.LLM_API_KEY):
        raise ServiceNotConfiguredError("LLM", "LLM_API_KEY")
    if not is_set(settings.LLM_API_BASE):
        raise ServiceNotConfiguredError("LLM", "LLM_API_BASE")


def complete(
    prompt: str,
    *,
    system: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 2048,
) -> str:
    _require_llm_config()

    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    headers = {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": settings.LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                f"{settings.LLM_API_BASE.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        raise ServiceFailingError("LLM", str(exc)) from exc

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ServiceFailingError("LLM", "unexpected response format") from exc


def _extract_json(raw: str) -> str:
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if fenced:
        return fenced.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def complete_json(
    prompt: str,
    model: type[T],
    *,
    system: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 4096,
    max_retries: int = 1,
) -> T:
    base_system = system or "Return valid JSON only. No markdown or commentary."
    current_prompt = prompt
    last_error = "invalid JSON"

    for attempt in range(max_retries + 1):
        raw = complete(
            current_prompt,
            system=base_system,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        try:
            payload = json.loads(_extract_json(raw))
            return model.model_validate(payload)
        except (json.JSONDecodeError, PydanticValidationError) as exc:
            last_error = str(exc)
            if attempt >= max_retries:
                break
            current_prompt = (
                f"{prompt}\n\nPrevious response was invalid ({last_error}). "
                "Return JSON that matches the schema exactly."
            )

    raise ServiceFailingError("LLM", f"invalid JSON schema: {last_error}")