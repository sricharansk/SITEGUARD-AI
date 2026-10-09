# Project Status

Last updated: 09 October 2026 (Prompts 09–13). Tracks the 52 implementation gates (Prompts 00–51) in
`docs/planning/Site_Guard_AI_Claude_Code_Detailed_Execution_Playbook_FINAL_UPDATED.md`. Update this file in the
same commit as any milestone.

## Baseline (Prompt 00)

| Item | State |
|---|---|
| Remote | `origin` = https://github.com/sricharansk/SITEGUARD-AI |
| Default branch | `main` at `065c2a9` (PR #1, backend pilot, merged) |
| Working branch | `claude/siteguard-buildout-7r52wj`, open as PR #2 (hardening + this baseline) |
| Tracked files | 113. No `.env`, database, key or certificate files are tracked; a pattern scan of tracked files and full history found no credentials. |
| Ignored locally | `.env`, caches, `build/`, `*.egg-info/` (see `.gitignore`) |

### Repository structure

```text
CLAUDE.md, README.md, Makefile, docker-compose.yml, .env.example, .gitignore
.claude/            Claude Code rules, reviewer agents, permission settings
.github/workflows/  ci.yml: backend lint/types/tests, Docker build, end-to-end smoke run
backend/            FastAPI app (40 modules), Alembic migrations, 7 test files, Dockerfile, requirements.lock
data/               seed/ (synthetic incidents, users, procedures), dataset_registry.yaml
docs/               source-of-truth documents; docs/planning/ holds the Blueprint, Playbook and strategy files
scripts/            demo_walkthrough.py (drives one incident end to end, writes docs/RESULTS.md)
PROJECT 2.MD        the original project brief (older copy of docs/planning/PROJECT 2 FINAL CONTENTS.MD)
```

Not created yet (Blueprint Part 15): `frontend/`, root `tests/`, `evals/`, `deployment/`. They are added by the
prompts that need them rather than as empty folders.

### Stack and manifests

| Area | What is in the repository |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic; `backend/pyproject.toml`, runtime deps locked in `backend/requirements.lock`, dev tools pinned |
| Database | PostgreSQL 16 (pgvector image) via Compose; SQLite for local runs and tests |
| AI | Rules provider (default, offline) and Claude provider (`anthropic` SDK) behind one interface |
| Containers | `backend/Dockerfile` (non-root, health check); `docker-compose.yml` (db + api) |
| CI | `.github/workflows/ci.yml` |
| Configuration | Environment variables prefixed `SITEGUARD_`; every setting is listed in `.env.example` |

### Baseline checks

| Command | Result on 09 October 2026 |
|---|---|
| `ruff check app tests` / `ruff format --check app tests` | Clean |
| `mypy app --ignore-missing-imports` (mypy 2.4.0) | Clean |
| `pytest -q` | 57 passed |
| `docker build -f backend/Dockerfile .` | Builds |
| `docker compose up` + `scripts/demo_walkthrough.py` | Passes end to end on PostgreSQL |

### Conflicts with the playbook

1. The playbook and blueprint expect themselves at the repository root; they are in `docs/planning/`.
2. The Blueprint describes the target system (OIDC, Neo4j, object storage, metrics). Since Prompt 01 each document
   marks what is implemented and what is target.
3. The playbook asks for "LangGraph-style" orchestration; the code uses a bounded sequential workflow
   (DECISIONS 007).
4. All demo incidents and procedures are synthetic. The public datasets in `docs/DATASETS.md` are registered but
   not downloaded, and several vision datasets are non-commercial.
5. The playbook runs prompts in order, but Prompts 02–23 were largely implemented together in PR #1. The table
   records the real state of each gate so the remaining work can continue in order.

## Gate status

Status values: **Done**, **Partial** (works, with listed gaps), **Missing**.

| Prompt | Milestone | Status | Notes |
|---|---|---|---|
| 00 | Repository baseline | Done | This report; `.gitignore`, `.env.example`, `docs/AGENTS.md` refreshed |
| 01 | Source-of-truth documentation | Done | All 16 docs follow the Blueprint and mark implemented vs target; open decisions O1–O12; `tests/test_docs.py` |
| 02 | Application scaffold | Done | Backend plus `frontend/` (Next.js 16, TypeScript, Tailwind) with lint, type check, tests and build in CI |
| 03 | Local development environment | Done | Makefile, Compose (PostgreSQL + API), `.env.example` |
| 04 | PostgreSQL foundation | Done | Alembic migrations, applied on startup; parity test |
| 05 | Authentication / RBAC | Partial | Password + JWT, 9 roles, server-side RBAC, login rate limit; no OIDC yet |
| 06 | Projects / sites | Done | Sites created with the project only |
| 07 | Incident lifecycle | Done | Enforced state machine; CLOSED only after verification |
| 08 | Evidence / storage | Done | Magic-byte validation, SHA-256, local disk (Blob Storage adapter pending) |
| 09 | Document parsing | Done | PDF, DOCX, Markdown, text; PENDING → PROCESSING → READY / FAILED; original kept; duplicates detected. No OCR for scanned PDFs |
| 10 | Chunking / provenance | Done | Heading, page and semantic strategies; page, section, version, effective date, tags on every hit; tables never split |
| 11 | Embeddings / vector search | Done | `chunk_embeddings` (pgvector on PostgreSQL), idempotent batch indexing with retries; offline hashing embedder until a semantic model is chosen (O5) |
| 12 | Hybrid retrieval / reranking | Done | BM25 + vector, RRF, deterministic reranker; 14 labelled queries, hybrid hit@3 ≥ 0.85 and never below lexical |
| 13 | Grounded RAG answers | Done | `POST /knowledge/answer`: citations, insufficient and conflicting evidence, unsupported claims removed, provider fallback |
| 14 | Risk engine | Done | Deterministic 5x5 matrix, versioned |
| 15 | Agent framework | Done | Tool allowlist, budget, schema validation, citation filtering, fallback |
| 16–21 | Triage, safety, quality, RCA, compliance, CAPA agents | Done | Rules provider default; Claude provider with fallback |
| 22 | Human approval | Done | Approve / modify / reject; critical needs HSE manager |
| 23 | CAPA workflow | Done | Progress, independent verification, gated closure |
| 24 | Notifications / escalation | Done | In-app notifications from workflow events, four escalation rules, email outbox with retries and dead letters, idempotent; external delivery off by default. Web screen pending |
| 25–27 | Vision foundation, PPE, defects | Missing | |
| 28 | Neo4j knowledge graph | Missing | |
| 29 | Multi-agent orchestration | Done | Bounded sequential workflow (DECISIONS 007) |
| 30 | Uncertainty / conflict | Partial | Low-confidence, suspicious-source and severity-conflict flags; knowledge answers report conflicting sources |
| 31 | Incident command center UI | Done | One workspace: summary, risk, evidence, AI triage and investigation, citations, RCA, compliance, CAPA, approvals, verification, timeline; AI output labelled |
| 32 | Dashboard / analytics | Partial | Dashboard API and screen; no date filters or response-time trend yet |
| 33 | Knowledge search | Partial | Hybrid search and grounded answer APIs; the web screen shows search results, not yet grounded answers or uploads |
| 34 | Reports | Done | Incident report in Markdown, Word and PDF from stored records: incident, history, evidence, risk, labelled AI analysis, actions, approval history, verification, cited sources; audited with SHA-256; snapshot-tested. Web download button pending |
| 35 | Audit / provenance | Done | Audit events with correlation IDs; evidence hashes |
| 36 | Observability | Partial | JSON logs, correlation IDs; no metrics / OpenTelemetry |
| 37 | Resilience | Partial | Provider fallback, agent failure isolation; no retries or queue |
| 38 | Security hardening | Partial | Validation, scoping, rate-limited login, security headers, safe seeding defaults, locked deps; no dependency scanning |
| 39 | Prompt injection / tool safety | Partial | Untrusted framing, injection flagging, allowlisted tools; no red-team suite |
| 40–41 | Evaluation, red team | Missing | Unit tests cover injection and fallback only |
| 42 | Performance | Missing | |
| 43 | Docker | Done | Non-root image from `requirements.lock`, health check |
| 44 | GitHub Actions | Done | Lint, types, tests, PostgreSQL + pgvector tests, image build, end-to-end smoke run |
| 45–46 | Staging, Azure | Missing | No live deployment without the owner's explicit approval |
| 47 | Governance gate | Missing | |
| 48 | End-to-end acceptance | Partial | API-level E2E test, walkthrough and a Playwright browser E2E (incident → investigation → approval; auditor read-only) |
| 49–50 | Final review, release | Missing | |
| 51 | Claude Code control plane | Partial | `CLAUDE.md`, `.claude/rules`, `.claude/agents`, `.claude/settings.json` exist; the verification itself runs as the last gate |

## Known gaps that affect a demo

- All incidents and procedures are synthetic (`data/seed/`); the public datasets in `docs/DATASETS.md` are registered
  in `data/dataset_registry.yaml` but not downloaded or ingested.
- Evidence is stored on local disk; mount a volume in containers.
- The login rate limiter is per process.

## Next gate

Prompt 25 (vision foundation), then the remaining gates in order.

## Verification commands

```bash
make install && make lint && make test
docker compose up --build   # PostgreSQL + API
make demo                   # regenerates docs/RESULTS.md from a live run
```
