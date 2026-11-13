"""Realistic review rounds, built by running fcp-mcp-server's own operations.

Each scenario: copy a cut, write notes into it with cutreview, then edit it
the way an agent would (fcp-mcp-server tool calls, through ``call_tool`` so
its journal records every write), then the editor's part by hand (a tick in
Final Cut, a clip deleted by hand), and save the result as the next export.

Used by ``scripts/make_fixtures.py``, by the test suite and by the demo.
Pass ``skip`` to leave one step out: that is how the mutation test removes
one change from the fixture.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Callable, Dict, List

HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parent / "fixtures"


def _env(journal_dir: Path) -> None:
    os.environ["FCP_MCP_JOURNAL"] = str(journal_dir)
    os.environ["FCP_MCP_AUTOPUSH"] = "off"     # never push into a running Final Cut
    os.environ["FCP_MCP_INDEX"] = "off"


def fcp_call(tool: str, args: dict) -> str:
    import server  # fcp-mcp-server, installed from PyPI

    result = asyncio.run(server.call_tool(tool, args))
    text = result[0].text
    if text.startswith(("Error", "Validation error", "Missing required", "Unknown tool", "File not found")):
        raise RuntimeError(f"fcp-mcp-server {tool}.{args.get('action')}: {text}")
    return text


@dataclass
class Round:
    folder: Path
    base: Path                    # the cut before notes
    marked: Path                  # with the notes as to-do markers
    next_export: Path             # after the agent and the editor
    steps: List[str] = field(default_factory=list)
    notes_file: Path = None


def validate(path: Path) -> str:
    from fcpxml import dtd

    ok, detail = dtd.validate_against_dtd(str(path), "1.13")
    if ok is False:
        raise RuntimeError(f"{path.name} is not valid against the FCPXML 1.13 DTD:\n{detail}")
    return detail


def normalize_sample(src: Path, dst: Path) -> None:
    """examples/sample.fcpxml as a DTD-valid 1.13 document, the same cut.

    The shipped file predates media-rep and keeps chapter markers on the
    <sequence>, which Apple's DTD does not allow. Here each asset's src moves
    into a <media-rep>, and each chapter marker moves onto the clip under it
    in that clip's local time, which is where Final Cut keeps them.
    """
    from fcpxml.writer import FCPXMLModifier, _dtd_insert
    from xml.etree import ElementTree as ET
    from fcpxml.rational import parse_seconds

    mod = FCPXMLModifier(str(src))
    root = mod.root
    for asset in root.iter("asset"):
        s = asset.attrib.pop("src", None)
        if s and asset.find("media-rep") is None:
            ET.SubElement(asset, "media-rep", {"kind": "original-media", "src": s})
    seq = root.find(".//sequence")
    spine = seq.find("spine")
    for cm in list(seq.findall("chapter-marker")):
        seq.remove(cm)
        at = parse_seconds(cm.get("start", "0s"))
        for clip in spine:
            off, dur = parse_seconds(clip.get("offset", "0s")), parse_seconds(clip.get("duration", "0s"))
            if off <= at < off + dur:
                local = parse_seconds(clip.get("start", "0s")) + (at - off)
                cm.set("start", f"{local}s" if local.denominator == 1 else f"{local.numerator}/{local.denominator}s")
                _dtd_insert(clip, cm)
                break
    root.set("version", "1.13")
    mod.save(str(dst))
    validate(dst)


def _hand_edit(src: Path, dst: Path, edit: Callable) -> None:
    """The editor's part: done in Final Cut, so it is not in any journal."""
    from fcpxml.writer import FCPXMLModifier

    mod = FCPXMLModifier(str(src))
    edit(mod.root)
    mod.save(str(dst))
    validate(dst)


def _tick(root, ids: List[int]) -> None:
    """Tick the to-do checkbox on markers #N, as an editor does in Final Cut."""
    for m in root.iter("marker"):
        mm = re.match(r"#(\d+)\b", m.get("value", ""))
        if mm and int(mm.group(1)) in ids:
            m.set("completed", "1")


def _delete_connected(root, name: str) -> None:
    for parent in root.iter():
        for child in list(parent):
            if child.get("lane") is not None and child.get("name") == name:
                parent.remove(child)
                return
    raise RuntimeError(f"no connected clip named {name}")


