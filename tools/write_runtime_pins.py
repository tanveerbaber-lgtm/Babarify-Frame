"""Record the Python packages a Windows release ships, for the monthly security check (M16).

Run from the build environment when preparing a release. The file pins what actually ships, because
pyproject.toml only sets minimum versions and a fresh install could audit something else.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from notices import closure  # noqa: E402

OUTPUT = ROOT / "requirements" / "windows-runtime.txt"


def main() -> int:
    version = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["project"]["version"]
    pins = sorted(f"{dist.metadata['Name']}=={dist.version}" for dist in closure())
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(f"# Babarify Frame {version} for Windows\n" + "\n".join(pins) + "\n", "utf-8")
    print(f"{len(pins)} packages written to {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
