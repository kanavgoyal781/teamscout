#!/usr/bin/env python3
"""JD metadata extraction eval — real LLM; loud skip without keys."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

FIXDIR = ROOT / "backend" / "tests" / "fixtures" / "jd_metadata"
HISTORY = ROOT / "evals" / "history.jsonl"
PRESENT_FIELDS = (
    "title",
    "company",
    "location",
    "remote_mode",
    "salary_min",
    "salary_max",
    "salary_currency",
    "seniority",
    "department",
)


def _keys_configured() -> bool:
    return bool(os.getenv("LLM_API_KEY") and os.getenv("LLM_API_BASE"))


def _match(exp, act, field: str) -> bool:
    e, a = exp.get(field), act.get(field)
    if e is None and a is None:
        return True
    if e is None or a is None:
        return False
    if field in ("salary_min", "salary_max"):
        return int(e) == int(a)
    if field == "salary_currency":
        return str(e).upper() == str(a).upper()
    if field == "remote_mode":
        return str(e).lower() == str(a).lower()
    el, al = str(e).lower().strip(), str(a).lower().strip()
    return el == al or el in al or al in el


def main() -> int:
    print("TeamScout jd_metadata eval")
    if not _keys_configured():
        print("SKIP: LLM_API_KEY / LLM_API_BASE not set — cannot run jd_metadata suite (loud skip).")
        return 0
    from app.db.session import SessionLocal, ensure_db
    from app.services.jobs_svc.jd_metadata import extract_job_metadata

    ensure_db()
    fixtures = sorted(FIXDIR.glob("*.json"))
    if len(fixtures) < 10:
        print(f"FAIL: need ≥10 fixtures, found {len(fixtures)}")
        return 1
    hits = present = 0
    sparse_fail = 0
    details = []
    db = SessionLocal()
    try:
        for path in fixtures:
            data = json.loads(path.read_text())
            exp = data["expected"]
            meta, _, _ = extract_job_metadata(data["raw"], db=db)
            act = meta.model_dump()
            if data.get("sparse"):
                for f in PRESENT_FIELDS:
                    if exp.get(f) is None and act.get(f) is not None:
                        sparse_fail += 1
                        details.append(f"{data['id']} hallucinated {f}={act.get(f)!r}")
            for f in PRESENT_FIELDS:
                if exp.get(f) is None:
                    continue
                present += 1
                if _match(exp, act, f):
                    hits += 1
                else:
                    details.append(f"{data['id']} {f}: exp={exp.get(f)!r} got={act.get(f)!r}")
    finally:
        db.close()
    acc = (hits / present) if present else 0.0
    print(f"present_field_hits={hits}/{present} accuracy={acc:.3f}")
    print(f"sparse_hallucinations={sparse_fail}")
    for line in details[:30]:
        print(" ", line)
    record = {
        "suite": "jd_metadata",
        "ts": datetime.now(timezone.utc).isoformat(),
        "accuracy": round(acc, 4),
        "hits": hits,
        "present": present,
        "sparse_hallucinations": sparse_fail,
        "fixtures": len(fixtures),
        "model": os.getenv("LLM_MODEL"),
    }
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    print(f"appended {HISTORY}")
    if sparse_fail > 0:
        print("FAIL: sparse hallucinations")
        return 1
    if acc < 0.90:
        print("FAIL: accuracy < 0.90")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
