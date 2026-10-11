# UX Flows

Source: Blueprint Part 4. The API supports every flow below; the web app (`frontend/`) presents them. What exists
and what is next is in `docs/PROJECT_STATUS.md`.

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

Overdue actions are counted on the dashboard and escalated by the scheduled notification job (`POST
/notifications/run` or `python -m app.jobs all`): the assignee (or, with none, the approvers) is notified, and
actions still overdue later escalate to the HSE managers (`APPROVE_CRITICAL`). Every notification is in-app; an email
delivery is queued for each and sent only when external delivery is turned on.

## Flow 5 — Critical Incident

Critical event → Immediate human escalation → Approved emergency/site procedure → Preserve evidence → AI decision
support → Human decision → Controlled workflow.

The platform must not replace emergency response procedures. Actions on HIGH or CRITICAL risk need an HSE manager's
approval, and closing a CRITICAL incident needs the same permission.

## Flow 6 — Ask the documents

Knowledge → Ask a question → Grounded answer (AI decision support, needs human review) → Check the cited sources
(document title, version, page, section) → Act through the incident workflow.

The answer says "Insufficient evidence" when the documents the user can read do not answer the question, and
"Conflicting evidence" when sources disagree; statements no source supports are removed and shown only as removed
text. Search shows every hit's version, page, section and scope. Users with `MANAGE_DOCUMENTS` upload PDF, Word,
Markdown or text files; the page shows the processing status (Ready, or Failed with the reason) the API returns.
Organization-wide documents need an organization-wide role.

## Flow 7 — Notifications

Workflow event (critical or high incident reported, actions to review, assignment, verification, escalation) → bell
in the header shows the unread count → Notifications → Open incident → Mark as read (or Mark all as read).

Organization-wide auditors, HSE managers and administrators also see the email delivery outbox for the selected
project's organization; organization-wide project managers and administrators can retry a FAILED (dead letter) or
SKIPPED delivery. In-app notifications always arrive, whatever happens to email.

## Flow 8 — Incident report

Incident workspace → Report → Format (PDF, Word, Markdown) → Include the AI analysis (labelled AI-GENERATED) or not →
Download report → The page shows the file name and the SHA-256 recorded in the audit log, so the file can be matched
to its audit event.

## Flow 9 — Dashboard

Dashboard → Filters (period of occurrence with presets or From/To in UTC, trend by month or ISO week, this project or
all the user's projects) → Apply filters → Totals, response and closure trends and breakdowns for the incidents that
occurred in that period. An inverted or invalid range is refused before it is sent, and again by the API.

## AI unavailable

The manual workflow continues (manual transitions, human-authored actions, human risk assessment) and all evidence
is preserved.
