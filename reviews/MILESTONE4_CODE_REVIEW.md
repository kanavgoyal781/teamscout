# Milestone 4 — Strict Code Quality Review

**Date:** 2026-07-04  
**Scope:** Feature 2 (library, Drive, intent search, best-resume pick) + M3 structural refactors  
**Tests:** `pytest -q` → 70 passed  
**Verdict:** **CONDITIONALLY APPROVE** — behavior and M3 debt resolution are strong; two structural simplifications remain before I'd call this codebase "clean."

---

## Executive Summary

Milestone 4 successfully lands Feature 2 and resolves the M3 blockers (decomposed Feature 1 UI, indexed `job_id`, extracted `team_search`). File sizes are healthy — nothing approaches 1k lines. The honesty layer, Drive pagination, incremental re-sync, and justification guards are well implemented.

The main maintainability debt is **parallel ranking implementations** (`ranking.py` vs `resume_ranking.py`) that duplicate ~80% of the hybrid pipeline. There is a clear code-judo move: one generic ranker with query/candidate adapters would delete an entire module's orchestration logic. Secondary concern: **`library/page.tsx` is repeating the M3 anti-pattern** Feature 1 just escaped — a 355-line page that should be three panels.

I would not block ship on correctness for typical demo libraries (≤30 resumes), but the resume-rank pool truncation violates the spec literal ("rank **all** library resumes") for larger libraries.

---

## Blockers / High-Conviction Issues

### 1. Duplicate hybrid ranking pipelines — missed code-judo move

**Severity:** Structural (presumptive blocker per review skill)  
**Files:** `backend/app/services/ranking.py` (201 lines), `backend/app/services/resume_ranking.py` (283 lines)

Both modules independently implement:
- dense embedding rank
- BM25 lexical rank
- RRF fusion + normalization
- LLM rerank with ID-set validation
- weighted `fuse_final_score` assembly

The loops in `rank_jobs` (lines 111–171) and `rank_resumes_for_job` (lines 214–284) are nearly isomorphic — only the entity direction and rerank schema differ.

**This refactor moves complexity around, not delete it** — until unified.

**Recommended judo:**

```python
# services/hybrid_rank.py
@dataclass
class Rankable:
    id: str
    dense_text: str
    lexical_text: str
    skills: list[str]

def hybrid_rank(
    query: Rankable,
    candidates: list[Rankable],
    *,
    rerank_fn: Callable[[list[Rankable]], dict[str, RerankResult]],
    recency_fn: Callable[[Rankable], float],
    top_n: int,
) -> list[ScoredResult]: ...
```

`ranking.py` and `resume_ranking.py` become thin wrappers: map `Job`/`ResumeProfile` → `Rankable`, call `hybrid_rank`, map back. Deletes ~120 lines and one entire class of "fix ranking bug twice" risk.

---

### 2. Resume pick only scores RRF top-30 — libraries >30 silently excluded

**Severity:** Correctness / spec alignment  
**Files:** `backend/app/services/resume_ranking.py:229-284`, `backend/app/core/config.py:41`

```python
rerank_ids = rrf_ranked_ids[: settings.RERANK_TOP_N]  # default 30
for resume_id in rerank_ids:  # ONLY these enter output
```

Spec: *"backend ranks **all** library resumes against that job description."* A library of 40 resumes means 10 never enter the candidate pool — not ranked with `llm_fit=0`, not listed — invisible.

For job→resume ranking, the pool is the **entire library**, not a pre-trimmed retrieval set. Job ranking trims 100–200 fetched jobs to top 30 for LLM cost; resume libraries can be larger and the pool IS the library.

**Fix:** Either:
- Set `rerank_ids = rrf_ranked_ids` when `len(candidates) <= RERANK_TOP_N`, else document cap; or
- Two-phase: score all with RRF+components, LLM rerank top 30, merge scores back into full pool, then take top 3.

Add test: 35 synthetic candidates, best resume at RRF rank 31 → must still surface or spec must change.

---

### 3. `library/page.tsx` repeating god-component pattern

**Severity:** Structural regression (M3 lesson not applied to M4)  
**Files:** `frontend/app/library/page.tsx` (355 lines)

Feature 1 was decomposed into `ResumeWizard`, `JobResultsList`, `TeamDiscoveryPanel`. Feature 2 bolted ingest + intent + pick + recommendations into a single page with 15 `useState` hooks and inline job/recommendation cards.

**Recommended decomposition (mirror Feature 1):**

