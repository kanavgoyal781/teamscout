from __future__ import annotations
from typing import Literal
from collections import defaultdict
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.env_utils import is_set
from app.core.logging import get_logger
from app.schemas.job_metadata import JobMetadata
from app.schemas.jobs import Job, ScoreBreakdown
from app.schemas.library import (
    AlignmentRow,
    RankedResumeRecommendation,
    RequirementCoverage,
    ResumeCandidate,
    TournamentRecord,
)
from app.schemas.resume import ResumeProfile
from app.services import embeddings
from app.services.resume.jd_decompose import decompose_jd
from app.services.resume.tournament import AlignmentEvidence, agreement_label, maybe_run_tournament
from app.services.ranking.math import skill_jaccard
from app.services.ranking.math_align import (
    align_resume,
    cluster_variant_label,
    evidence_strength,
    single_linkage_clusters,
    under_segmented_units,
)
from app.services.resume.justify import (
    ResumeRerankItem as _ResumeRerankItem, ResumeRerankResponse as _ResumeRerankResponse,
    evidence_units_from_alignment, llm_justify, rationale_cites_units,
    rationale_rank_consistent, rationale_references_resume,
)
from app.services.resume.units import ensure_candidate_units
logger = get_logger(__name__)
def _row_strength(r: dict) -> Literal["none", "weak", "solid", "strong"]:
    if r.get("status") == "miss": return "none"
    s = r.get("strength")
    if s in ("none", "weak", "solid", "strong"): return s  # type: ignore[return-value]
    return evidence_strength(float(r.get("evidence_score") or 0.0))  # type: ignore[return-value]

_rationale_cites_units, _rationale_references_resume = rationale_cites_units, rationale_references_resume
_rationale_rank_consistent, _llm_justify, _llm_rerank = rationale_rank_consistent, llm_justify, llm_justify
_ = (_ResumeRerankItem, _ResumeRerankResponse)
def _whole_doc_baseline_order(job: Job, candidates: list[ResumeCandidate]) -> list[str]:
    from app.services.ranking.math import cosine_similarity
    query = "\n".join(
        p for p in [job.title, job.company, ", ".join(job.skills), job.description[:2000]] if p
    )
    q_vec = embeddings.embed(query)
    texts = [c.profile.search_text() or c.filename for c in candidates]
    vecs = embeddings.embed_batch(texts)
    scored = [
        (c.resume_id, cosine_similarity(q_vec, v))
        for c, v in zip(candidates, vecs, strict=True)
    ]
    scored.sort(key=lambda item: (-item[1], item[0]))
    return [resume_id for resume_id, _ in scored]
def recluster_library(db: Session) -> dict[str, str]:
    from app.core.workspace import require_workspace_id
    from app.db.models import Resume
    wid = require_workspace_id()
    rows = db.query(Resume).filter(Resume.workspace_id == wid, Resume.in_library.is_(True)).all()
    if not rows: return {}
    ids: list[str] = []
    texts: list[str] = []
    for row in rows:
        profile = ResumeProfile.model_validate_json(row.parsed_json or "{}")
        ids.append(row.id)
        texts.append(profile.search_text() or row.filename)
    if not is_set(settings.EMBEDDINGS_API_KEY): return {row.id: row.cluster_id or row.id for row in rows}
    vecs = embeddings.embed_batch(texts)
    mapping = single_linkage_clusters(ids, vecs)
    for row in rows:
        row.cluster_id = mapping.get(row.id, row.id)
        db.add(row)
    db.commit()
    return mapping
