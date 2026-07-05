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
from app.schemas.library import ResumeCandidate
from app.services.resume_ranking import rank_resumes_for_job
from scripts.fixtures.resume_pick_fixtures import CASES


def main() -> int:
    if not is_set(settings.EMBEDDINGS_API_KEY) or not is_set(settings.EMBEDDINGS_API):
        print("SKIP: embeddings not configured — set EMBEDDINGS_API_KEY and EMBEDDINGS_API to run eval")
        return 0

    if not is_set(settings.LLM_API_KEY) or not is_set(settings.LLM_API_BASE):
        print("NOTE: LLM not configured — eval runs retrieval-only resume ranking")

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
    if wins < 4:
        print("FAIL: expected best resume #1 in at least 4 of 5 cases")
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())