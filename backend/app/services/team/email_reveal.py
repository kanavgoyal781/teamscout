from __future__ import annotations
from datetime import UTC, datetime
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.db.models import Contact, EmailReveal
from app.errors import ValidationError
from app.schemas.team import EmailRevealResponse
from app.services import sumble
TERMINAL_STATUSES = frozenset({"revealed", "not_found"})
def is_terminal(reveal: EmailReveal) -> bool:
    return reveal.status in TERMINAL_STATUSES
def _begin_immediate(db: Session) -> None:
    bind = db.get_bind()
    if bind.dialect.name != "sqlite":
        return
    if db.in_transaction():
        db.rollback()
    db.execute(text("BEGIN IMMEDIATE"))
def _terminal_response(contact_id: str, reveal: EmailReveal) -> EmailRevealResponse:
    if reveal.status == "revealed" and reveal.email:
        return EmailRevealResponse(
            contact_id=contact_id,
            cached=True,
            email=reveal.email,
            cost_credits=reveal.cost_credits,
            status=reveal.status,
        )
    return EmailRevealResponse(
        contact_id=contact_id,
        cached=True,
        email=None,
        cost_credits=reveal.cost_credits,
        status=reveal.status,
    )
def _cached_not_found_error(contact_id: str, reveal: EmailReveal) -> ValidationError:
    return ValidationError(
        "Email already attempted for this contact — no email found (cached)",
        details={
            "contact_id": contact_id,
            "status": reveal.status,
            "cost_credits": reveal.cost_credits,
            "cached": True,
        },
    )
def _global_person_reveal(db: Session, person_id: str | None, *, exclude_contact_id: str | None = None) -> EmailReveal | None:
    if not person_id:
        return None
    q = db.query(EmailReveal).filter(
        EmailReveal.sumble_person_id == person_id,
        EmailReveal.status.in_(tuple(TERMINAL_STATUSES)),
    )
    if exclude_contact_id:
        q = q.filter(EmailReveal.contact_id != exclude_contact_id)
    return q.order_by(EmailReveal.created_at.desc()).first()
def preview_reveal(db: Session, contact: Contact) -> EmailRevealResponse:
    existing = db.query(EmailReveal).filter(EmailReveal.contact_id == contact.id).one_or_none()
    if existing is not None and is_terminal(existing):
        return _terminal_response(contact.id, existing)
    global_hit = _global_person_reveal(db, contact.sumble_person_id, exclude_contact_id=contact.id)
    if global_hit is not None:
        return EmailRevealResponse(contact_id=contact.id, cost_credits=0, cached=True, status="preview", email=global_hit.email if global_hit.status == "revealed" else None)
    return EmailRevealResponse(contact_id=contact.id, cost_credits=sumble.EMAIL_REVEAL_COST, cached=False, status="preview")
def confirm_reveal(db: Session, contact: Contact) -> EmailRevealResponse:
    _begin_immediate(db)
    not_found_err: ValidationError | None = None
    try:
        existing = db.query(EmailReveal).filter(EmailReveal.contact_id == contact.id).one_or_none()
        if existing is not None and is_terminal(existing):
            db.rollback()
            if existing.status == "not_found":
                raise _cached_not_found_error(contact.id, existing)
            return _terminal_response(contact.id, existing)
        if existing is not None and existing.status == "pending":
            db.rollback()
            raise ValidationError(
                "Email reveal already in progress for this contact",
                details={"contact_id": contact.id, "status": existing.status},
            )
        if existing is None:
            existing = EmailReveal(
                contact_id=contact.id,
                sumble_person_id=contact.sumble_person_id,
                status="pending",
            )
            db.add(existing)
            try:
                db.flush()
            except IntegrityError:
                db.rollback()
                _begin_immediate(db)
                existing = db.query(EmailReveal).filter(EmailReveal.contact_id == contact.id).one()
                if is_terminal(existing):
                    if existing.status == "not_found":
                        raise _cached_not_found_error(contact.id, existing)
                    return _terminal_response(contact.id, existing)
                raise ValidationError(
                    "Email reveal already in progress for this contact",
                    details={"contact_id": contact.id, "status": existing.status},
                )
        global_hit = _global_person_reveal(db, contact.sumble_person_id, exclude_contact_id=contact.id)
        if global_hit is not None:
            existing.email = global_hit.email
            existing.cost_credits = 0
            existing.status = global_hit.status
            existing.revealed_at = global_hit.revealed_at
            existing.sumble_person_id = contact.sumble_person_id
            db.add(existing)
            db.commit()
            db.refresh(existing)
            if existing.status == "not_found":
                raise _cached_not_found_error(contact.id, existing)
            return EmailRevealResponse(contact_id=contact.id, cached=True, email=existing.email, cost_credits=0, status=existing.status)
        email, credits_used = sumble.reveal_email(int(contact.sumble_person_id))
        now = datetime.now(UTC)
        existing.email = email
        existing.cost_credits = credits_used
        existing.status = "revealed" if email else "not_found"
        existing.revealed_at = now if email else None
        existing.sumble_person_id = contact.sumble_person_id
        db.add(existing)
        db.commit()
        db.refresh(existing)
        if not email:
            not_found_err = ValidationError(
                "No email found for this contact",
                details={
                    "contact_id": contact.id,
                    "status": existing.status,
                    "cost_credits": existing.cost_credits,
                    "cached": True,
                },
            )
        else:
            return EmailRevealResponse(
                contact_id=contact.id,
                cached=False,
                email=email,
                cost_credits=existing.cost_credits,
                status=existing.status,
            )
    except Exception:
        db.rollback()
        raise
    if not_found_err is not None:
        raise not_found_err
    raise RuntimeError("unexpected reveal state")
