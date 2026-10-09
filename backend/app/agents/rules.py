"""Deterministic, offline decision rules for every agent.

These run when no LLM is configured, and as the fallback when the LLM fails. They use an explicit
construction hazard/defect taxonomy so their output is reproducible and testable.
"""

import re
from typing import Literal

from app.agents.schemas import (
    CapaOutput,
    CapaProposal,
    ComplianceFinding,
    ComplianceOutput,
    QualityInvestigationOutput,
    RcaOutput,
    RootCause,
    SafetyInvestigationOutput,
    TriageOutput,
)
from app.models import Domain, Severity

# --- Taxonomy -----------------------------------------------------------------------------------

SAFETY_HAZARDS: dict[str, list[str]] = {
    "Fall from height": [
        "fall from",
        "fell from height",
        "at height",
        "slab edge",
        "unprotected edge",
        "harness",
        "ladder",
        "roof edge",
        "floor opening",
        "guardrail",
        "guard rail",
        "lanyard",
        "mewp",
        "lost footing",
        "lost his footing",
        "lost her footing",
    ],
    "Struck by falling or moving object": [
        "dropped",
        "falling object",
        "struck",
        "hit by",
        "landed near",
    ],
    "Excavation collapse / caught-in": ["trench", "excavation", "collapse", "cave-in", "cave in", "shoring"],
    "Electrical contact": [
        "electric",
        "shock",
        "live cable",
        "energised",
        "energized",
        "arc flash",
        "lockout",
    ],
    "Lifting operation / crane": [
        "crane lift",
        "lifting operation",
        "lift plan",
        "rigging",
        "sling",
        "suspended load",
        "hoist",
        "load swung",
    ],
    "Mobile plant / vehicle": [
        "excavator",
        "revers",
        "vehicle",
        "forklift",
        "dumper",
        "telehandler",
        "mobile plant",
        "banksman",
    ],
    "Fire / hot work": ["fire", "hot work", "welding spark", "flammable", "gas cylinder"],
    "Missing or incorrect PPE": [
        "helmet",
        "hard hat",
        "ppe",
        "hi-vis",
        "high-visibility",
        "gloves",
        "goggles",
        "safety boots",
        "eye protection",
    ],
    "Confined space": ["confined space", "manhole", "tank entry", "oxygen"],
    "Cuts / sharp objects": ["cut his", "cut her", "cut their", "laceration", "stitches", "sharp edge"],
    "Manual handling / musculoskeletal": ["manual handling", "back injury", "strain", "lifting by hand"],
}

QUALITY_DEFECTS: dict[str, list[str]] = {
    "Concrete honeycombing / voids": ["honeycomb", "void", "segregation", "blowhole"],
    "Cracking": ["crack", "cracking", "spalling"],
    "Reinforcement / cover nonconformance": [
        "concrete cover",
        "cover meter",
        "cover of",
        "spacers",
        "bar spacing",
        "lap length",
        "reinforcement inspection",
    ],
    "Concrete strength / mix nonconformance": [
        "cube",
        "cylinder",
        "compressive strength",
        "slump",
        "mix design",
        "w/c ratio",
    ],
    "Formwork defect": [
        "formwork failure",
        "formwork movement",
        "shuttering failure",
        "bulge",
        "form failure",
        "grout loss",
        "blowout",
    ],
    "Dimensional / alignment tolerance": [
        "misalign",
        "out of plumb",
        "out of level",
        "dimensional",
        "out of tolerance",
        "setting-out error",
    ],
    "Water ingress / waterproofing": ["leak", "seepage", "damp", "moisture", "waterproof", "ingress"],
    "Welding / steelwork defect": ["weld", "porosity", "undercut", "bolt torque", "steel connection"],
    "Material nonconformance": ["wrong material", "substitut", "non-conforming material", "expired", "batch"],
}

CRITICAL_WORDS = ["fatal", "fatality", "death", "died", "amputation", "collapse", "unconscious", "crushed"]
HIGH_WORDS = [
    "hospital",
    "fracture",
    "broken",
    "lost time",
    "serious",
    "structural",
    "load-bearing",
    "failed",
]
NEAR_MISS_WORDS = ["near miss", "near-miss", "narrowly", "could have"]
NEGATION_CUES = [
    "without",
    "no ",
    "not ",
    "missing",
    "removed",
    "unsecured",
    "unguarded",
    "bypassed",
    "expired",
    "untagged",
    "uninspected",
    "did not",
    "wasn't",
    "was not",
    "absent",
    "lack",
]

