"""Write the rules provider's triage labels for every labelled and seeded incident, one line per case.

Run it before and after a change to backend/app/agents/rules.py and diff the two files, to see exactly which
cases a change moves (a narrow fix should move only the case it targets):

    cd backend
    python ../scripts/label_snapshot.py --out /tmp/before.txt
    # ... edit app/agents/rules.py ...
    python ../scripts/label_snapshot.py --out /tmp/after.txt
    diff /tmp/before.txt /tmp/after.txt

The held-out cases are listed so a change can be checked for side effects; they must not be used to tune the
rules (Decision 025). Accuracy itself comes from `make eval`.
"""

import argparse
from pathlib import Path

import yaml

from app.agents import rules
from app.core.config import REPO_ROOT

SOURCES = (
    "data/eval/incidents_gold.yaml",
    "data/eval/dev_v2.yaml",
    "data/eval/heldout_v2.yaml",
    "data/seed/incidents.yaml",
)


def _cases(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):  # seed file: the incident list sits under a key
        data = next(v for v in data.values() if isinstance(v, list))
    return data


def snapshot(root: Path = REPO_ROOT) -> list[str]:
    lines = []
    for source in SOURCES:
        for case in _cases(root / source):
            pack = {
                "incident": {
                    "title": case.get("title", ""),
                    "description": case.get("description", ""),
                    "domain": case.get("domain", "SAFETY"),
                    "people_involved": case.get("people_involved", 0),
                }
            }
            hazards, defects, domain = rules.classify(pack)
            name = Path(source).name
            lines.append(
                f"{name} {case.get('id', '-')} {case['title'][:60]} | hazards={hazards} defects={defects} "
                f"domain={domain.value if domain else None} | label={case.get('class', '-')}"
            )
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True, help="text file to write, one case per line")
    args = parser.parse_args()
    lines = snapshot()
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(lines)} cases to {args.out}")


if __name__ == "__main__":
    main()
