#!/usr/bin/env python3
"""TeamScout architectural scope gate (stdlib only).

Fails CI / `make check-scope` on named violations. Collects all violations
before exiting so fixers see the full set.

Usage:
  python scripts/check_scope.py
  python scripts/check_scope.py --root /path/to/repo   # test fixtures only

Env:
  TEAMSCOUT_SCOPE_ROOT  alternate repo root (overridden by --root)

Residual bypasses (not a security boundary — after the static gates):
  dynamic importlib / __import__ of banned modules;
  obfuscated string concatenation for banned terms;
  dishonest but present # why text (human review);
  TEAMSCOUT_SCOPE_ROOT / --root must not be set in CI.
See CONSTRAINTS.md.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Hard floors / budgets — do not raise in the name of convenience
# ---------------------------------------------------------------------------

SERVICE_FILE_MAX_LINES = 450
MAIN_MAX_LINES = 130
APP_LOC_MAX = 10100

THRESHOLD_FLOORS: dict[str, float | int] = {
    "ndcg_at_10": 0.85,
    "mrr": 0.8,
    "resume_pick_correct": 7,
    "resume_pick_total": 8,
}

ALLOWED_TOP_DIRS = frozenset(
    {"backend", "frontend", "scripts", "samples", "evals", "configs", "docs", ".github"}
)
ALLOWED_APP_SUBDIRS = frozenset(
    {"api", "core", "db", "schemas", "services", "prompts"}
)

# Banned import roots (case-insensitive). unittest.mock handled specially.
# Anti-bloat: queues, cloud SDKs-as-platform, wrong frameworks, ML platforms, A/B SDKs.
BANNED_IMPORT_ROOTS = frozenset(
    {
        # messaging / queues
        "kafka",
        "aiokafka",
        "confluent_kafka",
        "celery",
        "pika",
        "redis",
        "rq",
        "dramatiq",
        "huey",
        # wrong web / LLM frameworks
        "django",
        "flask",
        "langchain",
        "llama_index",
        "boto3",
        # feature stores / model registries / experiment platforms
        "feast",
        "mlflow",
        "launchdarkly",
        "ldclient",
        "optimizely",
        "splitio",
        "growthbook",
        "statsig",
    }
)

# Honesty / mock regression strings (substring match).
BANNED_STRINGS = (
    "mock_",
    "SAMPLE_JOBS",
    "fallback_embedding",
    "MagicMock",
)

# Anti-bloat infra terms in app code (word-boundary, case-insensitive).
# Keep specific — avoid short tokens like "queue" that false-positive.
BANNED_INFRA_TERMS = (
    "kubernetes",
    "k8s",
    "terraform",
    "helm chart",
    "istio",
    "linkerd",
    "service mesh",
    "feature store",
    "model registry",
    "microservice",
    "microservices",
    "kafka",
    "celery",
)

SECOND_UI_FRAMEWORKS = frozenset(
    {
        "styled-components",
        "@emotion/react",
        "@emotion/styled",
        "emotion",
        "@mui/material",
        "@mui/core",
        "antd",
        "@ant-design/icons",
    }
)

# App surface scanned for banned imports/terms (includes frontend hooks/lib).
APP_SCAN_DIRS = (
    "backend/app",
    "frontend/app",
    "frontend/components",
    "frontend/hooks",
    "frontend/lib",
)

FRONTEND_NO_STORAGE_DIRS = (
    "frontend/app",
    "frontend/components",
    "frontend/hooks",
    "frontend/lib",
)

# Broad-except kinds (exact match against allowlist; never supersets).
EXCEPT_KIND_BARE = "except:"
EXCEPT_KIND_EXCEPTION = "except Exception"
EXCEPT_KIND_BASE = "except BaseException"
EXCEPT_KINDS = frozenset(
    {EXCEPT_KIND_BARE, EXCEPT_KIND_EXCEPTION, EXCEPT_KIND_BASE}
)

COV_FAIL_UNDER_RE = re.compile(
    r"--cov-fail-under\s*=\s*(\d+)|--cov-fail-under\s+(\d+)",
    re.IGNORECASE,
)
COV_APP_RE = re.compile(r"--cov(=|\s+)app\b")
PROMPT_CONST_RE = re.compile(r"^\s*[A-Za-z_][A-Za-z0-9_]*_PROMPT\s*=")
DEP_NAME_RE = re.compile(
    r"^\s*([A-Za-z0-9_.-]+)(?:\[[^\]]*\])?\s*(?:[<>=!~]=?.*)?\s*(?:#.*)?$"
)
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# Secondary manifests that bypass a single requirements.txt scan.
SECONDARY_MANIFEST_NAMES = (
    "Pipfile",
    "Pipfile.lock",
    "poetry.lock",
    "setup.py",
    "setup.cfg",
)


def repo_root_from_args(argv: list[str] | None = None) -> Path:
    parser = argparse.ArgumentParser(description="TeamScout scope enforcement")
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repo root override (for fixture tests). Default: repo root or TEAMSCOUT_SCOPE_ROOT.",
    )
    args = parser.parse_args(argv)
    if args.root is not None:
        return args.root.resolve()
    env = os.environ.get("TEAMSCOUT_SCOPE_ROOT")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parent.parent


def rel(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def normalize_dep_name(raw: str) -> str:
    """Strip extras, versions, markers → package name (PEP 503-ish lower)."""
    s = raw.strip()
    if not s or s.startswith("#"):
        return ""
    s = s.split(";", 1)[0].strip()
    if "#" in s:
        s = s.split("#", 1)[0].strip()
    m = DEP_NAME_RE.match(s)
    if not m:
        token = re.split(r"[\[<>=!~\s]", s, maxsplit=1)[0]
        return token.strip().lower().replace("_", "-")
    return m.group(1).strip().lower().replace("_", "-")


def load_allowlist_packages(path: Path) -> tuple[set[str], list[str]]:
    """Load allowlist; every package line must include a non-empty # why comment."""
    names: set[str] = set()
    violations: list[str] = []
    if not path.is_file():
        return names, violations
    rpath = str(path).replace("\\", "/")
    # Prefer relative-looking name for messages
    display = path.name
    for i, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "#" not in raw:
            pkg = line.split()[0] if line.split() else line
            violations.append(
                f"DEP_NOT_ALLOWED: {display}:{i} package '{pkg}' missing # why comment — "
                "add a trailing justification, e.g. `pkg  # why this package is needed`."
            )
            name = normalize_dep_name(line)
            if name:
                # still record so missing-from-allowlist checks can work after fix
                names.add(name if not name.startswith("@") else name)
            continue
        left, why = raw.split("#", 1)
        name_raw = left.strip()
        why = why.strip()
        if not why:
            violations.append(
                f"DEP_NOT_ALLOWED: {display}:{i} package '{name_raw}' has empty # why — "
                "write a real justification after #."
            )
        # Frontend scoped packages keep @; backend normalized with -
        if name_raw.startswith("@"):
            names.add(name_raw.lower())
        else:
            # take first token (package name may have trailing spaces before #)
            token = name_raw.split()[0] if name_raw.split() else name_raw
            names.add(token.lower().replace("_", "-") if not token.startswith("@") else token.lower())
    return names, violations


