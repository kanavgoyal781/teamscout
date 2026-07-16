from __future__ import annotations
import re
from pydantic import BaseModel, Field
from app.core.config import settings
from app.errors import ServiceFailingError
from app.prompts import load_prompt
from app.schemas.jobs import Job
from app.schemas.library import RequirementCoverage, ResumeCandidate
from app.schemas.resume import ResumeProfile
from app.services import llm
from app.services.resume.jd_decompose import JdRequirement
_MIN_CITE_SPAN = 16
_MIN_CITE_RATIO = 0.35
_RANK_SUPERLATIVE = re.compile(
    r"(?:(?<!\w)#\s*1\b|\b(?:best\s+(?:match|fit|candidate|pick|resume|overall)|"
    r"strongest\s+(?:overall\s+)?(?:match|candidate|fit)|strongest\s+overall|"
    r"top\s+(?:choice|pick|resume)|preferred\s+(?:choice|resume)|ideal\s+(?:candidate|match|pick)|"
    r"most\s+suitable|superior\s+match|number\s+one|rank\s*#?\s*1|"
    r"stands\s+out\s+as\s+the\s+best|the\s+best\s+(?:fit|candidate|pick|match|resume|option)|"
    r"clearest\s+best|unambiguously\s+best)\b)", re.IGNORECASE,
)
class ResumeRerankItem(BaseModel):
    resume_id: str
    fit_score: float = Field(ge=0, le=100)
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    rationale: str = ""
    coverage: list[RequirementCoverage] = Field(default_factory=list)
class ResumeRerankResponse(BaseModel):
    results: list[ResumeRerankItem]
def evidence_units_from_alignment(rows: list[dict]) -> list[str]:
    units: list[str] = []
    for row in sorted(rows, key=lambda r: float(r.get("evidence_score") or 0), reverse=True):
        text = row.get("evidence_unit")
        if not text or str(text) == "No clear evidence" or text in units: continue
        units.append(str(text))
        if len(units) >= 8:
            break
    return units
def _span_in_text(unit: str, rationale: str) -> bool:
    u = " ".join(unit.strip().lower().split())
    text = " ".join(rationale.strip().lower().split())
    if not u or not text: return False
    if len(u) < 8:
        return u in text
    if u in text: return True
    min_span = min(len(u), max(_MIN_CITE_SPAN, int(len(u) * _MIN_CITE_RATIO)))
    return any(u[s : s + min_span] in text for s in range(0, len(u) - min_span + 1, 2))
def rationale_cites_units(rationale: str, evidence_units: list[str]) -> bool:
    text = (rationale or "").strip()
    if len(text) < 20: return False
    cleaned = [u for u in evidence_units if u and u.strip()]
    if not cleaned: return False
    long_units = [u for u in cleaned if len(u.strip()) >= _MIN_CITE_SPAN]
    return any(_span_in_text(unit, text) for unit in (long_units or cleaned))
def rationale_references_resume(rationale: str, profile: ResumeProfile) -> bool:
    units: list[str] = []
    if profile.title.strip():
        units.append(profile.title.strip())
    units.extend(s.strip() for s in profile.skills if s.strip())
    for role in profile.work_experience:
        units.extend(b for b in role.bullets[:3] if b.strip())
    if profile.summary.strip():
        units.append(profile.summary.strip()[:200])
    return rationale_cites_units(rationale, units)
def rationale_rank_consistent(rationale: str, *, final_rank: int) -> bool:
    if final_rank <= 1: return True
    text = (rationale or "").strip()
    return not text or _RANK_SUPERLATIVE.search(text) is None
def fit_scores_rank_monotonic(items: list[ResumeRerankItem], ranks: dict[str, int]) -> bool:
    ordered = sorted(items, key=lambda it: (ranks.get(it.resume_id, 99), it.resume_id))
    return all(float(cur.fit_score) <= float(prev.fit_score) + 1e-9 for prev, cur in zip(ordered, ordered[1:], strict=False))
def clamp_fit_scores_to_rank(items: list[ResumeRerankItem], ranks: dict[str, int]) -> None:
    ordered = sorted(items, key=lambda it: (ranks.get(it.resume_id, 99), it.resume_id))
    for i in range(1, len(ordered)):
        if ordered[i].fit_score > ordered[i - 1].fit_score:
            ordered[i].fit_score = float(ordered[i - 1].fit_score)
def evidence_in_units(evidence: str | None, units: list[str]) -> bool:
    if not evidence or not evidence.strip(): return False
    ev = evidence.strip().lower()
    for unit in units:
        u = unit.strip().lower()
        if not u: continue
        if ev in u or u in ev or _span_in_text(unit, evidence) or _span_in_text(evidence, unit): return True
    return False
def filter_llm_coverage(
    llm_coverage: list[RequirementCoverage], units: list[str]
) -> list[RequirementCoverage]:
    out: list[RequirementCoverage] = []
    for row in llm_coverage:
        if row.status == "hit" and not evidence_in_units(row.evidence, units):
            out.append(RequirementCoverage(requirement=row.requirement, status="miss", evidence=None))
        else:
            out.append(row)
    return out
