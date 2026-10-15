"""Crop the deck images in img/ from fresh screenshots. See README.md for where each screenshot comes from.

    python crop_images.py <screens-dir>

<screens-dir> holds the browser-test screenshots (02, 03, 05, 07, 08 from `SCREENSHOT_DIR=...`) and the
capture_screens.cjs output (2-dashboard-after.png, 10-audit-trail.png). Boxes are (left, top, right, bottom) in
pixels at the 1440 px wide viewport. If a screen's layout changes (for example more findings above the photo
review), check the crops by eye and adjust the box.
"""

import sys
from pathlib import Path

from PIL import Image

CROPS = {
    "dashboard_after.png": ("2-dashboard-after.png", (80, 60, 1360, 780)),
    "s_workspace.png": ("02-incident-ai-investigation.png", (80, 60, 1360, 960)),
    "s_closed.png": ("03-incident-closed.png", (80, 60, 1360, 500)),
    "s_queue.png": ("05-action-queue.png", (80, 90, 1360, 420)),
    "s_answer.png": ("07-grounded-answer.png", (80, 170, 1360, 545)),
    "s_photo.png": ("08-photo-review-and-workflow.png", (80, 1325, 985, 1675)),
    "s_audit.png": ("10-audit-trail.png", (80, 90, 1360, 510)),
}

if __name__ == "__main__":
    src, out = Path(sys.argv[1]), Path(__file__).resolve().parent / "img"
    for name, (shot, box) in CROPS.items():
        if not (src / shot).exists():
            print(f"skip {name}: {shot} not found")
            continue
        img = Image.open(src / shot).convert("RGB").crop(box)
        img.save(out / name)
        print(f"{name} <- {shot} {img.size}")
