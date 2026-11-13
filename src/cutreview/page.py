"""The review page: one self-contained HTML file. No CDN, no fetch, no script.

Ground is true black with one cyan accent (#00E5FF); with the system set to
light it is white with #007A8A. Red only marks material that left the cut.
Every label is HTML text, never drawn into an image.
"""

from __future__ import annotations

import html
import time
from fractions import Fraction
from typing import Iterable, List, Optional

from . import __version__
from .changes import Change, Review
from .cut import Cut
from .frames import FrameGrabber
from .timecode import format_tc

KIND_WORDS = {
    "removed": "Removed", "added": "Added", "trimmed": "Trimmed", "moved": "Moved",
    "retimed": "Retimed", "adjusted": "Adjusted", "transition": "Transition", "format": "Format",
}
KIND_ORDER = ["trimmed", "removed", "added", "moved", "retimed", "adjusted", "transition", "format"]
PIN_GAP = 7.5      # percent of the strip between pins: about 26px at 390px wide

CSS = """
:root{--bg:#000;--fg:#f4f4f4;--muted:#9b9b9b;--faint:#5e5e5e;--line:#232323;--card:#0a0a0a;
--block:#262626;--block-spine:#3a3a3a;--accent:#00E5FF;--accent-ink:#000;--accent-fill:rgba(0,229,255,.22);
--red:#FF4D4D;--red-fill:rgba(255,77,77,.24);--mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace;
color-scheme:dark}
@media (prefers-color-scheme:light){:root{--bg:#fff;--fg:#0b0b0b;--muted:#555;--faint:#8a8a8a;--line:#e2e2e2;
--card:#fff;--block:#e6e6e6;--block-spine:#cfcfcf;--accent:#007A8A;--accent-ink:#fff;--accent-fill:rgba(0,122,138,.16);
--red:#C8102E;--red-fill:rgba(200,16,46,.14);color-scheme:light}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1100px;margin:0 auto;padding:32px 24px 64px}
h1,h2,h3,p{margin:0}
.eyebrow{font:600 12px/1 var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--accent)}
header{display:grid;gap:14px;padding-bottom:24px;border-bottom:1px solid var(--line)}
h1{font-size:22px;font-weight:600;letter-spacing:-.01em;display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
h1 .big{font-size:64px;line-height:.9;font-weight:700;letter-spacing:-.03em}
.files{color:var(--muted);overflow-wrap:anywhere}
.files b{color:var(--fg);font-weight:600}
.chips{display:flex;flex-wrap:wrap;gap:8px;list-style:none;margin:0;padding:0}
.chips li{display:inline-flex;align-items:center;gap:8px;border:1px solid var(--line);border-radius:999px;padding:4px 12px 4px 10px;font-size:14px}
.chips i{width:8px;height:8px;border-radius:50%;background:var(--accent);display:inline-block}
.chips li.red i{background:var(--red)}
.chips li.none i{background:var(--faint)}
.quiet{color:var(--muted);font-size:14px}
section{padding:28px 0;border-bottom:1px solid var(--line)}
h2{font-size:13px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin-bottom:16px}
h2 .n{color:var(--fg)}
.strip{display:grid;gap:6px}
.lane-row{display:grid;grid-template-columns:56px 1fr;gap:12px;align-items:end}
.lane-row .lbl{font-size:12px;color:var(--muted);padding-bottom:2px}
.rail{position:relative}
.pin{position:absolute;transform:translateX(-50%);width:22px;height:22px;border-radius:50%;background:var(--accent);
color:var(--accent-ink);font:700 11px/22px var(--mono);text-align:center;text-decoration:none}
.pin.red{background:var(--red);color:#fff}
.track{position:relative;background:transparent;border-left:1px solid var(--line);border-right:1px solid var(--line)}
.blk{position:absolute;height:9px;background:var(--block);border-radius:2px;box-shadow:inset -2px 0 0 var(--bg)}
.blk.spine{background:var(--block-spine)}
.blk.audio{height:6px;margin-top:2px;opacity:.75}
.hl{position:absolute;top:-3px;bottom:-3px;background:var(--accent-fill);border-left:2px solid var(--accent);border-right:2px solid var(--accent);min-width:2px}
.hl.red{background:var(--red-fill);border-color:var(--red)}
.scale{display:grid;grid-template-columns:56px 1fr;gap:12px;font:12px var(--mono);color:var(--faint)}
.scale div{display:flex;justify-content:space-between}
.legend{display:flex;flex-wrap:wrap;gap:16px;font-size:13px;color:var(--muted);margin-top:10px}
.legend span{display:inline-flex;align-items:center;gap:6px}
.legend i{display:inline-block;width:14px;height:10px;background:var(--accent-fill);border:2px solid var(--accent);border-width:0 2px}
.legend i.red{background:var(--red-fill);border-color:var(--red)}
.list{display:grid;gap:12px}
.change{border:1px solid var(--line);border-radius:10px;padding:16px;background:var(--card);display:grid;gap:10px;scroll-margin-top:16px}
.change .head{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px}
.change .num{width:26px;height:26px;border-radius:50%;background:var(--accent);color:var(--accent-ink);font:700 12px/26px var(--mono);text-align:center;flex:none}
.change.removed .num{background:var(--red);color:#fff}
.kind{font:600 12px/1 var(--mono);text-transform:uppercase;letter-spacing:.08em;color:var(--accent)}
.change.removed .kind{color:var(--red)}
.clip{font-weight:600;overflow-wrap:anywhere}
.tc{font-family:var(--mono);font-size:13px;color:var(--muted);margin-left:auto}
.detail{font-size:16px}
.by{font-size:13px;color:var(--muted);overflow-wrap:anywhere}
.by b{color:var(--fg);font-weight:600;font-family:var(--mono);font-size:12px}
.frames{display:grid;grid-template-columns:repeat(2,minmax(0,340px));gap:12px}
.frames figure{margin:0;display:grid;gap:6px}
.frames img{width:100%;height:auto;display:block;border-radius:6px;border:1px solid var(--line)}
.frames figcaption{font-size:12px;color:var(--muted);display:grid;grid-template-columns:auto 1fr;gap:2px 8px}
.frames figcaption em{grid-column:1/-1;overflow-wrap:anywhere}
.frames figcaption b{color:var(--fg);font-weight:600}
.frames figcaption span{font-family:var(--mono);text-align:right}
.offline{font-size:13px;color:var(--faint)}
.age{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}
.age div{display:grid;gap:4px;font-size:13px;color:var(--muted)}
.age b{color:var(--fg);font-weight:600;overflow-wrap:anywhere}
.hash{font:12px var(--mono);word-break:break-all;color:var(--muted)}
footer{padding-top:24px;font-size:13px;color:var(--faint);display:grid;gap:6px}
.dis{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.box{border:1px solid var(--line);border-radius:10px;padding:16px;display:grid;gap:12px;align-content:start}
.box.hot{border-color:var(--accent)}
.box h3{display:flex;align-items:baseline;gap:10px;font-size:16px;font-weight:600}
.box h3 .big{font-size:40px;line-height:1;font-weight:700;letter-spacing:-.02em}
.box p.why{font-size:13px;color:var(--muted)}
.note{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;padding:12px 0;border-top:1px solid var(--line)}
.note:first-of-type{border-top:0}
.note .id{font:700 13px var(--mono);color:var(--accent);padding-top:1px}
.note .body{display:grid;gap:6px;min-width:0}
.note .txt{overflow-wrap:anywhere}
.note .meta{display:flex;flex-wrap:wrap;gap:6px 10px;align-items:center;font-size:13px;color:var(--muted)}
.note .meta .tc{margin-left:0}
.tag{font:600 11px/1 var(--mono);text-transform:uppercase;letter-spacing:.06em;border:1px solid var(--line);border-radius:4px;padding:4px 6px;color:var(--muted)}
.tag.on{border-color:var(--accent);color:var(--accent)}
.tag.red{border-color:var(--red);color:var(--red)}
.note .frames{grid-column:2;margin-top:4px}
.raw{font:13px var(--mono);overflow-wrap:anywhere;color:var(--fg)}
a{color:var(--accent)}
@media (max-width:640px){main{padding:20px 16px 48px}.frames{grid-template-columns:1fr 1fr}h1 .big{font-size:48px}.dis{grid-template-columns:1fr}
.lane-row,.scale{grid-template-columns:44px 1fr;gap:8px}.change{padding:14px}.tc{margin-left:0;width:100%}}
"""


