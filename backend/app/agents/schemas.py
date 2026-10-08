"""Structured outputs for every agent. Agents may only return these shapes (docs/AGENTS.md)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import Domain, Severity


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confidence: float = Field(ge=0, le=1, description="0-1 confidence in this output")
    evidence_refs: list[str] = Field(
        default_factory=list, description="Refs from the evidence pack only: incident:, evidence:, chunk:"
    )
    open_questions: list[str] = Field(default_factory=list, description="What a human must check or find out")


class TriageOutput(_Out):
    incident_class: str = Field(description="Short incident class, e.g. 'Fall from height'")
    domain: Domain
    severity_candidate: Severity
    priority: Literal["P1", "P2", "P3", "P4"]
    hazards: list[str]
    missing_information: list[str]
    recommended_next_agents: list[Literal["safety", "quality"]]
    rationale: str


class SafetyInvestigationOutput(_Out):
    hazards: list[str]
    unsafe_acts: list[str]
    unsafe_conditions: list[str]
    failed_or_missing_controls: list[str]
    likelihood: int = Field(ge=1, le=5, description="Suggested likelihood of recurrence 1-5")
    consequence: int = Field(ge=1, le=5, description="Suggested worst credible consequence 1-5")
    summary: str


class QualityInvestigationOutput(_Out):
    defects: list[str]
    requirement_vs_observed: list[str]
    probable_stage: Literal["DESIGN", "MATERIAL", "WORKMANSHIP", "INSPECTION", "UNKNOWN"]
    recommended_tests: list[str]
    likelihood: int = Field(ge=1, le=5)
    consequence: int = Field(ge=1, le=5)
    summary: str


class RootCause(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Literal["PEOPLE", "PROCESS", "EQUIPMENT", "MATERIALS", "ENVIRONMENT", "MANAGEMENT"]
    statement: str
    confidence: float = Field(ge=0, le=1)


class RcaOutput(_Out):
    method: Literal["5-WHYS"] = "5-WHYS"
    problem_statement: str
    whys: list[str] = Field(min_length=1, max_length=5)
    root_causes: list[RootCause] = Field(min_length=1)
    contributing_factors: list[str]


class ComplianceFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirement: str
    source_ref: str = Field(description="chunk: ref the requirement was taken from")
    source_title: str
    status: Literal["LIKELY_MET", "LIKELY_NOT_MET", "UNCLEAR"]
    note: str


class ComplianceOutput(_Out):
    findings: list[ComplianceFinding]
    disclaimer: str = (
        "Decision support only. Findings map incident facts to retrieved requirements and must be confirmed "
        "by a competent person; this is not a legal compliance determination."
    )


class CapaProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_type: Literal["CORRECTIVE", "PREVENTIVE"]
    title: str
    description: str
    owner_role: str
    due_in_days: int = Field(ge=0, le=180)
    verification_criteria: str
    addresses: str = Field(description="Root cause or hazard this action addresses")


class CapaOutput(_Out):
    actions: list[CapaProposal] = Field(min_length=1, max_length=8)


AGENT_OUTPUTS: dict[str, type[_Out]] = {
    "triage": TriageOutput,
    "safety": SafetyInvestigationOutput,
    "quality": QualityInvestigationOutput,
    "rca": RcaOutput,
    "compliance": ComplianceOutput,
    "capa": CapaOutput,
}
