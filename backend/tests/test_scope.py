"""Scope gate tests: clean tree passes; deliberate fixtures fail with named codes."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCOPE_SCRIPT = REPO_ROOT / "scripts" / "check_scope.py"

# Import check functions for isolated fixture assertions
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import check_scope  # noqa: E402


def _run_scope(root: Path | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(SCOPE_SCRIPT)]
    if root is not None:
        cmd.extend(["--root", str(root)])
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))


def test_clean_repo_passes_via_subprocess() -> None:
    proc = _run_scope()
    assert proc.returncode == 0, f"clean repo must pass check_scope\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"


def test_clean_repo_passes_via_import() -> None:
    violations = check_scope.run_all_checks(REPO_ROOT)
    assert violations == [], "\n".join(violations)


def _minimal_scaffold(tmp: Path) -> None:
    """Enough structure for structure-lock + allowlists for fixture tests."""
    for d in check_scope.ALLOWED_TOP_DIRS:
        (tmp / d).mkdir(parents=True, exist_ok=True)
    app = tmp / "backend" / "app"
    for d in check_scope.ALLOWED_APP_SUBDIRS:
        (app / d).mkdir(parents=True, exist_ok=True)
    (app / "prompts" / ".gitkeep").write_text("")
    (app / "main.py").write_text("app = None\n")
    (app / "services" / "__init__.py").write_text("")
    (tmp / "backend" / "requirements.txt").write_text("fastapi>=0.115\n")
    (tmp / "scripts" / "allowed_deps_backend.txt").write_text("fastapi  # api\n")
    (tmp / "scripts" / "allowed_deps_frontend.txt").write_text("next  # framework\nreact  # ui\nreact-dom  # dom\n")
    (tmp / "scripts" / "except_allowlist.txt").write_text("# none\n")
    (tmp / "frontend" / "package.json").write_text(
        json.dumps(
            {
                "name": "fixture",
                "dependencies": {"next": "16", "react": "19", "react-dom": "19"},
                "devDependencies": {},
            }
        )
    )
    (tmp / "frontend" / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n")
    for sub in ("app", "components", "hooks", "lib"):
        (tmp / "frontend" / sub).mkdir(parents=True, exist_ok=True)
    (tmp / "evals" / "thresholds.json").write_text(
        json.dumps(
            {
                "ndcg_at_10": 0.85,
                "mrr": 0.8,
                "resume_pick_correct": 4,
                "resume_pick_total": 5,
            }
        )
    )
    wf = tmp / ".github" / "workflows"
    wf.mkdir(parents=True, exist_ok=True)
    (wf / "ci.yml").write_text(
        textwrap.dedent(
            """
            jobs:
              scope:
                runs-on: ubuntu-latest
                steps:
                  - run: python3 scripts/check_scope.py
              backend:
                needs: scope
                runs-on: ubuntu-latest
                steps:
                  - run: pytest --cov=app --cov-fail-under=80
            """
        ).strip()
        + "\n"
    )


def test_fake_dep_named_violation(tmp_path: Path) -> None:
    _minimal_scaffold(tmp_path)
    req = tmp_path / "backend" / "requirements.txt"
    req.write_text(req.read_text() + "kafka-python>=2.0\n")
    viols = check_scope.check_backend_deps(tmp_path)
    assert any(v.startswith("DEP_NOT_ALLOWED:") and "kafka-python" in v for v in viols), viols
    proc = _run_scope(tmp_path)
    assert proc.returncode == 1
    assert "DEP_NOT_ALLOWED:" in proc.stderr


def test_bare_except_named_violation(tmp_path: Path) -> None:
    _minimal_scaffold(tmp_path)
    bad = tmp_path / "backend" / "app" / "services" / "bad.py"
    bad.write_text(
        textwrap.dedent(
            """
            def f():
                try:
                    1 / 0
                except Exception:
                    pass
            """
        ).strip()
        + "\n"
    )
    viols = check_scope.check_error_handling(tmp_path)
    assert any(v.startswith("BARE_EXCEPT:") for v in viols), viols
    proc = _run_scope(tmp_path)
    assert proc.returncode == 1
    assert "BARE_EXCEPT:" in proc.stderr


def test_new_top_level_dir_named_violation(tmp_path: Path) -> None:
    _minimal_scaffold(tmp_path)
    (tmp_path / "microservices").mkdir()
    viols = check_scope.check_structure(tmp_path)
    assert any(v.startswith("STRUCTURE_DRIFT:") and "microservices" in v for v in viols), viols
    proc = _run_scope(tmp_path)
    assert proc.returncode == 1
    assert "STRUCTURE_DRIFT:" in proc.stderr


def test_lowered_threshold_named_violation(tmp_path: Path) -> None:
    _minimal_scaffold(tmp_path)
    (tmp_path / "evals" / "thresholds.json").write_text(
        json.dumps(
            {
                "ndcg_at_10": 0.50,
                "mrr": 0.8,
                "resume_pick_correct": 4,
                "resume_pick_total": 5,
            }
        )
    )
    viols = check_scope.check_thresholds(tmp_path)
    assert any(v.startswith("THRESHOLD_FLOOR:") and "ndcg_at_10" in v for v in viols), viols
    proc = _run_scope(tmp_path)
    assert proc.returncode == 1
    assert "THRESHOLD_FLOOR:" in proc.stderr


def test_threshold_floors_match_script_constants() -> None:
    data = json.loads((REPO_ROOT / "evals" / "thresholds.json").read_text())
    for key, floor in check_scope.THRESHOLD_FLOORS.items():
        assert key in data
        assert float(data[key]) >= float(floor)


# --- Bypass-class regressions (review BUG-1/2/3/5/6) ---


def test_except_tuple_exception_is_flagged(tmp_path: Path) -> None:
    """BUG-3: except (Exception,): must not bypass BARE_EXCEPT."""
    _minimal_scaffold(tmp_path)
    bad = tmp_path / "backend" / "app" / "services" / "tuple_ex.py"
    bad.write_text(
        textwrap.dedent(
            """
            def f():
                try:
                    1 / 0
                except (Exception,):
                    pass
            """
        ).strip()
        + "\n"
    )
    viols = check_scope.check_error_handling(tmp_path)
    assert any(v.startswith("BARE_EXCEPT:") and "except Exception" in v for v in viols), viols


def test_except_base_exception_is_flagged(tmp_path: Path) -> None:
    _minimal_scaffold(tmp_path)
    bad = tmp_path / "backend" / "app" / "services" / "base_ex.py"
    bad.write_text(
        textwrap.dedent(
            """
            def f():
                try:
                    1 / 0
                except BaseException:
                    pass
            """
        ).strip()
        + "\n"
    )
    viols = check_scope.check_error_handling(tmp_path)
    assert any(v.startswith("BARE_EXCEPT:") and "BaseException" in v for v in viols), viols


def test_exception_allowlist_does_not_cover_bare_except(tmp_path: Path) -> None:
    """BUG-1: allowlist `except Exception` must not permit bare `except:`."""
    _minimal_scaffold(tmp_path)
    target = tmp_path / "backend" / "app" / "services" / "email_reveal.py"
    target.write_text(
        textwrap.dedent(
            """
            def f():
                try:
                    1 / 0
                except:
                    raise
            """
        ).strip()
        + "\n"
    )
    (tmp_path / "scripts" / "except_allowlist.txt").write_text(
        "backend/app/services/email_reveal.py:except Exception  # only Exception\n"
    )
    viols = check_scope.check_error_handling(tmp_path)
    assert any(v.startswith("BARE_EXCEPT:") and "except:" in v for v in viols), (
        f"bare except must still fail under Exception-only allowlist: {viols}"
    )


def test_exception_allowlist_covers_exact_exception_only(tmp_path: Path) -> None:
    _minimal_scaffold(tmp_path)
    target = tmp_path / "backend" / "app" / "services" / "email_reveal.py"
    target.write_text(
        textwrap.dedent(
            """
            def f():
                try:
                    1 / 0
                except Exception:
                    raise
            """
        ).strip()
        + "\n"
    )
    (tmp_path / "scripts" / "except_allowlist.txt").write_text(
        "backend/app/services/email_reveal.py:except Exception  # rollback\n"
    )
    viols = check_scope.check_error_handling(tmp_path)
    assert viols == [], viols


def test_ci_comment_only_cov_fail_under_is_rejected(tmp_path: Path) -> None:
    """BUG-2: YAML comment # --cov-fail-under=80 must not satisfy the gate."""
    _minimal_scaffold(tmp_path)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(
        textwrap.dedent(
            """
            jobs:
              scope:
                runs-on: ubuntu-latest
                steps:
                  - run: python3 scripts/check_scope.py
              backend:
                needs: scope
                runs-on: ubuntu-latest
                steps:
                  # --cov-fail-under=80
                  - run: pytest -q
            """
        ).strip()
        + "\n"
    )
    viols = check_scope.check_ci_coverage_gate(tmp_path)
    assert any(v.startswith("CI_COVERAGE:") for v in viols), viols
    assert not any("OK" in v for v in viols)