Priority = Literal["P1", "P2", "P3", "P4"]
ActionType = Literal["CORRECTIVE", "PREVENTIVE"]

SEVERITY_ORDER = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]


def _text(pack: dict) -> str:
    inc = pack["incident"]
    parts = [inc["title"], inc["description"], inc.get("activity") or "", inc.get("immediate_actions") or ""]
    parts += [e.get("description") or "" for e in pack.get("evidence", [])]
    return " ".join(parts).lower()


def _has(text: str, word: str) -> bool:
    """Word-prefix match: 'revers' matches 'reversed', but 'ppe' does not match 'stepped'."""
    return re.search(r"\b" + re.escape(word), text) is not None


def _match(text: str, taxonomy: dict[str, list[str]]) -> list[str]:
    """Labels ordered by how many of their keywords appear (ties keep taxonomy order)."""
    scored = [(sum(_has(text, w) for w in words), i, name) for i, (name, words) in enumerate(taxonomy.items())]
    return [name for n, _, name in sorted(scored, key=lambda t: (-t[0], t[1])) if n > 0]


def _base_refs(pack: dict, k: int = 3) -> list[str]:
    refs = [f"incident:{pack['incident']['id']}"]
    refs += [f"evidence:{e['id']}" for e in pack.get("evidence", [])]
    refs += [h["ref"] for h in pack.get("knowledge", [])[:k] if not h.get("suspicious")]
    return refs


def _vision(pack: dict, categories: set[str]) -> tuple[list[dict], list[dict]]:
    """Vision observations for these categories: (CONFIRMED by an engineer, UNREVIEWED machine observations)."""
    confirmed = [v for v in pack.get("vision", []) if v["category"] in categories]
    return confirmed, [v for v in pack.get("vision_unreviewed", []) if v["category"] in categories]


def _vision_questions(unreviewed: list[dict]) -> list[str]:
    return [
        f"Check the unreviewed vision observation '{v['name']}' (observation {v['observation_id']}, confidence "
        f"{v['confidence']:.0%}) against the photo; it is a machine observation, not a finding."
        for v in unreviewed[:5]
    ]


def _add_mapped(labels: list[str], confirmed: list[dict], unclassified: str) -> list[str]:
    out = [label for label in labels if label != unclassified]
    for v in confirmed:
        if v.get("maps_to") and v["maps_to"] not in out:
            out.append(v["maps_to"])
    return out or [unclassified]


HIGH_ENERGY = {
    "Fall from height",
    "Excavation collapse / caught-in",
    "Lifting operation / crane",
    "Mobile plant / vehicle",
    "Electrical contact",
    "Struck by falling or moving object",
    "Confined space",
}


def _consequence(text: str, people: int, hazards: list[str] | None = None) -> int:
    """Worst credible consequence 1-5. A near miss is rated by its potential, not its outcome."""
    if any(_has(text, w) for w in CRITICAL_WORDS):
        c = 5
    elif any(_has(text, w) for w in HIGH_WORDS):
        c = 4
    elif people > 0 or _has(text, "injur"):
        c = 3
    else:
        c = 2
    if any(_has(text, w) for w in NEAR_MISS_WORDS) or _has(text, "not struck") or _has(text, "no one was"):
        c = max(c, 4 if set(hazards or []) & HIGH_ENERGY else 3)
    return c


def _severity_for(consequence: int) -> Severity:
    return {5: Severity.CRITICAL, 4: Severity.HIGH, 3: Severity.MEDIUM}.get(consequence, Severity.LOW)


# --- Triage -------------------------------------------------------------------------------------


