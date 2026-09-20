from __future__ import annotations

import json
import shutil
import sys
import time
import zipfile
from pathlib import Path
from typing import Callable

import httpx

from trendforge.bootstrap import AppDirs
from trendforge.domain.install_catalog import (
    InstallItem,
    install_catalog,
    piper_dir,
    recommend_ids,
    whisper_dir,
)
from trendforge.logging_setup import get_logger
from trendforge.services.ffmpeg_tools import find_ffmpeg
from trendforge.services.maestro_client import MaestroClient, MaestroError
from trendforge.services.maestro_detect import detect_maestro
from trendforge.services.ollama_client import OllamaClient
from trendforge.settings import AppSettings

log = get_logger("installer")
ProgressFn = Callable[[str, int], None]
HEADERS = {"User-Agent": "TrendForgeStudio/1.1 (Windows; local installer)"}
PIPER_ZIP = "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip"


class InstallError(RuntimeError):
    pass


def free_gb(path: Path) -> float:
    usage = shutil.disk_usage(path)
    return round(usage.free / (1024**3), 1)


def item_installed(item: InstallItem, dirs: AppDirs, settings: AppSettings) -> bool:
    if item.kind == "ffmpeg":
        try:
            find_ffmpeg(settings.ffmpeg_path)
            return True
        except FileNotFoundError:
            return False
    if item.kind == "piper_runtime":
        return (piper_dir(dirs.models) / "piper.exe").exists()
    if item.kind == "piper":
        stem = item.piper_voice
        return (piper_dir(dirs.models) / f"{stem}.onnx").exists()
    if item.kind == "whisper":
        root = whisper_dir(dirs.models)
        return any(root.glob("**/*bin")) or any(root.glob("**/*.bin")) or (root / "base").exists()
    if item.kind == "ollama":
        st = OllamaClient(settings.ollama_url).status()
        tag = item.ollama_tag
        return any(tag in m for m in st.models)
    if item.kind == "maestro":
        return item.id in (settings.installed_items or [])
    return item.id in (settings.installed_items or [])


