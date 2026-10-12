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
