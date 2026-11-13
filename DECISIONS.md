# Decisions

Kept from day one so the reasons survive. Newest decisions go at the bottom of the log.

Sources in brackets: `[plan]` is the research plan that chose this tool (fable-plan.md: §2.5 checklist, §3.2 candidate A, §3.3 scores, §3.4 answers, §3.6 and §3.7), `[missing]` is its survey of what editors lack (missing.md, needs 1 and 2). Both are the author's research notes, kept outside this repo; the editor quotes they cite are linked in them to the original Reddit, Hacker News and Frame.io pages. `[built]` is something measured in this repo while building v0.1.

## The ten pre-build questions

Questions 2, 3 and 6 may not fail.

### 1. Chore: can I say the job in one sentence an editor would say, with no "AI" in it?

"Put the client's notes on the cut as to-dos, and after the recut show me which ones the cut actually changed."

Editors wrote both halves themselves. "Frame.io going nuts with more than 300 notes on a 90 min film" and "It's become impossible to search the comments" (r/premiere); "didn't realise that you can no longer drag and drop comments via the extension" (r/finalcutpro, with Frame.io support confirming V4 does not support Final Cut). For the agent half: a reviewer of Adobe's Creative Agent "would also like to know where it moved everything" `[missing needs 1, 2]`.

**Pass.**

### 2. File: is there a documented format I can read and write today with nobody's permission?

FCPXML. Apple's own definition ships inside Final Cut Pro, and `marker` carries `completed` ("0=not completed, 1=completed") and `note` in FCPXMLv1_13.dtd and FCPXMLv1_14.dtd `[plan §3.4 check T2]`. Read here from `/Applications/Final Cut Pro.app/Contents/Frameworks/Interchange.framework/Versions/A/Resources/FCPXMLv1_13.dtd`, lines 686 to 691 `[built]`. Markers are children of clips in the clip's source time, so they travel with the clip through a recut. Every file cutreview writes is validated with `xmllint` against that DTD before it is kept `[built]`.

**Pass.**

### 3. Owner: will Apple, or the biggest vendor beside the format, ship this within a year?

No, for two reasons. Apple has added no new automation surface to Final Cut in six releases `[plan §2.5, row 3]`. The vendor beside it, Frame.io, went the other way: V4 dropped the Final Cut round trip and returns only an EDL to Resolve `[missing need 1]`. Each NLE vendor that ships an agent logs its edits only inside its own app `[missing need 2]`.

**Pass.** Watch item: §3.7 trigger 1 (Frame.io restores the round trip) narrows the notes door.

### 4. Lane: fewer than three maintained tools doing this exact job?

| Tool | What it does | Stars, last push | Why it is not this |
|---|---|---|---|
| Marker Toolbox | Final Cut marker utility, €23 | paid app | Imports markers; does not report touched against done `[missing need 1]` |
| vit | "Git for video editing" | 739, 2026-09-01 | Resolve only, merge oriented `[plan §3.2 A]` |
| Shumai | review server | 261 | Rebuilds Frame.io in Docker `[missing need 1]` |
| clapshot | review server | 269 | Same `[plan §3.2 A]` |
| Kino (YC) | review product | n/a | Hosted platform `[plan §3.2 A]` |
| three `cutnotes` repos | unknown | 0 each, since 2026-10-29 | By their descriptions none writes notes into the timeline `[plan §3.2 A, check T7]` |

None joins notes in, markers on the cut, and touched against done out.

**Pass.**

### 5. Refusal: what will this tool refuse to do that the louder rival has to do?

Not a review platform. No server, no accounts, no upload. It says "touched", never "addressed". No AI in the notes path. It refuses to guess a time for a note with no timecode, and refuses to keep a marked file that fails Apple's DTD or that its own read-back cannot place `[plan §3.4 A row 5]` `[built: tests/test_markers.py]`. README opens with the full list.

**Pass.**

### 6. Truth: what is the host's ground truth, and do I hold one real project before the first commit, at no cost per test?

Ground truth is Final Cut's own export: the `completed` flag it writes when the editor ticks a to-do, and the clips as it writes them. Final Cut 12.4 is installed on this Mac, so every test of a round trip costs nothing `[plan §3.4 A row 6]`.

Held before the first commit: two fixture cuts from fcp-mcp-server (a gap-based music video and a spine-based interview) and a demo cut on synthesized media, each with a second version produced by fcp-mcp-server's own journaled operations `[built: scripts/scenarios.py, scripts/make_demo.py]`.