def _build_justify_prompt(
    job: Job,
    candidates: list[ResumeCandidate],
    alignment_by_id: dict[str, list[dict]],
    requirements: list[JdRequirement],
    instructions: str,
    *,
    rank_by_id: dict[str, int] | None = None,
    tournament_wins: dict[str, int] | None = None,
    contested_ids: set[str] | None = None,
) -> str:
    ranks, wins, contested = rank_by_id or {}, tournament_wins or {}, contested_ids or set()
    lines = [
        instructions.strip(), "",
        f"Job title: {job.title}", f"Company: {job.company}", f"Location: {job.location}",
        f"Required skills: {', '.join(job.skills)}", f"Description: {job.description[:1200]}",
        "", "Atomic requirements:",
    ]
    for req in requirements[:14]:
        lines.append(f"- [{req.kind}/{req.category}] {req.text}")
    lines += ["", "Resumes (final ranking FIXED — only final_rank=1 may claim best match):"]
    for candidate in candidates:
        rows = alignment_by_id.get(candidate.resume_id, [])
        rid = candidate.resume_id
        lines.append(
            f"- resume_id={rid}; filename={candidate.filename}; final_rank={ranks.get(rid, 0)}; "
            f"tournament_wins={wins.get(rid, 0)}; contested={rid in contested}; "
            f"title={candidate.profile.title}; skills={', '.join(candidate.profile.skills[:12])};"
        )
        for u in evidence_units_from_alignment(rows):
            lines.append(f"    evidence: {u}")
    return "\n".join(lines)
def llm_justify(
    job: Job,
    candidates: list[ResumeCandidate],
    alignment_by_id: dict[str, list[dict]],
    requirements: list[JdRequirement],
    *,
    attempt: int = 0,
    rank_by_id: dict[str, int] | None = None,
    tournament_wins: dict[str, int] | None = None,
    contested_ids: set[str] | None = None,
) -> dict[str, ResumeRerankItem]:
    if not candidates: return {}
    expected_ids = {c.resume_id for c in candidates}
    ranks = rank_by_id or {c.resume_id: i + 1 for i, c in enumerate(candidates)}
    tmpl = load_prompt("justify")
    prompt = _build_justify_prompt(
        job, candidates, alignment_by_id, requirements, tmpl.body,
        rank_by_id=ranks, tournament_wins=tournament_wins, contested_ids=contested_ids,
    )
    if attempt > 0:
        prompt += (
            "\n\nPrevious response failed grounding or rank-consistency checks. "
            "Quote evidence units; only final_rank=1 may use best-match superlatives; "
            "fit_score must be non-increasing with final_rank."
        )
    response = llm.complete_json(
        prompt, ResumeRerankResponse,
        system=tmpl.system or "You are a recruiting matcher. Return JSON only.",
        max_tokens=int(tmpl.model_params.get("max_tokens") or settings.max_tokens_for_operation("justify")),
        operation="justify", prompt_meta=tmpl,
    )
    if not response.results: raise ServiceFailingError("LLM", "resume justify returned no results")
    returned_ids = [item.resume_id for item in response.results]
    if len(returned_ids) != len(set(returned_ids)): raise ServiceFailingError("LLM", "resume justify returned duplicate resume_ids")
    returned_set = set(returned_ids)
    if returned_set != expected_ids:
        missing, extra = sorted(expected_ids - returned_set), sorted(returned_set - expected_ids)
        raise ServiceFailingError("LLM", f"resume justify resume_id mismatch: missing={missing}, extra={extra}")
    by_id = {c.resume_id: c for c in candidates}
    def _retry(msg: str) -> dict[str, ResumeRerankItem]:
        if attempt == 0: return llm_justify(
                job, candidates, alignment_by_id, requirements, attempt=1,
                rank_by_id=ranks, tournament_wins=tournament_wins, contested_ids=contested_ids,
            )
        raise ServiceFailingError("LLM", msg)
    for item in response.results:
        units = evidence_units_from_alignment(alignment_by_id.get(item.resume_id, []))
        if not units:
            if not rationale_references_resume(item.rationale, by_id[item.resume_id].profile):
                return _retry(f"resume justify rationale lacks concrete resume references for {item.resume_id}")
        elif not rationale_cites_units(item.rationale, units):
            return _retry(f"resume justify rationale does not cite evidence units for {item.resume_id}")
        final_rank = ranks.get(item.resume_id, 99)
        if not rationale_rank_consistent(item.rationale, final_rank=final_rank): return _retry(
                f"resume justify rationale rank-inconsistent superlative for rank {final_rank} resume {item.resume_id}"
            )
        if item.coverage:
            item.coverage = filter_llm_coverage(item.coverage, units)
    if not fit_scores_rank_monotonic(response.results, ranks):
        if attempt == 0: return _retry("resume justify fit_score not monotonic with final_rank")
        clamp_fit_scores_to_rank(response.results, ranks)
    return {item.resume_id: item for item in response.results}