def normalize_except_kind(raw: str | None) -> str | None:
    """Map allowlist kind tokens to exact EXCEPT_KIND_* values.

    Exact kinds only — `except Exception` never implies bare `except:`.
    """
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    if s in EXCEPT_KINDS:
        return s
    low = re.sub(r"\s+", " ", s.lower())
    if low in {"except:", "bare"}:
        return EXCEPT_KIND_BARE
    if low in {"except exception", "exception"}:
        return EXCEPT_KIND_EXCEPTION
    if low in {"except baseexception", "baseexception"}:
        return EXCEPT_KIND_BASE
    # Unknown token: keep as-is so it only matches an identical emitted kind
    return s


def load_except_allowlist(path: Path) -> list[tuple[str, int | None, str | None]]:
    """Return list of (rel_path, lineno|None, kind|None).

    Formats:
      path/to/file.py:LINE
      path/to/file.py:except Exception
      path/to/file.py:except:
      path/to/file.py:except BaseException
    Kind match is exact — `except Exception` never covers bare `except:`.
    """
    entries: list[tuple[str, int | None, str | None]] = []
    if not path.is_file():
        return entries
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" not in line:
            entries.append((line.replace("\\", "/"), None, None))
            continue
        # Split path from suffix: last colon that starts a kind or line number.
        # Paths are relative without drive letters on unix.
        left, right = line.rsplit(":", 1)
        left = left.strip().replace("\\", "/")
        right = right.strip()
        if right.isdigit():
            entries.append((left, int(right), None))
        else:
            entries.append((left, None, normalize_except_kind(right)))
    return entries


def path_matches_allow(rel_path: str, apath: str) -> bool:
    """Exact path or suffix under a directory boundary only.

    Never bare endswith(ap): that would let `email_reveal.py` match
    `not_email_reveal.py`.
    """
    norm = rel_path.replace("\\", "/")
    ap = apath.replace("\\", "/")
    return norm == ap or norm.endswith("/" + ap)


def except_is_allowlisted(
    rel_path: str,
    lineno: int,
    kind: str,
    allow: list[tuple[str, int | None, str | None]],
) -> bool:
    """Exact kind match. Line-only entries allow any kind at that line.
    Path-only entries (no line, no kind) allow any kind in that file — discouraged.
    """
    for apath, aline, akind in allow:
        if not path_matches_allow(rel_path, apath):
            continue
        if aline is not None and aline != lineno:
            continue
        if akind is not None and akind != kind:
            continue
        return True
    return False


def _handler_type_names(node: ast.expr | None) -> list[str]:
    """Return simple type names referenced by an ExceptHandler type expr."""
    if node is None:
        return []
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        # e.g. builtins.Exception → Exception
        return [node.attr]
    if isinstance(node, ast.Tuple):
        names: list[str] = []
        for elt in node.elts:
            names.extend(_handler_type_names(elt))
        return names
    return []


def broad_except_handlers(tree: ast.AST) -> list[tuple[int, str]]:
    """AST scan: bare except, Exception, BaseException, or tuples containing them."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if node.type is None:
            found.append((node.lineno, EXCEPT_KIND_BARE))
            continue
        names = _handler_type_names(node.type)
        if "BaseException" in names:
            found.append((node.lineno, EXCEPT_KIND_BASE))
        elif "Exception" in names:
            found.append((node.lineno, EXCEPT_KIND_EXCEPTION))
    return found


def iter_py_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    out: list[Path] = []
    for p in directory.rglob("*.py"):
        if any(part == "__pycache__" for part in p.parts):
            continue
        out.append(p)
    return sorted(out)


def iter_text_files(directory: Path, suffixes: set[str]) -> list[Path]:
    if not directory.is_dir():
        return []
    out: list[Path] = []
    for p in directory.rglob("*"):
        if not p.is_file():
            continue
        if any(
            part in {".git", "node_modules", "__pycache__", ".next"} for part in p.parts
        ):
            continue
        if p.suffix.lower() in suffixes:
            out.append(p)
    return sorted(out)


def strip_yaml_comment(line: str) -> str:
    """Strip unquoted # comments from a YAML line."""
    in_single = False
    in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            return line[:i].rstrip()
    return line.rstrip()


