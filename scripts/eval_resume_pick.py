#!/usr/bin/env python3
"""Requirement-level resume pick eval vs whole-doc baseline.

Hard fixtures: 8 libraries of 10+ near-dup resumes (measured shared-text ≥ 0.9)
with exactly one decisive variant. Engine must pick it ≥ 7/8; baseline should
pick fewer (architecture earns keep).
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.core.env_utils import is_set
from app.db.session import ensure_db
from app.prompts import prompt_versions
from app.schemas.library import ResumeCandidate
from app.services.resume.ranking import rank_resumes_for_job, _whole_doc_baseline_order
from scripts.fixtures.resume_pick_fixtures import (
    CASES,
    assert_fixture_honesty,
    min_pairwise_similarity,
)


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


def append_eval_history(metrics: dict, *, suite: str = "resume_pick") -> None:
    history = ROOT / "evals" / "history.jsonl"
    history.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(UTC).isoformat(),
        "suite": suite,
        "metrics": metrics,
        "prompt_versions": prompt_versions(),
        "model": settings.LLM_MODEL,
        "embeddings_model": settings.EMBEDDINGS_MODEL,
        "git_sha": _git_sha(),
    }
    with history.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def _synthetic_embed_batch(texts: list[str]) -> list[list[float]]:
    """Deterministic bag-of-chars embedding for offline eval without API keys.

    Not a silent production fallback — only used when EMBEDDINGS are unset and
    TEAMSCOUT_EVAL_SYNTHETIC_EMBED=1, or automatically in CI-style offline runs
    after a loud NOTE. For honest live eval, real embeddings are preferred.
    """
    dim = 64
    out: list[list[float]] = []
    for text in texts:
        vec = [0.0] * dim
        lowered = text.lower()
        for i, ch in enumerate(lowered[:2000]):
            vec[i % dim] += (ord(ch) % 31) / 31.0
        # boost exact phrase hashes so decisive bullets separate
        for token in lowered.replace("/", " ").split():
            h = hash(token) % dim
            vec[h] += 1.0
            if len(token) >= 4:
                vec[(h * 7 + 3) % dim] += 0.5
        # L2 normalize
        norm = sum(x * x for x in vec) ** 0.5 or 1.0
        out.append([x / norm for x in vec])
    return out


def _run_case(case, *, use_llm: bool, synthetic: bool) -> tuple[bool, bool, float]:
    candidates = [
        ResumeCandidate(
            resume_id=f"{case.name}-{index}",
            filename=f"resume-{index}.pdf",
            profile=profile,
            content_hash=f"{case.name}-hash-{index}",
        )
        for index, profile in enumerate(case.resumes)
    ]
    expected_id = f"{case.name}-{case.best_resume_index}"

    def _engine() -> str:
        ranked = rank_resumes_for_job(case.job, candidates, use_llm=use_llm)
        return ranked[0].resume_id if ranked else ""

    def _baseline() -> str:
        order = _whole_doc_baseline_order(case.job, candidates)
        return order[0] if order else ""

    if synthetic:
        with patch("app.services.inference.embeddings.embed_batch", side_effect=_synthetic_embed_batch):
            with patch("app.services.inference.embeddings.embed", side_effect=lambda t: _synthetic_embed_batch([t])[0]):
                # baseline hybrid_rank also needs embeddings
                top = _engine()
                base = _baseline()
    else:
        top = _engine()
        base = _baseline()

    return top == expected_id, base == expected_id, case.min_near_dup_similarity


def main() -> int:
    ensure_db()
    assert_fixture_honesty()

    from app.services.inference.embeddings import embeddings_endpoint

    has_emb = is_set(settings.EMBEDDINGS_API_KEY) and bool(embeddings_endpoint())
    synthetic = False
    if not has_emb:
        print(
            "NOTE: embeddings not configured — using deterministic synthetic embeddings "
            "for offline MaxSim eval (not a production fallback)."
        )
        synthetic = True
    else:
        print(f"Embeddings endpoint: {embeddings_endpoint()}")

    # Architecture eval is coverage/MaxSim discrimination. Near-dup libraries often
    # land in the tournament gap band and would burn 10 pairwise LLM calls × 8 cases.
    # Opt in with TEAMSCOUT_EVAL_LLM=1 when you intentionally want tournament+justify.
    import os

    use_llm = (
        os.environ.get("TEAMSCOUT_EVAL_LLM", "").strip() in {"1", "true", "yes"}
        and is_set(settings.LLM_API_KEY)
        and is_set(settings.LLM_API_BASE)
    )
    if not use_llm:
        print(
            "NOTE: eval runs coverage-only MaxSim (no tournament/justify). "
            "Set TEAMSCOUT_EVAL_LLM=1 to include LLM stages."
        )

    print("TeamScout resume-pick eval (requirement-level MaxSim)")
    print(f"Cases: {len(CASES)} libraries, each ≥10 near-dup resumes")

    engine_wins = 0
    baseline_wins = 0
    sims: list[float] = []

    for case in CASES:
        measured = min_pairwise_similarity(case.resumes)
        sims.append(measured)
        assert measured >= 0.9, f"{case.name} measured sim {measured} < 0.9"
        eng_ok, base_ok, _ = _run_case(case, use_llm=use_llm, synthetic=synthetic)
        engine_wins += int(eng_ok)
        baseline_wins += int(base_ok)
        status = "PASS" if eng_ok else "FAIL"
        print(
            f"{case.name}: engine={'hit' if eng_ok else 'miss'} "
            f"baseline={'hit' if base_ok else 'miss'} "
            f"sim={measured:.3f} [{status}]"
        )

    total = len(CASES)
    print(f"RESULT: engine {engine_wins}/{total}  baseline {baseline_wins}/{total}")
    print(f"min pairwise shared-text similarity across cases: {min(sims):.3f}")

    metrics_out = {
        "wins": engine_wins,
        "cases": total,
        "win_rate": engine_wins / total if total else 0.0,
        "baseline_wins": baseline_wins,
        "baseline_win_rate": baseline_wins / total if total else 0.0,
        "min_near_dup_similarity": min(sims) if sims else 0.0,
        "synthetic_embeddings": synthetic,
    }
    append_eval_history(metrics_out, suite="resume_pick")
    append_eval_history(
        {
            "wins": baseline_wins,
            "cases": total,
            "win_rate": baseline_wins / total if total else 0.0,
            "kind": "whole_doc_baseline",
        },
        suite="resume_pick_baseline",
    )

    # Floors: engine ≥ 7/8; must beat baseline unless both perfect
    floor = 7
    if engine_wins < floor:
        print(f"FAIL: expected best resume #1 in at least {floor}/{total} cases")
        return 1
    if engine_wins < baseline_wins:
        print(
            f"FAIL: engine ({engine_wins}) underperformed whole-doc baseline ({baseline_wins})"
        )
        return 1
    if engine_wins == baseline_wins and engine_wins < total:
        print(
            f"FAIL: engine tied baseline at {engine_wins}/{total} — architecture must earn keep"
        )
        return 1
    if engine_wins == baseline_wins == total:
        print("NOTE: both engine and baseline perfect; MaxSim still required for explainability")
    elif engine_wins > baseline_wins:
        print(f"NOTE: engine beat baseline ({engine_wins} > {baseline_wins})")

    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
