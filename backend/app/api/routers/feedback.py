"""POST /feedback — thumbs + implicit signals for the learning loop."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.rate_limit import feedback_limit, limiter
from app.db.session import get_db
from app.schemas.feedback import FeedbackCreate, FeedbackResponse
from app.services import feedback_store

router = APIRouter(tags=["feedback"])


@router.post("/feedback", response_model=FeedbackResponse)
@limiter.limit(feedback_limit)
def create_feedback(
    request: Request,
    payload: FeedbackCreate,
    db: Session = Depends(get_db),
) -> FeedbackResponse:
    row = feedback_store.record_feedback(db, payload)
    return FeedbackResponse(
        id=row.id,
        kind=row.kind,
        target_type=row.target_type,
        target_id=row.target_id,
        created_at=row.created_at.isoformat() if row.created_at else None,
    )
