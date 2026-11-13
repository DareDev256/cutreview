from fractions import Fraction

import pytest

from cutreview.timecode import TimecodeError, fcpxml_time, format_span, format_tc, parse_tc

F24 = Fraction(1, 24)
F2398 = Fraction(1001, 24000)


@pytest.mark.parametrize("text,seconds", [
    ("00:00:01:12", Fraction(3, 2)),
    ("01:00:00:00", Fraction(3600)),
    ("00:01:23", Fraction(83)),
    ("1:23", Fraction(83)),
    ("01:23.5", Fraction(167, 2)),
    ("00:00:10;12", Fraction(21, 2)),
])
def test_parse_at_24(text, seconds):
    assert parse_tc(text, F24) == seconds


def test_labels_count_frames_at_23976():
    # 10 labelled seconds at 23.976 are 240 frames, which last 10.01 real seconds.
    assert parse_tc("00:00:10:00", F2398) == 240 * F2398
    assert format_tc(240 * F2398, F2398) == "00:00:10:00"


@pytest.mark.parametrize("bad,why", [
    ("00:00:01:24", "past 23"),
    ("00:61:00", "past 59"),
    ("12", "not a timecode"),
    ("00:00:01:02.5", "both frames and a decimal"),
])
def test_unreadable_timecodes_say_why(bad, why):
    with pytest.raises(TimecodeError, match=why):
        parse_tc(bad, F24)


def test_format_counts_from_the_sequence_start():
    assert format_tc(Fraction(3, 2), F24, Fraction(3600)) == "01:00:01:12"


def test_spans_in_plain_words():
    assert format_span(Fraction(1, 2), F24) == "12 frames"
    assert format_span(Fraction(1, 24), F24) == "1 frame"
    assert format_span(Fraction(25, 4), F24) == "6s 6f"


def test_fcpxml_time_uses_the_sequence_timebase():
    assert fcpxml_time(Fraction(12)) == "12s"
    assert fcpxml_time(36 * F2398, 24000) == "36036/24000s"
    assert fcpxml_time(Fraction(1, 3), 24) == "8/24s"
