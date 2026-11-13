"""Build the GitHub Pages site in docs/: one static page, its sitemap, robots.txt and llms.txt.

    python3 scripts/build_site.py                  write the four files
    python3 scripts/build_site.py --check          exit 1 if any of them is stale, or any
                                                   guard in guards() fails
    uv run --with "playwright==1.63.0" --with pillow \\
        python scripts/build_site.py --shots build/demo
                                                   also render the page's pictures
                                                   from a demo round's pages

Everything a search engine or an answer engine reads (title, description,
canonical, Open Graph, the JSON-LD, the FAQ) comes from the constants below,
and the version and the sitemap date come from the package and the CHANGELOG,
never typed. The FAQ's JSON-LD is built from the same strings as the visible
questions, so the two cannot drift. No script loads from anywhere; the one
inline script only unhides the copy buttons.

Refuses (exit 2) when the version has no dated CHANGELOG heading, rather than
guess a date for the sitemap.
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"
SITE = "https://daredev256.github.io/cutreview/"
GITHUB = "https://github.com/DareDev256/cutreview"
BLOB = GITHUB + "/blob/main/"
PYPI = "https://pypi.org/project/cutreview/"
FCP_MCP = "https://github.com/DareDev256/fcp-mcp-server"
AUTHOR_URL = "https://jamesdare.com"

TITLE = "Cut Review: Frame.io comments to Final Cut Pro to-do markers"
DESCRIPTION = (
    "Turn Frame.io comments and client notes into Final Cut Pro to-do markers, "
    "then compare two FCPXML exports to see what changed. Free and open source."
)
H1 = "Frame.io comments and client notes as Final Cut Pro to-do markers"
DEFINITION = (
    "Cut Review is a free, open source command line tool and MCP server for Final Cut Pro. "
    "It writes client notes and Frame.io comment exports into your project's FCPXML as to-do markers on the clips they are about. "
    "After the recut it compares two FCPXML exports and shows, on one page, what changed and which notes the recut touched, "
    "whether you or an AI agent made the edit."
)
SOCIAL_CARD = "assets/social-card.png"
ICON_PNG = "assets/icon-512.png"
HERO_ALT = "The Cut Review status page: six notes, three done, four touched, and the two lists where the editor's tick and the cut disagree"
CHANGE_ALT = "The Cut Review change page: four changes, a timeline strip of the cut before and after, and before and after frames for each change"

# (question, answer as HTML). The JSON-LD gets the same text with the tags taken out.
FAQ = [
    ("How do I get Frame.io comments into Final Cut Pro?",
     "Export the comments from Frame.io as a CSV (in Frame.io V4: the three-dot menu in the Comments tab), then run "
     "<code>uvx cutreview notes cut.fcpxmld comments.csv</code> and import the result in Final Cut with File &gt; Import &gt; XML. "
     "Cut Review finds a Frame.io export by its Commenter and Comment columns, writes each comment as a to-do marker on the clip under it, "
     "folds replies into the comment they answer, and writes comments already marked complete as completed markers."),
    ("Does it work with Final Cut Pro 12.4?",
     "Yes. Final Cut Pro 12.4 imported the six to-do markers Cut Review wrote at the exact times and on the right clips, showed their note text "
     "in the Timeline Index, and wrote the editor's ticks into its XML export as completed markers. Cut Review read that export back as one trim, "
     "two notes ticked but untouched and one changed but not ticked, which is what happened. "
     f'The run, on test media, is <a href="{BLOB}docs/final-cut-proof.md">written up</a> and kept as a test.'),
    ("Does it work with Frame.io V4?",
     "Frame.io documents V4's comment export as CSV or plain text but publishes no column list. Cut Review reads the columns by name, "
     "never by position, and has been tested on a file rebuilt from the published V3-era names, not yet on a real V4 export. "
     f'If your export does not read, <a href="{GITHUB}/issues">open an issue</a> with its header row.'),
    ("How do I import a CSV of notes as Final Cut Pro markers?",
     "Any CSV with a header row works. Cut Review finds the time column by name (timecode, time, tc, in, start) and the note column likewise "
     "(note, comment, text, feedback), with an author column if there is one. <code>uvx cutreview notes cut.fcpxmld notes.csv</code> "
     "writes them as to-do markers. A row with no time is listed as not placed, never guessed."),
    ("How do I compare two FCPXML files and see what changed between two Final Cut exports?",
     "<code>uvx cutreview diff cut_v1.fcpxmld cut_v2.fcpxmld -o review.html</code> writes one HTML page listing every clip added, removed, "
     "trimmed, moved, retimed or adjusted, and every transition change, with a timeline strip and before and after frames. "
     "Clips are matched by source material, not by name, so a ripple, a head trim or a cut built on connected clips reads correctly."),
    ("How do I check what an AI agent changed in my edit?",
     "Run <code>cutreview diff</code> on the export before and after the agent worked. If the agent edited through "
     f'<a href="{FCP_MCP}">fcp-mcp-server</a>, <code>cutreview blame</code> names the tool call behind each change from that server\'s write journal, '
     "and marks anything done by hand as not in the journal. If your notes were on the cut, <code>cutreview status</code> shows which of them "
     "the agent's changes touched."),
    ("How do I track which client notes the recut dealt with?",
     "Put the notes on the cut as to-do markers with <code>cutreview notes</code>, tick them in Final Cut as you work, then run "
     "<code>cutreview status</code> on the next export. Each note comes back done or open (your tick) and touched or untouched "
     "(whether the cut changed within a second of it), and the page starts with the notes where those two disagree."),
    ("Is Cut Review a Frame.io alternative?",
     "No. It does not host video or collect comments from clients. It works on the notes you already get, from Frame.io, email, "
     "texts or a call, and on Final Cut's own XML exports."),
    ("Is there an MCP server for Final Cut Pro?",
     f'Yes: <a href="{FCP_MCP}">fcp-mcp-server</a> lets Claude and other MCP clients read and edit Final Cut Pro timelines through FCPXML. '
     "Cut Review is the review step beside it, as one MCP tool, <code>review</code>, with the actions diff, blame, notes and status."),
]

PRODUCTS = ["Cut Review", "Change List X", "Marker Toolbox", "Frame.io V4"]
COMPARE = [
    ("What it is", [
        "Free, open source command line tool and MCP server (MIT)",
        "Mac app, US$199.99",
        "Final Cut workflow extension, US$19.99",
        "Hosted review platform, free and paid plans"]),
    ("Notes into Final Cut as markers", [
        "Yes: plain text, any CSV, Frame.io comment CSV, as to-do markers on the clip",
        "No",
        "Yes: Frame.io FIOJSON (including the V4 beta), Vimeo, Wipster, Dropbox Replay, Premiere CSV, Timecode+, email text; resolved comments arrive completed",
        "Comment export as CSV or text; its V3 Import Comments into FCP article now redirects to the help center home"]),
    ("Compares two versions of the cut", [
        "Any two FCPXML exports, every lane, matched by source material",
        "Primary storylines of two projects, as a PDF or TSV change list with pull and discard lists",
        "No",
        "Plays two uploaded versions side by side or overlaid: the pictures, not the timeline's clips"]),
    ("Which notes the recut touched", [
        "Yes: done or open, against touched or untouched", "No", "No", "No"]),
    ("Which agent tool call made each change", [
        "Yes, from fcp-mcp-server's journal", "No", "No", "No"]),
]
COMPARE_SOURCES = [
    ("Change List X", "https://apps.apple.com/us/app/change-list-x/id694746044"),
    ("Marker Toolbox", "https://markertoolbox.fcp.cafe/"),
    ("Frame.io comment export", "https://help.frame.io/en/articles/9105309-comment-printing-and-comment-exporting"),
    ("Frame.io Comparison Viewer", "https://help.frame.io/en/articles/9952618-comparison-viewer"),
]
COMPARE_CHECKED = "2026-11-12"

# Search and answer engines first, then the AI crawlers. All are allowed.
BOTS = [
    "Googlebot", "Bingbot", "DuckDuckBot", "Applebot", "YandexBot",
    "OAI-SearchBot", "ChatGPT-User", "GPTBot",
    "Claude-SearchBot", "Claude-User", "ClaudeBot",
    "PerplexityBot", "Perplexity-User",
    "Google-Extended", "Applebot-Extended", "CCBot", "Meta-ExternalAgent", "Amazonbot", "cohere-ai",
]


def version() -> str:
    text = (REPO / "src" / "cutreview" / "__init__.py").read_text()
    m = re.search(r'__version__ = "([^"]+)"', text)
    if not m:
        raise SystemExit("refusing: no __version__ in src/cutreview/__init__.py")
    return m.group(1)


def released(ver: str) -> str:
    """The date on the CHANGELOG heading for this version. Refuses rather than guess."""
    m = re.search(rf"^## {re.escape(ver)} \((\d{{4}}-\d{{2}}-\d{{2}})\)", (REPO / "CHANGELOG.md").read_text(), re.M)
    if not m:
        print(f"refusing: CHANGELOG.md has no dated heading for {ver}; the sitemap date would be a guess", file=sys.stderr)
        raise SystemExit(2)
    return m.group(1)


def plain(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", fragment))


def json_ld(ver: str) -> str:
    graph = [
        {
            "@type": ["SoftwareApplication", "SoftwareSourceCode"],
            "@id": SITE + "#software",
            "name": "Cut Review",
            "alternateName": "cutreview",
            "description": DEFINITION,
            "url": SITE,
            "image": SITE + SOCIAL_CARD,
            "screenshot": SITE + "assets/status-desktop.webp",
            "applicationCategory": "MultimediaApplication",
            "applicationSubCategory": "Video editing review",
            "operatingSystem": "macOS",
            "softwareVersion": ver,
            "softwareRequirements": "Python 3.10 or newer; FCPXML exports from Final Cut Pro",
            "downloadUrl": PYPI,
            "installUrl": PYPI,
            "codeRepository": GITHUB,
            "programmingLanguage": "Python",
            "license": "https://opensource.org/licenses/MIT",
            "isAccessibleForFree": True,
            "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
            "featureList": [
                "Writes client notes and Frame.io comment CSV exports into FCPXML as Final Cut Pro to-do markers",
                "Reports each note as done or open, and touched or untouched by the recut",
                "Compares two FCPXML exports clip by clip, matched by source material",
                "Names the fcp-mcp-server tool call behind each change",
                "Runs as a command line tool and as an MCP server",
            ],
            "author": {"@id": AUTHOR_URL + "/#person"},
        },
        {
            "@type": "Person",
            "@id": AUTHOR_URL + "/#person",
            "name": "James Olusoga",
            "alternateName": "DareDev256",
            "url": AUTHOR_URL,
            "sameAs": ["https://github.com/DareDev256"],
        },
        {
            "@type": "FAQPage",
            "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": plain(a)}} for q, a in FAQ
            ],
        },
    ]
    return json.dumps({"@context": "https://schema.org", "@graph": graph}, indent=1, ensure_ascii=False).replace("</", "<\\/")


CSS = """
:root{--bg:#000;--fg:#f4f4f4;--muted:#9b9b9b;--faint:#5e5e5e;--line:#232323;--card:#0a0a0a;--accent:#00E5FF;--tint:rgba(0,229,255,.07);
--mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace}
*{box-sizing:border-box}
html{color-scheme:dark;background:var(--bg);-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--fg);font:17px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;-webkit-font-smoothing:antialiased}
a{color:var(--accent);text-underline-offset:3px}
:focus-visible{outline:2px solid var(--accent);outline-offset:3px;border-radius:4px}
.wrap{max-width:1080px;margin:0 auto;padding:0 16px}
@media(min-width:720px){.wrap{padding:0 32px}}
.top{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:20px 0}
.brand{display:flex;align-items:center;gap:10px;color:var(--fg);text-decoration:none;font-weight:700;letter-spacing:-.01em;font-size:18px}
.brand img{width:28px;height:28px;display:block}
.top nav{display:flex;gap:20px}
.top nav a{color:var(--muted);text-decoration:none;font-size:15px}
.top nav a:hover{color:var(--fg)}
h1{font-size:clamp(36px,6.4vw,66px);line-height:1.03;letter-spacing:-.04em;margin:44px 0 22px;max-width:19ch;text-wrap:balance}
.lede{font-size:clamp(18px,2.1vw,21px);line-height:1.55;max-width:60ch;margin:0 0 28px;color:var(--fg)}
.lede span{color:var(--muted)}
.cmd{display:flex;align-items:center;gap:12px;max-width:620px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 12px 12px 16px;font:15px/1.4 var(--mono)}
.cmd code{white-space:normal;flex:1;min-width:0;background:none;border:0;padding:0;font-size:inherit;overflow-wrap:normal}
.cmd .p{color:var(--accent);user-select:none}
.copy{margin-left:auto;flex:none;background:transparent;color:var(--fg);border:1px solid var(--line);border-radius:7px;padding:7px 11px;font:600 13px/1 system-ui,sans-serif;cursor:pointer}
.copy:hover{border-color:var(--accent)}
.verified{margin:-8px 0 24px;font-size:15px;color:var(--muted)}
.links{display:flex;flex-wrap:wrap;gap:8px 22px;margin:18px 0 0;font-size:16px}
figure{margin:0}
.shot{margin-top:48px;border:1px solid var(--line);border-radius:14px;overflow:hidden;background:var(--bg)}
.shot img{display:block;width:100%;height:auto}
.shot figcaption{font-size:14px;color:var(--muted);padding:12px 16px;border-top:1px solid var(--line)}
section{padding-top:80px}
h2{font-size:clamp(28px,3.6vw,40px);line-height:1.1;letter-spacing:-.03em;margin:0 0 14px;max-width:24ch;text-wrap:balance}
.sub{color:var(--muted);max-width:62ch;margin:0 0 28px}
h3{font-size:19px;line-height:1.3;letter-spacing:-.01em;margin:0 0 8px}
p{margin:0 0 14px}
.panels{display:grid;grid-template-columns:minmax(0,1fr);gap:16px}
@media(min-width:760px){.panels{grid-template-columns:repeat(2,minmax(0,1fr))}}
.panel{border:1px solid var(--accent);border-radius:12px;padding:22px 22px 10px}
.panel p{color:var(--muted)}
code{font-family:var(--mono);font-size:.88em;background:var(--card);border:1px solid var(--line);border-radius:5px;padding:1px 6px;overflow-wrap:anywhere}
pre{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:10px 0 16px;overflow-x:auto;font:14px/1.55 var(--mono)}
pre code{background:none;border:0;padding:0;font-size:inherit;overflow-wrap:normal}
ol.steps{list-style:none;counter-reset:s;padding:0;margin:0;display:grid;grid-template-columns:minmax(0,1fr);gap:22px;max-width:760px}
ol.steps>li{counter-increment:s;position:relative;padding-left:44px}
ol.steps>li::before{content:counter(s);position:absolute;left:0;top:-2px;width:30px;height:30px;border:1px solid var(--accent);border-radius:50%;
display:grid;place-items:center;font:600 14px/1 var(--mono);color:var(--accent)}
.grid{display:grid;grid-template-columns:minmax(0,1fr);gap:28px 40px}
@media(min-width:760px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
.grid p{color:var(--muted)}
ul.not{padding:0;margin:0;list-style:none;display:grid;gap:14px;max-width:760px}
ul.not li{padding-left:22px;position:relative;color:var(--muted)}
ul.not li::before{content:"";position:absolute;left:2px;top:.72em;width:9px;height:1px;background:var(--accent)}
ul.not b{color:var(--fg)}
.faq{max-width:780px}
.faq div{padding:22px 0;border-top:1px solid var(--line)}
.faq p{color:var(--muted);margin:0}
table{width:100%;border-collapse:collapse;font-size:15px;line-height:1.5}
th,td{text-align:left;vertical-align:top;padding:14px;border-top:1px solid var(--line)}
thead th{font:600 12px/1.3 var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--muted);border-top:0}
tbody th{font-weight:600;width:19%}
td{color:var(--muted)}
td.us,thead th.us{color:var(--fg);background:var(--tint)}
@media(max-width:760px){
 table,thead,tbody,tr,th,td{display:block;width:auto}
 thead{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
 tbody tr{border:1px solid var(--line);border-radius:12px;margin:0 0 14px;padding:4px 0 10px}
 tbody th{border:0;padding:14px 16px 6px;width:auto;font-size:17px}
 td{border:0;padding:6px 16px}
 td::before{content:attr(data-label);display:block;font:600 11px/1.4 var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--faint)}
 td.us{margin:0 8px;border-radius:8px;padding:8px}
}
.note{font-size:14px;color:var(--muted);margin-top:16px}
.visually-hidden{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.foot{margin-top:96px;padding:28px 0 56px;border-top:1px solid var(--line);color:var(--muted);font-size:15px;display:flex;flex-wrap:wrap;gap:8px 24px}
.foot a{color:var(--muted)}
.foot a:hover{color:var(--fg)}
"""


# The page's only script: it unhides the copy buttons. GitHub Pages cannot send
# headers, so the Content-Security-Policy rides in a meta tag, with this script
# allowed by its hash and everything else (other scripts, frames, forms,
# requests to any other host) refused.
SCRIPT = (
    'for(const b of document.querySelectorAll(".copy")){b.hidden=false;b.addEventListener("click",()=>'
    'navigator.clipboard.writeText(b.dataset.copy).then(()=>{b.textContent="Copied";setTimeout(()=>b.textContent="Copy",1500)}))}'
)


def csp() -> str:
    import base64
    import hashlib

    digest = base64.b64encode(hashlib.sha256(SCRIPT.encode()).digest()).decode()
    return (
        "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; "
        f"script-src 'sha256-{digest}'; base-uri 'none'; form-action 'none'"
    )

def page(ver: str) -> str:
    e = html.escape
    faq = "\n".join(f'<div><h3>{e(q)}</h3><p>{a}</p></div>' for q, a in FAQ)
    head_cells = "".join(f'<th scope="col"{" class=us" if i == 0 else ""}>{e(p)}</th>' for i, p in enumerate(PRODUCTS))
    rows = "\n".join(
        "<tr><th scope=\"row\">" + e(label) + "</th>"
        + "".join(f'<td data-label="{e(PRODUCTS[i])}"{" class=us" if i == 0 else ""}>{e(cell)}</td>' for i, cell in enumerate(cells))
        + "</tr>"
        for label, cells in COMPARE
    )
    sources = ", ".join(f'<a href="{u}">{e(n)}</a>' for n, u in COMPARE_SOURCES)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{csp()}">
<meta name="referrer" content="strict-origin-when-cross-origin">
<title>{e(TITLE)}</title>
<meta name="description" content="{e(DESCRIPTION)}">
<link rel="canonical" href="{SITE}">
<meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1">
<meta name="author" content="James Olusoga (DareDev256)">
<meta name="theme-color" content="#000000">
<meta name="color-scheme" content="dark">
<link rel="icon" href="favicon.svg" type="image/svg+xml">
<link rel="icon" href="{ICON_PNG}" type="image/png" sizes="512x512">
<link rel="apple-touch-icon" href="assets/apple-touch-icon.png">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Cut Review">
<meta property="og:title" content="{e(TITLE)}">
<meta property="og:description" content="{e(DESCRIPTION)}">
<meta property="og:url" content="{SITE}">
<meta property="og:image" content="{SITE}{SOCIAL_CARD}">
<meta property="og:image:type" content="image/png">
<meta property="og:image:width" content="1280">
<meta property="og:image:height" content="640">
<meta property="og:image:alt" content="Cut Review: client notes land in Final Cut as to-dos; after the recut, see which ones the cut changed">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{e(TITLE)}">
<meta name="twitter:description" content="{e(DESCRIPTION)}">
<meta name="twitter:image" content="{SITE}{SOCIAL_CARD}">
<link rel="preload" as="image" href="assets/status-desktop.webp" media="(min-width: 641px)" fetchpriority="high">
<link rel="preload" as="image" href="assets/status-phone.webp" media="(max-width: 640px)" fetchpriority="high">
<script type="application/ld+json">
{json_ld(ver)}
</script>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header class="top">
<a class="brand" href="{SITE}"><img src="favicon.svg" alt="" width="28" height="28">Cut Review</a>
<nav aria-label="Elsewhere"><a href="{GITHUB}">GitHub</a><a href="{PYPI}">PyPI</a></nav>
</header>
<main>
<h1>{e(H1).replace("Final Cut Pro", "Final&nbsp;Cut&nbsp;Pro")}</h1>
<p class="lede">{e(DEFINITION.split(". ", 1)[0])}. <span>{e(DEFINITION.split(". ", 1)[1])}</span></p>
<p class="verified">Verified on Final Cut Pro 12.4: to-do markers, their note text and the editor's ticks survive a <a href="{BLOB}docs/final-cut-proof.md">round trip</a>.</p>
<div class="cmd"><span class="p" aria-hidden="true">$</span><code>uvx cutreview notes cut.fcpxmld notes.txt</code><button class="copy" type="button" data-copy="uvx cutreview notes cut.fcpxmld notes.txt" hidden>Copy</button></div>
<p class="links"><a href="#quick-start">Quick start</a><a href="{GITHUB}">Source on GitHub</a><a href="{PYPI}">cutreview on PyPI</a><a href="#mcp">Use it from Claude</a></p>
<figure class="shot">
<picture>
<source media="(max-width: 640px)" srcset="assets/status-phone.webp" width="780" height="1520">
<img src="assets/status-desktop.webp" width="2560" height="1600" alt="{e(HERO_ALT)}" fetchpriority="high" decoding="async">
</picture>
<figcaption>The status page from the demo round, on synthesized test media. Every page Cut Review writes is one HTML file with nothing to load.</figcaption>
</figure>

<section aria-labelledby="disagree">
<h2 id="disagree">It starts where your tick and the cut disagree</h2>
<p class="sub">Each note comes back done or open, which is your tick in Final Cut, and touched or untouched, which is whether the cut changed within a second of it. The page leads with the two lists that need a second look.</p>
<div class="panels">
<div class="panel"><h3>Ticked but untouched</h3><p>Marked done in Final Cut, but nothing in the cut changed near it. The note may have needed no change, the fix may sit further away, or the tick came early.</p></div>
<div class="panel"><h3>Changed but not ticked</h3><p>The cut changed near it, but its to-do is still open. The change may have dealt with it and the tick was missed, or it was a change for something else.</p></div>
</div>
<p class="note">Cut Review says touched, never addressed. Whether a change is what the reviewer asked for stays your call.</p>
</section>

<section id="quick-start" aria-labelledby="qs">
<h2 id="qs">Quick start</h2>
<p class="sub">You need <a href="https://docs.astral.sh/uv/">uv</a> (<code>brew install uv</code>) and an XML export of your project from Final Cut Pro (File &gt; Export XML).</p>
<ol class="steps">
<li><h3>Write your notes, one per line, timecode first</h3>
<pre><code>00:00:05:00 Too long on B, cut it down
00:00:13:00 Drone could breathe, slow it down</code></pre></li>
<li><h3>Put them on the cut as to-do markers</h3>
<pre><code>uvx cutreview notes cut.fcpxmld notes.txt</code></pre>
<p>This writes <code>cut_notes.fcpxmld</code> and prints where each note landed. In Final Cut, File &gt; Import &gt; XML, then open the Timeline Index (Shift-Command-2) to see the to-dos.</p></li>
<li><h3>Recut, tick what you dealt with, export again</h3>
<p>Each to-do sits on its clip in that clip's own source time, so it moves with the clip when you trim or reorder.</p></li>
<li><h3>See which notes the recut touched, and what changed</h3>
<pre><code>uvx cutreview status cut_notes.fcpxmld cut_v2.fcpxmld -o status.html
uvx cutreview diff cut_notes.fcpxmld cut_v2.fcpxmld -o review.html</code></pre></li>
</ol>
</section>

<section aria-labelledby="does">
<h2 id="does">Four commands, one page each</h2>
<p class="sub">Notes are read by fixed rules you can read in the source. A note with no timecode is listed as not placed, never given a time, and a line that cannot be read is listed with the reason.</p>
<div class="grid">
<div><h3><code>cutreview notes</code></h3><p>Plain text with timecodes, any CSV, or a Frame.io comment CSV, written into the cut as to-do markers on the clip under each note. Every write is checked against Apple's FCPXML DTD and read back before it is kept.</p></div>
<div><h3><code>cutreview status</code></h3><p>Reads the next export and reports each note as done or open, touched or untouched. A note whose clip is gone reads removed with its clip.</p></div>
<div><h3><code>cutreview diff</code></h3><p>Any two exports, notes or not: every clip added, removed, trimmed, moved, retimed or adjusted, with a timeline strip and before and after frames. A clip that only slid with a ripple is counted, not listed.</p></div>
<div><h3><code>cutreview blame</code></h3><p>The same page with each change named by the <a href="{FCP_MCP}">fcp-mcp-server</a> tool call that made it. Work done by hand reads not in the journal.</p></div>
</div>
<figure class="shot">
<picture>
<source media="(max-width: 640px)" srcset="assets/review-phone.webp" width="780" height="1520">
<img src="assets/review-desktop.webp" width="2560" height="1600" alt="{e(CHANGE_ALT)}" loading="lazy" decoding="async">
</picture>
<figcaption>The change page from the same demo round.</figcaption>
</figure>
</section>

<section aria-labelledby="not">
<h2 id="not">What it is not</h2>
<ul class="not">
<li><b>Not a review platform.</b> There is no server, no account and no upload. Every page is one HTML file on your disk.</li>
<li><b>Not a judge of the edit.</b> It says touched, never addressed.</li>
<li><b>No AI in the notes path.</b> Notes are placed by rules, and a note it cannot place is listed, never guessed.</li>
<li><b>Not an editor.</b> It writes markers and nothing else. It never changes a clip, and it never opens or drives Final Cut.</li>
</ul>
</section>

<section aria-labelledby="faq">
<h2 id="faq">Questions</h2>
<div class="faq">
{faq}
</div>
</section>

<section aria-labelledby="compare">
<h2 id="compare">How it compares</h2>
<p class="sub">Use Change List X when you need a conform change list for sound or VFX, in feet and frames, with pull and discard lists. Use Marker Toolbox when your notes come from Vimeo, Wipster, Dropbox Replay or Frame.io's FIOJSON download, or when you want drawn annotations brought across. Cut Review is for the step after the notes are on the cut: knowing which ones the recut actually changed.</p>
<table>
<thead><tr><th scope="col"><span class="visually-hidden">Feature</span></th>{head_cells}</tr></thead>
<tbody>
{rows}
</tbody>
</table>
<p class="note">Read from each product's own page on {COMPARE_CHECKED}: {sources}. Prices are the US Mac App Store's.</p>
</section>

<section id="mcp" aria-labelledby="mcph">
<h2 id="mcph">Use it from Claude</h2>
<p class="sub">Cut Review is also an MCP server with one tool, <code>review</code>, and the actions diff, blame, notes and status. Every file it writes stays inside the folder of the cut it was given. Its name in the official MCP registry is <code>io.github.DareDev256/cutreview</code>.</p>
<pre><code>claude mcp add cutreview -- uvx cutreview mcp</code></pre>
<p>For Claude Desktop and other clients that take a JSON config:</p>
<pre><code>{{"mcpServers": {{"cutreview": {{"command": "uvx", "args": ["cutreview", "mcp"]}}}}}}</code></pre>
<p>It pairs with <a href="{FCP_MCP}">fcp-mcp-server</a>, which lets Claude read and edit Final Cut Pro timelines.</p>
</section>
</main>

<footer class="foot">
<span>Cut Review {e(ver)}, MIT license</span>
<span>Made by <a href="{AUTHOR_URL}">James Olusoga (DareDev256)</a></span>
<a href="{GITHUB}">Source</a>
<a href="{GITHUB}/issues">Issues</a>
<a href="{BLOB}CHANGELOG.md">Changelog</a>
<a href="llms.txt">llms.txt</a>
</footer>
</div>
<script>{SCRIPT}</script>
</body>
</html>
"""


def sitemap(date: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{SITE}</loc>
    <lastmod>{date}</lastmod>
  </url>
</urlset>
"""


def robots() -> str:
    named = "\n".join(f"User-agent: {b}" for b in BOTS)
    return f"""# Cut Review welcomes every search engine, answer engine and AI crawler.
# Note: crawlers read robots.txt only at a host's root, and this file sits under /cutreview/.
# A missing robots.txt at daredev256.github.io/ is read by crawlers as allow all.

User-agent: *
Allow: /

{named}
Allow: /

Sitemap: {SITE}sitemap.xml
"""


def llms(ver: str) -> str:
    faq = "\n".join(f"- {q} {plain(a)}" for q, a in FAQ)
    return f"""# Cut Review

> {DEFINITION}

- Package: `cutreview` on PyPI, version {ver}. Run with `uvx cutreview`. Python 3.10 or newer. MIT license.
- Author: James Olusoga (DareDev256), {AUTHOR_URL}
- Commands: `notes` (notes in as to-do markers), `status` (each note done or open, touched or untouched), `diff` (what changed between two exports), `blame` (which fcp-mcp-server tool call made each change), `mcp` (MCP server over stdio, one tool `review`).
- Reads: plain text notes with timecodes, any CSV with a header row, Frame.io comment CSV exports (columns read by name; not yet tested on a real Frame.io V4 export).
- Writes: FCPXML with to-do markers (checked against Apple's FCPXML DTD when Final Cut Pro is installed), and one self-contained HTML page per report.
- It is not a review platform (no server, no account, no upload), it says "touched" and never "addressed", there is no AI in the notes path, and it never changes a clip.
- Verified on Final Cut Pro 12.4: to-do markers, their note text and the editor's ticks survive a round trip (run once, on test media with one trim; {BLOB}docs/final-cut-proof.md).
- Limits: Final Cut Pro only (Resolve and Premiere wait for a later version); clips inside compound clips are not looked into; a speed ramp is read as one average speed.

## Docs

- [Website]({SITE}): what it does, quick start, questions, comparison
- [README]({GITHUB}#readme): full reference for every command and format
- [DECISIONS.md]({BLOB}DECISIONS.md): why it works the way it does, with sources
- [CHANGELOG.md]({BLOB}CHANGELOG.md)
- [PyPI]({PYPI})

## Questions

{faq}

## Related

- [fcp-mcp-server]({FCP_MCP}): an MCP server that lets Claude read and edit Final Cut Pro timelines through FCPXML. Cut Review reads its write journal for `blame`.
"""


def files() -> dict[str, str]:
    ver = version()
    return {
        "index.html": page(ver),
        "sitemap.xml": sitemap(released(ver)),
        "robots.txt": robots(),
        "llms.txt": llms(ver),
    }


TRACKERS = ("googletagmanager", "google-analytics", "gtag(", "plausible", "clarity.ms", "facebook.net", "segment.com", "hotjar")


def disk_texts() -> dict[str, str]:
    return {
        "index": (DOCS / "index.html").read_text(),
        "robots": (DOCS / "robots.txt").read_text(),
        "readme": (REPO / "README.md").read_text(),
        "server": (REPO / "server.json").read_text(),
        "pyproject": (REPO / "pyproject.toml").read_text(),
    }


def guards(t: dict[str, str]) -> list[str]:
    """Every way the published surfaces can quietly go wrong. Empty means all hold."""
    ver = version()
    bad = []
    if not 10 <= len(TITLE) <= 65:
        bad.append(f"title is {len(TITLE)} characters; search results cut it past 65")
    if not 50 <= len(DESCRIPTION) <= 160:
        bad.append(f"description is {len(DESCRIPTION)} characters; keep it 50 to 160")
    page_ = t["index"]

    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', page_, re.S)
    try:
        graph = json.loads(blocks[0])["@graph"] if len(blocks) == 1 else None
    except (ValueError, KeyError):
        graph = None
    if graph is None:
        bad.append("index.html needs exactly one JSON-LD block that parses, with an @graph")
        graph = []
    soft = next((n for n in graph if "SoftwareApplication" in n.get("@type", [])), {})
    if soft.get("softwareVersion") != ver:
        bad.append(f"JSON-LD softwareVersion {soft.get('softwareVersion')!r} is not the package version {ver}")
    if soft.get("offers", {}).get("price") != "0" or soft.get("codeRepository") != GITHUB:
        bad.append("JSON-LD lost its free offer or its codeRepository")
    faq_ld = [q["name"] for n in graph if n.get("@type") == "FAQPage" for q in n.get("mainEntity", [])]
    faq_seen = [html.unescape(q) for q in re.findall(r'<div><h3>(.*?)</h3><p>', page_.split('<div class="faq">', 1)[-1].split("</section>", 1)[0])]
    if not faq_ld or faq_ld != faq_seen:
        bad.append(f"FAQ JSON-LD ({len(faq_ld)} questions) does not match the questions on the page ({len(faq_seen)})")

    for ref in re.findall(r'(?:src|href|srcset)="([^"]+)"', page_):
        if ref.startswith(("http://", "https://", "#", "mailto:")):
            continue
        if not (DOCS / ref.split("#")[0].split("?")[0]).is_file():
            bad.append(f"index.html points at {ref}, which is not in docs/")
    for url in re.findall(r'"(' + re.escape(SITE) + r'[^"#?]+)"', page_):
        if not (DOCS / url[len(SITE):]).is_file():
            bad.append(f"{url} would 404: no such file in docs/")
    if re.search(r"<script[^>]+src=", page_) or re.search(r'<link[^>]+rel="stylesheet"', page_):
        bad.append("index.html loads a script or stylesheet; the page must load nothing but its own pictures")
    if f'content="{csp()}"' not in page_ or f"<script>{SCRIPT}</script>" not in page_:
        bad.append("the Content-Security-Policy meta is missing, or does not hash the script on the page")
    if any(tr in page_ for tr in TRACKERS):
        bad.append("index.html carries a tracker")
    if f'<link rel="canonical" href="{SITE}">' not in page_:
        bad.append("canonical is missing or not the live URL")

    for line in t["robots"].splitlines():
        key, _, val = line.partition(":")
        if key.strip().lower() == "disallow" and val.strip():
            bad.append(f"robots.txt disallows {val.strip()}")
    if f"Sitemap: {SITE}sitemap.xml" not in [ln.strip() for ln in t["robots"].splitlines()]:
        bad.append("robots.txt has no Sitemap line for the live sitemap")

    if f'Homepage = "{SITE}"' not in t["pyproject"]:
        bad.append("pyproject.toml Homepage is not the site")
    try:
        server = json.loads(t["server"])
    except ValueError:
        server = {}
        bad.append("server.json does not parse")
    if server.get("websiteUrl") != SITE:
        bad.append("server.json websiteUrl is not the site")
    if server.get("version") != ver or any(pk.get("version") != ver for pk in server.get("packages", [])):
        bad.append(f"server.json versions are not {ver}")
    for icon in server.get("icons", []):
        if not icon["src"].startswith(SITE) or not (DOCS / icon["src"][len(SITE):]).is_file():
            bad.append(f"server.json icon {icon['src']} is not a file the site serves")
    if f"<!-- mcp-name: {server.get('name')} -->" not in t["readme"]:
        bad.append("README has no mcp-name line matching server.json; the registry will refuse the package")

    raw = f"https://raw.githubusercontent.com/DareDev256/cutreview/v{ver}/"
    for img in re.findall(r"!\[[^\]]*\]\(([^)\s]+)\)", t["readme"]):
        if "img.shields.io" in img:
            continue
        if not img.startswith(raw):
            bad.append(f"README image {img} is not pinned to v{ver}; PyPI shows it broken")
        elif not (REPO / img[len(raw):]).is_file():
            bad.append(f"README image {img} has no file at that path")
    if SITE not in t["readme"]:
        bad.append("README does not link the site")

    card = DOCS / SOCIAL_CARD
    if not card.is_file() or card.read_bytes()[16:24] != (1280).to_bytes(4, "big") + (640).to_bytes(4, "big"):
        bad.append(f"{SOCIAL_CARD} is missing or not 1280x640")
    return bad


def shots(round_dir: Path) -> None:
    """Render the page's four pictures from a demo round's status and review pages, at 2x, as WebP."""
    import io

    from PIL import Image
    from playwright.sync_api import sync_playwright

    out = DOCS / "assets"
    out.mkdir(parents=True, exist_ok=True)
    jobs = [("status", "desktop", 1280, 800), ("status", "phone", 390, 760), ("review", "desktop", 1280, 800), ("review", "phone", 390, 760)]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, kind, w, h in jobs:
            src = round_dir / f"{name}.html"
            if not src.is_file():
                raise SystemExit(f"refusing: {src} not found; run scripts/make_demo.py first")
            page_ = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=2, color_scheme="dark")
            page_.goto(src.resolve().as_uri())
            page_.wait_for_load_state("load")
            png = page_.screenshot()
            page_.close()
            target = out / f"{name}-{kind}.webp"
            Image.open(io.BytesIO(png)).convert("RGB").save(target, "WEBP", quality=82, method=6)
            print(f"{target.relative_to(REPO)}  {w * 2}x{h * 2}  {target.stat().st_size // 1024} KB")
        browser.close()


def main(argv: list[str]) -> int:
    if "--shots" in argv:
        i = argv.index("--shots")
        if i + 1 >= len(argv):
            print("usage: build_site.py --shots ROUND_DIR", file=sys.stderr)
            return 2
        shots(Path(argv[i + 1]))
    built = files()
    if "--check" in argv:
        stale = [name for name, text in built.items() if not (DOCS / name).is_file() or (DOCS / name).read_text() != text]
        problems = (["stale, rebuild with scripts/build_site.py: " + ", ".join(stale)] if stale else []) + guards(disk_texts())
        if problems:
            print("site check failed:\n  " + "\n  ".join(problems), file=sys.stderr)
            return 1
        print("docs/ site is current; title, description, JSON-LD, FAQ, links, robots, registry and README images all hold")
        return 0
    for name, text in built.items():
        (DOCS / name).write_text(text)
        print(f"docs/{name}  {len(text.encode())} bytes")
    nojekyll = DOCS / ".nojekyll"
    if not nojekyll.exists():
        nojekyll.write_text("")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
