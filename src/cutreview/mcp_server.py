"""One MCP tool, ``review``, over stdio. Four actions: diff, blame, notes, status.

Registered against whichever ``mcp`` SDK is installed (1.x decorators or
2.x ``add_request_handler``) through fcp-mcp-server's ``mcp_compat`` probe.
Every page or file the tool writes stays inside the folder of the cut it
was given: a model cannot point it anywhere else.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent

from fcpxml.mcp_compat import build_tool, is_legacy_api

from . import __version__, api

TOOL_NAME = "review"
DESCRIPTION = (
    "Review a Final Cut cut. diff: what changed between two FCPXML exports, as one HTML page. "
    "blame: the same page with each change attributed to the fcp-mcp-server tool call that made it. "
    "notes: write a notes file (text with timecodes, CSV, or Frame.io comment CSV) into a cut as "
    "to-do markers; notes with no timecode are listed, never guessed. status: from the next export, "
    "each note done or open (the editor's tick) and touched or untouched (did the cut change under it)."
)
SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["diff", "blame", "notes", "status"]},
        "old": {"type": "string", "description": "diff/blame: earlier .fcpxml. status: the file the notes were written into."},
        "new": {"type": "string", "description": "diff/blame/status: the later .fcpxml"},
        "cut": {"type": "string", "description": "notes: the .fcpxml the notes are about"},
        "notes_file": {"type": "string", "description": "notes: .txt or .csv"},
        "format": {"type": "string", "enum": ["auto", "text", "csv", "frameio"], "default": "auto"},
        "output": {"type": "string", "description": "file to write; must be in the same folder as the cut"},
        "frames": {"type": "boolean", "default": True, "description": "pull before and after frames with ffmpeg"},
    },
    "required": ["action"],
}

_CUT_SUFFIXES = (".fcpxml", ".fcpxmld")
_NOTE_SUFFIXES = (".txt", ".csv", ".md", ".text")


class Refused(ValueError):
    pass


def _input(path: Optional[str], suffixes: tuple, what: str) -> str:
    if not path or "\x00" in path:
        raise Refused(f"{what} is required")
    p = Path(path).expanduser().resolve()
    if p.suffix.lower() not in suffixes:
        raise Refused(f"{what} must end in {' or '.join(suffixes)}")
    if not p.exists():
        raise Refused(f"{what} not found: {p}")
    return str(p)


def _output(path: Optional[str], anchor: str, suffixes: tuple) -> Optional[str]:
    if not path:
        return None
    if "\x00" in path:
        raise Refused("output path holds a null byte")
    out = Path(path).expanduser()
    if not out.is_absolute():
        out = Path(anchor).parent / out
    out = out.resolve()
    folder = Path(anchor).resolve().parent
    try:
        out.relative_to(folder)
    except ValueError:
        raise Refused(f"output must be inside {folder}") from None
    if out.suffix.lower() not in suffixes:
        raise Refused(f"output must end in {' or '.join(suffixes)}")
    return str(out)


def handle(arguments: dict) -> str:
    action = arguments.get("action")
    frames = bool(arguments.get("frames", True))
    if action in ("diff", "blame", "status"):
        old = _input(arguments.get("old"), _CUT_SUFFIXES, "old")
        new = _input(arguments.get("new"), _CUT_SUFFIXES, "new")
        out = _output(arguments.get("output"), new, (".html",))
        if action == "diff":
            res = api.diff(old, new, out, frames=frames)
        elif action == "blame":
            res = api.blame(old, new, out, frames=frames)
        else:
            res = api.status(old, new, out, frames=frames)
    elif action == "notes":
        cut = _input(arguments.get("cut"), _CUT_SUFFIXES, "cut")
        notes_file = _input(arguments.get("notes_file"), _NOTE_SUFFIXES, "notes_file")
        out = _output(arguments.get("output"), cut, _CUT_SUFFIXES)
        res = api.notes(cut, notes_file, out, arguments.get("format", "auto"))
    else:
        raise Refused("action must be one of diff, blame, notes, status")
    return res.summary


async def call_tool(name: str, arguments: dict[str, Any]) -> list:
    if name != TOOL_NAME:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    try:
        text = await asyncio.to_thread(handle, arguments or {})
    except (Refused, FileNotFoundError, ValueError, RuntimeError) as exc:
        text = f"cutreview refused: {exc}"
    return [TextContent(type="text", text=text)]


async def list_tools() -> list:
    return [build_tool(TOOL_NAME, DESCRIPTION, SCHEMA)]


def build_server() -> Server:
    server = Server("cutreview", version=__version__)
    if is_legacy_api():
        server.list_tools()(list_tools)
        server.call_tool()(call_tool)
        return server
    import mcp.types as types

    async def _on_list_tools(_ctx, _params):
        return types.ListToolsResult(tools=await list_tools())

    async def _on_call_tool(_ctx, params):
        return types.CallToolResult(content=list(await call_tool(params.name, params.arguments or {})))

    server.add_request_handler("tools/list", types.PaginatedRequestParams, _on_list_tools)
    server.add_request_handler("tools/call", types.CallToolRequestParams, _on_call_tool)
    return server


async def _main() -> None:
    server = build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def run() -> None:
    asyncio.run(_main())
