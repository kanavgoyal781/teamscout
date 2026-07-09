from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.rate_limit import limiter, reveal_email_limit
from app.db.models import Contact
from app.db.session import get_db
from app.errors import NotFoundError, ValidationError
from app.schemas.team import EmailRevealResponse
from app.services import email_reveal

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.post("/{contact_id}/reveal-email", response_model=EmailRevealResponse)
@limiter.limit(reveal_email_limit)
def reveal_email(
    request: Request,
    contact_id: str,
    confirm: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> EmailRevealResponse:
    contact = db.query(Contact).filter(Contact.id == contact_id).one_or_none()
    if contact is None:
        raise NotFoundError("contact", contact_id)
    if not contact.sumble_person_id:
        raise ValidationError("Contact is missing a person id — find the hiring team first")

    if not confirm:
        return email_reveal.preview_reveal(db, contact)
    return email_reveal.confirm_reveal(db, contact)
