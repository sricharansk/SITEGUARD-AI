"""Investigation report (Markdown). Every AI section is labelled as AI-generated and every human decision names
the person, so the report keeps the provenance the workspace has."""

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import (
    AgentRun,
    ApprovalEvent,
    AuditEvent,
    CapaAction,
    Evidence,
    Incident,
    IncidentEvent,
    Project,
    RiskAssessment,
    User,
    VerificationRecord,
    utcnow,
)
from app.services import capa as capa_service

DISCLAIMER = (
    "Site Guard AI is decision support. AI-generated sections are recommendations that were reviewed by the named "
    "people; nothing in this report is a legal compliance determination or certification."
)


def _cell(value: object) -> str:
    return str(value if value is not None else "").replace("|", "/").replace("\n", " ")


def _table(head: list[str], rows: list[list]) -> list[str]:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(_cell(c) for c in r) + " |" for r in rows]
    return out + [""]


def build(db: Session, inc: Incident) -> str:
    names = {u.id: u.full_name for u in db.scalars(select(User))}
    project = db.get(Project, inc.project_id)
    runs = list(db.scalars(select(AgentRun).where(AgentRun.incident_id == inc.id).order_by(AgentRun.started_at)))
    latest = runs[-1].workflow_id if runs else None
    runs = [r for r in runs if r.workflow_id == latest]
    by_agent = {r.agent: r for r in runs}
    risk = db.scalar(
        select(RiskAssessment)
        .where(RiskAssessment.incident_id == inc.id)
        .order_by(desc(RiskAssessment.created_at))
        .limit(1)
    )
    actions = list(
        db.scalars(select(CapaAction).where(CapaAction.incident_id == inc.id).order_by(CapaAction.created_at))
    )
    ids = [a.id for a in actions]
    approvals = list(db.scalars(select(ApprovalEvent).where(ApprovalEvent.capa_id.in_(ids)))) if ids else []
    verifs = list(db.scalars(select(VerificationRecord).where(VerificationRecord.capa_id.in_(ids)))) if ids else []
    decision = {a.capa_id: a for a in approvals}
    evidence = list(db.scalars(select(Evidence).where(Evidence.incident_id == inc.id).order_by(Evidence.created_at)))
    history = list(
        db.scalars(select(IncidentEvent).where(IncidentEvent.incident_id == inc.id).order_by(IncidentEvent.created_at))
    )
    audit_count = len(list(db.scalars(select(AuditEvent.id).where(AuditEvent.entity_id.in_([inc.id, *ids])))))

    md = [
        f"# Investigation report {inc.reference}: {inc.title}",
        "",
        f"Project: {project.name if project else ''} ({project.code if project else ''}). "
        f"Status: **{inc.status.value}**. Generated {utcnow():%Y-%m-%d %H:%M} UTC.",
        "",
        f"> {DISCLAIMER}",
        "",
    ]
    if inc.is_synthetic:
        md += ["_This incident is synthetic demo data._", ""]
    md += ["## 1. Incident", ""]
    md += _table(
        ["Field", "Value"],
        [
            ["Domain / reported severity", f"{inc.domain.value} / {inc.severity.value}"],
            ["Occurred", inc.occurred_at.isoformat()[:16]],
            ["Location", inc.location],
            ["Activity", inc.activity],
            ["People involved", inc.people_involved],
            ["Reported by", names.get(inc.reporter_id)],
            ["Immediate actions", inc.immediate_actions],
        ],
    )
    md += [inc.description, ""]
    md += ["## 2. Evidence", ""]
    md += (
        _table(
            ["File", "Type", "SHA-256", "Description"],
            [[e.filename, e.content_type, e.sha256[:16] + "...", e.description] for e in evidence],
        )
        if evidence
        else ["No evidence files attached.", ""]
    )

    md += ["## 3. AI investigation (AI-generated, reviewed by people)", ""]
    if not runs:
        md += ["No AI investigation was run.", ""]
    else:
        md += _table(
            ["Agent", "Provider", "Status", "Confidence", "Flagged for review"],
            [
                [
                    r.agent,
                    r.provider,
                    r.status,
                    (r.output or {}).get("confidence", ""),
                    "yes" if r.needs_human_review else "no",
                ]
                for r in runs
            ],
        )
    tri = (by_agent.get("triage") and by_agent["triage"].output) or {}
    if tri:
        md += [
            f"**Triage:** {tri['incident_class']}; domain {tri['domain']}; AI severity {tri['severity_candidate']}; "
            f"priority {tri['priority']}. Hazards/defects: {', '.join(tri['hazards'])}.",
            "",
        ]
    for name, label in (("safety", "Safety investigation"), ("quality", "Quality investigation")):
        out = (by_agent.get(name) and by_agent[name].output) or {}
        if not out:
            continue
        md += [f"**{label}:** {out.get('summary', '')}", ""]
        if name == "safety":
            md += [
                f"- Unsafe acts: {'; '.join(out['unsafe_acts'])}",
                f"- Unsafe conditions: {'; '.join(out['unsafe_conditions'])}",
                f"- Failed or missing controls: {'; '.join(out['failed_or_missing_controls'])}",
                "",
            ]
        else:
            md += [
                f"- Defects: {'; '.join(out['defects'])}",
                f"- Probable stage: {out['probable_stage']}",
                f"- Recommended tests: {'; '.join(out['recommended_tests'])}",
                "",
            ]
    if risk:
        md += [
            f"**Risk ({'human assessment' if risk.inputs_source == 'HUMAN' else 'AI-suggested inputs'}):** "
            f"{risk.rationale}",
            "",
        ]
    rca = (by_agent.get("rca") and by_agent["rca"].output) or {}
    if rca:
        md += ["**Root cause hypotheses (5-Whys):**", ""]
        md += [f"{i}. {w}" for i, w in enumerate(rca["whys"], 1)] + [""]
        md += _table(
            ["Category", "Hypothesis", "Confidence"],
            [[c["category"], c["statement"], c["confidence"]] for c in rca["root_causes"]],
        )
    comp = (by_agent.get("compliance") and by_agent["compliance"].output) or {}
    if comp:
        md += ["**Requirements mapped from retrieved documents (cited):**", ""]
        md += (
            _table(
                ["Status", "Requirement", "Source", "Citation"],
                [[f["status"], f["requirement"], f["source_title"], f["source_ref"]] for f in comp["findings"]],
            )
            if comp["findings"]
            else ["No relevant requirement was retrieved.", ""]
        )
        md += [f"_{comp['disclaimer']}_", ""]

    md += ["## 4. Corrective and preventive actions (human decisions)", ""]
    md += (
        _table(
            ["Type", "Action", "Origin", "Decision", "Reviewer / reason", "Owner", "Due", "Work"],
            [
                [
                    a.action_type,
                    a.title,
                    "AI-proposed" if a.ai_generated else "Human",
                    a.approval_status.value,
                    (
                        f"{names.get(decision[a.id].reviewer_id, '')}: {decision[a.id].reason}"
                        if a.id in decision
                        else ""
                    ),
                    names.get(a.assignee_id or "", a.owner_role),
                    a.due_date,
                    a.work_status.value,
                ]
                for a in actions
            ],
        )
        if actions
        else ["No actions recorded.", ""]
    )
    titles = {a.id: a.title for a in actions}
    md += ["## 5. Verification", ""]
    md += (
        _table(
            ["Action", "Verifier", "Effective", "Notes", "When"],
            [
                [
                    titles.get(v.capa_id),
                    names.get(v.verifier_id),
                    "yes" if v.effective else "no",
                    v.notes,
                    v.created_at.isoformat()[:16],
                ]
                for v in sorted(verifs, key=lambda v: v.created_at)
            ],
        )
        if verifs
        else ["No verifications yet.", ""]
    )
    blockers = capa_service.close_blockers(db, inc)
    if inc.status.value != "CLOSED" and blockers:
        md += ["**Not yet closable:** " + " ".join(blockers), ""]
    md += ["## 6. Lifecycle", ""]
    md += _table(
        ["When (UTC)", "From", "To", "By", "Note"],
        [
            [h.created_at.isoformat()[:16], h.from_status, h.to_status, names.get(h.actor_id or "", "system"), h.note]
            for h in history
        ],
    )
    md += [f"Audit events for this incident and its actions: {audit_count}.", ""]
    return "\n".join(md)