def test_ci_weak_live_cov_not_rescued_by_comment(tmp_path: Path) -> None:
    """BUG-2: live --cov-fail-under=50 + comment 80 must fail."""
    _minimal_scaffold(tmp_path)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(
        textwrap.dedent(
            """
            jobs:
              scope:
                runs-on: ubuntu-latest
                steps:
                  - run: python3 scripts/check_scope.py
              backend:
                needs: scope
                runs-on: ubuntu-latest
                steps:
                  # leftover: --cov-fail-under=80
                  - run: pytest --cov=app --cov-fail-under=50
            """
        ).strip()
        + "\n"
    )
    viols = check_scope.check_ci_coverage_gate(tmp_path)
    assert any("50" in v and v.startswith("CI_COVERAGE:") for v in viols), viols


def test_ci_job_missing_needs_scope(tmp_path: Path) -> None:
    """BUG-6 / SUGGESTION-4: non-scope jobs must needs: scope."""
    _minimal_scaffold(tmp_path)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(
        textwrap.dedent(
            """
            jobs:
              scope:
                runs-on: ubuntu-latest
                steps:
                  - run: python3 scripts/check_scope.py
              backend:
                runs-on: ubuntu-latest
                steps:
                  - run: pytest --cov=app --cov-fail-under=80
            """
        ).strip()
        + "\n"
    )
    viols = check_scope.check_ci_coverage_gate(tmp_path)
    assert any("needs: scope" in v and "backend" in v for v in viols), viols


