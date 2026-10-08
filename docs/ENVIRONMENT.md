# Environment

## Local

- Python 3.11+ (CI uses 3.12)
- Docker (for PostgreSQL + API)
- Node.js 18+ (frontend, next milestone)

## Commands

```bash
git clone https://github.com/sricharansk/SITEGUARD-AI.git
cd SITEGUARD-AI
make install && make test      # backend + tests on SQLite
make run                        # http://localhost:8000/docs with demo data
cp .env.example .env && make up # PostgreSQL + API in Docker
make demo                       # regenerate docs/RESULTS.md from a live run
```

## Settings

All settings are environment variables prefixed `SITEGUARD_` (see `.env.example` and
`backend/app/core/config.py`). Set `SITEGUARD_AI_PROVIDER=anthropic` and `ANTHROPIC_API_KEY` to use Claude.

## Secrets

Use `.env.example` as the template. Never commit real values. Demo users share `SITEGUARD_DEMO_PASSWORD`; turn
seeding off (`SITEGUARD_SEED_DEMO_DATA=false`) anywhere real data is stored.
