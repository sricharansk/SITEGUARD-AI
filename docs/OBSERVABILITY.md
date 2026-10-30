# Observability

## Log

Structured application errors, auth events, important workflow events and agent status.

## Never log

Passwords, tokens, API keys and raw sensitive evidence by default.

## Metrics

API latency; error rate; retrieval latency; agent latency; token/cost metadata where permitted; queue depth; CAPA overdue rate; incident closure time.

## Correlation

Every request/agent workflow should expose correlation ID / run ID.

## Implemented

JSON request logs with correlation ID, method, path, status and latency (no bodies); correlation ID on every
response, error envelope and audit event; agent runs store provider, trace, tool timings and review reasons;
dashboard exposes overdue/escalated actions and agent success/fallback counts. `GET /health` is liveness (the
process answers) and `GET /ready` is readiness (the database answers and its schema is at the latest migration;
503 `NOT_READY` otherwise, with only booleans in the body and the error type in the log). The Azure readiness probe
uses `/ready`, so a container is taken out of rotation, not restarted, while the database is unreachable.
