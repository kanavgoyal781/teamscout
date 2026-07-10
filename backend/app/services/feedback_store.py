"""Persist ranking feedback + aggregate counts for ops (no auto weight mutation)."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.env_utils import is_set
from app.db.models import Feedback
from app.prompts import prompt_versions
from app.schemas.feedback import FeedbackCreate

def current_ranking_config_hash() -> str:
    from app.services.ranking_config import ranking_config_hash

    return ranking_config_hash()
def resolve_evals_root() -> Path:
    """Locate directory that contains evals/ (monorepo, Docker /app, /data, EVALS_DIR)."""
    if is_set(getattr(settings, "EVALS_DIR", None)):
        return Path(str(settings.EVALS_DIR)).expanduser().resolve()
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "evals" / "thresholds.json").is_file() or (parent / "evals" / "history.jsonl").is_file():
            return parent
        if parent == parent.parent:
            break
    for candidate in (Path("/app"), Path("/data"), Path.cwd()):
        if (candidate / "evals").is_dir():
            return candidate.resolve()
    return Path.cwd().resolve()
def record_feedback(db: Session, payload: FeedbackCreate) -> Feedback:
    row = Feedback(
        kind=payload.kind,
        target_type=payload.target_type,
        target_id=payload.target_id,
        secondary_id=payload.secondary_id,
        profile_hash=payload.profile_hash,
        jd_hash=payload.jd_hash,
        score_shown=payload.score_shown,
        prompt_versions_json=json.dumps(prompt_versions(), sort_keys=True),
        model=settings.LLM_MODEL,
        embeddings_model=settings.EMBEDDINGS_MODEL,
        git_sha=settings.GIT_SHA or settings.APP_VERSION,
        ranking_config_hash=current_ranking_config_hash(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
def feedback_label_counts(db: Session) -> dict[str, int]:
    rows = db.query(Feedback.kind).all()
    counts = Counter(str(r[0]) for r in rows)
    return {
        "total": sum(counts.values()),
        "thumbs_up": counts.get("thumbs_up", 0),
        "thumbs_down": counts.get("thumbs_down", 0),
        "apply_click": counts.get("apply_click", 0),
        "find_team_click": counts.get("find_team_click", 0),
        "compose_opened": counts.get("compose_opened", 0),
    }
def learning_file_stats(repo_root: Path | str | None = None) -> dict[str, Any]:
    """Latest eval metrics, trends, last experiments from evals/ on disk."""
    root = Path(repo_root) if repo_root is not None else resolve_evals_root()
    by_suite: dict[str, list[dict]] = {}
    history = root / "evals" / "history.jsonl"
    if history.is_file():
        for line in history.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            by_suite.setdefault(str(row.get("suite") or "unknown"), []).append(row)

    latest: list[dict[str, Any]] = []
    for suite, rows in sorted(by_suite.items()):
        if not rows:
            continue
        last, prev = rows[-1], (rows[-2] if len(rows) >= 2 else None)
        metrics, prev_m = last.get("metrics") or {}, (prev or {}).get("metrics") or {}
        trends = {}
        for key in sorted(set(metrics) | set(prev_m)):
            try:
                a = float(prev_m[key]) if prev and key in prev_m else None
                b = float(metrics[key]) if key in metrics else None
            except (TypeError, ValueError):
                continue
            trends[key] = {
                "current": b,
                "previous": a,
                "delta": None if a is None or b is None else round(b - a, 4),
            }
        latest.append(
            {"suite": suite, "ts": last.get("ts"), "git_sha": last.get("git_sha"), "metrics": metrics, "trend": trends}
        )

    exp_rows: list[dict[str, Any]] = []
    experiments = root / "evals" / "experiments.jsonl"
    if experiments.is_file():
        for line in experiments.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                exp_rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return {
        "evals_root": str(root),
        "suites": latest,
        "experiments": exp_rows[-20:],
        "note": "Offline metrics only; feedback suite is score-separation not re-rank NDCG; weekly CI does not pull prod SQLite.",
    }
