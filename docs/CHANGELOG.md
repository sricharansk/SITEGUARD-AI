# Changelog

## Unreleased — rebuilding PR #2 on main

### Fresh screenshots; Review III deck with the product screens

- `docs/screenshots/` recaptured by the browser end-to-end run on main (after the crane-access fix: the action queue
  no longer shows a lift-plan action for the slab-edge slip).
- Review III deck, now 18 slides: two new findings slides show the product in use (AI investigation, action queue,
  verified closure; grounded answer, photo review, audit trail) from the same run. Backend test count 255 → 267 on
  the performance slide (and 249 → 267 in the README quick start). Every other figure re-checked against
  EVALUATION.md, RESULTS.md and LOAD_TEST.md.

### A crane mentioned in passing is not a lifting operation

- Triage ignores a crane named only as the reason for something else ("a section of guardrail had been removed for
  crane access"). That phrase had added Lifting operation / crane to a slab-edge slip, and with it the action
  "Suspend lifts until the lift plan is reviewed", which the scripted reviewer approved. A crane that is part of what
  happened ("the crane lost a load", "crane overturned") is still a lifting operation; a test covers both.
- No dev or held-out case changes label, so the evaluation is unchanged. Resolve-all: 21/21 closed, 79 decisions
  (64 approved, 15 rejected); SG-2026-0015 now has 4 proposed actions, all about the fall.
- Review III deck: the findings slide uses this run (15 actions awaiting review and 4 overdue before the run,
  79 decisions) and a new dashboard image; it had still shown figures from before the previous change.

### One word counts once; every class has a corrective action

- Triage scoring counts a keyword only where no longer keyword of the same label covers it, so "specification" no
  longer counts as both "spec" and "specification" (it had added Material nonconformance, and quarantine actions,
  to a cracking incident).
- The safety and quality investigation agents apply the same evidence bar as triage (a label needs more than one
  ambiguous word); their labels feed CAPA, so one incidental word no longer adds unrelated actions.
- A person struck in the passive voice ("a worker was struck by a falling prop") is recognised as struck-by.
- Mobile plant, cuts / sharp objects and manual handling now have a corrective action of their own; before, their
  corrective actions only appeared when an unrelated label added one. A test keeps every class covered.
- Evaluation: held-out class 89.1%, domain 93.5%, severity within one 97.7%, retrieval 93.5% unchanged; cases with a
  corrective action 84.8% → 91.3% (held-out) and 90.0% → 95.8% (dev); dev compliance citing the expected procedure
  85.8% → 85.0% (one case). Resolve-all: 21/21 closed, 80 decisions (65 approved, 15 rejected).

### Review III presentation

- `docs/presentation/SiteGuardAI_Review3_S.K.Sricharan_T9984.pptx`: 16-slide Review III deck on the programme
  template (introduction, objectives, modules, problem statement, methodology with the system architecture and the
  incident resolution workflow, approach and tools, findings, conclusion, acknowledgement, references). Every figure
  comes from docs/EVALUATION.md, docs/RESULTS.md and docs/LOAD_TEST.md.

### Fewer off-topic actions; a real demo photo

- Triage keeps a hazard or defect label only when more than one ambiguous word supports it, so "tower quarantined"
  no longer adds a material defect, and its quarantine actions, to a fall from height. Severity still weighs every
  cue, so it is unchanged. Held-out scores unchanged (class 89%, domain 93%, severity within one 98%, retrieval
  93%); reviewers now see 90 proposals in the resolve-all run instead of 99.
- `scripts/demo_walkthrough.py` uploads a small, valid, synthetic PNG (a scaffold tower with one open side) instead
  of placeholder bytes, so the photo review shows an image.

### Load test and capacity

- `scripts/load_test.py`: signed-in readers and optional incident reporters against a running stack; per-endpoint
  p50/p95/p99, throughput and error rate; `--max-error-rate` / `--max-p95-ms` gates; refuses production. CI runs a
  20 s check in the `docker` job.
- `docs/LOAD_TEST.md`: one API process serves about 55 req/s; 100 readers at 2 s think time plus 2 reporters ran
  at 39 req/s, read p95 0.80 s, 0 errors; an investigation takes 2–2.5 s; the dashboard, action queue and incident
  list slow linearly with project size (dashboard 20 ms → 82 ms from 20 to 155 incidents).
- Fix: two incident reports submitted at the same moment got the same reference and the second failed with HTTP 500.
  Numbering is serialised with a PostgreSQL advisory lock, and the API renumbers and retries when a reference is
  taken (SQLite). Tests on PostgreSQL (8 concurrent reports) and SQLite.

### Accuracy: new held-out set, second tuning round

- Evaluation protocol (Decision 025): the old test split had been seen, so it is now dev (`origin: test-v1`). A new
  held-out set `data/eval/heldout_v2.yaml` (46 cases, separate author) was frozen before tuning. 72 more dev cases
  (`data/eval/dev_v2.yaml`) were added.
- Triage rules tuned on dev errors only: weighted keyword evidence, object-fell / person-fell / person-struck
  patterns, a measured-deviation cue, broader construction vocabulary, stricter BOTH, no class from one ambiguous
  word, a reported BOTH is kept while both sides have evidence.
- Demo knowledge procedures filled out (fragile roofs and dropped objects, task PPE, temporary supplies and buried
  services, crane set-up, plant and deliveries, concrete, formwork, steelwork and goods-in checks).
- Held-out results (one measurement before and after): class 67% → 89%, domain 80% → 93%, severity within one
  96% → 98%, retrieval hit@3 67% → 93%, CRITICAL under-rated 0, red-team 100%. Every pilot target is met. CI floors
  raised to just under these values.

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

### Stage C: Word and PDF reports, email outbox

- `GET /incidents/{id}/report?format=md|docx|pdf`: Word and PDF rendered from the same Markdown report, with an
  `X-Report-SHA256` header; every download audited with format and checksum. The incident workspace offers
  Markdown, Word and PDF downloads.
- Email delivery outbox (`notification_deliveries`, migration `0003`): each notification is queued in the same
  transaction; `python -m app.jobs deliver-notifications` sends due rows with the `disabled` (default), `log` or
  `smtp` adapter, with backoff, bounded attempts and dead letters. `GET /notifications/deliveries`,
  `POST /notifications/deliver`, `POST /notifications/deliveries/{id}/retry` for administrators.
- Startup refuses `smtp` in local and test and SMTP without STARTTLS in staging and production. Azure Bicep and the
  staging stack pass email settings, with `smtp-password` in Key Vault; the scheduled job runs both jobs.

### Stage D1: vision analysis of photo evidence

- `POST /evidence/{id}/vision` (`PPE_HAZARD` or `DEFECT`): checks the stored file against its SHA-256, decodes the
  image in a resource-limited child process (orientation, metadata removed, size and decompression-bomb limits),
  measures image quality and runs the configured analyzer: `baseline` (no detection model; says so) or Claude vision.
  Every detection is stored as an observation with analyzer, model and taxonomy versions and the thresholds used;
  a failed analysis is stored as `FAILED`, never as "nothing found". Rate limited per user.
- Engineers confirm or reject observations (`POST /vision/observations/{id}/review`); thresholds per label can be
  calibrated per project or site. Safety and quality agents cite only confirmed observations (`vision:` refs) and turn
  unreviewed ones into open questions. The investigation report lists photo observations with their review state.
- Migration `0004`; `GET /vision/taxonomy`, `GET /incidents/{id}/vision`, `GET/PUT /projects/{id}/vision/calibration`.

### Stage D2: knowledge graph

- Optional knowledge graph built as a projection of PostgreSQL (`services/graph.py`): organizations, projects,
  sites, locations, people, incidents, evidence, documents, investigations, hazards, RCAs, causes, requirements and
  actions, with provenance (source table, row, field, agent run, AI-derived, review status) on every node and
  relationship. In-memory or Neo4j store; fixed, allowlisted, parameterized Cypher.
- `python -m app.jobs graph-sync` / `make graph-sync` and `POST /graph/sync` (organization-wide `MANAGE_PROJECTS`,
  audited) rebuild it idempotently and remove deleted records; `GET /incidents/{id}/graph` returns an incident's
  neighbourhood limited to the caller's organization and projects. Off by default (`SITEGUARD_GRAPH_BACKEND`).
- Startup refuses unsafe Neo4j settings (no password, wrong scheme, no TLS in staging and production). Optional
  `neo4j` compose service (`graph` profile) and a CI `neo4j` job against Neo4j 5.26.

### Stage D3: resumable investigations and recorded conflicts

- The investigation is a checkpointed `workflow_runs` row (migration `0005`): each stage's result is stored with its
  records in one transaction, so a workflow can pause for review (`?pause_after=`, `POST /workflows/{id}/pause`), be
  resumed from the next unfinished stage without duplicating runs or actions (`POST /workflows/{id}/resume`), be
  cancelled with a reason, or recover after a crash (lease). Agent stages are retried with backoff before they are
  recorded as failed; a failed workflow notifies the person who started it. One active workflow per incident.
- Disagreements are stored, not resolved by AI (`agent_conflicts`): severity, domain, risk above reported, safety
  versus quality, cited documents with different values, and vision analyses or reviews that disagree. Project and
  HSE managers are notified, an open conflict blocks closure until a person records a decision
  (`POST /conflicts/{id}/resolve`), and the workspace, web app and investigation report show both sides and the
  decision. The workflow also stores an uncertainty summary.
- `scripts/resolve_all.py` and `scripts/demo_walkthrough.py` record a decision on each open conflict before closing.

### Stage E3: email outbox screen

- Email outbox page for organization-wide auditors, HSE managers and administrators: deliveries by status with
  attempts, last error and next try, recipients by name only; organization-wide administrators send due emails now
  and retry failed or skipped deliveries. "AI" and "CAPA" labels. Browser test.

### Stage E2: incident workspace panels

- Workflow card (stages, attempts, lowest confidence, open questions; Resume, Cancel with reason, Pause while
  running) and "Pause after triage for my review"; the Run button is hidden while a workflow is active.
- Photo review: PPE/hazard and defect checks per photo, analyses marked as machine output with analyzer, image
  quality and limitations, boxes drawn on the photo, confirm or reject each observation with a note.
- Knowledge graph card: related records with AI-derived relationships marked, rebuild for organization-wide project
  managers, or a plain message when the graph is disabled. Browser test with a synthetic fixture photo.

### Stage E1: knowledge screens

- Knowledge page: ask the knowledge base (grounded answer with clickable citations to document, version, section and
  page; answered, insufficient or conflicting evidence; removed unsupported statements and flagged sources), search
  with provenance and scores, document detail with status, parser, pages, checksum, passages and original download,
  and document upload (PDF, Word, Markdown, text) for people with `MANAGE_DOCUMENTS`, with organization-wide scope
  offered only to organization-wide members. Browser test for upload and answers.

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
