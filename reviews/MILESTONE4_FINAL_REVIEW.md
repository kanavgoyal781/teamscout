# Milestone 4 — Final Code Review

**Date:** 2026-07-04  
**Scope:** Full codebase post M4 review fixes  
**Tests:** `pytest -q` → 71 passed; `pnpm build` + `pnpm test` → 6 passed; `smoke_api.py` → 8/8  
**Verdict:** **APPROVE**

---

## Summary

All eight items from the prior M4 review (`reviews/MILESTONE4_CODE_REVIEW.md`) are substantively resolved: unified `hybrid_rank.py`, full-library resume scoring via `score_pool="all"` (with a 36-candidate test), decomposed library UI, public `ResumeCandidate`, `experience_fit` in the schema, removed duplicate `justification`, shared `formatPostedAt`, and an updated `SPEC.md`. The honesty layer holds — no app-code mocks, typed 503s, optional Drive on `/health`, atomic email reveal. No ship-blocking bugs found; remaining items are docs/UI parity nits.

---

## M4 Blocker Resolution

| # | Prior issue | Status |
|---|-------------|--------|
| 1 | Duplicate ranking pipelines | **Resolved** — `hybrid_rank.py`; thin `ranking.py` / `resume_ranking.py` |
| 2 | Resume pool truncated to top-30 | **Resolved** — `score_pool="all"` + `test_rank_resumes_for_job_scores_full_library_beyond_rerank_top_n` |
| 3 | `library/page.tsx` god component | **Resolved** — 52-line composer + 3 panels + `useLibraryPage` |
| 4 | `_ResumeCandidate` leak | **Resolved** — `schemas/library.py` + `library_store.load_candidates()` |
| 5 | `recency` mislabeled | **Resolved** — `experience_fit` field; `recency=0.0` on resume path |
| 6 | Duplicate `justification` | **Resolved** — only `score_breakdown.rationale` |
| 7 | Duplicated `formatPostedAt` | **Resolved** — `frontend/lib/format.ts` |
| 8 | `SPEC.md` still M3 | **Resolved** — full M4 spec |

---

## Issues

### Issue 1 -- Severity: suggestion
- File: `AGENTS.md:1-38`
- Description: Root `AGENTS.md` still describes M3 only while `SPEC.md`/`README.md` document M4 (Drive, library, `hybrid_rank`, intent search, optional Drive health).
- Suggestion: Add an M4 section or point to `SPEC.md` as canonical scope.
- Status: open

### Issue 2 -- Severity: suggestion
- File: `frontend/components/ResumeRecommendations.tsx:67-74`
- Description: README promises "score breakdown" for resume picks, but UI shows only `match_score` and `rationale` — unlike Feature 1's expandable breakdown in `JobResultsList`.
- Suggestion: Add a `<details>` block surfacing `llm_fit`, `rrf_normalized`, `skill_jaccard`, and `experience_fit`.
- Status: open

### Issue 3 -- Severity: nit
- File: `frontend/app/page.tsx:11`, `frontend/components/ResumeWizard.tsx:8`, `frontend/hooks/useLibraryPage.ts:17`, `frontend/components/AppShell.tsx:10`
- Description: Toast type duplicated in four places.
- Suggestion: Extract `frontend/lib/toast.ts`.
- Status: open

### Issue 4 -- Severity: nit
- File: `backend/app/services/jobs.py:219`
- Description: `fetch_jobs_for_intent` assigns `location = ... or "United States"` but never uses it in JSearch params when location is empty.
- Suggestion: Align query construction with `fetch_jobs` or document the difference.
- Status: open

### Issue 5 -- Severity: nit
- File: `backend/app/services/hybrid_rank.py:70-140`
- Description: No dedicated unit tests for `hybrid_rank`; coverage is indirect via patched resume/job ranking tests.
- Suggestion: Add `test_hybrid_rank.py` for `score_pool` semantics.
- Status: open

### Issue 6 -- Severity: nit
- File: `backend/app/schemas/library.py:24-34`
- Description: `IntentProfile.as_query_profile()` uses `skills=[]`, so intent search always gets `skill_jaccard=0`.
- Suggestion: Derive skills from role or document de-emphasized skills signal in SPEC.
- Status: open

---

## AGENTS.md Compliance

| Rule | Result |
|------|--------|
| No mocks in `backend/app/` | ✓ |
| Hard-fail unconfigured services | ✓ |
| `/health` + optional Drive | ✓ |
| Config-presence health only | ✓ |
| Health banner, no loading flash | ✓ |
| Sumble credit logging | ✓ |
| Beta tabs disabled | ✓ |
| M3 retainers (email reveal, team flow) | ✓ |

---

## Build & Test Results

```
cd backend && pytest -q          → 71 passed
cd frontend && pnpm build        → ✓ routes: /, /library
cd frontend && pnpm test         → 6 passed
python scripts/smoke_api.py      → 8/8 PASS
python scripts/eval_ranking.py   → SKIP (no embeddings key)
python scripts/eval_resume_pick.py → SKIP (no embeddings key)
python scripts/smoke_sumble.py   → SKIP (no Sumble key)
make test                        → 71 + 6 passed
```

---

## Verdict: APPROVE

M4 blockers are fixed and tested. The codebase is demo-ready and structurally improved vs. the prior CONDITIONALLY APPROVE. Open items are docs/UI parity nits, not merge blockers.