def _download(url: str, dest: Path, on_progress: ProgressFn | None, cancelled: Callable[[], bool] | None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with httpx.Client(timeout=None, follow_redirects=True, headers=HEADERS) as client:
        with client.stream("GET", url) as res:
            res.raise_for_status()
            total = int(res.headers.get("content-length") or 0)
            done = 0
            with tmp.open("wb") as handle:
                for chunk in res.iter_bytes(1024 * 256):
                    if cancelled and cancelled():
                        raise InstallError("Cancelled")
                    handle.write(chunk)
                    done += len(chunk)
                    if on_progress and total:
                        pct = min(99, int(done * 100 / total))
                        on_progress(f"Downloading {dest.name} ({done // (1024 * 1024)} MB)", pct)
    tmp.replace(dest)


def _ensure_ffmpeg(on_progress: ProgressFn | None) -> None:
    try:
        find_ffmpeg("")
        if on_progress:
            on_progress("ffmpeg ready", 100)
    except FileNotFoundError as exc:
        raise InstallError(str(exc)) from exc


def _install_piper_runtime(dirs: AppDirs, on_progress: ProgressFn | None, cancelled: Callable[[], bool] | None) -> None:
    dest_dir = piper_dir(dirs.models)
    exe = dest_dir / "piper.exe"
    if exe.exists():
        return
    zpath = dest_dir / "piper_windows_amd64.zip"
    if on_progress:
        on_progress("Downloading Piper TTS engine…", 5)
    _download(PIPER_ZIP, zpath, on_progress, cancelled)
    with zipfile.ZipFile(zpath) as zf:
        zf.extractall(dest_dir)
    # zip may nest a piper/ folder
    nested = dest_dir / "piper" / "piper.exe"
    if nested.exists() and not exe.exists():
        for child in (dest_dir / "piper").iterdir():
            target = dest_dir / child.name
            if not target.exists():
                shutil.move(str(child), str(target))
    if not exe.exists():
        found = list(dest_dir.rglob("piper.exe"))
        if found:
            shutil.copy2(found[0], exe)
    if not exe.exists():
        raise InstallError("Piper zip extracted but piper.exe was not found")
    zpath.unlink(missing_ok=True)


def _install_piper_voice(item: InstallItem, dirs: AppDirs, on_progress: ProgressFn | None, cancelled: Callable[[], bool] | None) -> None:
    folder = piper_dir(dirs.models)
    for filename, url in item.urls:
        dest = folder / filename
        if dest.exists() and dest.stat().st_size > 1000:
            continue
        if on_progress:
            on_progress(f"Downloading {filename}…", 10)
        _download(url, dest, on_progress, cancelled)


def _install_whisper(dirs: AppDirs, on_progress: ProgressFn | None) -> None:
    if on_progress:
        on_progress("Installing faster-whisper (if needed) and fetching base weights…", 15)
    try:
        import faster_whisper  # noqa: F401
    except Exception:
        proc = __import__("subprocess").run(
            [sys.executable, "-m", "pip", "install", "faster-whisper>=1.0,<2"],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise InstallError(proc.stderr[-1500:] or "pip install faster-whisper failed")
    from faster_whisper import WhisperModel

    WhisperModel("base", device="cpu", compute_type="int8", download_root=str(whisper_dir(dirs.models)))
    if on_progress:
        on_progress("Whisper base ready", 100)


def _install_ollama(item: InstallItem, settings: AppSettings, on_progress: ProgressFn | None, cancelled: Callable[[], bool] | None) -> None:
    client = OllamaClient(settings.ollama_url)
    if not client.status().running:
        raise InstallError(
            "Ollama is not running. Install it from https://ollama.com/download then click Install again. "
            "TrendForge will pull the model automatically once Ollama is up."
        )
    client.pull(item.ollama_tag, on_progress=on_progress, cancelled=cancelled)


def _install_maestro(item: InstallItem, settings: AppSettings, on_progress: ProgressFn | None, cancelled: Callable[[], bool] | None) -> None:
    inst = detect_maestro(settings.maestro_url, settings.pinokio_path)
    if not inst.running_url:
        raise InstallError(
            "Maestro is not running. Start Maestro with start_maestro.bat, then re-run setup to download cinematic weights."
        )
    api = MaestroClient(inst.running_url)
    mtype = api.match_model(item.maestro_hint)
    if not mtype:
        raise InstallError(f"Maestro has no model matching '{item.maestro_hint}'. Start Maestro and update it.")
    if on_progress:
        on_progress(f"Asking Maestro to download {mtype}…", 5)
    try:
        api.start_weight_download(mtype)
    except MaestroError as exc:
        raise InstallError(str(exc)) from exc
    started = time.time()
    while time.time() - started < 60 * 60 * 6:
        if cancelled and cancelled():
            raise InstallError("Cancelled")
        try:
            status = api.weight_downloads()
        except MaestroError:
            time.sleep(3)
            continue
        downloads = status.get("downloads") or status
        info = {}
        if isinstance(downloads, dict):
            info = downloads.get(mtype) or {}
            if not info:
                for key, val in downloads.items():
                    if isinstance(val, dict) and mtype in str(key):
                        info = val
                        break
        state = str(info.get("status") or info.get("state") or "")
        if on_progress:
            on_progress(f"Maestro {mtype}: {state or 'downloading'}", 40)
        if state in {"completed", "complete", "done"}:
            return
        if state in {"failed", "error"}:
            raise InstallError(info.get("error") or f"Maestro download failed for {mtype}")
        # If status map is empty, assume Maestro queued it
        if not info and time.time() - started > 20:
            if on_progress:
                on_progress(f"Download queued in Maestro for {mtype}. Watch Maestro's UI for GB progress.", 70)
            return
        time.sleep(4)


def install_items(
    ids: list[str],
    dirs: AppDirs,
    settings: AppSettings,
    on_progress: ProgressFn | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> list[str]:
    """Install selected items. Returns a list of human-readable results."""
    catalog = {i.id: i for i in install_catalog()}
    notes: list[str] = []
    done_ids = list(settings.installed_items or [])
    for ident in ids:
        item = catalog.get(ident)
        if not item:
            notes.append(f"Unknown item {ident}")
            continue
        if cancelled and cancelled():
            notes.append("Cancelled")
            break
        if item_installed(item, dirs, settings):
            notes.append(f"Already installed: {item.name}")
            if ident not in done_ids:
                done_ids.append(ident)
            continue
        if on_progress:
            on_progress(f"Installing {item.name}…", 1)
        try:
            if item.kind == "ffmpeg":
                _ensure_ffmpeg(on_progress)
            elif item.kind == "piper_runtime":
                _install_piper_runtime(dirs, on_progress, cancelled)
            elif item.kind == "piper":
                _install_piper_voice(item, dirs, on_progress, cancelled)
            elif item.kind == "whisper":
                _install_whisper(dirs, on_progress)
            elif item.kind == "ollama":
                _install_ollama(item, settings, on_progress, cancelled)
            elif item.kind == "maestro":
                _install_maestro(item, settings, on_progress, cancelled)
            else:
                notes.append(f"Skipped unknown kind {item.kind}")
                continue
            notes.append(f"Installed: {item.name}")
            if ident not in done_ids:
                done_ids.append(ident)
        except Exception as exc:
            log.warning("Install failed for %s: %s", ident, exc)
            notes.append(f"Failed: {item.name} — {exc}")
    settings.installed_items = done_ids
    settings.save()
    return notes


def ids_that_fit(
    dirs: AppDirs,
    settings: AppSettings,
    reserve_gb: float = 8.0,
    local_only: bool = False,
) -> list[str]:
    """Pick installable items that fit this GPU, RAM, and remaining disk (leave reserve_gb free)."""
    from trendforge.services.hardware import detect_hardware

    hw = detect_hardware()
    catalog = install_catalog()
    rec = recommend_ids(hw)
    ordered = [s for s in catalog if s.id in rec] + [s for s in catalog if s.id not in rec]
    free = free_gb(dirs.models)
    used = 0.0
    chosen: list[str] = []
    for spec in ordered:
        if local_only and spec.kind in {"maestro", "ollama"}:
            continue
        if item_installed(spec, dirs, settings):
            continue
        fits_vram = (not spec.requires_gpu) or (hw.cuda_available and hw.vram_total_gb + 0.4 >= spec.min_vram_gb)
        fits_ram = hw.ram_total_gb + 0.4 >= spec.min_ram_gb
        if not (fits_vram and fits_ram):
            continue
        if used + spec.size_gb > free - reserve_gb:
            continue
        chosen.append(spec.id)
        used += spec.size_gb
    return chosen


def piper_exe(dirs: AppDirs) -> Path | None:
    candidate = piper_dir(dirs.models) / "piper.exe"
    return candidate if candidate.exists() else None


def piper_model_path(dirs: AppDirs, voice: str) -> Path | None:
    path = piper_dir(dirs.models) / f"{voice}.onnx"
    return path if path.exists() else None


def installed_piper_voices(dirs: AppDirs) -> list[str]:
    folder = piper_dir(dirs.models)
    return sorted(p.stem for p in folder.glob("*.onnx"))
