# Project Status

Last updated: 09 October 2026. Tracks the 52 implementation gates (Prompts 00–51) in
`docs/planning/Site_Guard_AI_Claude_Code_Detailed_Execution_Playbook_FINAL_UPDATED.md`. Update this file in the
same commit as any milestone.

Status values: **Done**, **Partial** (works, with listed gaps), **Missing**.

| Prompt | Milestone | Status | Notes |
|---|---|---|---|
| 00 | Repository baseline | Done | This file, `.gitignore`, `.env.example`, `docs/AGENTS.md` |
| 01 | Source-of-truth documentation | Done | `docs/`; planning package in `docs/planning/` |
| 02 | Application scaffold | Partial | Backend done; web app (`frontend/`) in progress |
| 03 | Local development environment | Done | Makefile, Compose (PostgreSQL + API), `.env.example` |
| 04 | PostgreSQL foundation | Done | Alembic migrations, applied on startup; parity test |
| 05 | Authentication / RBAC | Partial | Password + JWT, 9 roles, server-side RBAC, login rate limit; no OIDC yet |
| 06 | Projects / sites | Done | Sites created with the project only |
| 07 | Incident lifecycle | Done | Enforced state machine; CLOSED only after verification |
| 08 | Evidence / storage | Done | Magic-byte validation, SHA-256, local disk (Blob Storage adapter pending) |
| 09 | Document parsing | Partial | Markdown / plain text only; no PDF or DOCX |
| 10 | Chunking / provenance | Done | Heading-aware chunks with source metadata; no page numbers |
| 11 | Embeddings / vector search | Missing | BM25 only |
| 12 | Hybrid retrieval / reranking | Missing | |
| 13 | Grounded RAG answers | Missing | Search returns cited chunks; no answer endpoint |
| 14 | Risk engine | Done | Deterministic 5x5 matrix, versioned |
| 15 | Agent framework | Done | Tool allowlist, budget, schema validation, citation filtering, fallback |
| 16–21 | Triage, safety, quality, RCA, compliance, CAPA agents | Done | Rules provider default; Claude provider with fallback |
| 22 | Human approval | Done | Approve / modify / reject; critical needs HSE manager |
| 23 | CAPA workflow | Done | Progress, independent verification, gated closure |
| 24 | Notifications / escalation | Missing | Overdue actions are only counted on the dashboard |
| 25–27 | Vision foundation, PPE, defects | Missing | |
| 28 | Neo4j knowledge graph | Missing | |
| 29 | Multi-agent orchestration | Done | Bounded sequential workflow (DECISIONS 007) |
| 30 | Uncertainty / conflict | Partial | Low-confidence, suspicious-source and severity-conflict flags |
| 31 | Incident command center UI | Missing | In progress with the web app |
| 32 | Dashboard / analytics | Partial | Dashboard API; UI in progress |
| 33 | Knowledge search | Done | API, tenant and project scoped |
| 34 | Reports | Missing | |
| 35 | Audit / provenance | Done | Audit events with correlation IDs; evidence hashes |
| 36 | Observability | Partial | JSON logs, correlation IDs; no metrics / OpenTelemetry |
| 37 | Resilience | Partial | Provider fallback, agent failure isolation; no retries or queue |
| 38 | Security hardening | Partial | Validation, scoping, rate-limited login, security headers, safe seeding defaults, locked deps; no dependency scanning |
| 39 | Prompt injection / tool safety | Partial | Untrusted framing, injection flagging, allowlisted tools; no red-team suite |
| 40–41 | Evaluation, red team | Missing | Unit tests cover injection and fallback only |
| 42 | Performance | Missing | |
| 43 | Docker | Done | Non-root image from `requirements.lock`, health check |
| 44 | GitHub Actions | Done | Lint, types, tests, image build, end-to-end smoke run |
| 45–46 | Staging, Azure | Missing | No live deployment without the owner's explicit approval |
| 47 | Governance gate | Missing | |
| 48 | End-to-end acceptance | Partial | API-level E2E test and walkthrough; no browser E2E |
| 49–50 | Final review, release | Missing | |
| 51 | Claude Code control plane | Done | `CLAUDE.md`, `.claude/rules`, `.claude/agents`, `.claude/settings.json` |

## Known gaps that affect a demo

- All incidents and procedures are synthetic (`data/seed/`); the public datasets in `docs/DATASETS.md` are registered
  in `data/dataset_registry.yaml` but not downloaded or ingested.
- Evidence is stored on local disk; mount a volume in containers.
- The login rate limiter is per process.

## Verification commands

```bash
make install && make lint && make test
docker compose up --build   # PostgreSQL + API
make demo                   # regenerates docs/RESULTS.md from a live run
```
