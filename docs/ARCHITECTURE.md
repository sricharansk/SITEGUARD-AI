# Architecture

## Pattern

Modular backend + responsive web app + stateful agent orchestration. Keep components deployable in containers.

## Stack

Next.js; React; TypeScript; Tailwind; Python; FastAPI; Pydantic; SQLAlchemy; PostgreSQL; pgvector; Neo4j; object storage; Docker; GitHub Actions; Azure.


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


## Agent Components

Triage; Safety Investigation; Quality Investigation; RCA; Compliance; CAPA.

## Data Flow

Incident → evidence → retrieval → agents → risk/RCA/compliance → approval → workflow.

## Dependency Rules

UI does not access the database directly. Agents use approved service/tool interfaces. Provider-specific code stays behind adapters.