def e(x) -> str:
    return html.escape(str(x), quote=True)


def _pct(t: Fraction, total: Fraction) -> float:
    return max(0.0, min(100.0, float(t) / float(total) * 100)) if total else 0.0


def _doc(title: str, body: str) -> str:
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<meta name=\"generator\" content=\"cutreview {e(__version__)}\">"
        f"<title>{e(title)}</title><style>{CSS}</style></head><body><main>{body}</main></body></html>"
    )


def _chips(counts: dict) -> str:
    items = []
    for k in KIND_ORDER:
        if counts.get(k):
            cls = " class=\"red\"" if k == "removed" else ""
            items.append(f"<li{cls}><i></i>{counts[k]} {e(KIND_WORDS[k].lower())}</li>")
    return "<ul class=\"chips\">" + "".join(items) + "</ul>" if items else ""


def _stack_pins(items: List[tuple]) -> List[tuple]:
    """Give each (pct, n, red) pin a row so no two pins in a row are closer than PIN_GAP."""
    rows: List[float] = []
    placed = []
    for pct, n, red in sorted(items):
        for r, last in enumerate(rows):
            if pct - last >= PIN_GAP:
                rows[r] = pct
                placed.append((pct, n, red, r))
                break
        else:
            rows.append(pct)
            placed.append((pct, n, red, len(rows) - 1))
    return placed


