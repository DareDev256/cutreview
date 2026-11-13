# Final Cut proof: push in, tick, read back

Status: **run 2026-11-12, Final Cut side passed; cutreview failed the first read and was fixed the same night.** Result at the end. The v0.1 build itself never opens Final Cut (no GUI, no window focus); these are the steps for whoever runs it with the app. About ten minutes.

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

## Result

**Run on 2026-11-12, 23:56 to 23:58, on screen, with Final Cut Pro 12.4.** The export dialog offered FCPXML 1.14 as current; the export is a bundle. Both files are kept byte for byte in `tests/fixtures/fcp-12.4-roundtrip/` (`maya_v1_notes.fcpxml`, sha256 `30802ee3...2fd20`, and `maya_fcp.fcpxmld/Info.fcpxml`, sha256 `4259c091...d87ff`), and `tests/test_fcp_roundtrip.py` pins both hashes.

### Final Cut side: passed

| Marker name | Timeline | On clip | Seen |
|---|---|---|---|
| #1 Open on her laugh, not the breath before it | 01:00:01:12 | Interview Open | matched |
| #2 Street shot is too long, half it | 01:00:07:00 | Street Wide | matched |
| #3 This cutaway covers her best line | 01:00:12:12 | Street Cutaway (connected, lane 1) | matched, on the cutaway |
| #4 Studio detail feels random here | 01:00:19:00 | Studio Detail | matched |
| #5 Drone could hold longer | 01:00:23:00 | Drone Reveal | matched |
| #6 Logo needs a beat of black before it | 01:00:27:00 | Logo | matched |

- Import: the event and project came in with media online, six to-do markers, all at the exact times above.
- The note text was kept and shown in the Timeline Index's Notes column.
- Ticking #1 and #3 turned them green (completed).
- The recut: Street Wide's end trimmed two seconds (4s to 2s), the storyline rippled.
- The export: six markers; `grep -c 'completed="1"'` gives **2** (#1 and #3); `grep -c ' note="'` gives **6** (note kept on every marker).

### cutreview side: failed, then fixed

Run on the export as it came out of Final Cut, with v0.1.0 as first committed (`27ac551`):

```
$ cutreview diff maya_v1_notes.fcpxml maya_fcp.fcpxmld
maya_v1_notes.fcpxml -> maya_fcp.fcpxmld: 16 changes (8 removed, 8 added)
  1  01:00:00:00  removed    Music Bed: removed (29s at 01:00:00:00)
  2  01:00:00:00  added      Music Bed: added (29s at 01:00:00:00)
  ...
$ cutreview status maya_v1_notes.fcpxml maya_fcp.fcpxmld
6 notes in maya_v1_notes.fcpxml, checked against maya_fcp.fcpxmld
Ticked but untouched: 0
Changed but not ticked: 0
Every note:
  #1 01:00:01:12 removed with its clip (by change 3): Open on her laugh, not the breath before it
  #2 01:00:07:00 removed with its clip (by change 3, 5): Street shot is too long, half it
  #3 01:00:12:12 removed with its clip (by change 8, 10): This cutaway covers her best line
  #4 01:00:19:00 removed with its clip (by change 8, 12): Studio detail feels random here
  #5 01:00:23:00 removed with its clip (by change 14): Drone could hold longer
  #6 01:00:27:00 removed with its clip (by change 14, 16): Logo needs a beat of black before it
```

The cause: Final Cut rewrites every asset on export. It renumbers the resource ids (a2 becomes r2), adds `uid` and a `media-rep sig`, drops `start="0s"` on clips, drops `format` on asset-clips and reorders attributes. cutreview named each source by its `uid` when it had one and by its media path otherwise. The file it wrote had no `uid`, Final Cut's export did, so no source matched across the round trip.

The fix (DECISIONS.md, 2026-11-13): a source is named by its media file first, then Final Cut's `uid` and `sig`, then its asset name only when it has none of those; a resource id is never identity. Every name a source has is joined across both files, so a file relinked between exports still matches through its `uid`. A missing `start` reads as zero. The same two files after the fix:

```
$ cutreview diff maya_v1_notes.fcpxml maya_fcp.fcpxmld
maya_v1_notes.fcpxml -> maya_fcp.fcpxmld: 1 change (1 trimmed)
  1  01:00:08:00  trimmed    Street Wide: end trimmed 2s shorter
5 clips only slid with the ripple (not listed)
$ cutreview status maya_v1_notes.fcpxml maya_fcp.fcpxmld
6 notes in maya_v1_notes.fcpxml, checked against maya_fcp.fcpxmld
Ticked but untouched: 2
  #1 01:00:01:12 Open on her laugh, not the breath before it
  #3 01:00:12:12 This cutaway covers her best line
Changed but not ticked: 1
  #2 01:00:07:00 Street shot is too long, half it
Every note:
  #1 01:00:01:12 done, untouched: Open on her laugh, not the breath before it
  #2 01:00:07:00 open, touched (by change 1): Street shot is too long, half it
  #3 01:00:12:12 done, untouched: This cutaway covers her best line
  #4 01:00:19:00 open, untouched: Studio detail feels random here
  #5 01:00:23:00 open, untouched: Drone could hold longer
  #6 01:00:27:00 open, untouched: Logo needs a beat of black before it
```

That is the expected result from step 6, exactly. `tests/test_fcp_roundtrip.py` asserts it, and `scripts/mutate.py` checks that keying sources by resource id again makes it fail.

Still open from this proof: the round trip used ffmpeg test media and one hand edit. A real project with real footage and more kinds of edit (a blade, a transition, a speed change made in Final Cut) is the next round.
