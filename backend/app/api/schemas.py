from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import Domain, IncidentStatus, Severity, WorkStatus


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LoginIn(_In):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=200)


class ProjectIn(_In):
    organization_id: str
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=200)
    client: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=300)
    sites: list[str] = Field(default_factory=list, max_length=50)


class IncidentIn(_In):
    title: str = Field(min_length=3, max_length=300)
    description: str = Field(min_length=10, max_length=20000)
    domain: Domain
    severity: Severity
    occurred_at: datetime
    site_id: str | None = None
    category: str | None = Field(default=None, max_length=80)
    location: str | None = Field(default=None, max_length=300)
    activity: str | None = Field(default=None, max_length=200)
    people_involved: int = Field(default=0, ge=0, le=10000)
    immediate_actions: str | None = Field(default=None, max_length=5000)


class IncidentPatch(_In):
    title: str | None = Field(default=None, min_length=3, max_length=300)
    description: str | None = Field(default=None, min_length=10, max_length=20000)
    domain: Domain | None = None
    severity: Severity | None = None
    category: str | None = Field(default=None, max_length=80)
    location: str | None = Field(default=None, max_length=300)
    activity: str | None = Field(default=None, max_length=200)
    people_involved: int | None = Field(default=None, ge=0, le=10000)
    immediate_actions: str | None = Field(default=None, max_length=5000)


class TransitionIn(_In):
    to_status: IncidentStatus
    note: str = Field(min_length=1, max_length=2000)


class CloseIn(_In):
    note: str = Field(min_length=1, max_length=5000)


class RiskIn(_In):
    likelihood: int = Field(ge=1, le=5)
    consequence: int = Field(ge=1, le=5)
    rationale: str = Field(min_length=1, max_length=2000)


class DocumentIn(_In):
    organization_id: str
    title: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1, max_length=500_000)
    doc_type: str = Field(min_length=1, max_length=60)
    source: str = Field(min_length=1, max_length=500)
    domain: Domain = Domain.BOTH
    project_id: str | None = None
    version: str = Field(default="1", max_length=40)


class CapaIn(_In):
    action_type: Literal["CORRECTIVE", "PREVENTIVE"]
    title: str = Field(min_length=3, max_length=300)
    description: str = Field(min_length=3, max_length=5000)
    owner_role: str | None = Field(default=None, max_length=40)
    assignee_id: str | None = None
    due_date: date | None = None
    verification_criteria: str = Field(min_length=3, max_length=2000)
    critical: bool = False


class ReviewIn(_In):
    decision: Literal["APPROVE", "MODIFY", "REJECT"]
    reason: str = Field(min_length=1, max_length=2000)
    changes: dict | None = None


class ApproveIn(_In):
    reason: str = Field(min_length=1, max_length=2000)


class ProgressIn(_In):
    work_status: Literal["IN_PROGRESS", "COMPLETED"] | None = None
    assignee_id: str | None = None
    note: str | None = Field(default=None, max_length=2000)

    def status(self) -> WorkStatus | None:
        return WorkStatus(self.work_status) if self.work_status else None


class VerifyIn(_In):
    effective: bool
    notes: str = Field(min_length=1, max_length=5000)
    evidence_id: str | None = None
