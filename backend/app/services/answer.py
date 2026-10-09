"""Grounded knowledge answers (Playbook Prompt 13).

Bounded RAG: retrieval is scoped to the caller's organization and project; sources flagged as instruction-like are
excluded; every statement must cite a retrieved chunk; statements without a valid, supporting citation are moved to
`unsupported_claims` and are not presented as facts. When the sources do not answer the question the response says
so explicitly (INSUFFICIENT_EVIDENCE); when sources disagree on a value it says so (CONFLICTING_EVIDENCE).
"""

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.agents.schemas import AnswerDraft, AnswerStatement
from app.core.config import get_settings
from app.models import Domain, Incident
from app.services import embeddings, rag

DISCLAIMER = (
    "Decision support only. Statements come from the cited documents and must be checked by a competent person; "
    "this is not a legal or regulatory compliance determination."
)
INSUFFICIENT = "The available documents do not contain enough evidence to answer this question."
MIN_COVERAGE = 0.34  # share of question terms the best source must contain
_SENTENCE = re.compile(r"(?:[^.;!?\n]|\.(?=\d))+[.;!?]?")  # a decimal point does not end a sentence
_MEASURE = re.compile(r"(\d+(?:\.\d+)?)\s?(mm|cm|metres?|meters?|m|kg|kn|mpa|%|hours?|days?|°c)(?![a-z])", re.I)
_UNIT = {"metre": "m", "metres": "m", "meter": "m", "meters": "m", "hour": "hours", "day": "days"}


def _terms(text: str) -> set[str]:
    return {embeddings.stem(t) for t in rag.tokenize(text)}


def _supported(statement: str, source_text: str) -> bool:
    words = _terms(statement)
    return bool(words) and len(words & _terms(source_text)) / len(words) >= 0.5


