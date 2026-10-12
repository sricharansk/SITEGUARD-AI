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

Instruction-like text is flagged at ingestion in the document title, section heading and chunk text; flagged chunks
are never cited by agents and are excluded from knowledge answers. Content sent to Claude is JSON with `<` and `>`
escaped, so it cannot close the `<evidence_pack>` or `<sources>` tag around it. Grounded answers keep only
statements that cite a retrieved source and share its terms; a model's conflict claim is kept only when it names a
retrieved source (AGENTS.md).

## File Uploads

Validate extension, MIME, size, checksum and content before processing.

| Upload | Allowed | Checks |
|---|---|---|
| Incident evidence (`POST /incidents/{id}/evidence`) | jpg, png, pdf, txt | Extension, declared MIME, magic bytes, UTF-8 text, `SITEGUARD_EVIDENCE_MAX_BYTES` |
| Knowledge documents (`POST /documents/upload`) | pdf, docx, md, txt | Extension picks the parser; a declared MIME type must match it (or be `application/octet-stream`) and the stored type comes from the parser; the content must match the extension (`%PDF-`, zip header, UTF-8 text) before anything is stored; at most `SITEGUARD_DOCUMENT_MAX_BYTES` is read; DOCX rejected when it would expand past 100 MB, 100x its size or 5,000 entries; PDF and DOCX parsed in a child process with CPU-time, memory and wall-clock limits (`SITEGUARD_PARSER_TIMEOUT_SECONDS`, `SITEGUARD_PARSER_MEMORY_MB`) and at most 5 million characters of text |

Vision analysis (`POST /evidence/{id}/vision`) re-checks the stored file against its SHA-256 first (a mismatch is
refused and audited), then decodes JPEG/PNG only in a child process with CPU, memory and time limits
(`SITEGUARD_VISION_*`); the decoded format must match the evidence type and images above
`SITEGUARD_VISION_MAX_PIXELS` are refused as decompression bombs. Analyzers only see a re-encoded copy without
EXIF/GPS metadata; the original evidence is never modified. Text written in an image is untrusted content for the
vision model, and the analyzer's free-text notes are stored as labelled machine text and never passed to the agents.
Analyses are rate limited per user (`SITEGUARD_VISION_RATE_LIMIT_PER_MINUTE`). Child processes set their own memory
and CPU limits at startup (no `preexec_fn` in the threaded server), and at most four run at once per API process.

A document that cannot be parsed is kept as a `FAILED` document with a generic reason; a request that fails for any
other reason removes the stored file. Downloads are sent as attachments with the stored type and `nosniff`.

Organization-wide documents and the reindex job affect every project, so they need an organization-wide
membership with `MANAGE_DOCUMENTS`; a role limited to one project can only add documents to that project.

## Email

Email is off by default. With `smtp`, the job sends notification text (incident reference, action title, due date)
and a link that still requires sign-in; it never attaches evidence or reports. STARTTLS is required in staging and
production, the SMTP password is a secret (Key Vault in Azure), and `smtp` is refused in local and test so
development never emails real people. The `log` adapter records only the recipient's domain.

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

## Hardening (ported from PR #2)

- **Login throttle:** failed sign-ins are counted per (email, client) and per email in a 15-minute window
  (`SITEGUARD_LOGIN_MAX_FAILURES`, default 5; `SITEGUARD_LOGIN_MAX_FAILURES_PER_ACCOUNT`, default 20). Over the limit
  the API answers 429 `RATE_LIMITED` with `Retry-After`. Unknown emails count too, so throttling does not reveal which
  accounts exist. The counts are in-process: run one replica until a shared store exists.
- **Request body limit:** bodies larger than the biggest allowed upload (`max(SITEGUARD_DOCUMENT_MAX_BYTES,
  SITEGUARD_EVIDENCE_MAX_BYTES)` + 1 MB for form fields) get 413 `FILE_TOO_LARGE` before they are read, also for
  anonymous callers and chunked bodies, because multipart forms are spooled to disk before authentication runs.
  Set the same limit at any reverse proxy in front of the API.
- **Security headers** on every response: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, `Permissions-Policy`; `Cache-Control: no-store` on API responses;
  `Strict-Transport-Security` outside local and test. The web app at `/app` gets a Content-Security-Policy
  (`default-src 'self'`, `frame-ancestors 'none'`, `object-src 'none'`; `script-src` allows inline scripts because the
  Next.js static export bootstraps inline). `/docs` has no CSP because Swagger UI loads from a CDN.
- **Configuration validation:** the API refuses to start with unsafe settings for its environment (GOVERNANCE.md).
  Demo seeding (known passwords) defaults to on only for local, test and demo, and is refused in staging and
  production.
- **Supply chain:** runtime dependencies are pinned in `backend/requirements.lock` (used by Docker and CI) and dev
  tools in `pyproject.toml`; `scripts/dependency_audit.py` fails CI on known vulnerabilities in the lock file and on
  high or critical npm advisories in the web app's production dependencies, unless a reviewed, expiring exception is
  in `.github/dependency-audit-exceptions.toml`. It also runs weekly.
- **Deployment:** Azure secrets live in Key Vault and are read through a managed identity; GitHub deploys with OIDC
  (no stored cloud credentials) behind environment protection; PostgreSQL has no public endpoint (DEPLOYMENT.md).
- **Repository controls:** `.claude/` holds review agents, rules and permission settings for Claude Code sessions
  (deny reading `.env` and keys, deny force pushes and `rm -rf`, ask before `git push`, `az` and `alembic downgrade`).
