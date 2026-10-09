"""Project dashboard and analytics (Playbook Prompt 32). docs/API.md "Dashboard metrics" defines every metric.

The caller's readable projects, narrowed by the optional project and date filters, select one set of incidents
(incidents that occurred in the range). Every metric is computed from that set: categorical counts and trends from one
light row per incident, everything else from grouped SQL aggregates or bounded queries keyed by the same subquery, so
the cost is bounded by the filter and there are no per-incident queries.

Definitions (UTC throughout):
- response time: from `reported_at` to the first lifecycle transition out of REPORTED. Agents never run on their own
  (a person requests triage or investigation), so that transition is always the first human response.
- days to close: from `reported_at` to `closed_at`, for incidents that are CLOSED now.
- trend buckets: calendar months or ISO weeks (Monday start) of `occurred_at`; each bucket describes the incidents that
  occurred in it.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from statistics import mean, median
from typing import Any, Literal

from sqlalchemy import ColumnElement, and_, func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import (
    AgentRun,
    ApprovalStatus,
    CapaAction,
    Domain,
    Incident,
    IncidentEvent,
    IncidentStatus,
    Severity,
    WorkStatus,
)

Interval = Literal["month", "week"]

MIN_DATE = date(1970, 1, 1)
MAX_DATE = date(2999, 12, 31)
MAX_TREND_BUCKETS = 260  # five years of weeks; older buckets are dropped and `truncated` is set
TOP_N = 8
OVERDUE_LIMIT = 10
RECENT_LIMIT = 8
ACTIVE = (ApprovalStatus.APPROVED, ApprovalStatus.MODIFIED)
DONE_WORK = (WorkStatus.COMPLETED, WorkStatus.VERIFIED)
NO_MATCH_PREFIX = "No known"  # the rules triage placeholder when nothing matched; not a hazard


@dataclass(frozen=True)
class Filters:
    project_ids: list[str]
    date_from: date | None = None
    date_to: date | None = None
    interval: Interval = "month"

    def __post_init__(self) -> None:
        for name, value in (("date_from", self.date_from), ("date_to", self.date_to)):
            if value is not None and not MIN_DATE <= value <= MAX_DATE:
                raise AppError(f"{name} must be between {MIN_DATE.isoformat()} and {MAX_DATE.isoformat()}")
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise AppError("date_from must be on or before date_to")

    def conditions(self) -> list[ColumnElement[bool]]:
        conds: list[ColumnElement[bool]] = [Incident.project_id.in_(self.project_ids)]
        if self.date_from:
            conds.append(Incident.occurred_at >= _day_start(self.date_from))
        if self.date_to:
            conds.append(Incident.occurred_at < _day_start(self.date_to + timedelta(days=1)))
        return conds

    def echo(self, project_id: str | None) -> dict:
        return {
            "project_id": project_id,
            "projects": len(self.project_ids),
            "date_from": self.date_from,
            "date_to": self.date_to,
            "interval": self.interval,
        }


def _day_start(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=UTC)


def _utc(value: datetime) -> datetime:
    """SQLite returns naive timestamps (stored as UTC); PostgreSQL returns aware ones."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _round(values: list[float], fn) -> float | None:
    return round(fn(values), 1) if values else None


# --- trend periods --------------------------------------------------------------------------------------------------


def period_start(d: date, interval: Interval) -> date:
    return d.replace(day=1) if interval == "month" else d - timedelta(days=d.weekday())


