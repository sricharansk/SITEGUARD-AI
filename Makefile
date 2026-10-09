.PHONY: install test lint run up down demo migrate revision web-install web-dev web-test web-e2e

install:
	cd backend && pip install -r requirements.lock -e ".[dev]"

lint:
	cd backend && ruff check app tests && ruff format --check app tests && mypy app --ignore-missing-imports

test:
	cd backend && pytest -q

run:  ## API on SQLite with demo data at http://localhost:8000/docs
	cd backend && uvicorn app.main:app --reload

up:  ## PostgreSQL + API + web app in Docker (web app: http://localhost:3000)
	docker compose up -d --build

down:
	docker compose down

demo:  ## Drive one incident end to end and regenerate docs/RESULTS.md
	python scripts/demo_walkthrough.py --base-url http://localhost:8000 --out docs/RESULTS.md

migrate:  ## Apply database migrations (the API also does this on startup)
	cd backend && alembic upgrade head

jobs:  ## Run the scheduled jobs once: escalation rules, then due notification deliveries
	cd backend && python -m app.jobs all

revision:  ## Create a migration from model changes: make revision m="add reports table"
	cd backend && alembic revision --autogenerate -m "$(m)"

web-install:  ## Install the web app's pinned dependencies
	cd frontend && npm ci

web-dev:  ## Web app at http://localhost:3000, calling the API from `make run`
	cd frontend && npm run dev

web-test:  ## Web app lint, type check, unit/component tests and production build
	cd frontend && npm run lint && npm run typecheck && npm test && npm run build

web-e2e:  ## Browser E2E against a running API and web app (see frontend/README.md)
	cd frontend && npm run e2e
