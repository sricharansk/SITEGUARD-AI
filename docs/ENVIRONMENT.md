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

## Settings added in the hardening stage

| Setting | Default | Meaning |
|---|---|---|
| `SITEGUARD_ENV` | `local` | local, test, demo, staging or production; staging and production turn on every startup check |
| `SITEGUARD_SEED_DEMO_DATA` | on for local/test/demo, off otherwise | Demo users share a known password; refused in staging and production |
| `SITEGUARD_PUBLIC_WEB_URL` | `http://localhost:8000/app` | Public web app URL; https required in staging and production |
| `SITEGUARD_LOGIN_MAX_FAILURES` | 5 | Failed sign-ins per (email, client) in 15 minutes before HTTP 429 |
| `SITEGUARD_LOGIN_MAX_FAILURES_PER_ACCOUNT` | 20 | Failed sign-ins per email in 15 minutes from any client |
| `SITEGUARD_DOCUMENT_MAX_BYTES` | 26214400 (25 MB) | Largest knowledge document upload (HTTP 413 above) |
| `SITEGUARD_CHUNK_STRATEGY` | `heading` | `heading`, `page` or `semantic` chunking |
| `SITEGUARD_CHUNK_MAX_CHARS` | 900 | Maximum chunk length (200–8000) |
| `SITEGUARD_EMBEDDING_PROVIDER` | `hashing` | Offline deterministic embedder; the only provider today (DECISIONS 017) |
| `SITEGUARD_RETRIEVAL_MODE` | `hybrid` | `hybrid` (BM25 + vector) or `lexical` (BM25 only) |
| `SITEGUARD_PARSER_TIMEOUT_SECONDS` | 60 | Wall-clock and CPU limit for parsing one PDF or DOCX (5–600) |
| `SITEGUARD_PARSER_MEMORY_MB` | 1024 | Address-space limit of the parser child process (256–8192) |
| `SITEGUARD_NOTIFICATION_EMAIL_ADAPTER` | `disabled` | `disabled`, `log` (no address or content logged) or `smtp` (refused in local and test) |
| `SITEGUARD_NOTIFICATION_MAX_ATTEMPTS` | 3 | Send attempts before a delivery becomes `FAILED` (1–10) |
| `SITEGUARD_SMTP_HOST`, `_PORT`, `_USERNAME`, `_PASSWORD`, `_FROM`, `_STARTTLS` | `localhost`, 587, empty, empty, `siteguard@localhost`, true | SMTP server for `smtp`; STARTTLS is required in staging and production |

## Dependencies

Runtime packages are pinned in `backend/requirements.lock`; Docker and CI install from it. To change a dependency,
edit `pyproject.toml`, then regenerate the lock in a clean Python 3.12 virtual environment:

```bash
python3.12 -m venv /tmp/lock && /tmp/lock/bin/pip install ./backend
/tmp/lock/bin/pip freeze --exclude-editable | grep -vi '^siteguard-ai-backend'   # paste under the header
python scripts/dependency_audit.py pypi --requirements backend/requirements.lock  # needs pip-audit
```

Dev tools (pytest, httpx, ruff, mypy) are pinned in `pyproject.toml` so local runs match CI.
