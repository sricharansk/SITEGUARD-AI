# Run Site Guard AI on your own computer

This guide takes a fresh laptop to a running Site Guard AI, then shows how to run the tests and refresh the results
(`docs/RESULTS.md`, `docs/EVALUATION.md`). Ways A and C, the tests and the results commands were run on 30 October 2026 for this guide, and the
numbers in "What you should see" are from that run. Way B (Docker) could not be run there (no Docker daemon); it
is the same compose file the earlier results were produced with.

Pick one way to run it:

| Way | Needs | Database | Good for |
|---|---|---|---|
| **A. Quick start** | Python and Node | SQLite file, created for you | Trying the app, running the tests |
| **B. Docker** | Docker Desktop | PostgreSQL in a container | The setup closest to a real deployment, refreshing the results |
| **C. Your own PostgreSQL** | Python, Node, PostgreSQL 16 with pgvector | PostgreSQL you installed | Linux machines without Docker |

## 1. Install the tools (once)

| Tool | Version | Download | Check |
|---|---|---|---|
| Git | any recent | https://git-scm.com/downloads | `git --version` |
| Python | 3.12 (3.11 or newer works) | https://www.python.org/downloads/ (Windows: tick **Add python.exe to PATH**) | `python --version` |
| Node.js | 22 LTS | https://nodejs.org/ | `node --version` |
| Docker Desktop | way B only | https://www.docker.com/products/docker-desktop/ | `docker --version` |

On Mac and Linux the Python command may be `python3`; use that wherever this guide says `python`.

## 2. Download the project

```bash
git clone https://github.com/sricharansk/SITEGUARD-AI.git
cd SITEGUARD-AI
```

Already have it? Get the latest version instead: `git checkout main && git pull origin main`.

## 3. Create a Python environment and install (ways A and C)

A virtual environment keeps the project's packages away from the rest of your computer.

