"""Done or open (the editor's tick) against touched or untouched (the cut)."""

from fractions import Fraction

import pytest
import scenarios

from cutreview.changes import compare
from cutreview.cut import load
from cutreview.status import status


def states(rnd, reach=Fraction(1)):
    rep = status(compare(load(rnd.marked), load(rnd.next_export)), reach)
    return rep, {f"#{n.id}": n.state_words for n in rep.notes}


def test_music_video_round(music_round):
    rep, got = states(music_round)
    assert got == {
        "#1": "done, untouched",            # ticked, nothing changed near it
        "#2": "done, touched",              # head of SHOT B 1 trimmed by the agent
        "#3": "removed with its clip",      # OVERLAY 1 deleted by hand
        "#4": "open, touched",              # OVERLAY 3 trimmed, never ticked
        "#5": "done, touched",              # DRONE 1 slowed down
        "#6": "open, untouched",
    }
    assert [n.id for n in rep.bucket("ticked-untouched")] == [1]
    assert [n.id for n in rep.bucket("changed-unticked")] == [4]


def test_sample_round_catches_the_agent_trimming_the_wrong_clip(sample_round):
    rep, got = states(sample_round)
    # The note is on the first Broll_City; fcp-mcp-server's name lookup trimmed
    # the last one. The editor ticked it anyway: ticked but untouched.
    assert got["#2"] == "done, untouched"
    assert got["#3"] == "removed with its clip"
    assert got["#4"] == "open, touched"
    assert got["#5"] == "done, untouched"       # complete in Frame.io, nothing changed
    assert {n.id for n in rep.bucket("ticked-untouched")} == {2, 5}


def test_mutation_remove_one_change_and_its_note_flips_to_untouched(tmp_path):
    """The spec's mutation: build the round without the OVERLAY 3 trim."""
    without = scenarios.music_video(tmp_path / "m", skip={"trim the end of OVERLAY 3 by a second"})
    _, got = states(without)
    assert got["#4"] == "open, untouched"
    assert got["#2"] == "done, touched" and got["#5"] == "done, touched"


def test_mutation_keep_the_clip_and_the_note_is_back(tmp_path):
    without = scenarios.music_video(tmp_path / "m", skip={"delete OVERLAY 1 by hand"})
    _, got = states(without)
    assert got["#3"] == "open, untouched"


def test_reach_widens_what_counts_as_under(music_round):
    _, narrow = states(music_round, Fraction(0))
    _, wide = states(music_round, Fraction(4))
    assert narrow["#4"] == "open, untouched"   # the trim is 0.5s past the note
    assert wide["#1"] == "done, touched"       # OVERLAY 1's removal starts 1.5s after #1


def test_a_ripple_never_touches_a_note(tmp_path):
    """A trim early in the cut slides every later note: none of them is touched."""
    rnd = scenarios.sample(tmp_path / "s", skip={
        "delete the 6-frame Broll_Studio flash", "move Broll_Studio to the end",
        "move Broll_City to the end", "dissolve out of Interview_A", "trim Broll_City by 12 frames"})
    scenarios._env(tmp_path / "s" / "journal")
    out = tmp_path / "s" / "rippled.fcpxml"
    scenarios.fcp_call("edit", {"action": "trim_clip", "filepath": str(rnd.marked), "output_path": str(out),
                                "clip_id": "Broll_Studio", "trim_end": "-12f"})
    rep = status(compare(load(rnd.marked), load(out)))
    later = {f"#{n.id}": n.touched for n in rep.notes if n.marker.tl > 15}
    assert later and not any(later.values())


def test_a_marker_hidden_by_a_trim_reads_as_frames_cut(music_round, tmp_path):
    from fcpxml.writer import FCPXMLModifier

    mod = FCPXMLModifier(str(music_round.marked))
    for el in mod.root.iter("asset-clip"):
        if el.get("name") == "SHOT A 1":
            el.set("duration", "12012/24000s")       # half a second: #1 at 0.5s is now past the end
    out = tmp_path / "hidden.fcpxml"
    mod.save(str(out))
    rep = status(compare(load(music_round.marked), load(out)))
    one = next(n for n in rep.notes if n.id == 1)
    assert one.presence == "frames-cut" and one.touched


@pytest.mark.parametrize("bucket", ["ticked-untouched", "changed-unticked"])
def test_disagreements_only_count_notes_still_present(music_round, bucket):
    rep, _ = states(music_round)
    assert all(n.presence == "present" for n in rep.bucket(bucket))


def test_a_removal_next_to_a_note_touches_it_from_the_earlier_cut(music_round, tmp_path):
    """OVERLAY 1 (2s to 4s) is deleted; #1 at 0.5s with a 2s reach is touched only in the earlier cut."""
    out = tmp_path / "no-overlay.fcpxml"
    scenarios._hand_edit(music_round.marked, out, lambda root: scenarios._delete_connected(root, "OVERLAY 1"))
    rep = status(compare(load(music_round.marked), load(out)), Fraction(2))
    one = next(n for n in rep.notes if n.id == 1)
    assert one.touched and [c.kind for c in one.by] == ["removed"]
