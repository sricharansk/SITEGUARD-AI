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
        "fell through",
        "fell off",
        "fragile",
        "rooflight",
        "skylight",
        "edge protection",
        "fall arrest",
        "scaffold",
        "stepladder",
        "step ladder",
        "hop-up",
        "podium steps",
        "toppled off",
        "safety net",
        "netting",
        "stair void",
        "lift shaft",
        "hole below",
        "open edge",
        "leading edge",
        "went through",
        "fragile roof",
        "roof sheet",
    ],
    "Struck by falling or moving object": [
        "dropped",
        "falling object",
        "struck",
        "hit by",
        "landed near",
        "falling",
        "kicked off",
        "knocked off",
        "came down",
        "toe board",
        "brick guard",
        "struck by",
        "hit him",
        "hit her",
        "hit them",
        "whipped",
        "flew",
        "debris",
        "tool lanyard",
        "tethered",
        "drop zone",
        "dropped object",
        "rolled off",
        "fell onto",
        "fell on",
    ],
    "Excavation collapse / caught-in": [
        "trench",
        "excavation",
        "collapse",
        "cave-in",
        "cave in",
        "caved in",
        "shoring",
        "slumped",
        "slumping",
        "ran in",
        "run in",
        "spoil",
        "trench box",
        "battered",
        "buried",
        "engulf",
        "sheet pil",
        "dig",
        "gave way",
        "groundworks",
    ],
    "Electrical contact": [
        "electric shock",
        "electrical shock",
        "electrical burn",
        "electrocut",
        "exposure to electricity",
        "shock",
        "live cable",
        "energised",
        "energized",
        "arc flash",
        "lockout",
        "power cable",
        "underground cable",
        "kv",
        "high voltage",
        "lv cable",
        "hv cable",
        "cable strike",
        "flashover",
        "110v",
        "240v",
        "230v",
        "extension lead",
        "festoon",
        "exposed copper",
        "copper showing",
        "rcd",
        "distribution board",
        "live wire",
        "overhead line",
        "power line",
        "cat scan",
        "cat and genny",
        "electrical",
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
        "crane",
        "outrigger",
        "spreader mat",
        "slinger",
        "signaller",
        "tag line",
        "on the hook",
        "shackle",
        "lifting anchor",
        "lifting chain",
        "loler",
        "swl",
        "safe working load",
        "lifting accessor",
        "lifting beam",
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
        "slew",
        "roller",
        "haul road",
        "run over",
        "ran over",
        "overturn",
        "tipped over",
        "rops",
        "seat belt",
        "digger",
        "loader",
        "lorry",
        "wagon",
        "tipper",
        "plant operator",
        "reversing",
    ],
    "Fire / hot work": [
        "caught fire",
        "on fire",
        "small fire",
        "a fire",
        "the fire",
        "fire service",
        "fire watch",
        "smoulder",
        "ignit",
        "flame",
        "hot work",
        "welding spark",
        "flammable",
        "gas cylinder",
        "fire",
        "torch",
        "scorch",
        "smoke",
        "extinguisher",
        "propane",
        "lpg",
        "blowtorch",
        "fire brigade",
        "muster",
        "charred",
        "sparks",
        "burning",
        "fire alarm",
    ],
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
        "safety glasses",
        "glasses",
        "visor",
        "face shield",
        "respirator",
        "dust mask",
        "ear defenders",
        "hearing protection",
        "not wearing",
        "eyewash",
        "arc eye",
        "rpe",
        "ffp3",
        "face-fit",
        "face fit",
        "cut-resistant",
        "chin strap",
        "no gloves",
        "welding mask",
        "welding helmet",
        "hearing",
    ],
    "Confined space": [
        "confined space",
        "manhole",
        "tank entry",
        "oxygen",
        "sewer",
        "chamber",
        "gas monitor",
        "fumes",
        "lift pit",
        "tank",
        "sump",
        "overcome",
        "dizzy",
        "ventilation",
        "h2s",
        "carbon monoxide",
        "gas test",
        "attenuation",
        "solvent",
        "inspection chamber",
    ],
    "Cuts / sharp objects": [
        "cut his",
        "cut her",
        "cut their",
        "laceration",
        "stitches",
        "sharp edge",
        "nicked",
        "blade",
        "knife",
        "stanley",
        "sharp",
        "rebar cap",
        "protruding",
        "uncapped",
        "sliced",
        "gash",
        "cut to",
        "cut on",
        "cut himself",
        "cut herself",
        "cut themselves",
        "cut hand",
        "cut finger",
        "first aid box",
    ],
    "Manual handling / musculoskeletal": [
        "manual handling",
        "back injury",
        "strain",
        "lifting by hand",
        "by hand",
        "lower back",
        "pulled his back",
        "pulled her back",
        "pulled their back",
        "hurt his back",
        "hurt her back",
        "back pain",
        "lugging",
        "carrying",
        "heavy",
        "kg bag",
        "twisted",
        "hernia",
        "musculoskeletal",
        "sprain",
        "shoulder",
        "team lift",
        "awkward load",
        "repetitive",
    ],
}

