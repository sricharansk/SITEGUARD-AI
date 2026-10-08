# 01 — Site Guard AI Project & Product Implementation — FINAL UPDATED

## User Request Summary

Build Site Guard AI as a large Agentic AI construction-safety/quality project that can become a product, with a fast 4–5 hour presentation-grade implementation path, construction datasets/resources from 2024–2026 where genuinely available, full requirements, tech stack, implementation, product positioning, deployment and GitHub workflow.

## Final Product Definition

**Registered title:** Site Guard AI: Multi-Agent Construction Safety & Quality Incident Resolution System

**Product positioning:** Agentic AI-powered Construction Safety & Quality Decision-Support and Workflow Platform.

The platform is not a generic chatbot. Its core loop is:

```text
Incident
→ Evidence
→ Triage
→ Safety/Quality Investigation
→ RAG + Knowledge Graph
→ Risk + RCA + Compliance
→ Decision Support
→ Human Approval
→ CAPA
→ Assignment/Escalation
→ Verification
→ Closure
→ Learning
```

## Main modules

1. Incident Management
2. Evidence Management
3. Construction Document/RAG Engine
4. Incident Triage Agent
5. Safety Investigation Agent
6. Quality Investigation Agent
7. Deterministic Risk Engine
8. RCA Agent
9. Compliance Agent
10. CAPA Agent
11. Human Approval
12. Workflow/Escalation
13. Multimodal Vision
14. Neo4j Construction Knowledge Graph
15. Analytics
16. Reports
17. Audit/Observability
18. Evaluation/Red Team
19. Docker/CI/CD
20. Azure deployment

## Recommended stack

Frontend: Next.js + React + TypeScript + Tailwind.

Backend: Python + FastAPI + Pydantic + SQLAlchemy + Alembic.

Data: PostgreSQL + pgvector + object storage + Neo4j.

AI: enterprise-approved LLM/VLM provider abstraction + PyTorch/Transformers/vision models where required.

Agent orchestration: stateful bounded graph workflow.

Deployment: Docker + GitHub Actions + Azure Container Apps for the initial pilot.

## 4–5 hour reality

The requested 4–5 hour window should be used for a **presentation-grade product pilot**. It is not credible to call an enterprise safety platform production-ready after five hours.

Fast path:

```text
Repository/control plane
→ docs
→ DB/auth/projects
→ incident/evidence
→ RAG
→ agents
→ risk/RCA
→ CAPA/approval
→ dashboard/audit
→ Docker/CI
→ staging/deployment
```

## Data strategy

Use:
- current government safety statistics;
- recent construction vision datasets;
- authoritative current guidance;
- customer/project documents;
- synthetic edge cases.

Do not fabricate 2024–2026 releases. Record observation period and publication/access date separately.

## Immediate implementation

Start from:

```bash
git clone https://github.com/sricharansk/SITEGUARD-AI.git
cd SITEGUARD-AI
claude
```

Then execute the master/detailed playbook one prompt at a time.

## Acceptance

The final pilot should demonstrate:

```text
Create project
→ Create incident
→ Upload evidence
→ Retrieve construction evidence
→ Run triage
→ Safety/quality investigation
→ Risk
→ RCA
→ Compliance evidence
→ CAPA
→ Human approval
→ Track action
→ Verify
→ Close
→ Show audit/dashboard
```
