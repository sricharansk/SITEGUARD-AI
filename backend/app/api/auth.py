from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import ok
from app.api.schemas import LoginIn
from app.core.db import get_db
from app.core.errors import AppError
from app.core.hardening import login_throttle
from app.core.security import Principal, create_token, current_principal, verify_password
from app.models import Organization, User
from app.services import audit

router = APIRouter(tags=["auth"])


class ThrottledError(AppError):
    status_code = 429
    code = "RATE_LIMITED"

    def __init__(self, retry_after: int):
        super().__init__(f"Too many failed sign-in attempts. Try again in {retry_after} seconds.")
        self.retry_after = retry_after


@router.post("/auth/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    email = body.email.lower()
    client = request.client.host if request.client else "unknown"
    wait = login_throttle.retry_after(email, client)
    if wait:
        raise ThrottledError(wait)
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        login_throttle.failed(email, client)  # unknown emails count too, so throttling does not reveal accounts
        raise AppError("Invalid email or password", "UNAUTHENTICATED", 401)
    login_throttle.succeeded(email, client)
    for org_id in {m.organization_id for m in user.memberships}:
        audit.record(
            db,
            organization_id=org_id,
            actor_id=user.id,
            action="auth.login",
            entity_type="user",
            entity_id=user.id,
        )
    db.commit()
    return ok({"access_token": create_token(user.id), "token_type": "bearer"})


@router.get("/me")
def me(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    memberships = []
    for m in p.memberships:
        org = db.get(Organization, m.organization_id)
        memberships.append(
            {
                "organization_id": m.organization_id,
                "organization": org.name if org else None,
                "project_id": m.project_id,
                "role": m.role,
                "permissions": sorted(p.permissions(m.organization_id, m.project_id)),
            }
        )
    return ok({"id": p.user.id, "email": p.user.email, "full_name": p.user.full_name, "memberships": memberships})
