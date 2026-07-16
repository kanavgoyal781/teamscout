# TeamScout deployment runbook

Zero → public URL using **Fly.io** (API) + **Vercel** (Next.js frontend).
No Kubernetes, Terraform, or extra platforms.

### Live production (current)

| Surface | URL |
|---|---|
| Frontend | https://teamscout-opal.vercel.app/ |
| API | https://teamscout-api.fly.dev |
| Health | https://teamscout-api.fly.dev/health |

`ALLOWED_ORIGINS` on Fly must include `https://teamscout-opal.vercel.app` (no trailing slash).  
Vercel `NEXT_PUBLIC_API_BASE` must be `https://teamscout-api.fly.dev`.

> **Honesty:** This repo also ships deploy **config + CI + demo-check**. New
> environments still need the steps below with real account tokens and API keys.
> If `FLY_API_TOKEN` / `VERCEL_TOKEN` are not in GitHub Environment secrets, CI
> skips or blocks deploy; that is expected.

Related files (must match this runbook):

| File | Role |
|---|---|
| [`fly.toml`](./fly.toml) | Fly app, port **8000**, volume `/data`, `/livez` check, `ENV=prod` |
| [`Dockerfile.backend`](./Dockerfile.backend) | Multi-stage image, Litestream binary, entrypoint |
| [`.dockerignore`](./.dockerignore) | Excludes `.env`, `node_modules`, `*.db`, `.git` from build context |
| [`scripts/docker-entrypoint.sh`](./scripts/docker-entrypoint.sh) | `/data` uploads + optional Litestream |
| [`litestream.yml`](./litestream.yml) | S3-compatible replica template (env-gated; runtime config generated) |
| [`vercel.json`](./vercel.json) | Monorepo install/build → `frontend/` |
| [`frontend/next.config.ts`](./frontend/next.config.ts) | `output: 'standalone'` for Docker; Vercel uses its own Next runtime |
| [`.github/workflows/ci.yml`](./.github/workflows/ci.yml) | `deploy` job after scope/lint/typecheck/test/frontend/eval |
| [`scripts/demo_check.py`](./scripts/demo_check.py) | `make demo-check` against live API |
| [`Makefile`](./Makefile) | `deploy-api` / `deploy-web` / `deploy-status` / `pipeline` wrappers |

### Operator shortcuts (repo root)

```bash
make deploy-status   # flyctl/vercel presence + auth + app status (no mutations)
make deploy-api      # flyctl deploy --config fly.toml --app teamscout-api
make deploy-web      # vercel --prod (uses root vercel.json → frontend/)
make pipeline        # scope + backend unit tests + offline evals (+ ranking evals when embeddings in .env)
DEMO_API_BASE=https://teamscout-api.fly.dev make demo-check
```

`make deploy-api` / `make deploy-web` **fail loudly** if the CLI is missing or if auth preflight fails (`fly auth whoami` / `vercel whoami`) — they do not invent a successful deploy. Full first-time setup remains §§1–2 below.
---

## Architecture (one box each)

```text
Browser → Vercel (Next.js)  --NEXT_PUBLIC_API_BASE-->  Fly.io (FastAPI :8000)
                                                         │
                                                         ├─ volume teamscout_data → /data
                                                         │    teamscout.db + uploads/
                                                         └─ optional Litestream → S3-compatible bucket
```

- **SQLite + in-memory rate limits** assume **one machine** (`min_machines_running = 1`, `auto_stop_machines = off` in `fly.toml`). Do not scale to multiple machines without an external rate-limit store and a shared DB story.
- Behind Fly’s proxy, rate-limit keys use the direct peer IP (see `docs/ARCHITECTURE.md`). Fine for light demos; multi-tenant production may need trusted-hop keying later.

---

## Prerequisites

