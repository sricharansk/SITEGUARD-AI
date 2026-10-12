"""OSHA Severe Injury Reports (SIR) pipeline: register -> checksum -> validate -> filter construction ->
normalize -> score the triage agent against OSHA's own event coding.

    python -m app.datasets.osha_sir --input data/raw/government/osha/severeinjury.csv \
        --since 2024-01-01 --out ../docs/OSHA_SIR_EVALUATION.md

Download the CSV yourself from https://www.osha.gov/severeinjury (US federal data). This module never downloads
anything, never stores employer names or addresses in its outputs, and does not rank employers: the register in
docs/DATASETS.md forbids inferring liability from these records.

Every SIR record is an in-patient hospitalization, amputation or loss of an eye, so the expected triage severity
is HIGH or CRITICAL for all of them. OSHA's OIICS event title gives a coarse, independent label for the hazard
class (EVENT_MAP); agreement with it is a proxy, not ground truth.
"""

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from app.agents import rules

# Required columns (case/space-insensitive) with accepted aliases seen across SIR releases.
COLUMNS = {
    "id": ["id"],
    "event_date": ["eventdate", "event date"],
    "naics": ["primary naics", "primarynaics", "naics"],
    "narrative": ["final narrative", "finalnarrative", "narrative"],
    "event_title": ["eventtitle", "event title"],
    "hospitalized": ["hospitalized"],
    "amputation": ["amputation"],
}
OPTIONAL = {"nature_title": ["naturetitle", "nature title"], "source_title": ["sourcetitle", "source title"]}

# OIICS event title fragments -> Site Guard taxonomy class (first match wins, most specific first). None means the
# event has no counterpart in the taxonomy (for example machinery entanglement) and is left out of agreement.
EVENT_MAP: list[tuple[str, str | None]] = [
    ("running equipment", None),
    ("machinery", None),
    ("electric", "Electrical contact"),
    ("fire", "Fire / hot work"),
    ("explosion", "Fire / hot work"),
    ("oxygen deficiency", "Confined space"),
    ("inhalation", "Confined space"),
    ("collapsing", "Excavation collapse / caught-in"),
    ("caught in", "Excavation collapse / caught-in"),
    ("compressed or pinched", "Excavation collapse / caught-in"),
    ("fall", "Fall from height"),
    ("vehicle", "Mobile plant / vehicle"),
    ("transportation", "Mobile plant / vehicle"),
    ("struck by", "Struck by falling or moving object"),
    ("struck against", "Struck by falling or moving object"),
    ("overexertion", "Manual handling / musculoskeletal"),
    ("repetitive", "Manual handling / musculoskeletal"),
    ("bodily reaction", "Manual handling / musculoskeletal"),
    ("cut", "Cuts / sharp objects"),
    ("rubbed", "Cuts / sharp objects"),
]


class SchemaError(ValueError):
    pass


@dataclass
class Record:
    id: str
    event_date: date | None
    naics: str
    narrative: str
    event_title: str
    hospitalized: bool
    amputation: bool
    nature_title: str
    source_title: str


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def resolve_columns(header: list[str]) -> dict[str, str]:
    lookup = {_norm(h): h for h in header}
    found: dict[str, str] = {}
    missing = []
    for key, aliases in (COLUMNS | OPTIONAL).items():
        match = next((lookup[a] for a in aliases if a in lookup), None)
        if match:
            found[key] = match
        elif key in COLUMNS:
            missing.append(key)
    if missing:
        raise SchemaError(f"Missing required SIR columns: {', '.join(missing)}. Header was: {header}")
    return found


def _date(value: str) -> date | None:
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _flag(value: str) -> bool:
    try:
        return float(value or 0) > 0
    except ValueError:
        return value.strip().lower() in ("y", "yes", "true")


