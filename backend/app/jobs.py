"""Scheduled jobs. Run from cron, a Container Apps job or `make jobs`:

python -m app.jobs escalate   # time-based escalation rules for every organization
python -m app.jobs dispatch   # send due external notification deliveries
python -m app.jobs all        # both, in that order
"""

import argparse
import json
import logging

from sqlalchemy import select

from app.core import db as dbmod
from app.core.observability import configure_logging
from app.models import Organization
from app.services import notifications

log = logging.getLogger("siteguard.jobs")


def run(job: str) -> dict:
    out: dict = {}
    with dbmod.SessionLocal() as db:
        for org_id in db.scalars(select(Organization.id).order_by(Organization.id)):
            result: dict = {}
            if job in ("escalate", "all"):
                result["escalation"] = notifications.escalate(db, organization_id=org_id).__dict__
            if job in ("dispatch", "all"):
                result["dispatch"] = notifications.dispatch(db, organization_id=org_id).__dict__
            db.commit()
            out[org_id] = result
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("job", choices=["escalate", "dispatch", "all"])
    args = parser.parse_args(argv)
    configure_logging()
    dbmod.run_migrations()
    result = run(args.job)
    log.info("job finished", extra={"extra_fields": {"job": args.job}})
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
