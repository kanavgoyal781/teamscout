"""Shared explicit httpx timeouts for outbound calls."""

from __future__ import annotations

import httpx

from app.core.config import settings

def default_timeout() -> httpx.Timeout:
    return httpx.Timeout(settings.HTTP_TIMEOUT_DEFAULT)

def embeddings_batch_timeout() -> httpx.Timeout:
    return httpx.Timeout(settings.HTTP_TIMEOUT_EMBEDDINGS_BATCH)

def drive_download_timeout() -> httpx.Timeout:
    return httpx.Timeout(settings.HTTP_TIMEOUT_DRIVE_DOWNLOAD)
