"""Which tool call made each change, from fcp-mcp-server's write journal.

fcp-mcp-server appends one JSON line per write: tool, action, arguments, the
input's sha256 and the output's sha256 (``fcpxml/journal.py``). Every write
is a NEW file, so the journal is a chain of hashes. Blame walks that chain
from the old file's hash towards the new file's hash, diffs each step with
the same change model as the page, and gives each final change to the LAST
step that changed that material.

What it will not do: guess. A change no journaled step explains reads "not
in the journal" (made by hand in Final Cut, or by a tool that keeps no
journal). When an intermediate file is gone (an undo parked it, someone
deleted it), the steps around it are named as a group.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from fcpxml import journal as fcp_journal

from .changes import Review, compare
from .cut import file_sha256, load

_SKIP = {"undo", "preview_render"}


@dataclass
class Step:
    row: dict
    path: Optional[str]           # where the step's output is now, or None when gone

    @property
    def label(self) -> str:
        return f"{self.row.get('tool', '?')}.{self.row.get('action', '?')}"

    @property
    def args(self) -> str:
        args = dict(self.row.get("args") or {})
        for k in ("filepath", "output_path", "expected_sha256"):
            args.pop(k, None)
        return ", ".join(f"{k}={v}" for k, v in sorted(args.items()))

    @property
    def when(self) -> str:
        import time
        ts = self.row.get("ts")
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) if ts else ""


@dataclass
class BlameResult:
    journals: List[str]
    steps: List[Step]
    reached: bool                  # the chain ends exactly at the new file
    unexplained: int = 0
    notes: List[str] = field(default_factory=list)


def journal_candidates(old_path: str, explicit: Optional[str] = None) -> List[Path]:
    """Where fcp-mcp-server may have kept this project's journal, in order."""
    folder = Path(old_path).expanduser().resolve().parent
    key = fcp_journal.project_key(str(Path(old_path).expanduser().resolve()))
    out: List[Path] = []
    if explicit:
        p = Path(explicit).expanduser()
        out.extend(sorted(p.glob("*.jsonl")) if p.is_dir() else [p])
    env = os.environ.get("FCP_MCP_JOURNAL", "").strip()
    if env and env.lower() not in ("off", "0", "false", "no"):
        out.append(Path(env).expanduser() / f"{key}.jsonl")
    for d in (folder, folder / "journal", folder / ".fcp-mcp" / "journal"):
        out.append(d / f"{key}.jsonl")
        out.extend(sorted(d.glob("*.jsonl")) if d.is_dir() else [])
    out.append(Path.home() / ".fcp-mcp" / "journal" / f"{key}.jsonl")
    seen, uniq = set(), []
    for p in out:
        rp = p.resolve() if p.exists() else p
        if rp not in seen and p.is_file():
            seen.add(rp)
            uniq.append(p)
    return uniq


def _rows(files: List[Path]) -> List[dict]:
    rows = []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict) and row.get("action") not in _SKIP:
                    rows.append(row)
    rows.sort(key=lambda r: r.get("ts", 0))
    return rows


def _locate(row: dict, folder: Path) -> Optional[str]:
    out = row.get("output") or {}
    want = out.get("sha256")
    for cand in (out.get("path"), str(folder / Path(out.get("path") or "").name)):
        if cand and Path(cand).exists():
            try:
                if file_sha256(cand) == want:
                    return cand
            except OSError:
                continue
    return None


def chain(rows: List[dict], old_hash: str, new_hash: str) -> tuple:
    """The journaled path from old_hash: the one ending at new_hash, else the longest."""
    by_input: Dict[str, List[dict]] = {}
    for r in rows:
        h = (r.get("input") or {}).get("sha256")
        o = (r.get("output") or {}).get("sha256")
        if h and o and h != o:
            by_input.setdefault(h, []).append(r)
    best: List[dict] = []
    stack = [(old_hash, [])]
    seen = set()
    while stack:
        h, path = stack.pop()
        if h == new_hash and path:
            return path, True
        if len(path) > len(best) or (len(path) == len(best) and path and best
                                     and path[-1].get("ts", 0) > best[-1].get("ts", 0)):
            best = path
        for r in by_input.get(h, []):
            o = r["output"]["sha256"]
            if o not in seen:
                seen.add(o)
                stack.append((o, path + [r]))
    return best, False