QUALITY_DEFECTS: dict[str, list[str]] = {
    "Concrete honeycombing / voids": [
        "honeycomb",
        "void",
        "segregation",
        "blowhole",
        "exposed aggregate",
        "poor compaction",
        "compaction",
        "poker",
        "vibrat",
        "air pocket",
        "blow hole",
        "scabby",
    ],
    "Cracking": [
        "crack",
        "cracking",
        "spalling",
        "crazing",
        "craze",
        "hairline",
        "fissure",
        "shrinkage",
    ],
    "Reinforcement / cover nonconformance": [
        "concrete cover",
        "cover meter",
        "cover of",
        "spacers",
        "bar spacing",
        "lap length",
        "reinforcement inspection",
        "covermeter",
        "low cover",
        "cover to",
        "cover on",
        "rebar",
        "reinforcement",
        "bar size",
        "bar bending",
        "starter bars",
        "bottom mat",
        "top mat",
        "links",
        "chairs",
        "laps",
        "bars sitting",
        "steel fixer",
        "steelfixer",
        "fixers",
    ],
    "Concrete strength / mix nonconformance": [
        "cube",
        "cylinder result",
        "cylinder strength",
        "test cylinder",
        "compressive strength",
        "slump test",
        "mm slump",
        "slump of",
        "slump class",
        "slump was",
        "slump result",
        "mix design",
        "w/c ratio",
        "delivery ticket",
        "concrete grade",
        "lower grade",
        "wrong grade",
        "c25",
        "c28",
        "c30",
        "c32",
        "c35",
        "c40",
        "stiff mix",
        "wet mix",
        "added water",
        "water added",
        "retarder",
        "mix",
        "cylinders",
        "cubes",
    ],
    "Formwork defect": [
        "formwork failure",
        "formwork failed",
        "formwork collapse",
        "formwork movement",
        "shuttering failure",
        "bulge",
        "form failure",
        "grout loss",
        "blowout",
        "shutter",
        "formwork moved",
        "push-pull prop",
        "formwork",
        "table form",
        "wall form",
        "tie failed",
        "failed tie",
        "waler",
        "falsework",
        "back-prop",
        "backprop",
        "props",
        "propped",
        "deflect",
        "struck early",
        "early striking",
        "plywood",
        "form face",
        "shuttering",
    ],
    "Dimensional / alignment tolerance": [
        "misalign",
        "out of plumb",
        "out of level",
        "dimensional",
        "out of tolerance",
        "setting-out error",
        "out of line",
        "out of position",
        "wrong position",
        "setting-out position",
        "off their setting-out",
        "off line",
        "off level",
        "not plumb",
        "out of square",
        "wrong level",
        "gridline",
        "grid line",
        "cast-in",
        "holding-down bolt",
        "holding down bolt",
        "survey",
        "total station",
        "too high",
        "too low",
        "deviation",
        "tolerance",
        "setting out",
        "line and level",
    ],
    "Water ingress / waterproofing": [
        "leaking",
        "water leak",
        "leaked into",
        "seepage",
        "damp",
        "moisture",
        "waterproof",
        "ingress",
        "water coming through",
        "water through",
        "water was coming",
        "leak",
        "tanking",
        "membrane",
        "waterstop",
        "hydrophilic",
        "construction joint",
        "kicker joint",
        "flashing",
        "upstand",
        "puddl",
        "drip",
        "wet patch",
        "flood test",
    ],
    "Welding / steelwork defect": [
        "welds",
        "site weld",
        "fillet weld",
        "butt weld",
        "weld defect",
        "porosity",
        "undercut",
        "torque",
        "finger tight",
        "splice",
        "steel connection",
        "weld",
        "lack of fusion",
        "spatter",
        "ndt",
        "mpi",
        "ultrasonic",
        "galvanis",
        "intumescent",
        "base plate",
        "bolted connection",
        "column splice",
        "steelwork",
        "steel erector",
    ],
    "Material nonconformance": [
        "wrong material",
        "substitut",
        "non-conforming material",
        "expired",
        "batch",
        "submittal",
        "different product",
        "unapproved",
        "wrong spec",
        "wrong product",
        "wrong colour",
        "wrong color",
        "wrong size",
        "delivery note",
        "mill cert",
        "certificate",
        "heat number",
        "quarantin",
        "goods-in",
        "goods in",
        "not to spec",
        "specification",
        "instead of",
        "spec",
    ],
}

