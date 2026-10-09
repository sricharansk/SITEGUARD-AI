"""SQLAlchemy models. See docs/DATABASE.md for the table list and scoping rules."""

import enum
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.vector import VectorType


def _uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class Role(enum.StrEnum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ORG_ADMIN = "ORG_ADMIN"
    PROJECT_MANAGER = "PROJECT_MANAGER"
    HSE_MANAGER = "HSE_MANAGER"
    SAFETY_ENGINEER = "SAFETY_ENGINEER"
    QA_QC_ENGINEER = "QA_QC_ENGINEER"
    SITE_ENGINEER = "SITE_ENGINEER"
    AUDITOR = "AUDITOR"
    VIEWER = "VIEWER"


class Domain(enum.StrEnum):
    SAFETY = "SAFETY"
    QUALITY = "QUALITY"
    BOTH = "BOTH"


class Severity(enum.StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IncidentStatus(enum.StrEnum):
    REPORTED = "REPORTED"
    TRIAGED = "TRIAGED"
    UNDER_INVESTIGATION = "UNDER_INVESTIGATION"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    ACTION_IN_PROGRESS = "ACTION_IN_PROGRESS"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    CLOSED = "CLOSED"


class ApprovalStatus(enum.StrEnum):
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    MODIFIED = "MODIFIED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class WorkStatus(enum.StrEnum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    VERIFIED = "VERIFIED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Organization(Timestamped, Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), unique=True)


class User(Timestamped, Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(300))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    memberships: Mapped[list["Membership"]] = relationship(back_populates="user", lazy="selectin")


class Membership(Timestamped, Base):
    """A user's role in an organization. project_id=None means every project in the organization."""

    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "organization_id", "project_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False))
    user: Mapped[User] = relationship(back_populates="memberships")


class Project(Timestamped, Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(200))
    client: Mapped[str | None] = mapped_column(String(200), nullable=True)
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    sites: Mapped[list["Site"]] = relationship(back_populates="project", lazy="selectin")


class Site(Timestamped, Base):
    __tablename__ = "sites"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    project: Mapped[Project] = relationship(back_populates="sites")


class Incident(Timestamped, Base):
    __tablename__ = "incidents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    reference: Mapped[str] = mapped_column(String(40), unique=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    site_id: Mapped[str | None] = mapped_column(ForeignKey("sites.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    domain: Mapped[Domain] = mapped_column(Enum(Domain, native_enum=False))
    severity: Mapped[Severity] = mapped_column(Enum(Severity, native_enum=False))
    status: Mapped[IncidentStatus] = mapped_column(
        Enum(IncidentStatus, native_enum=False), default=IncidentStatus.REPORTED, index=True
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    activity: Mapped[str | None] = mapped_column(String(200), nullable=True)
    people_involved: Mapped[int] = mapped_column(Integer, default=0)
    immediate_actions: Mapped[str | None] = mapped_column(Text, nullable=True)
    reporter_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)


class IncidentEvent(Base):
    __tablename__ = "incident_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    from_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    to_status: Mapped[str] = mapped_column(String(40))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DocumentStatus(enum.StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"


class Document(Timestamped, Base):
    """Knowledge document for retrieval (procedure, ITP, spec, guidance). Content is untrusted."""

    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    doc_type: Mapped[str] = mapped_column(String(60))
    source: Mapped[str] = mapped_column(String(500))
    version: Mapped[str] = mapped_column(String(40), default="1")
    domain: Mapped[Domain] = mapped_column(Enum(Domain, native_enum=False), default=Domain.BOTH)
    sha256: Mapped[str] = mapped_column(String(64))
    # Processing state: PENDING -> PROCESSING -> READY | FAILED (docs/DATABASE.md).
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, native_enum=False), default=DocumentStatus.READY, server_default="READY"
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(300), nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parser: Mapped[str | None] = mapped_column(String(40), nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    uploaded_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", lazy="selectin", order_by="DocumentChunk.ordinal"
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    section: Mapped[str] = mapped_column(String(300))
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text)
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    suspicious: Mapped[bool] = mapped_column(Boolean, default=False)
    document: Mapped[Document] = relationship(back_populates="chunks")


