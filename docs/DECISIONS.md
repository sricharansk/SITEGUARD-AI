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

## Decision 009 — BM25 retrieval before pgvector (superseded by 015)

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

## Decision 015 — Hybrid retrieval with an offline hashing embedder until a model is chosen

Reason: Prompts 11–12 need vector search, but the embedding model is an open decision (O5: data residency, cost)
and tests must not call external services. `HashingEmbedder` (`hashing-bow` v1, 384 dimensions) hashes stemmed
words and word pairs into a normalised vector: deterministic, offline and free, and it catches word forms and
phrases BM25 misses, but it does not capture meaning. Vectors are stored per (chunk, model, version) in pgvector, so
a semantic model plugs in behind the `Embedder` interface and is indexed alongside without a schema change.
Lexical and vector rankings are combined with reciprocal rank fusion (k = 60), which needs no score calibration,
then a deterministic reranker (query coverage, heading match, phrase match) orders the top candidates. On the 14
labelled queries in `evals/retrieval/seed_queries.yaml` hybrid hit@3 must stay ≥ 0.85 and never below lexical.

## Decision 016 — Grounded answers verify citations and support after the model

Reason: an answer is only useful for safety work if each statement can be traced to a source. Whatever the
answerer returns, statements that cite unknown refs or share less than half their terms with a cited chunk are
removed into `unsupported_claims`; conflicting values across documents force `CONFLICTING_EVIDENCE`; a question the
sources barely cover returns `INSUFFICIENT_EVIDENCE` without calling a model. This keeps the guarantee the same for
the rules and Claude answerers.

## Decision 017 — Untrusted binary documents are parsed in a resource-limited child process

Reason: PDF and DOCX parsers can be driven into minutes of CPU or gigabytes of memory by small hostile files, and the
API process serves every tenant. `parsing.parse_document` runs pypdf and python-docx in `python -m
app.services.parse_worker` with an address-space limit, a CPU-time limit and a wall-clock timeout, after cheap
pre-checks (zip expansion, page count). Text and Markdown stay in process. The cost is a process start per binary
upload, which is small next to parsing and embedding.

## Decision 018 — The web app reaches the API through a same-origin BFF

Reason: keep the API token out of browser JavaScript and avoid cross-origin calls. The Next.js server signs in on
the user's behalf (`/api/session`), stores the JWT in an httpOnly, SameSite=Lax cookie (Secure in production) and
forwards browser calls under `/api/backend/*` to the API with `Authorization: Bearer`. Writes must carry an
`Origin` matching the host (CSRF), only the API roots the app uses are forwarded, and a 401 from the API clears the
cookie. The API still authorizes every call; the UI only hides controls using the `permissions` the API returns.

## Open decisions

These are unresolved. Each lists the behaviour that stays in place until someone decides.

| # | Question | Until decided |
|---|---|---|
| O1 | Which identity provider and tenant for SSO (Entra ID is the documented preference)? | Email + password with JWT |
| O2 | How do contractors and clients get access? There is no dedicated role. | Project-scoped memberships with an existing role (AUDITOR or VIEWER for clients) |
| O3 | Should triage run automatically when an incident is saved (Blueprint Flow 2) instead of on request? | Runs on request (`/triage`, `/investigate`); needs a background job runner first |
| O4 | Keep the bounded sequential orchestrator or adopt a graph framework with persisted checkpoints? | Bounded sequential workflow (Decision 007) |
| O5 | Which semantic embedding model/provider for vector search, given data-residency needs? | Offline hashing embedder in hybrid search (Decision 015) |
| O6 | Evidence storage container, retention and malware scanning in Azure Blob Storage? | Local disk / mounted volume |
| O7 | Which notification channels for reminders and escalation (email, Teams, SMS)? | Dashboard overdue counts only |
| O8 | Which vision models, and can any non-commercial dataset be used beyond evaluation? | No vision features; datasets registered only |
| O9 | Is Neo4j needed for the MVP or deferred? (Blueprint lists the knowledge graph as "should have".) | Deferred |
| O10 | Shared store for rate limiting when running more than one replica? | In-process limiter, single replica |
| O11 | Commercial-use rights for public datasets before any production use | `commercial_use` flags in `data/dataset_registry.yaml` |
| O12 | Production environment and go-live approval | No production deployment without the owner's explicit approval |

