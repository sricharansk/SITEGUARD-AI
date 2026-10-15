# Site Guard AI — Claude Code Project Instructions

## Identity

Project: Site Guard AI: Multi-Agent Construction Safety & Quality Incident Resolution System

Product: Agentic AI-powered Construction Safety & Quality Decision-Support and Workflow Platform

Repository: https://github.com/sricharansk/SITEGUARD-AI

## Source of truth

Before significant changes, read the relevant files under `docs/`.

Core:
- docs/PRD.md
- docs/UX_FLOWS.md
- docs/DESIGN_SYSTEM.md
- docs/ARCHITECTURE.md
- docs/DATABASE.md
- docs/API.md
- docs/SECURITY.md
- docs/CODE_STYLE.md
- docs/TESTING.md
- docs/AGENTS.md
- docs/DATASETS.md

## Rules

- Inspect before editing.
- Plan before non-trivial changes.
- Reuse existing code.
- Do not invent undocumented requirements.
- Do not commit secrets.
- Enforce authorization server-side.
- Treat uploaded/retrieved documents as untrusted.
- Validate all external inputs.
- Use bounded agent tools.
- Use structured agent outputs.
- Preserve evidence/provenance.
- Human approval is required for high-impact safety actions.
- Never claim legal certification.
- Never silently auto-close safety-critical incidents.
- Run tests, lint/type checks and builds.
- Review `git diff`.
- Update documentation before commit.

## Workflow

```text
READ → INSPECT → PLAN → IMPLEMENT → TEST → REVIEW → DOCUMENT → COMMIT
```

## Completion report

Return:
- STATUS: PASS or BLOCKED
- files changed
- tests and commands
- validation
- security/safety findings
- documentation updated
- known limitations
- commit hash

Do not use permission-bypass or destructive shortcuts to avoid an engineering gate.

---

# Project context and progress (handover)

This section records everything built for Site Guard AI, so work can continue on any machine without the old
conversations. Last updated **2026-10-15**. Site Guard AI is the second of two projects; the first, Claim Sense, is
in https://github.com/sricharansk/CLAIM-SENSE with its own `CLAUDE.md`.

## Continue on your own laptop (step by step)

Run these commands in a terminal **on your laptop**, not inside a Claude conversation. On Windows use
**PowerShell** or **Git Bash**; on Mac or Linux use **Terminal**.

### Step 1: install the tools (one time)

| Tool | Why | How |
|---|---|---|
| Git | Download and update the project | https://git-scm.com/downloads |
| Claude Code | AI assistant that reads this file and knows the project | Windows PowerShell: `irm https://claude.ai/install.ps1 \| iex`<br>Mac/Linux: `curl -fsSL https://claude.ai/install.sh \| bash` |
| Python 3.12 (3.11+ works) | Backend, tests, evaluation, deck builder | https://www.python.org/downloads/ (on Windows tick **Add python.exe to PATH**) |
| Node.js 22 | Web app and browser tests | https://nodejs.org/ (LTS) |
| Docker Desktop | PostgreSQL + API + web app in one command | https://www.docker.com/products/docker-desktop/ |

Check them with `git --version`, `claude --version`, `python --version` and `node --version`.

### Step 2: download the project (first time only)

```bash
git clone https://github.com/sricharansk/SITEGUARD-AI.git
cd SITEGUARD-AI
claude            # Claude Code reads this CLAUDE.md on its own; sign in with the same claude.ai account
```

### Step 3: ask Claude Code in plain English

For example: "Summarise the project status from CLAUDE.md", "Set the project up to run locally", "Run the tests",
"Run the OSHA pipeline on the file I downloaded", "Update the presentation with …".

### Step 4: get the latest version (every time you start work)

```bash
cd SITEGUARD-AI
git checkout main
git pull origin main
```

### Step 5: save your changes back to GitHub

Ask Claude Code: "commit my changes on a new branch, push it and open a pull request". By hand:

