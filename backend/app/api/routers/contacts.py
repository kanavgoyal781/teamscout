from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.rate_limit import limiter, llm_limit, reveal_email_limit
from app.core.workspace import require_workspace_id
from app.db.models import Contact
from app.db.session import get_db
from app.errors import NotFoundError, ValidationError
from app.schemas.team import EmailRevealResponse, OutreachDraftResponse
from app.services import email_reveal, outreach_draft

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.post("/{contact_id}/reveal-email", response_model=EmailRevealResponse)
@limiter.limit(reveal_email_limit)
def reveal_email(
    request: Request, contact_id: str, confirm: bool = Query(default=False), db: Session = Depends(get_db)
) -> EmailRevealResponse:
    wid = require_workspace_id()
    contact = db.query(Contact).filter(Contact.id == contact_id, Contact.workspace_id == wid).one_or_none()
    if contact is None:
        raise NotFoundError("contact", contact_id)
    if not contact.sumble_person_id:
        raise ValidationError("Contact is missing a person id — find the hiring team first")
    return email_reveal.preview_reveal(db, contact) if not confirm else email_reveal.confirm_reveal(db, contact)


@router.post("/{contact_id}/outreach-draft", response_model=OutreachDraftResponse)
@limiter.limit(llm_limit)
def create_outreach_draft(request: Request, contact_id: str, db: Session = Depends(get_db)) -> OutreachDraftResponse:
    """Compose-only email draft (no SMTP/OAuth/send)."""
    draft, email = outreach_draft.generate_outreach_draft(db, contact_id)
    return OutreachDraftResponse(contact_id=contact_id, subject=draft.subject, body=draft.body, email=email)
