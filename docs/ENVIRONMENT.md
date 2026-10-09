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

## Knowledge graph (optional)

Off by default (`SITEGUARD_GRAPH_BACKEND=disabled`). To use Neo4j locally:

```bash
docker compose --profile graph up -d neo4j     # Neo4j 5.26 on 127.0.0.1:7687 (browser on :7474)
# in .env: SITEGUARD_GRAPH_BACKEND=neo4j, SITEGUARD_NEO4J_PASSWORD = the compose NEO4J_PASSWORD,
# SITEGUARD_NEO4J_URI=bolt://neo4j:7687 for the api container or bolt://localhost:7687 from the host
make graph-sync                                 # python -m app.jobs graph-sync: every organization
```

`SITEGUARD_GRAPH_BACKEND=memory` keeps the graph inside the API process (sync with `POST /graph/sync`); it is lost on
restart and a separate job process cannot see it. To run the integration test against a local Neo4j, set
`SITEGUARD_TEST_NEO4J_URI`, `SITEGUARD_TEST_NEO4J_USER` and `SITEGUARD_TEST_NEO4J_PASSWORD` and run
`pytest tests/test_graph.py -rs`.

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
