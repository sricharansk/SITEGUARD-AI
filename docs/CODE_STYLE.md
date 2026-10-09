# Code Style & Conventions

Source: Blueprint Part 10.

## General

Small focused modules; typed request/response structures; descriptive names; domain-oriented folders; centralized
configuration (`app/core/config.py`); reusable services; explicit error classes (`app/core/errors.py`); structured
logs. Prefer existing patterns.

## Python (backend/)

- One toolchain: ruff (lint + format, line length 120), mypy, pytest. `make lint` and `make test`.
- Type hints everywhere; Pydantic models for every request body and agent output.
- Routes in `app/api/` stay thin; business rules in `app/services/`; agents in `app/agents/`.
- Raise `AppError` / `NotFound` / `Forbidden` / `Conflict` with a stable code; never return ad hoc error shapes.
- Responses use `ok(data)` so every endpoint returns the envelope.
- Schema changes ship with an Alembic revision.

## TypeScript (frontend/, when added)

ESLint and a formatter; strict TypeScript; component tests; feature-oriented structure.

## Never

Duplicate helpers; silently change API contracts; hard-code secrets; introduce unused dependencies; make unrelated
rewrites.