Held since 2026-11-12, 23:58: **the Final Cut round trip.** Final Cut Pro 12.4 imported the marked demo cut with all six to-dos on the right clips at the exact times, kept and showed each note, wrote the editor's two ticks back as `completed="1"`, and exported FCPXML 1.14. That export is kept byte for byte in `tests/fixtures/fcp-12.4-roundtrip/` and `tests/test_fcp_roundtrip.py` asserts the exact result on every run, at no cost `[built: docs/final-cut-proof.md, Result]`. The first read of it failed (every note "removed with its clip"), which is the reason to hold the host's truth before launch: it found that cutreview named sources in a way Final Cut's export breaks (log, 2026-11-13).

Still open, and named here so they stay open:

- **A real Frame.io comment export.** No current header list is published. The importer reads columns by name, from the V3-era names users quote (see the log, 2026-11-12). Closed when one real export reads correctly.
- **A real project of the author's with two exports and a notes file he writes himself** `[plan §3.6 done when]`. The round trip above used ffmpeg test media and one hand edit.

**Pass on the host's ground truth**, which is what this question guards: Final Cut's own export, read correctly, in the suite. The two items above are proof of reach (real footage, Frame.io's real columns) and stay open until each is closed.

### 7. Finder: what does someone type into Google, and is it in the name or the first line?

"frame.io comments to final cut markers", "compare two timelines", "Git for video editing" `[plan §3.4 A row 7]`. The name `cutreview` holds "cut" and "review".

Rechecked for the launch plan (2026-11-12), one phrase set per audience (the launch plan, §1; kept outside this repo with the author's research notes): editors with clients type "import frame.io comments into final cut pro"; people letting an agent edit type "compare two fcpxml files" or "what changed between two final cut timelines"; builders type "fcpxml diff" or "final cut pro mcp server". The README's first line now reads "Client notes and Frame.io comments in as Final Cut Pro to-do markers. Then compare two FCPXML exports of the timeline on one page: what changed, and which notes the recut touched, whether you or an agent made the edit." The package description carries the same phrases (see the log, 2026-11-12, launch metadata).

**Pass.**

### 8. Proof: can ten seconds of real footage show it working?

Two versions side by side with the changed ranges lit, and the status page leading with the two disagreements `[plan §3.4 A row 8]`. The demo pages in `docs/screenshots/` are on synthesized media (ffmpeg test sources) so they can be published; the launch GIF needs real footage.

**Pass** for the page; the GIF waits on the real project from question 6.

### 9. Size: a v0.1 in two weeks, useful alone, about six verbs, two dependencies?

Four verbs (`diff`, `blame`, `notes`, `status`) plus `mcp`. Two direct dependencies: `fcp-mcp-server==0.30.0` and `mcp`. The floor, "two files in, one review page out", is `cutreview diff` `[plan §3.6]` `[built]`.

**Pass.**

### 10. Tailwind: does each vendor release make this more needed, or less?

More. Resolve 21.1 ships an MCP, Premiere's assistant has one due in early 2027, and every one of them produces agent edits someone has to check `[plan §3.1, §3.5 reason 3]`. The one release that would make it less needed is Frame.io restoring the Final Cut round trip, and that only narrows the notes door `[plan §3.7]`.

**Pass.**

## Decision log

**2026-11-12. Its own repo, fcp-mcp-server as a pinned library.** Pinned to `fcp-mcp-server==0.30.0` from PyPI, never the working tree. cutreview uses its parser, its element walker (`FCPXMLModifier`: spine, connected clips, anchored offsets, timeline origin), its marker builder (`build_marker_element`, which inserts in DTD order), its DTD locator and validator (`fcpxml.dtd`), its journal format (`fcpxml.journal`), its `_compare_format`, and its MCP 1.x/2.x probe (`fcpxml.mcp_compat`). Reason: a file fcp-mcp-server wrote should read back here the way it meant it `[plan §3.6, decision 1]`.

**2026-11-12. Changes are matched on source material, not on (name, in-point).** `fcpxml.diff.compare_timelines` reads three common edits wrong, each measured in `tests/test_changes.py::test_why_not_diff_py`: a gap-based cut (all clips connected) reports no clip changes; a head trim reads as removed plus added; a ripple trim reads every later clip as moved. So clips are paired by overlapping source range per asset, material order on the primary storyline is checked by the longest run kept in order, and a connected clip is judged against its own host's material. A clip that only slid with a ripple is counted on the page ("7 clips only slid") and is not a change.

**2026-11-12. "Touched" is one rule.** A note is touched when a change lies within *reach* (default one second) of the note's frames on the earlier cut's timeline, or of its marker on the later cut's timeline. A change on an audio lane touches only notes that sit on audio. The first version also matched on the note's source range; the mutation run showed that branch never decided a case the timeline window did not already decide, so it was removed rather than kept untested.

**2026-11-12. Note identity is `#N` at the start of the marker name.** The full text, author and origin go in the marker's `note` attribute on one line (XML folds a newline inside an attribute into a space). Status finds the marker in the next export by `#N` on the same source, then by exact name on the same source frame. IDs continue after the highest `#N` already in the file.

**2026-11-12. Version 1.13 by default.** The 1.13 DTD fixes `version="1.13"`, so a 1.10 or 1.11 input is written as 1.13; a 1.14 input stays 1.14. An input that is already not DTD-valid (fcp-mcp-server's `examples/sample.fcpxml`) is written only when cutreview adds no new error, and the summary says so.

**2026-11-12. Frame.io columns by name, never by position.** Header names come from two V3-era sources: a SoundFlow forum thread naming "Timecode" and "Timecode Source" (2022-12-06, https://forum.soundflow.org/-9007/) and the 20-field row read positionally in adamhawkey/EDL_tools (`Frameio_csv_MarkerList_to_NucodaEDL.py`, last push 2022-12-07). Frame.io's V4 help describes the export menu, not the columns (https://help.frame.io/en/articles/9105309-comment-printing-and-comment-exporting). `fixtures/sample.frameio.csv` is a reconstruction from those names, labelled as such. Replies (a row with a reply and no comment) are folded into the comment above; this is unverified against a real export.

**2026-11-12. Timecodes count from the sequence start.** One automatic adjustment, made for a whole file and printed: when the sequence starts at zero, the cut is under an hour and every note reads past 01:00:00:00, an hour comes off each (a review copy exported with an hour start). `--start-tc` overrides.

**2026-11-12. Frames are source frames.** Before and after frames come from the source media at the instant shown, labelled in HTML. Effects, titles and grades are not drawn, and the page says so. Media that cannot be read is named as offline; no placeholder image is drawn.

**2026-11-12. The fixtures' second versions and journals are generated, not committed.** The journal records absolute paths, so `scripts/scenarios.py` rebuilds both rounds through `server.call_tool` on every test run (journal in the round's own folder, autopush and the index cache forced off).

**2026-11-12. Launch metadata, proposed in the launch plan (kept outside this repo) and applied on the launch day.** PyPI summary: "Client notes and Frame.io comments in as Final Cut Pro to-do markers. Compare two FCPXML exports: what changed, and which notes it touched." GitHub description: "Client notes and Frame.io comments in as Final Cut Pro to-do markers. Compare two FCPXML exports: what changed, and which notes the recut touched. CLI and MCP tool. No server, no upload." GitHub topics (16): final-cut-pro, finalcutpro, fcpx, fcpxml, fcpxml-diff, timeline-diff, frameio, video-review, client-feedback, markers, video-editing, post-production, mcp, mcp-server, model-context-protocol, python; `frameio` over `frame-io` because 11 repos use it against 2 (`gh api search/repositories?q=topic:<t>`, 2026-11-12). MCP registry name `io.github.DareDev256/cutreview`, description 91 of the registry's 100 characters, in `server.json`; the registry checks a PyPI package's ownership by the `mcp-name` line at the end of the README. If a real Frame.io V4 export has not been read correctly by launch day, "Frame.io" comes out of the GitHub description and the posts and stays only in the README with its caveat (launch plan §7).

**2026-11-13. Search and answer-engine pack (James: "SEO through the roof").** Phrase demand was read from Google's autocomplete (the public suggest endpoint, en-US) and web searches on 2026-11-12. Real completions: "frame io final cut pro", "frame.io final cut extension", "frame.io final cut plugin", "frame io export comments", "frame io import comments", "final cut pro markers", "final cut pro export markers", "final cut pro mcp server", "final cut pro mcp claude", "frame io alternative open source". None for "fcpxml diff", "compare fcpxml" or "final cut pro compare two projects": little demand, and no one holding them. So the lead phrase is Frame.io comments into Final Cut Pro as to-do markers, and it leads the README title and first sentence, the PyPI summary, the site title, H1 and description, and the registry description; the diff and agent phrases live in FAQ headings, where answer engines lift question and answer pairs. Frame.io stays in that copy with its caveat stated on the page and in the README FAQ (columns read by name; not yet a real V4 export). Frame.io's help center (updated 2026-09-09) documents V4 comment export as CSV or plain text, and its V3 "Import Comments into FCP" article now redirects to the help center home. The rule above that keeps Frame.io out of the GitHub description until a real export reads is unchanged; the description is set on the day, with or without it. Rivals read from their own pages: Change List X (US$199.99, primary storylines, PDF or TSV change list, pull and discard lists); Marker Toolbox (US$19.99, Frame.io FIOJSON including the V4 beta and five other review formats, resolved comments arrive completed, FCP 10.6.5 or later). Marker Toolbox already brings notes in as completed markers, so the comparison leads with what neither does: which notes the recut touched. PyPI: no `License :: OSI Approved :: MIT License` classifier, because the package declares `license = "MIT"` (an SPDX License-Expression) and PEP 639 has PyPI refuse an upload that carries both; PyPI shows the expression instead. The site is a project site under daredev256.github.io/cutreview/, so its robots.txt and sitemap sit under /cutreview/, where crawlers do not look for robots.txt (they read only the host root, which is missing, which they treat as allow all). A host the project owns (a custom domain, or the account's user site) would put robots.txt and the sitemap where crawlers read them; that is a choice for launch day. `scripts/build_site.py` builds the page, sitemap, robots.txt and llms.txt from one set of constants, the package version and the CHANGELOG date, and `--check` refuses a stale page and 15 kinds of drift (title or description length, JSON-LD that does not parse or carries another version, FAQ JSON-LD that differs from the visible questions, a picture or card that would 404, any loaded script, stylesheet or tracker, the canonical, robots blocking anything or losing its Sitemap line, the PyPI homepage, server.json's site, versions and icon, the README's mcp-name line, and README images not pinned to the release tag); each was broken on purpose and seen to fail.

**2026-11-13. A source is named by its media file, never by its resource id.** The first Final Cut round trip read as 16 changes and every note "removed with its clip". Final Cut rewrites every asset on export: it renumbers resource ids (a2 becomes r2), adds `uid` and a `media-rep sig`, drops `start="0s"` on clips, drops `format` on asset-clips and reorders attributes. cutreview had preferred `uid` over the media path, and the file it wrote had no `uid`, so nothing matched. Now each clip carries every name its source has, strongest first (the media file path, normalised from its URL; then `uid`; then `sig`; the asset's name only when it has none of these), and `changes.unify_sources` joins those names across both files, so a file relinked between exports still matches through its `uid`. A group of names is always called by its strongest member, so blame's step-by-step diffs agree with the whole diff. A missing `start` reads as zero. Not handled: a file both relinked and without a `uid` on either side (no shared name to join on); it reads as removed and added. Measured on the real export in `tests/test_fcp_roundtrip.py`; keying by resource id again, or skipping the join, fails it (`scripts/mutate.py`).

**2026-11-13. Published.** Public repo github.com/DareDev256/cutreview, PyPI `cutreview` 0.1.0, the MCP registry entry `io.github.DareDev256/cutreview` 0.1.0, and the site at daredev256.github.io/cutreview/ (Pages from `docs/` on main). Before the first push, history was rewritten with git filter-repo to drop the launch plan (drafts and private footage notes; now kept outside the repo) and the raw Final Cut round-trip fixtures (this machine's paths and macOS bookmarks); the fixtures came back sanitized, each edit listed in their README, and the whole history was scanned for paths, names, emails, phone numbers and tokens with nothing found beyond the commit author line. The GitHub description leaves Frame.io out, per the rule above, until a real V4 export reads. The site keeps the host-root warnings for now: a project site cannot own daredev256.github.io/robots.txt, and crawlers read a missing one as allow all. To own the root later: a CNAME record `cutreview` to `daredev256.github.io` on jamesdare.com (Cloudflare, DNS only so GitHub can issue the certificate), then the custom domain set on the repo's Pages, which redirects the github.io address to it; then `SITE` in `scripts/build_site.py`, the PyPI Homepage and `server.json`'s websiteUrl move with it. The page carries its Content-Security-Policy as a meta tag because Pages sends no headers but HSTS.
