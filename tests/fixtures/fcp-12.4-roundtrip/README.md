# A real Final Cut Pro 12.4 round trip

| File | What it is |
|---|---|
| `maya_v1_notes.fcpxml` | The demo cut with six to-do markers, as `cutreview notes` wrote it (`scripts/make_demo.py`). This is the file Final Cut imported. |
| `maya_fcp.fcpxmld/` | What Final Cut Pro 12.4 exported on 2026-11-12 at 23:58 after the editor ticked #1 and #3 and trimmed the end of Street Wide by two seconds. FCPXML 1.14, a bundle. |

Both are kept byte for byte; `tests/test_fcp_roundtrip.py` pins their sha256 and fails if either is edited. The steps that produced them, and what was seen in Final Cut, are in `docs/final-cut-proof.md`.

**Before this repo is made public:** both files carry absolute paths from the machine that made them (every `media-rep src`, and the export's `library location`), and the export carries a macOS `<bookmark>` per asset: a base64 blob that encodes the same path and the volume's identifiers. They are kept unedited because they are the evidence. Whether to publish them as they are, or to publish a re-run made from a neutral folder, is a decision for the public-release review.
