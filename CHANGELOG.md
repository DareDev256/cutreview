# Changelog

## 0.1.0 (2026-11-12)

First version. Not yet published.

Added:

- `cutreview diff OLD NEW`: one self-contained HTML page of what changed between two Final Cut exports. Clips are matched by source material, so ripples, head trims and gap-based (all connected) cuts read correctly. Timeline strip with changed ranges marked, before and after source frames when the media is on the machine, both file hashes and export times.
- `cutreview blame OLD NEW`: each change attributed to the fcp-mcp-server tool call that wrote it, from that server's sha256 journal; work after the last journaled write reads "not in the journal".
- `cutreview notes CUT NOTES`: plain text with timecodes, generic CSV and Frame.io comment CSV written into the cut as to-do markers on the clip under each note, in its source time. Unplaced notes and unreadable lines are listed with reasons and kept in a JSON ledger. Every write is checked against Apple's FCPXML DTD and read back through fcp-mcp-server's parser before it is kept.
- `cutreview status MARKED NEXT`: each note done or open (the editor's tick) and touched or untouched, leading with ticked but untouched and changed but not ticked; "removed with its clip" and "its frames were cut" when the material is gone.
- `cutreview mcp`: one MCP tool, `review`, with actions diff, blame, notes, status, over stdio, on mcp 1.x or 2.x. Writes stay inside the cut's folder.
- 85 tests, 17 guard mutations (`scripts/mutate.py`), a demo round on synthesized media (`scripts/make_demo.py`) and a rendered page check at 1440 and 390 in both colour schemes (`scripts/screenshots.py`).
