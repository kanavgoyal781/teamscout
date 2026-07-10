#!/usr/bin/env python3
"""Pure threshold gate used by weekly-eval (and unit tests). Observe-only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def check_ranking_thresholds(
    history_path: Path,
    floors: dict[str, Any],
) -> list[str]:
    """Return list of breach messages for latest ranking suite row (empty = pass)."""
    if not history_path.is_file():
        return []
    ranking: list[dict] = []
    for line in history_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (row.get("suite") or "") == "ranking":
            ranking.append(row)
    if not ranking:
        return []
    m = ranking[-1].get("metrics") or {}
    failed: list[str] = []
    try:
        ndcg = float(m.get("hybrid_ndcg10") or 0)
        mrr = float(m.get("hybrid_mrr") or 0)
    except (TypeError, ValueError):
        return ["ranking metrics unreadable"]
    ndcg_floor = float(floors.get("ndcg_at_10", 0.85))
    mrr_floor = float(floors.get("mrr", 0.8))
    if ndcg < ndcg_floor:
        failed.append(f"hybrid_ndcg10 {ndcg} < {ndcg_floor}")
    if mrr < mrr_floor:
        failed.append(f"hybrid_mrr {mrr} < {mrr_floor}")
    return failed


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    floors = json.loads((root / "evals" / "thresholds.json").read_text(encoding="utf-8"))
    failed = check_ranking_thresholds(root / "evals" / "history.jsonl", floors)
    if failed:
        for f in failed:
            print(f"THRESHOLD BREACH: {f}")
        return 1
    print("PASS: weekly threshold check (or no ranking history to gate)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
