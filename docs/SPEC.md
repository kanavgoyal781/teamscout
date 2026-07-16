# TeamScout — Milestone 4 Specification

> **Supersedes** the prior Milestone 3 spec for active product scope. See `AGENTS.md` and `README.md`.

## Product

**TeamScout** is a recruiting intelligence platform. Milestone 4 adds **Feature 2 end-to-end**: resume library ingestion (upload + Google Drive sync), paste-JD best-resume pick with coverage and LLM justification — on top of the M3 Feature 1 stack (team extraction, Sumble people search, email reveal). Intent-search and recommend-by-job-id library routes remain on the API for smoke/tests but are not the primary UI path.

## Architecture (M4)

| Layer | Choice |
|---|---|
| Backend | FastAPI, Python 3.12, Pydantic v2 |
| Frontend | Next.js, pnpm, Tailwind |
| Database | SQLite via SQLAlchemy |
| Ranking | Shared `hybrid_rank.py`: dense embeddings + BM25 + RRF + LLM rerank (top 30) + weighted fuse |
| Library | `library_store.py`, `drive.py`, `resume_ranking.py` |
| Enrichment | Sumble REST API (`SUMBLE_API_KEY`) |
| Secrets | Repo-root `.env` only |

**Explicitly not in M4:** PostgreSQL, ParadeDB, pgvector, queues/DLQ, outreach, applications tracker, Beta sidebar (tabs disabled only).

## Honesty layer

1. External services (`llm`, `embeddings`, `jobs_api`, `sumble`, `drive`) must **hard-fail** when unconfigured.
2. No mock data importable from `backend/app/` (mocks only in `tests/` and `scripts/fixtures/`).
3. No silent fallbacks for missing API keys or failed HTTP calls.
4. Typed errors in `errors.py` map to clean JSON (`503` for missing config or failing services).
5. Credit-costing Sumble calls logged at INFO with redacted URLs.

## Resume parsing (M2, retained)

- `services/parser.py`: PyMuPDF for PDF, python-docx for DOCX
- LLM structuring via `services/llm.py` into `ResumeProfile`
- `POST /resumes/upload`, `PUT /resumes/{id}/confirm`

## Jobs API (M2, retained)

- `services/jobs.py`: JSearch (RapidAPI)
- SQLite cache in `jobs_cache`
- Hard-fail if `JOBS_API_KEY` missing

## Ranking

- `services/hybrid_rank.py`: **job search only** — dense + BM25 + RRF + LLM rerank + fuse
- `services/ranking.py`: resume→jobs (`POST /searches`, intent search); soft prefs + MMR diversify
- `services/resume_ranking.py`: job→resumes (best-resume pick) via **MaxSim**, not hybrid_rank
- Job search: optional query expand; hard/soft `SearchParams`; LLM rerank top 30 (batches of 6); return top 10
- Resume pick: JD decompose → unit MaxSim coverage → optional close-call pairwise tournament → justify; return top 3

## Resume library (M4)

| Endpoint | Description |
|---|---|
| `GET /library/resumes` | List library resumes |
| `POST /library/upload` | Upload PDF/DOCX/ZIP; hash dedup |
| `POST /library/drive/sync` | Sync Google Drive folder (paginated, incremental re-sync) |
| `POST /library/recommend-from-jd` | **Primary Feature 2 UI path:** paste JD → cache job → rank all library resumes → top 3 + coverage |
| `POST /library/intent/search` | Retained API / smoke: intent profile → fetch jobs → hybrid rank (not active UI) |
| `POST /library/jobs/{job_id}/recommend-resumes` | Retained API / smoke: rank all library resumes for an existing `job_id` |

Drive edge cases:
- Pagination for large folders
- Re-sync skips unchanged files by `modified_time` + content hash
- `files_ignored` for non-PDF/DOCX

## Team extraction (M3, retained)

- `services/team_extract.py`: LLM extracts from JD
- `POST /jobs/{job_id}/extract-team`
- `POST /jobs/{job_id}/find-team`, `GET /jobs/{job_id}/team`
- `POST /contacts/{contact_id}/reveal-email` with atomic credit spend

## Frontend (M4)

| Page | Components |
|---|---|
| `app/page.tsx` | Feature 1: `ResumeWizard`, `JobResultsList`, `TeamDiscoveryPanel` |
| `app/library/page.tsx` | Feature 2: `LibraryIngestPanel`, `PasteJdPanel`, `ResumeRecommendations` |

Shared utilities: `frontend/lib/format.ts` (`formatPostedAgo`, score helpers).

## Smoke tests

- `scripts/smoke_sumble.py`: real Sumble when configured; loud SKIP when missing
- `scripts/smoke_api.py`: FastAPI TestClient exercises health, upload, search, library flows

## Tests

- pytest with `respx` mocking external HTTP (in `tests/` only)
- Resume pick: MaxSim ranks entire library; property tests for coverage/tournament; hard eval ≥7/8 near-dup libraries
- All existing tests must pass

## Acceptance criteria

- [ ] `cd backend && pytest -q` passes
- [ ] `cd frontend && pnpm build && pnpm test` passes
- [ ] `python scripts/eval_ranking.py` and `python scripts/eval_resume_pick.py` pass or skip loudly
- [ ] `python scripts/smoke_sumble.py` passes with key OR skips loudly
- [ ] `python scripts/smoke_api.py` reports PASS for all steps

## Later milestones (not M4)

Beta sidebar, outreach, applications tracker.