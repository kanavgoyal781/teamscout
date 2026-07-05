# Milestone 3 — Strict Code Quality Review

**Date:** 2026-07-04  
**Scope:** Feature 1 end-to-end (team extraction + Sumble + gated email reveal)  
**Tests:** `pytest -q` → 54 passed  
**Verdict:** **REQUEST CHANGES** — behavior is solid; structure is accumulating debt that will block Milestone 4 cleanly.

---

## Executive Summary

Milestone 3 correctly delivers the product flow and the credit-safety fixes from the implement review are genuine improvements (`email_reveal.py`, extraction snapshot binding, `JobTeamSearch`). The backend service split (`sumble.py`, `team_extract.py`, `email_reveal.py`) is mostly clean.

The main regression is **frontend orchestration bolted into an already-busy `page.tsx`**, plus a **canonical data-access smell** in `jobs_store.resolve_job` that will get worse as Feature 2 adds more job/resume surfaces. There is a clear code-judo path: extract a `TeamDiscovery` feature module and make jobs addressable by id without scanning cache rows.

Do not approve on "it works" alone — decompose before Milestone 4 adds Drive library + second feature page.

---

## Blockers (structural)

### 1. `page.tsx` is becoming a god component — decompose before M4

**Severity:** Structural regression  
**Files:** `frontend/app/page.tsx` (504 lines)

M2 put resume upload + confirm + ranked jobs in one page. M3 added `JobTeamState`, `teamByJob`, five new handlers, hydration `useEffect`, and ~120 lines of nested team/contact JSX inside the job card map.

This is classic spaghetti growth: every new wizard step adds state keys, patch helpers, and inline conditionals to the same file. Milestone 4 needs a second feature (resume library) — continuing this pattern means either duplicating patterns or making `page.tsx` unmaintainable.

**Code-judo move (recommended):**

```
frontend/
  components/
    ResumeWizard.tsx      # steps 1-2 (upload, confirm, search)
    JobResultsList.tsx    # step 3 job cards + score panels
    TeamDiscoveryPanel.tsx # extract → confirm → contacts → reveal
  hooks/
    useJobTeam(jobId)     # teamByJob state, hydrate, handlers
  app/page.tsx            # thin composition (~80 lines)
```

Delete the `updateJobTeam` / `emptyTeamState` / handler cluster from the page; let `useJobTeam` own the per-job state machine. The page should not know about `pendingReveal` record shapes.

---

### 2. `resolve_job` scans 500 cache rows — wrong canonical layer

**Severity:** Structural / performance smell  
**Files:** `backend/app/services/jobs_store.py:8-16`

Every `extract-team`, `find-team`, and `GET /team` call loads up to 500 `JobCache` rows and linearly deserializes JSON until `job.id` matches. This is O(n) per request with no index use.

Jobs already have stable `job.id` in `payload_json` — that id should be queryable directly. Either:

- Add `job_id` column to `jobs_cache` at ingest time (indexed), or
- Store a `{job_id → cache_row_id}` map when search results are persisted

**Why this matters for M4:** Feature 2 will fetch and rank jobs again; team discovery will multiply lookups. Fixing now is cheaper than patching around it later.

---

### 3. `find_team` route is an orchestration god function

**Severity:** Boundary leak  
**Files:** `backend/app/api/routers/jobs.py:123-184`

The route handler directly: loads extraction, calls Sumble org + people, upserts contacts in a loop, flushes per person, loads reveals, records `JobTeamSearch`, commits. That's ~60 lines of business logic in the router.

Routers elsewhere (`contacts.py`, `resumes.py`) stay thin. This one should match:

```python
# services/team_search.py
def find_team_for_job(job_id, extraction_id, search_id, db) -> FindTeamResponse: ...
```

The router becomes 5 lines. Tests can target the service without HTTP. M4 resume-pick won't accidentally copy this pattern.

---

## High-conviction improvements (not blockers alone, but push hard)

### 4. Extraction records accumulate without dedup — confusing state model

**Files:** `backend/app/api/routers/jobs.py:108-120`, `db/models.py:48-55`

`TeamExtractionRecord` has `content_hash` but `extract-team` always inserts a new row. Clicking "Find the team" twice on the same job creates multiple extractions; `GET /team` returns `_latest_extraction` by `created_at`, which may not match the `extraction_id` the user confirmed.

**Simpler model:** Upsert on `(job_id, content_hash)` and return existing `extraction_id` when JD unchanged. Or add `confirmed_at` and require `find-team` to use the latest *confirmed* extraction only.

