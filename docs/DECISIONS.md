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

## Decision 006 — create_all for the pilot, Alembic before shared data (superseded by 011)

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

## Decision 011 — Alembic owns the schema; the API migrates on startup

Reason: staging and demo environments must keep data across releases. Migrations live inside the `app` package so
the installed image carries them. Startup runs `upgrade head`; pilot databases without `alembic_version` are
stamped at `0001` (identical to the pilot schema) instead of being recreated. A parity test keeps models and
migrations in step.

## Decision 012 — Demo seeding is opt-in outside local, test and demo

Reason: demo users share one known password. `SITEGUARD_SEED_DEMO_DATA` now defaults to on only when
`SITEGUARD_ENV` is `local`, `test` or `demo`, and the API refuses to start with seeding on when
`SITEGUARD_ENV=production`. Outside local/test the API also refuses the default or a short JWT secret.

## Decision 013 — Pinned dependencies

Reason: CI found type errors that an unpinned local toolchain did not. Runtime dependencies are locked in
`backend/requirements.lock` (used by the Docker image and CI) and dev tools are pinned in `pyproject.toml`.

## Decision 014 — Downloaded datasets stay out of git

Reason: several registered datasets forbid redistribution or commercial use, and raw files are large.
`data/raw/`, `data/interim/` and `data/processed/` are git-ignored; each dataset is recorded in
`data/dataset_registry.yaml` with its source, version, checksum and licence so it can be fetched again.

