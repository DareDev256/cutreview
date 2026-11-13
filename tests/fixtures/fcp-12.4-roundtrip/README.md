# A real Final Cut Pro 12.4 round trip

| File | What it is |
|---|---|
| `maya_v1_notes.fcpxml` | The demo cut with six to-do markers, as `cutreview notes` wrote it (`scripts/make_demo.py`). This is the file Final Cut imported. |
| `maya_fcp.fcpxmld/` | What Final Cut Pro 12.4 exported on 2026-11-12 at 23:58 after the editor ticked #1 and #3 and trimmed the end of Street Wide by two seconds. FCPXML 1.14, a bundle. |

Both are what Final Cut and `cutreview notes` wrote, with only the edits below, made on 2026-11-13 before the repo was made public so that no file names the machine that made them. Nothing else was changed: not an id, a uid, a sig, a time, a marker, a note, a date or the attribute order. `tests/test_fcp_roundtrip.py` pins the sha256 of each file as it is now and fails if either is edited again.

| File | Edit |
|---|---|
| both | Each `media-rep src` path `file:///<home>/Projects/tools/cutreview/build/demo/media/<clip>` became `file:///Users/editor/cutreview-demo/media/<clip>`, file names unchanged (6 in each file). |
| `maya_fcp.fcpxmld/Info.fcpxml` | The `library location` became `file:///Users/editor/cutreview-demo/CutReview%20Proof.fcpbundle/` (it named the library's folder on that machine). |
| `maya_fcp.fcpxmld/Info.fcpxml` | The six `<bookmark>` elements were removed, one per `media-rep`, each on its own line. A bookmark is a base64 macOS security-scoped bookmark that encodes the same path and the volume's identifiers. The 1.14 DTD declares it optional (`<!ELEMENT media-rep (bookmark?)>`), and the file still validates against Apple's FCPXMLv1_14.dtd. |

Without its bookmarks, Final Cut relinks a re-imported copy of this export by path, so the media shows offline unless the clips sit at that path. cutreview never reads bookmarks, so its reading of the pair is the same as on the unedited files: one change (Street Wide's end trimmed 2s shorter), #1 and #3 ticked and untouched, #2 open and touched.

The steps that produced the files, and what was seen in Final Cut, are in `docs/final-cut-proof.md`.
