# Repository rules

- Workflow for every non-trivial change: READ → INSPECT → PLAN → IMPLEMENT → TEST → REVIEW → DOCUMENT → COMMIT.
- Read the relevant `docs/` files first; `docs/PROJECT_STATUS.md` says what exists and what is next.
- Backend: `backend/app/` (FastAPI). `api/` holds routes only; business rules live in `services/`; agents in `agents/`.
- Web app: `frontend/` (Next.js, TypeScript, Tailwind). The browser never decides authorization; it renders what
  the API allows.
- Every response uses the envelope `{"data": ..., "error": ...}`; errors carry `code`, `message`, `correlation_id`.
- Out-of-scope resources return 404, not 403.
- Schema changes need an Alembic revision (`make revision m="..."`) committed with the model change.
- Update `docs/` (API, DATABASE, DECISIONS, CHANGELOG, PROJECT_STATUS) in the same commit as the code.
- Never commit secrets, `.env`, databases, evidence files or proxy certificates.
- Production deployment, destructive migrations and force pushes need the owner's explicit approval.
