"""Incident reports (Prompt 34): correct record data, approval history, citations, labelled AI, authorization."""

import io
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.models import AgentRun, AuditEvent, CapaAction, Document, DocumentChunk
from app.services import reports
from tests.conftest import auth
from tests.test_api import PNG

SNAPSHOT = Path(__file__).parent / "snapshots" / "incident_report.md"


def _closed_incident(client, project_id, db) -> dict:
    """A human-driven incident with evidence, a cited action, a review, a failed and a passed verification."""
    hse, site, safety = auth(client, "hse"), auth(client, "site"), auth(client, "safety")
    inc = client.post(
        f"/projects/{project_id}/incidents",
        json={
            "title": "Report fixture: unguarded floor opening",
            "description": "A floor opening on level 4 was found without a cover or barrier during the morning walk.",
            "domain": "SAFETY",
            "severity": "MEDIUM",
            "occurred_at": "2026-09-01T07:30:00+00:00",
            "location": "Level 4, grid C3",
            "activity": "Services installation",
            "immediate_actions": "Opening covered and marked.",
        },
        headers=site,
    ).json()["data"]
    iid = inc["id"]
    ev = client.post(
        f"/incidents/{iid}/evidence",
        files={"file": ("opening.png", PNG, "image/png")},
        data={"description": "Opening before it was covered"},
        headers=site,
    ).json()["data"]
    chunk = db.execute(
        select(DocumentChunk.id)
        .join(Document)
        .where(Document.title.like("Working at Height%"), Document.organization_id == inc["organization_id"])
        .order_by(DocumentChunk.ordinal)
    ).first()[0]
    db.add(
        AgentRun(
            incident_id=iid,
            workflow_id="report-fixture",
            agent="triage",
            provider="rules",
            status="SUCCEEDED",
            output={
                "confidence": 0.7,
                "evidence_refs": [f"evidence:{ev['id']}", f"chunk:{chunk}"],
                "open_questions": ["Who removed the cover?"],
                "incident_class": "Fall through opening",
                "domain": "SAFETY",
                "severity_candidate": "HIGH",
                "priority": "P2",
                "hazards": ["Fall from height"],
                "missing_information": [],
                "recommended_next_agents": ["safety"],
                "rationale": "Unprotected opening at height.",
            },
            trace=[],
            needs_human_review=True,
            triggered_by=client.get("/me", headers=hse).json()["data"]["id"],
        )
    )
    db.commit()
    site_id = client.get("/me", headers=site).json()["data"]["id"]
    action = client.post(
        f"/incidents/{iid}/capa",
        json={
            "action_type": "CORRECTIVE",
            "title": "Fix covers to all floor openings",
            "description": "Screw-fixed covers marked HOLE.",
            "assignee_id": site_id,
            "due_date": "2026-09-10",
            "verification_criteria": "Walkdown finds every opening covered",
        },
        headers=safety,
    ).json()["data"]
    row = db.get(CapaAction, action["id"])
    row.evidence_refs = [f"chunk:{chunk}"]
    db.commit()
    client.post(f"/incidents/{iid}/transition", json={"to_status": "TRIAGED", "note": "Triaged"}, headers=hse)
    client.post(f"/incidents/{iid}/transition", json={"to_status": "UNDER_INVESTIGATION", "note": "Start"}, headers=hse)
    client.post(f"/incidents/{iid}/transition", json={"to_status": "PENDING_APPROVAL", "note": "Review"}, headers=hse)
    r = client.post(
        f"/capa/{action['id']}/review", json={"decision": "APPROVE", "reason": "Proportionate"}, headers=hse
    )
    assert r.status_code == 200, r.text
    client.patch(f"/capa/{action['id']}/progress", json={"work_status": "COMPLETED"}, headers=site)
    client.post(f"/capa/{action['id']}/verify", json={"effective": False, "notes": "Two covers loose"}, headers=hse)
    client.patch(f"/capa/{action['id']}/progress", json={"work_status": "COMPLETED"}, headers=site)
    client.post(f"/capa/{action['id']}/verify", json={"effective": True, "notes": "All covers fixed"}, headers=hse)
    r = client.post(f"/incidents/{iid}/close", json={"note": "Verified"}, headers=hse)
    assert r.status_code == 200, r.text
    return inc


