"""Before and after frames, pulled from the source media with ffmpeg.

The frame is the SOURCE frame under that instant of the cut: the clip's
picture as shot, with no effects, titles or grades drawn. Labels live in the
page, never burned into the image (and ffmpeg builds without drawtext still
work). A frame that cannot be read is reported as offline, never replaced
with a stand-in.
"""

from __future__ import annotations

import base64
import hashlib
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Dict, Optional

from .cut import Cut

WIDTH = 480
_TIMEOUT = 20


class FrameGrabber:
    def __init__(self, cache_dir: Path, enabled: bool = True):
        self.cache = Path(cache_dir)
        self.enabled = enabled and shutil.which("ffmpeg") is not None
        self.offline: Dict[str, str] = {}
        self.cache.mkdir(parents=True, exist_ok=True)

    def at(self, cut: Cut, t: Optional[Fraction]) -> Optional[dict]:
        """``{"uri", "clip", "file_time"}`` for the picture at *t*, or None."""
        if t is None or not self.enabled:
            return None
        t = max(Fraction(0), min(t, cut.duration - cut.frame_duration))
        span = cut.picture_at(t)
        if span is None:
            return None
        path = span.media_path
        if not path or not Path(path).is_file():
            self.offline[span.key] = path or span.key
            return None
        ft = max(Fraction(0), span.file_time(t))
        tag = hashlib.sha256(f"{path}|{ft}|{WIDTH}".encode()).hexdigest()[:20]
        out = self.cache / f"{tag}.jpg"
        if not out.exists():
            cmd = [
                "ffmpeg", "-nostdin", "-loglevel", "error", "-y",
                "-ss", f"{float(ft):.4f}", "-i", path,
                "-frames:v", "1", "-vf", f"scale={WIDTH}:-2", "-q:v", "5", str(out),
            ]
            try:
                subprocess.run(cmd, capture_output=True, timeout=_TIMEOUT, check=False)
            except (OSError, subprocess.TimeoutExpired):
                pass
        if not out.exists() or out.stat().st_size == 0:
            self.offline[span.key] = f"{path} (ffmpeg read no frame at {float(ft):.2f}s)"
            return None
        uri = "data:image/jpeg;base64," + base64.b64encode(out.read_bytes()).decode("ascii")
        return {"uri": uri, "clip": span.name, "file_time": ft}
