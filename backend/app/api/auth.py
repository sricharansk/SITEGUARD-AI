from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import ok
from app.api.schemas import LoginIn
from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import AppError
from app.core.ratelimit import RateLimiter
from app.core.security import Principal, create_token, current_principal, verify_password
from app.models import Organization, User
from app.services import audit

router = APIRouter(tags=["auth"])
login_limiter = RateLimiter(get_settings().login_rate_limit_per_minute)


@router.post("/auth/login")
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    client = request.client.host if request.client else "unknown"
    login_limiter.check(f"{client}:{body.email.lower()}")
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise AppError("Invalid email or password", "UNAUTHENTICATED", 401)
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
