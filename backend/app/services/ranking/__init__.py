"""ranking domain package (lazy attribute export from engine)."""
from __future__ import annotations
import importlib
from typing import Any

def __getattr__(name: str) -> Any:
    if name in {"hybrid", "math", "math_align", "config", "calibration", "cross_encoder", "listwise", "query_expand", "engine"}:
        return importlib.import_module(f"app.services.ranking.{name}")
    engine = importlib.import_module("app.services.ranking.engine")
    return getattr(engine, name)
