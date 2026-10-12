"""Scheduled jobs. Run with `python -m app.jobs escalate-overdue deliver-notifications` (for example from an Azure
Container Apps job or cron), and `python -m app.jobs graph-sync` when the knowledge graph is enabled. Jobs run in
the order given and act as SYSTEM in the audit trail."""

import argparse
import json

from sqlalchemy import select

from app.core import db as dbmod
from app.models import Project
from app.services import delivery, graph, notifications


def escalate_overdue() -> dict:
    with dbmod.SessionLocal() as db:
        ids = list(db.scalars(select(Project.id)))
        sent = notifications.escalate_overdue(db, project_ids=ids, actor_id=None)
        db.commit()
        return {"escalations": sent}


def deliver_notifications() -> dict:
    """Send due email deliveries for every organization (retries with backoff; dead letters stay FAILED)."""
    with dbmod.SessionLocal() as db:
        report = delivery.dispatch(db)
        db.commit()
        return {"delivery": report.__dict__}


def graph_sync() -> dict:
    """Rebuild every organization's knowledge graph projection (needs SITEGUARD_GRAPH_BACKEND=neo4j)."""
    store = graph.get_store()  # GraphDisabled when SITEGUARD_GRAPH_BACKEND=disabled
    with dbmod.SessionLocal() as db:
        return {"graph": graph.sync_all(db, store)}


JOBS = {"escalate-overdue": escalate_overdue, "deliver-notifications": deliver_notifications, "graph-sync": graph_sync}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m app.jobs")
    ap.add_argument("jobs", nargs="+", choices=sorted(JOBS))
    args = ap.parse_args(argv)
    result: dict = {}
    try:
        for name in args.jobs:
            result.update(JOBS[name]())
    except (graph.GraphDisabled, graph.GraphUnavailable) as exc:
        raise SystemExit(f"{name}: {exc.message}") from exc
    finally:
        graph.close_store()
    print(json.dumps(result, indent=1, default=str))


if __name__ == "__main__":
    main()
