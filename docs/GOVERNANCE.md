# Governance

How Site Guard AI data, access, models, datasets and backups are governed before and after go-live (Playbook
Prompt 47; adapted from PR #2). Each section says what the system enforces today and what the owner must decide.
Where a number (a retention period, a review interval) is a business or legal decision, it is listed as **owner
decision** and not invented here; the system keeps everything until the owner decides.

Related: [SECURITY.md](SECURITY.md) (controls), [DEPLOYMENT.md](DEPLOYMENT.md) (staging, Azure, rollback),
[DATASETS.md](DATASETS.md) and `data/dataset_registry.yaml` (dataset terms).

## Data classification

| Class | What | Where | Handling |
|---|---|---|---|
| Restricted | Secrets: JWT signing key, database password, Anthropic API key, storage keys | Key Vault (Azure), a chmod 600 settings file outside the checkout (staging host) | Never in git, images, logs or command lines. Rotate on staff change or suspected exposure |
| Confidential, personal | User names and emails; incident descriptions, people involved, injury details; evidence files; verification notes | PostgreSQL; evidence directory (`SITEGUARD_EVIDENCE_DIR`, Azure Files in Azure); backups | Tenant-scoped on every query; TLS in transit; encrypted at rest by the platform; backups restricted like production |
| Confidential, business | Customer procedures, ITPs, method statements; CAPA actions, approvals, audit events, agent runs; reports | PostgreSQL | As above. Documents are untrusted input (SECURITY.md) |
| Internal | Application logs (JSON request logs with correlation IDs, no bodies), availability results | Container stdout, Log Analytics | No passwords, tokens, keys, request bodies or evidence content |
| Public / synthetic | Demo seed data (`data/seed/`), evaluation set (`data/eval/`), docs, code | Git | Synthetic data is labelled synthetic wherever it is shown |

Staging holds no real incident data unless the owner approves it; if it does, staging is classified like production.
Demo seeding (known passwords) is refused in staging and production by the API itself.

## Retention

Nothing is deleted automatically: there is no delete endpoint for incidents, evidence, actions, approvals or audit
events, and no retention job. That keeps every safety record and its provenance, but personal data is kept until the
owner sets periods.

| Record | Today | Owner decision |
|---|---|---|
| Incidents, CAPA actions, approvals, verification records | Kept indefinitely | Retention per jurisdiction and contract (safety records often have statutory minimums) |
| Evidence files | Kept indefinitely (Azure Files share soft delete, default 14 days) | Retention, legal hold, malware scanning |
| Audit events | Kept indefinitely, append-only from the application | See [Audit retention](#audit-retention) |
| Notifications and email deliveries | Kept indefinitely | Purge period for read notifications and sent deliveries |
| Application logs (Log Analytics) | `logRetentionDays`, default 30 days | Period; archive if longer is required |
| PostgreSQL automated backups (Azure) | `postgresBackupRetentionDays`, default 7 days (7–35) | Period; geo-redundant backups for production |
| Logical backups (`scripts/backup.py`) | Kept where the operator stores them | Period and storage location |

A data-subject or customer deletion request needs a reviewed manual procedure until a retention feature exists;
deleting an incident would break its audit trail, so prefer redaction agreed with the owner.

## Access review

- **Who reviews:** the organization's ORG_ADMIN with the HSE manager, and the owner for SUPER_ADMIN and platform
  (Azure, GitHub) access. Interval: **owner decision** (quarterly is common for safety systems).
- **Application roles:** review memberships per organization and project; confirm APPROVE_CRITICAL holders
  (HSE_MANAGER, SUPER_ADMIN) are the intended people and that clients and contractors only have project-scoped
  AUDITOR or VIEWER memberships.
- **Leavers:** remove memberships the same day. There is no deactivation endpoint yet; an operator removes
  memberships in the database and rotates `SITEGUARD_JWT_SECRET` if the person held an admin role (tokens live
  `SITEGUARD_JWT_TTL_MINUTES`, default 8 hours).
- **Platform access:** Azure RBAC on the resource group, Key Vault and PostgreSQL admin; GitHub admins, environment
  reviewers and the OIDC deploy identity, which holds only AcrPush, resource-group Reader, Contributor on the app and
  jobs, and Managed Identity Operator on the app identity (DEPLOYMENT.md#azure).

## Incident response

For security incidents affecting Site Guard AI itself (not construction incidents, which are the product's subject).

1. **Detect.** Availability test failures, 401/403/429 spikes or 5xx errors in Log Analytics, the audit trail,
   dependency audit failures in CI, user reports.
2. **Contain.** Rotate the affected secret in Key Vault and restart the app (a new `SITEGUARD_JWT_SECRET` ends every
   session). Remove compromised memberships.
3. **Preserve evidence.** Do not delete logs or audit events. Take a `scripts/backup.py backup` and note the
   PostgreSQL point-in-time restore window before any repair.
4. **Eradicate and recover.** Fix and deploy through the normal workflow (CI must pass), or restore into a new
   database ([Backup and restore](#backup-and-restore)) and switch the `database-url` secret.
5. **Notify.** The owner decides on notifying customers, authorities and other parties; deadlines depend on
   jurisdiction (**owner decision**).
6. **Review.** Timeline, cause, what detection missed, actions with owners, tracked like any CAPA.

## Model and provider governance

- **Default is offline.** `SITEGUARD_AI_PROVIDER=rules` makes no external calls. `anthropic` sends the evidence pack
  (incident text, evidence metadata, retrieved chunks) to Anthropic's API; turning it on in staging or production is
  an owner decision covering data residency, provider terms and customer consent.
- **Model version** is pinned by `SITEGUARD_ANTHROPIC_MODEL`; changing it goes through staging and
  `python -m app.evaluation` (EVALUATION.md).
- **Human control** does not depend on the provider: AI output is never an approved action, high and critical
  actions need APPROVE_CRITICAL, and no incident closes without verified actions.
- **Vision** (`SITEGUARD_VISION_PROVIDER=anthropic`) sends a re-encoded copy of photo evidence (no EXIF/GPS metadata)
  to Anthropic; photos can show people's faces, so turning it on is an owner decision like the AI provider. The default
  `baseline` analyzer sends nothing anywhere.
- **Email** (`SITEGUARD_NOTIFICATION_EMAIL_ADAPTER=smtp`) sends notification text to people's mailboxes through the
  SMTP provider; turning it on is an owner decision like the AI provider. The outbox lists recipients by name only.
- **No legal certification:** outputs cite requirements for review; they never certify compliance.

## Dataset licences

Only synthetic, project-owned data is in the repository. Public datasets are registered with licence and allowed use
in `data/dataset_registry.yaml` (DATASETS.md); non-commercial datasets are for research and evaluation only.
Aggregate statistics are benchmarks, never facts about a person or employer.

## Audit retention

- `audit_events` is written in the same transaction as the change it records, with actor, organization,
  correlation ID and timestamp. The application has no update or delete path for it.
- The database owner role can still modify it. For production, run the application with a dedicated database role
  (DEPLOYMENT.md#azure) and keep the admin login for migrations and break-glass use.
- Retention and archiving to immutable storage are **owner decisions**. Export newer audit events before a
  point-in-time restore replaces a database.

## Backup and restore

1. **Platform backups (Azure):** PostgreSQL Flexible Server automated backups with point-in-time restore, and Azure
   Files share soft delete. The deploy workflow records a restore point before every migration.
2. **Logical backups (`scripts/backup.py`):** database and evidence together, with checksums. Procedure and drill:
   DEPLOYMENT.md#backup-and-restore. Backups contain personal data: store them encrypted with access restricted like
   production. RPO/RTO and the drill interval are **owner decisions**.

## Configuration validation

The API refuses to start, listing every problem at once, when its settings are unsafe for `SITEGUARD_ENV`
(`settings_problems` in `backend/app/main.py`, tested in `backend/tests/test_config_validation.py`).

| Check | local, test | demo | staging, production |
|---|---|---|---|
| `SITEGUARD_ENV` is one of local, test, demo, staging, production | yes | yes | yes |
| JWT secret not the default and at least 32 characters | – | yes | yes |
| JWT secret without the `CHANGE` placeholder and with at least 10 distinct characters | – | – | yes |
| Demo seeding (known passwords) off | – | – | yes |
| Database is PostgreSQL | – | – | yes |
| CORS origins without `*`, all `https://` | – | – | yes |
| `SITEGUARD_PUBLIC_WEB_URL` uses `https://` | – | – | yes |
| Email adapter is not `smtp` | yes | – | – |
| SMTP uses STARTTLS when `smtp` is chosen | – | – | yes |
| No `CHANGE` placeholder in the database URL, public URL, CORS origins or SMTP sender | – | – | yes |

## Change management

Changes reach staging and production only through CI (lint, types, tests, PostgreSQL migrations and restore drill,
dependency audit, image smoke and browser tests, Bicep and workflow checks) and the manual deploy workflow behind
GitHub environment protection. Production deployment, destructive migrations and force pushes need the owner's
explicit approval.
