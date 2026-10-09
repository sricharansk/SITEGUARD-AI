"""Project dashboard and analytics (Prompt 32): metrics match hand-computed fixtures, filters are enforced, and nobody
sees counts from projects they cannot read.

The fixture is a separate organization with two projects and timestamps chosen by hand, so every expected number
below can be checked against the records it comes from.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models import (
    AgentRun,
    ApprovalStatus,
    CapaAction,
    Domain,
    Incident,
    IncidentEvent,
    IncidentStatus,
    Membership,
    Organization,
    Project,
    Role,
    Severity,
    User,
    WorkStatus,
)
from tests.conftest import PASSWORD, auth


def _t(day: str, hour: float = 0) -> datetime:
    return datetime.fromisoformat(day).replace(tzinfo=UTC) + timedelta(hours=hour)


S, D, ST = Severity, Domain, IncidentStatus
# reference, project, severity, domain, status, occurred, hours to report, hours to first response, days to close
INCIDENTS = [
    ("ANA-A", "P1", S.HIGH, D.SAFETY, ST.CLOSED, _t("2026-03-02", 8), 1.0, 2.0, 4.0),
    ("ANA-B", "P1", S.CRITICAL, D.SAFETY, ST.ACTION_IN_PROGRESS, _t("2026-03-20", 10), 0.5, 1.0, None),
    ("ANA-C", "P1", S.MEDIUM, D.QUALITY, ST.CLOSED, _t("2026-04-10", 7), 1.0, 6.0, 10.0),
    ("ANA-D", "P1", S.LOW, D.QUALITY, ST.REPORTED, _t("2026-05-05", 12), 0.0, None, None),
    ("ANA-E", "P2", S.HIGH, D.SAFETY, ST.TRIAGED, _t("2026-03-15", 9), 0.0, 1.0, None),
]
PAST, FUTURE = date(2026, 1, 1), date(2999, 1, 1)
# incident, approval, work, due date
ACTIONS = [
    ("ANA-A", ApprovalStatus.APPROVED, WorkStatus.VERIFIED, date(2026, 3, 5)),
    ("ANA-B", ApprovalStatus.APPROVED, WorkStatus.IN_PROGRESS, PAST),  # overdue
    ("ANA-B", ApprovalStatus.MODIFIED, WorkStatus.NOT_STARTED, FUTURE),
    ("ANA-B", ApprovalStatus.PENDING_REVIEW, WorkStatus.NOT_STARTED, PAST),  # not approved, so not overdue
    ("ANA-C", ApprovalStatus.REJECTED, WorkStatus.NOT_STARTED, PAST),
    ("ANA-E", ApprovalStatus.APPROVED, WorkStatus.NOT_STARTED, PAST),  # overdue, project P2
]
# incident, agent, status, provider, needs review, minutes after report, output
RUNS = [
    ("ANA-A", "triage", "SUCCEEDED", "rules", False, 10, {"hazards": ["Fall from height", "Superseded hazard"]}),
    (
        "ANA-A",
        "triage",
        "SUCCEEDED",
        "rules",
        False,
        90,
        {"hazards": ["Fall from height", "Fall from height", "Missing or incorrect PPE"]},
    ),
    ("ANA-B", "triage", "SUCCEEDED", "rules", False, 5, {"hazards": ["Fall from height", "No known hazard matched."]}),
    ("ANA-C", "triage", "SUCCEEDED", "rules", False, 5, {"hazards": ["Concrete honeycombing / voids"]}),
    (
        "ANA-C",
        "quality",
        "SUCCEEDED",
        "rules (fallback from anthropic)",
        True,
        6,
        {"defects": ["Concrete honeycombing / voids"]},
    ),
    ("ANA-D", "triage", "FAILED", "rules", False, 5, None),
    ("ANA-E", "triage", "SUCCEEDED", "rules", False, 5, {"hazards": ["Struck by falling or moving object"]}),
]


@pytest.fixture(scope="module")
def analytics_org(client) -> dict:
    """Organization with projects P1 and P2, an organization-wide HSE manager and a P1-only safety engineer."""
    with SessionLocal() as db:
        if db.scalar(select(Organization).where(Organization.name == "Analytics Test Org")):
            pytest.fail("analytics fixture already exists; the test database is shared per session")
        org = Organization(name="Analytics Test Org")
        db.add(org)
        db.flush()
        projects = {
            key: Project(organization_id=org.id, code=f"ANA-{key}", name=f"Analytics {key}") for key in ("P1", "P2")
        }
        db.add_all(projects.values())
        db.flush()
        users = {}
        for who, role, project in (("ana-hse", Role.HSE_MANAGER, None), ("ana-p1", Role.SAFETY_ENGINEER, "P1")):
            user = User(email=f"{who}@demo.siteguard.local", full_name=who, password_hash=hash_password(PASSWORD))
            db.add(user)
            db.flush()
            db.add(
                Membership(
                    user_id=user.id,
                    organization_id=org.id,
                    project_id=projects[project].id if project else None,
                    role=role,
                )
            )
            users[who] = user.id
        incidents = {}
        for ref, key, severity, domain, status, occurred, report_after, response_after, close_after in INCIDENTS:
            reported = occurred + timedelta(hours=report_after)
            inc = Incident(
                reference=ref,
                organization_id=org.id,
                project_id=projects[key].id,
                title=f"Analytics fixture {ref}",
                description="Hand-built record for dashboard aggregation tests.",
                domain=domain,
                severity=severity,
                status=status,
                occurred_at=occurred,
                reported_at=reported,
                closed_at=reported + timedelta(days=close_after) if close_after is not None else None,
                reporter_id=users["ana-hse"],
            )
            db.add(inc)
            db.flush()
            incidents[ref] = inc
            events = [(None, "REPORTED", reported)]
            if response_after is not None:
                first = reported + timedelta(hours=response_after)
                events += [
                    ("REPORTED", "TRIAGED", first),
                    ("TRIAGED", "UNDER_INVESTIGATION", first + timedelta(hours=3)),
                ]
            if status == IncidentStatus.CLOSED:
                events.append(("PENDING_VERIFICATION", "CLOSED", inc.closed_at))
            for from_status, to_status, at in events:
                db.add(
                    IncidentEvent(
                        incident_id=inc.id,
                        actor_id=users["ana-hse"],
                        from_status=from_status,
                        to_status=to_status,
                        created_at=at,
                    )
                )
        for ref, approval, work, due in ACTIONS:
            db.add(
                CapaAction(
                    incident_id=incidents[ref].id,
                    action_type="CORRECTIVE",
                    title=f"Action for {ref} ({approval.value}, {work.value})",
                    description="Fixture action.",
                    verification_criteria="Checked.",
                    approval_status=approval,
                    work_status=work,
                    due_date=due,
                )
            )
        for ref, agent, status, provider, review, minutes, output in RUNS:
            started = incidents[ref].reported_at + timedelta(minutes=minutes)
            db.add(
                AgentRun(
                    incident_id=incidents[ref].id,
                    workflow_id=f"wf-{ref}-{minutes}",
                    agent=agent,
                    provider=provider,
                    status=status,
                    output=output,
                    trace=[],
                    needs_human_review=review,
                    started_at=started,
                    finished_at=started + timedelta(seconds=2),
                    triggered_by=users["ana-hse"],
                )
            )
        db.commit()
        return {
            "org": org.id,
            "P1": projects["P1"].id,
            "P2": projects["P2"].id,
            "ids": {r: i.id for r, i in incidents.items()},
        }


def _dash(client, who: str, **params):
    return client.get("/dashboard", params=params, headers=auth(client, who))


def test_metrics_match_hand_computed_records(client, analytics_org):
    r = _dash(client, "ana-hse", project_id=analytics_org["P1"])
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["filters"] == {
        "project_id": analytics_org["P1"],
        "projects": 1,
        "date_from": None,
        "date_to": None,
        "interval": "month",
    }
    assert d["totals"] == {
        "incidents": 4,
        "open": 2,
        "open_critical": 1,
        "closed": 2,
        "awaiting_review": 1,
        "actions_open": 2,  # approved or modified, not yet verified
        "actions_overdue": 1,
        "mean_days_to_close": 7.0,  # (4 + 10) / 2
        "median_days_to_close": 7.0,
        "responded": 3,
        "awaiting_response": 1,
        "mean_response_hours": 3.0,  # (2 + 1 + 6) / 3
        "median_response_hours": 2.0,
    }
    assert d["by_status"] == {"CLOSED": 2, "ACTION_IN_PROGRESS": 1, "REPORTED": 1}
    assert d["by_severity"] == {"HIGH": 1, "CRITICAL": 1, "MEDIUM": 1, "LOW": 1}
    assert d["by_domain"] == {"SAFETY": 2, "QUALITY": 2}
    assert d["by_month"] == {"2026-03": 2, "2026-04": 1, "2026-05": 1}
    assert d["capa_by_status"] == {"APPROVED": 2, "MODIFIED": 1, "PENDING_REVIEW": 1, "REJECTED": 1}
    assert d["capa_work"] == {"VERIFIED": 1, "IN_PROGRESS": 1, "NOT_STARTED": 1}
    assert [a["incident_id"] for a in d["overdue_actions"]] == [analytics_org["ids"]["ANA-B"]]
    assert d["overdue_actions"][0]["work_status"] == "IN_PROGRESS"
    assert [i["reference"] for i in d["recent"]] == ["ANA-D", "ANA-C", "ANA-B", "ANA-A"]
    # Latest successful triage per incident only; a label repeated inside one output counts once; placeholders skipped.
    assert d["top_hazards"] == [
        ["Fall from height", 2],
        ["Concrete honeycombing / voids", 1],
        ["Missing or incorrect PPE", 1],
    ]
    assert d["top_defects"] == [["Concrete honeycombing / voids", 1]]
    assert d["agents"] == {
        "runs": 6,
        "succeeded": 5,
        "failed": 1,
        "flagged_for_review": 1,
        "fallbacks": 1,
        "providers": {"rules": 5, "rules (fallback from anthropic)": 1},
    }


def test_trends_bucket_response_and_closure_by_month(client, analytics_org):
    d = _dash(client, "ana-hse", project_id=analytics_org["P1"]).json()["data"]
    assert d["trends"]["interval"] == "month" and d["trends"]["truncated"] is False
    assert d["trends"]["buckets"] == [
        {
            "period": "2026-03",
            "start": "2026-03-01",
            "end": "2026-03-31",
            "incidents": 2,
            "closed": 1,
            "open": 1,
            "responded": 2,
            "median_response_hours": 1.5,
            "mean_response_hours": 1.5,
            "median_days_to_close": 4.0,
            "mean_days_to_close": 4.0,
        },
        {
            "period": "2026-04",
            "start": "2026-04-01",
            "end": "2026-04-30",
            "incidents": 1,
            "closed": 1,
            "open": 0,
            "responded": 1,
            "median_response_hours": 6.0,
            "mean_response_hours": 6.0,
            "median_days_to_close": 10.0,
            "mean_days_to_close": 10.0,
        },
        {
            "period": "2026-05",
            "start": "2026-05-01",
            "end": "2026-05-31",
            "incidents": 1,
            "closed": 0,
            "open": 1,
            "responded": 0,
            "median_response_hours": None,
            "mean_response_hours": None,
            "median_days_to_close": None,
            "mean_days_to_close": None,
        },
    ]


def test_date_filter_selects_incidents_by_occurrence_day(client, analytics_org):
    p1 = analytics_org["P1"]
    d = _dash(client, "ana-hse", project_id=p1, date_from="2026-03-15", date_to="2026-04-30").json()["data"]
    assert d["filters"]["date_from"] == "2026-03-15" and d["filters"]["date_to"] == "2026-04-30"
    assert d["totals"]["incidents"] == 2 and d["by_month"] == {"2026-03": 1, "2026-04": 1}  # B and C
    assert d["totals"]["mean_response_hours"] == 3.5 and d["totals"]["mean_days_to_close"] == 10.0
    assert d["capa_by_status"] == {"APPROVED": 1, "MODIFIED": 1, "PENDING_REVIEW": 1, "REJECTED": 1}
    assert d["totals"]["actions_overdue"] == 1 and d["agents"]["runs"] == 3
    assert d["top_hazards"] == [["Concrete honeycombing / voids", 1], ["Fall from height", 1]]
    assert [b["period"] for b in d["trends"]["buckets"]] == ["2026-03", "2026-04"]
    # Both ends are whole UTC days, inclusive.
    assert _dash(client, "ana-hse", project_id=p1, date_to="2026-03-02").json()["data"]["totals"]["incidents"] == 1
    assert _dash(client, "ana-hse", project_id=p1, date_from="2026-03-03").json()["data"]["totals"]["incidents"] == 3
    # A range with no incidents still returns empty buckets for the whole range.
    empty = _dash(client, "ana-hse", project_id=p1, date_from="2026-06-01", date_to="2026-07-31").json()["data"]
    assert empty["totals"]["incidents"] == 0 and empty["top_hazards"] == [] and empty["overdue_actions"] == []
    assert [(b["period"], b["incidents"]) for b in empty["trends"]["buckets"]] == [("2026-06", 0), ("2026-07", 0)]


def test_weekly_trend_uses_iso_weeks(client, analytics_org):
    d = _dash(
        client, "ana-hse", project_id=analytics_org["P1"], date_from="2026-03-01", date_to="2026-03-21", interval="week"
    ).json()["data"]
    buckets = d["trends"]["buckets"]
    assert [(b["period"], b["start"], b["end"], b["incidents"]) for b in buckets] == [
        ("2026-W09", "2026-02-23", "2026-03-01", 0),
        ("2026-W10", "2026-03-02", "2026-03-08", 1),
        ("2026-W11", "2026-03-09", "2026-03-15", 0),
        ("2026-W12", "2026-03-16", "2026-03-22", 1),
    ]
    assert buckets[1]["median_response_hours"] == 2.0 and buckets[3]["median_response_hours"] == 1.0


def test_long_trend_ranges_are_capped_and_flagged(client, analytics_org):
    d = _dash(
        client, "ana-hse", project_id=analytics_org["P1"], date_from="2000-01-01", date_to="2026-12-31", interval="week"
    ).json()["data"]
    buckets = d["trends"]["buckets"]
    assert d["trends"]["truncated"] is True and len(buckets) == 260
    assert buckets[-1]["start"] == "2026-12-28" and d["totals"]["incidents"] == 4  # totals are never truncated
    assert sum(b["incidents"] for b in buckets) == 4


def test_filter_validation(client, analytics_org):
    p1 = analytics_org["P1"]
    for params in (
        {"date_from": "2026-05-01", "date_to": "2026-04-30"},  # inverted range
        {"date_from": "not-a-date"},
        {"date_to": "2026-02-30"},
        {"date_from": "1900-01-01"},
        {"interval": "day"},
    ):
        r = _dash(client, "ana-hse", project_id=p1, **params)
        assert r.status_code == 400, params
        assert r.json()["error"]["code"] == "INVALID_REQUEST" and r.json()["error"]["correlation_id"]
    assert client.get("/dashboard").status_code == 401


def test_project_filter_and_tenant_isolation(client, analytics_org, project_id):
    p1, p2 = analytics_org["P1"], analytics_org["P2"]
    # Organization-wide role: both projects, including P2's incident and its overdue action.
    everything = _dash(client, "ana-hse").json()["data"]
    assert everything["filters"]["projects"] == 2 and everything["filters"]["project_id"] is None
    assert everything["totals"]["incidents"] == 5 and everything["totals"]["actions_overdue"] == 2
    assert _dash(client, "ana-hse", project_id=p2).json()["data"]["totals"]["incidents"] == 1
    # Project-limited role: only P1, and P2 is "not found" rather than forbidden.
    limited = _dash(client, "ana-p1").json()["data"]
    assert limited["filters"]["projects"] == 1 and limited["totals"]["incidents"] == 4
    assert all(i["project_id"] == p1 for i in limited["recent"])
    assert "Struck by falling or moving object" not in dict(limited["top_hazards"])
    assert _dash(client, "ana-p1", project_id=p2).status_code == 404
    # Other tenants: the demo organization cannot see these projects and these users cannot see the demo project.
    for who, foreign in (("hse", p1), ("other", p2), ("ana-hse", project_id), ("ana-p1", project_id)):
        r = _dash(client, who, project_id=foreign)
        assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"
    assert _dash(client, "ana-hse", project_id="no-such-project").status_code == 404
    demo = _dash(client, "hse").json()["data"]
    assert not {i["reference"] for i in demo["recent"]} & {row[0] for row in INCIDENTS}


def test_unfiltered_counts_match_the_callers_own_projects(client, analytics_org, db):
    """For every demo role the unfiltered totals equal a direct count over the projects that user can read."""
    for who in ("hse", "auditor", "other", "ana-p1"):
        me = client.get("/me", headers=auth(client, who)).json()["data"]
        visible: set[str] = set()
        for m in me["memberships"]:
            if m["project_id"]:
                visible.add(m["project_id"])
            else:
                visible |= set(db.scalars(select(Project.id).where(Project.organization_id == m["organization_id"])))
        d = _dash(client, who).json()["data"]
        expected = db.scalar(select(func.count()).select_from(Incident).where(Incident.project_id.in_(visible)))
        closed = db.scalar(
            select(func.count())
            .select_from(Incident)
            .where(Incident.project_id.in_(visible), Incident.status == IncidentStatus.CLOSED)
        )
        assert d["totals"]["incidents"] == expected, who
        assert d["by_status"].get("CLOSED", 0) == closed == d["totals"]["closed"], who
        assert sum(d["by_severity"].values()) == expected, who
