"""Container liveness probe: /livez 200 means alive."""

from __future__ import annotations

import urllib.error
from unittest.mock import MagicMock, patch

from app.livez_probe import main


def test_livez_ok_on_200() -> None:
    with patch("app.livez_probe.urllib.request.urlopen", return_value=MagicMock()):
        assert main() == 0


def test_livez_fails_on_503() -> None:
    # /livez should not return 503; any non-200 is failure for this probe.
    err = urllib.error.HTTPError(
        url="http://127.0.0.1:8000/livez",
        code=503,
        msg="Service Unavailable",
        hdrs=None,  # type: ignore[arg-type]
        fp=None,
    )
    with patch("app.livez_probe.urllib.request.urlopen", side_effect=err):
        assert main() == 1


def test_livez_fails_on_500() -> None:
    err = urllib.error.HTTPError(
        url="http://127.0.0.1:8000/livez",
        code=500,
        msg="Internal",
        hdrs=None,  # type: ignore[arg-type]
        fp=None,
    )
    with patch("app.livez_probe.urllib.request.urlopen", side_effect=err):
        assert main() == 1


def test_livez_fails_on_connection_error() -> None:
    with patch(
        "app.livez_probe.urllib.request.urlopen",
        side_effect=urllib.error.URLError("connection refused"),
    ):
        assert main() == 1
