"""Resolve every open incident in the demo project through the real product workflow, over HTTP, and write the
results report (docs/RESULTS.md) plus one investigation report per incident (docs/reports/).

Usage:
    python scripts/resolve_all.py --base-url http://localhost:8000 --out docs/RESULTS.md --reports-dir docs/reports

Needs a freshly seeded API (SITEGUARD_SEED_DEMO_DATA=true). The people and decisions are scripted, but every number
in the report comes from the API: agents, deterministic risk, cited compliance mapping, approvals, verification,
escalation and closure all run for real. Incidents and procedures are synthetic.
"""

import argparse
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from demo_walkthrough import Api, table, walkthrough  # noqa: E402,I001

SEVERITY_ORDER = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


def site_note(inc: dict) -> bytes:
    return (
        f"Site note for {inc['reference']} ({inc['location'] or 'location not given'}).\n"
        f"Reported: {inc['title']}.\nImmediate actions: {inc['immediate_actions'] or 'none recorded'}.\n"
    ).encode()


def review_policy(action: dict, others: int) -> tuple[str, str, dict | None]:
    """The scripted reviewer: approve specific controls, reject generic root-cause actions already covered."""
    if action["title"].startswith("Address root cause") and others >= 2:
        return "REJECT", "Covered by the specific corrective and preventive actions approved for this incident.", None
    return "APPROVE", "Proportionate to the risk and matches the site conditions.", None


def resolve(api: Api, inc: dict) -> dict:
    iid = inc["id"]
    row: dict = {
        "reference": inc["reference"],
        "title": inc["title"],
        "domain": inc["domain"],
        "reported_severity": inc["severity"],
        "start_status": inc["status"],
    }
    ws = api.call("GET", f"/incidents/{iid}", "hse")

    if inc["status"] in ("REPORTED", "TRIAGED", "UNDER_INVESTIGATION"):
        api.http.post(
            f"/incidents/{iid}/evidence",
            headers=api.as_("site"),
            files={"file": ("site-note.txt", site_note(inc), "text/plain")},
            data={"description": "Site engineer's note written at the scene"},
        )
        started = time.perf_counter()
        res = api.call("POST", f"/incidents/{iid}/investigate", "safety" if inc["domain"] != "QUALITY" else "qa")
        row["investigation_ms"] = round((time.perf_counter() - started) * 1000)
        row["flags"] = res["flags"]
        ws = api.call("GET", f"/incidents/{iid}", "hse")

    runs = {r["agent"]: r for r in ws["agent_runs"]}
    tri = runs["triage"]["output"] if "triage" in runs else {}
    comp = runs["compliance"]["output"] if "compliance" in runs else {"findings": []}
    row.update(
        ai_class=tri.get("incident_class", ""),
        ai_domain=tri.get("domain", ""),
        ai_severity=tri.get("severity_candidate", ""),
        risk=f"{ws['risk']['band']} ({ws['risk']['score']})" if ws["risk"] else "",
        findings=len(comp["findings"]),
        not_met=sum(1 for f in comp["findings"] if f["status"] == "LIKELY_NOT_MET"),
        agents=len(ws["agent_runs"]),
        flagged=sum(1 for r in ws["agent_runs"] if r["needs_human_review"]),
    )

    # Human review of every proposal still waiting.
    pending = [a for a in ws["capa"] if a["approval_status"] == "PENDING_REVIEW"]
    decisions: Counter = Counter()
    for a in pending:
        decision, reason, changes = review_policy(a, len(pending) - 1)
        reviewer = "hse" if a["critical"] else "pm"
        body = {"decision": decision, "reason": reason}
        if changes:
            body["changes"] = changes
        api.call("POST", f"/capa/{a['id']}/review", reviewer, json=body)
        decisions[decision] += 1
        decisions[f"by_{reviewer}"] += 1

    ws = api.call("GET", f"/incidents/{iid}", "hse")
    active = [a for a in ws["capa"] if a["approval_status"] in ("APPROVED", "MODIFIED")]
    row["proposed"] = sum(1 for a in ws["capa"] if a["ai_generated"] and a["approval_status"] != "SUPERSEDED")
    row["approved"] = len(active)
    row["rejected"] = sum(1 for a in ws["capa"] if a["approval_status"] == "REJECTED")
    row["reviewed_now"] = dict(decisions)
    row["_active"] = active
    return row


