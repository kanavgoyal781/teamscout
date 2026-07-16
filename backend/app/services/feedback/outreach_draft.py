from __future__ import annotations
import json
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.core.workspace import require_workspace_id
from app.db.models import Contact, EmailReveal, JobTeamSearch, Resume, Search
from app.errors import NotFoundError, ValidationError
from app.prompts import load_prompt
from app.schemas.resume import ResumeProfile
from app.services import llm
from app.services.jobs_svc.store import resolve_job
class OutreachDraftResult(BaseModel):
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=8000)
def require_revealed_email(db: Session, contact_id: str) -> tuple[Contact, str]:
    wid = require_workspace_id()
    contact = db.query(Contact).filter(Contact.id == contact_id, Contact.workspace_id == wid).one_or_none()
    if contact is None:
        raise NotFoundError("contact", contact_id)
    reveal = (
        db.query(EmailReveal)
        .filter(EmailReveal.contact_id == contact_id, EmailReveal.status == "revealed")
        .one_or_none()
    )
    email = reveal.email if reveal else None
    if not email or "@" not in email:
        raise ValidationError(
            "Contact email is not revealed — reveal email before composing",
            details={"contact_id": contact_id},
        )
    return contact, email
def _profile_and_skills(db: Session, contact: Contact) -> tuple[ResumeProfile | None, list[str]]:
    search_id = contact.search_id
    if not search_id and contact.job_id:
        ts = db.query(JobTeamSearch).filter(JobTeamSearch.job_id == contact.job_id).one_or_none()
        search_id = ts.search_id if ts else None
    if not search_id:
        return None, []
    search = db.query(Search).filter(Search.id == search_id).one_or_none()
    if search is None:
        return None, []
    profile = None
    if search.resume_id:
        resume = db.query(Resume).filter(Resume.id == search.resume_id).one_or_none()
        if resume and resume.parsed_json:
            try:
                profile = ResumeProfile.model_validate_json(resume.parsed_json)
            except (ValueError, TypeError, json.JSONDecodeError):
                profile = None
    matched: list[str] = []
    if search.results_json and contact.job_id:
        try:
            results = json.loads(search.results_json)
        except json.JSONDecodeError:
            results = []
        if isinstance(results, list):
            for item in results:
                if not isinstance(item, dict):
                    continue
                job = item.get("job") if isinstance(item.get("job"), dict) else item
                jid = job.get("id") or job.get("job_id") if isinstance(job, dict) else None
                if jid != contact.job_id:
                    continue
                bd_raw = item.get("score_breakdown")
                bd: dict = bd_raw if isinstance(bd_raw, dict) else {}
                raw = bd.get("matched_skills") or []
                if isinstance(raw, list):
                    matched = [str(s) for s in raw if s][:8]
                break
    return profile, matched
def _strengths(profile: ResumeProfile | None, matched: list[str]) -> str:
    lines: list[str] = []
    if matched:
        lines.append("- Matched skills: " + ", ".join(matched[:6]))
    if profile is None:
        return "\n".join(lines) or "- (no resume profile linked)"
    if profile.skills:
        lines.append("- Skills: " + ", ".join(profile.skills[:10]))
    for role in (profile.work_experience or [])[:2]:
        head = " · ".join(p for p in ((role.title or "").strip(), (role.company or "").strip()) if p)
        if head:
            lines.append(f"- Experience: {head}")
        for bullet in (role.bullets or [])[:2]:
            if bullet and bullet.strip():
                lines.append(f"  · {bullet.strip()[:220]}")
    if profile.summary and profile.summary.strip():
        lines.append(f"- Summary: {profile.summary.strip()[:280]}")
    return "\n".join(lines) or "- (limited profile evidence)"
def generate_outreach_draft(db: Session, contact_id: str) -> tuple[OutreachDraftResult, str]:
    contact, email = require_revealed_email(db, contact_id)
    job_title, job_company = "", contact.company or ""
    if contact.job_id:
        try:
            job = resolve_job(contact.job_id, db)
            job_title, job_company = job.title or "", job.company or job_company
        except NotFoundError:
            pass
    profile, matched = _profile_and_skills(db, contact)
    tmpl = load_prompt("outreach_draft")
    mapping = {
        "recipient_name": contact.full_name or "",
        "recipient_title": contact.title or "",
        "recipient_team": contact.team or "",
        "company": contact.company or job_company or "",
        "job_title": job_title,
        "job_company": job_company,
        "candidate_name": (profile.name if profile else "") or "",
        "candidate_title": (profile.title if profile else "") or "",
        "candidate_skills": ", ".join((profile.skills if profile else [])[:12]),
        "strengths_block": _strengths(profile, matched),
    }
    prompt = tmpl.body
    for key, value in mapping.items():
        prompt = prompt.replace("{{" + key + "}}", value)
    result = llm.complete_json(
        prompt, OutreachDraftResult, system=tmpl.system,
        temperature=float(tmpl.model_params.get("temperature") or 0.4),
        max_tokens=int(tmpl.model_params.get("max_tokens") or 800),
        max_retries=1, operation="outreach_draft", prompt_meta=tmpl,
    )
    subject, body = (result.subject or "").strip(), (result.body or "").strip()
    if not subject or not body:
        raise ValidationError("Draft generation returned empty subject or body")
    return OutreachDraftResult(subject=subject[:300], body=body[:8000]), email
