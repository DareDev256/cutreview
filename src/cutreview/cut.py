"""Read one FCPXML cut into spans: every clip, where it plays, what it plays.

Built on fcp-mcp-server's own element walker (``FCPXMLModifier``): the spine,
the connected-clip iteration and the anchored-offset arithmetic are its code,
so a file fcp-mcp-server wrote reads back here the way fcp-mcp-server meant
it. What this module adds is the one thing a review needs from every clip:
its range on the timeline and its range on the SOURCE, exact, with the
element kept so notes can be written onto it.

All times are ``Fraction`` seconds. Timeline times count from the first frame
of the cut (fcp-mcp-server's ``timeline_origin``); the sequence's own start
timecode (``tcStart``) is kept separately and only added for display.
"""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Iterator, List, Optional
from urllib.parse import unquote, urlparse
from xml.etree import ElementTree as ET

from fcpxml.rational import parse_seconds
from fcpxml.writer import FCPXMLModifier

# Elements that play something on the timeline. 'gap' is not one of them,
# but its connected children are.
CLIP_TAGS = (
    "asset-clip", "clip", "video", "audio", "title", "ref-clip",
    "mc-clip", "sync-clip",
)
MARKER_TAGS = ("marker", "chapter-marker")
# Children that change what the clip looks or sounds like.
_LOOK_PREFIXES = ("adjust-", "filter-")
_LOOK_TAGS: tuple = ()  # conform-rate travels with a speed change, which is reported as a retime


def _t(value: Optional[str]) -> Fraction:
    return parse_seconds(value) if value else Fraction(0)


def file_sha256(path: str | Path) -> str:
    p = Path(path)
    if p.is_dir():
        p = p / "Info.fcpxml"
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class MarkerRec:
    """One marker as written, placed on the timeline and on the source."""
    elem: ET.Element = field(repr=False, compare=False)
    tag: str
    value: str
    note: str
    completed: Optional[str]      # "0", "1", or None for a plain marker
    local: Fraction               # the raw 'start' (host's local time)
    duration: Fraction
    tl: Fraction                  # timeline position
    src: Fraction                 # source position (asset clock)
    span: "Span" = field(repr=False, compare=False, default=None)

    @property
    def is_todo(self) -> bool:
        return self.tag == "marker" and self.completed in ("0", "1")


@dataclass
class Span:
    """A clip on the timeline."""
    idx: int
    elem: ET.Element = field(repr=False, compare=False)
    host: Optional[ET.Element] = field(repr=False, compare=False)
    tag: str
    name: str
    key: str                      # what it plays: asset uid, else media src, else name
    asset_name: str
    lane: int                     # 0 is the primary storyline
    tl_in: Fraction
    tl_out: Fraction
    local_in: Fraction            # the clip's 'start' attribute
    src_in: Fraction              # source time actually played (after any timeMap)
    src_out: Fraction
    timemap: tuple = ()           # ((local, media), ...) when retimed
    media_path: str = ""          # local file path, '' when not a file URL
    asset_origin: Fraction = Fraction(0)
    still: bool = False
    has_video: bool = True
    look: tuple = ()
    enabled: bool = True
    markers: List[MarkerRec] = field(default_factory=list)

    @property
    def duration(self) -> Fraction:
        return self.tl_out - self.tl_in

    @property
    def speed(self) -> Optional[Fraction]:
        """Source seconds per timeline second, None when it plays 1:1."""
        if not self.timemap or self.duration <= 0:
            return None
        s = (self.src_out - self.src_in) / self.duration
        return None if s == 1 else s

    def local_to_src(self, local: Fraction) -> Fraction:
        if not self.timemap:
            return local
        pts = self.timemap
        if local <= pts[0][0]:
            (t0, v0), (t1, v1) = pts[0], pts[1] if len(pts) > 1 else (pts[0][0] + 1, pts[0][1] + 1)
        elif local >= pts[-1][0]:
            (t0, v0), (t1, v1) = (pts[-2] if len(pts) > 1 else (pts[-1][0] - 1, pts[-1][1] - 1)), pts[-1]
        else:
            for (t0, v0), (t1, v1) in zip(pts, pts[1:]):
                if t0 <= local <= t1:
                    break
        if t1 == t0:
            return v0
        return v0 + (local - t0) * (v1 - v0) / (t1 - t0)

    def tl_to_src(self, tl: Fraction) -> Fraction:
        return self.local_to_src(self.local_in + (tl - self.tl_in))

    def src_to_tl(self, src: Fraction) -> Fraction:
        """Where a source frame plays (linear inverse; exact without a ramp)."""
        span_src = self.src_out - self.src_in
        if span_src == 0:
            return self.tl_in
        return self.tl_in + (src - self.src_in) * self.duration / span_src

    def file_time(self, tl: Fraction) -> Fraction:
        """Seconds into the media FILE for timeline time *tl*."""
        if self.still:
            return Fraction(0)
        return self.tl_to_src(tl) - self.asset_origin


