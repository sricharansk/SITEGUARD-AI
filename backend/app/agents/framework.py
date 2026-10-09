"""Bounded agent framework: declared tools, budgets, trace, schema-validated output.

An agent run has two phases:
1. gather: the agent calls its *declared* tools through AgentContext.call (anything else is refused)
   and builds an evidence pack;
2. decide: a provider (deterministic rules, or an LLM) turns the evidence pack into the agent's
   output schema. LLM output is validated and its evidence refs are checked against the pack.
   If the LLM fails, the rules provider answers instead and the trace records the fallback.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from app.agents.schemas import AGENT_OUTPUTS


class ToolNotAllowed(Exception):
    pass


class BudgetExceeded(Exception):
    pass


@dataclass
class AgentSpec:
    name: str
    description: str
    tools: frozenset[str]
    max_tool_calls: int
    gather: Callable[["AgentContext"], dict]
    rules: Callable[[dict], BaseModel]
    system_prompt: str

    @property
    def output_model(self) -> type[BaseModel]:
        return AGENT_OUTPUTS[self.name]


@dataclass
class AgentContext:
    spec: AgentSpec
    tools: dict[str, Callable[..., Any]]
    trace: list[dict] = field(default_factory=list)
    calls: int = 0

    def call(self, tool: str, **kwargs: Any) -> Any:
        if tool not in self.spec.tools:
            self.trace.append({"type": "tool_refused", "tool": tool})
            raise ToolNotAllowed(f"Agent '{self.spec.name}' may not call tool '{tool}'")
        if self.calls >= self.spec.max_tool_calls:
            raise BudgetExceeded(f"Agent '{self.spec.name}' exceeded {self.spec.max_tool_calls} tool calls")
        self.calls += 1
        started = time.perf_counter()
        result = self.tools[tool](**kwargs)
        self.trace.append(
            {
                "type": "tool_call",
                "tool": tool,
                "args": {k: (v if isinstance(v, str | int | float) else str(v)) for k, v in kwargs.items()},
                "ms": round((time.perf_counter() - started) * 1000, 1),
            }
        )
        return result


class Provider:
    name = "base"

    def decide(self, spec: AgentSpec, pack: dict) -> BaseModel:  # pragma: no cover - interface
        raise NotImplementedError


class RulesProvider(Provider):
    name = "rules"

    def decide(self, spec: AgentSpec, pack: dict) -> BaseModel:
        return spec.rules(pack)


def allowed_refs(pack: dict) -> set[str]:
    refs = {f"incident:{pack['incident']['id']}"}
    refs |= {f"evidence:{e['id']}" for e in pack.get("evidence", [])}
    refs |= {h["ref"] for h in pack.get("knowledge", [])}
    refs |= {v["ref"] for v in pack.get("vision", [])}
    return refs


@dataclass
class AgentResult:
    output: BaseModel
    provider: str
    trace: list[dict]
    needs_human_review: bool
    review_reasons: list[str]


def run_agent(spec: AgentSpec, tools: dict[str, Callable[..., Any]], provider: Provider) -> AgentResult:
    ctx = AgentContext(spec=spec, tools=tools)
    pack = spec.gather(ctx)
    used = provider.name
    try:
        output = provider.decide(spec, pack)
        output = spec.output_model.model_validate(output.model_dump())
    except (ValidationError, Exception) as exc:  # provider failure must not lose the incident
        if isinstance(provider, RulesProvider):
            raise
        ctx.trace.append({"type": "provider_fallback", "from": provider.name, "error": type(exc).__name__})
        output = RulesProvider().decide(spec, pack)
        used = f"rules (fallback from {provider.name})"

    reasons: list[str] = []
    valid = allowed_refs(pack)
    refs = list(getattr(output, "evidence_refs", []))
    unknown = [r for r in refs if r not in valid]
    if unknown:
        ctx.trace.append({"type": "evidence_refs_removed", "refs": unknown})
        output.evidence_refs = [r for r in refs if r in valid]  # type: ignore[attr-defined]
        reasons.append("Output cited evidence that was not retrieved; those citations were removed.")
    if not output.evidence_refs:  # type: ignore[attr-defined]
        reasons.append("No supporting evidence was cited.")
    if output.confidence < 0.5:  # type: ignore[attr-defined]
        reasons.append(f"Low confidence ({output.confidence:.2f}).")  # type: ignore[attr-defined]
    suspicious = [h["ref"] for h in pack.get("knowledge", []) if h.get("suspicious")]
    if suspicious:
        reasons.append("Retrieved content contained instruction-like text and was treated as data only.")
        ctx.trace.append({"type": "suspicious_content", "refs": suspicious})
    ctx.trace.append({"type": "decided", "provider": used})
    return AgentResult(output, used, ctx.trace, bool(reasons), reasons)