| Component | Owns |
|-----------|------|
| `LibraryIngestPanel` | upload, Drive sync, resume list |
| `IntentSearchPanel` | intent form, job results |
| `ResumeRecommendations` | pick job, coverage table, justification |
| `library/page.tsx` | composition + toast wiring (~80 lines) |

Not a ship blocker if M5 isn't planned, but this is the same mistake M3 review flagged — applying the lesson to Feature 1 but not Feature 2 is inconsistent architecture.

---

## Medium Issues

### 4. Private type leaked across API boundary

**Files:** `backend/app/api/routers/library.py:22,97-104`, `scripts/eval_resume_pick.py:14`

```python
from app.services.resume_ranking import _ResumeCandidate
```

Router and eval script import a `_`-prefixed private type. Move `ResumeCandidate` to `schemas/library.py` (public) or add `library_store.load_candidates(db) -> list[ResumeCandidate]`.

---

### 5. `score_breakdown.recency` mislabeled in resume ranking

**Files:** `backend/app/services/resume_ranking.py:256-261,271`

`_experience_score()` feeds the `recency` slot of `fuse_final_score` and is stored as `score_breakdown.recency`. This is the same honesty problem M2 fixed for dense-only `rrf_normalized` mislabeling — UI shows "Recency" but it's a years-of-experience heuristic.

Rename to `experience_fit` in schema or document in breakdown. Don't reuse the job-posting recency field name for a different signal.

---

### 6. Duplicate `justification` and `rationale` fields

**Files:** `backend/app/services/resume_ranking.py:277-279`, `schemas/library.py`

`RankedResumeRecommendation` stores the same LLM string in both `score_breakdown.rationale` and `justification`. Pick one canonical field; the other is redundant API surface.

---

### 7. Duplicated frontend utilities

**Files:** `formatPostedAt` in `JobResultsList.tsx`, `library/page.tsx`; `Toast` type in `page.tsx`, `library/page.tsx`, `ResumeWizard.tsx`

Extract `frontend/lib/format.ts` and `frontend/lib/toast.ts` (or a shared type). Small but signals missing shared frontend conventions now that there are two feature pages.

---

### 8. `SPEC.md` still Milestone 3

**File:** `SPEC.md:1`

Says "Explicitly not in M3: Google Drive sync, best-resume pick, Beta sidebar." README is accurate; spec will mislead the next contributor. Update or add M4 section.

---

## What Passed the Strict Bar

| Criterion | Result |
|-----------|--------|
| No file >1k lines | ✓ Max `library/page.tsx` 355 |
| M3 structural debt resolved | ✓ Decomposed Feature 1, indexed job_id, team_search |
| No silent fallbacks in app code | ✓ |
| Beta tabs disabled only | ✓ `Sidebar.tsx` |
| Drive edge cases (post-fix) | ✓ Pagination, re-sync skip, files_ignored |
| Health optional Drive | ✓ `REQUIRED_CHECKS` / `OPTIONAL_CHECKS` |
| Atomic email reveal (M3) | ✓ Retained |
| Router thinness (mostly) | ✓ `library.py` ~107 lines; `contacts.py` 26 lines |
| Tests | ✓ 70 pytest; library/drive/resume_ranking covered |
| README demo path | ✓ `samples/sample_resume.pdf`, step-by-step |

---

## Code-Judo Opportunities Ranked

1. **Unify hybrid ranker** — deletes the largest duplication in the backend
2. **Decompose `library/page.tsx`** — prevents second god component
3. **Public `ResumeCandidate` + `load_library_candidates()`** — fixes boundary leak
4. **Full-library resume pool** — align implementation with spec literal
5. **Shared `formatPostedAt`** — trivial, do with library decomposition

---

## Approval Bar Checklist

| Bar | Met? |
|-----|------|
| No clear structural regression | **Partial** — library page regresses M3 lesson |
| No obvious simplification missed | **No** — duplicate ranking pipelines |
| No unjustified file-size explosion | ✓ |
| No spaghetti branching in shared paths | ✓ |
| No hacky abstractions | ✓ |
| No boundary leaks | **Partial** — `_ResumeCandidate` import |
| Canonical layer reuse | **No** — ranking duplicated instead of shared |

---

## Verdict

**CONDITIONALLY APPROVE** for milestone completion and demo readiness.

**Before calling the codebase "done-done":**
1. Unify `ranking.py` + `resume_ranking.py` through a shared hybrid ranker (highest ROI)
2. Fix full-library resume pool semantics (or narrow spec to "top 30 by retrieval")
3. Decompose `library/page.tsx` to match Feature 1 architecture

Items 4–8 are worth fixing in the same pass but are not ship-blocking for a JobRight/Sumble demo with ≤30 library resumes and configured API keys.