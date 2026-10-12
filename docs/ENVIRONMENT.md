# Environment

## Local

- Python 3.11+ (CI uses 3.12)
- Docker (for PostgreSQL + API)
- Node.js 22 (web app; `frontend/`)

## Commands

```bash
git clone https://github.com/sricharansk/SITEGUARD-AI.git
cd SITEGUARD-AI
make install && make test      # backend + frontend deps, backend tests on SQLite
make run                        # builds the web app; http://localhost:8000/app/ and /docs with demo data
cp .env.example .env && make up # PostgreSQL + API + web app in Docker
make demo                       # resolve every open incident, regenerate docs/RESULTS.md and docs/reports/
make eval                       # regenerate docs/EVALUATION.md
make e2e                        # browser tests against the running stack
```

## Settings

All settings are environment variables prefixed `SITEGUARD_` (see `.env.example` and
`backend/app/core/config.py`). Set `SITEGUARD_AI_PROVIDER=anthropic` and `ANTHROPIC_API_KEY` to use Claude.
`SITEGUARD_WEB_DIR` points at the built web app (default `frontend/out`); `SITEGUARD_AUTO_CREATE_SCHEMA=false`
when migrations manage the schema. For `npm run dev` on port 3000 set `NEXT_PUBLIC_API_BASE=http://localhost:8000`.

## Secrets

Use `.env.example` as the template. Never commit real values. Demo users share `SITEGUARD_DEMO_PASSWORD`; turn
seeding off (`SITEGUARD_SEED_DEMO_DATA=false`) anywhere real data is stored.
