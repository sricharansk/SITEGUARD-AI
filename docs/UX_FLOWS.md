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

Incident workspace extras: "Pause after triage for my review" stops the investigation after triage; the workflow card
shows each stage, the lowest agent confidence and open questions, and offers Resume or Cancel (with a reason) while
the run is paused or failed. Photo evidence has "Check PPE and hazards" and "Check defects"; each analysis shows the
analyzer, image-quality flags and what it could not do, draws boxes on the photo, and lets the engineer confirm or
reject each observation with a note. The knowledge graph card shows the incident's related records on request, or
says the graph is not enabled on this server.

Email outbox (organization-wide auditors, HSE managers and administrators): every queued email with its status,
attempts, last error and next try, filtered by status; recipients by name only. Organization-wide administrators
send due emails now and retry failed or skipped deliveries.