def triage(pack: dict) -> TriageOutput:
    inc = pack["incident"]
    text = _text(pack)
    hazards = _match(text, SAFETY_HAZARDS)
    defects = _match(text, QUALITY_DEFECTS)
    if hazards and defects:
        domain = Domain.BOTH
    elif defects:
        domain = Domain.QUALITY
    elif hazards:
        domain = Domain.SAFETY
    else:
        domain = Domain(inc["domain"])
    consequence = _consequence(text, inc.get("people_involved", 0), hazards)
    severity = _severity_for(consequence)
    priorities: dict[Severity, Priority] = {
        Severity.CRITICAL: "P1",
        Severity.HIGH: "P2",
        Severity.MEDIUM: "P3",
        Severity.LOW: "P4",
    }
    priority = priorities[severity]

    missing = []
    if not pack.get("evidence"):
        missing.append("No photos or documents attached as evidence.")
    if not inc.get("location"):
        missing.append("Exact location on site.")
    if not inc.get("immediate_actions"):
        missing.append("Immediate actions taken to make the area safe.")
    if len(inc["description"].split()) < 15:
        missing.append("A fuller description: sequence of events, equipment, people and conditions.")

    labels = hazards + defects
    incident_class = labels[0] if labels else "Unclassified site event"
    nxt: list = []
    if domain in (Domain.SAFETY, Domain.BOTH):
        nxt.append("safety")
    if domain in (Domain.QUALITY, Domain.BOTH):
        nxt.append("quality")
    if not nxt:
        nxt = ["safety"]

    confidence = 0.4 + 0.15 * min(len(labels), 2) + (0.1 if pack.get("knowledge") else 0) - 0.05 * len(missing)
    confidence = round(max(0.2, min(0.9, confidence)), 2)
    similar = pack.get("similar_incidents", [])
    rationale = (
        f"Matched {len(hazards)} safety hazard(s) and {len(defects)} quality defect type(s) in the report. "
        f"Credible consequence rated {consequence}/5 from injury/damage cues, giving {severity.value} severity. "
        f"{len(similar)} similar past incident(s) found."
    )
    return TriageOutput(
        incident_class=incident_class,
        domain=domain,
        severity_candidate=severity,
        priority=priority,
        hazards=labels or ["No known hazard or defect pattern matched; needs human classification."],
        missing_information=missing,
        recommended_next_agents=nxt,
        rationale=rationale,
        confidence=confidence,
        evidence_refs=_base_refs(pack),
        open_questions=(["Confirm classification; no taxonomy pattern matched."] if not labels else []),
    )


# --- Safety investigation -----------------------------------------------------------------------

_SAFETY_DETAIL: dict[str, dict[str, list[str]]] = {
    "Fall from height": {
        "acts": ["Working at height without being attached to an anchor point"],
        "conditions": ["Unprotected edge or opening", "Access equipment not inspected or not tagged"],
        "controls": [
            "Edge protection / guardrails",
            "Fall arrest system and rescue plan",
            "Permit to work at height",
            "Pre-use scaffold/ladder inspection",
        ],
    },
    "Struck by falling or moving object": {
        "acts": ["Tools or materials not secured at height"],
        "conditions": ["No exclusion zone below overhead work", "No toe boards or debris netting"],
        "controls": ["Exclusion zone", "Tool tethering", "Toe boards / netting"],
    },
    "Excavation collapse / caught-in": {
        "acts": ["Entering an unsupported excavation"],
        "conditions": ["Excavation not shored, sloped or benched", "Spoil or plant too close to the edge"],
        "controls": [
            "Protective system (shoring/sloping/trench box)",
            "Daily excavation inspection",
            "Edge setback for spoil and plant",
        ],
    },
    "Electrical contact": {
        "acts": ["Working near conductors without isolation"],
        "conditions": ["Live or damaged cables", "No lockout/tagout applied"],
        "controls": ["Isolation and lockout/tagout", "Cable detection before digging", "RCD/GFCI protection"],
    },
    "Lifting operation / crane": {
        "acts": ["Lift carried out outside the lift plan", "Personnel under a suspended load"],
        "conditions": ["Rigging not inspected", "Wind or ground conditions outside limits"],
        "controls": ["Approved lift plan", "Competent slinger/signaller", "Rigging inspection register"],
    },
    "Mobile plant / vehicle": {
        "acts": ["Pedestrian inside plant operating zone", "Reversing without a banksman"],
        "conditions": ["No segregation of people and plant", "Reversing alarm/camera faulty"],
        "controls": ["Traffic management plan", "Physical segregation", "Banksman for reversing"],
    },
    "Fire / hot work": {
        "acts": ["Hot work without a permit or fire watch"],
        "conditions": ["Combustibles near hot work"],
        "controls": ["Hot work permit", "Fire watch", "Extinguisher at point of work"],
    },
    "Missing or incorrect PPE": {
        "acts": ["Required PPE not worn"],
        "conditions": ["PPE not available or not suitable for the task"],
        "controls": ["PPE issue and enforcement", "Task-specific PPE assessment"],
    },
    "Confined space": {
        "acts": ["Entry without gas testing or permit"],
        "conditions": ["Atmosphere not monitored"],
        "controls": ["Confined space permit", "Gas monitoring", "Standby person and rescue plan"],
    },
    "Cuts / sharp objects": {
        "acts": ["Handling sharp material without cut-resistant gloves"],
        "conditions": ["Exposed sharp ends or edges"],
        "controls": ["Cut-resistant gloves", "Rebar end caps", "Safe cutting method"],
    },
    "Manual handling / musculoskeletal": {
        "acts": ["Load lifted by hand beyond safe limits"],
        "conditions": ["No mechanical aid available"],
        "controls": ["Manual handling assessment", "Mechanical lifting aids"],
    },
}


