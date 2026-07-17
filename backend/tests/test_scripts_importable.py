"""Cheap gate: every scripts/**/*.py importable without running __main__.

Catches fixture renames that strand eval scripts (e.g. FIT_SIGNAL_PERSONAS)
before the slower CI eval job runs.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
SCRIPTS = ROOT / "scripts"

# Non-import targets (data / shell / allowlists)
_SKIP_NAMES = frozenset(
    {
        "docker-entrypoint.sh",
        "allowed_deps_backend.txt",
        "allowed_deps_frontend.txt",
        "except_allowlist.txt",
    }
)


def _script_modules() -> list[str]:
    """Return dotted module names under scripts/ for importlib."""
    mods: list[str] = []
    for path in sorted(SCRIPTS.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        if path.name in _SKIP_NAMES:
            continue
        rel = path.relative_to(ROOT)
        # scripts/foo.py -> scripts.foo ; scripts/fixtures/bar.py -> scripts.fixtures.bar
        parts = list(rel.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        mods.append(".".join(parts))
    return mods


def _ensure_paths() -> None:
    root_s, backend_s = str(ROOT), str(BACKEND)
    if backend_s not in sys.path:
        sys.path.insert(0, backend_s)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)


@pytest.mark.parametrize("modname", _script_modules())
def test_script_module_importable(modname: str) -> None:
    """Import each scripts module; failures surface as ImportError (stale symbols)."""
    _ensure_paths()
    # Clear prior failed partial imports of the same name
    if modname in sys.modules:
        del sys.modules[modname]
    # Also clear parent packages if needed for re-import
    importlib.import_module(modname)


def test_import_walk_catches_stale_fixture_symbol(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Prove the walker fails when a script imports a missing fixture name (class regression)."""
    _ensure_paths()
    # Plant a temporary package under scripts/ that references a nonexistent symbol
    plant = SCRIPTS / "_import_walk_probe.py"
    plant.write_text(
        "from scripts.fixtures.ranking_fixtures import THIS_SYMBOL_DOES_NOT_EXIST  # noqa: F401\n",
        encoding="utf-8",
    )
    try:
        name = "scripts._import_walk_probe"
        if name in sys.modules:
            del sys.modules[name]
        with pytest.raises(ImportError):
            importlib.import_module(name)
    finally:
        if plant.exists():
            plant.unlink()
        sys.modules.pop("scripts._import_walk_probe", None)


def test_script_module_list_nonempty() -> None:
    mods = _script_modules()
    assert any(m.endswith("eval_fit_signals") for m in mods)
    assert any(m.endswith("ranking_fixtures") for m in mods)
    assert len(mods) >= 10
