"""A real Final Cut Pro 12.4 round trip, kept byte for byte.

tests/fixtures/fcp-12.4-roundtrip/ holds the file cutreview wrote
(maya_v1_notes.fcpxml, six to-do markers) and what Final Cut exported after
the editor ticked #1 and #3 and trimmed the end of Street Wide by two
seconds (maya_fcp.fcpxmld, FCPXML 1.14, run 2026-11-12, docs/final-cut-proof.md).

Final Cut renumbers resource ids (a2 becomes r2), adds uid and sig, drops
start="0s" on clips, drops format on asset-clips and reorders attributes.
None of that is a change to the cut. v0.1.0 as first committed read this
pair as 16 changes and every note as "removed with its clip".
"""

import hashlib
from pathlib import Path

from cutreview import api
from cutreview.changes import compare
from cutreview.cut import load
from cutreview.status import status

HERE = Path(__file__).parent / "fixtures" / "fcp-12.4-roundtrip"
MARKED = HERE / "maya_v1_notes.fcpxml"
EXPORT = HERE / "maya_fcp.fcpxmld"
SHA = {
    MARKED: "30802ee3649d1afa9a02fe3827f7e902a9a0d98c439d8abc383eb08b9bb2fd20",
    EXPORT / "Info.fcpxml": "4259c091981a84aaa985ee5557d0f8ea960f4ed563c33e680d8d2a9c805d87ff",
}


def test_the_fixture_is_untouched():
    for path, digest in SHA.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, f"{path.name} was edited"


def test_final_cut_kept_the_markers_the_tick_and_the_notes():
    xml = (EXPORT / "Info.fcpxml").read_text()
    assert xml.count("<marker ") == 6
    assert xml.count('completed="1"') == 2
    assert xml.count(' note="') == 6
    assert '<fcpxml version="1.14">' in xml


def test_diff_is_exactly_one_trim(tmp_path):
    review = compare(load(MARKED), load(EXPORT))
    assert [(c.kind, c.name, c.detail) for c in review.changes] == [
        ("trimmed", "Street Wide", "end trimmed 2s shorter"),
    ]
    assert review.slid == 5
    res = api.diff(str(MARKED), str(EXPORT), str(tmp_path / "review.html"), frames=False)
    assert "Street Wide: end trimmed 2s shorter" in res.summary
    assert "5 clips only slid with the ripple (not listed)" in res.summary
    assert "1 change (1 trimmed)" in res.summary


def test_status_reads_the_editors_ticks_exactly():
    rep = status(compare(load(MARKED), load(EXPORT)))
    assert {f"#{n.id}": n.state_words for n in rep.notes} == {
        "#1": "done, untouched",
        "#2": "open, touched",
        "#3": "done, untouched",
        "#4": "open, untouched",
        "#5": "open, untouched",
        "#6": "open, untouched",
    }
    assert [n.id for n in rep.bucket("ticked-untouched")] == [1, 3]
    assert [n.id for n in rep.bucket("changed-unticked")] == [2]
    assert all(n.presence == "present" for n in rep.notes)


def test_a_missing_start_reads_as_zero():
    street = next(s for s in load(EXPORT).spans if s.name == "Street Wide")
    assert street.elem.get("start") is None
    assert (street.src_in, street.src_out) == (0, 2)


def test_a_relinked_file_still_matches_through_its_uid(tmp_path):
    """The same export with every media file moved: Final Cut's uid ties them together."""
    text = (EXPORT / "Info.fcpxml").read_text()
    moved = text.replace("file:///Users/", "file:///Volumes/Archive/")
    assert moved != text
    bundle = tmp_path / "relinked.fcpxmld"
    bundle.mkdir()
    (bundle / "Info.fcpxml").write_text(moved)
    assert compare(load(EXPORT), load(bundle)).changes == []