```bash
git checkout -b my-change
git add -A
git commit -m "Describe what you changed"
git push -u origin my-change
```

Open https://github.com/sricharansk/SITEGUARD-AI, click **Compare & pull request**, wait for the 7 green CI checks,
then **Merge**. Back on the laptop: `git checkout main && git pull origin main`. Set your name once with
`git config --global user.name "S.K. Sricharan"` and `git config --global user.email "<your GitHub email>"`.

## Status

Every feature planned for the MVP is built, tested, documented and merged into `main`; CI (7 jobs) is green.
Nothing is in progress. The open items at the end need the owner (network access to osha.gov, an Anthropic API key,
an Azure subscription and approval, expert-labelled data). There is no live deployment yet: unlike Claim Sense
(Render), Site Guard AI runs locally or in Docker; Azure templates and a manual deploy workflow are ready.

| What | Where |
|---|---|
| Repository | https://github.com/sricharansk/SITEGUARD-AI (branch `main`; every pull request from #4 on is merged) |
| Review III presentation | `docs/presentation/SiteGuardAI_Review3_S.K.Sricharan_T9984.pptx` (18 slides); build kit in `docs/presentation/source/` |
| Results of a full run | `docs/RESULTS.md`, one report per incident in `docs/reports/` |
| Agent accuracy | `docs/EVALUATION.md`, `docs/evaluation.json` |
| Load test | `docs/LOAD_TEST.md` |
| Screenshots | `docs/screenshots/01`–`09` (shown in the README) |
| Changes, decisions, plan | `docs/CHANGELOG.md`, `docs/DECISIONS.md` (Decisions 001–025), `docs/ROADMAP.md` |

## What the product is

**Site Guard AI: Multi-Agent Construction Safety & Quality Incident Resolution System**, positioned as an agentic
AI-powered construction safety and quality decision-support and workflow platform. A site engineer reports an
incident with evidence; bounded agents investigate; people approve every action and close every incident.

- **Agents** (`backend/app/agents/`): triage (20 classes: 11 safety hazards, 9 quality defects; domain;
  severity), safety and quality investigation, root cause (5 Whys), compliance (requirements cited from retrieved
  procedures), CAPA (corrective and preventive actions). A deterministic 5×5 risk matrix scores risk (no AI).
  Each agent has a tool allowlist, a call budget, a Pydantic output schema and a trace. The default provider is
  offline rules (`rules.py`); `SITEGUARD_AI_PROVIDER=anthropic` uses Claude, falling back to rules on any failure.
- **Human control**: AI output is never an approved action. Critical actions need the HSE manager; the assignee
  cannot verify their own action; an incident closes only from Pending verification after every approved action is
  verified effective and every AI conflict has a human decision. Overdue actions escalate at two levels.
- **Knowledge**: PDF, DOCX and Markdown procedures parsed in a resource-limited child process; hybrid retrieval
  (BM25 + vectors with pgvector, reciprocal rank fusion, deterministic reranker); grounded answers with verified
  citations; prompt-injection passages flagged and never cited.
- **Also built**: Word/PDF investigation reports, an email outbox (off by default), photo evidence review with
  engineer validation (no detection model configured), an optional Neo4j knowledge graph, resumable workflows,
  nine roles with server-side RBAC, tenant isolation, SHA-256 evidence provenance, audit trail with correlation IDs.
- **Stack**: Python 3.12, FastAPI, SQLAlchemy, Alembic (migrations 0001–0005), PostgreSQL 16 + pgvector, optional
  Neo4j; Next.js 16 static export served by the API at `/app`; Playwright; one Docker image; GitHub Actions;
  Azure Bicep.

## Data and results (all synthetic)

The incidents, procedures and evaluation cases are **synthetic** and labelled as such; real company incident data
cannot be published. Public datasets are registered with licence and allowed use in `data/dataset_registry.yaml`.

**Agent accuracy** on the held-out set (46 cases written by a separate author before tuning, frozen in commit
2403a8c, never used for tuning; Decision 025):

