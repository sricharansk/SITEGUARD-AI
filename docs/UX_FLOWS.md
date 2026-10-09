# UX Flows

Source: Blueprint Part 4. The API supports every flow below today; the web app that presents them is not built yet
(`docs/PROJECT_STATUS.md`, Prompts 02 and 31).

## Flow 1 — Onboarding

Open application → SSO/login → Organization → Project → Dashboard.

Today: email + password login (`POST /auth/login`); SSO is planned (OIDC / Entra ID).

## Flow 2 — Create Incident

Dashboard → New Incident → Incident metadata + description → Upload images/documents → Save → AI triage →
Incident workspace.

Today: triage runs when a user with `RUN_AGENTS` requests it (`POST /incidents/{id}/triage` or `/investigate`); it
is not queued automatically on save (open decision in `docs/DECISIONS.md`).

## Flow 3 — AI Investigation

Incident → Triage → Safety / Quality Investigation → Evidence Retrieval → Risk Rules → RCA → Compliance Evidence →
Decision-Support Packet → Human Review.

## Flow 4 — Corrective Action

Approved recommendation → CAPA → Owner → Due date → Work in progress → Evidence → Verification → Human verification
where required → Closure.

Escalation of overdue actions is planned (Prompt 24); today overdue actions are counted on the dashboard.

## Flow 5 — Critical Incident

Critical event → Immediate human escalation → Approved emergency/site procedure → Preserve evidence → AI decision
support → Human decision → Controlled workflow.

The platform must not replace emergency response procedures. Actions on HIGH or CRITICAL risk need an HSE manager's
approval, and closing a CRITICAL incident needs the same permission.

## AI unavailable

The manual workflow continues (manual transitions, human-authored actions, human risk assessment) and all evidence
is preserved.