CRITICAL_WORDS = [
    "fatal",
    "fatality",
    "death",
    "died",
    "amputat",
    "collapse",
    "caved in",
    "buried",
    "unconscious",
    "crushed",
    "high voltage",
    "kv",
]
HIGH_WORDS = [
    "hospital",
    "fracture",
    "broken",
    "lost time",
    "serious",
    "structural",
    "load-bearing",
    "failed",
    "off work",
    "fire service",
    "fire brigade",
    "evacuat",
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
    # Sentence breaks between fields, so a phrase cannot run from the title into the description.
    return ". ".join(p.strip().rstrip(".") for p in parts if p and p.strip()).lower()


def _has(text: str, word: str) -> bool:
    """Word-prefix match: 'revers' matches 'reversed', but 'ppe' does not match 'stepped'."""
    return re.search(r"\b" + re.escape(word), text) is not None


# Keywords that also appear in unrelated contexts ("stair void", "struck a pipe", "kept dry") count half.
WEAK_WORDS = {
    "void",
    "collapse",
    "struck",
    "shock",
    "strain",
    "by hand",
    "damp",
    "moisture",
    "batch",
    "chamber",
    "oxygen",
    "fumes",
    "position",
    "dropped",
    "fell off",
    "fell through",
    "edge",
    "gloves",
    "hoist",
    "slab edge",
    "roof edge",
    "not wearing",
    "formwork",
    "glasses",
    "lift shaft",
    "quarantin",
    "fire",
    "falling",
    "scaffold",
    "dig",
    "mix",
    "spec",
    "instead of",
    "heavy",
    "carrying",
    "shoulder",
    "sharp",
    "tank",
    "leak",
    "rebar",
    "reinforcement",
    "electrical",
    "sparks",
    "smoke",
    "certificate",
    "survey",
    "props",
    "links",
    "chairs",
    "fixers",
    "flew",
    "debris",
    "laps",
    "specification",
    "roller",
    "loader",
    "lorry",
    "burning",
    "blade",
    "membrane",
    "weld",
    "steelwork",
    "netting",
    "went through",
    "spoil",
    "buried",
    "compaction",
    "vibrat",
    "propped",
    "deflect",
    "plywood",
    "solvent",
    "ventilation",
    "drip",
    "cubes",
    "cylinders",
    "starter bars",
    "repetitive",
    "knife",
    "first aid box",
    "overcome",
    "dizzy",
    "flashing",
    "upstand",
    "hearing",
}
# An object (not a person) falling or being dropped: "a brick fell off the platform", "bolt dropped from".
_OBJECT_FELL = re.compile(
    r"\b(brick|block|bolt|nut|tool|hammer|spanner|wrench|scaffold board|board|plank|pipe|tube|clip|coupler|fitting|"
    r"debris|material|panel|sheet|bucket|load|object|kerb|stone|tile|timber|bar|rebar|bracket|drill|grinder|"
    r"glass|pane|slate|batten|bag|pallet|beam|section)s?\b[^.]{0,60}?\b(fell|dropped|falling|came down|"
    r"came loose|landed|toppled|slid off|blew off)"
)
# "12 mm off line", "40mm low", "15 mm out": a measured deviation is a tolerance problem.
_DEVIATION = re.compile(r"\b\d+(?:\.\d+)? ?mm\b[^.]{0,25}?\b(off|out|low|high|short|over|proud|too|outside|beyond)\b")
# A person hit by something: "striking a labourer on the leg", "hit the fixer".
_PERSON_STRUCK = re.compile(
    r"\b(struck|striking|hit|hitting|knocked)\b (?:a |the |his |her |their |one |another )?"
    r"(he|she|him|her|them|worker|operative|man|labourer|laborer|fixer|fitter|carpenter|joiner|electrician|"
    r"apprentice|engineer|banksman|slinger|driver|operator|colleague|hose man|lad)\b"
)
# A person falling or nearly falling.
_PERSON_FELL = re.compile(
    r"\b(he|she|they|worker|operative|man|labourer|laborer|roofer|scaffolder|carpenter|joiner|electrician|painter|"
    r"fixer|erector|apprentice|engineer|plumber|bricklayer|brickie|driver|operator|someone|colleague|lad)\b[^.]{0,50}?"
    r"\b(fell|slipped|tripped|toppled|went over|went through|lost (?:his|her|their) (?:footing|balance)|"
    r"dropped (?:about|around|roughly|some)? ?\d)"
)


def _scores(text: str, taxonomy: dict[str, list[str]], title: str = "") -> dict[str, float]:
    """Weighted keyword evidence per label: title matches count double, ambiguous words count half."""
    out: dict[str, float] = {}
    for name, words in taxonomy.items():
        s = 0.0
        for w in words:
            if _has(text, w):
                s += (0.5 if w in WEAK_WORDS else 1.0) * (2.0 if title and _has(title, w) else 1.0)
        if s:
            out[name] = s
    if taxonomy is SAFETY_HAZARDS:
        objects, people = _OBJECT_FELL.search(text), _PERSON_FELL.search(text)
        if objects or _PERSON_STRUCK.search(text):
            out["Struck by falling or moving object"] = out.get("Struck by falling or moving object", 0.0) + 2.0
        if people:
            out["Fall from height"] = out.get("Fall from height", 0.0) + 2.0
        elif objects and "Fall from height" in out:
            out["Fall from height"] = max(0.0, out["Fall from height"] - 1.5)  # the object fell, not a person
            if not out["Fall from height"]:
                del out["Fall from height"]
    if taxonomy is QUALITY_DEFECTS and _DEVIATION.search(text):
        out["Dimensional / alignment tolerance"] = out.get("Dimensional / alignment tolerance", 0.0) + 1.5
    return out


def _ranked(scores: dict[str, float], taxonomy: dict[str, list[str]]) -> list[str]:
    order = list(taxonomy)
    return [n for n in sorted(scores, key=lambda n: (-scores[n], order.index(n))) if scores[n] > 0]


def _match(text: str, taxonomy: dict[str, list[str]], title: str = "") -> list[str]:
    """Labels ordered by weighted keyword evidence (ties keep taxonomy order)."""
    return _ranked(_scores(text, taxonomy, title), taxonomy)


def classify(pack: dict, min_score: float = 1.0) -> tuple[list[str], list[str], Domain | None]:
    """Safety labels, quality labels and the domain the evidence supports (None when nothing matched).

    BOTH needs real evidence on both sides; a single incidental word ("stair void", "waterproofing operative")
    does not turn a safety event into a quality one or the reverse."""
    text, title = _text(pack), pack["incident"]["title"].lower()
    s, q = _scores(text, SAFETY_HAZARDS, title), _scores(text, QUALITY_DEFECTS, title)
    top_s, top_q = max(s.values(), default=0.0), max(q.values(), default=0.0)
    # A label needs more than one ambiguous word behind it: "tower quarantined" alone should not add a material
    # defect and its actions to a fall from height. The strongest label always clears this (see below).
    hazards = [n for n in _ranked(s, SAFETY_HAZARDS) if s[n] >= min_score]
    defects = [n for n in _ranked(q, QUALITY_DEFECTS) if q[n] >= min_score]
    if max(top_s, top_q) < 1.0:  # one ambiguous word is not enough to classify
        return [], [], None
    if min(top_s, top_q) >= 1.5 and min(top_s, top_q) >= max(top_s, top_q) / 3:
        return hazards, defects, Domain.BOTH
    return hazards, defects, (Domain.SAFETY if top_s >= top_q else Domain.QUALITY)


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
    """Add the taxonomy labels of confirmed photo observations to those found in the text."""
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
    high_energy = bool(set(hazards or []) & HIGH_ENERGY)
    if any(_has(text, w) for w in NEAR_MISS_WORDS) or _has(text, "not struck") or _has(text, "no one was"):
        c = max(c, 4 if high_energy else 3)
    elif high_energy and people > 0:
        c = max(c, 4)  # a person was exposed to a high-energy hazard: rate the credible outcome
    return c


STRUCTURAL_WORDS = [
    "structural",
    "load-bearing",
    "column",
    "beam",
    "slab",
    "transfer",
    "truss",
    "retaining wall",
    "core wall",
    "shear wall",
    "foundation",
    "raft",
]


def _quality_consequence(text: str) -> int:
    """A defect in a structural element is Major (4); other defects are Moderate (3)."""
    if any(_has(text, w) for w in CRITICAL_WORDS):
        return 5
    return 4 if any(_has(text, w) for w in STRUCTURAL_WORDS) else 3


def _severity_for(consequence: int) -> Severity:
    return {5: Severity.CRITICAL, 4: Severity.HIGH, 3: Severity.MEDIUM}.get(consequence, Severity.LOW)


# --- Triage -------------------------------------------------------------------------------------


def triage(pack: dict) -> TriageOutput:
    inc = pack["incident"]
    text = _text(pack)
    hazards, defects, found = classify(pack)
    domain = found or Domain(inc["domain"])
    # Severity weighs every cue, weak ones included, so dropping a weak label never lowers it.
    all_hazards, all_defects, _ = classify(pack, min_score=0.0)
    if inc["domain"] == Domain.BOTH and all_hazards and all_defects:
        domain = Domain.BOTH  # never narrow a reported BOTH while both sides have some evidence
    consequence = _consequence(text, inc.get("people_involved", 0), all_hazards)
    if all_defects:
        consequence = max(consequence, _quality_consequence(text))
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

    # The primary class comes from the domain the evidence supports; the other side's labels follow as secondary.
    labels = defects + hazards if domain == Domain.QUALITY else hazards + defects
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
    structural = any(_has(text, w) for w in STRUCTURAL_WORDS)
    consequence = _quality_consequence(text)
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
    "lockout": ("PROCESS", "Isolation and lockout were not applied before work near electrical systems."),
    "gas test": ("PROCESS", "The atmosphere was not tested before entry."),
    "fire watch": ("PROCESS", "Hot work controls (permit, fire watch, extinguisher) were not applied."),
    "certificat": ("MATERIALS", "Material or qualification certificates were not checked against requirements."),
    "qualification": ("PEOPLE", "The worker's qualification for the task was not checked before work started."),
    "setting-out": ("PROCESS", "Setting-out was not independently checked before the next stage of work."),
    "out of service": ("EQUIPMENT", "Equipment needed for the safe method was out of service with no alternative."),
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
        (
            "PREVENTIVE",
            "Weekly inspection of temporary electrical supplies",
            "Inspect temporary leads and boards weekly, check RCD protection and remove damaged cables from use.",
            "SITE_ENGINEER",
            7,
            "Inspection register and RCD trip-test records for four consecutive weeks.",
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
        (
            "PREVENTIVE",
            "Control water added to concrete on site",
            "Ban water addition on site without the QA/QC engineer's approval and record slump for every truck.",
            "QA_QC_ENGINEER",
            14,
            "Delivery tickets and slump records for the next five pours show no unapproved water.",
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
            "CORRECTIVE",
            "Inspect and make good the failed formwork section",
            "Stop pours on the element, inspect ties and walers, and get a temporary works decision before reuse.",
            "SITE_ENGINEER",
            2,
            "Temporary works coordinator inspection record for the repaired formwork.",
        ),
        (
            "PREVENTIVE",
            "Formwork sign-off before pours",
            "Formwork inspection signed by the temporary works coordinator before each pour.",
            "SITE_ENGINEER",
            7,
            "Signed checklists for the next three pours.",
        ),
    ],
    "Fire / hot work": [
        (
            "CORRECTIVE",
            "Stop hot work until permit and fire watch are in place",
            "Suspend hot work in the area, remove combustibles and restart only under a hot work permit.",
            "SITE_ENGINEER",
            0,
            "Hot work permit with fire watch and extinguisher check signed for each task.",
        ),
        (
            "PREVENTIVE",
            "Weekly hot work permit audit",
            "Audit hot work permits weekly against the tasks done, including the fire watch after work stops.",
            "HSE_MANAGER",
            14,
            "Two weekly audits show every hot work task had a permit and a fire watch.",
        ),
    ],
    "Confined space": [
        (
            "CORRECTIVE",
            "Suspend entry until permit, gas test and standby are in place",
            "No entry to the space without a confined space permit, continuous gas monitoring and a standby person.",
            "HSE_MANAGER",
            0,
            "Signed confined space permit with gas readings, standby person and rescue plan.",
        ),
        (
            "PREVENTIVE",
            "Confined space register and entrant training",
            "List every confined space on site, sign them, and train entrants and standby persons.",
            "SAFETY_ENGINEER",
            14,
            "Register complete, signs in place and training records for all entrants.",
        ),
    ],
    "Manual handling / musculoskeletal": [
        (
            "PREVENTIVE",
            "Manual handling assessment and lifting aids",
            "Assess the task, provide mechanical aids or a working goods lift, and brief the crew on safe loads.",
            "SAFETY_ENGINEER",
            10,
            "Assessment issued and aids in use on a follow-up inspection.",
        ),
    ],
    "Dimensional / alignment tolerance": [
        (
            "CORRECTIVE",
            "Survey and engineer disposition of the out-of-tolerance element",
            "Survey the element as built and get a structural engineer decision to accept, repair or replace.",
            "QA_QC_ENGINEER",
            5,
            "As-built survey and engineer disposition recorded on the NCR.",
        ),
        (
            "PREVENTIVE",
            "Independent check survey before pours",
            "Add an independent check survey of setting-out as a hold point before each pour or erection.",
            "SITE_ENGINEER",
            7,
            "Signed check-survey records for the next three elements.",
        ),
    ],
    "Welding / steelwork defect": [
        (
            "CORRECTIVE",
            "NDT and repair of the defective welds",
            "Test the affected welds by NDT, repair by a qualified welder and re-test.",
            "QA_QC_ENGINEER",
            7,
            "NDT reports show the repaired welds accepted.",
        ),
        (
            "PREVENTIVE",
            "Check welder qualifications before welding",
            "Check every welder's qualification against the welding procedure before they start work.",
            "QA_QC_ENGINEER",
            7,
            "Welder register checked against everyone welding on site.",
        ),
    ],
    "Material nonconformance": [
        (
            "CORRECTIVE",
            "Quarantine and replace the non-conforming material",
            "Tag and quarantine the material, raise an NCR and replace it with approved material.",
            "QA_QC_ENGINEER",
            2,
            "Material quarantined and tagged; NCR shows replacement with approved material.",
        ),
        (
            "PREVENTIVE",
            "Receiving inspection against approved submittals",
            "Check every delivery's certificates against the approved submittal before it is unloaded.",
            "QA_QC_ENGINEER",
            14,
            "Two weeks of delivery checks with certificates matched to submittals.",
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