Mac / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
cd backend && pip install -r requirements.lock -e ".[dev]" && cd ..
cd frontend && npm ci && npm run build && cd ..
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1      # if refused: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
cd backend; pip install -r requirements.lock -e ".[dev]"; cd ..
cd frontend; npm ci; npm run build; cd ..
```

Run `source .venv/bin/activate` (or `.venv\Scripts\Activate.ps1`) again in every new terminal.
With `make` installed (Mac, Linux, Git Bash), `make install` and `make web` do the same as the last two lines.

## 4A. Quick start on SQLite

```bash
cd backend
uvicorn app.main:app --reload
```

Open http://localhost:8000/app/ and sign in with any demo login below. API documentation is at
http://localhost:8000/docs. The demo data (a project with 20 synthetic incidents and site procedures) is seeded on
the first start into `backend/siteguard.db`. Delete that file to start again from fresh data. Stop the server with
Ctrl+C.

## 4B. Docker (PostgreSQL + API + web app)

```bash
cp .env.example .env          # Windows PowerShell: Copy-Item .env.example .env
```

Open `.env` and replace both values that say `CHANGE` (`SITEGUARD_JWT_SECRET` with a long random string, and
`POSTGRES_PASSWORD`). Then:

```bash
docker compose up -d --build  # or: make up
curl http://localhost:8000/ready
```

`/ready` answers `"status":"ready"` once the database is up and migrated (about 30 seconds on the first start).
Open http://localhost:8000/app/. Stop with `docker compose down`. To start again from fresh data (needed before
`make demo` or the browser tests): `docker compose down -v`, then `docker compose up -d`.

## 4C. Your own PostgreSQL (no Docker)

Install PostgreSQL 16 and the pgvector extension (Ubuntu: `sudo apt install postgresql-16 postgresql-16-pgvector`;
Mac: `brew install postgresql@16 pgvector`). Create a user and database:

```bash
sudo -u postgres psql -c "create user siteguard password 'siteguard-local' superuser" -c "create database siteguard owner siteguard"
```

The `superuser` flag lets the first migration create the `vector` extension; on a shared server, have an admin run
`create extension vector` in the database instead and leave the flag out. Then, from `backend/` with the
environment active:

```bash
export SITEGUARD_DATABASE_URL=postgresql+psycopg://siteguard:siteguard-local@localhost:5432/siteguard
export SITEGUARD_AUTO_CREATE_SCHEMA=false
export SITEGUARD_JWT_SECRET=change-me-to-a-long-random-string-of-32-chars-or-more
alembic upgrade head
uvicorn app.main:app
```

(Windows PowerShell: `$env:SITEGUARD_DATABASE_URL="..."` instead of `export`.)

## Demo logins

Password `siteguard-demo` for all of them:

| Login | Role |
|---|---|
| `hse@demo.siteguard.local` | HSE manager (approves critical actions) |
| `pm@demo.siteguard.local` | Project manager |
| `safety@demo.siteguard.local` | Safety engineer |
| `qa@demo.siteguard.local` | QA/QC engineer |
| `site@demo.siteguard.local` | Site engineer (reports incidents, does actions) |
| `auditor@demo.siteguard.local` | Auditor (read only, audit trail) |
| `admin@demo.siteguard.local` | Administrator |
| `other@demo.siteguard.local` | A user in a second company, to show they cannot see this company's data |

## 5. Run the tests

From `backend/` with the environment active:

```bash
pytest -q
```

What you should see: `265 passed, 10 skipped`. The 10 skipped tests need PostgreSQL or Neo4j. To run the
PostgreSQL ones too, create an **empty** database for them (the tests wipe it) and point at it:

```bash
createdb -O siteguard siteguard_test        # or: sudo -u postgres createdb -O siteguard siteguard_test
SITEGUARD_TEST_POSTGRES_URL=postgresql+psycopg://siteguard:siteguard-local@localhost:5432/siteguard_test pytest -q
```

What you should see: `274 passed, 1 skipped` (the remaining one needs Neo4j).

Lint and type checks (from the repository root): `make lint`, or by hand
`cd backend && ruff check app tests migrations ../scripts && mypy app --ignore-missing-imports`, then
`cd ../frontend && npm run typecheck`.

Browser tests need the app running on a **fresh** database (way B or C) and a Chromium browser:

```bash
cd frontend
npx playwright install chromium            # once
E2E_BASE_URL=http://localhost:8000 npx playwright test
```

What you should see: `6 passed`.

## 6. Refresh the results dashboard

`docs/RESULTS.md` (and one report per incident in `docs/reports/`) comes from resolving every open incident
through the real API. It needs the app running on a **fresh** PostgreSQL database (way B or C). From the
repository root:

```bash
python scripts/resolve_all.py --base-url http://localhost:8000 --out docs/RESULTS.md --reports-dir docs/reports
```

What you should see (run of 30 October 2026): 21 of 21 incidents closed, 107 agent runs with 0 failures, 79 human
decisions (64 approved, 15 rejected with a reason), mean days to close 11.0 before and 6.1 after.

The agent accuracy report, `docs/EVALUATION.md` and `docs/evaluation.json`, needs no server. From `backend/`:

```bash
python -m app.evaluation --out ../docs/EVALUATION.md --json ../docs/evaluation.json
```

What you should see: every gate `PASS`; held-out class 89.1%, domain 93.5%, severity within one level 97.7%,
retrieval hit at 3 93.5%, 10 of 10 red-team attacks contained.

Both reports rewrite their dates and timings on every run, so `git diff` shows changes even when the results are
the same. Commit them when you want the published results to carry the new date.

The live dashboard in the app (http://localhost:8000/app/, **Dashboard**) shows the same portfolio numbers as
section 5 of RESULTS.md after the run.

## Troubleshooting

| Problem | Fix |
|---|---|
| `python` is not found (Windows) | Reinstall Python and tick **Add python.exe to PATH**, or use `py` instead of `python`. |
| `Activate.ps1 cannot be loaded` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then try again. |
| Port 8000 is in use | `uvicorn app.main:app --port 8001`, and use that port in the URLs. |
| The web app at `/app/` is a 404 | Build it first: `cd frontend && npm run build`, then restart the API. |
| `/ready` says `NOT_READY` | The database is not reachable or not migrated: check `SITEGUARD_DATABASE_URL`, then `alembic upgrade head`. |
| `type "vector" does not exist` | Install pgvector (step 4C), or use the Docker setup, whose image includes it. |
| The app refuses to start in `staging` or `production` | That is intended until every unsafe setting is fixed; the message lists them. Use `SITEGUARD_ENV=local` on a laptop. |
| `resolve_all.py` or the browser tests fail on a reused database | They need fresh demo data: `docker compose down -v && docker compose up -d`, or drop and recreate the database. |
| Need the Claude provider | Put `ANTHROPIC_API_KEY` in `.env` and set `SITEGUARD_AI_PROVIDER=anthropic`; without a key the rules provider runs offline. |

Everything here runs offline after installation, with synthetic demo data. Never commit `.env`, database files or
evidence files.
