"""cutreview: notes in as Final Cut to-do markers, the changed cut out as one page."""

from __future__ import annotations

import argparse
import sys

from . import __version__

EPILOG = """\
examples:
  cutreview diff cut_v1.fcpxml cut_v2.fcpxml -o review.html
  cutreview blame cut_v1.fcpxml cut_v2.fcpxml
  cutreview notes cut_v1.fcpxml notes.txt
  cutreview status cut_v1_notes.fcpxml cut_v2.fcpxml -o status.html
  cutreview mcp

No server, no account, no upload. Every page is one HTML file.
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cutreview",
        description="Review notes in as Final Cut to-do markers; two exports in, one page out "
                    "showing what changed and which notes it touched.",
        epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version", action="version", version=f"cutreview {__version__}")
    sub = p.add_subparsers(dest="cmd", metavar="command")

    d = sub.add_parser("diff", help="what changed between two exports, as one page")
    d.add_argument("old", help="the earlier .fcpxml or .fcpxmld")
    d.add_argument("new", help="the later .fcpxml or .fcpxmld")
    d.add_argument("-o", "--output", help="page to write (default: <new>_review.html)")
    d.add_argument("--no-frames", action="store_true", help="skip before and after frames")

    b = sub.add_parser("blame", help="which fcp-mcp-server tool call made each change")
    b.add_argument("old")
    b.add_argument("new")
    b.add_argument("-o", "--output", help="page to write (default: <new>_blame.html)")
    b.add_argument("--journal", help="a journal file or folder (default: look where fcp-mcp-server keeps it)")
    b.add_argument("--no-frames", action="store_true")

    n = sub.add_parser("notes", help="write review notes into a cut as to-do markers")
    n.add_argument("cut", help="the .fcpxml the notes are about")
    n.add_argument("notes", help="plain text with timecodes, a CSV, or a Frame.io comment CSV")
    n.add_argument("-o", "--output", help="marked file to write (default: <cut>_notes.fcpxml)")
    n.add_argument("--format", default="auto", choices=["auto", "text", "csv", "frameio"])
    n.add_argument("--author", default="", help="who wrote the notes, when the file does not say")
    n.add_argument("--start-tc", help="the timecode the notes count from, e.g. 01:00:00:00 (default: the sequence start)")
    n.add_argument("--source-tc", action="store_true", help="Frame.io: use the Timecode Source columns")

    s = sub.add_parser("status", help="each note done or open, touched or untouched, in the next export")
    s.add_argument("marked", help="the file the notes were written into")
    s.add_argument("next", help="the next export of the same project")
    s.add_argument("-o", "--output", help="page to write (default: <next>_status.html)")
    s.add_argument("--reach", type=float, default=1.0, help="seconds around a note that count as under it (default 1)")
    s.add_argument("--ledger", help="the notes ledger (default: <marked>.cutreview.json)")
    s.add_argument("--no-frames", action="store_true")

    sub.add_parser("mcp", help="run the MCP server (stdio) with one tool, review")
    return p


def _quiet_library() -> None:
    # fcp-mcp-server logs timebase style warnings about the INPUT on every
    # save. cutreview's own checks (Apple's DTD, the read-back) decide
    # whether a write is kept, and they report in the summary.
    import logging

    logging.getLogger("fcpxml").setLevel(logging.ERROR)


def main(argv=None) -> int:
    _quiet_library()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.cmd:
        parser.print_help()
        return 2
    if args.cmd == "mcp":
        from .mcp_server import run
        run()
        return 0
    from . import api
    try:
        if args.cmd == "diff":
            res = api.diff(args.old, args.new, args.output, frames=not args.no_frames)
        elif args.cmd == "blame":
            res = api.blame(args.old, args.new, args.output, args.journal, frames=not args.no_frames)
        elif args.cmd == "notes":
            res = api.notes(args.cut, args.notes, args.output, args.format, args.author,
                            args.start_tc, args.source_tc)
        else:
            res = api.status(args.marked, args.next, args.output, args.reach, args.ledger,
                             frames=not args.no_frames)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"cutreview {args.cmd}: {exc}", file=sys.stderr)
        return 1
    print(res.summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