def _likelihood(text: str, similar: int) -> int:
    lk = 3
    if any(_has(text, c.strip()) for c in NEGATION_CUES):
        lk += 1  # a control was missing or bypassed
    if similar >= 2:
        lk += 1
    return min(lk, 5)


def safety(pack: dict) -> SafetyInvestigationOutput:
    inc = pack["incident"]
    text = _text(pack)
    seen, unreviewed = _vision(pack, {"PPE", "HAZARD"})
    hazards = _add_mapped(_match(text, SAFETY_HAZARDS), seen, "Unclassified safety hazard")
    acts, conds, controls = [], [], []
    for h in hazards:
        d = _SAFETY_DETAIL.get(h)
        if d:
            acts += d["acts"]
            conds += d["conditions"]
            controls += d["controls"]
    consequence = _consequence(text, inc.get("people_involved", 0), hazards)
    likelihood = _likelihood(text, len(pack.get("similar_incidents", [])))
    questions = [
        "Interview the people involved and witnesses.",
        "Check training and competence records for the task.",
    ]
    if not pack.get("evidence"):
        questions.append("Collect photos of the scene and equipment.")
    questions += _vision_questions(unreviewed)
    return SafetyInvestigationOutput(
        hazards=hazards,
        unsafe_acts=acts or ["To be determined by interview"],
        unsafe_conditions=conds or ["To be determined by site inspection"],
        failed_or_missing_controls=controls or ["To be determined"],
        likelihood=likelihood,
        consequence=consequence,
        summary=(
            f"{', '.join(hazards)}. Suggested likelihood {likelihood}/5 and consequence {consequence}/5; "
            "these inputs go to the deterministic risk matrix and must be confirmed by the investigator."
        ),
        confidence=0.7 if hazards[0] != "Unclassified safety hazard" else 0.35,
        evidence_refs=_base_refs(pack) + [v["ref"] for v in seen],
        open_questions=questions,
    )


# --- Quality investigation ----------------------------------------------------------------------

_QUALITY_DETAIL: dict[str, dict] = {
    "Concrete honeycombing / voids": {
        "req": "Concrete must be fully compacted with no honeycombing on formed surfaces.",
        "stage": "WORKMANSHIP",
        "tests": ["Visual survey and mapping of affected area", "Hammer sounding", "Core test if structural"],
    },
    "Cracking": {
        "req": "Crack widths must stay within the specification limit for the exposure class.",
        "stage": "UNKNOWN",
        "tests": [
            "Crack width and length mapping",
            "Crack monitoring with tell-tales",
            "Structural engineer review",
        ],
    },
    "Reinforcement / cover nonconformance": {
        "req": "Reinforcement size, spacing and cover must match the approved drawings before the pour.",
        "stage": "INSPECTION",
        "tests": ["Cover meter survey", "Compare against bar bending schedule and drawings"],
    },
    "Concrete strength / mix nonconformance": {
        "req": "Concrete must reach the specified characteristic strength at 28 days.",
        "stage": "MATERIAL",
        "tests": ["Review cube/cylinder results and delivery tickets", "Rebound hammer", "Core testing"],
    },
    "Formwork defect": {
        "req": "Formwork must be inspected and signed off before concrete placement.",
        "stage": "WORKMANSHIP",
        "tests": ["Dimensional survey of the element", "Formwork inspection record review"],
    },
    "Dimensional / alignment tolerance": {
        "req": "Elements must be within the specified dimensional tolerances.",
        "stage": "WORKMANSHIP",
        "tests": ["Survey against setting-out data"],
    },
    "Water ingress / waterproofing": {
        "req": "Waterproofing must be continuous and tested before backfill or finishes.",
        "stage": "WORKMANSHIP",
        "tests": ["Flood or spray test", "Moisture mapping"],
    },
    "Welding / steelwork defect": {
        "req": "Welds must meet the specified visual and NDT acceptance criteria.",
        "stage": "WORKMANSHIP",
        "tests": ["Visual weld inspection", "NDT (MT/UT) on affected welds", "Welder qualification check"],
    },
    "Material nonconformance": {
        "req": "Only approved materials with valid certificates may be used.",
        "stage": "MATERIAL",
        "tests": ["Check material certificates and delivery records"],
    },
}


