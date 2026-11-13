# Guards, broken on purpose

Each guard below was broken once, on purpose, and a test had to go red. Rerun with:

```
.venv/bin/python scripts/mutate.py
```

The script edits one line of the source, runs the tests that claim to protect it, restores the file, and exits non-zero if any mutation survives. Last run 2026-11-12: all 17 caught.

| Guard broken on purpose | File | Result | First failing test |
|---|---|---|---|
| touched: the later cut's window counts | `status.py` | caught | tests/test_status.py::test_sample_round_catches_the_agent_trimming_the_wrong_clip |
| touched: the earlier cut's window counts | `status.py` | caught | tests/test_status.py::test_a_removal_next_to_a_note_touches_it_from_the_earlier_cut |
| audio-lane changes do not touch picture notes | `status.py` | caught | tests/test_changes.py::test_an_audio_lane_change_does_not_touch_a_picture_note |
| a removed clip reads 'removed with its clip' | `status.py` | caught | tests/test_status.py::test_music_video_round |
| a marker hidden by a trim reads 'frames cut' | `status.py` | caught | tests/test_status.py::test_a_marker_hidden_by_a_trim_reads_as_frames_cut |
| no timecode is unplaced, never given a time | `notes.py` | caught | tests/test_notes.py::test_no_timecode_is_unplaced_never_given_a_time |
| unreadable lines are listed, never dropped | `notes.py` | caught | tests/test_notes.py::test_every_non_blank_line_is_accounted_for |
| the hour rule needs every note past the hour | `notes.py` | caught | tests/test_notes.py::test_hour_rule_needs_every_note_past_the_hour |
| DTD: a new error refuses the write | `markers.py` | caught | tests/test_markers.py::test_dtd_refuses_a_new_error_and_leaves_nothing |
| read-back: a misplaced marker refuses the write | `markers.py` | caught | tests/test_markers.py::test_readback_refuses_a_marker_on_the_wrong_frame |
| a ripple is not a move (order kept = longest run) | `changes.py` | caught | tests/test_changes.py::test_a_ripple_trim_is_one_change_and_the_rest_only_slid |
| a connected clip moves with its host | `changes.py` | caught | tests/test_changes.py::test_a_connected_clip_riding_a_rippled_host_only_slid |
| a head trim is a trim, not a swap (one-to-one pairing) | `changes.py` | caught | tests/test_changes.py::test_a_head_trim_reads_as_a_trim_not_a_swap |
| blame: work after the last journaled write is 'not in the journal' | `blame.py` | caught | tests/test_blame.py::test_journal_then_hand_on_the_same_material |
| MCP: writes stay in the cut's folder | `mcp_server.py` | caught | tests/test_cli_mcp.py::test_mcp_refuses_writes_outside_the_cut_folder[/tmp/elsewhere.html-output must be inside] |
| page: nothing loads from the network | `page.py` | caught | tests/test_page.py::test_pages_are_self_contained |
| page: note text is escaped | `page.py` | caught | tests/test_page.py::test_note_text_is_escaped |

## The spec's mutation

"Remove one change from the fixture, and the note under it must flip to untouched": `tests/test_status.py::test_mutation_remove_one_change_and_its_note_flips_to_untouched` rebuilds the music-video round through fcp-mcp-server with the OVERLAY 3 trim left out. Note #4 ("Overlay 3 distracts from the lyric") reads **open, touched** with the trim and **open, untouched** without it, while #2 and #5 stay **done, touched**. A second test leaves out the by-hand deletion of OVERLAY 1, and #3 flips from **removed with its clip** to **open, untouched**.

## The page checks, broken on purpose

`scripts/screenshots.py` renders each page at 1440 and 390, dark and light, and fails on horizontal overflow, on two labels overlapping inside one row of labels, or on any request that is not `file:` or `data:`. On 2026-11-12 a copy of the review page got a 2400px wide element and a copy of the status page got `.meta span{margin-right:-90px}`:

| Render | Overflow | Overlapping label pairs | Result |
|---|---|---|---|
| review, 1440 | 1154px | 0 | failed, as it should |
| review, 390 | 2026px | 0 | failed, as it should |
| status, 1440 | 0 | 68 | failed, as it should |
| status, 390 | 0 | 74 | failed, as it should |
| blame (unchanged) | 0 | 0 | passed |

The real pages pass all 12 renders.

## What the first mutation run found

The first run let four mutations through, which is the point of running it:

1. **Touched by source overlap** never decided a case that the timeline window had not already decided. The branch was removed, so "touched" is now one rule (DECISIONS.md, 2026-11-12).
2. **The earlier cut's timeline window** had no test of its own: every case it caught, the later cut's window also caught. Added a removal beside a note, which only the earlier cut can see.
3. **The hour rule** test passed a cut longer than an hour, so the rule could not apply either way. The test was vacuous; it now uses a 50 minute cut.
4. **"Changed again after the last journaled write"** had no test changing the same material by journal and by hand. Added one.

It also found a fault in the mutation script itself: a same-length mutation (`all(` to `any(`) restored within the same second left Python running the stale bytecode of the mutant in later runs. The script now writes no bytecode and clears the caches after each restore.
