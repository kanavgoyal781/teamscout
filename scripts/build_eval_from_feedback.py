#!/usr/bin/env python3
"""Build evals/feedback_set.jsonl from SQLite feedback rows (observe-only).

Mapping:
  thumbs_up      → relevance 2.0 (relevant)
  thumbs_down    → relevance 0.0 (irrelevant)
  apply_click    → relevance 3.0 (strong positive)
  find_team_click → relevance 2.5 (positive intent; not used as hard label alone)

Provenance (prompt_versions, model, score_shown, git_sha, hashes) is preserved
for real labels later. No production ranking mutation.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(ROOT))

from app.db.models import Feedback  # noqa: E402
from app.db.session import SessionLocal, ensure_db  # noqa: E402

OUT = ROOT / "evals" / "feedback_set.jsonl"

KIND_RELEVANCE = {
    "thumbs_up": 2.0,
    "thumbs_down": 0.0,
    "apply_click": 3.0,
    "find_team_click": 2.5,
}


def _row_to_label(row: Feedback) -> dict | None:
    if row.kind not in KIND_RELEVANCE:
        return None
    if row.kind == "find_team_click":
        # implicit positive but not a primary label for binary eval unless paired
        pass
    return {
        "ts": row.created_at.isoformat() if row.created_at else datetime.now(UTC).isoformat(),
        "kind": row.kind,
        "relevance": KIND_RELEVANCE[row.kind],
        "target_type": row.target_type,
        "target_id": row.target_id,
        "secondary_id": row.secondary_id,
        "profile_hash": row.profile_hash,
        "jd_hash": row.jd_hash,
        "score_shown": row.score_shown,
        "prompt_versions": json.loads(row.prompt_versions_json)
        if row.prompt_versions_json
        else {},
        "model": row.model,
        "embeddings_model": row.embeddings_model,
        "git_sha": row.git_sha,
        "ranking_config_hash": getattr(row, "ranking_config_hash", None),
        "feedback_id": row.id,
    }


def build(out_path: Path = OUT) -> int:
    ensure_db()
    db = SessionLocal()
    try:
        rows = db.query(Feedback).order_by(Feedback.created_at.asc()).all()
    finally:
        db.close()

    labels: list[dict] = []
    for row in rows:
        item = _row_to_label(row)
        if item is not None:
            labels.append(item)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for item in labels:
            fh.write(json.dumps(item, sort_keys=True) + "\n")

    print(f"wrote {len(labels)} labels → {out_path}")
    by_kind: dict[str, int] = {}
    for item in labels:
        by_kind[item["kind"]] = by_kind.get(item["kind"], 0) + 1
    for k, v in sorted(by_kind.items()):
        print(f"  {k}: {v}")
    return len(labels)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=OUT,
        help="Output JSONL path (default: evals/feedback_set.jsonl)",
    )
    args = parser.parse_args()
    build(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
