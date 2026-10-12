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

## Hardening (ported from PR #2)

- **Login throttle:** failed sign-ins are counted per (email, client) and per email in a 15-minute window
  (`SITEGUARD_LOGIN_MAX_FAILURES`, default 5; `SITEGUARD_LOGIN_MAX_FAILURES_PER_ACCOUNT`, default 20). Over the limit
  the API answers 429 `RATE_LIMITED` with `Retry-After`. Unknown emails count too, so throttling does not reveal which
  accounts exist. The counts are in-process: run one replica until a shared store exists.
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
