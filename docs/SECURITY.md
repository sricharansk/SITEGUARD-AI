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