def quality(pack: dict) -> QualityInvestigationOutput:
    text = _text(pack)
    seen, unreviewed = _vision(pack, {"DEFECT"})
    defects = _add_mapped(_match(text, QUALITY_DEFECTS), seen, "Unclassified quality issue")
    reqs, tests, stages = [], [], []
    for d in defects:
        det = _QUALITY_DETAIL.get(d)
        if det:
            photos = [v for v in seen if v.get("maps_to") == d]
            observed = (
                "; ".join(
                    f"{v['name']} on photo evidence:{v['evidence_id']}, confirmed by an engineer ({v['ref']})"
                    for v in photos
                )
                if photos
                else "see incident description"
            )
            reqs.append(f"{d}: requirement - {det['req']} Observed - {observed}.")
            tests += det["tests"]
            stages.append(det["stage"])
    structural = any(_has(text, w) for w in ["structural", "load-bearing", "column", "beam", "slab", "transfer"])
    consequence = 4 if structural else 3
    if any(_has(text, w) for w in CRITICAL_WORDS):
        consequence = 5
    return QualityInvestigationOutput(
        defects=defects,
        requirement_vs_observed=reqs or ["Specification requirement to be identified"],
        probable_stage=stages[0] if len(set(stages)) == 1 else "UNKNOWN",  # type: ignore[arg-type]
        recommended_tests=tests or ["Inspection by QA/QC engineer"],
        likelihood=_likelihood(text, len(pack.get("similar_incidents", []))),
        consequence=consequence,
        summary=f"{', '.join(defects)} on {'a structural' if structural else 'a non-structural'} element.",
        confidence=0.7 if defects[0] != "Unclassified quality issue" else 0.35,
        evidence_refs=_base_refs(pack) + [v["ref"] for v in seen],
        open_questions=[
            "Confirm the governing specification clause and drawing revision.",
            "Raise an NCR if the requirement is confirmed as not met.",
            *_vision_questions(unreviewed),
        ],
    )


# --- RCA ----------------------------------------------------------------------------------------

_CAUSE_MAP: dict[str, tuple[str, str]] = {
    "permit": ("PROCESS", "Permit-to-work control was not applied or not checked before work started."),
    "inspect": ("PROCESS", "Required inspection was not done, or was not recorded, before use."),
    "harness": ("PEOPLE", "Fall protection was available but not used; supervision did not catch it."),
    "guardrail": ("EQUIPMENT", "Edge protection was missing or had been removed without a replacement."),
    "training": ("PEOPLE", "Workers were not trained or briefed for this task."),
    "supervis": ("MANAGEMENT", "Supervision of the task was not enough for its risk level."),
    "rain": ("ENVIRONMENT", "Weather conditions were not covered by the method statement."),
    "wind": ("ENVIRONMENT", "Wind limits were not monitored or enforced."),
    "schedule": ("MANAGEMENT", "Programme pressure led to steps being skipped."),
    "rush": ("MANAGEMENT", "Programme pressure led to steps being skipped."),
    "vibrat": ("PROCESS", "Compaction method or duration was not controlled during the pour."),
    "cover": ("PROCESS", "Pre-pour reinforcement check was missed or not effective."),
    "mix": ("MATERIALS", "Concrete supplied did not match the approved mix design."),
    "drawing": ("PROCESS", "Work was done against a superseded or unclear drawing."),
}


