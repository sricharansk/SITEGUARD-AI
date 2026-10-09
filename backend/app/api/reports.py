from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import load_incident, ok
from app.core.db import get_db
from app.core.security import Principal, current_principal
from app.models import utcnow
from app.services import audit, reports

router = APIRouter(tags=["reports"])


@router.get("/incidents/{incident_id}/report")
def incident_report(
    incident_id: str,
    format: str = Query(default="md", pattern="^(md|docx|pdf|json)$"),
    include_ai: bool = Query(default=True, description="Include the labelled AI analysis section"),
    p: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
):
    """Incident report built only from stored records. Every generation is audited with the output's SHA-256."""
    inc = load_incident(db, p, incident_id)
    generated_at = utcnow()
    blocks = reports.build(db, inc, generated_at, include_ai=include_ai)
    rendered = reports.render(blocks, "md" if format == "json" else format)
    digest = reports.checksum(rendered)
    audit.record(
        db,
        organization_id=inc.organization_id,
        actor_id=p.id,
        action="report.generate",
        entity_type="incident",
        entity_id=inc.id,
        details={
            "format": format,
            "include_ai": include_ai,
            "sha256": digest,
            "generated_at": generated_at.isoformat(),
        },
    )
    db.commit()
    if format == "json":
        return ok({"generated_at": generated_at, "sha256": digest, "blocks": [b.__dict__ for b in blocks]})
    filename = f"{inc.reference}-report.{format}"
    return Response(
        rendered,
        media_type=reports.FORMATS[format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "X-Report-SHA256": digest},
    )
