import json
import re
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from app.core.config import settings
from app.core.env_utils import is_set
from app.core.http_timeouts import default_timeout
from app.errors import ServiceFailingError, ServiceNotConfiguredError
from app.prompts import PromptTemplate
from app.services import observability

T = TypeVar("T", bound=BaseModel)


def _require_llm_config() -> None:
    if not is_set(settings.LLM_API_KEY):
        raise ServiceNotConfiguredError("LLM", "LLM_API_KEY")
    if not is_set(settings.LLM_API_BASE):
        raise ServiceNotConfiguredError("LLM", "LLM_API_BASE")


def _extract_message_text(message: object) -> str:
    """Pull assistant text from OpenAI-compatible chat payloads.

    Some hosted models (e.g. MiniMax on Friendli) put interim text in
    reasoning_content and leave content null when max_tokens is tight.
    """
    if not isinstance(message, dict):
        raise ServiceFailingError("LLM", "unexpected response format")

    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str) and part.strip():
                parts.append(part)
            elif isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text)
        if parts:
            return "".join(parts)

    # Fallback: reasoning-only / truncated outputs
    for key in ("reasoning_content", "reasoning", "text"):
        val = message.get(key)
        if isinstance(val, str) and val.strip():
            return val

    raise ServiceFailingError("LLM", "unexpected response format: empty message content")


def complete(
    prompt: str,
    *,
    system: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 2048,
    operation: str = "llm",
    prompt_meta: PromptTemplate | None = None,
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

    est_in = observability.approx_token_count((system or "") + prompt)
    with observability.traced_call(
        operation,
        model=settings.LLM_MODEL,
        prompt_name=prompt_meta.name if prompt_meta else None,
        prompt_version=prompt_meta.version if prompt_meta else None,
        prompt_hash=prompt_meta.content_hash if prompt_meta else None,
        check_llm_ceiling=True,
        # Fail-closed preflight: charge worst-case output = full max_tokens budget
        # (not max_tokens//4) so remaining budget cannot be overshot by ~4×.
        estimated_cost_usd=observability.estimate_llm_cost_usd(
            model=settings.LLM_MODEL, input_tokens=est_in, output_tokens=max_tokens
        ),
    ) as trace:
        try:
            with httpx.Client(timeout=default_timeout()) as client:
                response = client.post(
                    f"{(settings.LLM_API_BASE or '').rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise ServiceFailingError("LLM", str(exc)) from exc

        try:
            message = data["choices"][0]["message"]
            content = _extract_message_text(message)
        except (KeyError, IndexError, TypeError) as exc:
            raise ServiceFailingError("LLM", "unexpected response format") from exc

        usage = data.get("usage") if isinstance(data, dict) else None
        if isinstance(usage, dict):
            trace.input_tokens = int(usage.get("prompt_tokens") or est_in)
            trace.output_tokens = int(
                usage.get("completion_tokens") or observability.approx_token_count(content)
            )
        else:
            trace.input_tokens = est_in
            trace.output_tokens = observability.approx_token_count(content)
        trace.cost_usd = observability.estimate_llm_cost_usd(
            model=settings.LLM_MODEL,
            input_tokens=trace.input_tokens,
            output_tokens=trace.output_tokens,
        )
        return content


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
    max_tokens: int | None = None,
    max_retries: int = 1,
    operation: str = "llm",
    prompt_meta: PromptTemplate | None = None,
) -> T:
    base_system = system or "Return valid JSON only. No markdown or commentary."
    budget = max_tokens if max_tokens is not None else settings.max_tokens_for_operation(operation)
    current_prompt = prompt
    last_error = "invalid JSON"

    for attempt in range(max_retries + 1):
        raw = complete(
            current_prompt,
            system=base_system,
            temperature=temperature,
            max_tokens=budget,
            operation=operation,
            prompt_meta=prompt_meta,
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
