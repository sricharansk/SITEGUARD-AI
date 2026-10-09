from datetime import date

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import load_incident, load_project, ok
from app.api.schemas import AnswerIn, DocumentIn
from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import AppError, NotFound
from app.core.security import Permission, Principal, current_principal
from app.models import Document, Domain, Project
from app.services import answer as answer_service
from app.services import audit, embeddings, evidence, rag
from app.services.parsing import ParseError, parser_for

router = APIRouter(tags=["knowledge"])


def _doc(d: Document, duplicate: bool | None = None) -> dict:
    out = {
        "id": d.id,
        "organization_id": d.organization_id,
        "project_id": d.project_id,
        "scope": "project" if d.project_id else "organization",
        "title": d.title,
        "doc_type": d.doc_type,
        "source": d.source,
        "version": d.version,
        "effective_date": d.effective_date,
        "tags": d.tags or [],
        "domain": d.domain,
        "status": d.status,
        "error": d.error,
        "file_name": d.file_name,
        "content_type": d.content_type,
        "size_bytes": d.size_bytes,
        "page_count": d.page_count,
        "parser": d.parser,
        "chunks": len(d.chunks),
        "suspicious_chunks": sum(1 for c in d.chunks if c.suspicious),
        "sha256": d.sha256,
        "uploaded_by": d.uploaded_by,
        "processed_at": d.processed_at,
        "created_at": d.created_at,
    }
    if duplicate is not None:
        out["duplicate"] = duplicate
    return out


def _load_document(db: Session, p: Principal, document_id: str) -> Document:
    doc = db.get(Document, document_id)
    if doc is None:
        raise NotFound("Document not found")
    if doc.project_id:
        load_project(db, p, doc.project_id)
    else:
        p.require(Permission.READ, doc.organization_id)
    return doc


def _check_scope(db: Session, p: Principal, organization_id: str, project_id: str | None) -> None:
    if project_id:
        project = load_project(db, p, project_id, Permission.MANAGE_DOCUMENTS)
        if project.organization_id != organization_id:
            raise AppError("project_id does not belong to organization_id")
    else:
        p.require_org_wide(Permission.MANAGE_DOCUMENTS, organization_id)


def _audit_ingest(db: Session, p: Principal, doc: Document, duplicate: bool) -> None:
    audit.record(
        db,
        organization_id=doc.organization_id,
        actor_id=p.id,
        action="document.duplicate" if duplicate else "document.ingest",
        entity_type="document",
        entity_id=doc.id,
        details={
            "title": doc.title,
            "status": doc.status.value,
            "sha256": doc.sha256,
            "chunks": len(doc.chunks),
            "suspicious": sum(1 for c in doc.chunks if c.suspicious),
            "error": doc.error,
        },
    )


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
    """Ingest Markdown or plain text. The same content in the same scope returns the existing document."""
    _check_scope(db, p, body.organization_id, body.project_id)
    result = rag.ingest_bytes(
        db,
        organization_id=body.organization_id,
        project_id=body.project_id,
        filename="document.md",
        content=body.text.encode(),
        content_type="text/markdown",
        title=body.title,
        doc_type=body.doc_type,
        source=body.source,
        domain=body.domain,
        version=body.version,
        effective_date=body.effective_date,
        tags=body.tags,
        uploaded_by=p.id,
    )
    _audit_ingest(db, p, result.document, result.duplicate)
    db.commit()
    db.refresh(result.document)
    data = ok(_doc(result.document, result.duplicate))
    return JSONResponse(data, status_code=200) if result.duplicate else data


