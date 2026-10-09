---
paths:
  - "backend/tests/**"
  - "frontend/**/*.test.*"
  - "evals/**"
---

# Testing rules

- Backend: `make lint` (ruff, ruff format, mypy) and `make test` (pytest) must pass before commit.
- Web app: `npm run lint`, `npm run typecheck`, `npm run test` and `npm run build` in `frontend/` must pass.
- Every new endpoint gets a success test, a validation failure test and an authorization or tenant-isolation test.
- Agent changes need fixtures for the expected case, insufficient evidence, provider failure and a poisoned
  document.
- Never skip, disable or loosen a test to get green. Fix the cause.
- Tests use the rules provider and SQLite; never call a live model or external service from the default suite.
