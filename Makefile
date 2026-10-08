.PHONY: install test lint run up down demo

install:
	cd backend && pip install -e ".[dev]"

lint:
	cd backend && ruff check app tests && ruff format --check app tests && mypy app --ignore-missing-imports

test:
	cd backend && pytest -q

run:  ## API on SQLite with demo data at http://localhost:8000/docs
	cd backend && uvicorn app.main:app --reload

up:  ## PostgreSQL + API in Docker
	docker compose up -d --build

down:
	docker compose down

demo:  ## Drive one incident end to end and regenerate docs/RESULTS.md
	python scripts/demo_walkthrough.py --base-url http://localhost:8000 --out docs/RESULTS.md