@dataclass
class Transition:
    name: str
    tl_in: Fraction
    tl_out: Fraction
    cut: Fraction                 # the edit point it sits on
    out_key: str = ""             # what plays before the cut
    out_src: Fraction = Fraction(0)


@dataclass
class Cut:
    path: str
    sha256: str
    version: str
    project: str
    frame_duration: Fraction
    width: int
    height: int
    tc_start: Fraction
    origin: Fraction
    duration: Fraction
    spans: List[Span]
    transitions: List[Transition]
    exported: str                 # when the file says it was made
    exported_source: str          # where that time came from
    modifier: FCPXMLModifier = field(repr=False, compare=False)

    @property
    def name(self) -> str:
        return Path(self.path).name

    @property
    def timebase(self) -> int:
        return self.frame_duration.denominator

    def markers(self) -> Iterator[MarkerRec]:
        for s in self.spans:
            yield from s.markers

    def spans_at(self, tl: Fraction) -> List[Span]:
        return [s for s in self.spans if s.tl_in <= tl < s.tl_out]

    def picture_at(self, tl: Fraction) -> Optional[Span]:
        """The clip whose picture shows at *tl*: highest lane at or above the spine."""
        pics = [s for s in self.spans_at(tl) if s.has_video and s.lane >= 0 and s.enabled]
        return max(pics, key=lambda s: (s.lane, s.idx)) if pics else None


def _local_path(src: str) -> str:
    if not src:
        return ""
    u = urlparse(src)
    if u.scheme in ("", "file"):
        return unquote(u.path)
    return ""


def _canon(el: ET.Element) -> tuple:
    return (el.tag, tuple(sorted(el.attrib.items())), tuple(_canon(c) for c in el))


class _Resources:
    def __init__(self, root: ET.Element):
        self.by_id: dict[str, ET.Element] = {}
        res = root.find("resources")
        if res is not None:
            for el in res:
                if el.get("id"):
                    self.by_id[el.get("id")] = el

    def describe(self, ref: Optional[str]) -> dict:
        el = self.by_id.get(ref or "")
        if el is None:
            return {"key": "", "name": "", "src": "", "origin": Fraction(0),
                    "still": False, "has_video": True}
        src = el.get("src", "")
        rep = el.find("media-rep")
        if rep is not None and rep.get("src"):
            src = rep.get("src")
        uid = el.get("uid", "")
        name = el.get("name", "")
        if uid:
            key = f"uid:{uid}"
        elif src:
            key = f"src:{src}"
        else:
            key = f"{el.tag}:{name or ref}"
        fmt = self.by_id.get(el.get("format", ""))
        still = (
            el.tag == "asset" and el.get("duration", "") in ("0s", "0")
        ) or (fmt is not None and "RateUndefined" in fmt.get("name", ""))
        return {
            "key": key, "name": name, "src": src,
            "origin": _t(el.get("start")), "still": still,
            "has_video": el.get("hasVideo", "1") != "0" if el.tag == "asset" else True,
        }


def _inner_media(el: ET.Element) -> Optional[ET.Element]:
    """For a <clip>/<sync-clip>, the non-lane child that carries the media."""
    for child in el:
        if child.get("lane") is None and child.tag in ("video", "asset-clip", "audio", "clip", "ref-clip"):
            return child
    return None


