.PHONY: install test lint eval run web up down demo e2e

install:
	cd backend && pip install -e ".[dev]"
	cd frontend && npm ci --no-audit --no-fund

lint:
	cd backend && ruff check app tests migrations && ruff format --check app tests migrations && mypy app --ignore-missing-imports
	cd frontend && npm run typecheck

test:
	cd backend && pytest -q

eval:  ## Gold-set evaluation + red-team suite -> docs/EVALUATION.md
	cd backend && python -m app.evaluation --out ../docs/EVALUATION.md --json ../docs/evaluation.json

web:  ## Build the web app; the API serves it at /app
	cd frontend && npm run build

run: web  ## API + web app on SQLite with demo data at http://localhost:8000/app/
	cd backend && uvicorn app.main:app --reload

up:  ## PostgreSQL + API (+ web app) in Docker
	docker compose up -d --build

down:
	docker compose down

demo:  ## Resolve every open incident on a fresh stack and regenerate docs/RESULTS.md and docs/reports/
	python scripts/resolve_all.py --base-url http://localhost:8000 --out docs/RESULTS.md --reports-dir docs/reports

e2e:  ## Browser tests against a running stack
	cd frontend && E2E_BASE_URL=http://localhost:8000 npx playwright test
