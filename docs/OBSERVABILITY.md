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

## Health and availability

- API `GET /health`; web app `GET /api/health` returns 200 with `"api": "ok"` or `"unreachable"`. Both images
  declare Docker health checks on them, and the compose stacks wait for them.
- Azure templates (`deployment/azure/`, not yet deployed): startup, liveness and readiness probes on both apps;
  container logs (the API's JSON request logs, web app and jobs) go to Log Analytics (`logRetentionDays`, default
  30); an Application Insights standard availability test calls `<web URL>/api/health` every 5 minutes from three
  regions, requires `"api":"ok"` and checks the TLS certificate (14 days' notice). Alert rules on it are an owner
  step (docs/DEPLOYMENT.md#azure). There is no telemetry SDK, so Application Insights holds availability results only.
- `scripts/smoke_test.py` checks a deployment end to end after every rollout (docs/DEPLOYMENT.md#smoke-test).

## Correlation

Every response carries `X-Correlation-ID` (generated or taken from the request); the same ID is stored on audit
events, and agent runs share a `workflow_id`.
