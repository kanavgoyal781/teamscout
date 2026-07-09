"""Container HEALTHCHECK helper: process liveness via GET /livez.

/livez always returns 200 when the app process can serve HTTP.
Readiness (integrations + DB) is GET /health and is not used here —
degraded config must not kill the container (Fly uses the same /livez path).
"""

from __future__ import annotations

import urllib.error
import urllib.request


def main() -> int:
    try:
        urllib.request.urlopen("http://127.0.0.1:8000/livez", timeout=3)
        return 0
    except urllib.error.HTTPError as exc:
        return 0 if exc.code == 200 else 1
    except (urllib.error.URLError, TimeoutError, OSError):
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