def test_allowlist_requires_why_comment(tmp_path: Path) -> None:
    """BUG-6: package lines without # why must fail."""
    _minimal_scaffold(tmp_path)
    (tmp_path / "scripts" / "allowed_deps_backend.txt").write_text("fastapi\n")
    viols = check_scope.check_backend_deps(tmp_path)
    assert any("missing # why" in v for v in viols), viols


def test_banned_term_in_frontend_lib(tmp_path: Path) -> None:
    """BUG-5: frontend/lib is app surface for banned terms."""
    _minimal_scaffold(tmp_path)
    (tmp_path / "frontend" / "lib" / "evil.ts").write_text("export const SAMPLE_JOBS = [];\n")
    viols = check_scope.check_banned_terms(tmp_path)
    assert any(v.startswith("BANNED_TERM:") and "frontend/lib" in v and "SAMPLE_JOBS" in v for v in viols), viols


def test_banned_import_in_frontend_hooks(tmp_path: Path) -> None:
    """BUG-5: frontend/hooks scanned for banned imports."""
    _minimal_scaffold(tmp_path)
    (tmp_path / "frontend" / "hooks" / "useRedis.ts").write_text("import redis from 'redis';\n")
    viols = check_scope.check_banned_terms(tmp_path)
    assert any(v.startswith("BANNED_IMPORT:") and "hooks" in v and "redis" in v for v in viols), viols


def test_secondary_requirements_file_scanned(tmp_path: Path) -> None:
    """SUGGESTION-2: requirements-dev.txt cannot smuggle banned deps."""
    _minimal_scaffold(tmp_path)
    (tmp_path / "backend" / "requirements-dev.txt").write_text("celery>=5\n")
    viols = check_scope.check_backend_deps(tmp_path)
    assert any("celery" in v and "DEP_NOT_ALLOWED" in v for v in viols), viols


