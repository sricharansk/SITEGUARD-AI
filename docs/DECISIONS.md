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

## Decision 009 — BM25 retrieval before pgvector (superseded by 017)

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
Stage B: document parsing, embeddings, hybrid retrieval and grounded answers (Decisions 017–019). Stage C: Word and
PDF reports, email delivery outbox (Decisions 020–021). Stage D: vision evidence analysis (Decision 022), knowledge
graph (Decision 023), resumable workflows and conflicts (Decision 024).

## Decision 016 — One container on Azure

Reason: main's API serves the web app at `/app` (Decision 011), so the Azure deployment from PR #2 is adapted to one
Container App with external HTTPS ingress instead of an internal API plus a web app with a server-side proxy. The
login throttle and startup migrations keep it at one replica for now.

## Decision 017 — Hybrid retrieval with an offline hashing embedder until a model is chosen

Reason: Playbook Prompts 11–12 need vector search, but the embedding model is an open owner decision (data
residency, cost) and tests must not call external services. `HashingEmbedder` (`hashing-bow` v1, 384 dimensions)
hashes stemmed words and word pairs into a normalised vector: deterministic, offline and free, and it catches word
forms and phrases BM25 misses, but it does not capture meaning. Vectors are stored per (chunk, model, version) in
pgvector, so a semantic model plugs in behind the `Embedder` interface and is indexed alongside without a schema
change. Lexical and vector rankings are combined with reciprocal rank fusion (k = 60), which needs no score
calibration, then a deterministic reranker (query coverage, heading match, phrase match) orders the top candidates.
On the 14 labelled queries in `evals/retrieval/seed_queries.yaml` hybrid hit@3 must stay ≥ 0.85 and never below
lexical.

## Decision 018 — Grounded answers verify citations and support after the model

Reason: an answer is only useful for safety work if each statement can be traced to a source. Whatever the
answerer returns, statements that cite unknown refs or share less than half their terms with a cited chunk are
removed into `unsupported_claims`; conflicting values across documents force `CONFLICTING_EVIDENCE`; a question the
sources barely cover returns `INSUFFICIENT_EVIDENCE` without calling a model. This keeps the guarantee the same for
the rules and Claude answerers.

## Decision 019 — Untrusted binary documents are parsed in a resource-limited child process

Reason: PDF and DOCX parsers can be driven into minutes of CPU or gigabytes of memory by small hostile files, and the
API process serves every tenant. `parsing.parse_document` runs pypdf and python-docx in `python -m
app.services.parse_worker` with an address-space limit, a CPU-time limit and a wall-clock timeout, after cheap
pre-checks (zip expansion, page count). Text and Markdown stay in process. The cost is a process start per binary
upload, which is small next to parsing and embedding.

## Decision 020 — Word and PDF reports are rendered from the Markdown report

Reason: PR #2 built reports from a separate block model; main already had a reviewed Markdown report that the web
app and `scripts/resolve_all.py` use. Rendering Word (python-docx) and PDF (fpdf2) from that Markdown keeps one
source, so the three formats cannot drift and the AI-generated labels and named human decisions appear in all of
them. Only the fixed Markdown subset the report builder writes is parsed, and nothing is rendered as HTML. The PDF
uses a standard font that covers Latin-1, so other characters are replaced there; Word and Markdown keep the full
text. Each download is audited with its SHA-256.

## Decision 021 — Email through an outbox, off by default

Reason: notifications must not be lost when email fails, and email must never block or undo a workflow change. Each
notification gets a delivery row in the same transaction; a job sends due rows with bounded retries and backoff,
and failures end as visible dead letters an administrator can retry. Email is `disabled` by default and `smtp` is
refused in local and test, because it sends incident details outside the system (an owner decision, GOVERNANCE.md).
Disabled deliveries are marked `SKIPPED`, so turning email on later does not send a backlog of old notifications.

## Decision 022 — Vision is an observation pipeline with a pluggable analyzer and engineer validation

