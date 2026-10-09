"""Agent specifications: declared tools, budgets, evidence gathering and role prompts."""

from app.agents import rules
from app.agents.framework import AgentContext, AgentSpec
from app.models import Domain


def _incident_query(inc: dict, extra: list[str] | None = None) -> str:
    return " ".join([inc["title"], inc["description"], inc.get("activity") or "", *(extra or [])])


def _gather_triage(ctx: AgentContext) -> dict:
    inc = ctx.call("get_incident")
    return {
        "incident": inc,
        "evidence": ctx.call("list_evidence"),
        "knowledge": ctx.call("search_knowledge", query=_incident_query(inc), domain=None, limit=4),
        "similar_incidents": ctx.call("similar_incidents"),
    }


def _gather_investigation(domain: Domain):
    def gather(ctx: AgentContext) -> dict:
        inc = ctx.call("get_incident")
        prior = ctx.call("get_prior_outputs")
        hazards = prior.get("triage", {}).get("hazards", [])
        return {
            "incident": inc,
            "evidence": ctx.call("list_evidence"),
            "knowledge": ctx.call("search_knowledge", query=_incident_query(inc, hazards), domain=domain, limit=5),
            "similar_incidents": ctx.call("similar_incidents"),
            "vision": ctx.call("list_vision_observations"),
            "prior": prior,
        }

    return gather


def _gather_with_prior(limit: int):
    def gather(ctx: AgentContext) -> dict:
        inc = ctx.call("get_incident")
        prior = ctx.call("get_prior_outputs")
        labels = prior.get("triage", {}).get("hazards", []) + prior.get("quality", {}).get("defects", [])
        return {
            "incident": inc,
            "evidence": ctx.call("list_evidence"),
            "knowledge": ctx.call("search_knowledge", query=_incident_query(inc, labels), domain=None, limit=limit),
            "similar_incidents": ctx.call("similar_incidents"),
            "prior": prior,
        }

    return gather


_COMMON = frozenset({"get_incident", "list_evidence", "search_knowledge", "similar_incidents"})

AGENTS: dict[str, AgentSpec] = {
    "triage": AgentSpec(
        name="triage",
        description="Classify the incident, propose severity/priority, list missing information and route.",
        tools=_COMMON,
        max_tool_calls=6,
        gather=_gather_triage,
        rules=rules.triage,
        system_prompt=(
            "Incident Triage Agent. Classify the event as SAFETY, QUALITY or BOTH, name the hazards or "
            "defects, propose a severity and priority (P1 highest), list missing information, and recommend "
            "which investigation agents should run next."
        ),
    ),
    "safety": AgentSpec(
        name="safety",
        description="Hazards, unsafe acts/conditions, failed controls, suggested likelihood/consequence.",
        tools=_COMMON | {"get_prior_outputs", "list_vision_observations"},
        max_tool_calls=6,
        gather=_gather_investigation(Domain.SAFETY),
        rules=rules.safety,
        system_prompt=(
            "Safety Investigation Agent. Identify hazards, unsafe acts, unsafe conditions and controls that "
            "failed or were missing. Suggest likelihood (1-5) and worst credible consequence (1-5); a "
            "deterministic matrix computes the final risk."
        ),
    ),
    "quality": AgentSpec(
        name="quality",
        description="Defects, requirement vs observed, probable stage, recommended tests.",
        tools=_COMMON | {"get_prior_outputs", "list_vision_observations"},
        max_tool_calls=6,
        gather=_gather_investigation(Domain.QUALITY),
        rules=rules.quality,
        system_prompt=(
            "Quality Investigation Agent. Identify defects, compare what the specification/ITP requires with "
            "what was observed, name the probable stage (design, material, workmanship, inspection) and "
            "recommend tests. Suggest likelihood and consequence 1-5."
        ),
    ),
    "rca": AgentSpec(
        name="rca",
        description="5-Whys root cause hypotheses with categories and confidence.",
        tools=_COMMON | {"get_prior_outputs"},
        max_tool_calls=6,
        gather=_gather_with_prior(4),
        rules=rules.rca,
        system_prompt=(
            "Root Cause Analysis Agent. Use the 5-Whys method on the investigation outputs. Give root cause "
            "hypotheses (PEOPLE, PROCESS, EQUIPMENT, MATERIALS, ENVIRONMENT, MANAGEMENT) with confidence. "
            "These are hypotheses for the investigator to validate, not conclusions."
        ),
    ),
    "compliance": AgentSpec(
        name="compliance",
        description="Map incident facts to retrieved requirements with citations.",
        tools=frozenset(
            {"get_incident", "list_evidence", "search_knowledge", "similar_incidents", "get_prior_outputs"}
        ),
        max_tool_calls=6,
        gather=_gather_with_prior(6),
        rules=rules.compliance,
        system_prompt=(
            "Compliance Agent. From the retrieved procedures, ITPs and guidance only, list the requirements "
            "relevant to this incident and whether the facts suggest each was LIKELY_MET, LIKELY_NOT_MET or "
            "UNCLEAR. Cite the chunk ref for every requirement."
        ),
    ),
    "capa": AgentSpec(
        name="capa",
        description="Corrective and preventive actions with owners, due dates and verification criteria.",
        tools=_COMMON | {"get_prior_outputs"},
        max_tool_calls=6,
        gather=_gather_with_prior(4),
        rules=rules.capa,
        system_prompt=(
            "CAPA Agent. Propose corrective actions (fix this occurrence) and preventive actions (stop "
            "recurrence) tied to the root causes and hazards. Each needs an owner role, due_in_days and a "
            "measurable verification criterion. Prefer higher-order controls (eliminate, engineer) over PPE."
        ),
    ),
}
