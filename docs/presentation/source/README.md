# Review III deck: build kit

`build.py` produces `../SiteGuardAI_Review3_S.K.Sricharan_T9984.pptx` (18 slides) from the programme template.

| File | What it is |
|---|---|
| `build.py` | Fills every slide: title page (project title, S.K. Sricharan, T-SERIES ID T9984), introduction, objectives, modules, problem statement, methodology (architecture and workflow diagrams), approach and tools, findings (accuracy chart, end-to-end results, two product-screen slides, load test and quality), conclusion, acknowledgement, references. |
| `stage.pptx` | The MTech Review III template with its slides already duplicated to the 18 the deck needs. |
| `img/` | Screenshots used on slides 2, 12, 13 and 14, cropped from the running product. |
| `capture_screens.cjs` | Captures the dashboard (before and after `resolve_all.py`), incident list, incident workspace and audit trail. |
| `crop_images.py` | Crops the deck images in `img/` from fresh screenshots. |

## Rebuild the deck

```bash
pip install python-pptx lxml pillow
python docs/presentation/source/build.py      # writes docs/presentation/SiteGuardAI_Review3_S.K.Sricharan_T9984.pptx
```

## Change a figure

Every number on the slides is typed in `build.py`, copied from the project's own reports. When results change,
update the figure in `build.py` from its source and rebuild:

| Slide | Figures | Source |
|---|---|---|
| 11 Findings: accuracy | held-out class, domain, severity within one, retrieval; red-team | `docs/EVALUATION.md`, `docs/evaluation.json` |
| 12 Findings: end-to-end | before/after table, agent runs, decisions, incidents closed | `docs/RESULTS.md` |
| 15 Findings: performance and quality | load-test table, backend test count, CI jobs | `docs/LOAD_TEST.md`, `pytest --collect-only -q` |

Search `build.py` for the old value (for example `"270", "backend tests`) to find where it is set.

## Refresh the screenshots

1. Start the stack on a fresh database: `make up` (Docker) or `make run` (SQLite).
2. Dashboard before the run: `node docs/presentation/source/capture_screens.cjs /tmp/shots before`
3. Resolve every incident: `python scripts/resolve_all.py --base-url http://localhost:8000 --out /tmp/RESULTS.md --reports-dir /tmp/reports`
   (to update the committed results instead, run `make demo`).
4. Dashboard after, incident list, workspace and audit: `node docs/presentation/source/capture_screens.cjs /tmp/shots after`
5. Product screens from the browser tests on another fresh database:
   `cd frontend && SCREENSHOT_DIR=/tmp/shots E2E_BASE_URL=http://localhost:8000 npx playwright test`
   (with `SCREENSHOT_DIR=../docs/screenshots` the same run refreshes the README screenshots).
6. `python docs/presentation/source/crop_images.py /tmp/shots`, check each image in `img/` by eye, then rebuild.

Set `CHROMIUM_PATH` if Playwright should use a Chromium that is already installed.
