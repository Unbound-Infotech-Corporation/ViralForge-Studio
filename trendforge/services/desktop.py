"""Open a local file or folder without assuming Windows."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def open_path(path: str) -> None:
    target = (path or "").strip()
    if not target or not Path(target).exists():
        raise FileNotFoundError(target or "empty path")
    if sys.platform.startswith("win"):
        import os

        os.startfile(target)  # type: ignore[attr-defined]
        return
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.Popen([opener, target])
