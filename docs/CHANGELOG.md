# Changelog

## Unreleased — Web app, first slice

### Added

- `frontend/`: Next.js 15 + TypeScript + Tailwind app against the existing API. Screens: login, dashboard, incident
  list with filters, incident workspace (report, AI agent outputs and tool traces, deterministic risk, CAPA, closure
  blockers, evidence, history) and review queue.
- Human approve/reject of proposed actions with a mandatory reason; AI output is visually distinct ("AI draft") and
  severity always has a text label. Permissions are read from the API; the server remains the authority.
- `make web`, `make web-check` and a `frontend` CI job (typecheck, lint, build).

### Known limitations

- No queue endpoint exists, so the review queue gathers pending actions from the project's open incidents client-side.
- Modify decision, new-incident form, evidence upload, verification and closure screens are not built yet.
- `npm audit` reports build-time-only advisories in Tailwind 3's file-glob dependencies (`braces`); the fix is a breaking
  Tailwind 4 migration. Next's nested `postcss` is overridden to the patched version.

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
