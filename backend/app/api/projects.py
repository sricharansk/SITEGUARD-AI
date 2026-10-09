from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api import serializers as ser
from app.api.deps import load_project, ok
from app.api.schemas import ProjectIn
from app.core.db import get_db
from app.core.security import Permission, Principal, current_principal
from app.models import Membership, Project, Site, User
from app.services import audit

router = APIRouter(tags=["projects"])


@router.get("/projects")
def list_projects(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    ids = p.visible_project_filter(db)
    rows: list[Project] = (
        list(db.scalars(select(Project).where(Project.id.in_(ids)).order_by(Project.name))) if ids else []
    )
    return ok([_with_permissions(p, x) for x in rows])


def _with_permissions(p: Principal, project: Project) -> dict:
    """The caller's effective permissions, so clients can hide actions the server would refuse anyway."""
    return {**ser.project(project), "permissions": sorted(p.permissions(project.organization_id, project.id))}


@router.post("/projects", status_code=201)
def create_project(body: ProjectIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    p.require(Permission.MANAGE_PROJECTS, body.organization_id)
    project = Project(
        organization_id=body.organization_id,
        code=body.code,
        name=body.name,
        client=body.client,
        location=body.location,
    )
    db.add(project)
    db.flush()
    for name in body.sites:
        db.add(Site(project_id=project.id, name=name))
    audit.record(
        db,
        organization_id=project.organization_id,
        actor_id=p.id,
        action="project.create",
        entity_type="project",
        entity_id=project.id,
        details={"name": project.name},
    )
    db.commit()
    db.refresh(project)
    return ok(ser.project(project))


@router.get("/projects/{project_id}")
def get_project(project_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    return ok(_with_permissions(p, load_project(db, p, project_id)))


@router.get("/projects/{project_id}/members")
def list_members(project_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Active people with a role on this project (organization-wide or project-specific), for assignment."""
    project = load_project(db, p, project_id)
    rows = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.organization_id == project.organization_id,
            or_(Membership.project_id.is_(None), Membership.project_id == project.id),
            User.is_active.is_(True),
        )
        .order_by(User.full_name)
    )
    return ok(
        [
            {
                "user_id": u.id,
                "full_name": u.full_name,
                "email": u.email,
                "role": m.role,
                "scope": "organization" if m.project_id is None else "project",
            }
            for m, u in rows
        ]
    )
