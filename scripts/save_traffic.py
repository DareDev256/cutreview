"""Save a GitHub repo's traffic before GitHub forgets it.

    python3 scripts/save_traffic.py OUT_DIR OWNER/REPO [OWNER/REPO ...]

GitHub keeps 14 days of views, clones, referrers and popular paths, then
drops them. fcp-mcp-server lost every day before its first look at the
numbers, so nobody can say which post or listing sent its first hundred
stars. Run this daily (launchd) and the history stays.

For each repo it reads, through the `gh` CLI (your login, read only):

    traffic/views, traffic/clones           one row per day, kept forever
    traffic/popular/referrers, .../paths    the 14-day top ten, one dated snapshot per run

and writes OUT_DIR/OWNER__REPO/{views,clones}.json (merged by day: a later
read of the same day replaces the earlier one, because today's count is
partial until the day ends) and OUT_DIR/OWNER__REPO/{referrers,paths}.jsonl
(one line per run, with the time it was read).

It refuses rather than guesses: a failed `gh` call, or a reply without the
fields it expects, exits 1 and writes nothing for that repo. A repo that is
private or not yet created reads as a failure, so add a repo to the job only
once it is public.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def gh(path: str) -> dict | list:
    out = subprocess.run(["gh", "api", path], capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise RuntimeError(f"gh api {path}: {out.stderr.strip() or out.stdout.strip()}")
    return json.loads(out.stdout)


def merge_days(old: dict, reply: dict, kind: str) -> dict:
    """Merge a views or clones reply into the saved days. Refuses a reply without its day list."""
    if not isinstance(reply, dict) or not isinstance(reply.get(kind), list):
        raise ValueError(f"{kind}: reply has no '{kind}' list")
    days = dict(old)
    for row in reply[kind]:
        if not {"timestamp", "count", "uniques"} <= set(row):
            raise ValueError(f"{kind}: row without timestamp/count/uniques: {row}")
        days[row["timestamp"][:10]] = {"count": int(row["count"]), "uniques": int(row["uniques"])}
    return dict(sorted(days.items()))


def snapshot(reply: list, kind: str, read_at: str) -> dict:
    if not isinstance(reply, list):
        raise ValueError(f"{kind}: reply is not a list")
    return {"read_at": read_at, kind: reply}


def save(out_dir: Path, repo: str) -> str:
    read_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    base = f"repos/{repo}/traffic"
    replies = {
        "views": gh(f"{base}/views"),
        "clones": gh(f"{base}/clones"),
        "referrers": gh(f"{base}/popular/referrers"),
        "paths": gh(f"{base}/popular/paths"),
    }
    folder = out_dir / repo.replace("/", "__")
    merged = {}
    for kind in ("views", "clones"):
        path = folder / f"{kind}.json"
        old = json.loads(path.read_text()).get("days", {}) if path.exists() else {}
        merged[kind] = merge_days(old, replies[kind], kind)
    snaps = {kind: snapshot(replies[kind], kind, read_at) for kind in ("referrers", "paths")}
    # Every reply checked before anything is written.
    folder.mkdir(parents=True, exist_ok=True)
    for kind, days in merged.items():
        (folder / f"{kind}.json").write_text(json.dumps({"repo": repo, "read_at": read_at, "days": days}, indent=1) + "\n")
    for kind, snap in snaps.items():
        with (folder / f"{kind}.jsonl").open("a") as fh:
            fh.write(json.dumps(snap) + "\n")
    v = merged["views"]
    return f"{repo}: {len(v)} days of views kept ({min(v) if v else '-'} to {max(v) if v else '-'}), read {read_at}"


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    out_dir = Path(argv[1]).expanduser()
    failed = 0
    for repo in argv[2:]:
        try:
            print(save(out_dir, repo))
        except (RuntimeError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
            failed += 1
            print(f"FAILED {repo}: {exc}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
