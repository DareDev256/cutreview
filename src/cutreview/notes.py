"""Read review notes: plain text with timecodes, a generic CSV, Frame.io's comment CSV.

Three promises, each tested:

* A note with no timecode is listed as UNPLACED. It is never given a time.
* A line or row that cannot be read is listed as UNREADABLE with the reason
  and its original text. Nothing is dropped silently.
* No AI touches the notes. Parsing is rules you can read below.

Timecodes are read at the cut's own frame rate, counted from the sequence's
start timecode (what Final Cut shows in the timeline). See ``resolve_times``
for the one automatic adjustment: a review copy that starts at 01:00:00:00.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import asdict, dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import List, Optional

from .timecode import TC_RE, TimecodeError, parse_tc

FORMATS = ("auto", "text", "csv", "frameio")
HOUR = Fraction(3600)


@dataclass
class Note:
    text: str
    origin: str                   # where it came from: "notes.txt line 4", "comments.csv row 7"
    author: str = ""
    tc_in: str = ""               # the timecode exactly as written
    tc_out: str = ""
    at: Optional[Fraction] = None     # seconds from the first frame of the cut
    until: Optional[Fraction] = None
    complete: bool = False        # Frame.io says it was already resolved
    id: int = 0
    placed: Optional[dict] = None

    def to_json(self) -> dict:
        d = asdict(self)
        d["at"] = float(self.at) if self.at is not None else None
        d["until"] = float(self.until) if self.until is not None else None
        return d


@dataclass
class Rejected:
    origin: str
    text: str
    reason: str

    def to_json(self) -> dict:
        return asdict(self)


@dataclass
class NoteSet:
    source: str
    format: str
    notes: List[Note] = field(default_factory=list)       # have a timecode
    unplaced: List[Note] = field(default_factory=list)    # no timecode, or no clip under it
    unreadable: List[Rejected] = field(default_factory=list)
    time_base: str = ""


class NotesFileError(ValueError):
    """The whole file cannot be read as the chosen format."""


# -- plain text ---------------------------------------------------------------

_LEAD = re.compile(
    r"^\s*[\[(]?@?\s*(?P<a>" + TC_RE.pattern + r")\s*"
    r"(?:(?:-|–|—|to)\s*(?P<b>" + TC_RE.pattern + r")\s*)?[\])]?\s*"
    r"(?:[-–—:|>]\s*)?(?P<text>.*)$"
)
# Shaped like the start of a timecode but not readable as one: '1:75:00', '00:00:12:99'.
_TC_SHAPED = re.compile(r"^\s*[\[(]?@?\s*\d{1,2}[:;]\d")


def _read_lines(data: bytes, name: str, rejected: List[Rejected]) -> List[tuple]:
    lines = []
    for i, raw in enumerate(data.split(b"\n"), 1):
        raw = raw.rstrip(b"\r")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as e:
            rejected.append(Rejected(
                f"{name} line {i}", raw.decode("utf-8", errors="replace"),
                f"not UTF-8 text (byte {e.start}); save the file as UTF-8",
            ))
            continue
        lines.append((i, text))
    return lines


def parse_text(data: bytes, name: str, frame_duration: Fraction, author: str = "") -> NoteSet:
    """One note per line, timecode first. Indented lines continue the note above."""
    ns = NoteSet(source=name, format="text")
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    lines = _read_lines(data, name, ns.unreadable)
    last: Optional[Note] = None
    for i, text in lines:
        if not text.strip():
            last = None
            continue
        origin = f"{name} line {i}"
        if text[:1] in (" ", "\t") and last is not None:
            last.text += "\n" + text.strip()
            continue
        m = _LEAD.match(text)
        if m:
            try:
                at = parse_tc(m.group("a"), frame_duration)
                until = parse_tc(m.group("b"), frame_duration) if m.group("b") else None
            except TimecodeError as e:
                ns.unreadable.append(Rejected(origin, text, str(e)))
                last = None
                continue
            body = m.group("text").strip()
            if not body:
                ns.unreadable.append(Rejected(origin, text, "a timecode with no note after it"))
                last = None
                continue
            if until is not None and until <= at:
                ns.unreadable.append(Rejected(origin, text, "the range ends before it starts"))
                last = None
                continue
            last = Note(text=body, origin=origin, author=author, tc_in=m.group("a"),
                        tc_out=m.group("b") or "", at=at, until=until)
            ns.notes.append(last)
        elif _TC_SHAPED.match(text):
            ns.unreadable.append(Rejected(origin, text, "starts like a timecode but is not one"))
            last = None
        else:
            last = Note(text=text.strip(), origin=origin, author=author)
            ns.unplaced.append(last)
    return ns


# -- CSV ------------------------------------------------------------------------

def _norm(h: str) -> str:
    return re.sub(r"[^a-z0-9]", "", h.lower())


_GENERIC = {
    "time": ("timecode", "time", "tc", "in", "start", "timecodein", "timestamp", "position", "at"),
    "out": ("out", "end", "timecodeout", "until"),
    "text": ("note", "notes", "comment", "comments", "text", "feedback", "description", "message"),
    "author": ("author", "name", "reviewer", "commenter", "user", "by", "from"),
}

# Frame.io comment CSV. No current header list is published (V4's help pages
# describe the menu, not the columns). These names come from the V3-era
# exports quoted by users: "Timecode" and "Timecode Source" (SoundFlow forum,
# 2022-12-06) and the 20-field row read positionally by adamhawkey/EDL_tools
# (Commenter, Comment, Reply, Complete, Annotation, Frame, Duration, Timecode,
# Timecode In/Out, Timecode Source In/Out). Matching is by normalised header
# NAME, never by position, so added or reordered columns still read.
_FRAMEIO = {
    "text": ("comment", "commenttext", "text"),
    "author": ("commenter", "author", "name", "user"),
    "time": ("timecodein", "timecode", "intimecode"),
    "out": ("timecodeout", "outtimecode"),
    "src_time": ("timecodesourcein", "timecodesource", "sourcetimecode", "timecodesrc"),
    "src_out": ("timecodesourceout", "timecodesrcout"),
    "frame": ("frame", "frameno", "framenumber"),
    "reply": ("reply", "replies"),
    "complete": ("complete", "completed", "resolved", "status"),
    "annotation": ("annotation", "annotations", "drawing"),
}


def _pick(headers: List[str], names: tuple) -> Optional[int]:
    normed = [_norm(h) for h in headers]
    for n in names:
        if n in normed:
            return normed.index(n)
    return None


def looks_like_frameio(headers: List[str]) -> bool:
    normed = {_norm(h) for h in headers}
    return "commenter" in normed and "comment" in normed and bool(
        normed & {"timecode", "timecodein", "frame", "timecodesource"}
    )


def _read_csv(data: bytes, name: str) -> tuple:
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("utf-8", errors="replace")
    rows = list(csv.reader(io.StringIO(text, newline="")))
    while rows and not any(c.strip() for c in rows[0]):
        rows.pop(0)
    if not rows:
        raise NotesFileError(f"{name} is empty")
    return rows[0], rows[1:]


def _seconds_cell(value: str, frame_duration: Fraction) -> Fraction:
    v = value.strip()
    if re.fullmatch(r"\d+(\.\d+)?", v):
        return Fraction(v)
    return parse_tc(v, frame_duration)


def parse_csv(data: bytes, name: str, frame_duration: Fraction, frameio: bool = False,
              author: str = "", use_source_tc: bool = False) -> NoteSet:
    headers, rows = _read_csv(data, name)
    table = _FRAMEIO if frameio else _GENERIC
    col = {k: _pick(headers, v) for k, v in table.items()}
    if col["text"] is None:
        raise NotesFileError(
            f"{name}: no note column. Headers are {headers}; expected one of {list(table['text'])}"
        )
    tkey, okey = ("src_time", "src_out") if (frameio and use_source_tc) else ("time", "out")
    if col.get(tkey) is None and col.get("frame") is None:
        raise NotesFileError(
            f"{name}: no timecode column. Headers are {headers}; expected one of {list(table[tkey])}"
        )
    ns = NoteSet(source=name, format="frameio" if frameio else "csv")
    last: Optional[Note] = None

    def cell(row, key):
        i = col.get(key)
        return row[i].strip() if i is not None and i < len(row) else ""

    for r, row in enumerate(rows, 2):
        origin = f"{name} row {r}"
        joined = ",".join(row)
        if not any(c.strip() for c in row):
            continue
        if len(row) < len(headers) and len(row) <= max(i for i in col.values() if i is not None):
            ns.unreadable.append(Rejected(origin, joined, f"{len(row)} cells where the header has {len(headers)}"))
            last = None
            continue
        text = cell(row, "text")
        reply = cell(row, "reply") if frameio else ""
        who = cell(row, "author") or author
        if not text and reply and last is not None:
            last.text += f"\nReply{f' from {who}' if who else ''}: {reply}"
            continue
        if reply:
            text = f"{text}\nReply: {reply}" if text else reply
        if not text:
            ns.unreadable.append(Rejected(origin, joined, "no note text in this row"))
            last = None
            continue
        if frameio and cell(row, "annotation"):
            text += "\n(has a drawing in Frame.io)"
        t_raw, o_raw = cell(row, tkey), cell(row, okey)
        if not t_raw and col.get("frame") is not None and cell(row, "frame"):
            frame_raw = cell(row, "frame")
            if not frame_raw.isdigit():
                ns.unreadable.append(Rejected(origin, joined, f"frame '{frame_raw}' is not a number"))
                last = None
                continue
            at, until = int(frame_raw) * frame_duration, None
            t_raw = f"frame {frame_raw}"
        elif not t_raw:
            last = Note(text=text, origin=origin, author=who)
            ns.unplaced.append(last)
            continue
        else:
            try:
                at = _seconds_cell(t_raw, frame_duration)
                until = _seconds_cell(o_raw, frame_duration) if o_raw else None
            except TimecodeError as e:
                ns.unreadable.append(Rejected(origin, joined, str(e)))
                last = None
                continue
            if until is not None and until <= at:
                until = None      # Frame.io writes in == out for a point comment
        done = frameio and cell(row, "complete").lower() in ("true", "yes", "1", "complete", "completed", "resolved")
        last = Note(text=text, origin=origin, author=who, tc_in=t_raw, tc_out=o_raw,
                    at=at, until=until, complete=done)
        ns.notes.append(last)
    return ns


# -- front door ----------------------------------------------------------------

def read_notes(path: str | Path, frame_duration: Fraction, fmt: str = "auto",
               author: str = "", use_source_tc: bool = False) -> NoteSet:
    p = Path(path)
    data = p.read_bytes()
    if fmt not in FORMATS:
        raise NotesFileError(f"unknown format '{fmt}'; use one of {', '.join(FORMATS)}")
    if fmt == "auto":
        if p.suffix.lower() == ".csv":
            headers, _ = _read_csv(data, p.name)
            fmt = "frameio" if looks_like_frameio(headers) else "csv"
        else:
            fmt = "text"
    if fmt == "text":
        return parse_text(data, p.name, frame_duration, author)
    return parse_csv(data, p.name, frame_duration, frameio=(fmt == "frameio"),
                     author=author, use_source_tc=use_source_tc)


def resolve_times(ns: NoteSet, tc_start: Fraction, duration: Fraction,
                  start_tc: Optional[Fraction] = None) -> None:
    """Turn timecodes as written into seconds from the first frame of the cut.

    *start_tc* given: every timecode counts from it. Otherwise (auto):

    1. Timecodes count from the sequence's start timecode, as Final Cut
       shows them. A note before that start counts from zero instead.
    2. One adjustment for the whole file, never per note: when the sequence
       starts at zero, the cut is shorter than an hour, and EVERY note reads
       at or past 01:00:00:00, the review copy was exported with an hour
       start, so an hour comes off each. The page says so.

    A note that lands past the end of the cut moves to unplaced with the reason.
    """
    if start_tc is not None:
        base, ns.time_base = start_tc, "counted from the start timecode given"
    else:
        base, ns.time_base = tc_start, "counted from the sequence's start timecode"
        timed = [n for n in ns.notes if n.at is not None]
        if tc_start == 0 and duration < HOUR and timed and all(n.at >= HOUR for n in timed):
            base, ns.time_base = HOUR, "read as a review copy starting at 01:00:00:00 (every note was past one hour)"
    keep = []
    for n in ns.notes:
        b = base if n.at >= base else Fraction(0)
        n.at -= b
        if n.until is not None:
            n.until -= b
        if n.at >= duration:
            n.placed = {"reason": "after the end of the cut"}
            ns.unplaced.append(n)
        else:
            keep.append(n)
    ns.notes = keep
