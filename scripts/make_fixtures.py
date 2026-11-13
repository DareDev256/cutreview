"""Build both review rounds into a folder you can open in Final Cut or read by hand.

    python scripts/make_fixtures.py fixtures/build

Each round gets the copied cut, the marked cut, one file per fcp-mcp-server
write, the next export, and fcp-mcp-server's journal in journal/.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scenarios  # noqa: E402

if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "fixtures/build").resolve()
    for name, rnd in scenarios.build_all(out).items():
        print(f"{name}: {rnd.marked.name} -> {rnd.next_export.name}")
        for step in rnd.steps:
            print(f"  {step}")
