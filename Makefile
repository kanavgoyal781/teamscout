.PHONY: dev backend frontend test install install-backend install-frontend \
	check-scope demo-check eval eval-fit eval-report pipeline pipeline-offline \
	deploy-api deploy-web deploy-status

# Backend loads repo-root .env automatically (see backend/app/core/config.py).
dev:
	$(MAKE) -j2 backend frontend

backend:
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

frontend:
	cd frontend && pnpm dev

install: install-backend install-frontend

install-backend:
	cd backend && python3 -m pip install -r requirements.txt -r requirements-dev.txt

install-frontend:
	cd frontend && pnpm install

check-scope:
	python3 scripts/check_scope.py

# Live demo gate against a deployed API (not local TestClient).
# Requires DEMO_API_BASE or BACKEND_URL, e.g.:
#   DEMO_API_BASE=https://teamscout-api.fly.dev make demo-check
demo-check:
	python3 scripts/demo_check.py

# —— Lightweight ML ops (in-process; no MLflow/feature-store platforms) ——

# Hybrid ranking NDCG/MRR (needs embeddings; LLM optional — script runs use_llm=False).
eval:
	python3 scripts/eval_ranking.py

# Offline YOE + requirements fit signals (no external APIs).
eval-fit:
	python3 scripts/eval_fit_signals.py

# Trend report from evals/history.jsonl.
eval-report:
	python3 scripts/eval_report.py

# Full product pipeline gate: scope → backend unit tests → fit-signal eval
# (+ ranking/resume-pick when embeddings configured via .env or env; + demo-check when DEMO_API_BASE set).
# Frontend tests stay in CI / `make test`, not this gate. See scripts/pipeline_check.py --help
pipeline:
	python3 scripts/pipeline_check.py

# Offline-only pipeline (scope + backend unit tests + fit-signals; never hits live APIs).
pipeline-offline:
	python3 scripts/pipeline_check.py --offline-only

test: check-scope
	cd backend && pytest -q
	cd frontend && pnpm test

# —— Deploy wrappers (operator CLIs; never commit tokens) ——
# See docs/DEPLOYMENT.md. Fail loudly if CLIs are missing or unauthenticated.

deploy-api:
	@set -e; \
	FLY=$$(command -v flyctl || command -v fly || true); \
	if [ -z "$$FLY" ]; then \
	  echo "deploy-api: flyctl not found. Install: https://fly.io/docs/hands-on/install-flyctl/"; \
	  echo "  Then: fly auth login && fly secrets set … (DEPLOYMENT.md §1)"; \
	  exit 1; \
	fi; \
	echo "deploy-api: using $$FLY"; \
	$$FLY auth whoami >/dev/null 2>&1 || { \
	  echo "deploy-api: not authenticated. Run: fly auth login"; \
	  exit 1; \
	}; \
	SHA=$$(git rev-parse HEAD 2>/dev/null || echo dev); \
	$$FLY deploy --config fly.toml --app teamscout-api --build-arg "GIT_SHA=$$SHA"

deploy-web:
	@set -e; \
	if ! command -v vercel >/dev/null 2>&1; then \
	  echo "deploy-web: vercel CLI not found. Install: npm i -g vercel@39"; \
	  echo "  Then: cd frontend && vercel link && vercel env add NEXT_PUBLIC_API_BASE production"; \
	  exit 1; \
	fi; \
	vercel whoami >/dev/null 2>&1 || { \
	  echo "deploy-web: not authenticated. Run: vercel login"; \
	  echo "  Then: vercel link (or set VERCEL_ORG_ID / VERCEL_PROJECT_ID) and vercel env add NEXT_PUBLIC_API_BASE production"; \
	  exit 1; \
	}; \
	echo "deploy-web: vercel --prod (repo root uses vercel.json → frontend/)"; \
	vercel --prod

# Print deploy readiness without mutating production. Never invents success.
deploy-status:
	@echo "=== Deploy readiness ==="; \
	FLY=$$(command -v flyctl || command -v fly || true); \
	if [ -n "$$FLY" ]; then \
	  echo "flyctl: $$FLY"; \
	  if $$FLY auth whoami >/dev/null 2>&1; then \
	    echo "flyctl auth: ok ($$($$FLY auth whoami 2>/dev/null))"; \
	    $$FLY status --app teamscout-api 2>&1 || echo "fly status: app teamscout-api not reachable or not created"; \
	  else \
	    echo "flyctl: present but not authenticated — run: fly auth login"; \
	  fi; \
	else \
	  echo "flyctl: MISSING — install: curl -L https://fly.io/install.sh | sh"; \
	  echo "  (or: brew install flyctl) then: fly auth login && make deploy-api"; \
	fi; \
	if command -v vercel >/dev/null 2>&1; then \
	  echo "vercel: $$(command -v vercel)"; \
	  if vercel whoami >/dev/null 2>&1; then \
	    echo "vercel auth: ok ($$(vercel whoami 2>/dev/null))"; \
	  else \
	    echo "vercel: present but not authenticated — run: vercel login"; \
	  fi; \
	else \
	  echo "vercel: MISSING — install: npm i -g vercel@39"; \
	  echo "  then: vercel login && vercel link && make deploy-web"; \
	fi; \
	echo "docs: DEPLOYMENT.md"; \
	echo "smoke after deploy: DEMO_API_BASE=https://<app>.fly.dev make demo-check"; \
	echo "status: no deploy performed (readiness only)"
