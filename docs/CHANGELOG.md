# Changelog

## Unreleased — rebuilding PR #2 on main

### Stage A: hardening and deployment

- Login throttle (429 `RATE_LIMITED`, `Retry-After`), security headers, CSP on the web app, `no-store` on API responses.
- Startup configuration validation for staging and production; demo seeding only in local, test and demo.
- Azure Bicep (network, private PostgreSQL, Key Vault, managed identity, registry, Azure Files evidence share,
  Container Apps app and jobs, monitoring) and a manual OIDC deploy workflow with a migration job, smoke test and
  rollback instructions, adapted to one container.
- Isolated staging compose stack; `scripts/smoke_test.py`, `scripts/backup.py` (with a PostgreSQL restore drill),
  `scripts/dependency_audit.py`; `app.core.db.run_migrations()`.
- `backend/requirements.lock`, pinned dev tools; CI jobs `postgres`, `dependency-audit` (also weekly),
  `infrastructure`, and a smoke test in `docker`.
- `.claude/` review agents, rules and permission settings; docs/GOVERNANCE.md.

### Stage B: documents, hybrid retrieval, grounded answers

- `POST /documents/upload` for PDF, DOCX, Markdown and text: parsed in a resource-limited child process, chunked
  with section and page provenance, original kept; unparseable files become `FAILED` documents with the reason;
  duplicates (same content, version and scope) are not ingested twice.
- `GET /documents/{id}`, `GET /documents/{id}/download`, `POST /documents/reindex`.
- Embeddings per chunk (`chunk_embeddings`; pgvector on PostgreSQL, JSON on SQLite) with an offline hashing
  embedder; hybrid search (BM25 + vector, reciprocal rank fusion, deterministic rerank), `mode=lexical` available.
- `POST /knowledge/answer`: grounded answers with citations, or explicit insufficient or conflicting evidence;
  unsupported claims removed; audited.
- Organization-wide documents need an organization-wide `MANAGE_DOCUMENTS` role; instruction-like titles and
  headings are flagged; content sent to Claude cannot close its untrusted-data tag.
- Request bodies over the largest allowed upload are refused with 413 before they are read; uploads whose content
  does not match the extension are refused before they are stored; agents can no longer cite instruction-like
  chunks with any provider (previously only the rules provider skipped them).
- Migration `0002`; CI runs the pgvector integration tests. Evaluation: dev-split retrieval hit@3 88% → 92%
  (held-out unchanged at 96%).

## 0.2.0 — Web app, full incident coverage, evaluation

### Added

- Web app (`frontend/`, Next.js 16 + TypeScript + Tailwind 4) served by the API at `/app`: dashboard with KPI tiles
  and accessible charts, incident list with filters, report incident with evidence, incident workspace (AI panels
  marked as AI-generated, deterministic risk, cited requirements, approve/modify/reject with reasons, work,
  independent verification, closure blockers, evidence, lifecycle, report download), action queue, knowledge
  search, audit trail, notifications. Playwright browser tests.
- Notifications (review required, assignment, failed verification) and idempotent two-level escalation of overdue
  actions: `POST /capa/escalate-overdue`, `python -m app.jobs escalate-overdue`.
- `GET /incidents/{id}/report` (Markdown investigation report), `GET /capa`, `GET /projects/{id}/people`.
- CAPA proposals and root-cause cues for every taxonomy class; 11 more synthetic incidents and 2 synthetic
  procedures so every class appears in the demo.
- Evaluation framework and red-team suite (`python -m app.evaluation`, `docs/EVALUATION.md`) with a held-out split
  and CI gates.
- Alembic migrations (initial revision `0001`), run by the container on start.
- Dataset registry (`data/dataset_registry.yaml`) and OSHA Severe Injury Reports pipeline (`app/datasets/osha_sir.py`).
- `scripts/resolve_all.py`: resolves every open incident over HTTP and writes `docs/RESULTS.md` and `docs/reports/`.

### Changed

- Triage rates structural quality defects by consequence (no longer LOW); high-energy hazards with a person exposed
  are rated by credible outcome; keyword fixes from dev-split errors and from browser testing (`fire`, `leak`,
  `cylinder`, `electric`, `amputat`).
- Injection detection also scans incident and evidence text.
- Backfilled seed actions are due relative to the incident date, so overdue actions exist in the demo.
- Docker image is two-stage (web build + API); CI adds frontend, browser and full-resolution jobs.

### Fixed

- Action queue could show a stale empty list when switching tabs quickly (found by the browser tests).

## 0.1.0 — Backend pilot

### Added

- FastAPI backend: projects, incidents and lifecycle, evidence upload, knowledge ingestion and BM25 search.
- Six bounded agents (triage, safety, quality, RCA, compliance, CAPA) with an offline rules provider and a Claude
  provider with automatic fallback.
- Deterministic 5x5 risk matrix.
- Human approval (approve / modify / reject), CAPA work tracking, independent verification and gated closure.
- Server-side RBAC for the nine documented roles, tenant isolation, audit trail with correlation IDs.
- Dashboard API, synthetic demo seed data, `scripts/demo_walkthrough.py` and `docs/RESULTS.md`.
- Dockerfile, docker-compose (PostgreSQL + API), GitHub Actions CI, 50 tests.
- `docs/AGENTS.md` (was referenced by CLAUDE.md but missing).

## Final Blueprint Revision (planning package)

- Vibe Coding Blueprint-aligned project structure, Claude Code control plane, data/resource register,
  4–5 hour pilot framing and decision-support positioning. Source files are in `docs/planning/`.
