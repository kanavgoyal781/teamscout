# TeamScout — 3-minute demo script

Executable path for someone who has never opened the app. Clock assumes services are already healthy (see checklist). Sample asset: [`samples/sample_resume.pdf`](./samples/sample_resume.pdf) (Jane Doe, Senior Backend Engineer).

**UI truth (do not improvise labels):** sidebar uses **Feature 1** / **Feature 2** / **About**; product copy says **hiring team**, not “Sumble”.

---

## Pre-demo checklist (T−5 min)

Do these before the audience is watching. Skip a step only if that path is out of scope for the room.

| # | Check | Command / action | Pass criteria |
|---|---|---|---|
| 1 | Scope + offline gate (optional if CI green) | `make pipeline-offline` | exit 0 |
| 2 | Local stack up | `make dev` (or already running) | UI :3000, API :8000 |
| 3 | Health green | `curl -s http://localhost:8000/health \| python3 -m json.tool` | `"ok": true`; required checks `llm`, `embeddings`, `jobs_api`, `sumble` = `configured` (not `missing` / `failing`). `google_drive` may be `missing` — optional; Drive sync not required for this script. |
| 4 | UI degraded banner | Open http://localhost:3000 | No red health banner across the top |
| 5 | Live deploy smoke (only if demoing production) | `DEMO_API_BASE=https://teamscout-api.fly.dev make demo-check` | All steps pass. If unset/unreachable, demo **local** only — do not claim a public URL. |
| 6 | Sumble credits remaining | After any recent team call, or from provider dashboard / ops traces | Enough headroom for **one** find-team (~org + job-match or people path; UI estimates ~20–30 credit band before lookup) + optional **one** email reveal (preview shows cost, confirm spends). Prefer **skipping confirm reveal** if credits are tight. |
| 7 | Cost ceiling headroom | `.env`: `LLM_DAILY_COST_CEILING_USD` (default 5), `SUMBLE_DAILY_CREDIT_CEILING` (default 1000) | Ceilings not already exhausted (exceed → HTTP 429). Avoid re-running full search loops in rehearsal right before the take. |
| 8 | Sample file reachable | `ls samples/sample_resume.pdf` | Present |
| 9 | Feature 2 extras (recommended) | 2–3 **distinct** PDF/DOCX resumes ready (content-hash dedupes identical files) | Library can show a ranked list; one file still works but top-3 comparison needs diversity |

**Credit-safe variant:** stop Feature 1 after **Why this match** (no Find the team / reveal). Still shows ranking honesty.

---

## Script (≈ 3:00)

| Clock | Where | Exact click path | Technical talking point (one) |
|---:|---|---|---|
| **0:00–0:20** | Browser | Open **http://localhost:3000**. Point at sidebar: **Feature 1** (Resume → Jobs → Team), **Feature 2**, **About**, disabled **Coming soon** tabs. Health dot on brand row. | Single Next app → `NEXT_PUBLIC_API_BASE` → one FastAPI process + SQLite; no job queue. |
| **0:20–0:50** | Feature 1 | Drop zone **Drag & drop resume** → choose `samples/sample_resume.pdf` (or click browse). Wait for parse toast. | Upload hits `POST /resumes/upload`; LLM `complete_json` fills `ResumeProfile` (title, location, skills). Unconfigured LLM → typed 503, not mock data. |
| **0:50–1:10** | Confirm profile | Review title / location / skills chips. Click **Confirm profile**, then **Search jobs** (primary). Leave filters at defaults unless asked. | Search requires confirmed profile (`canSearch`); pipeline is multi-query fetch → dense+BM25 → RRF → batched LLM rerank → weighted fuse (defaults 0.38/0.20/0.12/0.12/0.10/0.08). |
| **1:10–1:40** | Top matches | Section **Top matches & team discovery**. Point at rank badge + score ring. On card **#1**, open **Why this match** (`<details>`). Show score bars: LLM fit, RRF, Skill, Experience, Requirements, Recency + rationale. | `score_breakdown` is server-computed and rendered as-is — same signals used in the fuse, not a separate marketing score. |
| **1:40–2:20** | Hiring team | On the same card: **Find the team** → **Extract team from description** → wait for extraction card (team / department / likely hiring titles) → **Confirm & find hiring team**. When people appear, optionally **Reveal email — preview cost** only (say “confirm spends credits” and stop, or confirm once if checklist #6 allows). | Extract is LLM-on-JD; people lookup is Sumble (org + job-post match primary, people filter fallback). Email reveal is two-step; DB `email_reveals` avoids double-charge. |
| **2:20–2:50** | Feature 2 | Sidebar **Feature 2**. Panel **1. Resume library**: multi-select 2–3 PDFs → **Upload files or ZIP**. Panel **2. Paste a job description**: title optional, paste a backend/platform JD (or invent 8–10 lines matching Python/FastAPI). Click **Find best resume for this job**. | MaxSim path: JD → atomic requirements → unit coverage; optional close-call tournament. **Not** hybrid RRF. UI label is “Find best resume…”, not “Pick best resume”. |
| **2:50–3:00** | Comparison | Point at **Best match** card, coverage %, rationale, score bars (Coverage / LLM fit / Skill / Experience). Optional: **About** for funnel diagram if time left. | Eval suite `resume_pick` in `evals/history.jsonl` is the regression gate for this path (`make eval` / `eval_resume_pick.py`). |

---

## Suggested paste JD (Feature 2, ~15 s to paste)

```text
Senior Backend Engineer

We need an engineer with strong Python and FastAPI experience building
high-throughput REST APIs, data pipelines, and cloud infrastructure (AWS).
Requirements: 5+ years backend, PostgreSQL, Redis, Docker/K8s familiarity,
ownership of production services and CI/CD.
```

Aligns with `samples/sample_resume.pdf` skills so the top card is easy to narrate.

---

## If something breaks mid-demo

| Symptom | Likely cause | Recovery |
|---|---|---|
| Red degraded banner | Missing key or `ok: false` | `curl …/health`; fix `.env`; restart backend |
| Search spins / empty | Jobs API key or rate limit | Check backend logs; confirm `jobs_api: configured` |
| “Find the team” empty people | Org not in Sumble / no match | Say so; show extraction card still worked; skip reveal |
| 429 on LLM/Sumble | Daily ceiling hit | Point at `LLM_DAILY_COST_CEILING_USD` / `SUMBLE_DAILY_CREDIT_CEILING`; continue on cached results if any |
| Feature 2 “Add resumes above first” | Empty library | Upload at least one PDF |
| Identical files don’t add rows | Content-hash dedup | Use distinct files |

---

## Out of scope for this script (do not open)

- Live **Sync Drive folder** (needs `GOOGLE_DRIVE_API_KEY` + public folder)
- Bulk email composer / mailto (optional after multiple reveals)
- `/ops` dashboard (needs `OPS_TOKEN`; operator-only)
- Beta sidebar items (disabled by design)

---

## After the demo

```bash
# Optional: refresh local eval snapshot for the README metrics table
make eval-fit
# with embeddings configured:
make eval
python3 scripts/eval_resume_pick.py
make eval-report
```
