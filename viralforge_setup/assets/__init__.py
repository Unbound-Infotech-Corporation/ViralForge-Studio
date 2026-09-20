"""Resolve bundled icons from the package or the repo-level ``assets/icons``."""

from __future__ import annotations

from pathlib import Path


def icon_roots() -> tuple[Path, ...]:
    here = Path(__file__).resolve().parent
    return (
        here / "icons",
        here.parent.parent / "assets" / "icons",
    )


def icon_path(name: str) -> Path | None:
    for root in icon_roots():
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None


def first_existing(*names: str) -> Path | None:
    for name in names:
        found = icon_path(name)
        if found is not None:
            return found
    return None
