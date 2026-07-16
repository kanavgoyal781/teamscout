from __future__ import annotations

import json
import secrets
import shutil
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import (
    Contact,
    DriveSyncedFile,
    DriveSyncState,
    Feedback,
    IntentSearch,
    JobCache,
    JobTeamSearch,
    Resume,
    ResumeUnit,
    Search,
    TeamExtractionRecord,
    Workspace,
)
from app.db.session import SessionLocal, ensure_db

COOKIE_NAME = "ts_workspace"
SYSTEM_WORKSPACE = "__system__"
_SKIP_PATHS = frozenset({"/livez", "/health"})
_workspace_cv: ContextVar[str | None] = ContextVar("workspace_id", default=None)
_last_sweep_day: str | None = None
_sweep_lock = Lock()
logger = get_logger(__name__)


def current_workspace_id() -> str | None:
    return _workspace_cv.get()


def require_workspace_id() -> str:
    wid = _workspace_cv.get()
    if not wid:
        raise RuntimeError("workspace_id missing from request context")
    return wid


def workspace_or_system() -> str:
    return _workspace_cv.get() or SYSTEM_WORKSPACE


def mint_workspace_id() -> str:
    return secrets.token_urlsafe(32)


def parse_cookie_header(header: str | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if not header:
        return out
    for part in header.split(";"):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def cookie_samesite() -> str:
    raw = (getattr(settings, "WORKSPACE_COOKIE_SAMESITE", None) or "").strip().lower()
    if raw in {"lax", "none", "strict"}:
        return raw.capitalize() if raw != "none" else "None"
    return "None" if settings.is_prod else "Lax"


def cookie_header_value(workspace_id: str) -> str:
    parts = [f"{COOKIE_NAME}={workspace_id}", "Path=/", "HttpOnly", f"SameSite={cookie_samesite()}"]
    if settings.is_prod or cookie_samesite() == "None":
        parts.append("Secure")
    max_age = int(settings.WORKSPACE_TTL_DAYS) * 86400
    parts.append(f"Max-Age={max_age}")
    return "; ".join(parts)


def uploads_root() -> Path:
    return Path(__file__).resolve().parents[2] / "uploads"


def workspace_upload_dir(workspace_id: str) -> Path:
    d = uploads_root() / workspace_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def workspace_upload_path(workspace_id: str, file_hash: str, filename: str) -> Path:
    safe = Path(filename).name or "upload.bin"
    return workspace_upload_dir(workspace_id) / f"{file_hash}_{safe}"


def ensure_workspace(db: Session, workspace_id: str, *, now: datetime | None = None) -> Workspace:
    ts = now or datetime.now(UTC).replace(tzinfo=None)
    row = db.query(Workspace).filter(Workspace.id == workspace_id).one_or_none()
    if row is None:
        row = Workspace(id=workspace_id, created_at=ts, last_seen_at=ts, prefs_json="{}")
        db.add(row)
    else:
        row.last_seen_at = ts
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def load_prefs(row: Workspace) -> dict[str, Any]:
    try:
        data = json.loads(row.prefs_json or "{}")
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def save_prefs(db: Session, workspace_id: str, prefs: dict[str, Any]) -> dict[str, Any]:
    row = ensure_workspace(db, workspace_id)
    merged = load_prefs(row)
    merged.update(prefs)
    row.prefs_json = json.dumps(merged, sort_keys=True)
    db.add(row)
    db.commit()
    return merged


def sweep_expired_workspaces(*, now: datetime | None = None) -> int:
    ensure_db()
    ts = now or datetime.now(UTC).replace(tzinfo=None)
    cutoff = ts - timedelta(days=int(settings.WORKSPACE_TTL_DAYS))
    db = SessionLocal()
    deleted = 0
    try:
        expired = db.query(Workspace).filter(Workspace.last_seen_at < cutoff).all()
        for ws in expired:
            wid = ws.id
            file_paths = [r[0] for r in db.query(Resume.file_path).filter(Resume.workspace_id == wid).all() if r[0]]
            for model in (
                ResumeUnit,
                Contact,
                TeamExtractionRecord,
                JobTeamSearch,
                Search,
                IntentSearch,
                Feedback,
                JobCache,
                DriveSyncedFile,
                DriveSyncState,
                Resume,
            ):
                db.query(model).filter(model.workspace_id == wid).delete(synchronize_session=False)  # type: ignore[attr-defined]
            db.delete(ws)
            deleted += 1
            for fp in file_paths:
                try:
                    Path(fp).unlink(missing_ok=True)
                except OSError as exc:
                    logger.warning("workspace.file_delete_failed", path=fp, error=str(exc))
            ws_dir = uploads_root() / wid
            if ws_dir.is_dir():
                shutil.rmtree(ws_dir, ignore_errors=True)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    finally:
        db.close()
    if deleted:
        logger.info("workspace.ttl_sweep", deleted=deleted, cutoff=cutoff.isoformat())
    return deleted


def maybe_sweep_expired(*, now: datetime | None = None, force: bool = False) -> int:
    global _last_sweep_day
    ts = now or datetime.now(UTC).replace(tzinfo=None)
    day = ts.date().isoformat()
    with _sweep_lock:
        if not force and _last_sweep_day == day:
            return 0
        _last_sweep_day = day
    return sweep_expired_workspaces(now=ts)


class WorkspaceMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path") or ""
        if path in _SKIP_PATHS:
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        cookies = parse_cookie_header(headers.get("cookie"))
        raw = cookies.get(COOKIE_NAME, "").strip()
        if raw and len(raw) >= 16 and all(c.isalnum() or c in "-_" for c in raw):
            workspace_id = raw
        else:
            workspace_id = mint_workspace_id()
        state = scope.setdefault("state", {})
        if isinstance(state, dict):
            state["workspace_id"] = workspace_id
        token = _workspace_cv.set(workspace_id)
        maybe_sweep_expired()
        try:
            ensure_db()
            db = SessionLocal()
            try:
                ensure_workspace(db, workspace_id)
            finally:
                db.close()
        except SQLAlchemyError as exc:
            logger.warning("workspace.ensure_failed", error=str(exc))

        async def send_wrapper(message: dict[str, Any]) -> None:
            # Always refresh Max-Age so cookie TTL slides with activity
            if message["type"] == "http.response.start":
                raw_headers = list(message.get("headers") or [])
                raw_headers = [
                    (n, v)
                    for n, v in raw_headers
                    if n.decode("latin-1").lower() != "set-cookie" or COOKIE_NAME.encode("latin-1") not in v
                ]
                raw_headers.append((b"set-cookie", cookie_header_value(workspace_id).encode("latin-1")))
                message = {**message, "headers": raw_headers}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            _workspace_cv.reset(token)