1. [Fly.io](https://fly.io) account + [`flyctl`](https://fly.io/docs/hands-on/install-flyctl/)
2. [Vercel](https://vercel.com) account + project
3. Real integration keys (same as local `.env.example`):
   - `LLM_API_KEY` (+ optional `LLM_API_BASE`, `LLM_MODEL`)
   - `EMBEDDINGS_API_KEY`, `EMBEDDINGS_API`, `EMBEDDINGS_MODEL`
   - `JOBS_API_KEY` (+ `JOBS_API_BASE`, `JOBS_API_HOST`)
   - `SUMBLE_API_KEY` (+ optional `SUMBLE_BASE_URL`)
   - `OPS_TOKEN` (ops dashboard)
4. GitHub repo with Environment **`production`** (optional required reviewers)
5. **Google Drive (optional library sync):** folder must be **link-shared** (Anyone with the link → Viewer) for API-key access; native Google Docs/Sheets need export as PDF before sync; restrict `GOOGLE_DRIVE_API_KEY` to the **Drive API** only in Google Cloud Console.

---

## 1. Backend → Fly.io

### 1.1 Create app + volume

```bash
# From repo root. Rename app in fly.toml if "teamscout-api" is taken.
fly auth login
fly apps create teamscout-api   # skip if app already exists / fly.toml app= is set

# Volume name must match fly.toml [mounts].source = "teamscout_data"
# Region should match primary_region (default iad).
fly volumes create teamscout_data --region iad --size 1 --app teamscout-api
```

### 1.2 Set secrets (never commit)

`ALLOWED_ORIGINS` must be the **Vercel origin** (no trailing slash, no `*`).
In `ENV=prod` the API **refuses to start** without an explicit non-wildcard `ALLOWED_ORIGINS` (no localhost fallback).

```bash
fly secrets set --app teamscout-api \
  ENV=prod \
  DATABASE_URL=sqlite:////data/teamscout.db \
  LLM_API_KEY='…' \
  LLM_API_BASE='…' \
  LLM_MODEL='gpt-4o-mini' \
  EMBEDDINGS_API_KEY='…' \
  EMBEDDINGS_API='…' \
  EMBEDDINGS_MODEL='BAAI/bge-m3' \
  JOBS_API_KEY='…' \
  JOBS_API_BASE='https://jsearch.p.rapidapi.com' \
  JOBS_API_HOST='jsearch.p.rapidapi.com' \
  SUMBLE_API_KEY='…' \
  SUMBLE_BASE_URL='https://api.sumble.com' \
  OPS_TOKEN='…' \
  ALLOWED_ORIGINS='https://teamscout-opal.vercel.app'
```

Optional Google Drive keys: same pattern (`GOOGLE_DRIVE_API_KEY`, …).

Optional Litestream (S3-compatible) — only if you want continuous DB replication.
Credentials must be real keys (entrypoint maps `LITESTREAM_*` → `AWS_*` or you set `AWS_*` directly). **Do not** set `LITESTREAM_S3_ENDPOINT` for AWS S3 — omit it. Set it only for R2/MinIO.

```bash
# AWS S3 (omit endpoint entirely):
fly secrets set --app teamscout-api \
  LITESTREAM_S3_BUCKET='your-bucket' \
  LITESTREAM_S3_REGION='us-east-1' \
  LITESTREAM_ACCESS_KEY_ID='…' \
  LITESTREAM_SECRET_ACCESS_KEY='…'

# R2 / MinIO example (endpoint required):
# fly secrets set --app teamscout-api \
#   LITESTREAM_S3_BUCKET='your-bucket' \
#   LITESTREAM_S3_REGION='auto' \
#   LITESTREAM_S3_ENDPOINT='https://<account>.r2.cloudflarestorage.com' \
#   LITESTREAM_ACCESS_KEY_ID='…' \
#   LITESTREAM_SECRET_ACCESS_KEY='…'
```

If `LITESTREAM_S3_BUCKET` is **unset**, the entrypoint does **not** start Litestream (volume-only durability).
When Litestream **is** enabled: restore failures (bad creds/network) **fail container start** (`-if-replica-exists` still allows first boot with no replica yet).

### 1.3 First deploy

```bash
# .dockerignore excludes .env, node_modules, *.db, .git — never rely on .gitignore for this.
fly deploy --config fly.toml --app teamscout-api --build-arg "GIT_SHA=$(git rev-parse HEAD)"
```

Image build uses `Dockerfile.backend` (see `fly.toml` `[build]`). Entrypoint:

- ensures `/data/uploads` and symlinks `/app/uploads` → `/data/uploads`
- if Litestream env is set: restore DB if missing, then `litestream replicate -exec uvicorn …`
- else: `uvicorn app.main:app --host 0.0.0.0 --port 8000`

### 1.4 Verify API

```bash
# Liveness (always 200 if process up) — used by Fly http_service.checks
curl -sS "https://teamscout-api.fly.dev/livez"
# → {"status":"alive"}

# Readiness (200 only when integrations + DB are green; else 503 with checks)
curl -sS "https://teamscout-api.fly.dev/health" | jq .
# Expect ok=true and every check configured|ok for a real demo
```

Public hostname is typically `https://<app>.fly.dev` unless you attach a custom domain (`fly certs add`).

### 1.5 Logs & rollback

Fly has **no** `fly releases rollback` command. Redeploy a previous image:

```bash
fly logs --app teamscout-api
fly status --app teamscout-api
# List releases with image refs:
fly releases --app teamscout-api --image
# Redeploy a prior image (copy the image ref from the list):
fly deploy --image registry.fly.io/teamscout-api:deployment-XXXXXXXX --config fly.toml --app teamscout-api
```

---

## 2. Frontend → Vercel

### 2.1 Project settings

**Recommended (Vercel dashboard):**

1. Import the GitHub repo
2. **Root Directory** = `frontend`
3. Framework preset: Next.js (auto)
4. Install: `pnpm install` (enable corepack / pnpm 9)
5. Build: `pnpm build`
6. Env (Production):

| Name | Value |
|---|---|
| `NEXT_PUBLIC_API_BASE` | `https://teamscout-api.fly.dev` (no trailing slash) |

`frontend/next.config.ts` sets `output: 'standalone'` for **Docker** (`Dockerfile.frontend`). On Vercel, the platform uses its normal Next.js build/output; standalone is for self-hosted Node, not required by Vercel.

Root [`vercel.json`](./vercel.json) supports monorepo CLI deploys **without** changing Root Directory (install/build `cd frontend`). Prefer dashboard Root Directory = `frontend` for day-to-day; keep `vercel.json` for CI/`vercel` CLI from repo root.

### 2.2 CLI first deploy

```bash
# Link once (creates .vercel — do not commit tokens)
npm i -g vercel@39
cd frontend && vercel link   # or from root with vercel.json paths
vercel env add NEXT_PUBLIC_API_BASE production
# paste: https://teamscout-api.fly.dev

vercel --prod
```

After the frontend URL is known, **update Fly CORS**:

```bash
fly secrets set --app teamscout-api \
  ALLOWED_ORIGINS='https://teamscout-opal.vercel.app'
```

Prod rejects `ALLOWED_ORIGINS=*` (see `backend/app/main.py`).

### 2.3 Verify UI

1. Open the Vercel URL
2. Banner should not stay red if `/health` is fully green
3. Upload `samples/sample_resume.pdf` → confirm → search jobs

---

## 3. SQLite durability

### 3.A Volume (always on)

- Fly volume `teamscout_data` mounted at `/data`
- DB: `/data/teamscout.db` (`DATABASE_URL=sqlite:////data/teamscout.db`)
- Uploads: `/data/uploads` (entrypoint symlink from `/app/uploads`)

**Snapshot backup (no Litestream):**

```bash
fly volumes list --app teamscout-api
fly volumes snapshots list <vol_id> --app teamscout-api
# Create a snapshot (Fly may also take periodic snapshots depending on plan):
fly machine stop <machine_id> --app teamscout-api   # optional quiesce
fly volumes snapshots create <vol_id> --app teamscout-api
fly machine start <machine_id> --app teamscout-api
```

Restore from snapshot is a Fly volumes restore/fork flow — see current Fly docs for your plan; treat snapshots as the minimum DR path when Litestream is off.

### 3.B Litestream (optional, env-gated)

Config template: [`litestream.yml`](./litestream.yml). Runtime config is **generated** by [`scripts/docker-entrypoint.sh`](./scripts/docker-entrypoint.sh) (omits empty `endpoint`; credentials via AWS SDK env chain only):

- **Only if** `LITESTREAM_S3_BUCKET` is set **and** `litestream` binary is present (image includes it)
- Credentials required: `LITESTREAM_ACCESS_KEY_ID`+`LITESTREAM_SECRET_ACCESS_KEY` **or** `AWS_ACCESS_KEY_ID`+`AWS_SECRET_ACCESS_KEY`
- On start: `litestream restore -if-replica-exists` when DB file is missing (missing replica → success; other errors → container exit)
- While running: `litestream replicate -exec "uvicorn …"`
- **Omit** `LITESTREAM_S3_ENDPOINT` for AWS S3; set it only for R2/MinIO (never set it to empty string)

---

## 4. CI deploy pipeline

Workflow: [`.github/workflows/ci.yml`](./.github/workflows/ci.yml)

```text
scope → (lint, typecheck, test, frontend, eval)
                     ↘
                   deploy  (needs all of the above + scope)
```

- Runs only on **push** to `main` / `master` (not on PRs)
- `environment: production` — use GitHub Environment protection rules for manual approval
- If `FLY_API_TOKEN` or `VERCEL_TOKEN` is missing, the job **skips deploy** with a warning (does not print secret values)
- Vercel also needs `VERCEL_ORG_ID` and `VERCEL_PROJECT_ID` for non-interactive deploy

### Required GitHub secrets (Environment `production` recommended)

| Secret | Purpose |
|---|---|
| `FLY_API_TOKEN` | `flyctl deploy` |
| `VERCEL_TOKEN` | Vercel CLI |
| `VERCEL_ORG_ID` | Vercel team/org |
| `VERCEL_PROJECT_ID` | Vercel project |

Optional (already used by `eval` job): `LLM_*`, `EMBEDDINGS_*`.

Never add secrets to the repo or `echo` them in workflows.

---

## 5. Demo readiness

With the **server** holding real keys:

```bash
# From repo root (httpx required — `make install-backend` or pip install httpx)
DEMO_API_BASE=https://teamscout-api.fly.dev make demo-check
# equivalent: BACKEND_URL=https://teamscout-api.fly.dev python3 scripts/demo_check.py
```

Script steps (PASS/FAIL each; non-zero exit on failure):

1. `GET /health` reachable
2. `ok=true` (integrations configured on server)
3. Sample PDF present (`samples/sample_resume.pdf`)
4. `POST /resumes/upload`
5. `PUT /resumes/{id}/confirm`
6. `POST /searches` returns ≥1 result
7. Each result includes `score_breakdown` (incl. `final_score`)

The script does **not** ship or log API keys.

---

## 6. Seed / smoke after deploy

```bash
# Health
curl -sS "https://teamscout-api.fly.dev/health" | jq .

# Full demo path
DEMO_API_BASE=https://teamscout-api.fly.dev make demo-check

# Or manual upload of samples/sample_resume.pdf via the Vercel UI
```

---

## 7. Operational notes

### CORS

- Set `ALLOWED_ORIGINS` to the exact Vercel URL(s), comma-separated
- Rebuild/restart is automatic after `fly secrets set`

### Rate limits

- Configured via env (`RATE_LIMIT_*` in `.env.example`); defaults stay on in prod
- In-memory per process → keep **min 1 machine**; multiple machines split counters incorrectly

### Cold start

- `min_machines_running = 1` and `auto_stop_machines = off` avoid Fly scale-to-zero cold starts
- First request after a **deploy** still pays image boot (~tens of seconds) + first LLM/jobs latency
- `demo-check` uses a 300s read timeout on search for that reason

### Cost expectation (order of magnitude, not a quote)

| Item | Ballpark |
|---|---|
| Fly shared-cpu-1x 512MB, always on | ~$3–8 / month |
| Fly volume 1GB | usually free tier / low single-digit $ |
| Vercel Hobby | free for light frontend traffic |
| LLM + embeddings + JSearch + Sumble | **usage-based**; guardrails: `LLM_DAILY_COST_CEILING_USD`, `SUMBLE_DAILY_CREDIT_CEILING` |

Watch Sumble credit logs (INFO, redacted URLs) and `/ops` (token-gated).

### Security checklist

- [ ] No secrets in git
- [ ] Root `.dockerignore` present (blocks `.env` from Fly/Docker build context)
- [ ] `ENV=prod`, `ALLOWED_ORIGINS` explicit (required to boot in prod)
- [ ] `OPS_TOKEN` set
- [ ] Fly HTTPS forced (`force_https = true` in `fly.toml`)
- [ ] Volume exists before first deploy with mounts

---

## 8. Acceptance checklist

- [x] `fly.toml` + volume `/data` + secrets documented
- [x] Vercel / `NEXT_PUBLIC_API_BASE` production config
- [x] Litestream env-gated + volume snapshot alternative documented
- [x] CI `deploy` job `needs: [scope, lint, typecheck, test, frontend, eval]` + `environment: production`
- [x] This runbook matches config file names/paths
- [x] `make demo-check` → `scripts/demo_check.py`
- [ ] **Live** public URL — operator completes §§1–2 with real tokens (not claimed by config-only PRs)
- [ ] `make check-scope` green on the branch
- [ ] README points here

---

## Railway fallback

Use Railway only if Fly signup/deploy is blocked for the operator. Prefer Fly so this runbook and `fly.toml` stay the source of truth. On Railway: one service from `Dockerfile.backend`, persistent volume on `/data`, same secrets as §1.2, health path `/livez` or `/health` per Railway’s 2xx policy.