def extract_run_commands(text: str) -> list[str]:
    """Extract live `run:` shell command strings from a GitHub Actions workflow.

    Ignores full-line and trailing comments. Handles single-line and block scalars.
    """
    lines = text.splitlines()
    commands: list[str] = []
    i = 0
    while i < len(lines):
        raw = lines[i]
        stripped = strip_yaml_comment(raw)
        if not stripped.strip():
            i += 1
            continue
        m = re.match(r"^(\s*)-\s*run:\s*(.*)$", stripped)
        m2 = re.match(r"^(\s*)run:\s*(.*)$", stripped)
        match = m or m2
        if not match:
            i += 1
            continue
        indent = len(match.group(1))
        rest = match.group(2).strip()
        if rest in {"|", ">", "|-", ">-", "|+", ">+"}:
            block: list[str] = []
            i += 1
            while i < len(lines):
                braw = lines[i]
                bstrip = strip_yaml_comment(braw)
                if not bstrip.strip():
                    # blank line inside block — keep if more indented content follows
                    block.append("")
                    i += 1
                    continue
                # content must be more indented than the run: key
                leading = len(braw) - len(braw.lstrip(" "))
                if leading <= indent:
                    break
                block.append(bstrip.strip())
                i += 1
            commands.append("\n".join(block).strip())
            continue
        if rest:
            commands.append(rest)
        i += 1
    return commands


def parse_workflow_jobs(text: str) -> dict[str, dict]:
    """Lightweight jobs parser: {name: {needs: [str], runs: [str]}}.

    Stdlib only — not a full YAML parser. Good enough for GHA ci.yml shape.
    """
    lines = [strip_yaml_comment(l) for l in text.splitlines()]
    jobs: dict[str, dict] = {}
    in_jobs = False
    current: str | None = None
    # needs list mode
    in_needs_list = False
    needs_indent = 0

    for idx, stripped in enumerate(lines):
        if not stripped.strip():
            continue
        # top-level keys
        if re.match(r"^[A-Za-z0-9_.-]+:\s*", stripped) and not stripped.startswith(" "):
            key = stripped.split(":", 1)[0].strip()
            in_jobs = key == "jobs"
            if key != "jobs":
                # leaving jobs section only if we were in jobs and hit another top key
                if in_jobs and key != "jobs":
                    in_jobs = False
                    current = None
            continue

        if not in_jobs and stripped.strip() == "jobs:":
            in_jobs = True
            current = None
            continue

        if not in_jobs:
            continue

        # job name at 2-space indent (common GHA style) or any indent under jobs
        job_m = re.match(r"^([ \t]+)([A-Za-z0-9_.-]+):\s*$", stripped)
        if job_m:
            indent = len(job_m.group(1).replace("\t", "  "))
            name = job_m.group(2)
            # jobs are direct children — typically indent 2
            if indent <= 4 and name not in {
                "steps",
                "defaults",
                "services",
                "strategy",
                "outputs",
                "env",
                "permissions",
                "concurrency",
                "container",
            }:
                # Heuristic: if indent is small and not a known nested key, treat as job
                # Only accept if previous context is jobs root or we see runs-on later
                if indent <= 2 or name not in jobs and indent < 6:
                    # Avoid treating step keys as jobs: skip if name is common step field
                    if name in {
                        "runs-on",
                        "needs",
                        "name",
                        "if",
                        "uses",
                        "with",
                        "run",
                        "id",
                        "shell",
                        "working-directory",
                        "timeout-minutes",
                    }:
                        pass
                    else:
                        current = name
                        jobs.setdefault(current, {"needs": [], "runs": []})
                        in_needs_list = False
                        continue

        if current is None:
            continue

        # needs: scope  OR needs: [scope, x] OR needs:\n  - scope
        needs_inline = re.match(r"^\s+needs:\s*(.+)$", stripped)
        if needs_inline:
            val = needs_inline.group(1).strip()
            if not val:
                in_needs_list = True
                needs_indent = len(stripped) - len(stripped.lstrip(" "))
                continue
            in_needs_list = False
            if val.startswith("[") and val.endswith("]"):
                inner = val[1:-1]
                parts = [p.strip().strip("'\"") for p in inner.split(",") if p.strip()]
                jobs[current]["needs"].extend(parts)
            else:
                jobs[current]["needs"].append(val.strip("'\""))
            continue

        if in_needs_list:
            item = re.match(r"^\s+-\s+(.+)$", stripped)
            if item:
                jobs[current]["needs"].append(item.group(1).strip().strip("'\""))
                continue
            # left needs list
            in_needs_list = False

    # attach run commands per-job by a second pass: split text by job blocks
    # Simpler: assign all extract_run_commands to jobs by scanning regions
    raw_lines = text.splitlines()
    job_order: list[tuple[str, int]] = []
    in_jobs = False
    for i, raw in enumerate(raw_lines):
        stripped = strip_yaml_comment(raw)
        if re.match(r"^jobs:\s*$", stripped):
            in_jobs = True
            continue
        if in_jobs and re.match(r"^[A-Za-z0-9_.-]+:\s*", stripped) and not stripped.startswith(" "):
            in_jobs = False
            continue
        if not in_jobs:
            continue
        jm = re.match(r"^([ \t]{1,4})([A-Za-z0-9_.-]+):\s*$", stripped)
        if jm and jm.group(2) in jobs:
            job_order.append((jm.group(2), i))

    # For each job region, extract run commands from that slice
    for j, (name, start) in enumerate(job_order):
        end = job_order[j + 1][1] if j + 1 < len(job_order) else len(raw_lines)
        region = "\n".join(raw_lines[start:end])
        jobs[name]["runs"] = extract_run_commands(region)

    return jobs


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def _scan_requirements_file(path: Path, allowed: set[str], root: Path) -> list[str]:
    violations: list[str] = []
    rpath = rel(root, path)
    for i, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        name = normalize_dep_name(raw)
        if not name:
            continue
        if name not in allowed:
            violations.append(
                f"DEP_NOT_ALLOWED: {name} ({rpath}:{i}) — "
                "add to scripts/allowed_deps_backend.txt with a justification comment if genuinely needed."
            )
    return violations


