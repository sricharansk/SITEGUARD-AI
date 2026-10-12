# Security Guidelines

## Authentication

Prefer OIDC/OAuth2 and enterprise identity such as Microsoft Entra ID.

## Authorization

Enforce RBAC and organization/project scope server-side.

## Roles

SUPER_ADMIN, ORG_ADMIN, PROJECT_MANAGER, HSE_MANAGER, SAFETY_ENGINEER, QA_QC_ENGINEER, SITE_ENGINEER, AUDITOR, VIEWER.

## Secrets

Never commit credentials. Use environment variables locally and managed secret storage in cloud.

## AI Security

Retrieved documents are untrusted. Tool calls are allowlisted and validated. High-impact actions require human approval.

## File Uploads

Validate extension, MIME, size, checksum and content before processing.

## Logging

Do not log passwords, tokens, API keys or raw sensitive evidence by default.

## Implemented in 0.2.0

- Injection detection scans the incident title, description, immediate actions and evidence descriptions as well as
  retrieved documents; detection flags the run for review, and containment does not depend on it (agents cannot
  approve, close or write anything but typed output). See the red-team results in EVALUATION.md.
- Web app: the pilot keeps the bearer token in `sessionStorage` (cleared when the tab closes) and the API enforces
  every permission; the UI only hides controls. Production should move to OIDC (Entra ID) with httpOnly cookies.
- Notifications are only readable by their recipient; `/projects/{id}/people` returns names and roles, not emails.
- Dataset pipelines never read employer or address fields and never rank employers (DATASETS.md).
- Frontend dependencies are pinned and `npm audit --omit=dev --audit-level=high` runs in CI.
