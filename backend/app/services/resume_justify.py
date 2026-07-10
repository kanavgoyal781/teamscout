"""LLM top-resume justify with evidence-unit grounding."""
from __future__ import annotations
from pydantic import BaseModel, Field
from app.core.config import settings
from app.errors import ServiceFailingError
from app.prompts import load_prompt
from app.schemas.jobs import Job
from app.schemas.library import RequirementCoverage, ResumeCandidate
from app.schemas.resume import ResumeProfile
from app.services import llm
from app.services.jd_decompose import JdRequirement
_MIN_CITE_SPAN = 16
_MIN_CITE_RATIO = 0.35
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
        if text and text not in units:
            units.append(str(text))
        if len(units) >= 8:
            break
    return units
def _span_in_text(unit: str, rationale: str) -> bool:
    u = " ".join(unit.strip().lower().split())
    text = " ".join(rationale.strip().lower().split())
    if not u or not text:
        return False
    if len(u) < 8:
        return u in text
    if u in text:
        return True
    min_span = min(len(u), max(_MIN_CITE_SPAN, int(len(u) * _MIN_CITE_RATIO)))
    return any(u[s : s + min_span] in text for s in range(0, len(u) - min_span + 1, 2))
def rationale_cites_units(rationale: str, evidence_units: list[str]) -> bool:
    """Fail-closed; prefer long units when present (skill-name-only then insufficient)."""
    text = (rationale or "").strip()
    if len(text) < 20:
        return False
    cleaned = [u for u in evidence_units if u and u.strip()]
    if not cleaned:
        return False
    long_units = [u for u in cleaned if len(u.strip()) >= _MIN_CITE_SPAN]
    targets = long_units if long_units else cleaned
    return any(_span_in_text(unit, text) for unit in targets)
def rationale_references_resume(rationale: str, profile: ResumeProfile) -> bool:
    """Fallback when no alignment units: require span from bullets/summary/title."""
    units: list[str] = []
    if profile.title.strip():
        units.append(profile.title.strip())
    for skill in profile.skills:
        if skill.strip():
            units.append(skill.strip())
    for role in profile.work_experience:
        units.extend(b for b in role.bullets[:3] if b.strip())
    if profile.summary.strip():
        units.append(profile.summary.strip()[:200])
    return rationale_cites_units(rationale, units)
def evidence_in_units(evidence: str | None, units: list[str]) -> bool:
    """True when LLM coverage evidence is a span of a provided unit."""
    if not evidence or not evidence.strip():
        return False
    ev = evidence.strip().lower()
    for unit in units:
        u = unit.strip().lower()
        if not u:
            continue
        if ev in u or u in ev:
            return True
        if _span_in_text(unit, evidence) or _span_in_text(evidence, unit):
            return True
    return False
def filter_llm_coverage(
    llm_coverage: list[RequirementCoverage],
    units: list[str],
) -> list[RequirementCoverage]:
    """Keep LLM coverage only when hit evidence is grounded in provided units."""
    out: list[RequirementCoverage] = []
    for row in llm_coverage:
        if row.status == "hit":
            if not evidence_in_units(row.evidence, units):
                out.append(
                    RequirementCoverage(
                        requirement=row.requirement,
                        status="miss",
                        evidence=None,
                    )
                )
                continue
        out.append(row)
    return out
def _build_justify_prompt(
    job: Job,
    candidates: list[ResumeCandidate],
    alignment_by_id: dict[str, list[dict]],
    requirements: list[JdRequirement],
    instructions: str,
) -> str:
    lines = [
        instructions.strip(),
        "",
        f"Job title: {job.title}",
        f"Company: {job.company}",
        f"Location: {job.location}",
        f"Required skills: {', '.join(job.skills)}",
        f"Description: {job.description[:1200]}",
        "",
        "Atomic requirements:",
    ]
    for req in requirements[:14]:
        lines.append(f"- [{req.kind}] {req.text} (weight={req.weight})")
    lines.append("")
    lines.append("Resumes with best-evidence units (cite these in rationale):")
    for candidate in candidates:
        rows = alignment_by_id.get(candidate.resume_id, [])
        units = evidence_units_from_alignment(rows)
        profile = candidate.profile
        lines.append(
            f"- resume_id={candidate.resume_id}; filename={candidate.filename}; "
            f"title={profile.title}; skills={', '.join(profile.skills[:12])};"
        )
        for u in units:
            lines.append(f"    evidence: {u}")
    return "\n".join(lines)
def llm_justify(
    job: Job,
    candidates: list[ResumeCandidate],
    alignment_by_id: dict[str, list[dict]],
    requirements: list[JdRequirement],
    *,
    attempt: int = 0,
) -> dict[str, ResumeRerankItem]:
    if not candidates:
        return {}
    expected_ids = {c.resume_id for c in candidates}
    tmpl = load_prompt("justify")
    prompt = _build_justify_prompt(job, candidates, alignment_by_id, requirements, tmpl.body)
    if attempt > 0:
        prompt += (
            "\n\nPrevious rationales did not cite provided evidence units. "
            "Each rationale MUST quote a contiguous phrase from a provided evidence unit."
        )
    response = llm.complete_json(
        prompt,
        ResumeRerankResponse,
        system=tmpl.system or "You are a recruiting matcher. Return JSON only.",
        max_tokens=int(tmpl.model_params.get("max_tokens") or settings.max_tokens_for_operation("justify")),
        operation="justify",
        prompt_meta=tmpl,
    )
    if not response.results:
        raise ServiceFailingError("LLM", "resume justify returned no results")
    returned_ids = [item.resume_id for item in response.results]
    if len(returned_ids) != len(set(returned_ids)):
        raise ServiceFailingError("LLM", "resume justify returned duplicate resume_ids")
    returned_set = set(returned_ids)
    if returned_set != expected_ids:
        missing = sorted(expected_ids - returned_set)
        extra = sorted(returned_set - expected_ids)
        raise ServiceFailingError(
            "LLM",
            f"resume justify resume_id mismatch: missing={missing}, extra={extra}",
        )
    by_id = {c.resume_id: c for c in candidates}
    for item in response.results:
        units = evidence_units_from_alignment(alignment_by_id.get(item.resume_id, []))
        if not units:
            if not rationale_references_resume(item.rationale, by_id[item.resume_id].profile):
                if attempt == 0:
                    return llm_justify(job, candidates, alignment_by_id, requirements, attempt=1)
                raise ServiceFailingError(
                    "LLM",
                    f"resume justify rationale lacks concrete resume references for {item.resume_id}",
                )
        elif not rationale_cites_units(item.rationale, units):
            if attempt == 0:
                return llm_justify(job, candidates, alignment_by_id, requirements, attempt=1)
            raise ServiceFailingError(
                "LLM",
                f"resume justify rationale does not cite evidence units for {item.resume_id}",
            )
        if item.coverage:
            item.coverage = filter_llm_coverage(item.coverage, units)
    return {item.resume_id: item for item in response.results}
