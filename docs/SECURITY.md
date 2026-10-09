# Security Guidelines

## Authentication

Prefer OIDC/OAuth2 and enterprise identity such as Microsoft Entra ID.

Implemented today: email + password (PBKDF2) issuing short-lived HS256 JWTs. Login is rate limited per client and
email (`SITEGUARD_LOGIN_RATE_LIMIT_PER_MINUTE`, default 10, in-process; use a shared store when running more than
one replica). Outside `local`/`test` the API refuses to start with the default or a JWT secret shorter than 32
characters.

## Authorization

Enforce RBAC and organization/project scope server-side.

## Roles

SUPER_ADMIN, ORG_ADMIN, PROJECT_MANAGER, HSE_MANAGER, SAFETY_ENGINEER, QA_QC_ENGINEER, SITE_ENGINEER, AUDITOR, VIEWER.

## Secrets

Never commit credentials. Use environment variables locally and managed secret storage in cloud.

Demo data uses a shared known password, so it seeds by default only in `local`, `test` and `demo` environments and
the API refuses to start with seeding on in `production`.

## HTTP headers

Every response carries `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`
and `Cache-Control: no-store` (API responses can hold incident data).

## AI Security

Retrieved documents are untrusted. Tool calls are allowlisted and validated. High-impact actions require human approval.

## File Uploads

Validate extension, MIME, size, checksum and content before processing.

## Logging

Do not log passwords, tokens, API keys or raw sensitive evidence by default.