This deletes an entire class of "which extraction is active?" conditionals.

---

### 5. Misleading button label vs. two-step backend flow

**Files:** `frontend/app/page.tsx:397-407`

Button text is **"Find the team"** but `onClick` calls `handleExtractTeam` (LLM only). Actual Sumble search is a separate **"Confirm & search Sumble"** button.

Users and future maintainers will conflate these. Rename the first button to **"Extract team from description"** (or merge into one progressive button with explicit step indicator). The current naming hides the honesty-layer step the spec requires.

---

### 6. Hardcoded credit cost in UI

**Files:** `frontend/app/page.tsx:467`, `backend/app/services/sumble.py:18`

Frontend shows `"Reveal email — 10 Sumble credits"` as a string literal. Backend exposes `cost_credits` on preview response. The preview path already exists — use it for the initial button label so cost changes don't require frontend deploy.

Minor, but it's unnecessary dual-source-of-truth.

---

### 7. Eager hydration fan-out on every search

**Files:** `frontend/app/page.tsx:116-121`

When `results` arrives, `useEffect` calls `hydrateJobTeam` for all 10 jobs immediately. That's 10 `GET /team` calls even if the user only expands one job.

**Simpler:** Hydrate only on `<details>` open (already partially done at line 373-377) — remove the eager loop. The open handler is sufficient and deletes the effect entirely.

---

### 8. `email_reveal._begin_immediate` rolls back caller transactions

**Files:** `backend/app/services/email_reveal.py:23-29`

If `confirm_reveal` is called inside an outer transaction, `_begin_immediate` does `db.rollback()` then `BEGIN IMMEDIATE`. That silently destroys caller context.

Today `contacts.py` doesn't wrap transactions, so it works — but this is a footgun. Either document "must be top-level call" or use a nested connection. Prefer making the invariant explicit in the function docstring and a test that outer `db.commit()` state isn't corrupted.

---

### 9. Sumble `team` field fabrication

**Files:** `backend/app/services/sumble.py:190`

```python
team=team_name.strip() or attrs.get("job_function"),
```

When LLM returns empty `team_name`, the code substitutes `job_function` as `team`. That mislabels data shown in UI as "team" and violates the honesty principle for extracted vs. inferred fields.

Prefer `team=None` or `team=attrs.get("team")` if Sumble exposes it; don't backfill from department/function.

---

## What passed review

| Area | Assessment |
|------|------------|
| Credit-spend atomicity | `email_reveal.py` with `BEGIN IMMEDIATE` + terminal `not_found` — well done |
| Extraction-before-Sumble | Separate endpoints; `find-team` bound to `extraction_id` |
| Sumble client | Clean `_post` helper, typed errors, credit logging, no app mocks |
| `contacts.py` router | Thin — correct layer |
| `team_extract.py` | Small, focused, uses `complete_json` |
| Test coverage | 12 Sumble/reveal tests including race and cross-job cases |
| File size | No file >1k lines yet; `page.tsx` at 504 is the warning signal |
| Honesty layer | No silent fallbacks in Sumble path |

---

## Recommended PR plan (ordered)

1. **Extract `TeamDiscoveryPanel` + `useJobTeam`** — delete ~200 lines from `page.tsx`
2. **Add indexed `job_id` on `jobs_cache`** — replace `resolve_job` scan
3. **Move `find_team` orchestration to `services/team_search.py`**
4. **Dedup or confirm extractions** — simplify extraction state
5. **Remove eager hydration `useEffect`** — rely on details open only
6. **Fix button labels + dynamic credit cost from preview**

Items 1–3 are the code-judo moves that delete complexity rather than rearrange it. Do those before Milestone 4.

---

## Approval bar

| Criterion | Met? |
|-----------|------|
| No structural regression | **No** — `page.tsx` god growth |
| Obvious simplification path taken | **No** — decomposition deferred |
| No unjustified file-size explosion | **Borderline** — 504 lines, trending wrong |
| No spaghetti branching in shared paths | **No** — team state scattered in page |
| Logic in canonical layer | **Partial** — `resolve_job`, `find_team` in wrong layers |
| Credit safety | **Yes** |

**Verdict: REQUEST CHANGES** — fix items 1–3 (decompose frontend, fix job lookup, extract team search service) before calling M3 merge-complete. Items 4–9 can land in the same PR or immediately after, but 1–3 are the architectural debt that compounds in M4.