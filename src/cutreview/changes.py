"""What changed between two cuts, in the editor's terms.

fcp-mcp-server's ``fcpxml.diff`` matches clips by (name, source in-point) on
the primary storyline. On real review rounds that reads wrong three ways,
each measured in ``tests/test_changes.py::test_why_not_diff_py``:

1. A cut whose clips are all connected (a music video over a gap) reports
   no clip changes at all.
2. A head trim moves the in-point, so the clip reads as removed and added.
3. A ripple trim shifts every later clip, so each one reads as moved.

So the match here is on CONTENT. Each clip is a range of a source; two cuts
are compared source by source, and a change is material that left the cut,
material that entered it, material that now plays out of order, or material
that plays differently (speed, effects). A clip that only slid because
something before it got shorter is not a change. fcp-mcp-server's own
``_compare_format`` still reports format changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Dict, List, Optional, Tuple

from fcpxml import diff as fcp_diff
from fcpxml.parser import FCPXMLParser

from .cut import Cut, Span, Transition
from .timecode import format_span, format_tc

Interval = Tuple[Fraction, Fraction]


@dataclass
class Change:
    kind: str                     # removed added trimmed moved retimed adjusted transition format
    name: str
    detail: str
    lane: Optional[int] = None
    old: Optional[Span] = field(default=None, repr=False)
    new: Optional[Span] = field(default=None, repr=False)
    old_tl: Optional[Interval] = None
    new_tl: Optional[Interval] = None
    src: List[Tuple[str, Fraction, Fraction]] = field(default_factory=list)
    before_at: Optional[Fraction] = None
    after_at: Optional[Fraction] = None
    n: int = 0
    blame: Optional[dict] = None

    def signature(self) -> tuple:
        """Identity across two diffs of the same material (used by blame)."""
        return (self.kind, tuple(sorted((k, round(float(a), 2), round(float(b), 2)) for k, a, b in self.src)))


@dataclass
class MarkerChange:
    kind: str                     # added removed ticked unticked
    value: str
    clip: str
    at: Fraction                  # timeline position, in whichever cut holds it


@dataclass
class Review:
    old: Cut
    new: Cut
    changes: List[Change]
    marker_changes: List[MarkerChange]
    slid: int                     # clips that only moved because of a ripple
    pieces: list = field(default_factory=list, repr=False)

    def counts(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for c in self.changes:
            out[c.kind] = out.get(c.kind, 0) + 1
        return out

    def map_old_to_new(self, t: Fraction) -> Fraction:
        return _map(self.pieces, t, forward=True)

    def map_new_to_old(self, t: Fraction) -> Fraction:
        return _map(self.pieces, t, forward=False)


# -- interval helpers ----------------------------------------------------------

def _overlap(a: Interval, b: Interval) -> Optional[Interval]:
    lo, hi = max(a[0], b[0]), min(a[1], b[1])
    return (lo, hi) if hi > lo else None


def _subtract(base: Interval, cuts: List[Interval], tol: Fraction) -> List[Interval]:
    out = [base]
    for c in sorted(cuts):
        nxt = []
        for lo, hi in out:
            if c[1] <= lo or c[0] >= hi:
                nxt.append((lo, hi))
                continue
            if c[0] > lo:
                nxt.append((lo, c[0]))
            if c[1] < hi:
                nxt.append((c[1], hi))
        out = nxt
    return [iv for iv in out if iv[1] - iv[0] > tol]


@dataclass
class _Piece:
    o: Span
    n: Span
    a: Fraction                   # source range shared by both cuts
    b: Fraction

    @property
    def old_tl(self) -> Interval:
        return (self.o.src_to_tl(self.a), self.o.src_to_tl(self.b))

    @property
    def new_tl(self) -> Interval:
        return (self.n.src_to_tl(self.a), self.n.src_to_tl(self.b))

    @property
    def delta(self) -> Fraction:
        return self.new_tl[0] - self.old_tl[0]

    @property
    def spine(self) -> bool:
        return self.o.lane == 0 and self.n.lane == 0


def _map(pieces: List[_Piece], t: Fraction, forward: bool) -> Fraction:
    """Carry a timeline instant from one cut to the other through the spine."""
    spine = [p for p in pieces if p.spine]
    if not spine:
        return t
    src_tl = (lambda p: p.old_tl) if forward else (lambda p: p.new_tl)
    dst_tl = (lambda p: p.new_tl) if forward else (lambda p: p.old_tl)
    for p in spine:
        lo, hi = src_tl(p)
        if lo <= t < hi:
            return dst_tl(p)[0] + (t - lo)
    after = sorted((p for p in spine if src_tl(p)[0] > t), key=lambda p: src_tl(p)[0])
    if after:
        return dst_tl(after[0])[0]
    # Past the last kept material: carry the instant along with it.
    last = max(spine, key=lambda p: src_tl(p)[1])
    return dst_tl(last)[1] + (t - src_tl(last)[1])


def _pair(olds: List[Span], news: List[Span], tol: Fraction) -> List[Tuple[Span, Span]]:
    cand = []
    for o in olds:
        for n in news:
            ov = _overlap((o.src_in, o.src_out), (n.src_in, n.src_out))
            if ov and ov[1] - ov[0] > tol:
                cand.append((ov[1] - ov[0], abs(o.tl_in - n.tl_in), o, n))
    cand.sort(key=lambda c: (-c[0], c[1], c[2].idx, c[3].idx))
    pairs: List[Tuple[Span, Span]] = []
    partners_o: Dict[int, List[Span]] = {}
    partners_n: Dict[int, List[Span]] = {}
    for _, _, o, n in cand:                 # one to one first
        if o.idx not in partners_o and n.idx not in partners_n:
            pairs.append((o, n))
            partners_o[o.idx] = [n]
            partners_n[n.idx] = [o]
    for _, _, o, n in cand:                 # then splits (one old, many new) and joins
        if (o, n) in pairs:
            continue
        region = _overlap((o.src_in, o.src_out), (n.src_in, n.src_out))
        if n.idx not in partners_n and o.idx in partners_o:
            claimed = [_overlap(region, (p.src_in, p.src_out)) for p in partners_o[o.idx]]
            if _subtract(region, [c for c in claimed if c], tol):
                pairs.append((o, n))
                partners_o[o.idx].append(n)
                partners_n[n.idx] = [o]
        elif o.idx not in partners_o and n.idx in partners_n:
            claimed = [_overlap(region, (p.src_in, p.src_out)) for p in partners_n[n.idx]]
            if _subtract(region, [c for c in claimed if c], tol):
                pairs.append((o, n))
                partners_n[n.idx].append(o)
                partners_o[o.idx] = [n]
    return pairs


def _weighted_lis(pieces: List[_Piece]) -> set:
    """Indices of the spine pieces that kept their order (the longest such run)."""
    order = sorted(range(len(pieces)), key=lambda i: pieces[i].old_tl[0])
    best = {}
    prev = {}
    for j, i in enumerate(order):
        w = pieces[i].b - pieces[i].a
        best[i], prev[i] = w, None
        for k in order[:j]:
            if pieces[k].new_tl[0] < pieces[i].new_tl[0] and best[k] + w > best[i]:
                best[i], prev[i] = best[k] + w, k
    if not best:
        return set()
    i = max(best, key=lambda x: best[x])
    keep = set()
    while i is not None:
        keep.add(i)
        i = prev[i]
    return keep


def _look_detail(o: Span, n: Span) -> str:
    def tags(look):
        out: Dict[str, int] = {}
        for item in look:
            out[item[0]] = out.get(item[0], 0) + 1
        return out
    a, b = tags(o.look), tags(n.look)
    added = sorted(t for t in b if t not in a)
    removed = sorted(t for t in a if t not in b)
    changed = sorted(
        t for t in a if t in b
        and [x for x in o.look if x[0] == t] != [x for x in n.look if x[0] == t]
    )
    parts = []
    if o.enabled != n.enabled:
        parts.append("disabled" if not n.enabled else "enabled again")
    if added:
        parts.append("added " + ", ".join(added))
    if removed:
        parts.append("removed " + ", ".join(removed))
    if changed:
        parts.append("changed " + ", ".join(changed))
    return "; ".join(parts) or "adjusted"


def _pct(speed: Optional[Fraction]) -> str:
    return f"{float(speed if speed is not None else 1) * 100:.0f}%"


_PRIORITY = {"src": 0, "uid": 1, "sig": 2}


def unify_sources(old: Cut, new: Cut) -> None:
    """Give every span in both cuts one key per source file, whatever it is called.

    A span carries every identity its source has (media path, uid, sig). Two
    identities on one span are the same source, so a file relinked between
    exports still matches through its uid. Each group of identities is named
    by its strongest member, so the key is the same in any comparison that
    sees the same file. A resource id is never one of them.
    """
    parent: Dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    spans = list(old.spans) + list(new.spans)
    for s in spans:
        ids = s.ids or (s.key,)
        for other in ids[1:]:
            parent[find(other)] = find(ids[0])
        find(ids[0])
    groups: Dict[str, List[str]] = {}
    for token in list(parent):
        groups.setdefault(find(token), []).append(token)
    name = {
        root: min(tokens, key=lambda t: (_PRIORITY.get(t.split(":", 1)[0], 9), t))
        for root, tokens in groups.items()
    }
    for s in spans:
        s.key = name[find((s.ids or (s.key,))[0])]


def _transition_id(t: Transition, fd: Fraction) -> tuple:
    return (t.name, t.out_key, round(t.out_src / fd))


def compare(old: Cut, new: Cut) -> Review:
    """Every change from *old* to *new*, ordered by where it plays in *new*."""
    fd = new.frame_duration
    tol = fd / 2
    unify_sources(old, new)

    def tc(t: Fraction, cut: Cut) -> str:
        return format_tc(t, cut.frame_duration, cut.tc_start)

    by_key: Dict[str, Tuple[List[Span], List[Span]]] = {}
    for s in old.spans:
        by_key.setdefault(s.key, ([], []))[0].append(s)
    for s in new.spans:
        by_key.setdefault(s.key, ([], []))[1].append(s)

    pairs: List[Tuple[Span, Span]] = []
    for olds, news in by_key.values():
        pairs.extend(_pair(olds, news, tol))
    partners_o: Dict[int, List[Span]] = {}
    partners_n: Dict[int, List[Span]] = {}
    for o, n in pairs:
        partners_o.setdefault(o.idx, []).append(n)
        partners_n.setdefault(n.idx, []).append(o)

    pieces: List[_Piece] = []
    for o, n in pairs:
        ov = _overlap((o.src_in, o.src_out), (n.src_in, n.src_out))
        if ov:
            pieces.append(_Piece(o, n, ov[0], ov[1]))

    changes: List[Change] = []

    def mapped(t: Fraction) -> Fraction:
        return _map(pieces, t, forward=True)

    def unmapped(t: Fraction) -> Fraction:
        return _map(pieces, t, forward=False)

    # Material that left the cut, or entered it.
    for o in old.spans:
        if o.idx not in partners_o:
            mid = o.tl_in + o.duration / 2
            changes.append(Change(
                kind="removed", name=o.name, lane=o.lane, old=o,
                detail=f"removed ({format_span(o.duration, fd)} at {tc(o.tl_in, old)})",
                old_tl=(o.tl_in, o.tl_out), src=[(o.key, o.src_in, o.src_out)],
                before_at=mid, after_at=mapped(o.tl_in),
            ))
    for n in new.spans:
        if n.idx not in partners_n:
            changes.append(Change(
                kind="added", name=n.name, lane=n.lane, new=n,
                detail=f"added ({format_span(n.duration, fd)} at {tc(n.tl_in, new)})",
                new_tl=(n.tl_in, n.tl_out), src=[(n.key, n.src_in, n.src_out)],
                before_at=unmapped(n.tl_in), after_at=n.tl_in + min(n.duration / 2, Fraction(1)),
            ))

    # Trims and retimes, one change per clip that kept some of its material.
    for o in old.spans:
        news = partners_o.get(o.idx, [])
        if not news:
            continue
        kept = [_overlap((o.src_in, o.src_out), (n.src_in, n.src_out)) for n in news]
        removed = _subtract((o.src_in, o.src_out), [k for k in kept if k], tol)
        single = len(news) == 1 and len(partners_n.get(news[0].idx, [])) == 1
        added: List[Interval] = []
        n0 = news[0]
        if single:
            added = _subtract((n0.src_in, n0.src_out), [(o.src_in, o.src_out)], tol)
        speed_changed = single and (o.speed or 1) != (n0.speed or 1)
        if not removed and not added and not speed_changed:
            continue
        words: List[str] = []
        src: List[Tuple[str, Fraction, Fraction]] = []
        old_ranges: List[Interval] = []
        new_ranges: List[Interval] = []
        before_at = after_at = None
        for lo, hi in removed:
            src.append((o.key, lo, hi))
            old_ranges.append((o.src_to_tl(lo), o.src_to_tl(hi)))
            length = format_span(o.src_to_tl(hi) - o.src_to_tl(lo), fd)
            if lo <= o.src_in + tol:
                words.append(f"start trimmed {length} later")
                before_at, after_at = o.tl_in, (n0.tl_in if single else mapped(o.tl_in))
            elif hi >= o.src_out - tol:
                words.append(f"end trimmed {length} shorter")
                before_at = o.tl_out - fd
                after_at = (n0.tl_out - fd) if single else mapped(o.src_to_tl(lo)) - fd
            else:
                at = o.src_to_tl(lo)
                words.append(f"{length} cut out at {tc(at, old)}")
                before_at = at + (o.src_to_tl(hi) - at) / 2
                after_at = mapped(at)
        for lo, hi in added:
            src.append((n0.key, lo, hi))
            new_ranges.append((n0.src_to_tl(lo), n0.src_to_tl(hi)))
            length = format_span(n0.src_to_tl(hi) - n0.src_to_tl(lo), fd)
            if hi <= o.src_in + tol:
                words.append(f"start extended {length} earlier")
                before_at, after_at = o.tl_in, n0.tl_in
            elif lo >= o.src_out - tol:
                words.append(f"end extended {length} longer")
                before_at, after_at = o.tl_out - fd, n0.tl_out - fd
            else:
                words.append(f"{length} put back in")
                before_at, after_at = unmapped(n0.src_to_tl(lo)), n0.src_to_tl(lo)
        kind = "trimmed"
        if speed_changed:
            kind = "retimed"
            words.insert(0, f"speed {_pct(o.speed)} to {_pct(n0.speed)}")
            src.append((o.key, min(o.src_in, n0.src_in), max(o.src_out, n0.src_out)))
            old_ranges.append((o.tl_in, o.tl_out))
            new_ranges.append((n0.tl_in, n0.tl_out))
            before_at = before_at if before_at is not None else o.tl_in + o.duration / 2
            after_at = after_at if after_at is not None else n0.tl_in + n0.duration / 2
        if single and not old_ranges:
            old_ranges.append((o.tl_out, o.tl_out) if added and added[0][0] >= o.src_out - tol else (o.tl_in, o.tl_in))
        if single and not new_ranges:
            new_ranges.append((n0.tl_out, n0.tl_out) if removed and removed[-1][1] >= o.src_out - tol else (n0.tl_in, n0.tl_in))
        changes.append(Change(
            kind=kind, name=o.name, lane=o.lane, old=o, new=n0 if single else None,
            detail="; ".join(words),
            old_tl=(min(r[0] for r in old_ranges), max(r[1] for r in old_ranges)) if old_ranges else None,
            new_tl=(min(r[0] for r in new_ranges), max(r[1] for r in new_ranges)) if new_ranges else None,
            src=src, before_at=before_at, after_at=after_at,
        ))

    # Order: spine material out of sequence, or connected material off its anchor.
    spine = [p for p in pieces if p.spine]
    keep = _weighted_lis(spine)
    moved: Dict[Tuple[int, int], List[_Piece]] = {}
    slid = 0
    for i, p in enumerate(spine):
        if i not in keep:
            moved.setdefault((p.o.idx, p.n.idx), []).append(p)
        elif abs(p.delta) > tol:
            slid += 1
    old_by_elem = {s.elem: s for s in old.spans}
    for p in pieces:
        if p.spine:
            continue
        # A connected clip is anchored to its host's source frame, so it should
        # move exactly as its host's material moved. Gap hosts do not ripple.
        host = old_by_elem.get(p.o.host) if p.o.host is not None else None
        host_pieces = [q for q in spine if host is not None and q.o is host]
        if host_pieces:
            q = min(host_pieces, key=lambda q: abs(q.old_tl[0] - p.old_tl[0]))
            expected = q.delta
        elif host is None and p.o.host is not None:
            expected = Fraction(0)
        else:
            expected = mapped(p.old_tl[0]) - p.old_tl[0]
        if p.o.lane != p.n.lane or abs(p.delta - expected) > tol:
            moved.setdefault((p.o.idx, p.n.idx), []).append(p)
        elif abs(p.delta) > tol:
            slid += 1
    for group in moved.values():
        o, n = group[0].o, group[0].n
        old_tl = (min(p.old_tl[0] for p in group), max(p.old_tl[1] for p in group))
        new_tl = (min(p.new_tl[0] for p in group), max(p.new_tl[1] for p in group))
        words = f"moved from {tc(old_tl[0], old)} to {tc(new_tl[0], new)}"
        if o.lane != n.lane:
            words += f", lane {o.lane} to {n.lane}"
        # A trim that also shifted what is left is one edit, not two.
        same = next((c for c in changes if c.kind in ("trimmed", "retimed") and c.old is o and c.new is n), None)
        if same is not None:
            same.detail += f"; what is left {words}"
            same.src.extend((o.key, p.a, p.b) for p in group)
            same.old_tl = (min(same.old_tl[0], old_tl[0]), max(same.old_tl[1], old_tl[1])) if same.old_tl else old_tl
            same.new_tl = (min(same.new_tl[0], new_tl[0]), max(same.new_tl[1], new_tl[1])) if same.new_tl else new_tl
            continue
        changes.append(Change(
            kind="moved", name=n.name, lane=n.lane, old=o, new=n, detail=words,
            old_tl=old_tl, new_tl=new_tl,
            src=[(o.key, p.a, p.b) for p in group],
            before_at=old_tl[0] + (old_tl[1] - old_tl[0]) / 2,
            after_at=new_tl[0] + (new_tl[1] - new_tl[0]) / 2,
        ))

    # How a kept clip looks or sounds.
    for o, n in pairs:
        if o.look != n.look or o.enabled != n.enabled:
            ov = _overlap((o.src_in, o.src_out), (n.src_in, n.src_out))
            changes.append(Change(
                kind="adjusted", name=n.name, lane=n.lane, old=o, new=n,
                detail=_look_detail(o, n) + " (frames below are source frames; effects are not drawn)",
                old_tl=(o.tl_in, o.tl_out), new_tl=(n.tl_in, n.tl_out),
                src=[(o.key, ov[0], ov[1])] if ov else [],
                before_at=o.tl_in + o.duration / 2, after_at=n.tl_in + n.duration / 2,
            ))

    # Transitions, identified by the material they follow, not by index.
    old_tr = {_transition_id(t, fd): t for t in old.transitions}
    new_tr = {_transition_id(t, fd): t for t in new.transitions}
    for k, t in old_tr.items():
        if k not in new_tr:
            changes.append(Change(
                kind="transition", name=t.name,
                detail=f"{t.name} removed ({format_span(t.tl_out - t.tl_in, fd)})",
                old_tl=(t.tl_in, t.tl_out), src=[(t.out_key, t.out_src - fd, t.out_src)],
                before_at=t.cut, after_at=mapped(t.cut),
            ))
    for k, t in new_tr.items():
        was = old_tr.get(k)
        if was is None:
            changes.append(Change(
                kind="transition", name=t.name,
                detail=f"{t.name} added ({format_span(t.tl_out - t.tl_in, fd)} at {tc(t.cut, new)})",
                new_tl=(t.tl_in, t.tl_out), src=[(t.out_key, t.out_src - fd, t.out_src)],
                before_at=unmapped(t.cut), after_at=t.cut,
            ))
        elif abs((was.tl_out - was.tl_in) - (t.tl_out - t.tl_in)) > tol:
            changes.append(Change(
                kind="transition", name=t.name,
                detail=(f"{t.name} length {format_span(was.tl_out - was.tl_in, fd)} "
                        f"to {format_span(t.tl_out - t.tl_in, fd)}"),
                old_tl=(was.tl_in, was.tl_out), new_tl=(t.tl_in, t.tl_out),
                src=[(t.out_key, t.out_src - fd, t.out_src)],
                before_at=was.cut, after_at=t.cut,
            ))

    # Format, through fcp-mcp-server's own comparison.
    fmt = fcp_diff.TimelineDiff(timeline_a_name=old.project, timeline_b_name=new.project)
    tl_a = FCPXMLParser().parse_file(old.path).primary_timeline
    tl_b = FCPXMLParser().parse_file(new.path).primary_timeline
    if tl_a is not None and tl_b is not None:
        fcp_diff._compare_format(tl_a, tl_b, fmt)
    for line in fmt.format_changes:
        changes.append(Change(kind="format", name="Project", detail=line))

    def where(c: Change) -> Fraction:
        if c.new_tl:
            return c.new_tl[0]
        if c.old_tl:
            return mapped(c.old_tl[0])
        return Fraction(-1)

    changes.sort(key=lambda c: (where(c), c.lane if c.lane is not None else 0))
    for i, c in enumerate(changes, 1):
        c.n = i

    return Review(
        old=old, new=new, changes=changes,
        marker_changes=_marker_changes(old, new, fd), slid=slid, pieces=pieces,
    )


def _marker_changes(old: Cut, new: Cut, fd: Fraction) -> List[MarkerChange]:
    def ident(m):
        return (m.value, m.span.key, round(m.src / fd))
    a = {ident(m): m for m in old.markers()}
    b = {ident(m): m for m in new.markers()}
    out: List[MarkerChange] = []
    for k, m in a.items():
        if k not in b:
            out.append(MarkerChange("removed", m.value, m.span.name, m.tl))
        elif m.completed != b[k].completed and b[k].completed == "1":
            out.append(MarkerChange("ticked", m.value, m.span.name, b[k].tl))
        elif m.completed != b[k].completed and m.completed == "1":
            out.append(MarkerChange("unticked", m.value, m.span.name, b[k].tl))
    for k, m in b.items():
        if k not in a:
            out.append(MarkerChange("added", m.value, m.span.name, m.tl))
    return sorted(out, key=lambda x: x.at)