def read(path: Path, *, since: date | None = None, construction_only: bool = True) -> tuple[list[Record], dict]:
    """Read and normalize the CSV. Returns (records, stats). Employer and address columns are never read."""
    stats: Counter = Counter()
    out: list[Record] = []
    seen: set[str] = set()
    with path.open(newline="", encoding="utf-8-sig", errors="replace") as fh:
        reader = csv.DictReader(fh)
        cols = resolve_columns(list(reader.fieldnames or []))
        for row in reader:
            stats["rows"] += 1
            naics = (row[cols["naics"]] or "").strip().split(".")[0]
            if construction_only and not naics.startswith("23"):
                continue
            stats["construction_rows"] += 1
            rid = (row[cols["id"]] or "").strip()
            narrative = " ".join((row[cols["narrative"]] or "").split())
            if not narrative:
                stats["dropped_empty_narrative"] += 1
                continue
            if rid in seen:
                stats["dropped_duplicate_id"] += 1
                continue
            seen.add(rid)
            when = _date(row[cols["event_date"]] or "")
            if since and (when is None or when < since):
                stats["dropped_before_since"] += 1
                continue
            out.append(
                Record(
                    id=rid,
                    event_date=when,
                    naics=naics,
                    narrative=narrative[:5000],
                    event_title=(row[cols["event_title"]] or "").strip(),
                    hospitalized=_flag(row[cols["hospitalized"]]),
                    amputation=_flag(row[cols["amputation"]]),
                    nature_title=(row.get(cols.get("nature_title", ""), "") or "").strip(),
                    source_title=(row.get(cols.get("source_title", ""), "") or "").strip(),
                )
            )
    stats["kept"] = len(out)
    return out, dict(stats)


def oiics_class(event_title: str) -> str | None:
    t = event_title.lower()
    for frag, cls in EVENT_MAP:
        if frag in t:
            return cls
    return None


def triage(rec: Record) -> dict:
    pack = {
        "incident": {
            "id": rec.id,
            "title": rec.narrative[:120],
            "description": rec.narrative,
            "domain": "SAFETY",
            "people_involved": 1,
            "location": "reported",
            "immediate_actions": "reported",
        },
        "evidence": [],
        "knowledge": [],
        "similar_incidents": [],
    }
    out = rules.triage(pack)
    unclassified = out.hazards[0].startswith("No known")
    return {
        "class": None if unclassified else out.incident_class,
        "top3": [] if unclassified else out.hazards[:3],
        "severity": out.severity_candidate.value,
    }


def evaluate(records: list[Record]) -> dict:
    rows = []
    for r in records:
        t = triage(r)
        label = oiics_class(r.event_title)
        rows.append(
            {
                "id": r.id,
                "year": r.event_date.year if r.event_date else None,
                "event_title": r.event_title,
                "oiics_class": label,
                "ai_class": t["class"],
                "agree": label is not None and t["class"] == label,
                "agree_top3": label is not None and label in t["top3"],
                "ai_severity": t["severity"],
                "amputation": r.amputation,
            }
        )
    labelled = [x for x in rows if x["oiics_class"]]
    n = len(rows) or 1
    by_class: dict[str, Counter] = {}
    for x in labelled:
        by_class.setdefault(x["oiics_class"], Counter()).update(cases=1, agree=int(x["agree"]))
    return {
        "records": len(rows),
        "by_year": dict(sorted(Counter(x["year"] for x in rows).items(), key=lambda kv: str(kv[0]))),
        "mapped_to_taxonomy": len(labelled),
        "class_agreement": round(sum(x["agree"] for x in labelled) / (len(labelled) or 1), 3),
        "class_agreement_top3": round(sum(x["agree_top3"] for x in labelled) / (len(labelled) or 1), 3),
        "unclassified_by_ai": round(sum(1 for x in rows if x["ai_class"] is None) / n, 3),
        "severity_high_or_critical": round(sum(1 for x in rows if x["ai_severity"] in ("HIGH", "CRITICAL")) / n, 3),
        "severity_counts": dict(Counter(x["ai_severity"] for x in rows)),
        "amputations_rated_critical": round(
            sum(1 for x in rows if x["amputation"] and x["ai_severity"] == "CRITICAL")
            / (sum(1 for x in rows if x["amputation"]) or 1),
            3,
        ),
        "top_events": Counter(x["event_title"] for x in rows).most_common(12),
        "by_class": {k: dict(v) for k, v in sorted(by_class.items())},
        "rows": rows,
    }


def manifest(path: Path, stats: dict, since: date | None) -> dict:
    return {
        "dataset_id": "osha_severe_injury_reports",
        "source_url": "https://www.osha.gov/severeinjury",
        "file": path.name,
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
        "processed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "filter": {"naics_prefix": "23", "since": since.isoformat() if since else None},
        "stats": stats,
        "fields_kept": sorted(COLUMNS) + sorted(OPTIONAL),
        "fields_never_read": ["Employer", "Address1", "Address2", "City", "Zip", "Latitude", "Longitude"],
    }


