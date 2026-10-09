# Architecture

Source: Blueprint Part 6. The diagram below is the **target** architecture; the table after it says what is
implemented today.

## Pattern

Modular backend + responsive web app + bounded agent orchestration. Every component is deployable in containers.

## Target stack

| Layer | Target |
|---|---|
| Frontend | Next.js, React, TypeScript, Tailwind CSS |
| Backend | Python, FastAPI, Pydantic, SQLAlchemy, Alembic |
| Data | PostgreSQL, pgvector, object storage, Neo4j |
| AI | Provider abstraction for an approved enterprise LLM/VLM; Transformers/PyTorch where custom models are needed; vision adapters; stateful orchestration |
| Search / RAG | Hybrid lexical + vector search, reranking, metadata/authorization filtering, source citations |
| Workflow | Transactional application state machine for the MVP; Temporal/Camunda only if durable distributed workflows are justified later |
| DevOps | Docker, GitHub Actions, Azure Container Registry, Azure Container Apps (pilot), Azure Database for PostgreSQL, Azure Blob Storage, Azure Key Vault, Azure Monitor / Application Insights |

```mermaid
flowchart TD
    USER[HSE / QA-QC / Project User] --> UI[Next.js Web App]
    UI --> API[FastAPI API + OIDC/RBAC]
    API --> CORE[Domain Services]
    CORE --> INC[Incident Service]
    CORE --> EVID[Evidence Service]
    CORE --> WF[Workflow/CAPA]
    CORE --> ORCH[Agent Orchestrator]
    EVID --> OBJ[(Object Storage)]
    ORCH --> TRI[Triage Agent]
    ORCH --> SAFE[Safety Investigation Agent]
    ORCH --> QUAL[Quality Investigation Agent]
    ORCH --> RCA[RCA Agent]
    ORCH --> COMP[Compliance Agent]
    ORCH --> CAPA[CAPA Agent]
    TRI --> RAG[Hybrid RAG]
    SAFE --> RAG
    QUAL --> RAG
    COMP --> RAG
    RAG --> VDB[(PostgreSQL + pgvector)]
    RAG --> KG[(Neo4j)]
    SAFE --> RISK[Deterministic Risk Engine]
    QUAL --> RISK
    RCA --> RISK
    CAPA --> APPROVE[Human Approval Gate]
    APPROVE --> WF
    WF --> NOTIFY[Notification Adapter]
    WF --> VERIFY[Verification]
    VERIFY --> CLOSE[Closure]
    API --> DB[(PostgreSQL)]
    CORE --> AUDIT[Audit + Observability]
```

## Implemented today vs target

| Component | Today | Target / gap |
|---|---|---|
| Web app | Next.js 16 app in `frontend/`: same-origin BFF with an httpOnly session cookie (DECISIONS 018); dashboard, incident command center, CAPA review board, knowledge search, audit log | SSO sign-in (O1) |
| API | FastAPI, typed schemas, error envelope, correlation IDs | Same |
| Authentication | Email + password, HS256 JWT, login rate limit | OIDC / Microsoft Entra ID |
| Authorization | Server-side RBAC, 9 roles, organization/project scoping | Same |
| Database | PostgreSQL 16 with pgvector, or SQLite; Alembic migrations; chunk embeddings stored | Same; HNSW index once a semantic model is chosen |
| Evidence storage | Local disk under random keys, SHA-256 recorded | Azure Blob Storage adapter |
| Documents | PDF (pypdf), DOCX (python-docx), Markdown and text parsers; heading/page/semantic chunking with page and section provenance; original file kept | OCR for scanned PDFs |
| Retrieval | Hybrid: access-filtered candidates, BM25 + vector (offline hashing embedder), reciprocal rank fusion, deterministic reranker; grounded answers with citations, insufficient/conflicting-evidence statuses | Semantic embedding model and cross-encoder reranker behind the same interfaces (DECISIONS O5) |
| Knowledge graph | None | Neo4j (Prompt 28) |
| Orchestration | Bounded sequential workflow per run (DECISIONS 007); runs and traces stored | Stateful orchestration with checkpoints if needed |
| AI providers | Rules (default, offline) and Claude behind one `Provider` interface, with fallback | Same abstraction; VLM adapters for vision |
| Risk | Deterministic 5x5 matrix, versioned | Same |
| Workflow | Transactional incident and CAPA state machines | Same; reminders and escalation (Prompt 24) |
| Reports | Incident report (Markdown, Word, PDF) rendered by `services/reports.py` from stored records only, AI sections labelled, generation audited | Project summary reports |
| Notifications | In-app notifications from workflow events (via the audit trail), escalation rules for overdue actions, unreviewed severe incidents and waiting critical reviews, email outbox with retries and dead letters (`python -m app.jobs`); external delivery off by default | Teams/SMS channels (O7) |
| Vision | None | PPE/hazard and defect detection (Prompts 25–27) |
| Observability | JSON logs, correlation IDs, audit events, agent traces | Metrics, OpenTelemetry, App Insights |
| Deployment | Docker image, Compose, GitHub Actions | Azure (Prompts 45–46) |

## Agent components

Triage; Safety Investigation; Quality Investigation; RCA; Compliance; CAPA. Responsibilities, tools, budgets,
schemas and failure behaviour are in `docs/AGENTS.md`.

Every agent specifies: allowed tools; input (evidence pack) and output schema; evidence requirements; uncertainty
fields; maximum execution budget; failure behaviour; human-review conditions.

## Retrieval pipeline

```text
upload ─ parse (pdf | docx | text) ─ chunk (heading | page | semantic) ─ flag injection ─ embed ─ READY
query ─ access filter (organization, project or org-wide, READY, domain) ─┬─ BM25 ─────┐
                                                                         └─ vector ───┴─ RRF (k=60) ─ rerank ─ hits
answer ─ hits minus suspicious ─ answerer (rules or Claude) ─ citation + support check ─ conflict check ─ status
```

Every retrieval path starts from the access filter (`rag._allowed`), so a project document can never reach a
query in another project. Final score = 0.5 × normalised fused score + 0.5 × rerank score (query-term coverage,
heading match, phrase match). A hit carries document, version, effective date, page, section, tags, scope and the
individual scores, which is what citations show.

## Data flow

Incident → evidence → retrieval → agents → risk / RCA / compliance → approval → workflow → verification → closure.

## Dependency rules

- The UI never accesses the database directly and never decides authorization.
- Agents use approved service/tool interfaces only (allowlisted per agent).
- Provider-specific code stays behind adapters (`app/agents/llm.py`).
- Routes (`app/api/`) stay thin; business rules live in `app/services/`.