Reason: the detection model is not chosen (an owner decision) and the public PPE and defect datasets are
research-only, so the milestone builds everything around the model and keeps the model swappable. One
`VisionAnalyzer` interface (`agents/vision.py`) reports detections against a versioned taxonomy; the service checks
the evidence hash, decodes the image in a resource-limited child process (as for documents, Decision 019), applies
project/site calibrated thresholds and stores every detection with the analyzer, model version, taxonomy version and
thresholds used. The default `baseline` analyzer detects nothing and says so, rather than pretending; Claude vision
is available as an adapter with self-reported confidence. A failed analysis is stored as `FAILED`, never as "nothing
found". Agents only treat observations a person CONFIRMED as findings; unreviewed ones become open questions, and no
observation is ever read as "no hazard".

## Decision 023 — The knowledge graph is an optional, rebuildable projection of PostgreSQL

Reason: Playbook Prompt 28 asks for a Neo4j knowledge graph, while PostgreSQL stays the system of record (Decision
002) and Neo4j is not needed to run the pilot. The graph is derived: `graph-sync` rebuilds one organization's nodes
and relationships from stored rows, idempotently, and deletes what PostgreSQL no longer has, so it can be dropped and
rebuilt at any time. Every node and relationship names its source row and field, whether it came from AI output and
its review status. Reads go through the same incident authorization (404 out of scope) and are limited to the
caller's organization and projects. The store is `disabled` by default, `memory` for tests and demos, or `neo4j`.
Agents do not read the graph yet; graph-aware retrieval is a later owner decision.

## Decision 024 — The bounded workflow is checkpointed and resumable; conflicts are stored, not resolved by AI

Reason: Playbook Prompts 29, 30 and 37 need pause for human review, resume after a crash and no silent winner when
agents or sources disagree. A graph framework (for example LangGraph) was not needed for that: the fixed stage order
of Decision 007 is kept and each stage is checkpointed in a `workflow_runs` row (status, per-stage record and
validated state) in the same transaction as the stage's records. A resume continues from the next unfinished stage,
so finished stages are never repeated and actions are never duplicated; a stage that raises is rolled back, recorded
as `ERROR` and the workflow is `FAILED` but resumable. Agent stages are retried a bounded number of times
(`SITEGUARD_AGENT_MAX_ATTEMPTS`, exponential backoff) before they are recorded as failed and the workflow carries
on. A lease marks crashed runs. Only one active workflow per incident is allowed (409 `WORKFLOW_ACTIVE`).
Disagreements (severity, domain, risk above reported, safety versus quality, cited documents with different values,
vision analyses or reviews that disagree) are stored as `agent_conflicts` with both sides, people with
`APPROVE_CAPA` are notified, and closure is blocked until a person records a decision.

## Decision 025 — Accuracy is claimed only on a held-out set frozen before tuning

Reason: the first test split had been read while improving the rules, so a higher score on it would not show that
the agents generalise. It became dev data (`origin: test-v1`). Before the second tuning round a separate author
wrote a new held-out set (`heldout_v2.yaml`, 46 cases), committed it (2403a8c) and measured it once as a baseline.
Tuning then used only dev cases (`incidents_gold.yaml` and the new `dev_v2.yaml`, 120 cases); the held-out cases
were not opened. After tuning was frozen in a commit, the held-out set was measured once. Results are reported
whether or not they meet the targets. One gap is disclosed: before tuning, the held-out author's hand-back named
the topics of its four BOTH cases and two unclassifiable cases; no rule was written for them. Because the held-out
per-case results are now published, the next tuning round needs a new held-out set.

## Decision 026 — The audit trail is append-only in the database; readiness is separate from liveness

Reason: the application only inserts audit events, but a console session or a script could still edit or delete
them, which would make the trail worthless as evidence. Migration `0006` adds triggers that refuse `UPDATE` and
`DELETE` (and `TRUNCATE` on PostgreSQL) on `audit_events`. Only the table owner can drop the triggers, so deployed
environments keep the owner role apart from the API's role. `GET /ready` checks that the database answers and the
schema is at the latest migration (503 `NOT_READY` otherwise) and is the readiness probe; `GET /health` stays a
liveness check that touches nothing, so a database outage takes a container out of rotation instead of restarting
it. Both come from the unmerged first build-out branch (Playbook Prompt 36), rebuilt on main without that branch's
other changes (project-scoped audit, `/metrics`, provenance column), which need their own review.
