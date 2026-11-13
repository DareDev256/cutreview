"""Blame: each change to the fcp-mcp-server write that made it, or 'not in the journal'."""

import os
import shutil

from cutreview.blame import blame, chain, journal_candidates
from cutreview.changes import compare
from cutreview.cut import load


def _by(review):
    return {(c.kind, c.name): c.blame for c in review.changes}


def test_music_video_round(music_round):
    r = compare(load(music_round.marked), load(music_round.next_export))
    found = blame(r)
    by = _by(r)
    assert len(found.steps) == 3 and not found.reached
    assert by[("trimmed", "SHOT B 1")]["by"] == "edit.trim_clip"
    assert "trim_start=+1s" in by[("trimmed", "SHOT B 1")]["args"]
    assert "trim_end=-1s" in by[("trimmed", "OVERLAY 3")]["args"]
    assert by[("retimed", "DRONE 1")]["by"] == "edit.change_speed"
    assert by[("removed", "OVERLAY 1")]["kind"] == "hand"
    assert found.unexplained == 1


def test_sample_round(sample_round):
    r = compare(load(sample_round.marked), load(sample_round.next_export))
    blame(r)
    by = _by(r)
    assert by[("removed", "Broll_Studio")]["by"] == "edit.delete_clips"
    assert by[("transition", "Cross Dissolve")]["by"] == "edit.add_transition"
    # Trimmed, then moved: the last write that changed it is the reorder.
    assert by[("trimmed", "Broll_City")]["by"] in ("edit.trim_clip", "edit.reorder_clips")


def test_no_journal_says_so(work, monkeypatch):
    monkeypatch.setenv("FCP_MCP_JOURNAL", str(work / "nowhere"))
    monkeypatch.setenv("HOME", str(work))
    r = compare(load(work / "sample.fcpxml"), load(work / "sample.fcpxml"))
    found = blame(r)
    assert found.journals == [] and "No fcp-mcp-server journal found" in found.notes[0]


def test_a_missing_middle_file_names_the_steps_as_a_group(music_round, tmp_path):
    folder = tmp_path / "copy"
    shutil.copytree(music_round.folder, folder)
    # The journal records absolute paths; point it at this copy, then lose step 2's file.
    j = next((folder / "journal").glob("*.jsonl"))
    j.write_text(j.read_text().replace(str(music_round.folder), str(folder)))
    os.remove(folder / "music-video_notes_agent2.fcpxml")
    r = compare(load(folder / "music-video_notes.fcpxml"), load(folder / "music-video_v2.fcpxml"))
    blame(r, journal=str(folder / "journal"))
    by = _by(r)
    assert by[("trimmed", "OVERLAY 3")]["kind"] == "group"
    assert "edit.trim_clip" in by[("trimmed", "OVERLAY 3")]["by"] and "edit.change_speed" in by[("trimmed", "OVERLAY 3")]["by"]


def test_chain_follows_hashes_and_ignores_undo():
    rows = [
        {"action": "a", "input": {"sha256": "h0"}, "output": {"sha256": "h1"}, "ts": 1},
        {"action": "b", "input": {"sha256": "h1"}, "output": {"sha256": "h2"}, "ts": 2},
        {"action": "c", "input": {"sha256": "h0"}, "output": {"sha256": "hx"}, "ts": 3},
    ]
    path, reached = chain(rows, "h0", "h2")
    assert reached and [r["action"] for r in path] == ["a", "b"]
    path, reached = chain(rows, "h0", "nope")
    assert not reached and len(path) == 2


def test_journal_found_in_the_project_folder(music_round):
    assert any("journal" in str(p) for p in journal_candidates(str(music_round.marked)))


def test_journal_then_hand_on_the_same_material(music_round, tmp_path):
    """The agent trimmed OVERLAY 3 by a second; the editor trims it again in Final Cut."""
    from fcpxml.writer import FCPXMLModifier

    mod = FCPXMLModifier(str(music_round.next_export))
    for el in mod.root.iter("asset-clip"):
        if el.get("name") == "OVERLAY 3":
            el.set("duration", "12012/24000s")
    out = music_round.folder / "music-video_v3.fcpxml"
    mod.save(str(out))
    r = compare(load(music_round.marked), load(out))
    blame(r)
    b = _by(r)[("trimmed", "OVERLAY 3")]
    assert b["kind"] == "journal+hand" and b["by"] == "edit.trim_clip"
