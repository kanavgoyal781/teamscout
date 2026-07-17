# TeamScout

[![CI](https://github.com/kanavgoyal781/teamscout/actions/workflows/ci.yml/badge.svg)](https://github.com/kanavgoyal781/teamscout/actions/workflows/ci.yml)

**Recruiting intelligence for two jobs only:**

1. **Feature 1** — one resume → ranked live jobs → hiring team (+ optional email reveal)  
2. **Feature 2** — resume library → paste a JD → best-fit resumes (coverage + close-call tournament)

Production-hardened (CI, scope gates, rate limits, request IDs, cost ceilings) without platform sprawl. Deep notes: [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) · [CONSTRAINTS.md](./CONSTRAINTS.md).

---

## Live demo

| Surface | URL |
|---|---|
| **Frontend (Vercel)** | **https://teamscout-opal.vercel.app/** |
| **API (Fly.io)** | **https://teamscout-api.fly.dev** |
| Health | https://teamscout-api.fly.dev/health |
| Liveness | https://teamscout-api.fly.dev/livez |

```bash
DEMO_API_BASE=https://teamscout-api.fly.dev make demo-check
```

Deploy / secrets / rollback: **[docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md)**.

---

## How the system fits together

```mermaid
flowchart TB
  subgraph Client
    UI[Next.js UI<br/>Vercel]
  end
  subgraph API["Single FastAPI process · Fly.io"]
    Routers[Routers]
    Services[Domain services]
    SQLite[(SQLite + uploads<br/>volume /data)]
  end
  subgraph External
    LLM[LLM API]
    Emb[Embeddings API]
    Jobs[Job sources<br/>JSearch · ATS · feeds]
    Sumble[Sumble<br/>people + email]
    Drive[Google Drive<br/>optional]
  end

  UI -->|NEXT_PUBLIC_API_BASE| Routers
  Routers --> Services
  Services --> SQLite
  Services --> LLM
  Services --> Emb
  Services --> Jobs
  Services --> Sumble
  Services --> Drive
```

**One browser app · one API process · one SQLite file.** No queues, microservices, or remote vector DB.

### Deploy path

```mermaid
flowchart LR
  Dev[Local make dev] --> CI[GitHub CI<br/>scope · tests · evals]
  CI --> Fly[flyctl deploy<br/>teamscout-api]
  CI --> Vercel[vercel --prod<br/>teamscout UI]
  User[Browser] --> Vercel
  Vercel -->|API calls| Fly
  Fly --> Vol[(Fly volume<br/>/data SQLite)]
```

---

## Product flows

### Feature 1 — Resume → jobs → hiring team

Upload a resume, confirm the profile, search the live market, then (per job) extract hiring titles and look up people. Email reveal is gated and never double-charged.

```mermaid
flowchart TD
  A[Upload PDF/DOCX] --> B[LLM parse → ResumeProfile]
  B --> C[Confirm title · location · skills]
  C --> D[Optional query expand]
  D --> E[Fetch jobs multi-source]
  E --> F[Dense + BM25 → RRF]
  F --> G[Optional CE · LLM rerank]
  G --> H[Weighted fuse + MMR top N]
  H --> I[Job cards + score breakdown]
  I --> J[Extract team from JD]
  J --> K[Sumble people search]
  K --> L{Reveal email?}
  L -->|preview| M[Show credit cost]
  L -->|confirm| N[Reveal once<br/>no double-charge]
  M --> N

  P[Paste JD alternate] --> J
```

**Local walkthrough**

1. Open http://localhost:3000 → **Feature 1**  
2. Upload `samples/sample_resume.pdf` → confirm profile → **Search jobs**  
3. Open **Why this match** on a card  
4. **Find the team** → extract → confirm → optional email reveal  
5. Or use **Paste a job → extract hiring team** (no job board)

---

### Feature 2 — Library → best resume for a JD

Load many resumes, paste a full posting, get a ranked top-3 with evidence and an optional close-call tournament.

```mermaid
flowchart TD
  A[Upload · ZIP · Drive sync] --> B[Library SQLite<br/>units indexed]
  B --> C[Paste full JD]
  C --> D[Auto-detect title/company<br/>optional]
  D --> E[Decompose JD requirements]
  E --> F[MaxSim unit coverage]
  F --> G{Top scores close?}
  G -->|no| H[Order by coverage]
  G -->|yes| I[Pairwise tournament<br/>single judge default]
  I --> J[Borda merge]
  H --> K[Top 3 cards]
  J --> K
  K --> L[Why panel · alignment table]
  L --> M[Optional adversarial<br/>head-to-head · flag off by default]
```

**Local walkthrough**

1. Open http://localhost:3000/library  
2. Upload several resumes (or ZIP / Drive)  
3. Paste a real JD → **Find best resume for this job**  
4. Review score ring, one quiet metadata line, **Why this match**, alignment matrix  

---

### Job ranking funnel (Feature 1)

```mermaid
flowchart LR
  R[Retrieve<br/>~150+ jobs] --> D[Dense<br/>embeddings]
  R --> B[BM25<br/>lexical]
  D --> RRF[RRF fuse]
  B --> RRF
  RRF --> CE[Cross-encoder<br/>optional]
  CE --> LLM[LLM rerank]
  LLM --> Fuse[Weighted score]
  Fuse --> MMR[MMR diversify]
  MMR --> Out[Top 10 + facets]
```

Weights and ceilings live in env / `docs/ARCHITECTURE.md`. Fail loud if LLM or embeddings are missing — no silent fake ranks.

### Resume-pick ranking (Feature 2)

```mermaid
flowchart TD
  JD[JD text] --> Dec[Requirement atoms]
  Lib[Library resumes] --> Units[Bullet/skill units]
  Dec --> MaxSim[MaxSim evidence]
  Units --> MaxSim
  MaxSim --> Cov[Coverage score]
  Cov --> Band{Close-call band?}
  Band -->|gap ≥ threshold| Rank[Coverage order]
  Band -->|gap small| Tour[Pairwise judges]
  Tour --> Borda[Borda order]
  Rank --> Top[Top 3 + justify]
  Borda --> Top
```

Panel multi-model judging and adversarial critique are **opt-in** (`JUDGE_PANEL_MODELS`, `ADVERSARIAL_CRITIQUE`); single-judge remains default until evals show a flip-rate win.

---

## Honesty & credit safety

```mermaid
flowchart TD
  Call[LLM · Jobs · Sumble · Drive] --> Cfg{Configured?}
  Cfg -->|no| E503[ServiceNotConfiguredError<br/>503 JSON]
  Cfg -->|yes| Live[Live call]
  Live --> Trace[Trace + cost/credits]
  Trace --> Ceiling{Daily ceiling?}
  Ceiling -->|over| E429[429 CostCeilingExceeded]
  Ceiling -->|ok| OK[Response]

  Reveal[Email reveal confirm] --> Cache{Already revealed?}
  Cache -->|yes| Reuse[Return cached · no rebill]
  Cache -->|no| Charge[Charge once · store row]
```

- No mocks in app code · no silent fallbacks  
- Health banner when integrations are missing  
- Scope gate: `make check-scope` / `scripts/check_scope.py`

---

## Local development

### Prerequisites

- Python **3.12+**
- Node.js **20+**
- [pnpm](https://pnpm.io/installation) **9+**

### Configure and start

```bash
cp .env.example .env
# Minimum for full demos:
#   LLM_API_KEY, LLM_API_BASE, LLM_MODEL
#   EMBEDDINGS_API_KEY, EMBEDDINGS_API, EMBEDDINGS_MODEL
#   JOBS_API_KEY
#   SUMBLE_API_KEY
# UI → API:
#   ALLOWED_ORIGINS=http://localhost:3000
#   NEXT_PUBLIC_API_BASE=http://localhost:8000

make install
make dev
```

| Service | URL |
|---|---|
| UI | http://localhost:3000 |
| API | http://localhost:8000 |
| Health | http://localhost:8000/health |

```mermaid
flowchart LR
  Env[.env] --> API[uvicorn :8000]
  Env --> FE[next dev :3000]
  FE -->|fetch| API
  API --> DB[(teamscout.db)]
  API --> Up[uploads/]
```

### Docker (production-style local)

```bash
cp .env.example .env   # fill keys
docker compose up --build
```

API :8000 · UI :3000 · SQLite/uploads in named volumes.

### Google Drive (optional)

1. Enable Drive API; set `GOOGLE_DRIVE_API_KEY` (restrict key to Drive API only)  
2. Folder shared **Anyone with the link** (viewer)  
3. Library → paste folder URL → **Sync Drive folder**  
4. Native Docs/Sheets are skipped (export PDF first). Unconfigured Drive → clear 503.

---

## Public deploy (Fly + Vercel)

| Piece | Where |
|---|---|
| Frontend | https://teamscout-opal.vercel.app/ |
| API | https://teamscout-api.fly.dev (`fly.toml` → `teamscout-api`) |
| Runbook | [docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md) |

```bash
make deploy-status   # status only
make deploy-api      # flyctl deploy
make deploy-web      # vercel --prod
```

- Fly: `ALLOWED_ORIGINS=https://teamscout-opal.vercel.app`  
- Vercel: `NEXT_PUBLIC_API_BASE=https://teamscout-api.fly.dev` (build-time)

---

## Repository layout

```text
backend/app/          FastAPI
  api/routers/        HTTP
  services/           ranking · jobs_svc · team · resume · inference · library · ops · feedback
  schemas/ db/ core/ prompts/
frontend/
  app/                /  /library  /about
  components/         feature1 · feature2 · layout · about · ui · tour
  hooks/ lib/ e2e/
docs/                 ARCHITECTURE · DEPLOYMENT · CODEBASE · DEMO · SPEC
scripts/              check_scope · evals · smoke · demo_check
evals/ samples/ configs/
```

---

## API surface (summary)

| Area | Endpoints |
|---|---|
| Health | `GET /health`, `GET /livez` |
| Feature 1 | `POST /resumes/upload`, `PUT /resumes/{id}/confirm`, `POST /searches` |
| Team | `POST /jobs/from-text`, `…/extract-team`, `…/find-team`, `GET …/team`, `POST /contacts/{id}/reveal-email` |
| Feature 2 | `POST /library/upload`, `POST /library/drive/sync`, `GET /library/resumes`, `POST /library/recommend-from-jd` |
| Ops | `GET /ops`, `GET /ops/json` (token-gated) |

---

## Development commands

```bash
make test
python3 scripts/check_scope.py
cd backend && pytest -q
cd frontend && pnpm typecheck && pnpm test
cd frontend && pnpm test:e2e          # screenshots + craft assertions
python scripts/eval_ranking.py
python scripts/eval_resume_pick.py    # includes judge-stability bookkeeping
python scripts/smoke_sumble.py
```

---

## UI screenshots

Light mode is the default **cream + navy** editorial theme (dark variants as `*-dark.png`).

| Screen | Path |
|---|---|
| Wizard upload | `frontend/public/screenshots/01-wizard-upload.png` |
| Profile confirm | `frontend/public/screenshots/02-profile-confirm.png` |
| Job matches (why open) | `frontend/public/screenshots/03-job-matches.png` |
| Team discovery | `frontend/public/screenshots/04-team-discovery.png` |
| Resume library | `frontend/public/screenshots/05-library.png` |
| Top-3 comparison | `frontend/public/screenshots/06-resume-comparison.png` |
| About | `frontend/public/screenshots/07-about.png` |
| Paste-JD detecting | `frontend/public/screenshots/08-paste-jd-detecting.png` |
| Ops dashboard | `frontend/public/screenshots/09-ops.png` |

![Wizard upload](./frontend/public/screenshots/01-wizard-upload.png)

![Job matches](./frontend/public/screenshots/03-job-matches.png)

![Top-3 comparison](./frontend/public/screenshots/06-resume-comparison.png)

Refresh via Playwright:

```bash
cd frontend && pnpm test:e2e
```

---

## Stack

| Layer | Choice |
|---|---|
| Backend | FastAPI · Python 3.12 · Pydantic v2 |
| Frontend | Next.js · pnpm · Tailwind · React Query |
| Database | SQLite (SQLAlchemy) |
| Ranking | In-process dense + BM25 + RRF + LLM |
| Deploy | Fly.io (API) + Vercel (UI) |
| Secrets | Repo-root `.env` / platform secrets only |

---

## What we deliberately refuse

- Kubernetes, Terraform-as-product, Kafka/queues, microservices, feature stores  
- Silent LLM/job/Sumble fallbacks or mocks in app code  
- Third product surfaces (outreach send, full ATS) beyond beta stubs  

Contract: **[CONSTRAINTS.md](./CONSTRAINTS.md)** · enforced by **`make check-scope`**.

---

## Docs

| Doc | Purpose |
|---|---|
| [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) | Funnel math, credits, SQLite, M24 judge panel |
| [docs/DEPLOYMENT.md](./docs/DEPLOYMENT.md) | Zero → live Fly + Vercel |
| [docs/DEMO.md](./docs/DEMO.md) | Timed demo script |
| [docs/CODEBASE.md](./docs/CODEBASE.md) | Deep map of packages |
| [docs/SPEC.md](./docs/SPEC.md) | Product spec history |
| [AGENTS.md](./AGENTS.md) | Contributor / agent rules |
