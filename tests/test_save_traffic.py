"""scripts/save_traffic.py keeps GitHub's 14-day traffic forever, and refuses a reply it cannot read."""

import json

import pytest

import save_traffic


def reply(*days):
    return {"count": 0, "uniques": 0, "views": [{"timestamp": f"{d}T00:00:00Z", "count": c, "uniques": u} for d, c, u in days]}


def test_a_later_read_replaces_the_same_day_and_keeps_the_old_ones():
    saved = {"2026-10-01": {"count": 5, "uniques": 2}, "2026-11-11": {"count": 3, "uniques": 1}}
    merged = save_traffic.merge_days(saved, reply(("2026-11-11", 40, 9), ("2026-11-12", 7, 4)), "views")
    assert merged["2026-10-01"] == {"count": 5, "uniques": 2}  # older than GitHub's window, still kept
    assert merged["2026-11-11"] == {"count": 40, "uniques": 9}  # the partial day is replaced by the full one
    assert list(merged) == sorted(merged)


@pytest.mark.parametrize("bad", [{}, {"views": "nope"}, {"views": [{"timestamp": "2026-11-12T00:00:00Z", "count": 1}]}, []])
def test_a_reply_without_its_days_is_refused(bad):
    with pytest.raises(ValueError):
        save_traffic.merge_days({}, bad, "views")


def test_nothing_is_written_when_one_reply_is_bad(tmp_path, monkeypatch):
    good = {
        "repos/o/r/traffic/views": reply(("2026-11-12", 1, 1)),
        "repos/o/r/traffic/clones": {"clones": "broken"},
        "repos/o/r/traffic/popular/referrers": [],
        "repos/o/r/traffic/popular/paths": [],
    }
    monkeypatch.setattr(save_traffic, "gh", lambda path: json.loads(json.dumps(good[path])))
    assert save_traffic.main(["save_traffic.py", str(tmp_path), "o/r"]) == 1
    assert not (tmp_path / "o__r").exists()
