# Roadmap

## DONE (0.1.0)

Incident management; evidence; retrieval; triage; safety/quality investigation; risk; RCA; compliance mapping;
CAPA; human approval; workflow; dashboard API; audit; Docker; CI.

## DONE (0.2.0)

Next.js web app (dashboard, incident list, report incident, incident workspace, action queue, knowledge, audit);
notifications and two-level escalation of overdue actions; investigation reports; Alembic migrations; full
taxonomy coverage (11 safety + 9 quality classes); evaluation set with held-out split and red-team suite; dataset
registry and OSHA Severe Injury Reports pipeline; browser E2E tests; single image serving API + web app.

## IN PROGRESS — rebuilding PR #2 on main

Stage A (hardening, Azure IaC and deploy workflow, staging, operations) done. Next: B document parsing, embeddings,
hybrid retrieval and grounded answers; C reports in Word/PDF and email delivery; D vision, knowledge graph,
resumable workflows and conflicts; E web screens for these.

## NOW

Run the OSHA SIR pipeline on the real 2024-2026 file and publish the report; score the Claude provider on the gold
set; raise held-out class/domain accuracy to the 85% / 90% targets; Azure staging (Container Apps, PostgreSQL
Flexible Server, Blob Storage for evidence, Key Vault).

## NEXT

pgvector hybrid retrieval; vision (PPE and defect detection, licensed datasets only); Neo4j knowledge graph;
email/Teams notification adapters; OIDC (Entra ID) with httpOnly cookies; BLS CFOI and HSE benchmarks on the
dashboard; load tests.

## LATER

BIM/IFC; IoT; predictive risk; mobile/offline; digital site intelligence.

## NOT PLANNED FOR INITIAL MVP

Autonomous legal certification; autonomous critical safety authorization.