def to_markdown(m: dict, ev: dict) -> str:
    pct = lambda v: f"{v * 100:.1f}%"  # noqa: E731
    md = [
        "# OSHA Severe Injury Reports: construction triage evaluation",
        "",
        f"Source: [OSHA Severe Injury Reports]({m['source_url']}) file `{m['file']}` "
        f"(SHA-256 `{m['sha256'][:16]}...`, {m['bytes']:,} bytes), processed {m['processed_at']} UTC by "
        "`python -m app.datasets.osha_sir`. Construction only (NAICS 23"
        + (f", events on or after {m['filter']['since']}" if m["filter"]["since"] else "")
        + ").",
        "",
        "Every record is a real severe injury (in-patient hospitalization, amputation or loss of an eye) reported to "
        "OSHA. Narratives were triaged by the offline rules agent exactly as an incident report would be. Employer "
        "and address fields were never read.",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Rows in file / construction rows / kept | {m['stats'].get('rows', 0):,} / "
        f"{m['stats'].get('construction_rows', 0):,} / {ev['records']:,} |",
        f"| Records by year | {', '.join(f'{k}: {v:,}' for k, v in ev['by_year'].items())} |",
        f"| Triage severity HIGH or CRITICAL (expected for every severe injury) | "
        f"{pct(ev['severity_high_or_critical'])} |",
        f"| Amputations rated CRITICAL | {pct(ev['amputations_rated_critical'])} |",
        f"| Records whose OIICS event maps to a Site Guard class | {ev['mapped_to_taxonomy']:,} |",
        f"| AI class agrees with OIICS-mapped class (top-1) | {pct(ev['class_agreement'])} |",
        f"| OIICS-mapped class in AI top-3 | {pct(ev['class_agreement_top3'])} |",
        f"| Narratives the AI could not classify | {pct(ev['unclassified_by_ai'])} |",
        "",
        "## Agreement by class",
        "",
        "| OIICS-mapped class | Records | AI agrees |",
        "|---|---|---|",
    ]
    for cls, c in ev["by_class"].items():
        md.append(f"| {cls} | {c['cases']:,} | {pct(c.get('agree', 0) / c['cases'])} |")
    md += ["", "## Most frequent OIICS events", "", "| Event | Records |", "|---|---|"]
    md += [f"| {e} | {n:,} |" for e, n in ev["top_events"]]
    md += [
        "",
        "## How to read this",
        "",
        "- OIICS event codes describe how the injury happened, not the full hazard picture, and the mapping in "
        "`EVENT_MAP` is coarse; disagreement is not always an AI error.",
        "- SIR covers employers under federal OSHA jurisdiction that reported; it is not a census of construction "
        "injuries. Do not use it to rank or judge employers.",
        "",
    ]
    return "\n".join(md)


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m app.datasets.osha_sir")
    ap.add_argument("--input", required=True, type=Path, help="CSV downloaded from https://www.osha.gov/severeinjury")
    ap.add_argument("--since", default=None, help="Keep events on or after this date (YYYY-MM-DD)")
    ap.add_argument("--out", default=None, help="Markdown report path")
    ap.add_argument("--processed", default=None, type=Path, help="Write normalized records + manifest here")
    args = ap.parse_args()
    since = date.fromisoformat(args.since) if args.since else None
    records, stats = read(args.input, since=since)
    m = manifest(args.input, stats, since)
    ev = evaluate(records)
    if args.processed:
        args.processed.mkdir(parents=True, exist_ok=True)
        (args.processed / "manifest.json").write_text(json.dumps(m, indent=1))
        with (args.processed / "construction_records.jsonl").open("w") as fh:
            for r, row in zip(records, ev["rows"], strict=True):
                fh.write(json.dumps({**r.__dict__, "event_date": str(r.event_date), **row}, default=str) + "\n")
    if args.out:
        Path(args.out).write_text(to_markdown(m, ev))
    print(json.dumps({k: v for k, v in ev.items() if k != "rows"}, indent=1, default=str))


if __name__ == "__main__":
    main()