def _rail(pins: List[tuple]) -> str:
    placed = _stack_pins(pins)
    rows = max((p[3] for p in placed), default=-1) + 1
    h = rows * 26
    out = [f"<div class=\"rail\" style=\"height:{h}px\">"]
    for pct, n, red, row in placed:
        cls = "pin red" if red else "pin"
        out.append(
            f"<a class=\"{cls}\" href=\"#c{n}\" style=\"left:{pct:.3f}%;bottom:{row * 26}px\" "
            f"aria-label=\"change {n}\">{n}</a>"
        )
    out.append("</div>")
    return "".join(out)


def _track(cut: Cut, lanes: List[int], total: Fraction, hls: List[tuple]) -> str:
    row_h = 12
    height = len(lanes) * row_h
    out = [f"<div class=\"track\" style=\"height:{height}px\">"]
    for s in cut.spans:
        if s.lane not in lanes:
            continue
        top = lanes.index(s.lane) * row_h + 2
        cls = "blk spine" if s.lane == 0 else ("blk audio" if s.lane < 0 else "blk")
        out.append(
            f"<div class=\"{cls}\" title=\"{e(s.name)}\" style=\"left:{_pct(s.tl_in, total):.3f}%;"
            f"width:{max(0.15, _pct(s.tl_out, total) - _pct(s.tl_in, total)):.3f}%;top:{top}px\"></div>"
        )
    for lo, hi, red in hls:
        cls = "hl red" if red else "hl"
        out.append(
            f"<div class=\"{cls}\" style=\"left:{_pct(lo, total):.3f}%;width:{max(0.0, _pct(hi, total) - _pct(lo, total)):.3f}%\"></div>"
        )
    out.append("</div>")
    return "".join(out)