def test_resume_prompt_lives_under_prompts_dir() -> None:
    """BUG-4: clean tree models prompt discipline (file + frontmatter + loader)."""
    prompt = REPO_ROOT / "backend" / "app" / "prompts" / "resume_schema.md"
    assert prompt.is_file()
    text = prompt.read_text(encoding="utf-8")
    assert text.startswith("---")
    assert "name:" in text.split("---", 2)[1]
    assert "version:" in text.split("---", 2)[1]
    # services must not embed the old multi-line schema constant
    parser = (REPO_ROOT / "backend" / "app" / "services" / "parser.py").read_text()
    assert "Extract a structured resume profile" not in parser
    assert "load_prompt" in parser


# --- SUGGESTION-R1 / R2 regressions ---


def test_ci_echo_faked_coverage_is_rejected(tmp_path: Path) -> None:
    """SUGGESTION-R1: echo \"pytest --cov=app --cov-fail-under=80\" must fail."""
    _minimal_scaffold(tmp_path)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(
        textwrap.dedent(
            """
            jobs:
              scope:
                runs-on: ubuntu-latest
                steps:
                  - run: python3 scripts/check_scope.py
              backend:
                needs: scope
                runs-on: ubuntu-latest
                steps:
                  - run: echo "pytest --cov=app --cov-fail-under=80"
            """
        ).strip()
        + "\n"
    )
    viols = check_scope.check_ci_coverage_gate(tmp_path)
    assert any(v.startswith("CI_COVERAGE:") for v in viols), viols
    assert any("echo" in v.lower() or "pytest" in v for v in viols), viols


def test_ci_echo_flags_then_plain_pytest_is_rejected(tmp_path: Path) -> None:
    """SUGGESTION-R1: multi-line echo flags + bare pytest -q must not satisfy cov gate."""
    _minimal_scaffold(tmp_path)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(
        textwrap.dedent(
            """
            jobs:
              scope:
                runs-on: ubuntu-latest
                steps:
                  - run: python3 scripts/check_scope.py
              backend:
                needs: scope
                runs-on: ubuntu-latest
                steps:
                  - run: |
                      echo --cov=app --cov-fail-under=80
                      pytest -q
            """
        ).strip()
        + "\n"
    )
    viols = check_scope.check_ci_coverage_gate(tmp_path)
    assert any(v.startswith("CI_COVERAGE:") for v in viols), viols


def test_ci_echo_bare_check_scope_is_rejected(tmp_path: Path) -> None:
    """SUGGESTION-R1: echo check_scope (no .py path) must not satisfy scope job."""
    _minimal_scaffold(tmp_path)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(
        textwrap.dedent(
            """
            jobs:
              scope:
                runs-on: ubuntu-latest
                steps:
                  - run: echo check_scope
              backend:
                needs: scope
                runs-on: ubuntu-latest
                steps:
                  - run: pytest --cov=app --cov-fail-under=80
            """
        ).strip()
        + "\n"
    )
    viols = check_scope.check_ci_coverage_gate(tmp_path)
    assert any("scope" in v.lower() and "check_scope.py" in v for v in viols), viols


def test_path_matches_allow_no_suffix_collision() -> None:
    """SUGGESTION-R2: bare endswith must not match not_email_reveal.py."""
    assert check_scope.path_matches_allow(
        "backend/app/services/email_reveal.py",
        "backend/app/services/email_reveal.py",
    )
    assert check_scope.path_matches_allow(
        "backend/app/services/email_reveal.py",
        "email_reveal.py",
    )
    assert not check_scope.path_matches_allow(
        "backend/app/services/not_email_reveal.py",
        "email_reveal.py",
    )
    assert not check_scope.path_matches_allow(
        "backend/app/services/not_email_reveal.py",
        "backend/app/services/email_reveal.py",
    )


def test_except_allowlist_no_suffix_collision(tmp_path: Path) -> None:
    """SUGGESTION-R2: allowlist for email_reveal.py must not cover not_email_reveal.py."""
    _minimal_scaffold(tmp_path)
    bad = tmp_path / "backend" / "app" / "services" / "not_email_reveal.py"
    bad.write_text(
        textwrap.dedent(
            """
            def f():
                try:
                    1 / 0
                except Exception:
                    pass
            """
        ).strip()
        + "\n"
    )
    (tmp_path / "scripts" / "except_allowlist.txt").write_text(
        "email_reveal.py:except Exception  # only the real file\n"
    )
    viols = check_scope.check_error_handling(tmp_path)
    assert any(v.startswith("BARE_EXCEPT:") and "not_email_reveal.py" in v for v in viols), viols
