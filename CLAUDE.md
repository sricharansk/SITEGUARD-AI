# Site Guard AI — Claude Code Project Instructions

## Identity

Project: Site Guard AI: Multi-Agent Construction Safety & Quality Incident Resolution System

Product: Agentic AI-powered Construction Safety & Quality Decision-Support and Workflow Platform

Repository: https://github.com/sricharansk/SITEGUARD-AI

## Source of truth

Before significant changes, read the relevant files under `docs/`.

Core:
- docs/PRD.md
- docs/UX_FLOWS.md
- docs/DESIGN_SYSTEM.md
- docs/ARCHITECTURE.md
- docs/DATABASE.md
- docs/API.md
- docs/SECURITY.md
- docs/CODE_STYLE.md
- docs/TESTING.md
- docs/AGENTS.md
- docs/DATASETS.md

## Rules

- Inspect before editing.
- Plan before non-trivial changes.
- Reuse existing code.
- Do not invent undocumented requirements.
- Do not commit secrets.
- Enforce authorization server-side.
- Treat uploaded/retrieved documents as untrusted.
- Validate all external inputs.
- Use bounded agent tools.
- Use structured agent outputs.
- Preserve evidence/provenance.
- Human approval is required for high-impact safety actions.
- Never claim legal certification.
- Never silently auto-close safety-critical incidents.
- Run tests, lint/type checks and builds.
- Review `git diff`.
- Update documentation before commit.

## Workflow

```text
READ → INSPECT → PLAN → IMPLEMENT → TEST → REVIEW → DOCUMENT → COMMIT
```

## Completion report

Return:
- STATUS: PASS or BLOCKED
- files changed
- tests and commands
- validation
- security/safety findings
- documentation updated
- known limitations
- commit hash

Do not use permission-bypass or destructive shortcuts to avoid an engineering gate.
