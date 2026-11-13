import logging
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import scenarios  # noqa: E402

from fcpxml import dtd as fcp_dtd  # noqa: E402

FIXTURES = ROOT / "fixtures"
HAS_DTD = fcp_dtd.find_apple_dtd("1.13") is not None and shutil.which("xmllint") is not None
needs_dtd = pytest.mark.skipif(not HAS_DTD, reason="Apple's FCPXML DTD (Final Cut Pro) or xmllint not on this machine")
HAS_FFMPEG = shutil.which("ffmpeg") is not None

# fcp-mcp-server logs a timebase warning for the music-video fixture's
# deliberately odd 3606500/1000s offset on every write; it is not ours.
logging.getLogger("fcpxml").setLevel(logging.ERROR)


@pytest.fixture(scope="session")
def music_round(tmp_path_factory):
    return scenarios.music_video(tmp_path_factory.mktemp("music"))


@pytest.fixture(scope="session")
def sample_round(tmp_path_factory):
    return scenarios.sample(tmp_path_factory.mktemp("sample"))


@pytest.fixture()
def work(tmp_path):
    for f in ("music-video.fcpxml", "sample.fcpxml"):
        shutil.copy(FIXTURES / f, tmp_path / f)
    return tmp_path
