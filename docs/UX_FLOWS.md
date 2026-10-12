# UX Flows

## Login

Login/SSO → Organization → Project → Dashboard.

## Incident

New Incident → Metadata → Evidence → Save → Triage → Incident Workspace.

## Investigation

Triage → Safety/Quality → RAG → Risk → RCA → Compliance → Decision Support → Human Review.

## Resolution

Approval → CAPA → Assign → Track → Escalate → Verification → Close.

## AI unavailable

Allow manual incident workflow to continue and preserve all evidence.

## As built (0.2.0)

Login -> Dashboard -> Report incident (+ evidence) -> Incident workspace -> Run AI investigation (RUN_AGENTS) ->
review each proposal (APPROVE / MODIFY / REJECT with reason; critical ones only by the HSE manager) -> Mark
completed (assignee) -> Verify (someone else; failed verification sends it back) -> Close (blockers listed until
allowed). Overdue actions: dashboard "Escalate overdue actions" or the daily job; notifications in the header.

Knowledge: Ask a question -> grounded answer with citations (document, version, section, page) or a plain
"insufficient" or "conflicting evidence" answer -> open the cited document to read the passage. Search shows each
passage with its provenance and scores. People with MANAGE_DOCUMENTS add documents (PDF, Word, Markdown, text) for
their project, or for the whole organization when they hold an organization-wide role; the result says how many
passages were indexed, that the file is a duplicate, or why it could not be read.
