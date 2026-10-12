"""Scheduled jobs. Run with `python -m app.jobs escalate-overdue deliver-notifications` (for example from an Azure
Container Apps job or cron). Jobs run in the order given and act as SYSTEM in the audit trail."""

import argparse
import json

from sqlalchemy import select

from app.core import db as dbmod
from app.models import Project
from app.services import delivery, notifications


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


JOBS = {"escalate-overdue": escalate_overdue, "deliver-notifications": deliver_notifications}


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m app.jobs")
    ap.add_argument("jobs", nargs="+", choices=sorted(JOBS))
    args = ap.parse_args()
    result: dict = {}
    for name in args.jobs:
        result.update(JOBS[name]())
    print(json.dumps(result, indent=1, default=str))


if __name__ == "__main__":
    main()
