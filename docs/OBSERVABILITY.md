# Observability

## Log

Structured application errors, auth events, important workflow events and agent status.

## Never log

Passwords, tokens, API keys and raw sensitive evidence by default.

## Metrics

API latency; error rate; retrieval latency; agent latency; token/cost metadata where permitted; queue depth; CAPA overdue rate; incident closure time.

## Correlation

Every request/agent workflow should expose correlation ID / run ID.
