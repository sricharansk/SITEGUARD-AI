"""Scheduled jobs. Run with `python -m app.jobs escalate-overdue` (for example from an Azure Container Apps
job or cron once a day). Jobs act as SYSTEM in the audit trail."""

import argparse
import json

from sqlalchemy import select

from app.core import db as dbmod
from app.models import Project
from app.services import notifications


def escalate_overdue() -> list[dict]:
    with dbmod.SessionLocal() as db:
        ids = list(db.scalars(select(Project.id)))
        sent = notifications.escalate_overdue(db, project_ids=ids, actor_id=None)
        db.commit()
        return sent


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m app.jobs")
    ap.add_argument("job", choices=["escalate-overdue"])
    args = ap.parse_args()
    if args.job == "escalate-overdue":
        print(json.dumps({"escalations": escalate_overdue()}, indent=1))


if __name__ == "__main__":
    main()
