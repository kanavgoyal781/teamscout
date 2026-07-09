"""Atomic email reveal with SQLite billing lock and terminal cache."""

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


def preview_reveal(db: Session, contact: Contact) -> EmailRevealResponse:
    existing = db.query(EmailReveal).filter(EmailReveal.contact_id == contact.id).one_or_none()
    if existing is not None and is_terminal(existing):
        return _terminal_response(contact.id, existing)

    return EmailRevealResponse(
        contact_id=contact.id,
        cost_credits=sumble.EMAIL_REVEAL_COST,
        cached=False,
        status="preview",
    )


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
            # Set not_found terminal and commit BEFORE raising so the record survives.
            # Raise AFTER the try/except block below to prevent outer rollback from
            # destroying the terminal cached state (fixes double-charge on not_found).
            not_found_err = ValidationError(
                "No email found for this contact",
                details={
                    "contact_id": contact.id,
                    "status": existing.status,
                    "cost_credits": existing.cost_credits,
                    "cached": True,
                },
            )
            # fall to post-try raise
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
    # Unreachable: revealed path returns inside try; not_found raises above.
    raise RuntimeError("unexpected reveal state")
