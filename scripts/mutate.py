"""Break each guard on purpose and check that a test goes red.

    python scripts/mutate.py

Each mutation edits one line of the source, runs the tests that claim to
protect it, and restores the file whatever happens. A mutation the tests do
not catch is a test that guards nothing, and the script exits non-zero.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "cutreview"

MUTATIONS = [
    ("touched: the later cut's window counts", "status.py",
     "    if new_win and c.new_tl and c.new_tl[0] <= new_win[1] and c.new_tl[1] >= new_win[0]:\n        return True\n",
     "    if False:\n        return True\n",
     "tests/test_status.py"),
    ("touched: the earlier cut's window counts", "status.py",
     "    if c.old_tl and c.old_tl[0] <= old_hi and c.old_tl[1] >= old_lo:\n        return True\n",
     "    if False:\n        return True\n",
     "tests/test_status.py"),
    ("audio-lane changes do not touch picture notes", "status.py",
     "    if on_picture and c.lane is not None and c.lane < 0:\n        return False\n",
     "    if False:\n        return False\n",
     "tests/test_changes.py::test_an_audio_lane_change_does_not_touch_a_picture_note"),
    ("a removed clip reads 'removed with its clip'", "status.py",
     "            if not same_source:\n                presence = \"removed-with-clip\"",
     "            if False:\n                presence = \"removed-with-clip\"",
     "tests/test_status.py"),
    ("a marker hidden by a trim reads 'frames cut'", "status.py",
     "            hidden = not (after.span.tl_in <= after.tl < after.span.tl_out)",
     "            hidden = False",
     "tests/test_status.py::test_a_marker_hidden_by_a_trim_reads_as_frames_cut"),
    ("no timecode is unplaced, never given a time", "notes.py",
     "            last = Note(text=text.strip(), origin=origin, author=author)\n            ns.unplaced.append(last)",
     "            last = Note(text=text.strip(), origin=origin, author=author, at=Fraction(0))\n            ns.notes.append(last)",
     "tests/test_notes.py"),
    ("unreadable lines are listed, never dropped", "notes.py",
     "            except TimecodeError as e:\n                ns.unreadable.append(Rejected(origin, text, str(e)))\n                last = None\n                continue\n            body",
     "            except TimecodeError as e:\n                last = None\n                continue\n            body",
     "tests/test_notes.py"),
    ("the hour rule needs every note past the hour", "notes.py",
     "all(n.at >= HOUR for n in timed)",
     "any(n.at >= HOUR for n in timed)",
     "tests/test_notes.py"),
    ("DTD: a new error refuses the write", "markers.py",
     "        if new:\n            raise WriteRefused(",
     "        if False:\n            raise WriteRefused(",
     "tests/test_markers.py"),
    ("read-back: a misplaced marker refuses the write", "markers.py",
     "    if misses:\n        raise WriteRefused(",
     "    if False:\n        raise WriteRefused(",
     "tests/test_markers.py"),
    ("a ripple is not a move (order kept = longest run)", "changes.py",
     "        if i not in keep:\n            moved.setdefault",
     "        if abs(p.delta) > tol:\n            moved.setdefault",
     "tests/test_changes.py tests/test_status.py"),
    ("a connected clip moves with its host", "changes.py",
     "            expected = q.delta\n",
     "            expected = Fraction(0)\n",
     "tests/test_changes.py"),
    ("a head trim is a trim, not a swap (one-to-one pairing)", "changes.py",
     "            if ov and ov[1] - ov[0] > tol:\n                cand.append(",
     "            if ov and ov[1] - ov[0] > tol and o.src_in == n.src_in:\n                cand.append(",
     "tests/test_changes.py"),
    ("blame: work after the last journaled write is 'not in the journal'", "blame.py",
     "        by_hand = any(_same(k, sig) for k in hand)",
     "        by_hand = False",
     "tests/test_blame.py"),
    ("a source is its media, never its resource id (Final Cut renumbers ids)", "cut.py",
     "            ids = info[\"ids\"] or (f\"{el.tag}:{el.get('name', '')}\",)",
     "            ids = (f\"ref:{ref}\",)",
     "tests/test_fcp_roundtrip.py"),
    ("a source's names are joined across both files (relinked media)", "changes.py",
     "    unify_sources(old, new)\n",
     "    pass\n",
     "tests/test_fcp_roundtrip.py"),
    ("a missing start reads as zero", "cut.py",
     "    return parse_seconds(value) if value else Fraction(0)",
     "    return parse_seconds(value) if value else Fraction(1)",
     "tests/test_fcp_roundtrip.py"),
    ("MCP: writes stay in the cut's folder", "mcp_server.py",
     "        out.relative_to(folder)",
     "        out.relative_to(Path('/'))",
     "tests/test_cli_mcp.py"),
    ("page: nothing loads from the network", "page.py",
     "f\"<title>{e(title)}</title><style>{CSS}</style></head>",
     "f\"<title>{e(title)}</title><link rel=stylesheet href=\\\"https://fonts.googleapis.com/css2?family=Inter\\\"><style>{CSS}</style></head>",
     "tests/test_page.py"),
    ("page: note text is escaped", "page.py",
     "    return html.escape(str(x), quote=True)",
     "    return str(x)",
     "tests/test_page.py"),
]


def main() -> int:
    rows, escaped = [], []
    for name, file, old, new, tests in MUTATIONS:
        path = SRC / file
        original = path.read_text()
        if original.count(old) != 1:
            rows.append((name, file, "mutation did not apply", ""))
            escaped.append(name)
            continue
        path.write_text(original.replace(old, new))
        # No bytecode: a same-length mutation restored within the same second
        # would otherwise leave a .pyc of the MUTANT that Python keeps using.
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *tests.split()],
                cwd=ROOT, capture_output=True, text=True, timeout=600, env=env,
            )
        finally:
            path.write_text(original)
            for cache in SRC.rglob("__pycache__"):
                shutil.rmtree(cache, ignore_errors=True)
        tail = [ln for ln in proc.stdout.splitlines() if ln.startswith(("FAILED", "ERROR"))]
        caught = proc.returncode != 0
        rows.append((name, file, "caught" if caught else "NOT CAUGHT", tail[0][7:] if tail else ""))
        if not caught:
            escaped.append(name)
    print("| Guard broken on purpose | File | Result | First failing test |")
    print("|---|---|---|---|")
    for r in rows:
        print(f"| {r[0]} | `{r[1]}` | {r[2]} | {r[3].split(' - ')[0]} |")
    if escaped:
        print(f"\n{len(escaped)} mutation(s) escaped: " + "; ".join(escaped))
        return 1
    print(f"\nAll {len(rows)} mutations caught.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
