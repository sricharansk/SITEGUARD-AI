# Testing

Run: `make test` (or `cd backend && pytest -q`). Lint and types: `make lint`. CI runs both plus a Docker build and
an end-to-end smoke run of `scripts/demo_walkthrough.py` (`.github/workflows/ci.yml`).

## Implemented

| File | Covers |
|---|---|
| tests/test_risk.py | Every matrix cell, band boundaries, invalid inputs, determinism |
| tests/test_lifecycle.py | Allowed path, rejected shortcuts, CLOSED only from PENDING_VERIFICATION |
| tests/test_rag.py | Chunking, injection detection, ranking, tenant and project scoping |
| tests/test_agents.py | Triage fixtures (obvious, mixed, insufficient evidence, near miss), tool allowlist, budget, provider failure and invalid output fallback, invented citations removed, poisoned document not cited, Claude provider request shape and refusal fallback (mocked) |
| tests/test_migrations.py | Migrations produce exactly the model schema, pilot databases are stamped without data loss, downgrade to base and back |
| tests/test_api.py | Login rate limit, security headers, unsafe production settings refused, error envelope, login, validation, tenant isolation, RBAC, evidence validation, invalid transitions, full E2E incident -> investigation -> review -> work -> failed and passed verification -> closure -> audit, critical closure permission, agent failure with manual continuation, dashboard and search |

## Not yet implemented

Retrieval relevance and citation-coverage evaluation sets, LLM red-team suite against a live model, load tests,
frontend and browser E2E tests.

## Definition of Done

Tests, lint, type check and build pass for the affected scope.
