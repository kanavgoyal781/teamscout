.PHONY: dev backend frontend test install install-backend install-frontend check-scope demo-check

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

test: check-scope
	cd backend && pytest -q
	cd frontend && pnpm test