def work_and_close(api: Api, row: dict, iid: str, site_id: str, fail_once: set[str]) -> None:
    verifier = "qa" if row["domain"] == "QUALITY" else "safety"
    failed = 0
    for a in row["_active"]:
        if a["work_status"] in ("NOT_STARTED", "IN_PROGRESS", "VERIFICATION_FAILED"):
            api.call(
                "PATCH",
                f"/capa/{a['id']}/progress",
                "site",
                json={"work_status": "COMPLETED", "assignee_id": site_id, "note": "Done; photos attached"},
            )
    for a in row["_active"]:
        if a["work_status"] == "VERIFIED":
            continue
        if row["reference"] in fail_once and failed == 0:
            api.call(
                "POST",
                f"/capa/{a['id']}/verify",
                verifier,
                json={"effective": False, "notes": "Control incomplete at re-inspection; redo and re-submit."},
            )
            failed += 1
            api.call(
                "PATCH",
                f"/capa/{a['id']}/progress",
                "site",
                json={"work_status": "COMPLETED", "note": "Reworked after failed verification"},
            )
        api.call(
            "POST",
            f"/capa/{a['id']}/verify",
            verifier,
            json={"effective": True, "notes": "Checked on site; control in place and working."},
        )
    row["failed_verifications"] = failed
    closer = "hse" if row["reported_severity"] == "CRITICAL" else "pm"
    # The incident cannot close while an AI conflict has no recorded human decision.
    decisions = []
    for c in api.call("GET", f"/incidents/{iid}/conflicts", closer):
        if c["status"] == "OPEN":
            note = "Reviewed both sides; the recorded severity and the human risk decision stand."
            api.call("POST", f"/conflicts/{c['id']}/resolve", closer, json={"resolution": note})
            decisions.append(c["kind"])
    row["conflict_decisions"] = decisions
    closed = api.call(
        "POST",
        f"/incidents/{iid}/close",
        closer,
        json={"note": "All approved actions verified effective; lessons shared at the toolbox talk."},
    )
    row["final_status"] = closed["status"]
    row["closed_by"] = {"hse": "HSE manager", "pm": "Project manager"}[closer]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--out", default="docs/RESULTS.md")
    ap.add_argument("--reports-dir", default="docs/reports")
    args = ap.parse_args()
    api = Api(args.base_url)
    reports = Path(args.reports_dir)
    reports.mkdir(parents=True, exist_ok=True)
    health = api.http.get("/health").json()["data"]
    project = next(p for p in api.call("GET", "/projects", "pm") if p["code"] == "RMT-01")
    pid = project["id"]
    ids = {w: api.call("GET", "/me", w)["id"] for w in ("site", "safety", "qa", "hse", "pm")}
    before = api.call("GET", "/dashboard", "pm", params={"project_id": pid})
    all_before = api.call("GET", f"/projects/{pid}/incidents", "pm")

    md = [
        "# Site Guard AI: results",
        "",
        f"Generated by `scripts/resolve_all.py` against the running stack on {datetime.now(UTC):%d %B %Y %H:%M} UTC. "
        f"API environment `{health['env']}`, AI provider `{health['ai_provider']}`.",
        "",
        "> All incidents are **synthetic** (`data/seed/incidents.yaml`) and the knowledge base is synthetic site "
        "procedures (`data/seed/knowledge/`). The reviewers' decisions are scripted; everything else (triage, "
        "investigation, risk scores, cited requirements, proposed actions, permission checks, verification, "
        "escalation, closure and dashboard numbers) is produced by the real API and is not typed by hand. "
        "Agent quality on a labelled held-out set is in [EVALUATION.md](EVALUATION.md).",
        "",
        f"## 1. Portfolio before resolution ({project['name']})",
        "",
        table([[k.replace("_", " "), v] for k, v in before["totals"].items()], ["Metric", "Value"]),
        "",
        "Incidents by status: " + ", ".join(f"{k} {v}" for k, v in sorted(before["by_status"].items())) + ".  ",
        "By domain: " + ", ".join(f"{k} {v}" for k, v in sorted(before["by_domain"].items())) + ".",
        "",
    ]

    # 2. One new incident in full detail.
    body, new_id = walkthrough(api, pid, h="###")
    md += [
        "## 2. A new incident, start to finish",
        "",
        "A site engineer reports a fall from a scaffold tower. Everything below is the API's response.",
        "",
    ]
    md += body
    api.http.get(f"/incidents/{new_id}/report", headers=api.as_("pm"))

    # 3. Resolve everything else that is open.
    open_incidents = [i for i in all_before if i["status"] != "CLOSED"]
    quality = [i for i in open_incidents if i["domain"] == "QUALITY"]
    fail_once = {quality[0]["reference"]} if quality else set()
    rows = []
    for inc in sorted(open_incidents, key=lambda i: i["reference"]):
        rows.append((inc["id"], resolve(api, inc)))
    escalation = api.call("POST", "/capa/escalate-overdue", "pm", json={"project_id": pid})["escalations"]
    pm_notes = api.call("GET", "/notifications", "pm", params={"unread_only": True})
    for iid, row in rows:
        work_and_close(api, row, iid, ids["site"], fail_once)
    closed_before = [i for i in all_before if i["status"] == "CLOSED"]

    md += [
        "## 3. Every open incident resolved",
        "",
        f"{len(rows)} incidents were open ({sum(1 for _, r in rows if r['domain'] == 'SAFETY')} safety, "
        f"{sum(1 for _, r in rows if r['domain'] == 'QUALITY')} quality, "
        f"{sum(1 for _, r in rows if r['domain'] == 'BOTH')} both). Incidents still at REPORTED were investigated "
        "by the agents first; every proposal was reviewed by a person; critical actions went to the HSE manager; "
        "work was done by the site engineer and verified by someone else.",
        "",
        table(
            [
                [
                    f"[{r['reference']}](reports/{r['reference']}.md)",
                    r["title"],
                    r["domain"],
                    r["start_status"],
                    r["ai_class"],
                    f"{r['reported_severity']} / {r['ai_severity']}",
                    r["risk"],
                    f"{r['findings']} ({r['not_met']} likely not met)",
                    f"{r['approved']} approved, {r['rejected']} rejected",
                    r["failed_verifications"],
                    r["final_status"],
                ]
                for _, r in rows
            ],
            [
                "Ref",
                "Incident",
                "Domain",
                "Started at",
                "AI class",
                "Severity reported / AI",
                "Risk (score)",
                "Cited requirements",
                "Actions",
                "Failed verifications",
                "Final",
            ],
        ),
        "",
    ]
    flags = [(r["reference"], f) for _, r in rows for f in r.get("flags", [])]
    if flags:
        md += ["Conflicts the agents raised for human attention:", ""]
        md += [f"- {ref}: {f}" for ref, f in flags] + [""]
    decided = sum(len(r.get("conflict_decisions", [])) for _, r in rows)
    if decided:
        md += [
            f"Before closing, the closer recorded a decision on each of the {decided} open conflict(s) "
            "(`POST /conflicts/{id}/resolve`); an incident cannot close while a conflict has no recorded decision.",
            "",
        ]
    md += [
        "### Escalation of overdue actions",
        "",
        f"Before the work was completed, the project manager ran the escalation job "
        f"(`POST /capa/escalate-overdue`; daily job `python -m app.jobs escalate-overdue`). It sent "
        f"{len(escalation)} escalation(s):",
        "",
    ]
    md += (
        [
            table(
                [
                    [e["incident_reference"], e["title"], e["days_overdue"], e["level"], e["recipients"]]
                    for e in escalation
                ],
                ["Ref", "Action", "Days overdue", "Level", "People notified"],
            ),
            "",
        ]
        if escalation
        else ["No action was overdue.", ""]
    )
    md += [
        f"Unread notifications in the project manager's inbox at that point: {len(pm_notes)} "
        f"({', '.join(f'{k} {v}' for k, v in Counter(n['kind'] for n in pm_notes).items())}).",
        "",
    ]

    # 4. Safety vs quality summary.
    by_domain: dict[str, list[dict]] = defaultdict(list)
    for _, r in rows:
        by_domain[r["domain"]].append(r)
    md += [
        "## 4. Safety and quality outcomes",
        "",
        table(
            [
                [
                    d,
                    len(rs),
                    sum(r["approved"] for r in rs),
                    sum(r["rejected"] for r in rs),
                    sum(r["findings"] for r in rs),
                    sum(r["failed_verifications"] for r in rs),
                    sum(1 for r in rs if r["final_status"] == "CLOSED"),
                ]
                for d, rs in sorted(by_domain.items())
            ],
            [
                "Domain",
                "Incidents resolved",
                "Actions approved",
                "Actions rejected",
                "Cited requirements",
                "Failed verifications (reworked)",
                "Closed",
            ],
        ),
        "",
    ]
    ai_vs_reported = Counter(
        "AI higher"
        if SEVERITY_ORDER.index(r["ai_severity"]) > SEVERITY_ORDER.index(r["reported_severity"])
        else "AI lower"
        if SEVERITY_ORDER.index(r["ai_severity"]) < SEVERITY_ORDER.index(r["reported_severity"])
        else "same"
        for _, r in rows
        if r["ai_severity"]
    )
    md += [
        "AI triage severity compared with the reporter's: "
        + ", ".join(f"{k} {v}" for k, v in ai_vs_reported.items())
        + ". Differences of two levels or more are flagged for review; the person decides.",
        "",
    ]
    classes = Counter(r["ai_class"] for _, r in rows)
    md += [
        "Incident classes found by triage in this run: "
        + ", ".join(f"{k} ({v})" for k, v in classes.most_common())
        + ".",
        "",
    ]

    # 5. Dashboard after.
    after = api.call("GET", "/dashboard", "pm", params={"project_id": pid})
    md += [
        "## 5. Portfolio after resolution",
        "",
        table(
            [[k.replace("_", " "), before["totals"].get(k), v] for k, v in after["totals"].items()],
            ["Metric", "Before", "After"],
        ),
        "",
        "Mean days to close falls only because the scripted people in this run close incidents minutes after "
        "they are reported; read it as a workflow check, not a performance figure.",
        "",
        "Top hazards and defects found by triage: " + ", ".join(f"{h} ({n})" for h, n in after["top_hazards"]) + ".",
        "",
        "Action decisions across the project: "
        + ", ".join(f"{k} {v}" for k, v in sorted(after["capa_by_status"].items()))
        + ".",
        "",
        "Agent runs: " + ", ".join(f"{k} {v}" for k, v in after["agents"].items() if k != "providers") + ".",
        "",
    ]

    # 6. Reports for every incident.
    final = api.call("GET", f"/projects/{pid}/incidents", "pm")
    for inc in final:
        r = api.http.get(f"/incidents/{inc['id']}/report", headers=api.as_("auditor"))
        r.raise_for_status()
        (reports / f"{inc['reference']}.md").write_text(r.text)
    md += [
        "## 6. Investigation reports",
        "",
        f"One Markdown report per incident ({len(final)} in total) was downloaded from "
        "`GET /incidents/{id}/report` as the auditor and saved in [docs/reports/](reports/). Incidents closed "
        "before this run were closed by the seed history:",
        "",
        ", ".join(
            f"[{i['reference']}](reports/{i['reference']}.md)"
            for i in sorted(closed_before, key=lambda i: i["reference"])
        )
        + ".",
        "",
    ]

    Path(args.out).write_text("\n".join(md))
    print(f"Wrote {args.out} and {len(final)} reports to {reports}")


if __name__ == "__main__":
    main()
