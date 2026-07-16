# CONSTRAINTS — TeamScout architectural contract

This is a hard contract. Drift fails CI via `scripts/check_scope.py` (`make check-scope`).
Violations are named codes; the job exits non-zero. Do not “temporarily” bypass gates.

## Anti-bloat (binding)

This is a **focused two-feature app**, not a platform. **Every addition must earn its place.**

**BANNED** (do not introduce, even “just for prod readiness”):

| Category | Examples (non-exhaustive) |
|---|---|
| Orchestration / IaC | Kubernetes, Terraform, Helm, service meshes (Istio, Linkerd) |
| Data / ML platform | Feature stores, model registries, remote vector DBs as product infra |
| Messaging | Kafka, Celery, Redis-as-queue, pika, RQ, Dramatiq, other job queues |
| Architecture fashion | Microservices splits, service meshes, A/B testing frameworks (LaunchDarkly, Optimizely, Split, etc.) |
| Wrong web stacks | Django, Flask, LangChain, LlamaIndex as app dependencies |

**Production-grade here means only:**

1. **Reproducible builds** — lockfiles + pinned/allowlisted deps  
2. **CI that blocks bad code** — `scope` job first, tests, coverage ≥80  
3. **Observable LLM / credit-costing calls** — structured logs + redacted URLs; Sumble credits at INFO  
4. **Eval regression gates** — `evals/thresholds.json` floors enforced by `check_scope`  
5. **Secure defaults** — no mocks in app code, no silent fallbacks, secrets in `.env` only  
6. **A live deployment** — one deployable API + Next frontend; not a cluster

Anything beyond that list must be justified in a PR and still pass `check_scope`. Prefer deleting complexity over wrapping it.

## Scope

- **Two features + beta stubs only.** Feature 1 (resume → jobs → team → email) and Feature 2 (library → intent → best resume). Beta sidebar stays disabled stubs. No outreach product, applications tracker, or third surface.
- **SQLite only.** No Postgres, no Docker-required DB, no multi-DB fan-out.
- **In-process ranking.** Dense + BM25 + RRF + LLM rerank in-process. No remote feature stores, vector DBs, or model registries.
- **No distributed infrastructure** — see anti-bloat table above.
- **No silent fallbacks.** LLM, embeddings, jobs API, Sumble: unconfigured → typed `ServiceNotConfiguredError`; failing → typed fail. Never invent data.
- **No mocks importable from app code.** Mocks and fixtures live only in `tests/` and `scripts/fixtures/`.
- **Fail loud.** Bare `except:` / `except Exception` / `except BaseException` (and tuples containing them) banned in `backend/app` except the tiny allowlist in `scripts/except_allowlist.txt` (exact kind match only).

## Dependency & structure locks

- Backend deps must appear in `scripts/allowed_deps_backend.txt` **with a non-empty `# why` comment** (enforced).
- Frontend deps must appear in `scripts/allowed_deps_frontend.txt` **with a non-empty `# why` comment** (enforced).
- Only `backend/requirements.txt` (+ any `backend/requirements*.txt`) and `frontend/package.json` are allowed dependency surfaces; secondary manifests (Pipfile, poetry.lock, pyproject dep tables, setup.py) fail the gate.
- Top-level dirs exactly: `backend`, `frontend`, `scripts`, `samples`, `evals`, `configs`, `docs`, `.github`.
- `backend/app` package dirs exactly: `api`, `core`, `db`, `schemas`, `services`, `prompts`.

## Size budgets (do not raise)

- Any file under `backend/app/services/` ≤ 450 lines.
- `backend/app/main.py` ≤ 130 lines.
- Total `backend/app` Python LOC ≤ 10100.

## Frontend

- Exactly one lockfile: `pnpm-lock.yaml` (no npm/yarn lockfiles).
- No `localStorage` / `sessionStorage` in app surface (`app`, `components`, `hooks`, `lib`).
- No second UI framework (styled-components / emotion / MUI / antd).
- Banned imports/terms scanned in `frontend/app|components|hooks|lib`.

## Prompts

- Versioned prompt files live under `backend/app/prompts/` with YAML frontmatter (`name` + `version`).
- No `*_PROMPT` constants in `backend/app/services/`; load via `app.prompts.load_prompt`.

## Eval floors (do not lower)

- Floors live in `evals/thresholds.json` and are re-checked against hardcoded floors in `check_scope.py`.
- Coverage fail-under stays ≥ 80 on a **live** backend CI `run:` command (`--cov=app` and `--cov-fail-under=N` with N≥80); YAML comments do not count.

## Enforcement

```text
make check-scope          # scripts/check_scope.py
pytest backend/tests/test_scope.py
```

CI must include job `scope` that runs `scripts/check_scope.py`. **Every other job must `needs: scope`** (enforced by the gate).

### Residual bypasses (honest)

`check_scope.py` is a stdlib static gate, not a security boundary. Remaining hard residuals after the gates above:

- Dynamic `__import__` / `importlib` of banned modules
- Obfuscated string concatenation for banned terms
- Dishonest but present `# why` text (needs human review)
- `TEAMSCOUT_SCOPE_ROOT` / `--root` must not be set in CI (test-only override)

Reviewers still own intent; the script catches accidental and casual drift.
