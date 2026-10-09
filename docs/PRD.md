# Product Requirements Document

Source: Blueprint Part 3 (`docs/planning/`). What is built today is tracked in `docs/PROJECT_STATUS.md`.

## Product Overview

| | |
|---|---|
| Product | Site Guard AI |
| Registered project title | Site Guard AI: Multi-Agent Construction Safety & Quality Incident Resolution System |
| Positioning | Agentic AI-powered Construction Safety & Quality Decision-Support and Workflow Platform |
| Product type | Enterprise-oriented responsive web application + REST API |
| Primary platform | Web + API; mobile/PWA later |
| Primary AI mode | Agentic AI + RAG + multimodal evidence analysis |
| Primary outcome | Evidence-backed incident investigation and closed-loop resolution workflow |

## Problem

Construction safety and quality information is fragmented across incident forms, near-miss logs, inspection
checklists, PDFs, spreadsheets, emails, photographs, method statements, JSA/JHA, ITPs, specifications, NCR/CAR/CAPA
records and audit reports. Teams must find that information and also interpret evidence, assess risk, identify
causes, locate applicable requirements and follow corrective actions through closure.

## Goals

Primary: assist teams with evidence collection, incident investigation, risk assessment, RCA, compliance evidence
retrieval and corrective-action workflow.

Secondary: standardize investigation workflows; reduce manual document lookup; preserve evidence and provenance;
make AI uncertainty visible; track CAPA to verified closure; create analytics and historical learning; provide a
deployable product pilot.

## Target Users

| User | Needs | Role(s) in the system (docs/SECURITY.md) |
|---|---|---|
| HSE / Safety Manager | triage, risk visibility, evidence-backed recommendations, escalation, closure verification | HSE_MANAGER |
| Safety Engineer | hazard analysis, controls, evidence, RCA support, compliance retrieval | SAFETY_ENGINEER |
| QA/QC Engineer | defects, NCRs, ITP/specification references, quality evidence, CAPA | QA_QC_ENGINEER |
| Project Manager | project-level risk, overdue actions, recurring issues, management reporting | PROJECT_MANAGER |
| Site Engineer | report incidents, add evidence, carry out actions | SITE_ENGINEER |
| Auditor / Client | traceable evidence, approvals, audit history, report export | AUDITOR (VIEWER for read-only) |
| Administrators | organizations, projects, users | ORG_ADMIN, SUPER_ADMIN |

Contractor access has no dedicated role yet (see "Open decisions" in `docs/DECISIONS.md`).

## Core Features

1. Authentication and RBAC
2. Organization / project / site management
3. Incident and quality-observation lifecycle
4. Evidence upload
5. Document ingestion
6. Hybrid RAG + reranking
7. Incident Triage Agent
8. Safety Investigation Agent
9. Quality Investigation Agent
10. Deterministic Risk Engine
11. RCA Agent
12. Compliance Agent
13. CAPA Recommendation Agent
14. Human approval
15. Workflow, reminders and escalation
16. Multimodal vision
17. Construction knowledge graph
18. Dashboard / analytics
19. Reports
20. Audit / provenance
21. Observability
22. Evaluation / red-team
23. Docker / CI
24. Azure deployment

## Non-goals for the initial pilot

- Autonomous work stoppage without a configured human policy.
- Autonomous legal or regulatory certification.
- Autonomous regulatory filing.
- Full BIM / digital-twin implementation.
- Full mobile / offline field application.
- Predictive safety claims without validated customer data.

The platform does not replace emergency response procedures.

## MVP Scope

- **Must have:** login/RBAC, projects, incidents, evidence, RAG, triage, safety/quality investigation, risk engine,
  RCA, CAPA, human approval, workflow, dashboard, audit.
- **Should have:** basic vision, compliance agent, reports, notifications, knowledge graph.
- **Future:** BIM/IFC, IoT, predictive risk, mobile/offline, digital site intelligence.

## Success Metrics

Triage classification accuracy; retrieval precision/recall; citation coverage; unsupported-claim rate; RCA expert
agreement; risk-matrix agreement; CAPA actionability/acceptance; workflow completion rate; overdue-action rate;
critical-hazard false-negative rate; latency and cost per incident analysis. How each is measured is in
`docs/TESTING.md`.

## Timeline Constraint

The Project 2 brief sets a minimum 4–5 hour implementation window for the final presentation. That window fits a
demonstrable product pilot, not a production-grade enterprise release. The full roadmap is in the playbook and
`docs/ROADMAP.md`.

## Definition of Done

A feature is complete only when: the implementation works; authorization is enforced; relevant tests pass;
API/database changes are documented; AI outputs are structured; evidence provenance is preserved; failure states
are handled; documentation is updated; the git diff is reviewed; and a commit is created.