@router.post("/documents/upload", status_code=201)
def upload_document(
    file: UploadFile = File(...),
    organization_id: str = Form(...),
    title: str = Form(..., min_length=1, max_length=300),
    doc_type: str = Form(..., min_length=1, max_length=60),
    source: str = Form(..., min_length=1, max_length=500),
    domain: Domain = Form(Domain.BOTH),
    project_id: str | None = Form(None),
    version: str = Form("1", max_length=40),
    effective_date: date | None = Form(None),
    tags: str | None = Form(None, max_length=500, description="Comma-separated"),
    p: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    """Upload PDF, DOCX, Markdown or text. Unparseable files are kept as FAILED documents with the reason.

    A plain `def` route: FastAPI runs it in a worker thread, and PDF/DOCX parsing runs in a resource-limited child
    process, so a hostile file cannot block the event loop."""
    _check_scope(db, p, organization_id, project_id or None)
    s = get_settings()
    content = file.file.read(s.document_max_bytes + 1)  # never read more than the limit into memory
    name = evidence.safe_filename(file.filename or "")
    if not content:
        raise AppError("File is empty", "UNSUPPORTED_FILE")
    if len(content) > s.document_max_bytes:
        raise AppError(f"File exceeds {s.document_max_bytes} bytes", "FILE_TOO_LARGE", 413)
    try:
        parser = parser_for(name)
    except ParseError as exc:
        raise AppError(str(exc), "UNSUPPORTED_FILE") from exc
    declared = (file.content_type or "").split(";")[0].strip().lower()
    if declared and declared not in (*parser.content_types, "application/octet-stream"):
        raise AppError("Declared content type does not match the file extension", "UNSUPPORTED_FILE")
    key, _ = evidence.store(organization_id, "documents", content)
    try:
        result = rag.ingest_bytes(
            db,
            organization_id=organization_id,
            project_id=project_id or None,
            filename=name,
            content=content,
            content_type=parser.content_types[0],
            title=title,
            doc_type=doc_type,
            source=source,
            domain=domain,
            version=version,
            effective_date=effective_date,
            tags=[t.strip() for t in (tags or "").split(",") if t.strip()],
            uploaded_by=p.id,
            storage_key=key,
        )
        if result.duplicate:
            evidence.path_for(key).unlink(missing_ok=True)
        _audit_ingest(db, p, result.document, result.duplicate)
        db.commit()
    except Exception:
        db.rollback()
        evidence.path_for(key).unlink(missing_ok=True)  # no stored file without a document record
        raise
    db.refresh(result.document)
    data = ok(_doc(result.document, result.duplicate))
    return JSONResponse(data, status_code=200) if result.duplicate else data


@router.get("/documents/{document_id}")
def get_document(document_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    doc = _load_document(db, p, document_id)
    return ok(
        {
            **_doc(doc),
            "chunk_list": [
                {
                    "ref": f"chunk:{c.id}",
                    "ordinal": c.ordinal,
                    "section": c.section,
                    "page": c.page,
                    "suspicious": c.suspicious,
                    "text": c.text,
                }
                for c in doc.chunks
            ],
        }
    )


@router.get("/documents/{document_id}/download")
def download_document(document_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    doc = _load_document(db, p, document_id)
    if not doc.storage_key or not evidence.path_for(doc.storage_key).exists():
        raise NotFound("No original file is stored for this document")
    return FileResponse(
        evidence.path_for(doc.storage_key),
        media_type=doc.content_type or "application/octet-stream",
        filename=doc.file_name or "document",
    )


@router.post("/documents/reindex")
def reindex(organization_id: str = Query(), p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Batch embedding job: embeds chunks that have no current embedding. Idempotent."""
    p.require_org_wide(Permission.MANAGE_DOCUMENTS, organization_id)
    report = embeddings.index_pending(db, organization_id=organization_id)
    audit.record(
        db,
        organization_id=organization_id,
        actor_id=p.id,
        action="document.reindex",
        entity_type="organization",
        entity_id=organization_id,
        details=report.__dict__,
    )
    db.commit()
    return ok(report.__dict__)


@router.get("/search")
def search(
    q: str = Query(min_length=2, max_length=500),
    project_id: str = Query(),
    domain: Domain | None = None,
    limit: int = Query(default=5, ge=1, le=20),
    mode: str | None = Query(
        default=None, pattern="^(hybrid|lexical)$", description="Default: SITEGUARD_RETRIEVAL_MODE"
    ),
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
        mode=mode,
    )
    return ok([h.as_dict() for h in hits])


@router.post("/knowledge/answer")
def knowledge_answer(body: AnswerIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Grounded answer with citations, or an explicit insufficient/conflicting-evidence response."""
    project = load_project(db, p, body.project_id)
    incident = None
    if body.incident_id:
        incident = load_incident(db, p, body.incident_id)
        if incident.project_id != project.id:
            raise AppError("incident_id does not belong to project_id")
    result = answer_service.answer(
        db,
        organization_id=project.organization_id,
        project_id=project.id,
        question=body.question,
        incident=incident,
        domain=body.domain,
    )
    audit.record(
        db,
        organization_id=project.organization_id,
        actor_id=p.id,
        action="knowledge.answer",
        entity_type="incident" if incident else "project",
        entity_id=incident.id if incident else project.id,
        details={
            "question": body.question[:500],
            "status": result["status"],
            "citations": [c["ref"] for c in result["citations"]],
            "unsupported_claims": len(result["unsupported_claims"]),
            "provider": result["provider"],
        },
    )
    db.commit()
    return ok(result)
