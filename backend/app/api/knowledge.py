from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import load_project, ok
from app.api.schemas import DocumentIn
from app.core.db import get_db
from app.core.errors import AppError
from app.core.security import Permission, Principal, current_principal
from app.models import Document, Domain, Project
from app.services import audit, rag

router = APIRouter(tags=["knowledge"])


def _doc(d: Document) -> dict:
    return {
        "id": d.id,
        "title": d.title,
        "doc_type": d.doc_type,
        "source": d.source,
        "version": d.version,
        "domain": d.domain,
        "project_id": d.project_id,
        "chunks": len(d.chunks),
        "suspicious_chunks": sum(1 for c in d.chunks if c.suspicious),
        "sha256": d.sha256,
    }


@router.get("/documents")
def list_documents(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    projects = p.visible_project_filter(db)
    rows = db.scalars(
        select(Document)
        .where(
            Document.organization_id.in_(p.org_ids()),
            or_(Document.project_id.is_(None), Document.project_id.in_(projects)),
        )
        .order_by(Document.title)
    )
    return ok([_doc(d) for d in rows])


@router.post("/documents", status_code=201)
def add_document(body: DocumentIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    if body.project_id:
        project = load_project(db, p, body.project_id, Permission.MANAGE_DOCUMENTS)
        if project.organization_id != body.organization_id:
            raise AppError("project_id does not belong to organization_id")
    else:
        p.require(Permission.MANAGE_DOCUMENTS, body.organization_id)
    doc = rag.ingest(
        db,
        organization_id=body.organization_id,
        project_id=body.project_id,
        title=body.title,
        text=body.text,
        doc_type=body.doc_type,
        source=body.source,
        domain=body.domain,
        version=body.version,
    )
    audit.record(
        db,
        organization_id=body.organization_id,
        actor_id=p.id,
        action="document.ingest",
        entity_type="document",
        entity_id=doc.id,
        details={
            "title": doc.title,
            "chunks": len(doc.chunks),
            "suspicious": sum(1 for c in doc.chunks if c.suspicious),
        },
    )
    db.commit()
    db.refresh(doc)
    return ok(_doc(doc))


@router.get("/search")
def search(
    q: str = Query(min_length=2, max_length=500),
    project_id: str = Query(),
    domain: Domain | None = None,
    limit: int = Query(default=5, ge=1, le=20),
    p: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    project: Project = load_project(db, p, project_id)
    hits = rag.search(
        db,
        organization_id=project.organization_id,
        project_id=project.id,
        query=q,
        domain=domain,
        limit=limit,
    )
    return ok([h.as_dict() for h in hits])
