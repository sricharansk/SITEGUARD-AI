# Governance

How Site Guard AI data, access, models, datasets and backups are governed before and after go-live (Playbook
Prompt 47). Each section says what the system enforces today and what the owner must decide. Where a number (a
retention period, a review interval) is a business or legal decision, it is listed as **owner decision** and not
invented here; the system keeps everything until the owner decides.

Related: [SECURITY.md](SECURITY.md) (controls), [DEPLOYMENT.md](DEPLOYMENT.md) (staging, Azure, rollback),
[DATASETS.md](DATASETS.md) and `data/dataset_registry.yaml` (dataset terms), [DECISIONS.md](DECISIONS.md) (open
decisions O1–O12).

## Data classification

| Class | What | Where | Handling |
|---|---|---|---|
| Restricted | Secrets: JWT signing key, database password, Anthropic API key, SMTP password, storage keys | Key Vault (Azure), a chmod 600 settings file outside the checkout (staging host) | Never in git, images, logs or command lines. Rotate on staff change or suspected exposure |
| Confidential, personal | User names and email addresses; incident descriptions, people involved, injury details; evidence files (photos, PDFs, notes); comments and verification notes | PostgreSQL; evidence directory (`SITEGUARD_EVIDENCE_DIR`, Azure Files in Azure); backups | Tenant-scoped on every query; TLS in transit; encrypted at rest by the platform; backups restricted like production |
| Confidential, business | Customer procedures, ITPs and method statements uploaded as knowledge documents; CAPA actions, approvals, audit events, agent runs; generated reports | PostgreSQL; evidence directory (original documents) | As above. Uploaded documents are untrusted input (SECURITY.md) |
| Internal | Application logs (JSON request logs with correlation IDs, no bodies), metrics, availability results | Container stdout, Log Analytics | No passwords, tokens, keys, request bodies or evidence content (OBSERVABILITY.md) |
| Public / synthetic | Demo seed data (`data/seed/`), docs, code | Git | Synthetic data is labelled synthetic wherever it is shown |

