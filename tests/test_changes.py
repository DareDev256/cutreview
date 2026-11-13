"""The change model, on edits made by fcp-mcp-server itself."""

from fractions import Fraction

import scenarios

from fcpxml import diff as fcp_diff

from cutreview.changes import compare
from cutreview.cut import load


def edit(work, src, out, **args):
    scenarios._env(work / "journal")
    scenarios.fcp_call("edit", dict(args, filepath=str(work / src), output_path=str(work / out)))
    return work / out


def kinds(review):
    return [(c.kind, c.name) for c in review.changes]


def test_identical_cuts_have_no_changes(work):
    cut = load(work / "sample.fcpxml")
    assert compare(cut, cut).changes == []


def test_a_ripple_trim_is_one_change_and_the_rest_only_slid(work):
    out = edit(work, "sample.fcpxml", "t.fcpxml", action="trim_clip", clip_id="Broll_Studio", trim_end="-12f")
    r = compare(load(work / "sample.fcpxml"), load(out))
    assert kinds(r) == [("trimmed", "Broll_Studio")]
    assert "end trimmed 12 frames shorter" in r.changes[0].detail
    assert r.slid >= 1


def test_a_head_trim_reads_as_a_trim_not_a_swap(work):
    out = edit(work, "music-video.fcpxml", "h.fcpxml", action="trim_clip", clip_id="SHOT B 1",
               trim_start="+1s", ripple=False)
    r = compare(load(work / "music-video.fcpxml"), load(out))
    assert kinds(r) == [("trimmed", "SHOT B 1")]
    assert r.changes[0].detail.startswith("start trimmed 1s later")


def test_a_blade_alone_changes_nothing_anyone_can_see(work):
    out = edit(work, "sample.fcpxml", "b.fcpxml", action="split_clip", clip_id="Interview_A",
               split_points=["00:00:02:00"])
    assert compare(load(work / "sample.fcpxml"), load(out)).changes == []


def test_a_reorder_is_one_move(work):
    out = edit(work, "sample.fcpxml", "r.fcpxml", action="reorder_clips", clip_ids=["Broll_Studio"],
               target_position="start")
    r = compare(load(work / "sample.fcpxml"), load(out))
    assert kinds(r) == [("moved", "Broll_Studio")]


def test_delete_with_ripple_is_one_removal(work):
    out = edit(work, "sample.fcpxml", "d.fcpxml", action="delete_clips", clip_ids=["Broll_Studio"])
    r = compare(load(work / "sample.fcpxml"), load(out))
    assert kinds(r) == [("removed", "Broll_Studio")]
    assert r.changes[0].old_tl == (9, Fraction(37, 4))


def test_speed_change_is_a_retime(work):
    out = edit(work, "music-video.fcpxml", "s.fcpxml", action="change_speed", clip_id="DRONE 1", speed=0.5)
    r = compare(load(work / "music-video.fcpxml"), load(out))
    assert kinds(r) == [("retimed", "DRONE 1")]
    assert "speed 100% to 50%" in r.changes[0].detail


def test_transition_added(work):
    out = edit(work, "sample.fcpxml", "x.fcpxml", action="add_transition", clip_id="Broll_Studio", position="end")
    r = compare(load(work / "sample.fcpxml"), load(out))
    assert [c.kind for c in r.changes] == ["transition"]


def test_why_not_diff_py(work):
    """fcp-mcp-server's diff.compare_timelines, on the same edits, reads them wrong.

    This is the measured reason cutreview matches on source material
    instead of (name, source in-point). If a future fcp-mcp-server fixes
    these, this test fails and the decision should be revisited.
    """
    base = work / "music-video.fcpxml"
    trimmed = edit(work, "music-video.fcpxml", "m.fcpxml", action="trim_clip", clip_id="OVERLAY 3",
                   trim_end="-1s", ripple=False)
    # 1. Gap-based cut: diff.py walks the spine only and sees no clip change.
    old_view = fcp_diff.compare_timelines(str(base), str(trimmed))
    assert [d for d in old_view.clip_diffs if d.action != "unchanged"] == []
    assert kinds(compare(load(base), load(trimmed))) == [("trimmed", "OVERLAY 3")]

    # 2. A head trim moves the in-point, so diff.py reports a removal and an addition.
    head = edit(work, "sample.fcpxml", "hh.fcpxml", action="trim_clip", clip_id="Broll_Studio", trim_start="+12f")
    actions = sorted(d.action for d in fcp_diff.compare_timelines(str(work / "sample.fcpxml"), str(head)).clip_diffs)
    assert "removed" in actions and "added" in actions

    # 3. A ripple trim: every later clip reads as moved.
    rip = edit(work, "sample.fcpxml", "rr.fcpxml", action="trim_clip", clip_id="Broll_Studio", trim_end="-12f")
    moved = [d for d in fcp_diff.compare_timelines(str(work / "sample.fcpxml"), str(rip)).clip_diffs if d.action == "moved"]
    assert len(moved) >= 1
    assert all(c.kind != "moved" for c in compare(load(work / "sample.fcpxml"), load(rip)).changes)


def test_a_connected_clip_riding_a_rippled_host_only_slid(work):
    """Spine A then B with C connected to B; trim A: C moves with B and is no change."""
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.13"><resources>
<format id="r1" name="FFVideoFormat1080p24" frameDuration="1/24s" width="1920" height="1080"/>
<asset id="a1" name="A" start="0s" duration="60s" hasVideo="1" format="r1"><media-rep kind="original-media" src="file:///m/A.mov"/></asset>
<asset id="a2" name="B" start="0s" duration="60s" hasVideo="1" format="r1"><media-rep kind="original-media" src="file:///m/B.mov"/></asset>
<asset id="a3" name="C" start="0s" duration="60s" hasVideo="1" format="r1"><media-rep kind="original-media" src="file:///m/C.mov"/></asset>
</resources><library><event name="e"><project name="p"><sequence format="r1" duration="8s" tcStart="3600s">
<spine><asset-clip ref="a1" name="A" offset="3600s" start="10s" duration="4s"/>
<asset-clip ref="a2" name="B" offset="3604s" start="20s" duration="4s"><asset-clip ref="a3" lane="1" name="C" offset="21s" start="5s" duration="2s"/></asset-clip>
</spine></sequence></project></event></library></fcpxml>
"""
    (work / "abc.fcpxml").write_text(xml)
    out = edit(work, "abc.fcpxml", "abc2.fcpxml", action="trim_clip", clip_id="A", trim_end="-1s")
    r = compare(load(work / "abc.fcpxml"), load(out))
    assert kinds(r) == [("trimmed", "A")]
    assert r.slid == 2


def test_an_audio_lane_change_does_not_touch_a_picture_note(music_round, tmp_path):
    from fcpxml.writer import FCPXMLModifier

    from cutreview.status import status

    mod = FCPXMLModifier(str(music_round.marked))
    for el in mod.root.iter("asset-clip"):
        if el.get("name") == "TRACK":
            el.set("offset", "3601s")                 # the music bed slips a second late
    out = tmp_path / "track.fcpxml"
    mod.save(str(out))
    r = compare(load(music_round.marked), load(out))
    assert kinds(r) == [("moved", "TRACK")]
    rep = status(r)
    got = {n.id: n.touched for n in rep.notes}
    assert got[1] is False and got[6] is True        # #6 sits on the music bed itself
