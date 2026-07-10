"""Load versioned prompt templates from this package (YAML frontmatter + body)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_PROMPTS_DIR = Path(__file__).resolve().parent

@dataclass(frozen=True)
class PromptTemplate:
    """Loaded prompt with version metadata for tracing."""

    name: str
    version: str
    body: str
    content_hash: str
    model_params: dict[str, Any] = field(default_factory=dict)
    system: str | None = None

    def __str__(self) -> str:
        return self.body

def _parse_frontmatter(fm: str) -> dict[str, Any]:
    """Minimal YAML subset: scalar key: value lines (no nested blocks)."""
    data: dict[str, Any] = {}
    for line in fm.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            continue
        key, _, raw = stripped.partition(":")
        key = key.strip()
        value = raw.strip().strip('"').strip("'")
        if not key:
            continue
        if value.lower() in {"true", "false"}:
            data[key] = value.lower() == "true"
        else:
            try:
                if "." in value:
                    data[key] = float(value)
                else:
                    data[key] = int(value)
            except ValueError:
                data[key] = value
    return data

@lru_cache(maxsize=32)
def load_prompt(name: str) -> PromptTemplate:
    """Load `name.md` (or `name.txt`) with YAML frontmatter (name + version required)."""
    for ext in (".md", ".txt"):
        path = _PROMPTS_DIR / f"{name}{ext}"
        if path.is_file():
            break
    else:
        raise FileNotFoundError(f"prompt template not found: {name}")

    text = path.read_text(encoding="utf-8")
    m = _FRONTMATTER.match(text)
    if not m:
        raise ValueError(f"prompt {path.name} missing YAML frontmatter with name + version")
    meta = _parse_frontmatter(m.group(1))
    if "name" not in meta or "version" not in meta:
        raise ValueError(f"prompt {path.name} frontmatter must include name and version")
    body = text[m.end() :]
    content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
    model_params: dict[str, Any] = {}
    for key in ("temperature", "max_tokens", "top_p"):
        if key in meta:
            model_params[key] = meta[key]
    system = meta.get("system")
    if system is not None:
        system = str(system)
    return PromptTemplate(
        name=str(meta["name"]),
        version=str(meta["version"]),
        body=body,
        content_hash=content_hash,
        model_params=model_params,
        system=system,
    )

def prompt_versions() -> dict[str, str]:
    """Map prompt name → version for eval history records."""
    out: dict[str, str] = {}
    for path in sorted(_PROMPTS_DIR.glob("*.md")):
        try:
            tmpl = load_prompt(path.stem)
        except (OSError, ValueError, FileNotFoundError):
            continue
        out[tmpl.name] = tmpl.version
    return out