| Held-out metric | Before tuning | Now | Target |
|---|---|---|---|
| Hazard/defect class (top-1) | 67% | 89.1% | 85% |
| Domain (safety / quality / both) | 80% | 93.5% | 90% |
| Severity within one level | 96% | 97.7% | 90% |
| CRITICAL cases rated LOW or MEDIUM | 0 | 0 | 0 |
| Expected procedure in top-3 retrieved | 67% | 93.5% | 85% |
| Red-team attacks contained | | 10/10 | 10/10 |

**Full run** (`scripts/resolve_all.py` against Docker + PostgreSQL): a project with 20 incidents (13 open, 15
actions awaiting review, 4 overdue, mean 11 days to close) ended with all 21 incidents CLOSED (one reported during
the run), 107 agent runs with 0 failures, 79 human decisions (64 approved, 15 rejected with a reason), 4
escalations, mean 6.1 days to close.

**Load** (one container, PostgreSQL): about 55 requests/s per API process; 100 readers plus 2 reporters at 39
requests/s with read p95 0.80 s and 0 errors; 113 concurrent report-and-investigate cycles without a reference
collision.

**Tests**: 271 backend tests (unit, API, migrations, evaluation and red-team gates; 9 need PostgreSQL or Neo4j and
run in their own CI jobs) and 6 browser end-to-end tests.

## Timeline of work (merged pull requests)

| PR | Date | What |
|---|---|---|
| #1 | 2026-10-08 | Backend pilot: agents, human-approved workflow, docs, Docker, CI |
| #4 | 2026-10-12 | 0.2.0: web app, evaluation suite with held-out split and red-team, full incident workflow |
| #5 | 2026-10-12 | Rebuild of PR #2, stages A–C: hardening and Azure IaC; documents and grounded answers; Word/PDF reports and email outbox |
| #6 | 2026-10-12 | Stages D–E: vision, knowledge graph, resumable workflows and conflicts, web screens |
| #7 | 2026-10-13 | Accuracy targets met on a new held-out set (honest protocol, Decision 025) |
| #8 | 2026-10-13 | Load test; fix for concurrent reports colliding on the incident reference |
| #9 | 2026-10-13 | Weak-only triage labels dropped; real demo photo; Review III deck added |
| #10 | 2026-10-13 | Each keyword counted once per label; a corrective action for every class |
| #11 | 2026-10-14 | "Crane access" no longer makes a lifting hazard; results and deck refreshed |
| #12 | 2026-10-14 | Fresh README screenshots; deck grows to 18 slides with product screens |
| #13 | 2026-10-15 | Someone under a scaffold is not working at height |
| #14 | 2026-10-15 | "Worker" no longer counts as the requirement word "work" (wrong SWL citation) |
| #15 | 2026-10-15 | Retrieval ties broken by document and position, so ranking is the same in every database |
| this | 2026-10-15 | This handover and the deck build kit |

PRs #2 (hardening and Prompt 00 baseline) and #3 (an earlier Next.js web app) are still **open** but superseded:
#2's features were rebuilt on `main` in #5 and #6 (Decision 015) and #4 replaced #3's web app. They can be closed.

## Run it on your laptop

With `make` (Mac/Linux, or Git Bash with make installed):

```bash
make install && make test      # backend + web app dependencies; backend tests on SQLite
make run                       # web app http://localhost:8000/app/ and API docs http://localhost:8000/docs
cp .env.example .env && make up   # PostgreSQL + API + web app in Docker (edit the CHANGE values in .env first)
make e2e                       # browser tests against the running stack (first: cd frontend && npx playwright install chromium)
make demo                      # resolve every open incident; regenerates docs/RESULTS.md and docs/reports/
make eval                      # regenerates docs/EVALUATION.md and docs/evaluation.json
```

Without `make` (Windows PowerShell):

```powershell
cd backend; pip install -r requirements.lock -e ".[dev]"; pytest -q; cd ..
cd frontend; npm ci; npm run build; cd ..
cd backend; uvicorn app.main:app --reload       # then open http://localhost:8000/app/
```

