import re
from dataclasses import dataclass, field

import httpx
from app.core.config import settings
from app.core.env_utils import is_set
from app.core.http_timeouts import default_timeout, drive_download_timeout
from app.core.redact import drive_user_reason, format_httpx_error, redact_error
from app.errors import ServiceFailingError, ServiceNotConfiguredError, ValidationError

_DRIVE_FOLDER_RE = re.compile(r"/folders/([a-zA-Z0-9_-]+)")
_DRIVE_API = "https://www.googleapis.com/drive/v3"
_ALLOWED_MIME = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}
_GOOGLE_APPS_PREFIX = "application/vnd.google-apps."
NATIVE_GOOGLE_REASON = "Google Docs format — download as PDF and re-add"


@dataclass(frozen=True)
class DriveFile:
    file_id: str
    name: str
    mime_type: str
    modified_time: str


@dataclass(frozen=True)
class DriveSkippedFile:
    """Non-ingestible listing entry with a plain-language reason."""

    file_id: str
    name: str
    mime_type: str
    reason: str


@dataclass(frozen=True)
class FolderListResult:
    supported_files: list[DriveFile]
    files_ignored: int
    skipped_native: list[DriveSkippedFile] = field(default_factory=list)


def parse_folder_id(folder_url: str) -> str:
    url = folder_url.strip()
    if not url:
        raise ValidationError("Drive folder URL is required")
    match = _DRIVE_FOLDER_RE.search(url)
    if match is None:
        raise ValidationError(
            "Invalid Google Drive folder URL — expected https://drive.google.com/drive/folders/<id>",
            details={"folder_url": folder_url},
        )
    return match.group(1)


def _require_drive_config() -> None:
    if is_set(settings.GOOGLE_DRIVE_API_KEY):
        return
    oauth = (
        settings.GOOGLE_DRIVE_CLIENT_ID,
        settings.GOOGLE_DRIVE_CLIENT_SECRET,
        settings.GOOGLE_DRIVE_REFRESH_TOKEN,
    )
    if all(is_set(v) for v in oauth):
        return
    raise ServiceNotConfiguredError(
        "Google Drive",
        "GOOGLE_DRIVE_API_KEY (public folder) or GOOGLE_DRIVE_CLIENT_ID/SECRET/REFRESH_TOKEN",
    )


def _oauth_access_token() -> str:
    _require_drive_config()
    if not all(
        is_set(v)
        for v in (
            settings.GOOGLE_DRIVE_CLIENT_ID,
            settings.GOOGLE_DRIVE_CLIENT_SECRET,
            settings.GOOGLE_DRIVE_REFRESH_TOKEN,
        )
    ):
        raise ServiceNotConfiguredError("Google Drive", "GOOGLE_DRIVE_CLIENT_ID/SECRET/REFRESH_TOKEN")
    payload = {
        "client_id": settings.GOOGLE_DRIVE_CLIENT_ID,
        "client_secret": settings.GOOGLE_DRIVE_CLIENT_SECRET,
        "refresh_token": settings.GOOGLE_DRIVE_REFRESH_TOKEN,
        "grant_type": "refresh_token",
    }
    try:
        with httpx.Client(timeout=default_timeout()) as client:
            response = client.post("https://oauth2.googleapis.com/token", data=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        raise ServiceFailingError(
            "Google Drive", f"OAuth token refresh failed: {format_httpx_error(exc)}"
        ) from exc
    token = data.get("access_token")
    if not token:
        raise ServiceFailingError("Google Drive", "OAuth token refresh returned no access_token")
    return str(token)


def _auth_params() -> dict[str, str]:
    if is_set(settings.GOOGLE_DRIVE_API_KEY):
        return {"key": settings.GOOGLE_DRIVE_API_KEY or ""}
    return {}


def _auth_headers() -> dict[str, str]:
    if is_set(settings.GOOGLE_DRIVE_API_KEY):
        return {}
    return {"Authorization": f"Bearer {_oauth_access_token()}"}


def _raise_drive_http(exc: httpx.HTTPError) -> None:
    """Raise ServiceFailingError with host/status only — never key-bearing URLs."""
    raise ServiceFailingError("Google Drive", format_httpx_error(exc)) from exc


def list_folder_files(folder_id: str) -> FolderListResult:
    _require_drive_config()
    query = f"'{folder_id}' in parents and trashed=false"
    supported: list[DriveFile] = []
    skipped_native: list[DriveSkippedFile] = []
    ignored = 0
    page_token: str | None = None
    try:
        with httpx.Client(timeout=default_timeout()) as client:
            while True:
                params = {
                    "q": query,
                    "fields": "nextPageToken,files(id,name,mimeType,modifiedTime)",
                    "pageSize": 200,
                    **_auth_params(),
                }
                if page_token:
                    params["pageToken"] = page_token
                response = client.get(
                    f"{_DRIVE_API}/files",
                    params=params,
                    headers=_auth_headers(),
                )
                response.raise_for_status()
                payload = response.json()
                raw_files = payload.get("files")
                if not isinstance(raw_files, list):
                    raise ServiceFailingError("Google Drive", "unexpected files response")
                for item in raw_files:
                    if not isinstance(item, dict):
                        continue
                    mime = str(item.get("mimeType") or "")
                    file_id = str(item.get("id") or "").strip()
                    name = str(item.get("name") or "").strip() or file_id or "unknown"
                    modified_time = str(item.get("modifiedTime") or "").strip()
                    if mime.startswith(_GOOGLE_APPS_PREFIX):
                        # Native Docs/Sheets/Slides — cannot download as binary without export.
                        skipped_native.append(
                            DriveSkippedFile(
                                file_id=file_id or name,
                                name=name,
                                mime_type=mime,
                                reason=NATIVE_GOOGLE_REASON,
                            )
                        )
                        continue
                    if mime not in _ALLOWED_MIME:
                        ignored += 1
                        continue
                    if file_id and name and modified_time:
                        supported.append(
                            DriveFile(
                                file_id=file_id,
                                name=name,
                                mime_type=mime,
                                modified_time=modified_time,
                            )
                        )
                page_token = payload.get("nextPageToken")
                if not page_token:
                    break
    except httpx.HTTPError as exc:
        _raise_drive_http(exc)
    return FolderListResult(
        supported_files=supported,
        files_ignored=ignored,
        skipped_native=skipped_native,
    )


def download_file(file_id: str) -> bytes:
    _require_drive_config()
    params = {"alt": "media", **_auth_params()}
    try:
        with httpx.Client(timeout=drive_download_timeout()) as client:
            response = client.get(
                f"{_DRIVE_API}/files/{file_id}",
                params=params,
                headers=_auth_headers(),
            )
            response.raise_for_status()
            return response.content
    except httpx.HTTPError as exc:
        _raise_drive_http(exc)
    raise ServiceFailingError("Google Drive", "download failed")  # pragma: no cover


def user_reason_for_download_error(exc: BaseException) -> str:
    """Map a download failure to a plain-language library UI reason (already redacted)."""
    status = None
    if isinstance(exc, ServiceFailingError):
        # Parse HTTP status from redacted reason if present
        m = re.search(r"HTTP\s+(\d{3})", exc.message or "")
        if m:
            status = int(m.group(1))
        return drive_user_reason(exc.message, status_code=status)
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        return drive_user_reason(exc, status_code=exc.response.status_code)
    return drive_user_reason(redact_error(exc))
