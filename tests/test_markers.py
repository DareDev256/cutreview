"""Writing to-do markers: on the right clip, valid, and read back by a second instrument."""

import re
from fractions import Fraction
from pathlib import Path

import pytest

from conftest import needs_dtd

from cutreview import api, markers
from cutreview.cut import load
from cutreview.markers import WriteRefused, next_id, place, write_markers
from cutreview.notes import parse_text, resolve_times


def _notes(cut, text: bytes):
    ns = parse_text(text, "n.txt", cut.frame_duration)
    resolve_times(ns, cut.tc_start, cut.duration)
    return ns


def test_notes_land_on_the_picture_clip_in_its_source_time(work):
    cut = load(work / "music-video.fcpxml")
    ns = _notes(cut, b"00:00:03:00 overlay note\n00:00:00:12 shot note\n00:00:30:00 music only\n")
    pl = place(cut, ns)
    assert [(p.span.name, p.on_audio) for p in pl] == [("OVERLAY 1", False), ("SHOT A 1", False), ("TRACK", True)]
    # OVERLAY 1 starts at 2s on the timeline and 20s in its source: 3s is 21s local.
    assert pl[0].local == 20 + (72 * cut.frame_duration - 2)


def test_a_note_over_nothing_is_unplaced_not_moved(work):
    cut = load(work / "music-video.fcpxml")
    for s in cut.spans:
        if s.name == "TRACK":
            s.enabled = False
    ns = _notes(cut, b"00:00:30:00 here\n")
    assert place(cut, ns) == []
    assert ns.unplaced[0].placed["reason"].startswith("no clip under 00:00:30:00")


@needs_dtd
def test_written_file_is_valid_1_13_and_reads_back(work):
    res = api.notes(str(work / "music-video.fcpxml"), str(Path(__file__).parent.parent / "fixtures" / "music-video.notes.txt"),
                    str(work / "marked.fcpxml"))
    assert res.data["dtd"] == "valid"
    text = (work / "marked.fcpxml").read_text()
    assert '<fcpxml version="1.13">' in text
    assert text.count('completed="0"') == 6
    cut = load(work / "marked.fcpxml")
    todo = [m for m in cut.markers() if m.is_todo]
    assert {m.value.split()[0] for m in todo} == {f"#{i}" for i in range(1, 7)}
    assert all("\n" not in m.note for m in todo)


@needs_dtd
def test_an_input_already_invalid_is_kept_only_if_no_new_error(work):
    (work / "n.txt").write_bytes(b"00:00:01:00 note\n")
    res = api.notes(str(work / "sample.fcpxml"), str(work / "n.txt"), str(work / "s.fcpxml"))
    assert res.data["dtd"] == "input-invalid"
    assert "cutreview added none" in res.summary


def test_ids_continue_after_existing_ones(work):
    (work / "n.txt").write_bytes(b"00:00:01:00 first\n")
    api.notes(str(work / "music-video.fcpxml"), str(work / "n.txt"), str(work / "a.fcpxml"))
    assert next_id(load(work / "a.fcpxml")) == 2
    (work / "m.txt").write_bytes(b"00:00:02:00 second\n")
    api.notes(str(work / "a.fcpxml"), str(work / "m.txt"), str(work / "b.fcpxml"))
    values = sorted(m.value for m in load(work / "b.fcpxml").markers())
    assert values == ["#1 first", "#2 second"]


def test_readback_refuses_a_marker_on_the_wrong_frame(work, monkeypatch):
    """Guard: shift every written marker a second late; the parser must catch it."""
    real = markers.fcpxml_time

    def late(value, timebase=None):
        return real(Fraction(value) + 1, timebase)

    monkeypatch.setattr(markers, "fcpxml_time", late)
    cut = load(work / "music-video.fcpxml")
    ns = _notes(cut, b"00:00:05:00 B note\n")
    with pytest.raises(WriteRefused, match="placement check failed"):
        write_markers(cut, place(cut, ns), work / "out.fcpxml")
    assert not (work / "out.fcpxml").exists()


@needs_dtd
def test_dtd_refuses_a_new_error_and_leaves_nothing(work, monkeypatch):
    """Guard: write an attribute Apple's DTD does not declare."""
    real = markers.build_marker_element

    def bad(**kw):
        el = real(**kw)
        el.set("colour", "red")
        return el

    monkeypatch.setattr(markers, "build_marker_element", bad)
    cut = load(work / "music-video.fcpxml")
    ns = _notes(cut, b"00:00:05:00 B note\n")
    with pytest.raises(WriteRefused, match="would not validate"):
        write_markers(cut, place(cut, ns), work / "out.fcpxml")
    assert not (work / "out.fcpxml").exists()
    assert not [p for p in work.iterdir() if re.match(r"\.cutreview-", p.name)]
