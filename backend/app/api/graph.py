from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import load_incident, ok
from app.core.db import get_db
from app.core.security import Permission, Principal, current_principal
from app.services import audit
from app.services import graph as service

router = APIRouter(tags=["graph"])


@router.post("/graph/sync")
def sync_graph(
    organization_id: str = Query(min_length=1, max_length=36),
    p: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    """Rebuild the organization's knowledge graph from PostgreSQL (normally `python -m app.jobs graph-sync`)."""
    p.require_org_wide(Permission.MANAGE_PROJECTS, organization_id)
    store = service.get_store()
    result = service.sync(db, store, organization_id).as_dict()
    audit.record(
        db,
        organization_id=organization_id,
        actor_id=p.id,
        action="graph.sync",
        entity_type="organization",
        entity_id=organization_id,
        details=result,
    )
    db.commit()
    return ok(result)


@router.get("/incidents/{incident_id}/graph")
def incident_graph(
    incident_id: str,
    include_ai: bool = Query(default=True, description="Include AI-derived nodes and relationships"),
    p: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    """The incident's neighbourhood in the knowledge graph, with provenance on every node and relationship."""
    inc = load_incident(db, p, incident_id)
    store = service.get_store()
    return ok(service.incident_graph(store, inc, p.visible_project_filter(db), include_ai=include_ai))