class ChunkEmbedding(Base):
    """One vector per chunk and embedding model version. Re-embedding the same content is a no-op."""

    __tablename__ = "chunk_embeddings"
    __table_args__ = (UniqueConstraint("chunk_id", "model", "model_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    chunk_id: Mapped[str] = mapped_column(ForeignKey("document_chunks.id", ondelete="CASCADE"), index=True)
    model: Mapped[str] = mapped_column(String(80))
    model_version: Mapped[str] = mapped_column(String(40))
    dim: Mapped[int] = mapped_column(Integer)
    content_sha256: Mapped[str] = mapped_column(String(64))
    vector: Mapped[list] = mapped_column(VectorType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    workflow_id: Mapped[str] = mapped_column(String(36), index=True)
    agent: Mapped[str] = mapped_column(String(60))
    provider: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(20))  # SUCCEEDED | FAILED | SKIPPED
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    trace: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    needs_human_review: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    triggered_by: Mapped[str] = mapped_column(ForeignKey("users.id"))


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    matrix_version: Mapped[str] = mapped_column(String(20))
    likelihood: Mapped[int] = mapped_column(Integer)
    consequence: Mapped[int] = mapped_column(Integer)
    score: Mapped[int] = mapped_column(Integer)
    band: Mapped[str] = mapped_column(String(20))
    rationale: Mapped[str] = mapped_column(Text)
    inputs_source: Mapped[str] = mapped_column(String(40))  # AI_SUGGESTED | HUMAN
    assessed_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CapaAction(Timestamped, Base):
    __tablename__ = "capa_actions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(20))  # CORRECTIVE | PREVENTIVE
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    owner_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    assignee_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    verification_criteria: Mapped[str] = mapped_column(Text)
    critical: Mapped[bool] = mapped_column(Boolean, default=False)
    approval_status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus, native_enum=False), default=ApprovalStatus.PENDING_REVIEW
    )
    work_status: Mapped[WorkStatus] = mapped_column(Enum(WorkStatus, native_enum=False), default=WorkStatus.NOT_STARTED)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    original_ai_output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    evidence_refs: Mapped[list] = mapped_column(JSON, default=list)


class ApprovalEvent(Base):
    __tablename__ = "approval_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    capa_id: Mapped[str] = mapped_column(ForeignKey("capa_actions.id"), index=True)
    reviewer_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text)
    before: Mapped[dict] = mapped_column(JSON)
    after: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class VerificationRecord(Base):
    __tablename__ = "verification_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    capa_id: Mapped[str] = mapped_column(ForeignKey("capa_actions.id"), index=True)
    verifier_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    effective: Mapped[bool] = mapped_column(Boolean)
    notes: Mapped[str] = mapped_column(Text)
    evidence_id: Mapped[str | None] = mapped_column(ForeignKey("evidence.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(20), default="USER")  # USER | AGENT | SYSTEM
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class DeliveryStatus(enum.StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"  # dead letter: every attempt failed; an administrator can retry it
    SKIPPED = "SKIPPED"  # external delivery disabled in this environment


class Notification(Base):
    """An in-app notification for one person. `dedupe_key` makes event handling and escalation idempotent."""

    __tablename__ = "notifications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    incident_id: Mapped[str | None] = mapped_column(ForeignKey("incidents.id"), nullable=True)
    recipient_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    priority: Mapped[str] = mapped_column(String(10))  # INFO | HIGH | CRITICAL
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    dedupe_key: Mapped[str] = mapped_column(String(200), unique=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    deliveries: Mapped[list["NotificationDelivery"]] = relationship(
        back_populates="notification", cascade="all, delete-orphan"
    )


class NotificationDelivery(Base):
    """External delivery (email) of a notification: an outbox row with bounded retries."""

    __tablename__ = "notification_deliveries"
    __table_args__ = (UniqueConstraint("notification_id", "channel"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    notification_id: Mapped[str] = mapped_column(ForeignKey("notifications.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(20))  # EMAIL
    status: Mapped[DeliveryStatus] = mapped_column(
        Enum(DeliveryStatus, native_enum=False), default=DeliveryStatus.PENDING, index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    notification: Mapped[Notification] = relationship(back_populates="deliveries")
