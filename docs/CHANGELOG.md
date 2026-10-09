# Changelog

## Unreleased

### Added

- Alembic migrations (`backend/app/migrations/`), applied on startup and with `make migrate`; pilot databases are
  stamped at the baseline instead of recreated. Model/migration parity test.
- Login rate limiting (429 `RATE_LIMITED`) and security headers on every response.
- `backend/requirements.lock`; pinned dev tools.
- `docs/PROJECT_STATUS.md`, `.claude/` rules, reviewer agents and settings, `data/dataset_registry.yaml`.
- Prompt 00 baseline: repository state, structure, checks and playbook conflicts in `docs/PROJECT_STATUS.md`;
  `.gitignore` now covers all `.env.*` files, keys, local databases and downloaded datasets; `.env.example`
  lists every setting.

- Prompt 01 source of truth: PRD, UX flows, design system, architecture, database, API, security, error handling,
  observability, code style and testing docs now follow the Blueprint and mark what is implemented versus target;
  open decisions are listed in `docs/DECISIONS.md`; `tests/test_docs.py` fails when a route, role or error code
  is missing from the docs.

- Prompts 09–13 knowledge pipeline: PDF and DOCX parsing (`POST /documents/upload`) with processing states,
  failure reasons, duplicate detection and the original file kept; heading, page and semantic chunking with page and
  section provenance; chunk embeddings (`chunk_embeddings`, pgvector on PostgreSQL) with idempotent batch indexing
  and retries (`POST /documents/reindex`, also at startup); hybrid search (BM25 + vector, reciprocal rank fusion,
  reranking) with full citation metadata; grounded answers (`POST /knowledge/answer`) with insufficient and
  conflicting evidence statuses and unsupported claims removed. `GET /documents/{id}` and
  `GET /documents/{id}/download`. Migration `0002`. Labelled retrieval queries in `evals/retrieval/`.
- CI job running PostgreSQL + pgvector integration tests.
- Prompt 24 notifications: in-app notifications for workflow events, escalation rules for overdue actions,
  unreviewed severe incidents and waiting critical reviews, an email outbox with retries, backoff and dead letters,
  `python -m app.jobs` / `make jobs`, `/notifications` endpoints and migration `0003`. Notification failures never
  undo a workflow change; real email is refused in local and test environments.
- Prompts 25–27 vision: `POST /evidence/{id}/vision` checks the evidence hash, decodes JPEG/PNG in a
  resource-limited child process (orientation, metadata removal, decompression-bomb limit, image-quality flags) and
  runs the configured analyzer (`baseline` or Claude vision) against a versioned PPE, hazard and defect taxonomy;
  project and site threshold calibration (`/projects/{id}/vision/calibration`); observations stored with evidence
  SHA-256, analyzer, model and taxonomy versions; engineer review (`/vision/observations/{id}/review`); safety and
  quality agents cite only confirmed observations and question unreviewed ones; reports list observations.
  Migration `0004`.
- Prompt 34 reports: `GET /incidents/{id}/report` in Markdown, Word or PDF (fpdf2), built only from stored records
  with labelled AI sections, approval history, verification and cited sources; generation audited with SHA-256.
- Web app (`frontend/`, Next.js 16): sign-in through a same-origin BFF with an httpOnly session cookie, project
  dashboard, incident list and intake, incident command center, CAPA review board, knowledge search and audit log;
  Vitest unit and component tests, Playwright browser E2E, Docker image, compose service and CI jobs.
- Upload hardening: PDF/DOCX parsed in a resource-limited child process, zip-bomb checks, declared MIME type
  checked against the extension, size enforced while reading, no stored file left behind by a failed request,
  organization-wide documents and reindex limited to organization-wide roles, injection flagging covers headings
  and titles, untrusted blocks escaped in model prompts.

### Changed

- `GET /search` is hybrid by default (`mode=lexical` for BM25 only) and returns version, effective date, page,
  tags, scope and scores on every hit. `POST /documents` accepts `effective_date` and `tags` and returns the
  existing document (200, `duplicate: true`) for the same content and version.
- Demo data seeds by default only when `SITEGUARD_ENV` is local, test or demo; production refuses to start with
  seeding on, and non-local environments refuse a weak JWT secret.

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