def check_backend_deps(root: Path) -> list[str]:
    violations: list[str] = []
    allow_path = root / "scripts" / "allowed_deps_backend.txt"
    allowed, allow_violations = load_allowlist_packages(allow_path)
    violations.extend(allow_violations)

    req = root / "backend" / "requirements.txt"
    if not req.is_file():
        violations.append(
            "DEP_NOT_ALLOWED: backend/requirements.txt missing — restore requirements and allowlist."
        )
    else:
        if not allowed and not allow_violations:
            violations.append(
                "DEP_NOT_ALLOWED: scripts/allowed_deps_backend.txt empty or missing — "
                "seed one package per line with a # why comment."
            )
        violations.extend(_scan_requirements_file(req, allowed, root))

    # Secondary requirements*.txt under backend/
    backend_dir = root / "backend"
    if backend_dir.is_dir():
        for extra in sorted(backend_dir.glob("requirements*.txt")):
            if extra.resolve() == req.resolve():
                continue
            violations.extend(_scan_requirements_file(extra, allowed, root))

    # Fail loud on alternate packaging manifests that could smuggle deps
    for base in (root, root / "backend"):
        for name in SECONDARY_MANIFEST_NAMES:
            p = base / name
            if p.is_file() and p.stat().st_size > 0:
                violations.append(
                    f"DEP_NOT_ALLOWED: secondary manifest {rel(root, p)} present — "
                    "TeamScout uses only backend/requirements.txt; remove this file or fold "
                    "deps into requirements.txt + allowlist."
                )
        pyproject = base / "pyproject.toml"
        if pyproject.is_file():
            text = pyproject.read_text(encoding="utf-8", errors="replace")
            if re.search(
                r"(?m)^\[project(\.optional-dependencies)?\]|dependencies\s*=\s*\[",
                text,
            ):
                violations.append(
                    f"DEP_NOT_ALLOWED: {rel(root, pyproject)} declares dependencies — "
                    "use backend/requirements.txt + allowlist only; remove dep tables "
                    "or delete the file."
                )
    return violations


def check_frontend_deps(root: Path) -> list[str]:
    violations: list[str] = []
    pkg_path = root / "frontend" / "package.json"
    allow_path = root / "scripts" / "allowed_deps_frontend.txt"
    if not pkg_path.is_file():
        return [
            "DEP_NOT_ALLOWED: frontend/package.json missing — restore package.json and allowlist."
        ]
    try:
        data = json.loads(pkg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"DEP_NOT_ALLOWED: frontend/package.json invalid JSON: {exc}"]

    allowed, allow_violations = load_allowlist_packages(allow_path)
    violations.extend(allow_violations)
    if not allowed and not allow_violations:
        violations.append(
            "DEP_NOT_ALLOWED: scripts/allowed_deps_frontend.txt empty or missing — "
            "seed one package per line with a # why comment."
        )

    for section in ("dependencies", "devDependencies"):
        deps = data.get(section) or {}
        if not isinstance(deps, dict):
            continue
        for name in deps:
            if not any(name.lower() == a.lower() for a in allowed):
                violations.append(
                    f"DEP_NOT_ALLOWED: {name} (frontend/package.json {section}) — "
                    "add to scripts/allowed_deps_frontend.txt with a justification comment if genuinely needed."
                )

    all_names: set[str] = set()
    for section in ("dependencies", "devDependencies"):
        deps = data.get(section) or {}
        if isinstance(deps, dict):
            all_names.update(deps.keys())
    for name in sorted(all_names):
        low = name.lower()
        if low in SECOND_UI_FRAMEWORKS or any(
            low == s or low.startswith(s + "/") for s in SECOND_UI_FRAMEWORKS
        ):
            violations.append(
                f"FRONTEND_GATE: second UI framework '{name}' in package.json — "
                "remove it; Tailwind + React only."
            )
    return violations