def _strip(review: Review) -> str:
    old, new = review.old, review.new
    total = max(old.duration, new.duration)
    lanes = sorted({s.lane for s in old.spans} | {s.lane for s in new.spans}, reverse=True)
    if not lanes:
        return ""
    before_hl, after_hl, before_pins, after_pins = [], [], [], []
    for c in review.changes:
        red = c.kind == "removed" or (c.kind == "trimmed" and c.new_tl is not None and c.new_tl[0] == c.new_tl[1])
        if c.old_tl:
            before_hl.append((c.old_tl[0], c.old_tl[1], red or c.kind == "removed"))
        if c.new_tl:
            after_hl.append((c.new_tl[0], c.new_tl[1], False))
            after_pins.append((_pct(c.new_tl[0], total), c.n, False))
        elif c.old_tl:
            before_pins.append((_pct(c.old_tl[0], total), c.n, c.kind == "removed"))
    end_tc = format_tc(total, new.frame_duration, new.tc_start)
    start_tc = format_tc(Fraction(0), new.frame_duration, new.tc_start)
    return (
        "<section class=\"strip\" aria-label=\"timeline\"><h2>Where</h2>"
        f"<div class=\"lane-row\"><span></span>{_rail(before_pins)}</div>"
        f"<div class=\"lane-row\"><span class=\"lbl\">Before</span>{_track(old, lanes, total, before_hl)}</div>"
        f"<div class=\"lane-row\"><span></span>{_rail(after_pins)}</div>"
        f"<div class=\"lane-row\"><span class=\"lbl\">After</span>{_track(new, lanes, total, after_hl)}</div>"
        f"<div class=\"scale\"><span></span><div><span>{e(start_tc)}</span><span>{e(end_tc)}</span></div></div>"
        "<div class=\"legend\"><span><i></i>changed</span><span><i class=\"red\"></i>left the cut</span>"
        "<span>Rows are lanes: connected clips above the primary storyline, audio below.</span></div>"
        "</section>"
    )


def _figure(label: str, cut: Cut, t: Optional[Fraction], shot: Optional[dict]) -> str:
    if shot is None or t is None:
        return ""
    return (
        f"<figure><img src=\"{shot['uri']}\" alt=\"{e(label)} frame of {e(shot['clip'])}\" loading=\"lazy\">"
        f"<figcaption><b>{e(label)}</b><span>{e(format_tc(t, cut.frame_duration, cut.tc_start))}</span>"
        f"<em>{e(shot['clip'])}</em></figcaption></figure>"
    )


def _frames(review: Review, c: Change, grabber: Optional[FrameGrabber]) -> str:
    if grabber is None or not grabber.enabled:
        return ""
    b = grabber.at(review.old, c.before_at) if c.before_at is not None else None
    a = grabber.at(review.new, c.after_at) if c.after_at is not None else None
    if not b and not a:
        return ""
    return "<div class=\"frames\">" + _figure("Before", review.old, c.before_at, b) + _figure("After", review.new, c.after_at, a) + "</div>"


def _blame_line(c: Change) -> str:
    b = c.blame
    if not b:
        return ""
    if b.get("kind") in ("journal", "journal+hand", "group"):
        args = f" ({e(b['args'])})" if b.get("args") else ""
        when = f" at {e(b['when'])}" if b.get("when") else ""
        extra = " Also changed after the last journaled write." if b.get("kind") == "journal+hand" else ""
        group = f" {e(b['why'])}." if b.get("kind") == "group" else ""
        return f"<p class=\"by\">By <b>{e(b['by'])}</b>{args}{when}.{group}{extra}</p>"
    if b.get("kind") == "hand":
        return "<p class=\"by\">Not in the journal: made by hand in Final Cut, or by a tool that keeps no journal.</p>"
    return ""


def _change_card(review: Review, c: Change, grabber: Optional[FrameGrabber]) -> str:
    cut = review.new if c.new_tl else review.old
    at = c.new_tl[0] if c.new_tl else (c.old_tl[0] if c.old_tl else None)
    tc = f"<span class=\"tc\">{e(format_tc(at, cut.frame_duration, cut.tc_start))}</span>" if at is not None else ""
    lane = "" if c.lane in (None, 0) else f" <span class=\"quiet\">lane {c.lane}</span>"
    return (
        f"<article class=\"change {e(c.kind)}\" id=\"c{c.n}\"><div class=\"head\">"
        f"<span class=\"num\">{c.n}</span><span class=\"kind\">{e(KIND_WORDS.get(c.kind, c.kind))}</span>"
        f"<span class=\"clip\">{e(c.name)}</span>{lane}{tc}</div>"
        f"<p class=\"detail\">{e(c.detail)}</p>{_blame_line(c)}{_frames(review, c, grabber)}</article>"
    )