def rca(pack: dict) -> RcaOutput:
    text = _text(pack)
    prior = pack.get("prior", {})
    tri = prior.get("triage", {})
    problem = f"{tri.get('incident_class', pack['incident']['title'])}: {pack['incident']['title']}"
    causes: dict[str, RootCause] = {}
    for key, (cat, statement) in _CAUSE_MAP.items():
        if _has(text, key) and statement not in causes:
            causes[statement] = RootCause(category=cat, statement=statement, confidence=0.6)  # type: ignore[arg-type]
    if not causes:
        causes["generic"] = RootCause(
            category="PROCESS",
            statement="The method statement / risk assessment did not control this hazard well enough.",
            confidence=0.4,
        )
    controls = prior.get("safety", {}).get("failed_or_missing_controls", [])
    whys = [
        f"Why did it happen? {pack['incident']['title']}.",
        "Why was that possible? "
        + (f"The control '{controls[0].lower()}' was missing or not effective." if controls else "A control failed."),
        f"Why was the control missing? {next(iter(causes.values())).statement}",
        "Why was that not caught? Pre-task checks and supervision did not verify the control was in place.",
    ]
    contributing = []
    if pack.get("similar_incidents"):
        contributing.append(
            f"{len(pack['similar_incidents'])} similar incident(s) before this one: "
            "earlier actions may not have worked."
        )
    contributing += [c for c in ["night shift", "subcontractor", "new starter", "language"] if c in text]
    return RcaOutput(
        problem_statement=problem,
        whys=whys,
        root_causes=list(causes.values())[:4],
        contributing_factors=contributing,
        confidence=0.55 if "generic" not in causes else 0.35,
        evidence_refs=_base_refs(pack),
        open_questions=["Validate each root cause with the people involved before approving actions."],
    )


# --- Compliance ---------------------------------------------------------------------------------


def _negated_near(text: str, word: str, window: int = 30) -> bool:
    """True if a negation cue appears in the same sentence shortly before (or right after) a mention of word."""
    for m in re.finditer(r"\b" + re.escape(word), text):
        before = text[max(0, m.start() - window) : m.start()].rsplit(".", 1)[-1]
        after = text[m.end() : m.end() + 15].split(".", 1)[0]
        if any(_has(f"{before} {after}", c.strip()) for c in NEGATION_CUES):
            return True
    return False


_GENERIC = {
    "where",
    "there",
    "their",
    "which",
    "before",
    "after",
    "until",
    "under",
    "about",
    "other",
    "every",
    "least",
    "within",
    "approved",
    "required",
    "protected",
    "person",
    "persons",
    "workers",
    "provided",
    "practicable",
    "specified",
}


