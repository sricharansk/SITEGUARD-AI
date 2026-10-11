# Error Handling

## API

Every error uses the envelope in `docs/API.md` with a stable `code`, a safe `message` and the request's
`correlation_id`. Status codes: 400 validation; 401 authentication; 403 authorization; 404 not found (also for
resources in another tenant); 409 conflict (invalid state or transition, close blocked, a feature switched off in
this server's configuration such as the knowledge graph); 413 file too large; 429 rate limit; 500 unexpected error
(generic message; details only in server logs); 503 an optional backing store is unreachable (the Neo4j knowledge
graph; retry later).

Implemented in `backend/app/core/errors.py`; the knowledge graph's two errors are in `app/services/graph.py`.
Authorization always runs first, so a caller outside the incident's scope gets 404 even when the graph is disabled.

## Knowledge graph

The graph is a derived copy of PostgreSQL, so a graph failure never affects incidents, actions or approvals. With
`SITEGUARD_GRAPH_BACKEND=disabled` the graph endpoints answer 409 `GRAPH_DISABLED` and `python -m app.jobs
graph-sync` exits with an error. A Neo4j outage or error answers 503 `GRAPH_UNAVAILABLE`; the server log records only
the exception type. A sync runs in one Neo4j transaction, so a failed sync leaves the previous graph in place, and
the next successful sync converges it.

## AI

| Situation | Behaviour | Status |
|---|---|---|
| Provider timeout | The Claude client retries once (`max_retries=1`, `SITEGUARD_AGENT_TIMEOUT_SECONDS`), then falls back to rules | Implemented |
| Provider failure, refusal or invalid output | Rules provider answers; the run records `rules (fallback from anthropic)` | Implemented |
| Agent raises | Run recorded as FAILED; other agents continue; the incident and evidence are kept; manual workflow stays available | Implemented |
| Insufficient evidence | Do not guess: missing information and open questions are listed, low confidence or no citations flag the run for human review | Implemented |
| Agent conflict | Outputs are kept and flagged (for example reported vs triaged severity) for human review | Implemented for severity conflicts |

## UX

Long-running AI operations show their stage and status, never an unexplained spinner. Applies to the web app
(not built yet).