def _changes_section(review: Review, grabber: Optional[FrameGrabber], title: str = "Changes") -> str:
    if not review.changes:
        return f"<section><h2>{e(title)}</h2><p class=\"quiet\">No changes to the cut.</p></section>"
    cards = "".join(_change_card(review, c, grabber) for c in review.changes)
    off = ""
    if grabber is not None and grabber.offline:
        where = "; ".join(sorted(grabber.offline.values())[:6])
        off = f"<p class=\"offline\">No frames for media that is offline: {e(where)}</p>"
    elif grabber is None or not grabber.enabled:
        off = "<p class=\"offline\">Frames not drawn (ffmpeg not found, or turned off).</p>"
    return (
        f"<section class=\"list\"><h2>{e(title)} <span class=\"n\">{len(review.changes)}</span></h2>"
        f"{cards}{off}</section>"
    )


def _markers_section(review: Review) -> str:
    if not review.marker_changes:
        return ""
    rows = "".join(
        f"<div class=\"note\"><span class=\"id\">{e(m.kind)}</span><div class=\"body\"><span class=\"txt\">{e(m.value)}</span>"
        f"<span class=\"meta\"><span>{e(m.clip)}</span><span class=\"tc\">{e(format_tc(m.at, review.new.frame_duration, review.new.tc_start))}</span></span></div></div>"
        for m in review.marker_changes
    )
    return f"<section><h2>Markers <span class=\"n\">{len(review.marker_changes)}</span></h2>{rows}</section>"


def _age(cuts: Iterable[tuple], extra: str = "") -> str:
    parts = []
    for label, cut in cuts:
        parts.append(
            f"<div><span>{e(label)}</span><b>{e(cut.name)}</b>"
            f"<span>Exported {e(cut.exported)} (from {e(cut.exported_source)})</span>"
            f"<span class=\"hash\">sha256 {e(cut.sha256)}</span></div>"
        )
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    parts.append(f"<div><span>This page</span><b>Made {e(now)}</b><span>cutreview {e(__version__)}</span>{extra}</div>")
    return "<section class=\"age\" aria-label=\"files\">" + "".join(parts) + "</section>"


FOOT = (
    "<footer><p>Cut Review reads two Final Cut exports and shows what changed between them. "
    "Nothing was uploaded; this page is one file with nothing to load.</p>"
    "<p>Frames are source frames under each instant: effects, titles and grades are not drawn.</p></footer>"
)


def render_diff(review: Review, grabber: Optional[FrameGrabber] = None, blame=None) -> str:
    n = len(review.changes)
    head = (
        "<header><span class=\"eyebrow\">Cut Review" + (" &middot; blame" if blame is not None else "") + "</span>"
        f"<h1><span class=\"big\">{n}</span> change{'s' if n != 1 else ''}</h1>"
        f"<p class=\"files\"><b>{e(review.old.name)}</b> to <b>{e(review.new.name)}</b></p>"
        f"{_chips(review.counts())}"
        + (f"<p class=\"quiet\">{review.slid} clip{'s' if review.slid != 1 else ''} only slid with the ripple and "
           f"{'are' if review.slid != 1 else 'is'} not listed.</p>" if review.slid else "")
        + "</header>"
    )
    blame_note = ""
    if blame is not None:
        found = len(blame.journals)
        lines = [f"{found} journal file{'s' if found != 1 else ''} read, {len(blame.steps)} journaled write{'s' if len(blame.steps) != 1 else ''} on the path from the old file"]
        if blame.unexplained:
            lines.append(f"{blame.unexplained} change{'s' if blame.unexplained != 1 else ''} not in the journal")
        blame_note = "<section><h2>Journal</h2><p>" + e("; ".join(lines)) + ".</p>" + "".join(
            f"<p class=\"quiet\">{e(x)}</p>" for x in blame.notes) + "</section>"
    body = (
        head + _strip(review) + blame_note + _changes_section(review, grabber)
        + _markers_section(review) + _age([("Before", review.old), ("After", review.new)]) + FOOT
    )
    return _doc(f"Cut Review: {review.new.name}", body)


