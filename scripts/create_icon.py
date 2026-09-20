"""Bake PNG/ICO from the in-app painter. Run from repo root: python scripts/create_icon.py"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from trendforge.bootstrap import assets_root  # noqa: E402
from trendforge.ui.theme import _paint_icon  # noqa: E402


def main() -> int:
    app = QApplication([])
    pix = _paint_icon(256)
    folder = assets_root() / "icons"
    folder.mkdir(parents=True, exist_ok=True)
    png = folder / "trendforge.png"
    ico = folder / "trendforge.ico"
    pix.save(str(png), "PNG")
    pix.save(str(ico), "ICO")
    print(f"Wrote {png} and {ico}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
