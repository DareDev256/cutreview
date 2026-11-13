"""Render the demo pages headless at 1440 and 390, dark and light, and check them.

    python3 scripts/screenshots.py build/demo docs/screenshots 2026-11-12

Needs Playwright with Chromium (a dev tool, not a cutreview dependency).
For every render it checks, and exits non-zero on any failure:

* no horizontal overflow (the page is never wider than the window);
* no two labels overlap inside the same row of labels (change header,
  frame caption, chip row, note meta, pin rail);
* no request leaves the file: every URL is file: or data:.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

PAGES = ["review", "blame", "status"]
SIZES = {1440: 900, 390: 844}
FULL = {("review", "dark"), ("review", "light"), ("status", "dark"), ("status", "light"), ("blame", "dark")}

CHECK = """
() => {
  const doc = document.documentElement;
  const overflow = doc.scrollWidth - doc.clientWidth;
  const groups = document.querySelectorAll('.head, figcaption, .chips, .meta, .rail, .scale div, .legend, .lane-row');
  const hits = [];
  for (const g of groups) {
    const kids = [...g.children].filter(k => k.getClientRects().length);
    for (let i = 0; i < kids.length; i++) for (let j = i + 1; j < kids.length; j++) {
      const a = kids[i].getBoundingClientRect(), b = kids[j].getBoundingClientRect();
      const w = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      const h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      if (w > 1 && h > 1 && a.width && b.width) hits.push(`${g.className}: "${kids[i].textContent.slice(0,30)}" x "${kids[j].textContent.slice(0,30)}"`);
    }
  }
  const wide = [...document.querySelectorAll('body *')].filter(el => el.getBoundingClientRect().right > doc.clientWidth + 1)
    .slice(0, 5).map(el => el.tagName + '.' + el.className);
  return {overflow, hits, wide, height: doc.scrollHeight};
}
"""


def main() -> int:
    src = Path(sys.argv[1]).resolve()
    out = Path(sys.argv[2]).resolve()
    date = sys.argv[3]
    out.mkdir(parents=True, exist_ok=True)
    failures, report = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for page_name in PAGES:
            html = src / f"{page_name}.html"
            for width, height in SIZES.items():
                for scheme in ("dark", "light"):
                    ctx = browser.new_context(viewport={"width": width, "height": height},
                                              color_scheme=scheme, device_scale_factor=1)
                    page = ctx.new_page()
                    external = []
                    page.on("request", lambda r: external.append(r.url) if not r.url.startswith(("file:", "data:")) else None)
                    page.goto(html.as_uri())
                    page.wait_for_load_state("load")
                    res = page.evaluate(CHECK)
                    tag = f"{page_name}-{width}-{scheme}"
                    shots = []
                    if (page_name, scheme) in FULL:
                        f = out / f"{date}_{tag}.png"
                        page.screenshot(path=str(f), full_page=True)
                        shots.append(f.name)
                    if scheme == "dark" and page_name in ("review", "status"):
                        f = out / f"{date}_{tag}-fold.png"
                        page.screenshot(path=str(f), full_page=False)
                        shots.append(f.name)
                    ok = res["overflow"] <= 0 and not res["hits"] and not external
                    report.append({"render": tag, "ok": ok, "overflow_px": res["overflow"],
                                   "overlaps": res["hits"], "too_wide": res["wide"],
                                   "external_requests": external, "page_height": res["height"], "shots": shots})
                    if not ok:
                        failures.append(tag)
                    ctx.close()
        browser.close()
    print(json.dumps(report, indent=1))
    print("FAILED: " + ", ".join(failures) if failures else f"all {len(report)} renders pass")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
