# AGENTS.md — TeamScout

## What this is
Recruiting intelligence platform. Milestone 3 adds Feature 1 end-to-end: LLM team extraction, Sumble people search, and gated email reveal on the M1–M2 honesty layer.

## Architecture
- Backend: FastAPI (Python 3.12), Pydantic v2
- Frontend: Next.js with pnpm
- Database: SQLite via SQLAlchemy (no Postgres, no Docker required)
- Ranking: in-process dense + BM25 + RRF + LLM rerank
- Enrichment: Sumble REST (`SUMBLE_API_KEY`, base `https://api.sumble.com`)
- Secrets: repo-root `.env` only; never log keys

## Honesty layer (hard rules)
- NO mock data importable from app code (mocks only in `tests/` and `scripts/fixtures/`)
- NO silent fallbacks for LLM, embeddings, jobs API, or Sumble
- Unconfigured services raise typed `ServiceNotConfiguredError` (503-style JSON)
- `/health` reports `configured|missing|failing` per integration; `ok` is false if any check is missing or failing
- **M2/M3 health is config-presence only** for integrations; live probes reserved for later milestones
- Frontend must show a red degraded banner when health is not fully green (no flash while loading)
- Log credit-costing Sumble calls at INFO with redacted URLs

## Milestone 3 scope
- Team extraction (`services/team_extract.py`) + `POST /jobs/{job_id}/extract-team`
- Sumble client (`services/sumble.py`): org lookup, people search, email reveal
- Contacts APIs: `POST /jobs/{job_id}/find-team`, `GET /jobs/{job_id}/team`, `POST /contacts/{id}/reveal-email`
- SQLite `contacts` + `email_reveals` with no double-charge on email reveal
- Frontend wizard: upload → confirm → search → per-job team flow + email reveal
- `scripts/smoke_sumble.py` + pytest with `respx`

## Retained from M2
- Resume parsing + confirmation
- JSearch jobs client + SQLite cache
- Hybrid ranking + transparent `score_breakdown`
- `scripts/eval_ranking.py` + ranking math tests

## Not in M3
- Drive library, best-resume pick, Beta sidebar, outreach, applications, queues, pgvector, ParadeDB