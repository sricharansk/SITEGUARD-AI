# Security Guidelines

Source: Blueprint Part 9. Each section says what is implemented today.

## Authentication

Target: OIDC/OAuth2, with Microsoft Entra ID as the enterprise option.

Implemented today: email + password (PBKDF2) issuing short-lived HS256 JWTs. Login is rate limited per client and
email (`SITEGUARD_LOGIN_RATE_LIMIT_PER_MINUTE`, default 10, in-process; use a shared store when running more than
one replica). Outside `local`/`test` the API refuses to start with the default or a JWT secret shorter than 32
characters; in `staging` and `production` it also refuses a secret containing the `CHANGE` placeholder or with fewer
than 10 distinct characters (full list in docs/GOVERNANCE.md#configuration-validation).

## Authorization

RBAC and organization/project scope are enforced on the server for every route
(`backend/app/core/security.py`). Queries resolve user → membership → organization → project → resource. A
resource in another tenant returns 404, so its existence is not revealed. The frontend never filters for security.

## Roles and permissions

| Role | Permissions |
|---|---|
| SUPER_ADMIN | All |
| ORG_ADMIN | All except APPROVE_CRITICAL |
| HSE_MANAGER | All except MANAGE_PROJECTS |
| PROJECT_MANAGER | Engineer set + APPROVE_CAPA, CLOSE_INCIDENT, MANAGE_PROJECTS |
| SAFETY_ENGINEER | Engineer set |
| QA_QC_ENGINEER | Engineer set + MANAGE_DOCUMENTS |
| SITE_ENGINEER | READ, CREATE_INCIDENT, EDIT_INCIDENT, UPDATE_CAPA_PROGRESS |
| AUDITOR | READ, VIEW_AUDIT |
| VIEWER | READ |

Engineer set: READ, CREATE_INCIDENT, EDIT_INCIDENT, RUN_AGENTS, PROPOSE_CAPA, UPDATE_CAPA_PROGRESS, VERIFY_CAPA.

Extra rules: actions on HIGH/CRITICAL risk need APPROVE_CRITICAL; the assignee of an action cannot verify it;
closing a CRITICAL incident needs APPROVE_CRITICAL.

## Security requirements (Blueprint) and status

| Requirement | Status |
|---|---|
| Tenant isolation | Implemented and tested |
| Least privilege | Implemented (role table above) |
| Secure secret handling | Environment variables; `.env`/`*.env` files git-ignored; placeholder-only templates; Key Vault references through a managed identity in the Azure templates (`deployment/azure/`, not yet deployed) |
| Safe configuration | API refuses unsafe settings per environment and the image defaults to `production` (docs/GOVERNANCE.md#configuration-validation) |
| TLS in transit | Provided by the hosting platform: HTTPS-only Container Apps ingress, PostgreSQL `sslmode=require`, HTTPS-only storage (Azure templates); a TLS reverse proxy for the staging host. Not terminated by the app |
| Managed encryption at rest | Provided by managed PostgreSQL and Azure Storage once deployed |
| Container images | Non-root (uid 10001), read-only code, digest-pinned bases, no secrets in layers, allowlisted build contexts (docs/DEPLOYMENT.md#images) |
| Network exposure (Azure) | PostgreSQL private (VNet only); API internal ingress; storage firewall limited to the apps subnet; registry admin user disabled |
| Secure file validation | Implemented (extension, declared type, magic bytes, size, SHA-256) |
| Rate limiting where appropriate | Login rate limited; other routes not yet |
| Safe error messages | Implemented (error envelope; unexpected errors return a generic message) |
| Audit logging | Implemented (`audit_events` with correlation IDs) |
| Dependency scanning | Implemented: CI `dependency-audit` job, on every push, pull request and weekly (see below) |
| Backup / restore | Implemented: `scripts/backup.py` with checksums and a CI restore drill; PostgreSQL point-in-time restore in Azure (docs/GOVERNANCE.md#backup-and-restore) |
| Access reviews | Process defined (docs/GOVERNANCE.md#access-review); no admin UI yet |
| Deployment credentials | GitHub OIDC federation, no stored cloud secrets; least-privilege roles; manual, environment-protected deploys |

## Dependency scanning

`scripts/dependency_audit.py` runs in the CI `dependency-audit` job:

- `pip-audit` on the exact pins in `backend/requirements.lock` (PyPI advisory data). Every known vulnerability
  fails, since pip-audit reports no severity.
- `npm audit --omit=dev --audit-level=high` on the web app's production dependencies: high and critical advisories
  fail. Development-only tools are not in the images.

A finding that cannot be fixed yet needs an entry in `.github/dependency-audit-exceptions.toml`, reviewed in a pull
request: advisory id, ecosystem, package, reason, reviewer, review date and an expiry at most 90 days after review.
Expired or incomplete entries fail the audit, and unused entries are reported. Fix a finding by bumping the pin
minimally and regenerating the lock (Decision 013). Container base images are pinned by digest and bumped by hand
(docs/DEPLOYMENT.md#images); image scanning is not yet in CI.

## Secrets

Never commit credentials. Use environment variables locally and managed secret storage in the cloud.

Demo data uses a shared known password, so it seeds by default only in `local`, `test` and `demo` environments, and
the API refuses to start with seeding on in `staging` or `production`.

## HTTP headers

Every response carries `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`
and `Cache-Control: no-store` (API responses can hold incident data).

## Web app session

The browser never holds the API token. The Next.js server (`frontend/`) stores it in the `sg_session` cookie
(httpOnly, SameSite=Lax, Secure in production, 8 hours) and attaches it when it forwards calls to the API
(DECISIONS 018). POST/PATCH/DELETE to the web app's server need an `Origin` that matches the host, or one listed in
`SITEGUARD_ALLOWED_ORIGINS`; other requests get 403 before the API is called. Only the API roots the app uses are
forwarded. Pages carry a Content-Security-Policy (`default-src 'self'`, `frame-ancestors 'none'`,
`object-src 'none'`), `X-Frame-Options: DENY` and `X-Content-Type-Options: nosniff`. Serve the web app over HTTPS.

## Agent security

Retrieved documents and uploaded files are untrusted content. A construction document must never be able to
override system instructions, authorize a tool its agent does not have, request secret access, or cause automatic
approval. Implemented controls: per-agent tool allowlists and budgets, untrusted-content framing for the model,
injection-pattern flagging at ingestion (document title, section heading and text), untrusted JSON blocks with `<`
and `>` escaped so content cannot close the `<evidence_pack>` or `<sources>` tag, citation and support checks, model
conflict claims kept only when they name a retrieved source, and no agent write access to approvals, risk scores or
closure (`docs/AGENTS.md`).

## Human approval

High-impact safety recommendations require a recorded evidence basis, recommendation, uncertainty, reviewer,
timestamp, decision, modification/reason and resulting action. Today these are stored across `capa_actions`
(recommendation, evidence refs, original AI output), the agent run output (confidence, open questions) and
`approval_events` (reviewer, decision, reason, before/after, timestamp).

## File uploads

Validate extension, MIME type, size, checksum and content before processing.

| Upload | Allowed | Checks |
|---|---|---|
| Incident evidence (`POST /incidents/{id}/evidence`) | jpg, png, pdf, txt | Extension, declared MIME, magic bytes, UTF-8 text, `SITEGUARD_EVIDENCE_MAX_BYTES` |
| Knowledge documents (`POST /documents/upload`) | pdf, docx, md, txt | Extension picks the parser; a declared MIME type must match it (or be `application/octet-stream`) and the stored type comes from the parser; at most `SITEGUARD_DOCUMENT_MAX_BYTES` is read; DOCX rejected when it would expand past 100 MB, 100x its size or 5,000 entries; PDF and DOCX parsed in a child process with CPU-time, memory and wall-clock limits (`SITEGUARD_PARSER_TIMEOUT_SECONDS`, `SITEGUARD_PARSER_MEMORY_MB`) and at most 5 million characters of text |

A file that cannot be parsed is kept as a `FAILED` document with a generic reason; a request that fails for any
other reason removes the stored file. Downloads are sent as attachments with the stored type and `nosniff`.

Organization-wide documents and the reindex job affect every project, so they need an organization-wide
membership with `MANAGE_DOCUMENTS`; a role limited to one project can only add documents to that project.

## Logging

Do not log passwords, tokens, API keys, request bodies or raw sensitive evidence.