def _note_row(rep, ns, grabber: Optional[FrameGrabber], with_frames: bool) -> str:
    review = rep.review
    fd = review.old.frame_duration
    m = ns.marker
    tc = format_tc(m.tl, fd, review.old.tc_start)
    tags = []
    if ns.presence == "present":
        tags.append(f"<span class=\"tag{' on' if ns.done else ''}\">{'Done' if ns.done else 'Open'}</span>")
        tags.append(f"<span class=\"tag{' on' if ns.touched else ''}\">{'Touched' if ns.touched else 'Untouched'}</span>")
    elif ns.presence == "removed-with-clip":
        tags.append("<span class=\"tag red\">Removed with its clip</span>")
    elif ns.presence == "frames-cut":
        tags.append("<span class=\"tag red\">Its frames were cut</span>")
        if ns.done is not None:
            tags.append(f"<span class=\"tag{' on' if ns.done else ''}\">{'Done' if ns.done else 'Open'}</span>")
    else:
        tags.append("<span class=\"tag\">Marker deleted</span>")
        tags.append(f"<span class=\"tag{' on' if ns.touched else ''}\">{'Touched' if ns.touched else 'Untouched'}</span>")
    by = ""
    if ns.by:
        links = ", ".join(f"<a href=\"#c{c.n}\">{c.n}</a>" for c in ns.by[:8])
        by = f"<span>by change {links}</span>"
    frames = ""
    if with_frames and grabber is not None and grabber.enabled:
        b = grabber.at(review.old, m.tl)
        after_t = ns.after.tl if ns.after is not None else review.map_old_to_new(m.tl)
        a = grabber.at(review.new, after_t)
        if b or a:
            frames = ("<div class=\"frames\">" + _figure("Before", review.old, m.tl, b)
                      + _figure("After", review.new, after_t, a) + "</div>")
    ident = f"#{ns.id}" if ns.id is not None else "&bull;"
    return (
        f"<div class=\"note\"><span class=\"id\">{ident}</span><div class=\"body\">"
        f"<span class=\"txt\">{e(ns.text)}</span>"
        f"<span class=\"meta\"><span class=\"tc\">{e(tc)}</span><span>{e(m.span.name)}</span>{''.join(tags)}{by}</span>"
        f"</div>{frames}</div>"
    )


