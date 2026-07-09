#!/usr/bin/env python3
"""Print eval regression trends from evals/history.jsonl."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "evals" / "history.jsonl"


def main() -> int:
    if not HISTORY.is_file():
        print(f"No history at {HISTORY} — run eval_ranking.py / eval_resume_pick.py first")
        return 0

    by_suite: dict[str, list[dict]] = defaultdict(list)
    for line in HISTORY.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        suite = str(row.get("suite") or "unknown")
        by_suite[suite].append(row)

    if not by_suite:
        print("History empty")
        return 0

    for suite, rows in sorted(by_suite.items()):
        print(f"== {suite} ({len(rows)} runs) ==")
        # show last 10
        for row in rows[-10:]:
            ts = row.get("ts", "?")
            sha = row.get("git_sha", "?")
            model = row.get("model", "?")
            metrics = row.get("metrics") or {}
            prompts = row.get("prompt_versions") or {}
            metric_s = " ".join(f"{k}={v}" for k, v in metrics.items())
            prompt_s = ",".join(f"{k}:{v}" for k, v in sorted(prompts.items()))
            print(f"  {ts} sha={sha} model={model} {metric_s} prompts=[{prompt_s}]")
        if len(rows) >= 2:
            prev_m = rows[-2].get("metrics") or {}
            last_m = rows[-1].get("metrics") or {}
            for key in sorted(set(prev_m) | set(last_m)):
                try:
                    a = float(prev_m.get(key, 0))
                    b = float(last_m.get(key, 0))
                except (TypeError, ValueError):
                    continue
                delta = b - a
                print(f"  trend {key}: {a} -> {b} (delta {delta:+.4f})")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
