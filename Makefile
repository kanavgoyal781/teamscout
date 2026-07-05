.PHONY: dev backend frontend test install install-backend install-frontend

# Backend loads repo-root .env automatically (see backend/app/core/config.py).
dev:
	$(MAKE) -j2 backend frontend

backend:
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

frontend:
	cd frontend && pnpm dev

install: install-backend install-frontend

install-backend:
	cd backend && python3 -m pip install -r requirements.txt

install-frontend:
	cd frontend && pnpm install

test:
	cd backend && pytest -q
	cd frontend && pnpm test