def _agent(folder: Path, start: Path, steps: List[tuple], skip, log: List[str]) -> Path:
    current = start
    for i, (label, tool, args) in enumerate(steps, 1):
        if label in skip:
            log.append(f"skipped: {label}")
            continue
        out = folder / f"{start.stem}_agent{i}.fcpxml"
        fcp_call(tool, dict(args, filepath=str(current), output_path=str(out)))
        validate(out)
        log.append(f"{tool}.{args['action']}: {label}")
        current = out
    return current


MUSIC_STEPS = [
    ("trim the head of SHOT B 1 by a second", "edit",
     {"action": "trim_clip", "clip_id": "SHOT B 1", "trim_start": "+1s", "ripple": False}),
    ("trim the end of OVERLAY 3 by a second", "edit",
     {"action": "trim_clip", "clip_id": "OVERLAY 3", "trim_end": "-1s", "ripple": False}),
    ("slow DRONE 1 to half speed", "edit",
     {"action": "change_speed", "clip_id": "DRONE 1", "speed": 0.5}),
]


def music_video(folder: Path, skip=()) -> Round:
    """A gap-based music video: every clip connected, notes from a text file."""
    from cutreview import api

    folder.mkdir(parents=True, exist_ok=True)
    _env(folder / "journal")
    base = folder / "music-video.fcpxml"
    shutil.copy(FIXTURES / "music-video.fcpxml", base)
    notes = folder / "music-video.notes.txt"
    shutil.copy(FIXTURES / "music-video.notes.txt", notes)
    marked = folder / "music-video_notes.fcpxml"
    api.notes(str(base), str(notes), str(marked))
    validate(marked)
    log: List[str] = []
    after_agent = _agent(folder, marked, MUSIC_STEPS, skip, log)
    nxt = folder / "music-video_v2.fcpxml"

    def editor(root):
        if "delete OVERLAY 1 by hand" not in skip:
            _delete_connected(root, "OVERLAY 1")
            log.append("by hand: delete OVERLAY 1")
        _tick(root, [1, 2, 5])
        log.append("by hand: tick #1, #2, #5")

    _hand_edit(after_agent, nxt, editor)
    return Round(folder, base, marked, nxt, log, notes)


SAMPLE_STEPS = [
    # fcp-mcp-server finds clips by name, and three clips are named Broll_City:
    # this trims the LAST one, not the one the note is on.
    ("trim Broll_City by 12 frames", "edit",
     {"action": "trim_clip", "clip_id": "Broll_City", "trim_end": "-12f"}),
    ("delete the 6-frame Broll_Studio flash", "edit",
     {"action": "delete_clips", "clip_ids": ["Broll_Studio"]}),
    ("move Broll_City to the end", "edit",
     {"action": "reorder_clips", "clip_ids": ["Broll_City"], "target_position": "end"}),
    ("dissolve out of Interview_A", "edit",
     {"action": "add_transition", "clip_id": "Interview_A", "position": "end"}),
]


def sample(folder: Path, skip=()) -> Round:
    """A spine-based interview cut: notes from a Frame.io-shaped comment CSV."""
    from cutreview import api

    folder.mkdir(parents=True, exist_ok=True)
    _env(folder / "journal")
    shutil.copy(FIXTURES / "sample.fcpxml", folder / "sample.fcpxml")
    base = folder / "sample_dtd.fcpxml"
    normalize_sample(folder / "sample.fcpxml", base)
    notes = folder / "sample.frameio.csv"
    shutil.copy(FIXTURES / "sample.frameio.csv", notes)
    marked = folder / "sample_dtd_notes.fcpxml"
    api.notes(str(base), str(notes), str(marked))
    validate(marked)
    log: List[str] = []
    after_agent = _agent(folder, marked, SAMPLE_STEPS, skip, log)
    nxt = folder / "sample_v2.fcpxml"

    def editor(root):
        _tick(root, [2])
        log.append("by hand: tick #2")

    _hand_edit(after_agent, nxt, editor)
    return Round(folder, base, marked, nxt, log, notes)


def build_all(folder: Path) -> Dict[str, Round]:
    return {"music-video": music_video(folder / "music-video"), "sample": sample(folder / "sample")}


def frac(x) -> Fraction:
    return Fraction(str(x))
