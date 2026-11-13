# Final Cut proof: push in, tick, read back

Status: **staged, not run.** The v0.1 build never opens Final Cut (no GUI, no window focus). These are the exact steps for whoever runs it with the app. About ten minutes.

What it proves: Final Cut Pro 12.4 imports the to-do markers cutreview writes, shows them on the right clips at the right times, writes the editor's tick back as `completed="1"`, and cutreview reads that export.

## 0. Build the round (terminal, no GUI)

```
cd ~/Projects/tools/cutreview
.venv/bin/python scripts/make_demo.py build/demo
```

This makes five clips with ffmpeg test sources in `build/demo/media/`, the cut `build/demo/maya_v1.fcpxml`, and the marked cut `build/demo/maya_v1_notes.fcpxml` with six to-do markers. Its output ends with three pages; ignore them for this proof. The marked file is already checked against Apple's 1.13 DTD and read back.

## 1. A scratch library

Final Cut Pro 12.4: **File > New > Library...**, save as `~/Movies/CutReview Proof.fcpbundle`. Nothing in this proof touches any other library.

## 2. Import

**File > Import > XML...**, choose `build/demo/maya_v1_notes.fcpxml`.

Expected: an event "Cut Review Demo" holding the project "Maya Profile v1", media online (no red offline frames).

Failure looks like: an import error naming the DTD or a time value; offline media; no project.

## 3. Check the markers

Open the project. **Window > Show in Workspace > Timeline Index** (Shift-Command-2), **Tags** tab, show To Do items.

Expected, exactly six, all incomplete:

| Marker name | Timeline | On clip |
|---|---|---|
| #1 Open on her laugh, not the breath before it | 01:00:01:12 | Interview Open |
| #2 Street shot is too long, half it | 01:00:07:00 | Street Wide |
| #3 This cutaway covers her best line | 01:00:12:12 | Street Cutaway (connected, lane 1) |
| #4 Studio detail feels random here | 01:00:19:00 | Studio Detail |
| #5 Drone could hold longer | 01:00:23:00 | Drone Reveal |
| #6 Logo needs a beat of black before it | 01:00:27:00 | Logo |

Click #3 in the index: the playhead lands on the cutaway above Interview Answer, and the marker sits on the cutaway, not on the clip below.

Double-click #2 to open its marker window. Record whether the note text ("Street shot is too long, half it (client-notes.txt line 2, written at 01:00:07:00)") appears anywhere in Final Cut's interface. The DTD declares `note` on `marker`; whether 12.4 shows or keeps it is one of the things this proof finds out.

Failure looks like: fewer than six; a marker a frame or more off its time; #3 on Interview Answer; markers shown as standard (blue) instead of to-do (red).

## 4. Recut by hand

1. Open marker #1's window, check **Completed**. Do the same for #3. Leave #2 unticked.
2. Trim the end of **Street Wide** two seconds shorter: select its end edge, type `-2.00`, press Return (the storyline ripples).

## 5. Export

Select the project in the browser. **File > Export XML...**, save as `build/demo/maya_fcp.fcpxmld` (Final Cut 12 writes a bundle; cutreview reads bundles). Note which XML version the dialog offered.

## 6. Read it back

```
cd ~/Projects/tools/cutreview
.venv/bin/cutreview status build/demo/maya_v1_notes.fcpxml build/demo/maya_fcp.fcpxmld -o build/demo/fcp-status.html
.venv/bin/cutreview diff   build/demo/maya_v1_notes.fcpxml build/demo/maya_fcp.fcpxmld -o build/demo/fcp-review.html
grep -c 'completed="1"' build/demo/maya_fcp.fcpxmld/Info.fcpxml
grep -c ' note="' build/demo/maya_fcp.fcpxmld/Info.fcpxml
```

Expected:

- `status`: 6 notes. Ticked but untouched: #1 and #3. Changed but not ticked: #2. #4, #5 and #6 open and untouched.
- `diff`: one change, "Street Wide: end trimmed 2s shorter", and a line saying the later clips only slid.
- `completed="1"` count: 2. `note="` count: 6 if Final Cut keeps the note, 0 if it drops it.

Failure looks like, and what it would mean:

| Seen | Meaning |
|---|---|
| status finds fewer than 6 notes | Final Cut renamed or dropped a marker; read `Info.fcpxml` for the six `#N` names |
| #1 or #3 reads open | Final Cut wrote the tick somewhere other than `completed`; read the marker element |
| diff lists more than one change | Final Cut changes something on a round trip (asset ids, formats, durations). Each extra line is a v0.2 fix in the change model; record them verbatim |
| `note="` count is 0 | Final Cut drops the note on import or export. The `#N` name still carries identity; the full text then lives only in the ledger, and the README must say so |

## 7. Record the result here

Add a "Result" section below with: the date, Final Cut's version (Final Cut Pro > About), the XML version exported, the six-row table with what was seen, the `status` summary as printed, the two grep counts, and any extra `diff` lines. Then close the scratch library and move `~/Movies/CutReview Proof.fcpbundle` to the Trash.

## Optional: the gap-based fixture

`fixtures/music-video.fcpxml` hangs every clip off a gap, the shape where fcp-mcp-server's spine tools see nothing. After `cutreview notes fixtures/music-video.fcpxml fixtures/music-video.notes.txt -o build/mv_notes.fcpxml`, importing `build/mv_notes.fcpxml` the same way checks that markers on connected clips survive Final Cut. Its media paths are fictional, so the clips import offline; the markers are what to check. Its `offset="3606500/1000s"` is deliberately off the 23.98 frame grid, and Final Cut may warn about it.
