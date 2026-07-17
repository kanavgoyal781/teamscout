#!/usr/bin/env python3
"""Offline fit-signal eval: experience + requirements (no embeddings / LLM).

Ranks jobs with fuse_final_score using zeroed llm/rrf so pure signal quality is measured.
Enforces floors from evals/thresholds.json for experience_order_accuracy and
requirements_order_accuracy (and optional overqualified_penalty_rate).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(ROOT))

from app.core.config import settings  # noqa: E402
from app.services.ranking.math import (  # noqa: E402
    experience_fit_score,
    fuse_final_score,
    recency_score,
    requirements_met_score,
    skill_jaccard,
)
from scripts.fixtures.ranking_fixtures import PERSONAS  # noqa: E402



def _load_thresholds() -> dict:
    path = ROOT / "evals" / "thresholds.json"
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def rank_by_fit_signals(persona) -> list[tuple[str, float, float]]:
    """Return (job_id, final_score, label_relevance) sorted by final_score desc."""
    profile = persona.profile
    profile_text = profile.search_text()
    scored: list[tuple[str, float, float]] = []
    for labeled in persona.jobs:
        job = labeled.job
        skill = skill_jaccard(profile.skills, job.skills)
        exp = experience_fit_score(
            profile.years_of_experience,
            title=job.title,
            description=job.description,
        )
        req = requirements_met_score(
            profile_skills=profile.skills,
            profile_text=profile_text,
            job_skills=job.skills,
            job_description=job.description,
        )
        rec = recency_score(job.posted_at)
        # llm/rrf zeroed — isolates experience + requirements (+ skills/recency policy weights)
        final = fuse_final_score(
            llm_fit=0.0,
            rrf_normalized=0.0,
            skill_overlap=skill,
            recency=rec,
            experience_fit=exp,
            requirements_met=req,
        )
        scored.append((job.id, final, labeled.relevance))
    scored.sort(key=lambda row: row[1], reverse=True)
    return scored


def experience_order_accuracy(ranked: list[tuple[str, float, float]]) -> float:
    """Pairwise: among pairs where labels differ, higher label should rank higher."""
    correct = 0
    total = 0
    for i, (_id_a, _sa, rel_a) in enumerate(ranked):
        for _id_b, _sb, rel_b in ranked[i + 1 :]:
            if rel_a == rel_b:
                continue
            total += 1
            # ranked is score-desc; i is already above j
            if rel_a > rel_b:
                correct += 1
    return 1.0 if total == 0 else correct / total


def overqualified_penalty_rate(persona, ranked: list[tuple[str, float, float]]) -> float:
    """Staff/principal/director labeled 0 should land in bottom half for mid candidates."""
    n = len(ranked)
    if n == 0:
        return 1.0
    half = n // 2
    bottom_ids = {job_id for job_id, _s, _r in ranked[half:]}
    trap_ids = {
        labeled.job.id
        for labeled in persona.jobs
        if labeled.relevance <= 0.0
        and any(
            token in labeled.job.title.lower()
            for token in ("staff", "principal", "director")
        )
    }
    if not trap_ids:
        return 1.0
    hit = sum(1 for tid in trap_ids if tid in bottom_ids)
    return hit / len(trap_ids)


def requirements_order_accuracy(persona) -> float:
    """Jobs with high requirements_met should beat low-coverage same-title traps when labeled higher."""
    profile = persona.profile
    profile_text = profile.search_text()
    good = []
    bad = []
    for labeled in persona.jobs:
        job = labeled.job
        req = requirements_met_score(
            profile_skills=profile.skills,
            profile_text=profile_text,
            job_skills=job.skills,
            job_description=job.description,
        )
        if labeled.relevance >= 2.5:
            good.append(req)
        if labeled.relevance <= 0.0 and "software engineer" in job.title.lower():
            bad.append(req)
    if not good or not bad:
        # fallback: mean req of high labels > mean req of zero labels
        high = [
            requirements_met_score(
                profile_skills=profile.skills,
                profile_text=profile_text,
                job_skills=j.job.skills,
                job_description=j.job.description,
            )
            for j in persona.jobs
            if j.relevance >= 2.5
        ]
        low = [
            requirements_met_score(
                profile_skills=profile.skills,
                profile_text=profile_text,
                job_skills=j.job.skills,
                job_description=j.job.description,
            )
            for j in persona.jobs
            if j.relevance <= 0.0
        ]
        if not high or not low:
            return 1.0
        return 1.0 if (sum(high) / len(high)) > (sum(low) / len(low)) else 0.0
    return 1.0 if (sum(good) / len(good)) > (sum(bad) / len(bad)) else 0.0


def main() -> int:
    thresholds = _load_thresholds()
    floor_exp = float(thresholds.get("experience_order_accuracy", 0.85))
    floor_req = float(thresholds.get("requirements_order_accuracy", 0.85))
    floor_over = float(thresholds.get("overqualified_penalty_rate", 0.8))

    print("TeamScout fit-signal eval (no embeddings)")
    print(
        f"weights: llm={settings.RANKING_WEIGHT_LLM} rrf={settings.RANKING_WEIGHT_RRF} "
        f"skills={settings.RANKING_WEIGHT_SKILLS} recency={settings.RANKING_WEIGHT_RECENCY} "
        f"exp={settings.RANKING_WEIGHT_EXPERIENCE} req={settings.RANKING_WEIGHT_REQUIREMENTS}"
    )

    exp_scores: list[float] = []
    req_scores: list[float] = []
    over_scores: list[float] = []

    for persona in PERSONAS:
        ranked = rank_by_fit_signals(persona)
        exp_acc = experience_order_accuracy(ranked)
        req_acc = requirements_order_accuracy(persona)
        over = overqualified_penalty_rate(persona, ranked)
        exp_scores.append(exp_acc)
        req_scores.append(req_acc)
        over_scores.append(over)
        top3 = ", ".join(f"{jid}({rel:g})" for jid, _s, rel in ranked[:3])
        print(
            f"{persona.name}: exp_order={exp_acc:.3f} req_order={req_acc:.3f} "
            f"overqual_penalty={over:.3f} | top3={top3}"
        )

    avg_exp = sum(exp_scores) / len(exp_scores)
    avg_req = sum(req_scores) / len(req_scores)
    avg_over = sum(over_scores) / len(over_scores)
    print(
        f"OVERALL: experience_order={avg_exp:.4f} requirements_order={avg_req:.4f} "
        f"overqualified_penalty={avg_over:.4f}"
    )

    # Append history
    history = ROOT / "evals" / "history.jsonl"
    history.parent.mkdir(parents=True, exist_ok=True)
    from datetime import UTC, datetime

    record = {
        "ts": datetime.now(UTC).isoformat(),
        "suite": "fit_signals",
        "metrics": {
            "experience_order_accuracy": avg_exp,
            "requirements_order_accuracy": avg_req,
            "overqualified_penalty_rate": avg_over,
        },
    }
    with history.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")

    failures: list[str] = []
    if avg_exp < floor_exp:
        failures.append(f"experience_order_accuracy {avg_exp:.4f} < {floor_exp}")
    if avg_req < floor_req:
        failures.append(f"requirements_order_accuracy {avg_req:.4f} < {floor_req}")
    if avg_over < floor_over:
        failures.append(f"overqualified_penalty_rate {avg_over:.4f} < {floor_over}")

    if failures:
        print("FAIL:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