Staging holds no real incident data unless the owner approves it; if it does, staging is classified like production.
Demo seeding (known passwords) is refused in staging and production by the API itself (see
[Configuration validation](#configuration-validation)).

## Retention

Nothing is deleted automatically today: there is no delete endpoint for incidents, evidence, actions, approvals or
audit events, and no retention job. That keeps every safety record and its provenance, but it also means personal
data is kept indefinitely until the owner sets periods.

| Record | Today | Owner decision |
|---|---|---|
| Incidents, CAPA actions, approvals, verification records | Kept indefinitely | Retention per jurisdiction and contract (construction safety records often have statutory minimums) |
| Evidence files and original documents | Kept indefinitely (Azure Files share soft delete: `evidenceShareSoftDeleteDays`, default 14 days) | Retention, legal hold and malware scanning (open decision O6) |
| Audit events | Kept indefinitely, append-only from the application | See [Audit retention](#audit-retention) |
| Notifications and outbox rows | Kept indefinitely | Purge period for delivered and dead-lettered rows |
| Application logs (Log Analytics) | `logRetentionDays`, default 30 days | Period; export to archive storage if longer is required |
| PostgreSQL automated backups (Azure) | `postgresBackupRetentionDays`, default 7 days (7–35) | Period; geo-redundant backups for production |
| Logical backups (`scripts/backup.py`) | Kept where the operator stores them | Period and storage location |
| User accounts | Kept; no deactivation endpoint yet | Leaver process (see [Access review](#access-review)) |

A data-subject or customer deletion request needs a reviewed manual procedure until a retention feature exists;
deleting an incident would break its audit trail, so prefer redaction agreed with the owner.

## Access review

Access is role-based and scoped to an organization or project (SECURITY.md). Reviews are a process; the system
provides the data.

- **Who reviews:** the organization's ORG_ADMIN with the HSE manager, and the owner for SUPER_ADMIN and platform
  (Azure, GitHub) access. Interval: **owner decision** (quarterly is common for safety systems).
- **Application roles:** list memberships per organization and project (`memberships` table, or `GET /me` per user);
  confirm each person still needs the role, that APPROVE_CRITICAL holders (HSE_MANAGER, SUPER_ADMIN) are the
  intended people, and that clients and contractors only have project-scoped AUDITOR or VIEWER memberships (open
  decision O2). Record the review outcome outside the application until an admin UI exists.
- **Leavers:** remove memberships the same day. There is no account deactivation endpoint yet; until there is, an
  operator removes memberships in the database and rotates `SITEGUARD_JWT_SECRET` if the person held an admin role
  (tokens live `SITEGUARD_JWT_TTL_MINUTES`, default 8 hours).
- **Platform access:** Azure RBAC on the resource group, Key Vault and PostgreSQL admin; GitHub repository admins,
  environment reviewers and the OIDC deploy identity's role assignments (DEPLOYMENT.md#azure). The deploy identity
  holds only AcrPush, resource-group Reader, Contributor on the apps and jobs, and Managed Identity Operator on the
  apps' identity.
- **Evidence for auditors:** `audit_events` records sign-ins, approvals, rejections, closures and agent runs with
  correlation IDs.

## Incident response

For security incidents affecting Site Guard AI itself (not construction incidents, which are the product's subject).

1. **Detect.** Availability test failures, Log Analytics queries on 401/403/429 spikes or 5xx errors, the audit trail,
   dependency audit failures in CI, user reports.
2. **Contain.** Rotate the affected secret: a new `SITEGUARD_JWT_SECRET` invalidates every session; rotate the
   database password, Anthropic key or storage key in Key Vault and restart the apps (Container Apps read Key Vault
   references when a revision starts). Remove compromised memberships. Set `apiExternalIngress=false` if it was
   opened. Scale the web app to zero only with the owner's approval, since sites rely on it for safety reporting.
3. **Preserve evidence.** Do not delete logs or audit events. Take a `scripts/backup.py backup` and note the PostgreSQL
   point-in-time restore window before any repair.
4. **Eradicate and recover.** Fix, deploy through the normal workflow (CI must pass), or restore from backup into a
   new database ([Backup and restore](#backup-and-restore)) and switch the `database-url` secret.
5. **Notify.** The owner decides on notifying customers, data protection authorities and other parties; legal
   notification deadlines depend on jurisdiction (**owner decision**, record contacts here when set).
6. **Review.** Write a post-incident review: timeline, cause, what detection missed, actions with owners. Track the
   actions like any CAPA.

Severity, on-call contacts and response times are **owner decisions**.

## Model and provider governance

- **Default is offline.** `SITEGUARD_AI_PROVIDER=rules` runs the deterministic rules engine with no external calls.
  `anthropic` sends the evidence pack (incident text, evidence metadata, retrieved document chunks) to Anthropic's
  API; turning it on in staging or production is an owner decision covering data residency, the provider's data
  terms and customer consent.
- **Model version** is pinned by `SITEGUARD_ANTHROPIC_MODEL`; changing it is a configuration change that goes through
  staging and the AI evaluation (Prompt 40, not yet built).
- **Human control** does not depend on the provider: AI output is never an approved action, high and critical
  actions need APPROVE_CRITICAL, and no incident closes without verified actions (Decision 004). Every agent run
  stores its provider, status, tool-call trace and review reasons (`agent_runs`), and provider failure falls back to
  rules (Decision 008).
- **Untrusted input:** uploaded and retrieved documents can contain prompt injection; the controls are in
  SECURITY.md#agent-security and AGENTS.md.
- **Embeddings** use the offline hashing embedder; choosing a semantic model is open decision O5 (data residency).
- **No legal certification:** outputs cite requirements for review; they never certify compliance.

## Dataset licences

Only synthetic, project-owned data is in the repository. Public datasets are registered, not downloaded
(`data/dataset_registry.yaml`, Decision 014). A dataset enters the pipeline only with source, access date, version,
checksum, licence, commercial-use status and purpose recorded; commercial-use rights for production use are open
decision O11.

| Dataset | Publisher | Licence | Commercial use | Status |
|---|---|---|---|---|
| siteguard_synthetic_incidents | Site Guard AI project | project-owned | allowed | in repository |
| siteguard_synthetic_procedures | Site Guard AI project | project-owned | allowed | in repository |
| osha_ita_2025 | OSHA | see source terms | review required | registered |
| bls_cfoi_2024 | BLS | see source terms | review required | registered |
| hse_fatal_injuries_2025_26 | HSE (UK) | see source terms | review required | registered |
| hse_construction_statistics_2024_25 | HSE (UK) | see source terms | review required | registered |
| niosh_face | NIOSH | see publisher terms | review required | registered |
| dgfasli_srn_2024 | DGFASLI (India) | see source terms | review required | registered |
| mospi_plfs_2025 | MoSPI (India) | see source terms | review required | registered |
| constructionsite_10k | Chen/Zou | CC BY-NC 4.0 (dataset card) | not allowed without permission | registered |
| consynth_x | see dataset card | non-commercial / gated | not allowed without permission | registered |
| sh17 | see repository | CC BY-NC-SA 4.0 | not allowed without permission | registered |
| cubit_det_seg | see repository | CC BY 4.0 for CUBIT-Det; verify each component | review required | registered |
| concrete_crack_2025 | see article | verify repository licence | review required | registered |
| pagg_net_crack | see record | copyright, no blanket commercial licence | not allowed without permission | registered |
| soda_baseline | see source | verify terms | review required | registered |

The registry is the source of truth; `tests/test_dataset_registry.py` keeps these fields filled. Non-commercial
datasets are for research and evaluation only. Aggregate statistics are benchmarks, never facts about a person or
employer.

## Audit retention

- `audit_events` is written in the same transaction as the change it records (sign-in, incident changes, approvals,
  rejections, closures, agent runs, reports) with actor, organization, correlation ID and timestamp. The application
  has no update or delete path for it.
- The database owner role can still modify it. For production, run the application with a dedicated database role
  (DEPLOYMENT.md#azure) and keep the admin login for migrations and break-glass use.
- Audit events are kept indefinitely. The retention period, and whether to archive older events to immutable storage
  (for example Azure Blob Storage with a time-based retention policy), are **owner decisions**.
- Backups include the audit table; restoring an old backup does not remove the need to keep the newer audit events,
  so export them before a point-in-time restore replaces a database.

## Backup and restore

Two layers:

1. **Platform backups (Azure):** PostgreSQL Flexible Server automated backups with point-in-time restore
   (`postgresBackupRetentionDays`, optional geo-redundancy) and Azure Files share soft delete. The deploy workflow
   records a restore point before every migration.
2. **Logical backups (`scripts/backup.py`):** database and evidence together, with checksums, portable between
   hosts. Used for the staging host, before risky changes, and for the restore drill.

```bash
# Backup (database URL from the environment, never the command line)
export SITEGUARD_DATABASE_URL='postgresql+psycopg://...'
python scripts/backup.py backup --evidence-dir /srv/evidence --out /backups/$(date -u +%Y%m%dT%H%MZ)

# Restore into an EMPTY database and an empty evidence directory, then verify
export SITEGUARD_RESTORE_DATABASE_URL='postgresql+psycopg://.../siteguard_restore'
python scripts/backup.py restore --backup /backups/<stamp> --evidence-dir /srv/evidence-restored

# Check a live or restored deployment: every evidence and document file matches the SHA-256 in the database
python scripts/backup.py verify --evidence-dir /srv/evidence [--manifest /backups/<stamp>/manifest.json]
```

- The backup holds `database.dump` (pg_dump custom format), `evidence.tar.gz` and `manifest.json` (SHA-256 of both,
  per-file evidence hashes, row counts, Alembic revision). It is written with mode 0700/0600 and contains personal
  data: store it encrypted with access restricted like production.
- `restore` checks every checksum first, refuses a non-empty database or evidence directory (it never overwrites),
  restores in one transaction, extracts only the files listed in the manifest, and re-verifies hashes and row counts.
- The database is dumped before the evidence is archived; evidence files are written before their rows commit and
  never modified, so every row in the dump has its file.
- **Drill:** `backend/tests/test_backup_restore.py` creates data through the application (demo seed, evidence, an
  uploaded document), backs up, restores into a fresh database and directory, and checks row counts, evidence
  hashes, vector search on the copy, refusal to restore over data and detection of a tampered file. CI runs it in
  the `postgres` job. Run a manual restore drill against staging at an interval the owner sets (**owner
  decision**; after every schema change is a sensible minimum) and record the result.
- Recovery point and time objectives (RPO/RTO) are **owner decisions**; the defaults give a point-in-time restore
  window of 7 days in Azure.

## Configuration validation

The API refuses to start, listing every problem at once, when its settings are unsafe for `SITEGUARD_ENV`
(`settings_problems` in `backend/app/main.py`, tested in `backend/tests/test_config_validation.py`). The container
image defaults to `production`, so an unconfigured container never starts.

| Check | local, test | demo | staging, production |
|---|---|---|---|
| `SITEGUARD_ENV` is one of local, test, demo, staging, production | yes | yes | yes |
| JWT secret not the default and at least 32 characters | – | yes | yes |
| JWT secret without the `CHANGE` placeholder and with at least 10 distinct characters | – | – | yes |
| Demo seeding (known passwords) off | – | – | yes |
| Database is PostgreSQL | – | – | yes |
| CORS origins without `*`, all `https://` | – | – | yes |
| `SITEGUARD_PUBLIC_WEB_URL` uses `https://` | – | – | yes |
| No `CHANGE` placeholder in the database URL, public URL or CORS origins | – | – | yes |
| SMTP delivery refused | yes | – | – |

## Change management

Changes reach staging and production only through CI (lint, types, tests, PostgreSQL and restore drill, dependency
audit, image and compose smoke tests, Bicep and workflow checks) and the manual deploy workflow behind GitHub
environment protection. Production deployment, destructive migrations and force pushes need the owner's explicit
approval (open decision O12).