def blame(review: Review, journal: Optional[str] = None) -> BlameResult:
    """Attribute each change in *review* (in place) and return what was found."""
    old, new = review.old, review.new
    files = journal_candidates(old.path, journal)
    result = BlameResult(journals=[str(f) for f in files], steps=[], reached=False)
    for c in review.changes:
        c.blame = {"by": "journal not found", "kind": "none"}
    if not files:
        result.notes.append(
            "No fcp-mcp-server journal found for this folder. Looked in FCP_MCP_JOURNAL, "
            "the project folder, its journal/ and .fcp-mcp/journal/, and ~/.fcp-mcp/journal/."
        )
        result.unexplained = len(review.changes)
        return result
    rows = _rows(files)
    path_rows, reached = chain(rows, old.sha256, new.sha256)
    result.reached = reached
    folder = Path(old.path).resolve().parent
    steps = [Step(r, _locate(r, folder)) for r in path_rows]
    result.steps = steps
    if not steps:
        result.notes.append("The journal has no write that started from the old file's hash.")
        for c in review.changes:
            c.blame = {"by": "not in the journal", "kind": "hand"}
        result.unexplained = len(review.changes)
        return result

    # Diff each available step; a missing file joins its neighbours into a group.
    prev_path, group = old.path, []
    attributed: Dict[tuple, dict] = {}
    for i, st in enumerate(steps):
        group.append(st)
        if st.path is None and i < len(steps) - 1:
            continue
        end_path = st.path
        if end_path is None:          # the last step's file is gone too
            if reached:
                end_path = new.path
            else:
                result.notes.append(f"{len(group)} step(s) at the end of the chain have no file left to diff.")
                break
        step_review = compare(load(prev_path), load(end_path))
        if len(group) == 1:
            who = {"by": st.label, "args": st.args, "when": st.when, "kind": "journal"}
        else:
            who = {"by": "one of " + ", ".join(s.label for s in group),
                   "args": "", "when": group[-1].when, "kind": "group",
                   "why": "the files between these steps are gone, so they cannot be told apart"}
        for c in step_review.changes:
            attributed[c.signature()] = who          # later steps overwrite: the last writer wins
        prev_path, group = end_path, []

    end_hash = file_sha256(prev_path)
    tail_review = compare(load(prev_path), new) if end_hash != new.sha256 else None
    hand = {c.signature() for c in tail_review.changes} if tail_review else set()

    for c in review.changes:
        sig = c.signature()
        hits = [v for k, v in attributed.items() if _same(k, sig)]
        by_hand = any(_same(k, sig) for k in hand)
        if by_hand and hits:
            c.blame = dict(hits[-1], kind="journal+hand",
                           why="a journaled write changed this material, and so did a change after the last journaled write")
        elif by_hand:
            c.blame = {"by": "not in the journal", "kind": "hand",
                       "why": "made after the last journaled write: by hand in Final Cut, or by a tool with no journal"}
        elif hits:
            c.blame = hits[-1]
        else:
            c.blame = {"by": "not in the journal", "kind": "hand"}
    result.unexplained = sum(1 for c in review.changes if c.blame.get("kind") == "hand")
    if not reached:
        result.notes.append(
            "The journal does not reach the new file's hash, so the new file was "
            "written outside fcp-mcp-server (a Final Cut export, or another tool)."
        )
    return result


def _same(a: tuple, b: tuple) -> bool:
    """Same kind of change on overlapping source material."""
    if a[0] != b[0]:
        return False
    for ka, a0, a1 in a[1]:
        for kb, b0, b1 in b[1]:
            if ka == kb and a0 < b1 + 0.05 and b0 < a1 + 0.05:
                return True
    return not a[1] and not b[1]
