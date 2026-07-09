#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.core.env_utils import is_set
from app.db.session import ensure_db
from app.schemas.library import ResumeCandidate
from app.services.resume_ranking import rank_resumes_for_job
from scripts.fixtures.resume_pick_fixtures import CASES


import json
import subprocess
from datetime import UTC, datetime

from app.prompts import prompt_versions


def _git_sha() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return settings.GIT_SHA or "unknown"


def append_eval_history(metrics: dict) -> None:
    history = ROOT / "evals" / "history.jsonl"
    history.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(UTC).isoformat(),
        "suite": "resume_pick",
        "metrics": metrics,
        "prompt_versions": prompt_versions(),
        "model": settings.LLM_MODEL,
        "embeddings_model": settings.EMBEDDINGS_MODEL,
        "git_sha": _git_sha(),
    }
    with history.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")



def main() -> int:
    ensure_db()

    from app.services.embeddings import embeddings_endpoint

    if not is_set(settings.EMBEDDINGS_API_KEY) or not embeddings_endpoint():
        print(
            "SKIP: embeddings not configured — set EMBEDDINGS_API_KEY and "
            "EMBEDDINGS_API (or LLM_API_BASE) to run eval"
        )
        return 0

    if not is_set(settings.LLM_API_KEY) or not is_set(settings.LLM_API_BASE):
        print("NOTE: LLM not configured — eval runs retrieval-only resume ranking")

    print(f"Embeddings endpoint: {embeddings_endpoint()}")

    wins = 0
    print("TeamScout resume-pick eval")
    for case in CASES:
        candidates = [
            ResumeCandidate(
                resume_id=f"{case.name}-{index}",
                filename=f"resume-{index}.pdf",
                profile=profile,
            )
            for index, profile in enumerate(case.resumes)
        ]
        use_llm = is_set(settings.LLM_API_KEY) and is_set(settings.LLM_API_BASE)
        ranked = rank_resumes_for_job(case.job, candidates, use_llm=use_llm)
        top_id = ranked[0].resume_id if ranked else ""
        expected_id = f"{case.name}-{case.best_resume_index}"
        passed = top_id == expected_id
        wins += int(passed)
        status = "PASS" if passed else "FAIL"
        print(
            f"{case.name}: top={top_id} expected={expected_id} score={ranked[0].match_score if ranked else 0:.1f} [{status}]"
        )

    print(f"RESULT: best resume ranked #1 in {wins}/{len(CASES)} cases")
    metrics_out = {
        "wins": wins,
        "cases": len(CASES),
        "win_rate": wins / len(CASES) if CASES else 0.0,
    }
    append_eval_history(metrics_out)
    if wins < 4:
        print("FAIL: expected best resume #1 in at least 4 of 5 cases")
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())