"""Build a review round on real, synthesized media, and render its three pages.

    python scripts/make_demo.py build/demo

Makes five short clips with ffmpeg's built-in test sources (no footage, no
text burned in), a cut that references them in the shape Final Cut exports
(start timecode 01:00:00:00, assets with media-rep), notes in plain text,
an agent pass through fcp-mcp-server's journaled operations, the editor's
ticks, and then diff, blame and status pages with before and after frames.
Everything lands under the folder given; nothing is pushed anywhere.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scenarios  # noqa: E402

W, H, FPS = 1280, 720, 24
SOURCES = {
    "Interview_Maya": f"gradients=s={W}x{H}:r={FPS}:c0=0x0b3d91:c1=0xff6a3d:c2=0x111111:speed=0.03",
    "Broll_Street": f"mandelbrot=s={W}x{H}:r={FPS}:end_scale=0.05",
    "Broll_Studio": f"colorchart=rate={FPS}:patch_size=96x96:preset=reference,scale={W}:{H}:flags=neighbor",
    "Drone_Bay": f"zoneplate=s={W}x{H}:r={FPS}:kt2=2:kx2=60:ky2=60",
    "Logo_Bars": f"smptehdbars=s={W}x{H}:r={FPS}",
}


def make_media(folder: Path) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    out = {}
    for name, src in SOURCES.items():
        path = folder / f"{name}.mp4"
        if not path.exists():
            subprocess.run([
                "ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi", "-i", src,
                "-t", "40" if name == "Interview_Maya" else "20", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "28",
                str(path)], check=True)
        out[name] = path
    music = folder / "Music_Bed.m4a"
    if not music.exists():
        subprocess.run([
            "ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi",
            "-i", "sine=frequency=220:duration=60", "-c:a", "aac", "-b:a", "96k", str(music)], check=True)
    out["Music_Bed"] = music
    return out


def cut_xml(media: dict) -> str:
    def asset(i, name, video=True):
        p = media[name].resolve().as_uri()
        dur = "60s" if name == "Music_Bed" else ("40s" if name == "Interview_Maya" else "20s")
        fmt = ' format="r1"' if video else ""
        hv = "1" if video else "0"
        return (f'<asset id="a{i}" name="{name}" start="0s" duration="{dur}" hasVideo="{hv}" hasAudio="{0 if video else 1}"'
                f'{fmt}><media-rep kind="original-media" src="{p}"/></asset>')

    names = ["Interview_Maya", "Broll_Street", "Broll_Studio", "Drone_Bay", "Logo_Bars"]
    assets = "".join(asset(i, n) for i, n in enumerate(names, 2)) + asset(7, "Music_Bed", video=False)
    # Spine on the 01:00:00:00 clock, as Final Cut writes it.
    clips = [
        ("a2", "Interview Open", 0, 2, 6),
        ("a3", "Street Wide", 6, 0, 4),
        ("a2", "Interview Answer", 10, 12, 8),
        ("a4", "Studio Detail", 18, 3, 3),
        ("a5", "Drone Reveal", 21, 0, 5),
        ("a6", "Logo", 26, 2, 3),
    ]
    spine = []
    for ref, name, off, start, dur in clips:
        inner = ""
        if name == "Interview Answer":
            # A connected clip's offset is on its parent's local clock, which begins at the parent's start.
            inner = (f'<asset-clip ref="a3" lane="1" name="Street Cutaway" offset="{start + 2}s" '
                     f'start="8s" duration="3s"/>')
        if name == "Interview Open":
            inner = (f'<asset-clip ref="a7" lane="-1" name="Music Bed" offset="{start}s" start="0s" '
                     f'duration="29s" audioRole="music"/>')
        spine.append(f'<asset-clip ref="{ref}" offset="{3600 + off}s" name="{name}" start="{start}s" '
                     f'duration="{dur}s" format="r1" tcFormat="NDF">{inner}</asset-clip>')
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n<fcpxml version="1.13"><resources>'
        f'<format id="r1" name="FFVideoFormat720p24" frameDuration="1/24s" width="{W}" height="{H}"/>{assets}'
        '</resources><library><event name="Cut Review Demo"><project name="Maya Profile v1">'
        '<sequence format="r1" duration="29s" tcStart="3600s" tcFormat="NDF" audioLayout="stereo" audioRate="48k">'
        f'<spine>{"".join(spine)}</spine></sequence></project></event></library></fcpxml>\n'
    )


NOTES = """\
01:00:01:12 Open on her laugh, not the breath before it
01:00:07:00 Street shot is too long, half it
01:00:12:12 - 01:00:14:00 This cutaway covers her best line
01:00:19:00 Studio detail feels random here
01:00:23:00 Drone could hold longer
01:00:27:00 Logo needs a beat of black before it
Music is a little loud under the interview
01:00:31:00 Fade the music out
"""

DEMO_STEPS = [
    ("trim the head of Interview Open", "edit", {"action": "trim_clip", "clip_id": "Interview Open", "trim_start": "+12f"}),
    ("trim Street Wide to 2 seconds", "edit", {"action": "trim_clip", "clip_id": "Street Wide", "trim_end": "-2s"}),
    ("move Studio Detail to the start", "edit", {"action": "reorder_clips", "clip_ids": ["Studio Detail"], "target_position": "start"}),
    ("dissolve into the logo", "edit", {"action": "add_transition", "clip_id": "Drone Reveal", "position": "end"}),
]


def build(folder: Path) -> scenarios.Round:
    from cutreview import api

    folder = folder.resolve()
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    scenarios._env(folder / "journal")
    media = make_media(folder / "media")
    base = folder / "maya_v1.fcpxml"
    base.write_text(cut_xml(media), encoding="utf-8")
    scenarios.validate(base)
    notes = folder / "client-notes.txt"
    notes.write_text(NOTES, encoding="utf-8")
    marked = folder / "maya_v1_notes.fcpxml"
    print(api.notes(str(base), str(notes), str(marked)).summary)
    log: list = []
    after = scenarios._agent(folder, marked, DEMO_STEPS, (), log)
    nxt = folder / "maya_v2.fcpxml"
    scenarios._hand_edit(after, nxt, lambda root: scenarios._tick(root, [1, 3, 4]))
    log.append("by hand: tick #1, #3, #4")
    return scenarios.Round(folder, base, marked, nxt, log, notes)


def main() -> None:
    from cutreview import api

    folder = Path(sys.argv[1] if len(sys.argv) > 1 else "build/demo")
    r = build(folder)
    print("\n".join(r.steps))
    print(api.diff(str(r.marked), str(r.next_export), str(r.folder / "review.html")).summary)
    print(api.blame(str(r.marked), str(r.next_export), str(r.folder / "blame.html")).summary)
    print(api.status(str(r.marked), str(r.next_export), str(r.folder / "status.html")).summary)


if __name__ == "__main__":
    main()
