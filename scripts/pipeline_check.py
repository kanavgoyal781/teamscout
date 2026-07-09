#!/usr/bin/env python3
"""TeamScout product pipeline gate (offline-first, optional live).

Runs the coherent quality path for this repo's definition of production-grade —
scope, backend unit tests, offline fit-signal evals — not a distributed training stack.

Order (default):
  1. scripts/check_scope.py
  2. backend pytest -q (backend unit tests; frontend covered separately in CI)
  3. scripts/eval_fit_signals.py (offline; no embeddings/LLM)
  4. If embeddings are configured (repo-root .env or process env):
       eval_ranking.py + eval_resume_pick.py + eval_report.py
       (both scripts hard-require embeddings; LLM is optional — they note and continue)
  5. If DEMO_API_BASE / BACKEND_URL is set: scripts/demo_check.py

Usage:
  python3 scripts/pipeline_check.py
  python3 scripts/pipeline_check.py --help
  python3 scripts/pipeline_check.py --skip-tests
  python3 scripts/pipeline_check.py --offline-only
  python3 scripts/pipeline_check.py --require-live
  python3 scripts/pipeline_check.py --require-ranking-eval
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


def _load_repo_dotenv() -> None:
    """Load repo-root .env into os.environ without overriding existing keys.

    Matches the project secret surface (backend Settings also reads this file).
    dotenv is a backend dep; fall back to a tiny parser if unavailable.
    """
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path, override=False)
        return
    except ImportError:
        pass

    # Minimal KEY=VALUE loader (no export/quotes expansion beyond simple strip)
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


def _step(name: str, cmd: list[str], *, cwd: Path | None = None) -> int:
    workdir = cwd or ROOT
    rel = workdir.relative_to(ROOT) if workdir != ROOT else Path(".")
    print()
    print(f"── {name}")
    print(f"   $ (cd {rel}) {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=workdir)
    status = "PASS" if result.returncode == 0 else "FAIL"
    print(f"[{status}] {name} (exit {result.returncode})")
    return result.returncode


def _embeddings_ready() -> bool:
    """Same readiness as eval_ranking / eval_resume_pick (embeddings key + endpoint).

    Uses app settings so .env-loaded values match the scripts that will run.
    """
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from app.core.config import settings
    from app.core.env_utils import is_set
    from app.services.embeddings import embeddings_endpoint

    return bool(is_set(settings.EMBEDDINGS_API_KEY) and embeddings_endpoint())


def _demo_base() -> str:
    return (os.environ.get("DEMO_API_BASE") or os.environ.get("BACKEND_URL") or "").strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run TeamScout pipeline checks: scope → backend unit tests → fit-signal eval "
            "(+ optional embeddings ranking/resume-pick evals and demo-check)."
        )
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip backend pytest (still runs scope + fit-signal eval).",
    )
    parser.add_argument(
        "--offline-only",
        action="store_true",
        help="Never run embeddings ranking evals or live demo-check, even if env is set.",
    )
    parser.add_argument(
        "--require-live",
        action="store_true",
        help="Fail if DEMO_API_BASE/BACKEND_URL is unset (forces demo-check).",
    )
    parser.add_argument(
        "--require-ranking-eval",
        action="store_true",
        help=(
            "Fail if embeddings are not configured "
            "(forces ranking + resume-pick evals; LLM optional)."
        ),
    )
    args = parser.parse_args(argv)

    _load_repo_dotenv()

    print("TeamScout pipeline_check")
    print(f"  root={ROOT}")
    print(f"  skip_tests={args.skip_tests} offline_only={args.offline_only}")

    failures: list[str] = []

    if _step("scope", [sys.executable, "scripts/check_scope.py"]) != 0:
        failures.append("scope")

    if not args.skip_tests:
        if (
            _step(
                "backend unit tests",
                [sys.executable, "-m", "pytest", "-q"],
                cwd=BACKEND,
            )
            != 0
        ):
            failures.append("backend unit tests")

    if (
        _step("eval fit-signals (offline)", [sys.executable, "scripts/eval_fit_signals.py"])
        != 0
    ):
        failures.append("eval_fit_signals")

    if not args.offline_only:
        emb_ok = _embeddings_ready()
        if emb_ok:
            # Both scripts hard-require embeddings; LLM is optional (NOTE + continue).
            if _step("eval ranking", [sys.executable, "scripts/eval_ranking.py"]) != 0:
                failures.append("eval_ranking")
            if (
                _step("eval resume-pick", [sys.executable, "scripts/eval_resume_pick.py"])
                != 0
            ):
                failures.append("eval_resume_pick")
            if _step("eval report", [sys.executable, "scripts/eval_report.py"]) != 0:
                failures.append("eval_report")
        elif args.require_ranking_eval:
            print(
                "[FAIL] --require-ranking-eval set but embeddings not configured "
                "(need EMBEDDINGS_API_KEY and EMBEDDINGS_API or LLM_API_BASE; "
                "repo-root .env is loaded)"
            )
            failures.append("ranking-eval-secrets")
        else:
            print()
            print(
                "[SKIP] ranking + resume-pick evals "
                "(need EMBEDDINGS_API_KEY and EMBEDDINGS_API or LLM_API_BASE; "
                "repo-root .env is loaded automatically; LLM optional)"
            )

        base = _demo_base()
        if base:
            if _step("demo-check (live)", [sys.executable, "scripts/demo_check.py"]) != 0:
                failures.append("demo_check")
        elif args.require_live:
            print("[FAIL] --require-live set but DEMO_API_BASE / BACKEND_URL unset")
            failures.append("demo-base-missing")
        else:
            print()
            print(
                "[SKIP] demo-check "
                "(set DEMO_API_BASE=https://your-api.fly.dev to smoke the live deploy)"
            )
    else:
        print()
        print("[SKIP] embeddings ranking evals + demo-check (--offline-only)")

    print()
    if failures:
        print(f"PIPELINE FAIL: {', '.join(failures)}")
        return 1
    print("PIPELINE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