def _import_roots_from_tree(tree: ast.AST) -> list[tuple[str, int]]:
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            found.append((mod, node.lineno))
            if mod == "unittest" or mod.startswith("unittest."):
                for alias in node.names:
                    if alias.name in {"mock", "MagicMock"}:
                        found.append(("unittest.mock", node.lineno))
            if mod == "unittest.mock" or mod.endswith(".mock"):
                found.append(("unittest.mock", node.lineno))
    return found


def _magicmock_import_lines(tree: ast.AST) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if (alias.name or "") == "MagicMock" or (alias.asname or "") == "MagicMock":
                    lines.append(getattr(node, "lineno", 0))
    return lines


def check_banned_terms(root: Path) -> list[str]:
    violations: list[str] = []
    for scan_root in (root / d for d in APP_SCAN_DIRS):
        if not scan_root.exists():
            continue

        for py in iter_py_files(scan_root):
            text = py.read_text(encoding="utf-8", errors="replace")
            rpath = rel(root, py)
            try:
                tree = ast.parse(text, filename=str(py))
            except SyntaxError as exc:
                violations.append(
                    f"BANNED_IMPORT: {rpath} unparseable ({exc.msg}) — fix syntax so the gate can scan."
                )
                tree = None
            if tree is not None:
                for mod, lineno in _import_roots_from_tree(tree):
                    top = (mod or "").split(".")[0].lower()
                    full = (mod or "").lower()
                    if full == "unittest.mock" or full.startswith("unittest.mock"):
                        violations.append(
                            f"BANNED_IMPORT: {rpath}:{lineno} imports unittest.mock — "
                            "mocks belong in tests/, not app code."
                        )
                        continue
                    if top in BANNED_IMPORT_ROOTS or full in BANNED_IMPORT_ROOTS:
                        violations.append(
                            f"BANNED_IMPORT: {rpath}:{lineno} imports '{mod}' — "
                            "remove banned infrastructure / framework from app code."
                        )
                for lineno in _magicmock_import_lines(tree):
                    violations.append(
                        f"BANNED_IMPORT: {rpath}:{lineno} imports MagicMock — "
                        "mocks belong in tests/."
                    )

            for s in BANNED_STRINGS:
                if s in text:
                    for i, line in enumerate(text.splitlines(), 1):
                        if s in line:
                            violations.append(
                                f"BANNED_TERM: {rpath}:{i} contains '{s}' — "
                                "remove mock/fallback artifacts from app code "
                                "(fixtures only in tests/ and scripts/fixtures/)."
                            )
                            break
            for term in BANNED_INFRA_TERMS:
                if re.search(rf"\b{re.escape(term)}\b", text, re.IGNORECASE):
                    for i, line in enumerate(text.splitlines(), 1):
                        if re.search(rf"\b{re.escape(term)}\b", line, re.IGNORECASE):
                            violations.append(
                                f"BANNED_TERM: {rpath}:{i} contains anti-bloat term '{term}' — "
                                "TeamScout is a two-feature app; do not add platform/infra "
                                "(see CONSTRAINTS.md). Remove the reference."
                            )
                            break

        # Frontend TS/JS surface
        if "frontend" in scan_root.parts:
            for f in iter_text_files(scan_root, {".ts", ".tsx", ".js", ".jsx"}):
                text = f.read_text(encoding="utf-8", errors="replace")
                rpath = rel(root, f)
                for term in BANNED_IMPORT_ROOTS:
                    if re.search(
                        rf"(from|import)\s+['\"]?{re.escape(term)}\b",
                        text,
                        re.IGNORECASE,
                    ):
                        violations.append(
                            f"BANNED_IMPORT: {rpath} references '{term}' — "
                            "remove banned dependency usage."
                        )
                for s in BANNED_STRINGS:
                    if s in text:
                        for i, line in enumerate(text.splitlines(), 1):
                            if s in line:
                                violations.append(
                                    f"BANNED_TERM: {rpath}:{i} contains '{s}' — remove from app code."
                                )
                                break
                for term in BANNED_INFRA_TERMS:
                    if re.search(rf"\b{re.escape(term)}\b", text, re.IGNORECASE):
                        for i, line in enumerate(text.splitlines(), 1):
                            if re.search(rf"\b{re.escape(term)}\b", line, re.IGNORECASE):
                                violations.append(
                                    f"BANNED_TERM: {rpath}:{i} contains anti-bloat term '{term}' — "
                                    "remove platform/infra references (CONSTRAINTS.md)."
                                )
                                break

    seen: set[str] = set()
    out: list[str] = []
    for v in violations:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def check_structure(root: Path) -> list[str]:
    violations: list[str] = []
    if not root.is_dir():
        return [f"STRUCTURE_DRIFT: root {root} is not a directory"]

    top_dirs = []
    for p in root.iterdir():
        if not p.is_dir():
            continue
        name = p.name
        if name.startswith(".") and name != ".github":
            continue
        top_dirs.append(name)

    for name in sorted(top_dirs):
        if name not in ALLOWED_TOP_DIRS:
            violations.append(
                f"STRUCTURE_DRIFT: {name} — top-level dirs must be exactly "
                f"{sorted(ALLOWED_TOP_DIRS)}. Remove or relocate '{name}'."
            )
    for required in sorted(ALLOWED_TOP_DIRS):
        if required not in top_dirs:
            violations.append(
                f"STRUCTURE_DRIFT: missing top-level '{required}/' — create it "
                "(use .gitkeep if empty). Allowed set is locked."
            )

    app = root / "backend" / "app"
    if app.is_dir():
        sub = []
        for p in app.iterdir():
            if not p.is_dir():
                continue
            if p.name.startswith(".") or p.name == "__pycache__":
                continue
            sub.append(p.name)
        for name in sorted(sub):
            if name not in ALLOWED_APP_SUBDIRS:
                violations.append(
                    f"STRUCTURE_DRIFT: backend/app/{name} — app package dirs must be exactly "
                    f"{sorted(ALLOWED_APP_SUBDIRS)}. Remove or relocate."
                )
        for required in sorted(ALLOWED_APP_SUBDIRS):
            if required not in sub:
                violations.append(
                    f"STRUCTURE_DRIFT: missing backend/app/{required}/ — create it "
                    "(prompts/ may use .gitkeep until Milestone 8)."
                )
    else:
        violations.append(
            "STRUCTURE_DRIFT: backend/app missing — restore the application package."
        )
    return violations


