from datetime import UTC, datetime
from sqlalchemy.orm import Session
from app.core.workspace import require_workspace_id
from app.db.models import Contact, EmailReveal, JobTeamSearch
from app.schemas.jobs import Job
from app.schemas.team import ContactOut, FindTeamResponse, TeamExtraction
from app.services import sumble
def contact_to_out(contact: Contact, reveal_email: str | None = None) -> ContactOut:
    return ContactOut(
        id=contact.id,
        full_name=contact.full_name,
        title=contact.title,
        company=contact.company,
        team=contact.team,
        seniority=contact.seniority,
        sumble_person_id=contact.sumble_person_id,
        email_revealed=reveal_email is not None,
        email=reveal_email,
    )
def _record_team_search(
    job_id: str,
    extraction_id: str,
    search_id: str | None,
    credits_used: int,
    search_path: str | None,
    db: Session,
) -> None:
    now = datetime.now(UTC)
    wid = require_workspace_id()
    existing = db.query(JobTeamSearch).filter(JobTeamSearch.job_id == job_id, JobTeamSearch.workspace_id == wid).one_or_none()
    if existing is None:
        db.add(
            JobTeamSearch(
                workspace_id=wid,
                job_id=job_id,
                extraction_id=extraction_id,
                search_id=search_id,
                team_searched_at=now,
                credits_used=credits_used,
                search_path=search_path,
            )
        )
        return
    existing.extraction_id = extraction_id
    existing.search_id = search_id
    existing.team_searched_at = now
    existing.credits_used = credits_used
    existing.search_path = search_path
    db.add(existing)
def find_team_for_job(
    job: Job,
    extraction: TeamExtraction,
    extraction_id: str,
    search_id: str | None,
    db: Session,
) -> FindTeamResponse:
    wid = require_workspace_id()
    org, org_credits = sumble.lookup_organization(job.company, job.apply_url)
    people, search_credits, search_path = sumble.find_hiring_team(
        organization_id=org.organization_id,
        team_name=extraction.team_name,
        department=extraction.department,
        likely_hiring_titles=extraction.likely_hiring_titles,
        jd_title=job.title,
        company=job.company,
    )
    credits_used = org_credits + search_credits  # aggregate: org lookup + (title-lookup|job-match) + people/related
    contacts: list[ContactOut] = []
    for person in people:
        person_key = str(person.person_id)
        existing = (
            db.query(Contact).filter(Contact.workspace_id == wid, Contact.sumble_person_id == person_key, Contact.job_id == job.id).one_or_none()
        )
        if existing is None:
            existing = Contact(
                workspace_id=wid,
                full_name=person.name or "Unknown",
                title=person.title,
                company=job.company,
                team=person.team,
                seniority=person.seniority,
                job_id=job.id,
                search_id=search_id,
                extraction_id=extraction_id,
                sumble_person_id=person_key,
            )
            db.add(existing)
        else:
            existing.full_name = person.name or existing.full_name
            existing.title = person.title
            existing.team = person.team
            existing.seniority = person.seniority
            existing.search_id = search_id or existing.search_id
            existing.extraction_id = extraction_id
            db.add(existing)
        db.flush()
        reveal = (
            db.query(EmailReveal)
            .filter(EmailReveal.contact_id == existing.id, EmailReveal.status == "revealed")
            .one_or_none()
        )
        contacts.append(contact_to_out(existing, reveal.email if reveal else None))
    _record_team_search(job.id, extraction_id, search_id, credits_used, search_path, db)
    db.commit()
    return FindTeamResponse(
        job_id=job.id,
        contacts=contacts,
        credits_used=credits_used,
        team_searched=True,
        search_path=search_path,
    )