def _normalise(text: str) -> str:
    text = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "<id>", text)
    text = re.sub(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC", "<time>", text)
    text = re.sub(r"SG-\d{4}-\d{4}", "<ref>", text)
    return re.sub(r"\b[0-9a-f]{16}\.\.\.", "<sha>...", text)


def test_report_content_matches_records_and_snapshot(client, project_id, db):
    inc = _closed_incident(client, project_id, db)
    blocks = reports.build(db, _incident(db, inc["id"]), datetime(2026, 9, 20, 12, 0, tzinfo=UTC))
    md = reports.to_markdown(blocks)
    for expected in (
        inc["reference"],
        "| Status | CLOSED |",
        "Opening covered and marked.",
        "opening.png",
        "| Fix covers to all floor openings | CORRECTIVE | Human | APPROVED | VERIFIED |",
        "| APPROVE | Hana Safety (HSE Manager) | Proportionate |",
        "| no | Hana Safety (HSE Manager) | Two covers loose |",
        "| yes | Hana Safety (HSE Manager) | All covers fixed |",
        "> **AI-GENERATED** [triage agent, provider rules",
        "Open questions: Who removed the cover?",
        "Working at Height Procedure (HSE-PRO-004) (version",
        "Nothing in this report is a legal or regulatory compliance determination",
    ):
        assert expected in md, expected
    normalised = _normalise(md)
    if os.environ.get("UPDATE_SNAPSHOTS") or not SNAPSHOT.exists():
        SNAPSHOT.write_text(normalised)
    assert normalised == SNAPSHOT.read_text(), "report layout changed; rerun with UPDATE_SNAPSHOTS=1 if intended"


def _incident(db, incident_id):
    from app.models import Incident

    return db.get(Incident, incident_id)


def test_report_formats_and_audit(client, project_id, db):
    inc = _closed_incident(client, project_id, db)
    url = f"/incidents/{inc['id']}/report"
    md = client.get(url, headers=auth(client, "auditor"))
    assert md.status_code == 200 and md.headers["content-type"].startswith("text/markdown")
    assert f'filename="{inc["reference"]}-report.md"' in md.headers["content-disposition"]
    digest = md.headers["x-report-sha256"]
    assert digest == reports.checksum(md.content)
    event = db.scalars(
        select(AuditEvent).where(AuditEvent.action == "report.generate", AuditEvent.entity_id == inc["id"])
    ).first()
    assert event is not None and event.details["sha256"] == digest and event.details["format"] == "md"

    from docx import Document as Docx
    from pypdf import PdfReader

    docx = client.get(url, params={"format": "docx"}, headers=auth(client, "hse"))
    text = "\n".join(p.text for p in Docx(io.BytesIO(docx.content)).paragraphs)
    assert inc["reference"] in text and "AI-GENERATED" in text
    pdf = client.get(url, params={"format": "pdf"}, headers=auth(client, "hse"))
    assert pdf.content.startswith(b"%PDF-")
    pdf_text = "".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf.content)).pages)
    assert inc["reference"] in pdf_text and "AI-GENERATED" in pdf_text
    data = client.get(url, params={"format": "json", "include_ai": "false"}, headers=auth(client, "hse")).json()["data"]
    assert not any(b["kind"] == "ai" for b in data["blocks"]) and data["sha256"]


def test_report_validation_and_authorization(client, project_id, db):
    inc = _closed_incident(client, project_id, db)
    url = f"/incidents/{inc['id']}/report"
    assert client.get(url, params={"format": "html"}, headers=auth(client, "hse")).status_code == 400
    assert client.get(url, headers=auth(client, "other")).status_code == 404
    assert client.get(url).status_code == 401
    assert client.get("/incidents/missing/report", headers=auth(client, "hse")).status_code == 404
