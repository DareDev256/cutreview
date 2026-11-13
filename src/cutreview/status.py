"""Where each note stands in the next export.

Two independent readings per note:

* **done / open** is the editor's own tick: the ``completed`` attribute of
  the note's marker in the next export, which is what Final Cut writes when
  the to-do checkbox is ticked. cutreview never sets it.
* **touched / untouched** is computed: did anything in the cut change under
  the note? "Under" means the note's frames widened by *reach* on each side
  (default one second), on the earlier cut's timeline where the note was
  written, or on the later cut's timeline where its marker now sits. A
  change below the primary storyline (audio lanes) touches only notes that
  sit on audio. A clip that only slid with a ripple is not a change, so it
  touches nothing.

"Touched" is never "addressed". A trim near a note touches it whether or not
it is what the reviewer asked for. The page leads with the two places the
readings disagree, because those are the ones worth a look.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import List, Optional

from .changes import Change, Review
from .cut import Cut, MarkerRec
from .markers import ID_RE


@dataclass
class NoteStatus:
    marker: MarkerRec                         # in the marked (earlier) cut
    after: Optional[MarkerRec]                # the same marker in the next export
    presence: str                             # present | removed-with-clip | frames-cut | marker-deleted
    done: Optional[bool]                      # None when the marker is gone
    touched: bool
    by: List[Change] = field(default_factory=list)

    @property
    def id(self) -> Optional[int]:
        m = ID_RE.match(self.marker.value)
        return int(m.group(1)) if m else None

    @property
    def text(self) -> str:
        m = ID_RE.match(self.marker.value)
        return self.marker.value[m.end():].strip() if m else self.marker.value

    @property
    def disagreement(self) -> Optional[str]:
        if self.presence != "present":
            return None
        if self.done and not self.touched:
            return "ticked-untouched"
        if self.done is False and self.touched:
            return "changed-unticked"
        return None

    @property
    def state_words(self) -> str:
        if self.presence == "removed-with-clip":
            return "removed with its clip"
        if self.presence == "frames-cut":
            return "its frames were cut"
        if self.presence == "marker-deleted":
            return "marker deleted in the next export"
        return ("done" if self.done else "open") + ", " + ("touched" if self.touched else "untouched")


@dataclass
class StatusReport:
    review: Review
    notes: List[NoteStatus]
    reach: Fraction
    new_todos: List[MarkerRec]

    def bucket(self, name: str) -> List[NoteStatus]:
        return [n for n in self.notes if n.disagreement == name]


def _ident(m: MarkerRec, fd: Fraction) -> tuple:
    return (m.value, m.span.key, round(m.src / fd))


def _find_after(m: MarkerRec, new: Cut, fd: Fraction) -> Optional[MarkerRec]:
    idm = ID_RE.match(m.value)
    if idm:
        for cand in new.markers():
            c = ID_RE.match(cand.value)
            if c and c.group(1) == idm.group(1) and cand.span.key == m.span.key:
                return cand
    want = _ident(m, fd)
    for cand in new.markers():
        if cand.completed is not None and abs(round(cand.src / fd) - want[2]) <= 1 \
                and cand.value == m.value and cand.span.key == m.span.key:
            return cand
    return None


def _hits(c: Change, old_lo: Fraction, old_hi: Fraction, new_win: Optional[tuple], on_picture: bool) -> bool:
    # Only on the same side of the storyline: moving the music bed does not
    # touch a note about the picture.
    if on_picture and c.lane is not None and c.lane < 0:
        return False
    if c.old_tl and c.old_tl[0] <= old_hi and c.old_tl[1] >= old_lo:
        return True
    if new_win and c.new_tl and c.new_tl[0] <= new_win[1] and c.new_tl[1] >= new_win[0]:
        return True
    return False


def status(review: Review, reach: Fraction = Fraction(1)) -> StatusReport:
    old, new = review.old, review.new
    fd = old.frame_duration
    notes: List[NoteStatus] = []
    for m in old.markers():
        if not m.is_todo:
            continue
        after = _find_after(m, new, fd)
        span = m.span
        # The note's frames, widened by reach, on the timeline of each cut.
        old_lo, old_hi = m.tl - reach, m.tl + m.duration + reach
        new_win = (after.tl - reach, after.tl + after.duration + reach) if after else None
        by = [c for c in review.changes
              if c.kind != "format"
              and _hits(c, old_lo, old_hi, new_win, span.lane >= 0 and span.has_video)]
        if after is not None:
            # Final Cut keeps a marker on its clip when a trim hides its frame;
            # the marker is still in the file but nothing under it plays.
            hidden = not (after.span.tl_in <= after.tl < after.span.tl_out)
            presence = "frames-cut" if hidden else "present"
        else:
            same_source = [s for s in new.spans if s.key == span.key
                           and s.src_in < span.src_out and s.src_out > span.src_in]
            if not same_source:
                presence = "removed-with-clip"
            elif not any(s.src_in <= m.src < s.src_out for s in same_source):
                presence = "frames-cut"
            else:
                presence = "marker-deleted"
        done = None if after is None else after.completed == "1"
        notes.append(NoteStatus(
            marker=m, after=after, presence=presence, done=done,
            touched=bool(by) or presence in ("removed-with-clip", "frames-cut"), by=by,
        ))
    notes.sort(key=lambda n: (n.id if n.id is not None else 10 ** 9, n.marker.tl))
    old_ids = {_ident(m, fd) for m in old.markers()}
    seen_ids = {ID_RE.match(m.value).group(1) for m in old.markers() if ID_RE.match(m.value)}
    new_todos = [
        m for m in new.markers()
        if m.is_todo and _ident(m, fd) not in old_ids
        and not (ID_RE.match(m.value) and ID_RE.match(m.value).group(1) in seen_ids)
    ]
    return StatusReport(review=review, notes=notes, reach=reach, new_todos=new_todos)
