"""Timecode text in and out.

Everything inside cutreview is exact: seconds as ``Fraction``. Text only
exists at the edges, so the parsing and formatting live here and nowhere
else.
"""

from __future__ import annotations

import re
from fractions import Fraction
from typing import Optional

# One timecode token. Groups: up to four fields separated by ':' or ';'
# (the last field may carry a decimal fraction of a second instead).
_TC = r"\d{1,2}(?:[:;]\d{2}){1,3}(?:\.\d{1,3})?(?![\w.]|[:;]\d)"
TC_RE = re.compile(_TC)


class TimecodeError(ValueError):
    """A timecode that is shaped like one but cannot be read."""


def nominal(frame_duration: Fraction) -> int:
    """Frames per labelled second: 24 at 23.976, 30 at 29.97, 25 at 25."""
    return round(1 / frame_duration)


def parse_tc(text: str, frame_duration: Fraction) -> Fraction:
    """Read ``HH:MM:SS:FF``, ``HH:MM:SS``, ``MM:SS`` or ``MM:SS.mmm`` as seconds.

    Frames count at the timeline's nominal rate (non-drop): 24 per second at
    23.976, which is how Final Cut and Frame.io label them. Raises
    ``TimecodeError`` with a reason the page can print.
    """
    raw = text.strip()
    if not TC_RE.fullmatch(raw):
        raise TimecodeError(f"'{raw}' is not a timecode")
    decimal = Fraction(0)
    if "." in raw:
        raw, frac = raw.split(".", 1)
        decimal = Fraction(int(frac), 10 ** len(frac))
    parts = [int(p) for p in re.split(r"[:;]", raw)]
    fps = nominal(frame_duration)
    frames = 0
    if len(parts) == 4:
        if decimal:
            raise TimecodeError(f"'{text.strip()}' has both frames and a decimal")
        hh, mm, ss, ff = parts
        if ff >= fps:
            raise TimecodeError(f"frame {ff} in '{text.strip()}' is past {fps - 1} at {fps} fps")
        frames = ff
    elif len(parts) == 3:
        hh, mm, ss = parts
    else:
        hh, (mm, ss) = 0, parts
    if mm >= 60 or ss >= 60:
        raise TimecodeError(f"'{text.strip()}' has minutes or seconds past 59")
    total_frames = ((hh * 60 + mm) * 60 + ss) * fps + frames
    # A labelled second holds `fps` frames of real duration frame_duration.
    return total_frames * frame_duration + decimal * fps * frame_duration


def to_frames(seconds: Fraction, frame_duration: Fraction) -> int:
    return int(round(Fraction(seconds) / frame_duration))


def format_tc(seconds: Fraction, frame_duration: Fraction, base: Fraction = Fraction(0)) -> str:
    """``HH:MM:SS:FF`` for a position, counted from *base* (the sequence start)."""
    fps = nominal(frame_duration)
    total = to_frames(seconds, frame_duration) + to_frames(base, frame_duration)
    sign = "-" if total < 0 else ""
    total = abs(total)
    secs, ff = divmod(total, fps)
    hh, rem = divmod(secs, 3600)
    mm, ss = divmod(rem, 60)
    return f"{sign}{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"


def format_span(seconds: Fraction, frame_duration: Fraction) -> str:
    """A length in plain words: '12 frames', '2s', '1s 6f'."""
    frames = abs(to_frames(seconds, frame_duration))
    fps = nominal(frame_duration)
    if frames == 0:
        return "0 frames"
    if frames < fps:
        return f"{frames} frame{'s' if frames != 1 else ''}"
    secs, ff = divmod(frames, fps)
    if secs >= 60:
        mm, ss = divmod(secs, 60)
        return f"{mm}m {ss}s" + (f" {ff}f" if ff else "")
    return f"{secs}s" + (f" {ff}f" if ff else "")


def fcpxml_time(value: Fraction, timebase: Optional[int] = None) -> str:
    """Render an exact time as an FCPXML attribute ('12s', '86496/24000s').

    Uses the sequence timebase as the denominator when it represents the
    value exactly, which is the shape Final Cut writes; otherwise the
    reduced fraction, which is still exact.
    """
    value = Fraction(value)
    if value.denominator == 1:
        return f"{value.numerator}s"
    if timebase and (value * timebase).denominator == 1:
        return f"{int(value * timebase)}/{timebase}s"
    return f"{value.numerator}/{value.denominator}s"
