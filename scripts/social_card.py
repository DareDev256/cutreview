"""Build the GitHub social preview card: 1280x640, true black, one cyan, the real page as the picture.

    uv run --with playwright python scripts/social_card.py build/launch/status.html

Renders the given status page (dark) in Chromium, then lays the card out
around that render and writes ``docs/assets/social-card.png``. Pass the page
from the real-footage round on launch day; the demo round's page
(``build/demo/status.html``, synthesized media) is only for a draft.

Same rules as fcp-mcp-server 0.31's card: no version and no star count on it
(a number printed into an image goes stale the day it is uploaded, and GitHub
has no API to replace the image), and the script REFUSES (exit 1) when any
text box overlaps the picture or another text box, or runs off the card.
Uploading stays one step in the repo's Settings (Social preview).
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "docs" / "assets" / "social-card.png"
WIDTH, HEIGHT = 1280, 640
SHOT_W, SHOT_H = 1120, 860  # the page is rendered at this size, then scaled into the card

# fcp-mcp-server 0.31 dark tokens (fcpxml/palette.py): one accent, greys, true black.
GROUND, INK, MUTE, ACCENT, LINE = "#000000", "#EDEDF0", "#8C8C96", "#00E5FF", "#3A3A44"

NAME = "cutreview"
SUBTITLE = "Frame.io comments and client notes as Final Cut Pro to-do markers"
PROMISE = "Client notes land in Final Cut as to-dos. After the recut, see which ones the cut changed."
INSTALL = "uvx cutreview"


def html(shot_png: bytes) -> str:
    shot = "data:image/png;base64," + base64.b64encode(shot_png).decode("ascii")
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
  html, body {{ margin: 0; width: {WIDTH}px; height: {HEIGHT}px; overflow: hidden; background: {GROUND}; }}
  body {{ position: relative; font-family: ui-sans-serif, system-ui, -apple-system, "Helvetica Neue", sans-serif; color: {INK}; }}
  #copy {{ position: absolute; left: 64px; top: 64px; width: 450px; bottom: 64px; display: flex; flex-direction: column; }}
  #name {{ font-size: 60px; line-height: 1; font-weight: 700; letter-spacing: -0.035em; margin: 0; }}
  #subtitle {{ margin: 16px 0 0; font-size: 21px; line-height: 1.3; color: {MUTE}; text-wrap: balance; }}
  #promise {{ margin: 34px 0 0; font-size: 30px; line-height: 1.22; font-weight: 600; letter-spacing: -0.01em; }}
  #install {{ margin-top: auto; align-self: flex-start; font: 600 19px/1 ui-monospace, "SF Mono", Menlo, monospace;
             color: {ACCENT}; border: 1px solid {LINE}; border-radius: 8px; padding: 11px 14px; }}
  #shot {{ position: absolute; left: 556px; top: 57px; width: 692px; height: 526px; border-radius: 14px;
          border: 1px solid {LINE}; overflow: hidden; background: {GROUND}; }}
  #shot img {{ display: block; width: 100%; }}
</style></head><body>
<div id="copy">
  <h1 id="name">{NAME}</h1>
  <p id="subtitle">{SUBTITLE}</p>
  <p id="promise">{PROMISE}</p>
  <div id="install">{INSTALL}</div>
</div>
<div id="shot"><img alt="" src="{shot}"></div>
</body></html>"""


MEASURE = """() => {
  const box = (id) => { const r = document.getElementById(id).getBoundingClientRect();
    return { id, x0: r.left, y0: r.top, x1: r.right, y1: r.bottom }; };
  const text = (id) => { const el = document.getElementById(id), range = document.createRange();
    range.selectNodeContents(el); const rs = [...range.getClientRects()];
    return { id, x0: Math.min(...rs.map(r => r.left)), y0: Math.min(...rs.map(r => r.top)),
             x1: Math.max(...rs.map(r => r.right)), y1: Math.max(...rs.map(r => r.bottom)) }; };
  return { texts: ["name", "subtitle", "promise", "install"].map(id => id === "install" ? box(id) : text(id)), shot: box("shot") };
}"""


def collisions(layout: dict, gap: float = 20) -> list[str]:
    """Every overlap, and every box off the card. Empty means the card is clean."""
    problems = []
    boxes, shot = layout["texts"], layout["shot"]
    for b in boxes:
        if b["x1"] > shot["x0"] - gap:
            problems.append(f"{b['id']} runs to x={b['x1']:.0f}, into the picture at x={shot['x0']:.0f}")
        if b["x0"] < 0 or b["y0"] < 0 or b["y1"] > HEIGHT:
            problems.append(f"{b['id']} is off the card: {b}")
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            if a["x0"] < b["x1"] and b["x0"] < a["x1"] and a["y0"] < b["y1"] and b["y0"] < a["y1"]:
                problems.append(f"{a['id']} overlaps {b['id']}")
    if shot["x1"] > WIDTH or shot["y1"] > HEIGHT:
        problems.append(f"the picture runs off the card: {shot}")
    return problems


def main(argv: list[str]) -> int:
    from playwright.sync_api import sync_playwright

    if len(argv) != 2 or not Path(argv[1]).is_file():
        print("usage: social_card.py STATUS_PAGE.html  (the page cutreview status wrote)", file=sys.stderr)
        return 2
    page_path = Path(argv[1]).resolve()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        shot_page = browser.new_page(viewport={"width": SHOT_W, "height": SHOT_H}, device_scale_factor=1, color_scheme="dark")
        shot_page.goto(page_path.as_uri())
        shot_page.wait_for_load_state("load")
        shot_png = shot_page.screenshot()
        card = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1)
        card.set_content(html(shot_png))
        card.wait_for_load_state("load")
        problems = collisions(card.evaluate(MEASURE))
        if problems:
            browser.close()
            print("refusing to write the card:\n  " + "\n  ".join(problems), file=sys.stderr)
            return 1
        OUT.parent.mkdir(parents=True, exist_ok=True)
        card.screenshot(path=str(OUT))
        browser.close()
    print(f"{OUT.relative_to(REPO)}  {WIDTH}x{HEIGHT}  picture: {page_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
