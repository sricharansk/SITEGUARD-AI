from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Incident, IncidentEvent, IncidentStatus, utcnow
from app.services import audit


def next_reference(db: Session) -> str:
    year = utcnow().year
    prefix = f"SG-{year}-"
    count = db.scalar(select(func.count()).select_from(Incident).where(Incident.reference.like(f"{prefix}%"))) or 0
    return f"{prefix}{count + 1:04d}"


def create(
    db: Session,
    *,
    organization_id: str,
    project_id: str,
    reporter_id: str,
    data: dict,
    is_synthetic: bool = False,
) -> Incident:
    inc = Incident(
        reference=next_reference(db),
        organization_id=organization_id,
        project_id=project_id,
        reporter_id=reporter_id,
        status=IncidentStatus.REPORTED,
        is_synthetic=is_synthetic,
        **data,
    )
    db.add(inc)
    db.flush()
    db.add(
        IncidentEvent(
            incident_id=inc.id,
            actor_id=reporter_id,
            from_status=None,
            to_status=IncidentStatus.REPORTED.value,
            note="Incident reported",
        )
    )
    audit.record(
        db,
        organization_id=organization_id,
        actor_id=reporter_id,
        action="incident.create",
        entity_type="incident",
        entity_id=inc.id,
        details={"reference": inc.reference, "severity": inc.severity.value, "domain": inc.domain.value},
    )
    return inc
