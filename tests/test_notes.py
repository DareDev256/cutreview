"""Notes in: unplaced is listed, unreadable is listed, nothing is dropped."""

from fractions import Fraction

import pytest

from conftest import FIXTURES

from cutreview.notes import (
    NotesFileError, looks_like_frameio, parse_csv, parse_text, read_notes, resolve_times,
)

F24 = Fraction(1, 24)


def test_every_non_blank_line_is_accounted_for():
    data = (FIXTURES / "music-video.notes.txt").read_bytes()
    ns = parse_text(data, "n.txt", F24)
    lines = [ln for ln in data.decode().splitlines() if ln.strip()]
    continuation = [ln for ln in lines if ln[:1] in (" ", "\t")]
    assert len(ns.notes) + len(ns.unplaced) + len(ns.unreadable) + len(continuation) == len(lines)


def test_text_forms_and_continuations():
    ns = parse_text(
        b"00:00:05:00 - 00:00:06:00 Too long\n\tkeep the gesture\n[1:02] bracketed\n@ 00:00:03:00: at sign\n",
        "n.txt", F24)
    assert [n.text for n in ns.notes] == ["Too long\nkeep the gesture", "bracketed", "at sign"]
    assert ns.notes[0].until == 6 and ns.notes[1].at == 62


def test_no_timecode_is_unplaced_never_given_a_time():
    ns = parse_text(b"Overall the grade is great\n", "n.txt", F24)
    assert ns.notes == [] and ns.unplaced[0].at is None


def test_unreadable_lines_are_listed_with_the_reason_and_the_original_text():
    ns = parse_text(b"00:01:75:00 Check sync\n00:00:13:00\n12:3x broken\n00:00:09:00 - 00:00:08:00 backwards\n", "n.txt", F24)
    reasons = {r.text: r.reason for r in ns.unreadable}
    assert "past 59" in reasons["00:01:75:00 Check sync"]
    assert reasons["00:00:13:00"] == "a timecode with no note after it"
    assert reasons["12:3x broken"] == "starts like a timecode but is not one"
    assert reasons["00:00:09:00 - 00:00:08:00 backwards"] == "the range ends before it starts"


def test_bytes_that_are_not_utf8_are_listed_not_dropped():
    ns = parse_text(b"00:00:01:00 fine\n00:00:02:00 caf\xe9\n", "n.txt", F24)
    assert len(ns.notes) == 1
    assert ns.unreadable[0].origin == "n.txt line 2" and "not UTF-8" in ns.unreadable[0].reason


def test_generic_csv_by_header_name():
    ns = parse_csv(b"Reviewer,Time,Note\nAna,12.5,Lift the mids\nBo,,General thought\n", "c.csv", F24)
    assert ns.notes[0].at == Fraction(25, 2) and ns.notes[0].author == "Ana"
    assert ns.unplaced[0].text == "General thought"


def test_csv_without_a_note_column_refuses_and_names_the_headers():
    with pytest.raises(NotesFileError, match="no note column"):
        parse_csv(b"Time,Who\n00:00:01:00,Ana\n", "c.csv", F24)


def test_frameio_export():
    data = (FIXTURES / "sample.frameio.csv").read_bytes()
    assert looks_like_frameio(data.decode().splitlines()[0].split(","))
    ns = read_notes(FIXTURES / "sample.frameio.csv", F24)
    assert ns.format == "frameio"
    assert [n.text.splitlines()[0] for n in ns.notes] == [
        "Love this take, keep it", "City shot runs long, trim it", "Is that a flash frame?",
        "Ending feels abrupt", "Logo needs to be bigger",
    ]
    abrupt = ns.notes[3]
    assert "Reply from Dana: Agreed, a dissolve would help" in abrupt.text
    assert ns.notes[4].complete and "(has a drawing in Frame.io)" in ns.notes[4].text
    assert [n.text for n in ns.unplaced] == ["Music is a touch loud overall"]
    assert ns.unreadable[0].reason == "'00:00:6O:00' is not a timecode"


def test_frameio_columns_in_another_order_still_read():
    ns = parse_csv(b"Timecode,Comment,Commenter\n00:00:02:00,Lift it,Ana\n", "f.csv", F24, frameio=True)
    assert ns.notes[0].at == 2 and ns.notes[0].author == "Ana"


def test_frameio_source_timecode_columns_on_request():
    ns = read_notes(FIXTURES / "sample.frameio.csv", F24, use_source_tc=True)
    assert ns.notes[0].tc_in == "01:00:01:00"


def test_hour_start_review_copy_is_read_once_for_the_whole_file():
    ns = parse_text(b"01:00:01:00 a\n01:00:02:00 b\n", "n.txt", F24)
    resolve_times(ns, Fraction(0), Fraction(60))
    assert [n.at for n in ns.notes] == [1, 2] and "01:00:00:00" in ns.time_base


def test_hour_rule_needs_every_note_past_the_hour():
    ns = parse_text(b"01:00:01:00 a\n00:00:02:00 b\n", "n.txt", F24)
    resolve_times(ns, Fraction(0), Fraction(3000))
    assert [n.at for n in ns.notes] == [2]
    assert [n.text for n in ns.unplaced] == ["a"] and "01:00:00:00" not in ns.time_base


def test_notes_past_the_end_move_to_unplaced_with_the_reason():
    ns = parse_text(b"00:00:30:00 late\n", "n.txt", F24)
    resolve_times(ns, Fraction(0), Fraction(10))
    assert ns.notes == [] and ns.unplaced[0].placed == {"reason": "after the end of the cut"}


def test_sequence_start_timecode_is_subtracted():
    ns = parse_text(b"01:00:05:00 a\n", "n.txt", F24)
    resolve_times(ns, Fraction(3600), Fraction(60))
    assert ns.notes[0].at == 5