def load(path: str | Path) -> Cut:
    """Read a cut. Accepts ``.fcpxml`` files and ``.fcpxmld`` bundles."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))
    mod = FCPXMLModifier(str(p))
    root = mod.root
    res = _Resources(root)

    seq = root.find(".//project/sequence")
    if seq is None:
        seq = root.find(".//sequence")
    if seq is None:
        raise ValueError(f"{p.name} holds no project with a sequence")
    project = root.find(".//project")
    fmt = res.by_id.get(seq.get("format", ""))
    fd = _t(fmt.get("frameDuration")) if fmt is not None and fmt.get("frameDuration") else Fraction(1, 24)
    width = int(fmt.get("width", 0) or 0) if fmt is not None else 0
    height = int(fmt.get("height", 0) or 0) if fmt is not None else 0

    spine = mod._get_spine()
    origin = mod.timeline_origin()
    spans: List[Span] = []
    transitions: List[Transition] = []

    def make_span(el: ET.Element, host: Optional[ET.Element], lane: int, tl_in: Fraction) -> Span:
        ref = el.get("ref")
        media = el
        if el.tag in ("clip", "sync-clip") and not ref:
            inner = _inner_media(el)
            if inner is not None:
                media, ref = inner, inner.get("ref")
        info = res.describe(ref)
        dur = _t(el.get("duration"))
        local_in = _t(el.get("start"))
        timemap = tuple(
            (_t(tp.get("time")), _t(tp.get("value")))
            for tp in el.findall("timeMap/timept")
        )
        if el.tag == "title":
            key = f"title:{el.get('name', '')}"
            info["has_video"] = True
        else:
            key = info["key"] or f"{el.tag}:{el.get('name', '')}"
        span = Span(
            idx=len(spans), elem=el, host=host, tag=el.tag,
            name=el.get("name") or info["name"] or el.tag,
            key=key, asset_name=info["name"], lane=lane,
            tl_in=tl_in, tl_out=tl_in + dur, local_in=local_in,
            src_in=Fraction(0), src_out=Fraction(0), timemap=timemap,
            media_path=_local_path(info["src"]),
            asset_origin=info["origin"], still=info["still"],
            has_video=info["has_video"] and el.tag != "audio",
            look=tuple(
                _canon(c) for c in el
                if c.tag.startswith(_LOOK_PREFIXES) or c.tag in _LOOK_TAGS
            ),
            enabled=el.get("enabled", "1") != "0",
        )
        if media is not el and el.tag in ("clip", "sync-clip"):
            # The wrapper's local clock maps onto the inner media's start.
            shift = _t(media.get("start")) - _t(media.get("offset"))
            span.local_in = local_in
            span.src_in = local_in + shift
            span.src_out = span.src_in + dur
        else:
            span.src_in = span.local_to_src(local_in)
            span.src_out = span.local_to_src(local_in + dur)
        for m in el:
            if m.tag in MARKER_TAGS:
                mlocal = _t(m.get("start"))
                span.markers.append(MarkerRec(
                    elem=m, tag=m.tag, value=m.get("value", ""),
                    note=m.get("note", ""), completed=m.get("completed"),
                    local=mlocal, duration=_t(m.get("duration")) or fd,
                    tl=tl_in + (mlocal - local_in), src=span.local_to_src(mlocal),
                    span=span,
                ))
        spans.append(span)
        return span

    prev_end: Optional[Span] = None
    for el in spine:
        if el.tag == "transition":
            t_in = _t(el.get("offset")) - origin
            t_dur = _t(el.get("duration"))
            cut_at = prev_end.tl_out if prev_end is not None else t_in + t_dur / 2
            transitions.append(Transition(
                name=el.get("name", "Transition"), tl_in=t_in, tl_out=t_in + t_dur,
                cut=cut_at,
                out_key=prev_end.key if prev_end is not None else "",
                out_src=prev_end.src_out if prev_end is not None else Fraction(0),
            ))
            continue
        if el.tag not in CLIP_TAGS and el.tag != "gap":
            continue
        if el.tag in CLIP_TAGS:
            prev_end = make_span(el, None, 0, _t(el.get("offset")) - origin)
        for child in el:
            if child.get("lane") is not None and child.tag in CLIP_TAGS:
                make_span(child, el, int(child.get("lane")),
                          mod.connected_timeline_offset(child, el) - origin)
            elif child.tag == "storyline":
                lane = int(child.get("lane", "1"))
                for sub in child:
                    if sub.tag in CLIP_TAGS:
                        make_span(sub, el, lane, mod.connected_timeline_offset(sub, el) - origin)

    seq_dur = _t(seq.get("duration"))
    end = max([s.tl_out for s in spans] + [seq_dur])
    mod_date = (project.get("modDate") if project is not None else None) or ""
    if mod_date:
        exported, exported_source = mod_date, "the project's modDate"
    else:
        st = os.stat(p / "Info.fcpxml" if p.is_dir() else p)
        exported = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))
        exported_source = "the file's modified time"
    return Cut(
        path=str(p), sha256=file_sha256(p), version=root.get("version", ""),
        project=project.get("name", "") if project is not None else "",
        frame_duration=fd, width=width, height=height,
        tc_start=_t(seq.get("tcStart")), origin=origin, duration=end,
        spans=spans, transitions=transitions,
        exported=exported, exported_source=exported_source, modifier=mod,
    )