def rank_resumes_for_job(
    job: Job,
    candidates: list[ResumeCandidate],
    *,
    use_llm: bool = True,
    db: Session | None = None,
    metadata_hints: JobMetadata | None = None,
) -> list[RankedResumeRecommendation]:
    if not candidates: return []
    by_id = {c.resume_id: c for c in candidates}
    requirements = decompose_jd(job, use_llm=use_llm, db=db, metadata_hints=metadata_hints)
    req_texts = [r.text for r in requirements]
    weights = [r.weight for r in requirements]
    categories = [r.category for r in requirements]
    req_embs = embeddings.embed_batch(req_texts)
    evidence_floor = float(settings.EVIDENCE_FLOOR)
    units_by_id: dict[str, list] = {}
    whole_texts: list[str] = []
    whole_ids: list[str] = []
    for c in candidates:
        units = ensure_candidate_units(c.profile, db=db, resume_id=c.resume_id if db else None)
        units_by_id[c.resume_id] = units
        whole_ids.append(c.resume_id)
        whole_texts.append(c.profile.search_text() or c.filename)
    whole_vecs = embeddings.embed_batch(whole_texts)
    cluster_map = single_linkage_clusters(whole_ids, whole_vecs)
    members: dict[str, list[str]] = defaultdict(list)
    for rid, cid in cluster_map.items():
        members[cid].append(rid)
    for cid in members:
        members[cid].sort()
    if db is not None:
        from app.db.models import Resume
        for rid, cid in cluster_map.items():
            resume_row = db.query(Resume).filter(Resume.id == rid).one_or_none()
            if resume_row is not None:
                resume_row.cluster_id = cid
                db.add(resume_row)
        db.commit()
    coverage_by_id: dict[str, float] = {}
    alignment_by_id: dict[str, list[dict]] = {}
    categories_str: list[str] = list(categories)
    for c in candidates:
        units = units_by_id[c.resume_id]
        unit_embs = [u.embedding for u in units if u.embedding is not None]
        unit_texts = [u.unit_text for u in units if u.embedding is not None]
        unit_sections = [u.section for u in units if u.embedding is not None]
        if len(unit_embs) != len([u for u in units if u.embedding is not None]) or not unit_embs:
            from app.services.resume.units import embed_units, extract_units
            fresh = embed_units(extract_units(c.profile))
            unit_embs = [u.embedding for u in fresh if u.embedding is not None]
            unit_texts = [u.unit_text for u in fresh if u.embedding is not None]
            unit_sections = [u.section for u in fresh if u.embedding is not None]
            units_by_id[c.resume_id] = fresh
        cov, rows = align_resume(
            req_embs,
            req_texts,
            weights,
            unit_embs,
            unit_texts,
            c.profile.skills,
            unit_sections=unit_sections,
            evidence_floor=evidence_floor,
            categories=categories_str,
        )
        for i, align_row in enumerate(rows):
            if i < len(requirements):
                align_row["kind"] = requirements[i].kind
                align_row["category"] = requirements[i].category
        over_cited = under_segmented_units(rows)
        if over_cited:
            logger.warning(
                "resume_units.under_segmented",
                resume_id=c.resume_id,
                units=over_cited[:5],
                message="unit cited as best evidence for >3 requirements",
            )
        coverage_by_id[c.resume_id] = cov
        alignment_by_id[c.resume_id] = rows
    ordered_ids = sorted(coverage_by_id.keys(), key=lambda i: (-coverage_by_id[i], i))
    evidences = [
        AlignmentEvidence(
            resume_id=rid,
            content_hash=by_id[rid].content_hash or rid,
            coverage=coverage_by_id[rid],
            top_units=evidence_units_from_alignment(alignment_by_id[rid]),
            alignment_rows=alignment_by_id[rid],
            filename=by_id[rid].filename,
        )
        for rid in ordered_ids
    ]
    tournament = maybe_run_tournament(job, requirements, evidences, use_llm=use_llm, db=db)
    final_ids = tournament.ordered_ids
    top_n = min(settings.RESUME_RECOMMEND_TOP_N, len(final_ids))
    justify_lookup = {}
    if use_llm and top_n > 0:
        top_candidates = [by_id[i] for i in final_ids[:top_n]]
        rank_by_id = {rid: idx + 1 for idx, rid in enumerate(final_ids[:top_n])}
        justify_lookup = llm_justify(
            job,
            top_candidates,
            alignment_by_id,
            requirements,
            rank_by_id=rank_by_id,
            tournament_wins=tournament.wins if tournament.ran else {},
            contested_ids=set(tournament.contested_ids) if tournament.ran else set(),
        )
    ranked: list[RankedResumeRecommendation] = []
    for rank_idx, rid in enumerate(final_ids[:top_n]):
        c = by_id[rid]
        cov = coverage_by_id[rid]
        rows = alignment_by_id[rid]
        item = justify_lookup.get(rid)
        units_preview = evidence_units_from_alignment(rows) or ["—"]
        must_n = sum(1 for r in requirements if r.kind == "must")
        must_hit_preview = sum(
            1 for r in rows if str(r.get("kind") or "must") == "must" and r.get("status") == "hit"
        )
        rationale = (
            item.rationale
            if item
            else (
                f"{must_hit_preview} of {must_n or len(requirements)} must-haves evidenced; "
                f"best evidence: {units_preview[0][:160]}"
            )
        )
        if not rationale_rank_consistent(rationale, final_rank=rank_idx + 1):
            if rank_idx == 0:
                pass
            else:
                rationale = (
                    f"Rank #{rank_idx + 1}: {must_hit_preview} of {must_n or len(requirements)} "
                    f"must-haves evidenced; evidence: {units_preview[0][:160]}"
                )
        matched = item.matched_skills if item else [r["requirement"] for r in rows if r.get("status") == "hit"][:12]
        missing = item.missing_skills if item else [r["requirement"] for r in rows if r.get("status") == "miss"][:12]
        llm_fit = float(item.fit_score) if item else cov * 100.0
        skill = skill_jaccard(c.profile.skills, job.skills)
        from app.services.ranking.math import experience_fit_score
        exp = experience_fit_score(
            c.profile.years_of_experience,
            title=job.title,
            description=job.description,
        )
        final_score = (0.55 * cov + 0.25 * (llm_fit / 100.0) + 0.10 * skill + 0.10 * exp) * 100.0
        # Headline match = weighted final blend (one coherent scale with table/justification).
        match_score = round(final_score, 2)
        must_rows = [r for r in rows if str(r.get("kind") or "must") == "must"]
        must_hit = sum(1 for r in must_rows if r.get("status") == "hit")
        must_total = len(must_rows)
        cid = cluster_map.get(rid, rid)
        mlist = members.get(cid, [rid])
        cov_rows = [
            RequirementCoverage(
                requirement=r["requirement"], status=r["status"], evidence=r.get("evidence_unit")
            )
            for r in rows
        ]
        ranked.append(
            RankedResumeRecommendation(
                resume_id=c.resume_id,
                filename=c.filename,
                match_score=match_score,
                content_hash=c.content_hash,
                score_breakdown=ScoreBreakdown(
                    llm_fit=llm_fit,
                    rrf_normalized=cov,
                    skill_jaccard=skill,
                    recency=0.0,
                    experience_fit=exp,
                    requirements_met=cov,
                    final_score=round(final_score, 2),
                    matched_skills=matched,
                    missing_skills=missing,
                    rationale=rationale,
                ),
                coverage=cov_rows,
                coverage_score=round(cov, 4),
                must_haves_hit=must_hit,
                must_haves_total=must_total,
                alignment=[
                    AlignmentRow(
                        requirement=r["requirement"],
                        kind=str(r.get("kind") or "must"),
                        category=str(r.get("category") or "skill"),
                        weight=float(r.get("weight") or 1.0),
                        evidence_unit=r.get("evidence_unit"),
                        evidence_score=float(r.get("evidence_score") or 0.0),
                        strength=_row_strength(r),
                        status=r["status"],
                    )
                    for r in rows
                ],
                cluster_id=cid,
                cluster_label=cluster_variant_label(rid, cid, mlist),
                cluster_size=len(mlist),
                tournament=TournamentRecord(
                    ran=tournament.ran,
                    comparisons=tournament.comparisons if tournament.ran else 0,
                    cache_hits=tournament.cache_hits if tournament.ran else 0,
                    cost_usd=tournament.cost_usd if tournament.ran else None,
                    wins=tournament.wins.get(rid, 0) if tournament.ran else 0,
                    borda_score=float(tournament.borda_scores.get(rid, 0.0)) if tournament.ran else 0.0,
                    contested=rid in tournament.contested_ids if tournament.ran else False,
                    overrode_coverage=bool(tournament.overrode_coverage) if tournament.ran else False,
                    reasons=[reason for (a, b), reason in tournament.reasons.items() if rid in (a, b) and reason][:3],
                    judge_agreement=tournament.judge_agreement_mean if tournament.ran else None,
                    judge_agreement_label=(agreement_label(tournament.judge_agreement_mean, max(1, len(tournament.panel_models) or 1)) if tournament.ran and tournament.panel_models else None),
                ),
            )
        )
    # Tournament only reorders cards; match_score stays the weighted final blend
    # (never fudge rings to hide inverted scores — badge explains tournament order).
    rank_resumes_for_job.last_tournament = tournament  # type: ignore[attr-defined]
    return ranked
rank_resumes_for_job.last_tournament = None  # type: ignore[attr-defined]