def _stem(word: str) -> str:
    for suffix in ("ings", "ing", "ed", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


_REQ_SENTENCE = re.compile(r"[^.;]*\b(must|shall|required|is required to)\b[^.;]*[.;]", re.I)


def compliance(pack: dict) -> ComplianceOutput:
    text = _text(pack)
    domain = pack.get("prior", {}).get("triage", {}).get("domain")
    labels = _match(text, SAFETY_HAZARDS) + _match(text, QUALITY_DEFECTS)
    taxonomy = SAFETY_HAZARDS | QUALITY_DEFECTS
    hazard_terms = {_stem(w) for label in labels for kw in taxonomy[label] for w in kw.split() if len(w) >= 5}
    findings: list[ComplianceFinding] = []
    for hit in pack.get("knowledge", []):
        if hit.get("suspicious"):
            continue
        if domain in ("SAFETY", "QUALITY") and hit.get("domain") not in (domain, "BOTH", None):
            continue  # e.g. a concrete ITP is not evidence for a scaffold fall
        for m in _REQ_SENTENCE.finditer(" ".join(hit["text"].split())):
            sentence = m.group(0).strip(" -*\n")
            words = [_stem(w) for w in re.findall(r"[a-z]{5,}", sentence.lower()) if w not in _GENERIC]
            overlap = [w for w in words if _has(text, w)]
            if len(set(overlap)) < 2 and not set(overlap) & hazard_terms:
                continue  # one shared word is too weak to call a requirement relevant
            negated = any(_negated_near(text, w) for w in overlap)
            status = "LIKELY_NOT_MET" if negated else "UNCLEAR"
            findings.append(
                ComplianceFinding(
                    requirement=sentence[:400],
                    source_ref=hit["ref"],
                    source_title=f"{hit['document_title']} - {hit['section']}",
                    status=status,  # type: ignore[arg-type]
                    note=(
                        "The incident report describes this control as missing or not followed."
                        if negated
                        else f"Related terms in the report: {', '.join(sorted(set(overlap))[:5])}. Confirm on site."
                    ),
                )
            )
            if len(findings) >= 6:
                break
        if len(findings) >= 6:
            break
    return ComplianceOutput(
        findings=findings,
        confidence=0.5 if findings else 0.3,
        evidence_refs=[f"incident:{pack['incident']['id']}"] + sorted({f.source_ref for f in findings}),
        open_questions=([] if findings else ["No relevant requirement was retrieved; check the project documents."]),
    )


# --- CAPA ---------------------------------------------------------------------------------------

_CAPA_LIBRARY: dict[str, list[tuple[ActionType, str, str, str, int, str]]] = {
    # hazard/defect: (type, title, description, owner_role, due_days, verification)
    "Fall from height": [
        (
            "CORRECTIVE",
            "Reinstate edge protection at the affected area",
            "Install compliant guardrails/toe boards or cover openings at the location before work resumes.",
            "SITE_ENGINEER",
            1,
            "Photo evidence and supervisor sign-off that edge protection is complete.",
        ),
        (
            "PREVENTIVE",
            "Enforce work-at-height permit and harness checks",
            "Add a permit check and 100% tie-off spot checks to the daily supervisor round for work at height.",
            "HSE_MANAGER",
            14,
            "Two weeks of completed permit and spot-check records with no gaps.",
        ),
    ],
    "Struck by falling or moving object": [
        (
            "CORRECTIVE",
            "Set up exclusion zone below overhead work",
            "Barricade and sign the area below overhead work; tether tools.",
            "SITE_ENGINEER",
            1,
            "Exclusion zone in place on inspection.",
        ),
    ],
    "Excavation collapse / caught-in": [
        (
            "CORRECTIVE",
            "Install protective system before re-entry",
            "Shore, slope or box the excavation per the temporary works design before anyone re-enters.",
            "SITE_ENGINEER",
            1,
            "Temporary works coordinator sign-off and daily inspection record.",
        ),
        (
            "PREVENTIVE",
            "Daily excavation inspection by competent person",
            "Add excavation inspection to the daily permit, including spoil and plant setback.",
            "HSE_MANAGER",
            7,
            "Inspection register complete for every open excavation.",
        ),
    ],
    "Electrical contact": [
        (
            "CORRECTIVE",
            "Isolate and lock out the affected circuit",
            "Isolate, lock and tag the circuit; test for dead before work.",
            "SITE_ENGINEER",
            0,
            "LOTO record signed by an authorised person.",
        ),
    ],
    "Lifting operation / crane": [
        (
            "CORRECTIVE",
            "Suspend lifts until the lift plan is reviewed",
            "Review the lift plan, rigging inspection and exclusion zone with the appointed person.",
            "PROJECT_MANAGER",
            2,
            "Reviewed lift plan signed by the appointed person.",
        ),
    ],
    "Mobile plant / vehicle": [
        (
            "PREVENTIVE",
            "Segregate pedestrians from plant",
            "Update the traffic management plan with physical barriers and marked walkways.",
            "PROJECT_MANAGER",
            7,
            "Site walk confirms barriers and walkways match the plan.",
        ),
    ],
    "Cuts / sharp objects": [
        (
            "PREVENTIVE",
            "Cut-resistant gloves and rebar caps for cutting work",
            "Issue cut-level gloves for rebar work, cap exposed bar ends and add both to the task risk assessment.",
            "SAFETY_ENGINEER",
            7,
            "Spot checks show gloves worn and bar ends capped on three separate days.",
        ),
    ],
    "Missing or incorrect PPE": [
        (
            "CORRECTIVE",
            "Brief the crew on PPE requirements",
            "Hold a toolbox talk on task PPE and issue missing items.",
            "SAFETY_ENGINEER",
            2,
            "Signed toolbox talk attendance sheet.",
        ),
    ],
    "Concrete honeycombing / voids": [
        (
            "CORRECTIVE",
            "Assess and repair honeycombed area per approved method",
            "Map the defect, get engineer approval for the repair method, and repair.",
            "QA_QC_ENGINEER",
            7,
            "Repair inspected and accepted by QA/QC; NCR closed with photos.",
        ),
        (
            "PREVENTIVE",
            "Add compaction checks to the pour checklist",
            "Require vibrator count, spacing and duration checks in the concrete pour ITP.",
            "QA_QC_ENGINEER",
            14,
            "Next three pours have completed compaction checks.",
        ),
    ],
    "Reinforcement / cover nonconformance": [
        (
            "CORRECTIVE",
            "Cover survey and engineer assessment",
            "Survey cover on the element and get a structural engineer decision on acceptance or remediation.",
            "QA_QC_ENGINEER",
            5,
            "Cover meter report and engineer disposition attached to the NCR.",
        ),
        (
            "PREVENTIVE",
            "Hold point: pre-pour reinforcement inspection",
            "Make pre-pour reinforcement inspection a hold point that QA/QC must sign off.",
            "QA_QC_ENGINEER",
            7,
            "ITP updated and used on the next pour.",
        ),
    ],
    "Concrete strength / mix nonconformance": [
        (
            "CORRECTIVE",
            "Investigate low strength results",
            "Review delivery tickets and cube results; core-test the element if needed.",
            "QA_QC_ENGINEER",
            7,
            "Test results reviewed by structural engineer and disposition recorded.",
        ),
    ],
    "Cracking": [
        (
            "CORRECTIVE",
            "Monitor and assess cracks",
            "Map cracks, install tell-tales and get a structural engineer assessment.",
            "QA_QC_ENGINEER",
            7,
            "Engineer assessment and four weeks of monitoring data.",
        ),
    ],
    "Water ingress / waterproofing": [
        (
            "CORRECTIVE",
            "Locate and repair the leak path",
            "Flood test the area, find the defect and repair the membrane.",
            "QA_QC_ENGINEER",
            10,
            "Passed flood test after repair.",
        ),
    ],
    "Formwork defect": [
        (
            "PREVENTIVE",
            "Formwork sign-off before pours",
            "Formwork inspection signed by the temporary works coordinator before each pour.",
            "SITE_ENGINEER",
            7,
            "Signed checklists for the next three pours.",
        ),
    ],
}


def capa(pack: dict) -> CapaOutput:
    prior = pack.get("prior", {})
    labels: list[str] = list(prior.get("triage", {}).get("hazards", []))
    labels += prior.get("safety", {}).get("hazards", [])
    labels += prior.get("quality", {}).get("defects", [])
    seen: set[str] = set()
    actions: list[CapaProposal] = []
    for label in labels:
        for t, title, desc, owner, due, verify in _CAPA_LIBRARY.get(label, []):
            if title in seen:
                continue
            seen.add(title)
            actions.append(
                CapaProposal(
                    action_type=t,
                    title=title,
                    description=desc,
                    owner_role=owner,
                    due_in_days=due,
                    verification_criteria=verify,
                    addresses=label,
                )
            )
    for rc in prior.get("rca", {}).get("root_causes", [])[:2]:
        title = f"Address root cause: {rc['category'].title()}"
        if title not in seen:
            seen.add(title)
            actions.append(
                CapaProposal(
                    action_type="PREVENTIVE",
                    title=title,
                    description=f"Put a control in place for: {rc['statement']}",
                    owner_role="PROJECT_MANAGER",
                    due_in_days=21,
                    verification_criteria="Control documented and checked in the next audit.",
                    addresses=rc["statement"],
                )
            )
    if not actions:
        actions.append(
            CapaProposal(
                action_type="CORRECTIVE",
                title="Make the area safe and investigate",
                description="Secure the area and complete a full investigation.",
                owner_role="HSE_MANAGER",
                due_in_days=3,
                verification_criteria="Investigation report reviewed.",
                addresses="Unclassified",
            )
        )
    return CapaOutput(
        actions=actions[:8],
        confidence=0.65 if len(actions) > 1 else 0.4,
        evidence_refs=_base_refs(pack),
        open_questions=["Assign named owners and confirm due dates during review."],
    )


RULES = {
    "triage": triage,
    "safety": safety,
    "quality": quality,
    "rca": rca,
    "compliance": compliance,
    "capa": capa,
}
