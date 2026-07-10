from typing import Any
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.workspace import ensure_workspace, load_prefs, require_workspace_id, save_prefs
from app.db.session import get_db
router = APIRouter(tags=["workspace"])
class WorkspaceOut(BaseModel):
    workspace_id: str
    ttl_days: int
    prefs: dict[str, Any] = Field(default_factory=dict)
class PrefsPatch(BaseModel):
    filter_hint_dismissed: bool | None = None
@router.get("/workspace", response_model=WorkspaceOut)
def get_workspace(db: Session = Depends(get_db)) -> WorkspaceOut:
    wid = require_workspace_id()
    row = ensure_workspace(db, wid)
    return WorkspaceOut(workspace_id=wid, ttl_days=int(settings.WORKSPACE_TTL_DAYS), prefs=load_prefs(row))
@router.patch("/workspace/prefs", response_model=WorkspaceOut)
def patch_workspace_prefs(payload: PrefsPatch, db: Session = Depends(get_db)) -> WorkspaceOut:
    wid = require_workspace_id()
    data = payload.model_dump(exclude_none=True)
    prefs = save_prefs(db, wid, data)
    return WorkspaceOut(workspace_id=wid, ttl_days=int(settings.WORKSPACE_TTL_DAYS), prefs=prefs)