def render_status(rep, ledger: Optional[dict] = None, grabber: Optional[FrameGrabber] = None) -> str:
    notes = rep.notes
    ticked_untouched = rep.bucket("ticked-untouched")
    changed_unticked = rep.bucket("changed-unticked")
    present = [n for n in notes if n.presence == "present"]
    done = sum(1 for n in present if n.done)
    touched = sum(1 for n in notes if n.touched and n.presence == "present")
    gone = sum(1 for n in notes if n.presence == "removed-with-clip")
    cut_frames = sum(1 for n in notes if n.presence == "frames-cut")
    deleted = sum(1 for n in notes if n.presence == "marker-deleted")
    chips = [f"<li><i></i>{done} done</li>", f"<li class=\"none\"><i></i>{len(present) - done} open</li>",
             f"<li><i></i>{touched} touched</li>", f"<li class=\"none\"><i></i>{len(present) - touched} untouched</li>"]
    if gone:
        chips.append(f"<li class=\"red\"><i></i>{gone} removed with its clip</li>")
    if cut_frames:
        chips.append(f"<li class=\"red\"><i></i>{cut_frames} with frames cut</li>")
    if deleted:
        chips.append(f"<li class=\"none\"><i></i>{deleted} marker{'s' if deleted != 1 else ''} deleted</li>")
    n = len(notes)
    reach = float(rep.reach)
    head = (
        "<header><span class=\"eyebrow\">Cut Review &middot; notes</span>"
        f"<h1><span class=\"big\">{n}</span> note{'s' if n != 1 else ''}</h1>"
        f"<p class=\"files\">Notes in <b>{e(rep.review.old.name)}</b>, checked against <b>{e(rep.review.new.name)}</b></p>"
        f"<ul class=\"chips\">{''.join(chips)}</ul>"
        f"<p class=\"quiet\">Done or open is the editor's tick in Final Cut. Touched means the cut changed within "
        f"{reach:g}s of the note; it does not mean the note was dealt with.</p></header>"
    )

    def box(title, items, why, hot):
        rows = "".join(_note_row(rep, x, grabber, True) for x in items) or "<p class=\"quiet\">None.</p>"
        return (f"<div class=\"box{' hot' if hot and items else ''}\"><h3><span class=\"big\">{len(items)}</span>{e(title)}</h3>"
                f"<p class=\"why\">{e(why)}</p>{rows}</div>")

    dis = (
        "<section><h2>Where the tick and the cut disagree</h2><div class=\"dis\">"
        + box("Ticked but untouched", ticked_untouched,
              "Marked done in Final Cut, but nothing in the cut changed near it.", True)
        + box("Changed but not ticked", changed_unticked,
              "The cut changed near it, but its to-do is still open.", True)
        + "</div></section>"
    )
    rows = "".join(_note_row(rep, x, grabber, False) for x in notes) or "<p class=\"quiet\">No to-do markers in the earlier file.</p>"
    all_notes = f"<section><h2>Every note <span class=\"n\">{n}</span></h2>{rows}</section>"

    extra = ""
    if ledger:
        unplaced = ledger.get("unplaced") or []
        unreadable = ledger.get("unreadable") or []
        if unplaced:
            items = "".join(
                f"<div class=\"note\"><span class=\"id\">&bull;</span><div class=\"body\"><span class=\"txt\">{e(u.get('text', ''))}</span>"
                f"<span class=\"meta\"><span>{e(u.get('origin', ''))}</span><span>{e((u.get('placed') or {}).get('reason', 'no timecode'))}</span></span></div></div>"
                for u in unplaced)
            extra += f"<section><h2>Not placed <span class=\"n\">{len(unplaced)}</span></h2><p class=\"quiet\">These notes have no time cutreview could use, so no marker was written. They were not guessed.</p>{items}</section>"
        if unreadable:
            items = "".join(
                f"<div class=\"note\"><span class=\"id\">&bull;</span><div class=\"body\"><span class=\"raw\">{e(u.get('text', ''))}</span>"
                f"<span class=\"meta\"><span>{e(u.get('origin', ''))}</span><span>{e(u.get('reason', ''))}</span></span></div></div>"
                for u in unreadable)
            extra += f"<section><h2>Unreadable <span class=\"n\">{len(unreadable)}</span></h2><p class=\"quiet\">Lines cutreview could not read, exactly as they were written.</p>{items}</section>"
    if rep.new_todos:
        items = "".join(
            f"<div class=\"note\"><span class=\"id\">new</span><div class=\"body\"><span class=\"txt\">{e(m.value)}</span>"
            f"<span class=\"meta\"><span class=\"tc\">{e(format_tc(m.tl, rep.review.new.frame_duration, rep.review.new.tc_start))}</span><span>{e(m.span.name)}</span></span></div></div>"
            for m in rep.new_todos)
        extra += f"<section><h2>New to-dos in the later file <span class=\"n\">{len(rep.new_todos)}</span></h2>{items}</section>"

    body = (
        head + dis + _strip(rep.review) + all_notes + extra
        + _changes_section(rep.review, grabber, "What changed")
        + _age([("Notes written into", rep.review.old), ("Checked against", rep.review.new)]) + FOOT
    )
    return _doc(f"Cut Review notes: {rep.review.new.name}", body)
