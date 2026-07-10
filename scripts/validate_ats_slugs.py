#!/usr/bin/env python3
"""Validate ATS board slugs in configs/ats_companies.json against live APIs.

Prints dead/invalid slugs. Exit 0 always unless --strict (then non-zero if any dead).
Official APIs only — no HTML scraping.
"""
from __future__ import annotations
import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import httpx
ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "ats_companies.json"
URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
}
UA = {"User-Agent": "TeamScout-validate-ats/1.0"}
def check_one(source: str, slug: str, timeout: float) -> tuple[str, str, str]:
    url = URLS[source].format(slug=slug)
    try:
        with httpx.Client(timeout=timeout, headers=UA) as client:
            resp = client.get(url)
        if resp.status_code == 200:
            # empty board still "alive"
            return source, slug, "ok"
        return source, slug, f"http_{resp.status_code}"
    except httpx.HTTPError as exc:
        return source, slug, f"error:{type(exc).__name__}"
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="exit 1 if any slug is dead")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    tasks: list[tuple[str, str]] = []
    for source, slugs in data.items():
        if source not in URLS:
            print(f"unknown source key: {source}", file=sys.stderr)
            continue
        for slug in slugs:
            tasks.append((source, str(slug)))
    print(f"checking {len(tasks)} slugs from {CONFIG}")
    dead: list[tuple[str, str, str]] = []
    ok_n = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(check_one, s, slug, args.timeout) for s, slug in tasks]
        for fut in as_completed(futs):
            source, slug, status = fut.result()
            if status == "ok":
                ok_n += 1
            else:
                dead.append((source, slug, status))
                print(f"DEAD {source}/{slug} {status}")
    print(f"ok={ok_n} dead={len(dead)} total={len(tasks)}")
    if args.strict and dead:
        return 1
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