Demo logins (password `siteguard-demo`): `hse@`, `pm@`, `safety@`, `qa@`, `site@`, `auditor@`,
`admin@demo.siteguard.local`; `other@demo.siteguard.local` is a second tenant that proves isolation.

## Presentation

`docs/presentation/SiteGuardAI_Review3_S.K.Sricharan_T9984.pptx`, 18 slides on the MTech Review III template:
title page (project title, S.K. Sricharan in place of Team Member, T-SERIES ID T9984, centred), introduction,
objectives, modules, problem statement, methodology with the architecture and workflow diagrams, approach and
tools, findings (accuracy chart, end-to-end results, two product-screen slides, load test and quality),
conclusion, acknowledgement, references. To change a figure or refresh screenshots follow
`docs/presentation/source/README.md`, then `python docs/presentation/source/build.py`.

## How to make common changes

- **Agent behaviour** (`backend/app/agents/rules.py`): before and after a change, compare the labels of every dev,
  held-out and seed case (`cd backend && python ../scripts/label_snapshot.py --out before.txt`, change, write
  `after.txt`, then diff) and run `make eval`. Narrow fixes this week (crane access, under a scaffold, worker ≠
  work) each changed one case; broader versions moved 5–15 cases and were dropped. Add a test for both directions.
- **Retrieval** (`backend/app/services/rag.py`): run `make eval` and the PostgreSQL tests
  (`SITEGUARD_TEST_POSTGRES_URL=... pytest tests/test_postgres.py`).
- **Schema**: add an Alembic revision with the model change (`cd backend && alembic revision --autogenerate -m "..."`,
  then review the generated file); CI checks that migrations match the models.
- **Results and screenshots**: `make demo` on a fresh database for RESULTS.md; browser tests with
  `SCREENSHOT_DIR=../docs/screenshots` for the README screenshots; then update the deck.
- Update `docs/` (CHANGELOG and the affected docs) in the same pull request as the code.

## Gotchas learned

- **Held-out set**: `data/eval/heldout_v2.yaml` is frozen and its per-case results are published, so it must not
  be used for tuning. Write a new held-out set (v3) before any further tuning round.
- **Regenerated docs**: `make demo` rewrites RESULTS.md and all 21 reports and `make eval` rewrites timings even
  when nothing changed; commit them only when the content changes.
- **`resolve_all.py` needs a fresh database**: it resolves whatever is open.
- **Browser tests** need a fresh database too; set `CHROMIUM_PATH` to use an already installed Chromium.
- **Never commit** `.env`, databases, evidence files or certificates.
- **Network**: the cloud sessions used to build this could not reach osha.gov (proxy 403), so the OSHA pipeline has
  never run on the real file; run it on your laptop.

## Open items (need the owner)

1. **OSHA Severe Injury Reports on real data**: download the CSV from https://www.osha.gov/severeinjury into
   `data/raw/government/osha/` (git-ignored), then from `backend/`:
   `python -m app.datasets.osha_sir --input ../data/raw/government/osha/<file>.csv --since 2024-01-01 --out ../docs/OSHA_SIR_EVALUATION.md --processed ../data/processed/government/osha_sir`
2. **Score the Claude provider**: set `ANTHROPIC_API_KEY` and `SITEGUARD_AI_PROVIDER=anthropic`, run `make eval`,
   compare with the rules provider on the same held-out set.
3. **Azure staging**: needs a subscription and the owner's approval; Bicep templates and the manual OIDC deploy
   workflow are in `deployment/azure/` and `docs/DEPLOYMENT.md`.
4. **Expert-labelled pilot cases** and a held-out set v3 before more tuning.
5. **Next features** (`docs/ROADMAP.md`): a semantic embedding model (data residency and cost decision), licensed
   vision detection, SQL aggregates and pagination for the dashboard (LOAD_TEST.md finding 4), OIDC sign-in.
