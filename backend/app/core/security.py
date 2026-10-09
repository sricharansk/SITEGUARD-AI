"""Authentication (password + JWT for the pilot; OIDC/Entra ID later) and server-side RBAC."""

import enum
import hashlib
import hmac
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import AppError, Forbidden, NotFound
from app.models import Membership, Project, Role, User

_PBKDF2_ROUNDS = 240_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${_PBKDF2_ROUNDS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, rounds, salt, digest = stored.split("$")
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds))
    return hmac.compare_digest(candidate.hex(), digest)


def create_token(user_id: str) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {"sub": user_id, "iat": now, "exp": now + timedelta(minutes=s.jwt_ttl_minutes)}
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


class Permission(enum.StrEnum):
    READ = "READ"
    CREATE_INCIDENT = "CREATE_INCIDENT"
    EDIT_INCIDENT = "EDIT_INCIDENT"
    RUN_AGENTS = "RUN_AGENTS"
    PROPOSE_CAPA = "PROPOSE_CAPA"
    APPROVE_CAPA = "APPROVE_CAPA"
    APPROVE_CRITICAL = "APPROVE_CRITICAL"
    UPDATE_CAPA_PROGRESS = "UPDATE_CAPA_PROGRESS"
    VERIFY_CAPA = "VERIFY_CAPA"
    CLOSE_INCIDENT = "CLOSE_INCIDENT"
    MANAGE_DOCUMENTS = "MANAGE_DOCUMENTS"
    MANAGE_PROJECTS = "MANAGE_PROJECTS"
    VIEW_AUDIT = "VIEW_AUDIT"


_ALL = set(Permission)
_ENGINEER = {
    Permission.READ,
    Permission.CREATE_INCIDENT,
    Permission.EDIT_INCIDENT,
    Permission.RUN_AGENTS,
    Permission.PROPOSE_CAPA,
    Permission.UPDATE_CAPA_PROGRESS,
    Permission.VERIFY_CAPA,
}
ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.SUPER_ADMIN: _ALL,
    Role.ORG_ADMIN: _ALL - {Permission.APPROVE_CRITICAL},
    Role.HSE_MANAGER: _ALL - {Permission.MANAGE_PROJECTS},
    Role.PROJECT_MANAGER: _ENGINEER | {Permission.APPROVE_CAPA, Permission.CLOSE_INCIDENT, Permission.MANAGE_PROJECTS},
    Role.SAFETY_ENGINEER: _ENGINEER,
    Role.QA_QC_ENGINEER: _ENGINEER | {Permission.MANAGE_DOCUMENTS},
    Role.SITE_ENGINEER: {
        Permission.READ,
        Permission.CREATE_INCIDENT,
        Permission.EDIT_INCIDENT,
        Permission.UPDATE_CAPA_PROGRESS,
    },
    Role.AUDITOR: {Permission.READ, Permission.VIEW_AUDIT},
    Role.VIEWER: {Permission.READ},
}


@dataclass
class Principal:
    user: User
    memberships: list[Membership]

    @property
    def id(self) -> str:
        return self.user.id

    def org_ids(self) -> set[str]:
        return {m.organization_id for m in self.memberships}

    def _roles_for(self, organization_id: str, project_id: str | None) -> set[Role]:
        return {
            m.role
            for m in self.memberships
            if m.organization_id == organization_id
            and (m.project_id is None or project_id is None or m.project_id == project_id)
        }

    def permissions(self, organization_id: str, project_id: str | None = None) -> set[Permission]:
        perms: set[Permission] = set()
        for role in self._roles_for(organization_id, project_id):
            perms |= ROLE_PERMISSIONS[role]
        return perms

    def can(self, perm: Permission, organization_id: str, project_id: str | None = None) -> bool:
        return perm in self.permissions(organization_id, project_id)

    def require(self, perm: Permission, organization_id: str, project_id: str | None = None) -> None:
        if not self._roles_for(organization_id, project_id):
            # Do not reveal that a resource in another tenant exists.
            raise NotFound("Resource not found")
        if not self.can(perm, organization_id, project_id):
            raise Forbidden(f"Missing permission {perm.value}")

    def require_org_wide(self, perm: Permission, organization_id: str) -> None:
        """For changes that affect every project (organization documents, jobs); project-limited roles do not count."""
        org_roles = {m.role for m in self.memberships if m.organization_id == organization_id and m.project_id is None}
        if not any(m.organization_id == organization_id for m in self.memberships):
            raise NotFound("Resource not found")
        if not any(perm in ROLE_PERMISSIONS[r] for r in org_roles):
            raise Forbidden(f"Missing organization-wide permission {perm.value}")

    def visible_project_filter(self, db: Session) -> list[str]:
        ids: set[str] = set()
        for m in self.memberships:
            if m.project_id:
                ids.add(m.project_id)
            else:
                ids |= set(db.scalars(select(Project.id).where(Project.organization_id == m.organization_id)))
        return sorted(ids)


_bearer = HTTPBearer(auto_error=False)


def current_principal(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> Principal:
    if creds is None:
        raise AppError("Authentication required", "UNAUTHENTICATED", 401)
    try:
        payload = jwt.decode(creds.credentials, get_settings().jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise AppError("Invalid or expired token", "UNAUTHENTICATED", 401) from exc
    user = db.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise AppError("Invalid or expired token", "UNAUTHENTICATED", 401)
    request.state.user_id = user.id
    return Principal(user=user, memberships=list(user.memberships))