def _next_period(start: date, interval: Interval) -> date:
    if interval == "week":
        return start + timedelta(days=7)
    return date(start.year + start.month // 12, start.month % 12 + 1, 1)


def _shift_back(start: date, periods: int, interval: Interval) -> date:
    if interval == "week":
        return start - timedelta(days=7 * periods)
    months = start.year * 12 + start.month - 1 - periods
    return date(months // 12, months % 12 + 1, 1)


def _count_periods(first: date, last: date, interval: Interval) -> int:
    if interval == "week":
        return (last - first).days // 7 + 1
    return (last.year - first.year) * 12 + last.month - first.month + 1


def period_label(start: date, interval: Interval) -> str:
    if interval == "month":
        return start.strftime("%Y-%m")
    year, week, _ = start.isocalendar()
    return f"{year}-W{week:02d}"


def _periods(first: date, last: date, interval: Interval) -> tuple[list[date], bool]:
    """Contiguous period starts from first to last, keeping the latest MAX_TREND_BUCKETS."""
    first, last = period_start(first, interval), period_start(last, interval)
    truncated = _count_periods(first, last, interval) > MAX_TREND_BUCKETS
    if truncated:
        first = _shift_back(last, MAX_TREND_BUCKETS - 1, interval)
    starts: list[date] = []
    cursor = first
    while cursor <= last:
        starts.append(cursor)
        cursor = _next_period(cursor, interval)
    return starts, truncated


# --- queries --------------------------------------------------------------------------------------------------------


@dataclass
class _Row:
    id: str
    status: IncidentStatus
    severity: Severity
    domain: str
    occurred_at: datetime
    reported_at: datetime
    closed_at: datetime | None
    response_hours: float | None = None

    @property
    def days_to_close(self) -> float | None:
        if self.status != IncidentStatus.CLOSED or self.closed_at is None:
            return None
        return max(0.0, (self.closed_at - self.reported_at).total_seconds() / 86400)


def _incident_rows(db: Session, f: Filters) -> list[_Row]:
    stmt = select(
        Incident.id,
        Incident.status,
        Incident.severity,
        Incident.domain,
        Incident.occurred_at,
        Incident.reported_at,
        Incident.closed_at,
    ).where(*f.conditions())
    rows = [
        _Row(
            id=r.id,
            status=IncidentStatus(r.status),
            severity=Severity(r.severity),
            domain=Domain(r.domain).value,
            occurred_at=_utc(r.occurred_at),
            reported_at=_utc(r.reported_at),
            closed_at=_utc(r.closed_at) if r.closed_at else None,
        )
        for r in db.execute(stmt)
    ]
    first_response = db.execute(
        select(IncidentEvent.incident_id, func.min(IncidentEvent.created_at))
        .where(
            IncidentEvent.from_status == IncidentStatus.REPORTED.value,
            IncidentEvent.incident_id.in_(_ids(f)),
        )
        .group_by(IncidentEvent.incident_id)
    ).all()
    responded = {incident_id: _utc(at) for incident_id, at in first_response}
    for row in rows:
        if row.id in responded:
            row.response_hours = max(0.0, (responded[row.id] - row.reported_at).total_seconds() / 3600)
    return rows


def _ids(f: Filters):
    return select(Incident.id).where(*f.conditions())


def _latest_outputs(db: Session, f: Filters, agent: str) -> list[dict]:
    """Output of the latest succeeded run of one agent per incident (a re-run replaces, never double counts)."""
    latest = (
        select(AgentRun.incident_id, func.max(AgentRun.started_at).label("started"))
        .where(AgentRun.agent == agent, AgentRun.status == "SUCCEEDED", AgentRun.incident_id.in_(_ids(f)))
        .group_by(AgentRun.incident_id)
        .subquery()
    )
    rows = db.execute(
        select(AgentRun.incident_id, AgentRun.output)
        .join(latest, and_(AgentRun.incident_id == latest.c.incident_id, AgentRun.started_at == latest.c.started))
        .where(AgentRun.agent == agent, AgentRun.status == "SUCCEEDED")
    ).all()
    outputs: dict[str, dict] = {}
    for incident_id, output in rows:
        outputs.setdefault(incident_id, output or {})
    return list(outputs.values())


def _recurring(outputs: list[dict], key: str) -> list[tuple[str, int]]:
    """How many incidents list each label; a label repeated inside one output counts once."""
    counts: Counter[str] = Counter()
    for output in outputs:
        labels = output.get(key, [])
        if isinstance(labels, list):
            counts.update({h for h in labels if isinstance(h, str) and h and not h.startswith(NO_MATCH_PREFIX)})
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_N]


def _capa(db: Session, f: Filters, today: date) -> dict[str, Any]:
    in_scope = CapaAction.incident_id.in_(_ids(f))
    grouped = db.execute(
        select(CapaAction.approval_status, CapaAction.work_status, func.count())
        .where(in_scope)
        .group_by(CapaAction.approval_status, CapaAction.work_status)
    ).all()
    by_approval: Counter[str] = Counter()
    active_work: Counter[str] = Counter()
    for approval, work, n in grouped:
        approval, work = ApprovalStatus(approval), WorkStatus(work)
        by_approval[approval.value] += n
        if approval in ACTIVE:
            active_work[work.value] += n
    overdue = and_(
        in_scope,
        CapaAction.approval_status.in_(ACTIVE),
        CapaAction.due_date.is_not(None),
        CapaAction.due_date < today,
        CapaAction.work_status.not_in(DONE_WORK),
    )
    overdue_count = db.scalar(select(func.count()).select_from(CapaAction).where(overdue)) or 0
    overdue_rows = db.scalars(
        select(CapaAction).where(overdue).order_by(CapaAction.due_date, CapaAction.id).limit(OVERDUE_LIMIT)
    ).all()
    return {
        "awaiting_review": by_approval[ApprovalStatus.PENDING_REVIEW.value],
        "actions_open": sum(n for work, n in active_work.items() if work != WorkStatus.VERIFIED.value),
        "actions_overdue": overdue_count,
        "capa_by_status": dict(by_approval),
        "capa_work": dict(active_work),
        "overdue_actions": list(overdue_rows),
    }


def _agents(db: Session, f: Filters) -> dict[str, Any]:
    grouped = db.execute(
        select(AgentRun.status, AgentRun.provider, AgentRun.needs_human_review, func.count())
        .where(AgentRun.incident_id.in_(_ids(f)))
        .group_by(AgentRun.status, AgentRun.provider, AgentRun.needs_human_review)
    ).all()
    providers: Counter[str] = Counter()
    stats = {"runs": 0, "succeeded": 0, "failed": 0, "flagged_for_review": 0, "fallbacks": 0}
    for status, provider, flagged, n in grouped:
        stats["runs"] += n
        stats["succeeded"] += n if status == "SUCCEEDED" else 0
        stats["failed"] += n if status == "FAILED" else 0
        stats["flagged_for_review"] += n if flagged else 0
        stats["fallbacks"] += n if "fallback" in provider else 0
        providers[provider] += n
    return {**stats, "providers": dict(providers)}


def _trends(rows: list[_Row], f: Filters) -> dict[str, Any]:
    first = f.date_from or (min(r.occurred_at for r in rows).date() if rows else None)
    last = f.date_to or (max(r.occurred_at for r in rows).date() if rows else None)
    if first is None or last is None:
        return {"interval": f.interval, "truncated": False, "buckets": []}
    starts, truncated = _periods(first, last, f.interval)
    grouped: dict[date, list[_Row]] = {s: [] for s in starts}
    for row in rows:
        start = period_start(row.occurred_at.date(), f.interval)
        if start in grouped:
            grouped[start].append(row)
    buckets = []
    for start in starts:
        members = grouped[start]
        responses = [r.response_hours for r in members if r.response_hours is not None]
        closing = [d for r in members if (d := r.days_to_close) is not None]
        buckets.append(
            {
                "period": period_label(start, f.interval),
                "start": start,
                "end": _next_period(start, f.interval) - timedelta(days=1),
                "incidents": len(members),
                "closed": len(closing),
                "open": len(members) - len(closing),
                "responded": len(responses),
                "median_response_hours": _round(responses, median),
                "mean_response_hours": _round(responses, mean),
                "median_days_to_close": _round(closing, median),
                "mean_days_to_close": _round(closing, mean),
            }
        )
    return {"interval": f.interval, "truncated": truncated, "buckets": buckets}


# --- dashboard ------------------------------------------------------------------------------------------------------


def dashboard(db: Session, f: Filters, *, project_id: str | None = None, today: date | None = None) -> dict:
    """Every dashboard metric for the filtered incidents. `overdue_actions` and `recent` hold model rows."""
    today = today or datetime.now(UTC).date()
    rows = _incident_rows(db, f) if f.project_ids else []
    capa = _capa(db, f, today) if rows else _capa_empty()
    agents = _agents(db, f) if rows else {**dict.fromkeys(_AGENT_KEYS, 0), "providers": {}}
    responses = [r.response_hours for r in rows if r.response_hours is not None]
    closing = [d for r in rows if (d := r.days_to_close) is not None]
    latest = select(Incident).where(*f.conditions()).order_by(Incident.reported_at.desc()).limit(RECENT_LIMIT)
    recent: list[Incident] = list(db.scalars(latest)) if rows else []
    return {
        "filters": f.echo(project_id),
        "totals": {
            "incidents": len(rows),
            "open": sum(1 for r in rows if r.status != IncidentStatus.CLOSED),
            "open_critical": sum(
                1 for r in rows if r.severity == Severity.CRITICAL and r.status != IncidentStatus.CLOSED
            ),
            "closed": len(closing),
            "awaiting_review": capa["awaiting_review"],
            "actions_open": capa["actions_open"],
            "actions_overdue": capa["actions_overdue"],
            "mean_days_to_close": _round(closing, mean),
            "median_days_to_close": _round(closing, median),
            "responded": len(responses),
            "awaiting_response": len(rows) - len(responses),
            "mean_response_hours": _round(responses, mean),
            "median_response_hours": _round(responses, median),
        },
        "by_status": dict(Counter(r.status.value for r in rows)),
        "by_severity": dict(Counter(r.severity.value for r in rows)),
        "by_domain": dict(Counter(r.domain for r in rows)),
        "by_month": dict(sorted(Counter(r.occurred_at.strftime("%Y-%m") for r in rows).items())),
        "trends": _trends(rows, f),
        "top_hazards": _recurring(_latest_outputs(db, f, "triage"), "hazards") if rows else [],
        "top_defects": _recurring(_latest_outputs(db, f, "quality"), "defects") if rows else [],
        "capa_by_status": capa["capa_by_status"],
        "capa_work": capa["capa_work"],
        "agents": agents,
        "overdue_actions": capa["overdue_actions"],
        "recent": recent,
    }


_AGENT_KEYS = ("runs", "succeeded", "failed", "flagged_for_review", "fallbacks")


def _capa_empty() -> dict[str, Any]:
    return {
        "awaiting_review": 0,
        "actions_open": 0,
        "actions_overdue": 0,
        "capa_by_status": {},
        "capa_work": {},
        "overdue_actions": [],
    }
