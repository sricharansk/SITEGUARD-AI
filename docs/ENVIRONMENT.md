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

`SITEGUARD_ENV` is one of `local`, `test`, `demo`, `staging` or `production`; anything else is refused. The API
refuses to start with settings that are unsafe for that environment and lists every problem at once (table in
`docs/GOVERNANCE.md#configuration-validation`). In `staging` and `production` that means a random JWT secret
(32+ characters, no `CHANGE` placeholder), PostgreSQL, demo seeding off, and `https://` for
`SITEGUARD_PUBLIC_WEB_URL` and any CORS origin. The API image defaults to `production`, so `.env` must set
`SITEGUARD_ENV=local` or `demo` for the local Docker stack.

| Environment | Where | Settings |
|---|---|---|
| local, test | `make run`, tests | `.env.example` / defaults; SQLite allowed; demo data seeds |
| demo | `docker compose` with `SITEGUARD_ENV=demo` | Real JWT secret; demo data seeds (known passwords) |
| staging | `deployment/staging/` on one host, or Azure | `deployment/staging/staging.env.example` (placeholders only), or Key Vault in Azure |
| production | Azure (`deployment/azure/`) | Key Vault through managed identity; never a file |

## Secrets

Use `.env.example` (local, demo) or `deployment/staging/staging.env.example` (staging) as the template. Never
commit real values: `.env`, `.env.*` and `*.env` are git-ignored; keep the staging settings file outside the checkout
(`/etc/siteguard/staging.env`, chmod 600). In Azure the apps read secrets from Key Vault (docs/DEPLOYMENT.md#azure). Demo users share `SITEGUARD_DEMO_PASSWORD`, so demo
seeding defaults to on only when `SITEGUARD_ENV` is `local`, `test` or `demo`; `staging` and `production` refuse it.

## Dependencies

Runtime dependencies are locked in `backend/requirements.lock` (Linux, CPython 3.12+); `make install` installs from
it. Dev tools (pytest, httpx, ruff, mypy) are pinned in `backend/pyproject.toml` to the versions CI uses. Web app
dependencies are pinned to exact versions in `frontend/package.json` and locked in `frontend/package-lock.json`.
Container base images are pinned by tag and digest in the Dockerfiles. CI audits both locks for known
vulnerabilities (`scripts/dependency_audit.py`, docs/SECURITY.md#dependency-scanning).

## Operations tools

- `scripts/smoke_test.py` (needs `httpx`): smoke test a running stack (docs/DEPLOYMENT.md#smoke-test).
- `scripts/backup.py` (standard library only, plus PostgreSQL 16 client tools `pg_dump`, `pg_restore`, `psql`):
  backup, restore and verify (docs/GOVERNANCE.md#backup-and-restore).
- `scripts/dependency_audit.py` (needs `pip-audit` and `npm`): the CI dependency audit.
- Azure: Azure CLI with Bicep for `deployment/azure/` (offline validation needs only `az bicep`).

## Database migrations

`make migrate` applies migrations (the API also does this on startup). After changing `backend/app/models.py`,
`make revision m="describe the change"`, review the generated file under `backend/app/migrations/versions/`, and
commit it.