def check_size_budgets(root: Path) -> list[str]:
    violations: list[str] = []
    services = root / "backend" / "app" / "services"
    if services.is_dir():
        for py in iter_py_files(services):
            n = len(py.read_text(encoding="utf-8", errors="replace").splitlines())
            if n > SERVICE_FILE_MAX_LINES:
                violations.append(
                    f"SIZE_BUDGET: {rel(root, py)} has {n} lines (max {SERVICE_FILE_MAX_LINES}) — "
                    "split or simplify, do not raise the budget."
                )
    main_py = root / "backend" / "app" / "main.py"
    if main_py.is_file():
        n = len(main_py.read_text(encoding="utf-8", errors="replace").splitlines())
        if n > MAIN_MAX_LINES:
            violations.append(
                f"SIZE_BUDGET: backend/app/main.py has {n} lines (max {MAIN_MAX_LINES}) — "
                "split or simplify, do not raise the budget."
            )
    app = root / "backend" / "app"
    total = 0
    if app.is_dir():
        for py in iter_py_files(app):
            total += len(py.read_text(encoding="utf-8", errors="replace").splitlines())
    if total > APP_LOC_MAX:
        violations.append(
            f"SIZE_BUDGET: backend/app total LOC is {total} (max {APP_LOC_MAX}) — "
            "split or simplify, do not raise the budget."
        )
    return violations


def check_error_handling(root: Path) -> list[str]:
    violations: list[str] = []
    allow = load_except_allowlist(root / "scripts" / "except_allowlist.txt")
    app = root / "backend" / "app"
    for py in iter_py_files(app):
        rpath = rel(root, py)
        text = py.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(text, filename=str(py))
        except SyntaxError as exc:
            violations.append(
                f"BARE_EXCEPT: {rpath} unparseable ({exc.msg}) — fix syntax so the gate can scan."
            )
            continue
        for lineno, kind in broad_except_handlers(tree):
            if except_is_allowlisted(rpath, lineno, kind, allow):
                continue
            violations.append(
                f"BARE_EXCEPT: {rpath}:{lineno} uses '{kind}' — narrow the exception type, "
                "or add a justified entry to scripts/except_allowlist.txt "
                f"(preferred format: {rpath}:{kind}  # reason; "
                f"line-pin format also accepted: {rpath}:{lineno}  # reason)."
            )
    return violations


def check_frontend_gates(root: Path) -> list[str]:
    violations: list[str] = []
    fe = root / "frontend"
    if not fe.is_dir():
        return ["FRONTEND_GATE: frontend/ missing — restore the Next.js app."]

    pnpm = fe / "pnpm-lock.yaml"
    npm = fe / "package-lock.json"
    yarn = fe / "yarn.lock"
    root_npm = root / "package-lock.json"
    root_yarn = root / "yarn.lock"
    root_pnpm = root / "pnpm-lock.yaml"

    if not pnpm.is_file() and not root_pnpm.is_file():
        violations.append(
            "FRONTEND_GATE: pnpm-lock.yaml missing under frontend/ — "
            "use pnpm and commit frontend/pnpm-lock.yaml."
        )
    if npm.is_file() or root_npm.is_file():
        violations.append(
            "FRONTEND_GATE: package-lock.json present — remove it; pnpm is the only package manager."
        )
    if yarn.is_file() or root_yarn.is_file():
        violations.append(
            "FRONTEND_GATE: yarn.lock present — remove it; pnpm is the only package manager."
        )

    storage_re = re.compile(r"\b(localStorage|sessionStorage)\b")
    for d in FRONTEND_NO_STORAGE_DIRS:
        base = root / d
        for f in iter_text_files(base, {".ts", ".tsx", ".js", ".jsx"}):
            text = f.read_text(encoding="utf-8", errors="replace")
            for i, line in enumerate(text.splitlines(), 1):
                if storage_re.search(line):
                    violations.append(
                        f"FRONTEND_GATE: {rel(root, f)}:{i} uses localStorage/sessionStorage — "
                        "remove browser storage; keep state in React/server only."
                    )
    return violations