@dataclass
class RulesAnswerer:
    """Extractive answers: the sentences from the sources that best match the question, each with its citation."""

    name: str = "rules"
    max_statements: int = 3

    def draft(self, question: str, sources: list[dict]) -> AnswerDraft:
        q = _terms(question)
        need = max(2, (len(q) + 1) // 2)
        scored: list[tuple[int, int, str, str]] = []
        for rank, src in enumerate(sources):
            for m in _SENTENCE.finditer(" ".join(src["text"].split())):
                sentence = m.group(0).strip(" -*#|")
                overlap = len(q & _terms(sentence))
                if len(sentence) > 20 and overlap >= min(need, len(q)):
                    scored.append((overlap, -rank, sentence, src["ref"]))
        scored.sort(key=lambda t: (-t[0], -t[1]))
        statements: list[AnswerStatement] = []
        seen: set[str] = set()
        for _, _, sentence, ref in scored:
            if sentence.lower() in seen:
                continue
            seen.add(sentence.lower())
            statements.append(AnswerStatement(text=sentence, citations=[ref]))
            if len(statements) == self.max_statements:
                break
        if not statements:
            return AnswerDraft(
                status="INSUFFICIENT_EVIDENCE",
                answer=INSUFFICIENT,
                statements=[],
                confidence=0.0,
                uncertainty="No source sentence matches enough of the question.",
            )
        return AnswerDraft(
            status="ANSWERED",
            answer=" ".join(s.text for s in statements),
            statements=statements,
            confidence=round(min(0.9, 0.4 + 0.15 * len(statements)), 2),
            uncertainty="Extracted verbatim from the cited sources; check they apply to this site and activity.",
        )


def _conflicts(statements: list[AnswerStatement], by_ref: dict[str, dict]) -> list[str]:
    """Same unit, different value, overlapping wording, different documents: report it as a conflict."""
    found: list[str] = []
    measured = []
    for st in statements:
        for ref in st.citations:
            for value, unit in _MEASURE.findall(st.text):
                norm = _UNIT.get(unit.lower(), unit.lower())
                measured.append((float(value), norm, _terms(st.text), by_ref[ref]))
    for i, (v1, u1, t1, s1) in enumerate(measured):
        for v2, u2, t2, s2 in measured[i + 1 :]:
            if u1 == u2 and v1 != v2 and s1["document_id"] != s2["document_id"] and len(t1 & t2) >= 3:
                msg = (
                    f"'{s1['document_title']}' gives {v1:g} {u1} but '{s2['document_title']}' gives {v2:g} {u2} "
                    f"for the same requirement."
                )
                if msg not in found:
                    found.append(msg)
    return found


def get_answerer():
    if get_settings().ai_provider == "anthropic":
        from app.agents.llm import AnthropicAnswerer

        return AnthropicAnswerer()
    return RulesAnswerer()


def answer(
    db: Session,
    *,
    organization_id: str,
    project_id: str,
    question: str,
    incident: Incident | None = None,
    domain: Domain | None = None,
    answerer=None,
) -> dict:
    query = f"{question} {incident.title}" if incident is not None else question
    hits = rag.search(db, organization_id=organization_id, project_id=project_id, query=query, domain=domain, limit=6)
    excluded = [
        {"ref": h.ref, "reason": "instruction-like content; treated as data only"} for h in hits if h.suspicious
    ]
    usable = [h for h in hits if not h.suspicious]
    sources: list[dict] = [
        {
            "ref": h.ref,
            "document_id": h.document_id,
            "document_title": h.document_title,
            "section": h.section,
            "page": h.page,
            "version": h.version,
            "effective_date": h.effective_date.isoformat() if h.effective_date else None,
            "text": h.text,
        }
        for h in usable
    ]
    by_ref: dict[str, dict] = {s["ref"]: s for s in sources}
    provider = "rules"
    best = max((h.scores.get("rerank", 0.0) for h in usable), default=0.0)
    q_terms = _terms(question)
    coverage = max((len(q_terms & _terms(s["text"])) / len(q_terms) for s in sources), default=0.0) if q_terms else 0
    if not sources or coverage < MIN_COVERAGE:
        draft = AnswerDraft(
            status="INSUFFICIENT_EVIDENCE",
            answer=INSUFFICIENT,
            statements=[],
            confidence=0.0,
            uncertainty="No authorized document covers enough of the question.",
        )
    else:
        answerer = answerer or get_answerer()
        try:
            draft = answerer.draft(question, sources)
            provider = answerer.name
        except Exception:  # provider failure: fall back to extractive answers, never lose the request
            draft = RulesAnswerer().draft(question, sources)
            provider = f"rules (fallback from {getattr(answerer, 'name', 'provider')})"

    supported: list[AnswerStatement] = []
    unsupported: list[str] = []
    for st in draft.statements:
        refs = [r for r in st.citations if r in by_ref]
        if refs and any(_supported(st.text, by_ref[r]["text"]) for r in refs):
            supported.append(AnswerStatement(text=st.text, citations=refs))
        else:
            unsupported.append(st.text)

    # A model-reported conflict counts only if it names a retrieved source; otherwise it is unverified text.
    grounded = [c for c in draft.conflicts if any(ref in c for ref in by_ref)]
    conflicts = list(dict.fromkeys([*grounded, *_conflicts(supported, by_ref)]))
    status = draft.status
    confidence = draft.confidence
    if not supported:
        status, confidence = "INSUFFICIENT_EVIDENCE", 0.0
    elif conflicts:
        status, confidence = "CONFLICTING_EVIDENCE", min(confidence, 0.4)
    answer_text = INSUFFICIENT if status == "INSUFFICIENT_EVIDENCE" else " ".join(s.text for s in supported)
    if status == "INSUFFICIENT_EVIDENCE":
        supported = []
    cited = list(dict.fromkeys(r for s in supported for r in s.citations))
    return {
        "status": status,
        "answer": answer_text,
        "statements": [s.model_dump() for s in supported],
        "citations": [{k: v for k, v in by_ref[r].items() if k != "text"} for r in cited],
        "confidence": round(confidence, 2),
        "uncertainty": draft.uncertainty[:500],
        "unsupported_claims": unsupported,
        "conflicts": conflicts,
        "excluded_sources": excluded,
        "needs_human_review": status != "ANSWERED" or bool(unsupported) or confidence < 0.5,
        "provider": provider,
        "retrieval": {"sources": len(sources), "best_rerank": round(best, 3), "question_coverage": round(coverage, 2)},
        "disclaimer": DISCLAIMER,
    }
