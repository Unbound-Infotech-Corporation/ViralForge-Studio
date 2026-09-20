from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from trendforge.logging_setup import get_logger

log = get_logger("ffmpeg")


def _no_window() -> int:
    if sys.platform == "win32":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


def bundled_ffmpeg() -> str | None:
    try:
        import imageio_ffmpeg
    except Exception:
        return None
    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        log.warning("imageio-ffmpeg missing binary: %s", exc)
        return None


def find_ffmpeg(explicit: str = "") -> str:
    if explicit:
        path = Path(explicit)
        if path.exists():
            return str(path)
    which = shutil.which("ffmpeg")
    if which:
        return which
    bundled = bundled_ffmpeg()
    if bundled:
        return bundled
    raise FileNotFoundError(
        "ffmpeg was not found. Install it (winget install Gyan.FFmpeg) or keep imageio-ffmpeg in requirements."
    )


def find_ffprobe(ffmpeg_path: str) -> str | None:
    candidate = Path(ffmpeg_path).with_name("ffprobe.exe" if sys.platform == "win32" else "ffprobe")
    if candidate.exists():
        return str(candidate)
    return shutil.which("ffprobe")


def run_ffmpeg(args: list[str], ffmpeg: str) -> subprocess.CompletedProcess[str]:
    cmd = [ffmpeg, "-y", *args]
    log.info("ffmpeg %s", " ".join(args[:12]))
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        creationflags=_no_window(),
    )


def require_ok(proc: subprocess.CompletedProcess[str], context: str) -> None:
    if proc.returncode == 0:
        return
    err = (proc.stderr or proc.stdout or "").strip()[-4000:]
    raise RuntimeError(f"{context} failed (code {proc.returncode}):\n{err}")
