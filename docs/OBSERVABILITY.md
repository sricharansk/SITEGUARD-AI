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
dashboard exposes overdue/escalated actions and agent success/fallback counts.
