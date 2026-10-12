# Testing

Run: `make test` (or `cd backend && pytest -q`, 88 tests). Lint and types: `make lint`. CI runs backend lint, types and
tests; frontend typecheck, build and dependency audit; then builds the Docker image, runs the browser tests against
it and resolves every open incident with `scripts/resolve_all.py` (`.github/workflows/ci.yml`).

## Implemented

| File | Covers |
|---|---|
| tests/test_risk.py | Every matrix cell, band boundaries, invalid inputs, determinism |
| tests/test_lifecycle.py | Allowed path, rejected shortcuts, CLOSED only from PENDING_VERIFICATION |
| tests/test_rag.py | Chunking, injection detection, ranking, tenant and project scoping |
| tests/test_agents.py | Triage fixtures (obvious, mixed, insufficient evidence, near miss), tool allowlist, budget, provider failure and invalid output fallback, invented citations removed, poisoned document not cited, Claude provider request shape and refusal fallback (mocked) |
| tests/test_api.py | Error envelope, login, validation, tenant isolation, RBAC, evidence validation, invalid transitions, full E2E incident -> investigation -> review -> work -> failed and passed verification -> closure -> audit, critical closure permission, agent failure with manual continuation, dashboard and search |

| tests/test_notifications.py | Review/assignment/failed-verification notifications, two-level overdue escalation and its idempotency, endpoint permissions |
| tests/test_evaluation.py | Runs the gold-set evaluation and red-team suite: no CRITICAL case under-rated, workflow invariants, 100% red-team containment, accuracy regression floors, every taxonomy class labelled |
| tests/test_migrations.py | Alembic migrations build exactly the schema in `models.py`, and downgrade |
| tests/test_datasets.py | OSHA SIR pipeline on a synthetic fixture: column validation, construction filter, dedupe, date filter, OIICS mapping, no employer data in outputs; dataset registry completeness |
| frontend/e2e/workflow.spec.ts | Browser: report -> AI investigation -> PM blocked from critical approval -> HSE approval -> work -> independent verification -> closure; dashboard, lists, action queue, knowledge, audit; cross-tenant URL returns NOT_FOUND |

## Evaluation

`make eval` (or `cd backend && python -m app.evaluation --out ../docs/EVALUATION.md`) scores the agents on
`data/eval/incidents_gold.yaml` (24 dev + 24 held-out test cases, synthetic, covering all 20 classes) and runs the
10-case red-team suite. Results: [EVALUATION.md](EVALUATION.md). The rules were tuned once on dev errors only; the
test split is the headline number.

## Browser tests

```bash
make web && make run            # or: make up (Docker)
cd frontend && npx playwright install chromium
E2E_BASE_URL=http://localhost:8000 npx playwright test   # SCREENSHOT_DIR=../docs/screenshots to refresh images
```

## Not yet implemented

Load tests; scoring the Claude provider on the gold set in CI (needs an API key); red-team prompts against a live
model; real-data evaluation (blocked in the build sandbox, see DATASETS.md).

## Definition of Done

Tests, lint, type check and build pass for the affected scope.