def check_prompt_discipline(root: Path) -> list[str]:
    violations: list[str] = []
    prompts = root / "backend" / "app" / "prompts"
    if prompts.is_dir():
        content_files = [
            p
            for p in prompts.rglob("*")
            if p.is_file()
            and p.name not in {".gitkeep", ".keep", "README.md", "README"}
            and not p.name.startswith(".")
            and p.name != "__init__.py"
            and p.suffix not in {".pyc", ".pyo"}
            and "__pycache__" not in p.parts
            and p.suffix in {".md", ".txt", ".prompt", ".yml", ".yaml"}
        ]
        for p in content_files:
            text = p.read_text(encoding="utf-8", errors="replace")
            rpath = rel(root, p)
            m = FRONTMATTER_RE.match(text)
            if not m:
                violations.append(
                    f"PROMPT_DISCIPLINE: {rpath} missing YAML frontmatter with name + version — "
                    "add ---\\nname: ...\\nversion: ...\\n--- at file start."
                )
                continue
            fm = m.group(1)
            has_name = re.search(r"(?m)^name\s*:", fm) is not None
            has_ver = re.search(r"(?m)^version\s*:", fm) is not None
            if not has_name or not has_ver:
                violations.append(
                    f"PROMPT_DISCIPLINE: {rpath} frontmatter must include both 'name' and 'version' keys."
                )

    services = root / "backend" / "app" / "services"
    for py in iter_py_files(services):
        text = py.read_text(encoding="utf-8", errors="replace")
        rpath = rel(root, py)
        for i, line in enumerate(text.splitlines(), 1):
            if PROMPT_CONST_RE.match(line):
                violations.append(
                    f"PROMPT_DISCIPLINE: {rpath}:{i} defines *_PROMPT — "
                    "move prompt text to backend/app/prompts/ with YAML frontmatter "
                    "(name + version); load it from services instead of embedding."
                )
    return violations


def check_artifact_hygiene(root: Path) -> list[str]:
    violations: list[str] = []
    if not (root / ".git").exists():
        return violations
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "ls-files"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        return [f"ARTIFACT_HYGIENE: cannot run git ls-files: {exc}"]
    if proc.returncode != 0:
        return [
            f"ARTIFACT_HYGIENE: git ls-files failed: {proc.stderr.strip() or proc.returncode}"
        ]
    tracked = [
        ln.strip().replace("\\", "/") for ln in proc.stdout.splitlines() if ln.strip()
    ]
    for path in tracked:
        if path.endswith(".db") or path.endswith(".sqlite") or path.endswith(".sqlite3"):
            violations.append(
                f"ARTIFACT_HYGIENE: tracked database '{path}' — "
                "add to .gitignore and `git rm --cached` it."
            )
        if path.startswith("backend/uploads/") and not path.endswith(".gitkeep"):
            violations.append(
                f"ARTIFACT_HYGIENE: tracked upload '{path}' — "
                "only backend/uploads/.gitkeep may be tracked; git rm --cached the rest."
            )
        if (
            path.endswith(".pytest_cache")
            or path.endswith(".ruff_cache")
            or "/.pytest_cache/" in f"/{path}/"
            or "/.ruff_cache/" in f"/{path}/"
        ):
            violations.append(
                f"ARTIFACT_HYGIENE: tracked cache '{path}' — "
                "add to .gitignore and `git rm -r --cached` it."
            )
    return violations


def check_thresholds(root: Path) -> list[str]:
    violations: list[str] = []
    path = root / "evals" / "thresholds.json"
    if not path.is_file():
        return [
            "THRESHOLD_FLOOR: evals/thresholds.json missing — restore floors "
            f"{THRESHOLD_FLOORS} and do not lower them."
        ]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"THRESHOLD_FLOOR: evals/thresholds.json invalid JSON: {exc}"]
    if not isinstance(data, dict):
        return ["THRESHOLD_FLOOR: evals/thresholds.json must be a JSON object."]
    for key, floor in THRESHOLD_FLOORS.items():
        if key not in data:
            violations.append(
                f"THRESHOLD_FLOOR: missing key '{key}' (floor {floor}) — "
                "restore it in evals/thresholds.json; do not remove floors."
            )
            continue
        try:
            val = data[key]
            if isinstance(floor, float):
                if float(val) + 1e-12 < float(floor):
                    violations.append(
                        f"THRESHOLD_FLOOR: {key}={val} is below floor {floor} — "
                        "do not lower thresholds; restore the floor value."
                    )
            else:
                if int(val) < int(floor):
                    violations.append(
                        f"THRESHOLD_FLOOR: {key}={val} is below floor {floor} — "
                        "do not lower thresholds; restore the floor value."
                    )
        except (TypeError, ValueError):
            violations.append(
                f"THRESHOLD_FLOOR: {key}={data[key]!r} is not a number — use the floor type."
            )
    return violations


def _logical_shell_lines(cmd: str) -> list[str]:
    """Split a run: command into logical shell lines (newlines, &&, ;)."""
    out: list[str] = []
    for raw_line in cmd.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        for part in re.split(r"\s*(?:&&|;)\s*", line):
            part = part.strip()
            if part:
                out.append(part)
    return out


def _first_shell_token(line: str) -> str:
    return (line.split() or [""])[0]


def _is_echo_line(line: str) -> bool:
    return _first_shell_token(line) == "echo"


_PYTEST_RE = re.compile(
    r"(?:^|[\s/`\"'])(?:python[0-9.]*\s+-m\s+)?pytest\b",
    re.IGNORECASE,
)
# Path-like scope script only — bare `check_scope` / `echo check_scope` do not count.
_SCOPE_SCRIPT_RE = re.compile(
    r"(?:^|[\s/`\"'])(?:\./)?(?:scripts/)?check_scope\.py\b"
)


