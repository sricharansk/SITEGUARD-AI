from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.core.security import Permission, Principal
from app.models import CapaAction, Incident, Project


def ok(data: Any) -> dict:
    return {"data": jsonable_encoder(data), "error": None}


def load_project(db: Session, p: Principal, project_id: str, perm: Permission = Permission.READ) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise NotFound("Project not found")
    p.require(perm, project.organization_id, project.id)
    return project


def load_incident(db: Session, p: Principal, incident_id: str, perm: Permission = Permission.READ) -> Incident:
    inc = db.get(Incident, incident_id)
    if inc is None:
        raise NotFound("Incident not found")
    p.require(perm, inc.organization_id, inc.project_id)
    return inc


def load_capa(db: Session, p: Principal, capa_id: str) -> tuple[CapaAction, Incident]:
    action = db.get(CapaAction, capa_id)
    if action is None:
        raise NotFound("Action not found")
    inc = load_incident(db, p, action.incident_id)
    return action, inc
