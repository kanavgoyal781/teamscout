"""CI gate: resume-pick fixture honesty without running full eval."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.fixtures.resume_pick_fixtures import CASES, assert_fixture_honesty  # noqa: E402


def test_fixture_honesty_import_gate() -> None:
    # assert_fixture_honesty runs at module import; re-run explicitly for CI.
    assert_fixture_honesty()
    assert len(CASES) >= 8
    for case in CASES:
        assert len(case.resumes) >= 10
