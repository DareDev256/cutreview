from fractions import Fraction

from conftest import FIXTURES

from cutreview.cut import load


def test_gap_based_cut_reads_every_connected_clip():
    cut = load(FIXTURES / "music-video.fcpxml")
    by = {s.name: s for s in cut.spans}
    assert len(cut.spans) == 8
    assert by["SHOT B 1"].lane == 1 and by["SHOT B 1"].tl_in == 4
    assert by["OVERLAY 2"].tl_in == Fraction(13, 2)          # 3606500/1000s on a gap at 3600s
    assert by["TRACK"].lane == -1 and not by["TRACK"].has_video
    assert cut.origin == 3600 and cut.tc_start == 0


def test_picture_is_the_highest_lane_at_or_above_the_spine():
    cut = load(FIXTURES / "music-video.fcpxml")
    assert cut.picture_at(Fraction(3)).name == "OVERLAY 1"
    assert cut.picture_at(Fraction(1)).name == "SHOT A 1"
    assert cut.picture_at(Fraction(30)) is None              # only the music bed plays there


def test_spine_cut_and_its_sources():
    cut = load(FIXTURES / "sample.fcpxml")
    first = cut.spans[0]
    assert (first.name, first.tl_in, first.tl_out, first.src_in, first.src_out) == ("Interview_A", 0, 3, 10, 13)
    assert cut.frame_duration == Fraction(1, 24)


def test_retimed_clip_plays_the_source_its_timemap_says(tmp_path):
    xml = (FIXTURES / "music-video.fcpxml").read_text()
    xml = xml.replace(
        '<asset-clip ref="a3" lane="1" name="DRONE 1"\n                          offset="3612s" start="0s" duration="4s"/>',
        '<asset-clip ref="a3" lane="1" name="DRONE 1" offset="3612s" start="0s" duration="8s">'
        '<timeMap><timept time="0s" value="0s" interp="linear"/><timept time="8s" value="4s" interp="linear"/></timeMap>'
        '</asset-clip>',
    )
    p = tmp_path / "retimed.fcpxml"
    p.write_text(xml)
    drone = next(s for s in load(p).spans if s.name == "DRONE 1")
    assert (drone.src_in, drone.src_out, drone.speed) == (0, 4, Fraction(1, 2))
    assert drone.tl_to_src(Fraction(16)) == 2
