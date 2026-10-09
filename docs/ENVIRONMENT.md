# Environment

## Local

- Python 3.11+ (CI uses 3.12)
- Docker (for PostgreSQL + API)
- Node.js 22.12+ (web app in `frontend/`, see `frontend/README.md`)

## Commands

```bash
git clone https://github.com/sricharansk/SITEGUARD-AI.git
cd SITEGUARD-AI
make install && make test      # backend + tests on SQLite
make run                        # http://localhost:8000/docs with demo data
make web-install && make web-dev # web app on http://localhost:3000 (needs make run)
cp .env.example .env && make up # PostgreSQL + API + web app in Docker
make demo                       # regenerate docs/RESULTS.md from a live run
```

## Settings

All settings are environment variables prefixed `SITEGUARD_` (see `.env.example` and
`backend/app/core/config.py`). Set `SITEGUARD_AI_PROVIDER=anthropic` and `ANTHROPIC_API_KEY` to use Claude.

## Secrets

Use `.env.example` as the template. Never commit real values. Demo users share `SITEGUARD_DEMO_PASSWORD`, so demo
seeding defaults to on only when `SITEGUARD_ENV` is `local`, `test` or `demo`; `production` refuses it.

## Dependencies

Runtime dependencies are locked in `backend/requirements.lock` (Linux, CPython 3.12+); `make install` installs from
it. Dev tools (pytest, httpx, ruff, mypy) are pinned in `backend/pyproject.toml` to the versions CI uses. Web app
dependencies are pinned to exact versions in `frontend/package.json` and locked in `frontend/package-lock.json`.

## Database migrations

`make migrate` applies migrations (the API also does this on startup). After changing `backend/app/models.py`,
`make revision m="describe the change"`, review the generated file under `backend/app/migrations/versions/`, and
commit it.
