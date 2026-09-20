from __future__ import annotations

import os
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_dir, user_log_dir

from trendforge import __app_name__, __org_name__

DEFAULT_F_DRIVE_HOME = Path("F:/TrendForge")


@dataclass(frozen=True, slots=True)
class AppDirs:
    root: Path
    projects: Path
    gallery: Path
    cache: Path
    logs: Path
    models: Path
    music: Path
    tmp: Path
    settings_file: Path


def package_root() -> Path:
    return Path(__file__).resolve().parent


def assets_root() -> Path:
    return package_root() / "assets"


def resolve_data_root() -> Path:
    """Projects, models, and settings. Prefer TRENDFORGE_HOME, then F:\\TrendForge, else LocalAppData."""
    env = (os.environ.get("TRENDFORGE_HOME") or os.environ.get("TRENDFORGE_DATA") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    if Path("F:/").exists():
        try:
            DEFAULT_F_DRIVE_HOME.mkdir(parents=True, exist_ok=True)
            return DEFAULT_F_DRIVE_HOME.resolve()
        except OSError:
            pass
    return Path(user_data_dir(__app_name__, __org_name__))


def ensure_app_dirs() -> AppDirs:
    root = resolve_data_root()
    logs = root / "logs"
    # Keep a C: log copy only when data is not already on a dedicated drive.
    if root.drive.upper() not in {"F:", "D:", "E:"}:
        logs = Path(user_log_dir(__app_name__, __org_name__))
    dirs = AppDirs(
        root=root,
        projects=root / "projects",
        gallery=root / "gallery",
        cache=root / "cache",
        logs=logs,
        models=root / "models",
        music=root / "music",
        tmp=root / "tmp",
        settings_file=root / "settings.json",
    )
    for path in (
        dirs.root,
        dirs.projects,
        dirs.gallery,
        dirs.cache,
        dirs.logs,
        dirs.models,
        dirs.music,
        dirs.tmp,
    ):
        path.mkdir(parents=True, exist_ok=True)
    return dirs


def install_exception_hook() -> None:
    def _hook(exc_type, exc, tb) -> None:
        from trendforge.logging_setup import get_logger

        log = get_logger("crash")
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        log.error("Unhandled exception:\n%s", text)
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _hook
