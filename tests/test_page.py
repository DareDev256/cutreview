"""The page: one file, nothing to load, everything escaped, red only for removals."""

import re
import subprocess
from pathlib import Path

import pytest

from conftest import HAS_FFMPEG

from cutreview import api
from cutreview.changes import compare
from cutreview.cut import load
from cutreview.frames import FrameGrabber
from cutreview.page import render_diff, render_status
from cutreview.status import status


def _external(html: str):
    refs = re.findall(r'(?:src|href)\s*=\s*"([^"]+)"', html)
    return [r for r in refs if not r.startswith(("#", "data:"))]


def test_pages_are_self_contained(music_round):
    r = compare(load(music_round.marked), load(music_round.next_export))
    for html in (render_diff(r), render_status(status(r))):
        assert _external(html) == []
        assert "<script" not in html and "<link" not in html and "@import" not in html
        assert "http://" not in html and "https://" not in html


def test_palette_black_cyan_and_the_light_mode(music_round):
    html = render_diff(compare(load(music_round.marked), load(music_round.next_export)))
    assert "--bg:#000" in html and "--accent:#00E5FF" in html
    assert "prefers-color-scheme:light" in html and "--bg:#fff" in html and "--accent:#007A8A" in html


def test_red_marks_only_removals(music_round):
    html = render_diff(compare(load(music_round.marked), load(music_round.next_export)))
    for cls in re.findall(r'class="change ([a-z]+)"', html):
        assert cls in ("removed", "added", "trimmed", "moved", "retimed", "adjusted", "transition", "format")
    pins = re.findall(r'class="pin( red)?"[^>]*>(\d+)<', html)
    removed = {m.group(1) for m in re.finditer(r'class="change removed" id="c(\d+)"', html)}
    assert {n for red, n in pins if red} <= removed


def test_note_text_is_escaped(work):
    (work / "n.txt").write_bytes(b'00:00:01:00 <script>alert("x")</script> & "quotes"\n')
    api.notes(str(work / "music-video.fcpxml"), str(work / "n.txt"), str(work / "m.fcpxml"))
    html = render_status(status(compare(load(work / "m.fcpxml"), load(work / "m.fcpxml"))))
    assert "<script>alert" not in html and "&lt;script&gt;alert" in html


def test_page_admits_its_age(music_round):
    r = compare(load(music_round.marked), load(music_round.next_export))
    html = render_diff(r)
    assert r.old.sha256 in html and r.new.sha256 in html
    assert "Exported" in html and "Made " in html


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")
def test_frames_come_from_reachable_media_and_offline_media_is_named(tmp_path, work):
    clip = tmp_path / "A.mp4"
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i",
                    "smptehdbars=s=320x180:r=24", "-t", "60", "-pix_fmt", "yuv420p", str(clip)], check=True)
    xml = (work / "music-video.fcpxml").read_text().replace("file:///Footage/A.mov", clip.as_uri())
    (work / "mv.fcpxml").write_text(xml)
    cut = load(work / "mv.fcpxml")
    grab = FrameGrabber(tmp_path / "cache")
    shot = grab.at(cut, cut.spans[1].tl_in + 1)          # SHOT A 1, reachable
    assert shot and shot["uri"].startswith("data:image/jpeg;base64,")
    assert grab.at(cut, cut.spans[2].tl_in + 1) is None  # SHOT B 1, offline
    assert any("B.mov" in v for v in grab.offline.values())


def test_every_html_file_written_by_the_cli_is_one_file(music_round, tmp_path):
    res = api.diff(str(music_round.marked), str(music_round.next_export), str(tmp_path / "r.html"))
    html = Path(res.outputs[0]).read_text()
    assert _external(html) == []
