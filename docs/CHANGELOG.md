# Changelog

## Unreleased

### Added

- Alembic migrations (`backend/app/migrations/`), applied on startup and with `make migrate`; pilot databases are
  stamped at the baseline instead of recreated. Model/migration parity test.
- Login rate limiting (429 `RATE_LIMITED`) and security headers on every response.
- `backend/requirements.lock`; pinned dev tools.
- `docs/PROJECT_STATUS.md`, `.claude/` rules, reviewer agents and settings, `data/dataset_registry.yaml`.

### Changed

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
