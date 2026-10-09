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

## Web app

- The bearer token is kept in `sessionStorage` (cleared when the tab closes or on a 401). This is a pilot choice until
  OIDC/Entra ID with HttpOnly cookies replaces it; it is exposed to any XSS, so the app renders all API text as React
  text nodes and never uses `dangerouslySetInnerHTML` (incident text and agent output are untrusted).
- The UI hides actions the user lacks permission for, but this is convenience only. Every route re-checks RBAC and tenant
  scope on the server.
- Approve/reject requires a written reason, which is stored in the audit trail.
