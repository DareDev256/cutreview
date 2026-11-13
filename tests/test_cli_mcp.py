"""The two doors: the command line and the one MCP tool."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import FIXTURES

from cutreview import __version__, cli, mcp_server


def run_cli(*args):
    return subprocess.run([sys.executable, "-m", "cutreview.cli", *args], capture_output=True, text=True)


def test_help_and_version():
    out = run_cli("--help")
    assert out.returncode == 0 and "diff" in out.stdout and "status" in out.stdout
    assert run_cli("--version").stdout.strip() == f"cutreview {__version__}"


def test_cli_end_to_end(music_round, tmp_path):
    assert cli.main(["diff", str(music_round.marked), str(music_round.next_export), "-o", str(tmp_path / "d.html"), "--no-frames"]) == 0
    assert cli.main(["blame", str(music_round.marked), str(music_round.next_export), "-o", str(tmp_path / "b.html"), "--no-frames"]) == 0
    assert cli.main(["status", str(music_round.marked), str(music_round.next_export), "-o", str(tmp_path / "s.html"), "--no-frames"]) == 0
    assert all((tmp_path / f).stat().st_size > 1000 for f in ("d.html", "b.html", "s.html"))


def test_cli_fails_loud_on_a_missing_file(tmp_path):
    out = run_cli("diff", str(tmp_path / "nope.fcpxml"), str(tmp_path / "nope2.fcpxml"))
    assert out.returncode == 1 and "nope.fcpxml" in out.stderr


def test_notes_command_lists_unplaced_and_unreadable(work, capsys):
    assert cli.main(["notes", str(work / "music-video.fcpxml"), str(FIXTURES / "music-video.notes.txt"),
                     "-o", str(work / "m.fcpxml")]) == 0
    out = capsys.readouterr().out
    assert "6 notes written" in out
    assert "2 not placed (listed, never guessed)" in out and "2 unreadable (listed, never dropped)" in out
    ledger = json.loads((work / "m.fcpxml.cutreview.json").read_text())
    assert len(ledger["placed"]) == 6 and len(ledger["unplaced"]) == 2 and len(ledger["unreadable"]) == 2


def test_mcp_lists_one_tool_with_four_actions():
    tools = asyncio.run(mcp_server.list_tools())
    assert [t.name for t in tools] == ["review"]
    schema = tools[0].inputSchema if hasattr(tools[0], "inputSchema") else tools[0].input_schema
    assert schema["properties"]["action"]["enum"] == ["diff", "blame", "notes", "status"]


def test_mcp_diff_and_status(music_round):
    text = asyncio.run(mcp_server.call_tool("review", {
        "action": "status", "old": str(music_round.marked), "new": str(music_round.next_export), "frames": False}))[0].text
    assert "Ticked but untouched: 1" in text and "Changed but not ticked: 1" in text


@pytest.mark.parametrize("output,why", [
    ("/tmp/elsewhere.html", "output must be inside"),
    ("../escape.html", "output must be inside"),
    ("page.txt", "must end in .html"),
])
def test_mcp_refuses_writes_outside_the_cut_folder(music_round, output, why):
    text = asyncio.run(mcp_server.call_tool("review", {
        "action": "diff", "old": str(music_round.marked), "new": str(music_round.next_export), "output": output}))[0].text
    assert text.startswith("cutreview refused") and why in text


def test_mcp_refuses_non_fcpxml_inputs(music_round):
    text = asyncio.run(mcp_server.call_tool("review", {"action": "diff", "old": "/etc/passwd", "new": str(music_round.next_export)}))[0].text
    assert "must end in .fcpxml" in text


def test_mcp_over_stdio(music_round):
    """A real client conversation: initialize, list tools, call one."""
    proc = subprocess.Popen([sys.executable, "-m", "cutreview.cli", "mcp"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            env=dict(os.environ, PYTHONUNBUFFERED="1"))

    def send(msg):
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()

    def recv():
        while True:
            line = proc.stdout.readline()
            if not line:
                raise RuntimeError(proc.stderr.read())
            msg = json.loads(line)
            if "id" in msg:
                return msg

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "test", "version": "0"}}})
        assert recv()["result"]["serverInfo"]["name"] == "cutreview"
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert [t["name"] for t in recv()["result"]["tools"]] == ["review"]
        send({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "review", "arguments": {
            "action": "diff", "old": str(music_round.marked), "new": str(music_round.next_export), "frames": False}}})
        text = recv()["result"]["content"][0]["text"]
        assert "4 changes" in text and Path(text.split("Page: ")[1].strip()).is_file()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
