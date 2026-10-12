# Error Handling

## API

400 validation; 401 authentication; 403 authorization; 404 not found; 409 conflict (including `GRAPH_DISABLED` when
the knowledge graph is off); 413 file too large; 429 rate limit; 500 unexpected error; 503 `GRAPH_UNAVAILABLE` when
the optional Neo4j store cannot be reached (retry later).

The knowledge graph is a derived copy of PostgreSQL, so a graph failure never affects incidents, actions or
approvals. A sync runs in one Neo4j transaction: a failed sync leaves the previous graph in place, and the next
successful sync converges it. Authorization runs first, so a caller outside the incident's scope gets 404 even when
the graph is disabled.

## AI

Provider timeout → retry if safe.
Provider failure → preserve incident and allow manual workflow.
Insufficient evidence → do not guess.
Agent conflict → preserve outputs and request human review.

## UX

All long-running AI operations show stage/status, not an unexplained spinner.