def _is_real_pytest_line(line: str) -> bool:
    """True if line invokes pytest (not echo-wrapped)."""
    if _is_echo_line(line):
        return False
    return bool(_PYTEST_RE.search(line))


def _coverage_n_on_line(line: str) -> int | None:
    m = COV_FAIL_UNDER_RE.search(line)
    if not m:
        return None
    return int(next(g for g in m.groups() if g is not None))


def _line_satisfies_coverage(line: str) -> bool:
    """pytest (or python -m pytest) AND --cov=app AND --cov-fail-under>=80 on same line."""
    if not _is_real_pytest_line(line):
        return False
    if not COV_APP_RE.search(line):
        return False
    n = _coverage_n_on_line(line)
    return n is not None and n >= 80


def _line_is_scope_script(line: str) -> bool:
    """True if line runs scripts/check_scope.py or check_scope.py (not echo, not bare name)."""
    if _is_echo_line(line):
        return False
    return bool(_SCOPE_SCRIPT_RE.search(line))


def check_ci_coverage_gate(root: Path) -> list[str]:
    """Enforce live backend coverage command and needs: scope graph (not comments/echo)."""
    violations: list[str] = []
    wf_dir = root / ".github" / "workflows"
    ci_files: list[Path] = []
    if wf_dir.is_dir():
        ci_files.extend(sorted(wf_dir.glob("*.yml")))
        ci_files.extend(sorted(wf_dir.glob("*.yaml")))
    if not ci_files:
        return [
            "CI_COVERAGE: no .github/workflows/*.yml found — add ci.yml with "
            "a `scope` job running scripts/check_scope.py, other jobs `needs: scope`, "
            "and a live backend step `pytest --cov=app --cov-fail-under=80`."
        ]

    combined_jobs: dict[str, dict] = {}
    all_commands: list[str] = []
    for p in ci_files:
        text = p.read_text(encoding="utf-8", errors="replace")
        jobs = parse_workflow_jobs(text)
        for name, info in jobs.items():
            if name not in combined_jobs:
                combined_jobs[name] = {"needs": [], "runs": []}
            combined_jobs[name]["needs"].extend(info.get("needs") or [])
            combined_jobs[name]["runs"].extend(info.get("runs") or [])
        all_commands.extend(extract_run_commands(text))

    if "scope" not in combined_jobs:
        violations.append(
            "CI_COVERAGE: CI workflow missing job named 'scope' — "
            "add job `scope` that runs `python3 scripts/check_scope.py`; "
            "all other jobs must `needs: scope`."
        )
    else:
        scope_runs = combined_jobs["scope"].get("runs") or []
        if not any(
            any(_line_is_scope_script(line) for line in _logical_shell_lines(cmd))
            for cmd in scope_runs
        ):
            violations.append(
                "CI_COVERAGE: job 'scope' does not run scripts/check_scope.py — "
                "add a step: `run: python3 scripts/check_scope.py` "
                "(path must include check_scope.py; echo / bare `check_scope` do not count)."
            )

    for name, info in sorted(combined_jobs.items()):
        if name == "scope":
            continue
        needs = info.get("needs") or []
        if "scope" not in needs:
            violations.append(
                f"CI_COVERAGE: job '{name}' missing `needs: scope` — "
                "every non-scope job must depend on the scope gate."
            )

    # Live pytest lines only — echo and non-pytest substrings never satisfy
    strong = False
    reported_weak = False
    for cmd in all_commands:
        for line in _logical_shell_lines(cmd):
            if not _is_real_pytest_line(line):
                continue
            n = _coverage_n_on_line(line)
            has_app = bool(COV_APP_RE.search(line))
            if _line_satisfies_coverage(line):
                strong = True
                continue
            if n is not None and not has_app:
                violations.append(
                    f"CI_COVERAGE: pytest has --cov-fail-under={n} but missing "
                    "`--cov=app` on the same logical command line — use "
                    "`pytest --cov=app --cov-fail-under=80` "
                    "(echo / comments do not count)."
                )
                reported_weak = True
            elif n is not None and n < 80:
                violations.append(
                    f"CI_COVERAGE: live pytest --cov-fail-under={n} is below 80 — "
                    "raise it to at least 80 on the same line as pytest and --cov=app "
                    "(YAML comments and echo do not count)."
                )
                reported_weak = True

    if not strong and not reported_weak:
        violations.append(
            "CI_COVERAGE: no live backend pytest command with `--cov=app` and "
            "`--cov-fail-under=80` (or higher) on the same logical line — "
            "add `pytest --cov=app --cov-fail-under=80` to the backend job. "
            "YAML comments and `echo ...` do not satisfy this gate."
        )
    return violations


def run_all_checks(root: Path) -> list[str]:
    violations: list[str] = []
    for fn in (
        check_backend_deps,
        check_frontend_deps,
        check_banned_terms,
        check_structure,
        check_size_budgets,
        check_error_handling,
        check_frontend_gates,
        check_prompt_discipline,
        check_artifact_hygiene,
        check_thresholds,
        check_ci_coverage_gate,
    ):
        violations.extend(fn(root))
    return violations


def main(argv: list[str] | None = None) -> int:
    root = repo_root_from_args(argv)
    violations = run_all_checks(root)
    if not violations:
        print(f"check_scope: OK ({root})")
        return 0
    print(f"check_scope: {len(violations)} violation(s) in {root}", file=sys.stderr)
    for v in violations:
        print(v, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
