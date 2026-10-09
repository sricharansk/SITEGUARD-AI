# Observability

## Logs

Target: structured application errors, authentication events, important workflow events and agent status.

Implemented: JSON logs per request (method, path, status, duration, correlation ID); authentication, workflow,
approval and agent events in `audit_events`; each agent run stores its provider, status, tool-call trace and
review reasons in `agent_runs`.

## Never log

Passwords, tokens, API keys, request bodies and raw sensitive evidence.

## Metrics

Target: API latency; error rate; retrieval latency; agent latency; token/cost metadata where permitted; queue
depth; CAPA overdue rate; incident closure time.

Implemented: the dashboard API reports CAPA overdue counts, mean days to close, and agent run, failure, fallback
and review counts. No metrics exporter or OpenTelemetry yet (Prompt 36).

## Correlation

Every response carries `X-Correlation-ID` (generated or taken from the request); the same ID is stored on audit
events, and agent runs share a `workflow_id`.
