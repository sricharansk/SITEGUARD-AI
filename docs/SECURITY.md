# Security Guidelines

Source: Blueprint Part 9. Each section says what is implemented today.

## Authentication

Target: OIDC/OAuth2, with Microsoft Entra ID as the enterprise option.

Implemented today: email + password (PBKDF2) issuing short-lived HS256 JWTs. Login is rate limited per client and
email (`SITEGUARD_LOGIN_RATE_LIMIT_PER_MINUTE`, default 10, in-process; use a shared store when running more than
one replica). Outside `local`/`test` the API refuses to start with the default or a JWT secret shorter than 32
characters.

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
| Secure secret handling | Environment variables; `.env` files git-ignored; Key Vault planned for Azure |
| TLS in transit | Provided by the hosting platform (Azure Container Apps ingress); not terminated by the app |
| Managed encryption at rest | Provided by managed PostgreSQL and Blob Storage once deployed |
| Secure file validation | Implemented (extension, declared type, magic bytes, size, SHA-256) |
| Rate limiting where appropriate | Login rate limited; other routes not yet |
| Safe error messages | Implemented (error envelope; unexpected errors return a generic message) |
| Audit logging | Implemented (`audit_events` with correlation IDs) |
| Dependency scanning | Not yet (Prompt 38) |
| Backup / restore | Not yet (managed PostgreSQL backups once deployed) |
| Access reviews | Not yet (process, Prompt 47) |

## Secrets

Never commit credentials. Use environment variables locally and managed secret storage in the cloud.

Demo data uses a shared known password, so it seeds by default only in `local`, `test` and `demo` environments, and
the API refuses to start with seeding on in `production`.

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

Vision analysis (`POST /evidence/{id}/vision`) re-checks the stored file against its SHA-256 first (a mismatch is
refused and audited), then decodes JPEG/PNG only in a child process with CPU, memory and time limits
(`SITEGUARD_VISION_*`); the decoded format must match the evidence type and images above
`SITEGUARD_VISION_MAX_PIXELS` are refused as decompression bombs. Analyzers only see a re-encoded copy without
EXIF/GPS metadata; the original evidence is never modified. Text written in an image is untrusted content for the
vision model, and the analyzer's free-text notes are stored as labelled machine text and never passed to the agents.
Analyses are rate limited per user (`SITEGUARD_VISION_RATE_LIMIT_PER_MINUTE`). Child processes set their own memory
and CPU limits at startup (no `preexec_fn` in the threaded server), and at most four run at once per API process.

A file that cannot be parsed is kept as a `FAILED` document with a generic reason; a request that fails for any
other reason removes the stored file. Downloads are sent as attachments with the stored type and `nosniff`.

Organization-wide documents and the reindex job affect every project, so they need an organization-wide
membership with `MANAGE_DOCUMENTS`; a role limited to one project can only add documents to that project.

## Logging

Do not log passwords, tokens, API keys, request bodies or raw sensitive evidence.
