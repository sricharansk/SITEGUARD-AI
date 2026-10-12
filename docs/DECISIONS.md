# Architecture Decisions

## Decision 001 — Modular architecture

Reason: keeps MVP fast while preserving clear service boundaries.

## Decision 002 — PostgreSQL as source of truth

Reason: transactional data, authorization and audit require relational guarantees.

## Decision 003 — pgvector for MVP

Reason: reduces infrastructure complexity. Upgrade to managed hybrid/vector search when required.

## Decision 004 — Human approval for high-impact safety actions

Reason: AI is decision support and cannot replace accountable personnel.

## Decision 005 — Provider abstraction for LLM/VLM

Reason: avoid vendor lock-in and preserve enterprise deployment flexibility.

## Decision 006 — create_all for the pilot, Alembic before shared data

Reason: the 4–5 hour pilot needs a schema that can change freely. Before a shared staging environment keeps
data across releases, add Alembic and an initial migration generated from `models.py`.

## Decision 007 — Bounded workflow instead of free tool-calling agents

Reason: the orchestrator calls each agent's declared tools to build an evidence pack, and the LLM only turns that
pack into a typed output. This keeps tool use allowlisted and auditable, makes citations checkable, and gives a
deterministic fallback when the LLM is unavailable.

## Decision 008 — Deterministic rules provider as default and fallback

Reason: the product must work offline, in CI and when the AI provider fails (ERROR_HANDLING.md). Rules output is
reproducible and testable; Claude adds better reasoning when configured.

## Decision 009 — BM25 retrieval before pgvector

Reason: no embedding provider is needed for the pilot and results are explainable. The `rag.search` interface
stays the same when vector and hybrid retrieval are added.

## Decision 010 — Seeded demo data is synthetic and labelled

Reason: the sandbox used to build the pilot cannot download the public datasets in DATASETS.md, and incident data
from real companies cannot be published. Seed incidents carry `is_synthetic = true`.

## Decision 011 — Web app as a static export served by the API

Reason: one container serves the API and the UI, so deployment, CORS and TLS stay simple for the pilot. Next.js with
`output: "export"` under `/app`; incident pages use `?id=` because static export cannot pre-render unknown IDs. A
separate Node server can come later if server rendering is needed.

## Decision 012 — Held-out evaluation split and safety-first gates

Reason: tuning keyword rules against the cases you report on inflates results. The gold set has a dev split for
tuning and a test split that was written first and never tuned on. CI enforces the safety gates (no CRITICAL case
rated LOW/MEDIUM, workflow invariants, red-team containment) and a regression floor for accuracy; accuracy targets
that are not yet met are reported, not hidden.

## Decision 013 — Alembic migrations run at container start

Reason: the schema must survive releases once staging holds data (Decision 006). The image runs `alembic upgrade
head` before uvicorn; `create_all` remains for local runs and tests, and a test fails on model changes without a
migration.

## Decision 014 — Escalation as an idempotent job, notifications in-app first

Reason: overdue CAPA escalation must be safe to run repeatedly from a scheduler. Each action records its escalation
level, so each level is sent once. Notifications are stored in the database; email or Teams adapters can read the
same table later.

## Decision 015 — Rebuild PR #2's features on main in stages

Reason: PR #2 and PR #4 were built in parallel from the same base and implement the same parts differently
(migrations, notifications, web app); merging main into #2 conflicted in 50 files. The owner chose to merge #4 and
port #2's additional features onto main stage by stage, each with tests and green CI, rather than one large merge.
Stage A: hardening, configuration validation, Azure IaC and deploy workflow, staging stack, operations scripts.

## Decision 016 — One container on Azure

Reason: main's API serves the web app at `/app` (Decision 011), so the Azure deployment from PR #2 is adapted to one
Container App with external HTTPS ingress instead of an internal API plus a web app with a server-side proxy. The
login throttle and startup migrations keep it at one replica for now.
