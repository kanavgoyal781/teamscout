# TeamScout

[![CI](https://github.com/OWNER/teamscout/actions/workflows/ci.yml/badge.svg)](https://github.com/OWNER/teamscout/actions/workflows/ci.yml)

Recruiting intelligence — resume→jobs→team and library→best-resume, with production hardening (containers, CI, rate limits, request IDs). See [ARCHITECTURE.md](./ARCHITECTURE.md).

> Replace `OWNER/teamscout` in the badge URL with your GitHub org/repo.

![About TeamScout](./frontend/public/screenshots/07-about.png)

## 3-minute demo (JobRight / Sumble)

### Prerequisites

- Python 3.12+
- Node.js 20+
- [pnpm](https://pnpm.io/installation) 9+

### 1. Configure and start

```bash
cd /path/to/teamscout
cp .env.example .env
# Fill LLM_API_KEY, EMBEDDINGS_API_KEY, JOBS_API_KEY, SUMBLE_API_KEY
make install
make dev
```

Optional frontend: `NEXT_PUBLIC_GITHUB_BASE=https://github.com/<org>/<repo>/blob/main` for About page repo links.


- Backend: http://localhost:8000
- Frontend: http://localhost:3000

### 2. Feature 1 — Resume → Jobs → Sumble team

1. Open http://localhost:3000 (sidebar: **Resume → Jobs → Team**)
2. Upload `samples/sample_resume.pdf`
3. Confirm title, location, and skills
4. Click **Search jobs** → review top 10 ranked matches
5. On a job, click **Extract team from description** → **Confirm & search Sumble**
6. Preview then confirm **Reveal email** per contact

### 3. Feature 2 — Resume library + best resume

1. Open http://localhost:3000/library (sidebar: **Resume Library**)
2. Upload multiple PDF/DOCX files or a ZIP of resumes (or sync a public Drive folder — see below)
3. Fill the intent form (role, years, location, remote preference) → **Search jobs by intent**
4. Click **Pick best resume** on a job
5. Review top 3 resumes with score breakdown, JD coverage table, and LLM justification

### Google Drive sync (optional)

Public shared-folder approach (recommended):

1. Create a Google Cloud project and enable **Google Drive API**
2. Create an API key and set `GOOGLE_DRIVE_API_KEY` in `.env`
3. Share the Drive folder as **Anyone with the link**
4. Paste the folder URL in the library UI → **Sync Drive folder**

Without `GOOGLE_DRIVE_API_KEY` (or OAuth client credentials), Drive sync hard-fails with a clear 503 error.


## Docker (production-style local)

```bash
cp .env.example .env
# Fill LLM_*, EMBEDDINGS_*, JOBS_*, SUMBLE_* (and optional Drive keys)
docker compose up --build
```

- API: http://localhost:8000  (`GET /health` includes `version`; `GET /livez` is process liveness)
- UI: http://localhost:3000
- SQLite + uploads persist in named volumes `teamscout-data` / `teamscout-uploads`
- Set `NEXT_PUBLIC_API_BASE=http://localhost:8000` (browser → host-mapped backend)
- Required env vars are documented in `.env.example` (compose uses `env_file: .env`)

## Public deploy (Fly.io + Vercel)

See **[DEPLOYMENT.md](./DEPLOYMENT.md)** for zero→live commands (`fly.toml`, secrets, Vercel `NEXT_PUBLIC_API_BASE`, Litestream/volume backups, CI deploy job, cost notes).

```bash
make deploy-status         # CLIs + auth + app status (no mutations)
make deploy-api            # flyctl deploy (requires fly auth + secrets)
make deploy-web            # vercel --prod (requires vercel auth + project link)
# After the API is live and secrets are set on the server:
DEMO_API_BASE=https://YOUR-APP.fly.dev make demo-check
```

Config-only PRs do not imply a public URL is already live — the runbook is the operator path.
## Development

```bash
make test
make pipeline              # scope → backend unit tests → fit-signal eval (+ ranking/resume-pick if embeddings in .env; + demo-check if DEMO_API_BASE)
make pipeline-offline      # scope → backend unit tests → fit-signal eval only
make eval-fit              # YOE + requirements order (no embeddings)
make eval                  # hybrid ranking NDCG/MRR (needs embeddings; LLM optional)
make eval-report           # trends from evals/history.jsonl
cd backend && pytest -q
cd frontend && pnpm build && pnpm test
python3 scripts/smoke_sumble.py
```
## API (M4)

| Endpoint | Description |
|---|---|
| `GET /health` | Config presence for all integrations |
| `POST /resumes/upload` | Parse PDF/DOCX → `ResumeProfile` |
| `PUT /resumes/{id}/confirm` | Confirm editable profile fields |
| `POST /searches` | Fetch jobs, hybrid rank, return top 10 |
| `POST /jobs/{job_id}/extract-team` | LLM team extraction from cached job JD |
| `POST /jobs/{job_id}/find-team` | Sumble people search with confirmed extraction |
| `GET /jobs/{job_id}/team` | List cached contacts for a job |
| `POST /contacts/{id}/reveal-email` | Preview or confirm email reveal (`?confirm=true`) |
| `POST /library/drive/sync` | Sync PDF/DOCX from public Drive folder |
| `POST /library/upload` | Upload multi-file or ZIP into resume library |
| `GET /library/resumes` | List library resumes (hash-deduped) |
| `POST /library/intent/search` | Fetch + rank jobs for intent form |
| `POST /library/jobs/{job_id}/recommend-resumes` | Top 3 library resumes for a job |

## Ranking pipeline

**Jobs (Feature 1)** — see [ARCHITECTURE.md](./ARCHITECTURE.md) for the full funnel:

1. Multi-source fetch (~150): optional LLM query expand → JSearch multi-query + optional Remotive/Arbeitnow; recency via `SearchParams.date_window` (default **month**); hard/soft prefs; exact/embedding dedupe; SQLite `jobs_cache`
2. Dense cosine similarity + BM25 lexical retrieval
3. Reciprocal Rank Fusion (`k=60`)
4. LLM rerank top 30 in batches of **6** (retry + labeled heuristic fill for omitted ids)
5. Final score (defaults): `0.38·LLM + 0.20·RRF + 0.12·skills + 0.12·experience + 0.10·requirements + 0.08·recency`, then soft-pref boosts + MMR diversify

**Resume pick (Feature 2):** JD → atomic requirements → MaxSim unit coverage → optional close-call pairwise tournament → top 3 with alignment + justification. Not hybrid RRF.

**Deploy model:** single-operator demo. No multi-user auth; protect public deploys with network gates / secrets and daily cost ceilings (see DEPLOYMENT.md).

## UI screenshots (M10)

Generated by Playwright e2e (`cd frontend && pnpm test:e2e`) with a route-mocked API — not live production captures.

| Screen | File |
|---|---|
| Wizard upload | `frontend/public/screenshots/01-wizard-upload.png` |
| Profile confirm | `frontend/public/screenshots/02-profile-confirm.png` |
| Job matches | `frontend/public/screenshots/03-job-matches.png` |
| Team discovery | `frontend/public/screenshots/04-team-discovery.png` |
| Resume library | `frontend/public/screenshots/05-library.png` |
| Top-3 comparison | `frontend/public/screenshots/06-resume-comparison.png` |

Embed after a local e2e run:

![Wizard upload](./frontend/public/screenshots/01-wizard-upload.png)
![Job matches](./frontend/public/screenshots/03-job-matches.png)
![Top-3 comparison](./frontend/public/screenshots/06-resume-comparison.png)

### Frontend elevation notes

- Dark-first theme + light toggle (cookie class strategy (no browser storage APIs))
- `@tanstack/react-query` for server data; credit mutations use `retry: false`
- Sonner toasts surface backend `message` and request id when present
- Lighthouse scores were **not** measured in this milestone; manual targets remain Perf ≥85 / A11y ≥95 / BP ≥95 if you run a local audit

## Architecture

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the ranking funnel, credit-safety, and deploy surface.

## Stack

| Layer | Choice |
|---|---|
| Backend | FastAPI, Python 3.12, Pydantic v2 |
| Frontend | Next.js, pnpm, Tailwind |
| Database | SQLite via SQLAlchemy |
| Secrets | Repo-root `.env` only |

## Milestone 4 scope

- Google Drive + local/ZIP resume library with content-hash dedup
- Intent form → ranked job list
- Best-resume pick with coverage table + LLM justification
- Sidebar navigation with disabled Beta tabs (tooltip: "Coming soon")
- `scripts/eval_resume_pick.py` + pytest coverage
- M3 structural debt: decomposed frontend, indexed job lookup, `team_search` service

Not implemented: outreach, applications tracker, auto-submit.