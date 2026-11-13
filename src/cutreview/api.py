"""The four actions, shared by the command line and the MCP tool."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import List, Optional

from . import __version__
from .blame import blame as run_blame_on
from .changes import compare
from .cut import file_sha256, load
from .frames import FrameGrabber
from .markers import place, write_markers
from .notes import read_notes, resolve_times
from .page import render_diff, render_status
from .status import status as run_status_on
from .timecode import format_tc, parse_tc


@dataclass
class Result:
    summary: str
    outputs: List[str] = field(default_factory=list)
    data: dict = field(default_factory=dict)


def _write(path: Path, text: str) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def _default_out(new_path: str, suffix: str) -> Path:
    p = Path(new_path)
    stem = p.name[: -len(p.suffix)] if p.suffix else p.name
    return p.parent / f"{stem}{suffix}"


def _change_lines(review, with_blame: bool = False) -> List[str]:
    lines = []
    for c in review.changes:
        cut = review.new if c.new_tl else review.old
        at = c.new_tl[0] if c.new_tl else (c.old_tl[0] if c.old_tl else None)
        tc = format_tc(at, cut.frame_duration, cut.tc_start) if at is not None else "           "
        line = f"{c.n:>3}  {tc}  {c.kind:<10} {c.name}: {c.detail}"
        if with_blame and c.blame:
            b = c.blame
            if b.get("kind") == "hand":
                line += "\n       not in the journal (by hand in Final Cut, or a tool with no journal)"
            elif b.get("kind") == "none":
                line += "\n       no journal found"
            else:
                who = b.get("by", "") + (f" ({b['args']})" if b.get("args") else "")
                line += f"\n       by {who}"
                if b.get("kind") == "journal+hand":
                    line += ", and changed again after the last journaled write"
        lines.append(line)
    return lines


def diff(old: str, new: str, output: Optional[str] = None, frames: bool = True) -> Result:
    review = compare(load(old), load(new))
    out = Path(output) if output else _default_out(new, "_review.html")
    with tempfile.TemporaryDirectory(prefix="cutreview-frames-") as tmp:
        grabber = FrameGrabber(Path(tmp), enabled=frames)
        written = _write(out, render_diff(review, grabber))
    counts = ", ".join(f"{v} {k}" for k, v in review.counts().items()) or "no changes"
    summary = "\n".join(
        [f"{review.old.name} -> {review.new.name}: {len(review.changes)} change{'' if len(review.changes) == 1 else 's'} ({counts})"]
        + _change_lines(review)
        + ([f"{review.slid} clips only slid with the ripple (not listed)"] if review.slid else [])
        + [f"Page: {written}"]
    )
    return Result(summary, [written], {"changes": len(review.changes), "counts": review.counts()})


def blame(old: str, new: str, output: Optional[str] = None, journal: Optional[str] = None,
          frames: bool = True) -> Result:
    review = compare(load(old), load(new))
    found = run_blame_on(review, journal)
    out = Path(output) if output else _default_out(new, "_blame.html")
    with tempfile.TemporaryDirectory(prefix="cutreview-frames-") as tmp:
        grabber = FrameGrabber(Path(tmp), enabled=frames)
        written = _write(out, render_diff(review, grabber, blame=found))
    head = [
        f"{review.old.name} -> {review.new.name}: {len(review.changes)} change{'' if len(review.changes) == 1 else 's'}",
        f"journal files: {', '.join(found.journals) or 'none found'}",
        f"journaled writes on the path: {len(found.steps)}"
        + ("" if found.reached else " (the chain does not reach the new file)"),
    ]
    summary = "\n".join(head + _change_lines(review, True) + found.notes + [f"Page: {written}"])
    return Result(summary, [written], {
        "changes": len(review.changes), "steps": len(found.steps),
        "unexplained": found.unexplained, "reached": found.reached,
        "blame": [{"n": c.n, "change": c.kind, "name": c.name, **(c.blame or {})} for c in review.changes],
    })


def notes(cut_path: str, notes_path: str, output: Optional[str] = None, fmt: str = "auto",
          author: str = "", start_tc: Optional[str] = None, source_tc: bool = False) -> Result:
    cut = load(cut_path)
    ns = read_notes(notes_path, cut.frame_duration, fmt, author=author, use_source_tc=source_tc)
    base = parse_tc(start_tc, cut.frame_duration) if start_tc else None
    resolve_times(ns, cut.tc_start, cut.duration, base)
    placements = place(cut, ns)
    out = Path(output) if output else _default_out(cut_path, "_notes" + Path(cut_path).suffix)
    report = write_markers(cut, placements, out) if placements else {"path": "", "dtd": "nothing written"}
    ledger = {
        "tool": "cutreview", "version": __version__,
        "cut": {"path": str(Path(cut_path).resolve()), "sha256": cut.sha256},
        "notes_file": {"path": str(Path(notes_path).resolve()), "sha256": file_sha256(notes_path), "format": ns.format},
        "marked": {"path": report.get("path", ""), "sha256": file_sha256(report["path"]) if report.get("path") else ""},
        "time_base": ns.time_base,
        "dtd": report.get("dtd"), "dtd_detail": report.get("dtd_detail", ""),
        "readback": report.get("readback", ""),
        "placed": [n.to_json() for n in ns.notes],
        "unplaced": [n.to_json() for n in ns.unplaced],
        "unreadable": [r.to_json() for r in ns.unreadable],
    }
    outputs = []
    if report.get("path"):
        outputs.append(report["path"])
        ledger_path = Path(report["path"] + ".cutreview.json")
    else:
        ledger_path = _default_out(cut_path, "_notes.cutreview.json")
    outputs.append(_write(ledger_path, json.dumps(ledger, indent=2, ensure_ascii=False)))
    lines = [
        f"{len(ns.notes)} notes written as to-do markers into {report.get('path') or '(nothing: no note could be placed)'}",
        f"Times {ns.time_base}.",
    ]
    for n in ns.notes:
        audio = " (audio only under it)" if n.placed.get("on_audio") else ""
        lines.append(f"  #{n.id:<3} {n.placed['timecode']}  on {n.placed['clip']}{audio}: {n.text.splitlines()[0][:70]}")
    if ns.unplaced:
        lines.append(f"{len(ns.unplaced)} not placed (listed, never guessed):")
        for n in ns.unplaced:
            lines.append(f"  {n.origin}: {(n.placed or {}).get('reason', 'no timecode')}: {n.text.splitlines()[0][:70]}")
    if ns.unreadable:
        lines.append(f"{len(ns.unreadable)} unreadable (listed, never dropped):")
        for r in ns.unreadable:
            lines.append(f"  {r.origin}: {r.reason}: {r.text[:70]}")
    if report.get("dtd") == "valid":
        lines.append(f"Checked: {report['dtd_detail']}; {report.get('readback', '')}.")
    elif report.get("dtd") == "input-invalid":
        lines.append(f"Checked: {report['dtd_detail']}; {report.get('readback', '')}.")
    elif report.get("dtd") == "unchecked":
        lines.append(f"DTD check not run: {report.get('dtd_detail', '')}")
    lines.append(f"Ledger: {ledger_path}")
    return Result("\n".join(lines), outputs, {
        "placed": len(ns.notes), "unplaced": len(ns.unplaced), "unreadable": len(ns.unreadable),
        "dtd": report.get("dtd"),
    })


def status(marked: str, next_export: str, output: Optional[str] = None, reach: float = 1.0,
           ledger: Optional[str] = None, frames: bool = True) -> Result:
    review = compare(load(marked), load(next_export))
    rep = run_status_on(review, Fraction(str(reach)))
    ledger_data = None
    lp = Path(ledger) if ledger else Path(str(marked) + ".cutreview.json")
    if lp.is_file():
        ledger_data = json.loads(lp.read_text(encoding="utf-8"))
    out = Path(output) if output else _default_out(next_export, "_status.html")
    with tempfile.TemporaryDirectory(prefix="cutreview-frames-") as tmp:
        grabber = FrameGrabber(Path(tmp), enabled=frames)
        written = _write(out, render_status(rep, ledger_data, grabber))
    tu, cu = rep.bucket("ticked-untouched"), rep.bucket("changed-unticked")
    fd = review.old.frame_duration
    lines = [f"{len(rep.notes)} notes in {review.old.name}, checked against {review.new.name}"]
    lines.append(f"Ticked but untouched: {len(tu)}")
    lines += [f"  #{x.id} {format_tc(x.marker.tl, fd, review.old.tc_start)} {x.text[:70]}" for x in tu]
    lines.append(f"Changed but not ticked: {len(cu)}")
    lines += [f"  #{x.id} {format_tc(x.marker.tl, fd, review.old.tc_start)} {x.text[:70]}" for x in cu]
    lines.append("Every note:")
    for x in rep.notes:
        by = f" (by change {', '.join(str(c.n) for c in x.by)})" if x.by else ""
        lines.append(f"  #{x.id} {format_tc(x.marker.tl, fd, review.old.tc_start)} {x.state_words}{by}: {x.text[:60]}")
    if ledger_data:
        lines.append(f"{len(ledger_data.get('unplaced', []))} not placed, {len(ledger_data.get('unreadable', []))} unreadable (from {lp.name})")
    lines.append(f"Page: {written}")
    return Result("\n".join(lines), [written], {
        "notes": len(rep.notes), "ticked_untouched": len(tu), "changed_unticked": len(cu),
        "states": {f"#{x.id}": x.state_words for x in rep.notes},
    })
