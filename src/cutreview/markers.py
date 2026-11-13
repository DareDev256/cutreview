"""Write notes into a cut as Final Cut to-do markers.

Each note becomes ``<marker completed="0" value="#N text" note="...">`` on the
clip whose picture shows at the note's time, in that clip's local (source)
time, so the marker travels with the clip through a recut. ``completed`` and
``note`` are both declared on ``marker`` in Apple's FCPXMLv1_13.dtd and
FCPXMLv1_14.dtd ("0=not completed, 1=completed").

Two instruments check every write before it is kept:

1. ``xmllint`` against Apple's DTD from the installed Final Cut Pro. A file
   that was valid stays valid; a file that was already invalid may carry its
   old errors but no new one.
2. fcp-mcp-server's parser reads the written file back, independently of the
   walker that placed the markers, and each marker must land on its note's
   frame (within one frame) on the clip it was meant for.

Either check failing deletes the output and raises.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import List, Optional, Tuple

from fcpxml import dtd as fcp_dtd
from fcpxml.models import MarkerType
from fcpxml.parser import FCPXMLParser
from fcpxml.writer import build_marker_element

from .cut import Cut, Span
from .notes import Note, NoteSet
from .timecode import fcpxml_time, format_tc, to_frames

ID_RE = re.compile(r"^#(\d+)\b")
WRITE_VERSION = "1.13"
_NAME_LIMIT = 120


class WriteRefused(RuntimeError):
    """The output failed a check and was not kept."""


@dataclass
class Placement:
    note: Note
    span: Span
    local: Fraction
    duration: Fraction
    on_audio: bool


def next_id(cut: Cut) -> int:
    ids = [int(m.group(1)) for mk in cut.markers() for m in [ID_RE.match(mk.value)] if m]
    return max(ids, default=0) + 1


def target_span(cut: Cut, t: Fraction) -> Tuple[Optional[Span], bool]:
    """The clip a note at *t* belongs on, and whether it is an audio-only fallback."""
    pic = cut.picture_at(t)
    if pic is not None:
        return pic, False
    sound = [s for s in cut.spans_at(t) if s.enabled]
    if sound:
        return max(sound, key=lambda s: (s.lane, s.idx)), True
    return None, False


def place(cut: Cut, ns: NoteSet) -> List[Placement]:
    """Choose a clip for each timed note. Notes over nothing move to unplaced."""
    fd = cut.frame_duration
    out: List[Placement] = []
    nid = next_id(cut)
    keep = []
    for note in ns.notes:
        t = to_frames(note.at, fd) * fd                     # on the timeline's frame grid
        span, on_audio = target_span(cut, t)
        if span is None:
            note.placed = {"reason": f"no clip under {format_tc(t, fd, cut.tc_start)} (a gap)"}
            ns.unplaced.append(note)
            continue
        dur = fd
        if note.until is not None:
            end = min(to_frames(note.until, fd) * fd, span.tl_out)
            dur = max(fd, end - t)
        note.id = nid
        nid += 1
        local = span.local_in + (t - span.tl_in)
        note.placed = {
            "clip": span.name, "lane": span.lane, "at": float(t),
            "timecode": format_tc(t, fd, cut.tc_start), "on_audio": on_audio,
        }
        out.append(Placement(note, span, local, dur, on_audio))
        keep.append(note)
    ns.notes = keep
    return out


def marker_name(note: Note) -> str:
    first = note.text.strip().splitlines()[0] if note.text.strip() else ""
    if len(first) > _NAME_LIMIT:
        first = first[: _NAME_LIMIT - 3].rstrip() + "..."
    return f"#{note.id} {first}"


def marker_note(note: Note) -> str:
    """One line: XML folds a newline inside an attribute into a space on read."""
    who = f"from {note.author}, " if note.author else ""
    when = note.tc_in + (f" to {note.tc_out}" if note.tc_out else "")
    body = " / ".join(line.strip() for line in note.text.strip().splitlines() if line.strip())
    return f"{body} ({who}{note.origin}, written at {when})"


def _validate(path: Path, version: str) -> Tuple[Optional[bool], List[str], str]:
    ok, detail = fcp_dtd.validate_against_dtd(str(path), version)
    errors = []
    if ok is False:
        for line in detail.splitlines():
            if "validity error" in line or "parser error" in line:
                # Drop the file name and line number: compare the complaint itself.
                errors.append(re.sub(r"^.*?:\d+:\s*", "", line).strip())
    return ok, errors, detail


def write_markers(cut: Cut, placements: List[Placement], output: Path) -> dict:
    """Write every placement into a copy of the cut at *output*; check it; keep it or refuse."""
    root = cut.modifier.root
    in_version = root.get("version", "")
    try:
        newer = tuple(int(x) for x in in_version.split(".")) > (1, 13)
    except ValueError:
        newer = False
    version = in_version if newer else WRITE_VERSION

    for pl in placements:
        build_marker_element(
            parent=pl.span.elem,
            marker_type=MarkerType.COMPLETED if pl.note.complete else MarkerType.INCOMPLETE,
            start=fcpxml_time(pl.local, cut.timebase),
            duration=fcpxml_time(pl.duration, cut.timebase),
            name=marker_name(pl.note),
            note=marker_note(pl.note),
        )
    root.set("version", version)

    output = Path(output)
    tmpdir = Path(tempfile.mkdtemp(prefix=".cutreview-", dir=output.parent))
    staged = tmpdir / output.name
    try:
        cut.modifier.save(str(staged))
        report = _check(cut, placements, staged, version)
        if output.exists():
            if output.is_dir():
                shutil.rmtree(output)
            else:
                output.unlink()
        shutil.move(str(staged), str(output))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    report["path"] = str(output)
    return report


def _check(cut: Cut, placements: List[Placement], staged: Path, version: str) -> dict:
    report = {"version": version, "dtd": "unchecked", "dtd_detail": ""}
    ok, errors, detail = _validate(staged, version)
    if ok is None:
        report["dtd"], report["dtd_detail"] = "unchecked", detail
    elif ok:
        report["dtd"], report["dtd_detail"] = "valid", detail
    else:
        # Was the input already invalid at this version? Check a copy with only
        # the version attribute raised, so the comparison is like for like.
        src = Path(cut.path)
        src_file = src / "Info.fcpxml" if src.is_dir() else src
        before_dir = Path(tempfile.mkdtemp(prefix=".cutreview-in-"))
        try:
            text = src_file.read_text(encoding="utf-8")
            text = re.sub(r'(<fcpxml\b[^>]*\bversion=")[^"]*(")', rf"\g<1>{version}\g<2>", text, count=1)
            before = before_dir / "input.fcpxml"
            before.write_text(text, encoding="utf-8")
            _, before_errors, _ = _validate(before, version)
        finally:
            shutil.rmtree(before_dir, ignore_errors=True)
        new = [e for e in errors if e not in before_errors]
        if new:
            raise WriteRefused(
                "the marked file would not validate against Apple's FCPXML "
                f"{version} DTD, and the input did. New errors:\n  " + "\n  ".join(new[:10])
            )
        report["dtd"] = "input-invalid"
        report["dtd_detail"] = (
            f"the input was already not valid against the {version} DTD "
            f"({len(before_errors)} errors); cutreview added none"
        )

    # Second instrument: fcp-mcp-server's parser, which places markers by its
    # own arithmetic (cumulative frame counts), not by the walker used above.
    tl = FCPXMLParser().parse_file(str(staged)).primary_timeline
    found = {}
    for clip in list(tl.clips) + list(tl.connected_clips):
        for m in clip.markers:
            mm = ID_RE.match(m.name)
            if mm:
                found[int(mm.group(1))] = (clip.name, m.position.frames)
    misses = []
    for pl in placements:
        want = to_frames(pl.span.tl_in + (pl.local - pl.span.local_in), cut.frame_duration)
        got = found.get(pl.note.id)
        if got is None:
            misses.append(f"#{pl.note.id} is missing from the written file")
        elif got[0] != pl.span.name or abs(got[1] - want) > 1:
            misses.append(f"#{pl.note.id} reads back on '{got[0]}' at frame {got[1]}, meant '{pl.span.name}' at frame {want}")
    if misses:
        raise WriteRefused("placement check failed:\n  " + "\n  ".join(misses))
    report["readback"] = f"{len(placements)} markers read back on their clips, each within one frame"
    return report
