"""Seed demo organizations, users, knowledge documents and synthetic incidents.

Incidents are driven through the real services (agents, review, progress, verification, closure) so the
dashboard and audit trail show genuine workflow data. Seeding always uses the offline rules provider.
"""

import os
from datetime import timedelta

import yaml
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents import orchestrator
from app.agents.framework import RulesProvider
from app.core.config import get_settings
from app.core.security import Principal, hash_password
from app.models import (
    CapaAction,
    Domain,
    Membership,
    Organization,
    Project,
    Role,
    Severity,
    Site,
    User,
    WorkStatus,
    utcnow,
)
from app.services import capa, incidents, rag


def _front_matter(text: str) -> tuple[dict, str]:
    if text.startswith("---"):
        _, meta, body = text.split("---", 2)
        return yaml.safe_load(meta) or {}, body.strip()
    return {}, text


def _principal(db: Session, email: str) -> Principal:
    user = db.scalar(select(User).where(User.email == email))
    assert user is not None
    return Principal(user=user, memberships=list(user.memberships))


def seed_if_empty(db: Session) -> bool:
    if db.scalar(select(func.count()).select_from(Organization)):
        return False
    seed(db)
    return True


def seed(db: Session) -> None:
    s = get_settings()
    password = os.environ.get("SITEGUARD_DEMO_PASSWORD", "siteguard-demo")
    config = yaml.safe_load((s.seed_dir / "users.yaml").read_text())
    knowledge = [
        _front_matter(p.read_text()) for p in sorted((s.seed_dir / "knowledge").glob("*.md")) if p.name != "README.md"
    ]
    demo_project: Project | None = None
    for org_cfg in config["organizations"]:
        org = Organization(name=org_cfg["name"])
        db.add(org)
        db.flush()
        pc = org_cfg["project"]
        project = Project(
            organization_id=org.id,
            code=pc["code"],
            name=pc["name"],
            client=pc.get("client"),
            location=pc.get("location"),
        )
        db.add(project)
        db.flush()
        for site in pc.get("sites", []):
            db.add(Site(project_id=project.id, name=site))
        for u in org_cfg["users"]:
            user = User(email=u["email"], full_name=u["name"], password_hash=hash_password(password))
            db.add(user)
            db.flush()
            db.add(Membership(user_id=user.id, organization_id=org.id, role=Role(u["role"])))
        for meta, body in knowledge:
            rag.ingest(
                db,
                organization_id=org.id,
                title=meta["title"],
                text=body,
                doc_type=meta["doc_type"],
                source=meta["source"],
                domain=Domain(meta.get("domain", "BOTH")),
                version=str(meta.get("version", "1")),
            )
        if demo_project is None:
            demo_project = project
    db.flush()
    assert demo_project is not None
    db.refresh(demo_project)
    _seed_incidents(db, demo_project)
    db.commit()


def _seed_incidents(db: Session, project: Project) -> None:
    s = get_settings()
    rows = yaml.safe_load((s.seed_dir / "incidents.yaml").read_text())
    sites = {site.name: site.id for site in project.sites}
    hse = _principal(db, "hse@demo.siteguard.local")
    site_eng = _principal(db, "site@demo.siteguard.local")
    verifiers = {
        "SAFETY": _principal(db, "safety@demo.siteguard.local"),
        "QUALITY": _principal(db, "qa@demo.siteguard.local"),
    }
    reporter = site_eng
    for row in sorted(rows, key=lambda r: -r["days_ago"]):
        occurred = utcnow() - timedelta(days=row["days_ago"], hours=3)
        inc = incidents.create(
            db,
            organization_id=project.organization_id,
            project_id=project.id,
            reporter_id=reporter.id,
            is_synthetic=True,
            data={
                "title": row["title"],
                "description": row["description"],
                "domain": Domain(row["domain"]),
                "severity": Severity(row["severity"]),
                "occurred_at": occurred,
                "site_id": sites.get(row["site"]),
                "location": row.get("location"),
                "activity": row.get("activity"),
                "people_involved": row.get("people_involved", 0),
                "immediate_actions": row.get("immediate_actions"),
            },
        )
        inc.reported_at = occurred + timedelta(hours=2)
        stage = row["stage"]
        if stage == "reported":
            continue
        orchestrator.run_investigation(db, inc, hse.id, provider=RulesProvider())
        if stage == "investigated":
            continue
        actions = list(
            db.scalars(
                select(CapaAction).where(
                    CapaAction.incident_id == inc.id, CapaAction.approval_status == "PENDING_REVIEW"
                )
            )
        )
        for a in actions:
            a.assignee_id = site_eng.id
            capa.review(db, hse, inc, a, "APPROVE", "Reviewed against site conditions; proportionate.", None)
        if stage == "in_progress":
            if actions:
                capa.update_progress(db, site_eng, inc, actions[0], WorkStatus.IN_PROGRESS, None, "Started")
            continue
        verifier = verifiers["QUALITY" if row["domain"] == "QUALITY" else "SAFETY"]
        for a in actions:
            capa.update_progress(db, site_eng, inc, a, WorkStatus.COMPLETED, None, "Done; photos attached")
            capa.verify(db, verifier, inc, a, True, "Checked on site; control in place and working.", None)
        capa.close_incident(db, hse, inc, "All actions verified effective. Lessons shared at toolbox talk.")
        inc.closed_at = inc.reported_at + timedelta(days=max(1, row["days_ago"] // 2))
