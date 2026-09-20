from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from trendforge.domain.enums import VoiceEngine
from trendforge.logging_setup import get_logger

log = get_logger("tts")


def _no_window() -> int:
    if sys.platform == "win32":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


def sapi_available() -> bool:
    try:
        import pyttsx3  # noqa: F401
        return True
    except Exception:
        return False


def synthesize_sapi(text: str, dest: Path, rate: int = 175) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.suffix.lower() != ".wav":
        dest = dest.with_suffix(".wav")
    import threading

    frozen = bool(getattr(sys, "frozen", False))
    if frozen or threading.current_thread() is threading.main_thread():
        return _sapi_inprocess(text, dest, rate)
    proc = subprocess.run(
        [sys.executable, "-m", "trendforge.services.tts_engine", str(dest), str(rate), text],
        capture_output=True,
        text=True,
        creationflags=_no_window(),
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "")[-1500:] or "SAPI subprocess failed")
    if not dest.exists() or dest.stat().st_size < 100:
        raise RuntimeError("Windows SAPI did not write an audio file")
    return dest


def _sapi_inprocess(text: str, dest: Path, rate: int) -> Path:
    import pyttsx3

    if sys.platform == "win32":
        try:
            import pythoncom  # type: ignore

            pythoncom.CoInitialize()
        except Exception:
            pass
    engine = pyttsx3.init()
    engine.setProperty("rate", rate)
    engine.save_to_file(text, str(dest))
    engine.runAndWait()
    engine.stop()
    if not dest.exists() or dest.stat().st_size < 100:
        raise RuntimeError("Windows SAPI did not write an audio file")
    return dest


def synthesize_edge(text: str, dest: Path, voice: str = "en-US-JennyNeural") -> Path:
    """Optional free cloud TTS. Disabled unless the user explicitly selects it."""
    import asyncio

    try:
        import edge_tts
    except ImportError as exc:
        raise RuntimeError("edge-tts is not installed") from exc

    dest.parent.mkdir(parents=True, exist_ok=True)

    async def _run() -> None:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(dest))

    asyncio.run(_run())
    return dest


def find_piper(explicit: str = "") -> str | None:
    if explicit and Path(explicit).exists():
        return explicit
    bundled = None
    try:
        from trendforge.bootstrap import ensure_app_dirs
        from trendforge.services.installer import piper_exe

        bundled = piper_exe(ensure_app_dirs())
    except Exception:
        bundled = None
    if bundled:
        return str(bundled)
    return shutil.which("piper")


def synthesize_piper(text: str, dest: Path, model: str, exe: str = "") -> Path:
    binary = find_piper(exe)
    if not binary:
        raise RuntimeError("piper executable not found — run the setup wizard to install Piper TTS")
    dest.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [binary, "--model", model, "--output_file", str(dest)],
        input=text,
        text=True,
        capture_output=True,
        creationflags=_no_window(),
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-1500:])
    return dest


def synthesize(
    text: str,
    dest: Path,
    engine: VoiceEngine,
    piper_model: str = "",
    allow_cloud: bool = False,
) -> Path | None:
    text = " ".join((text or "").split())
    if not text or engine is VoiceEngine.NONE:
        return None
    if engine is VoiceEngine.WINDOWS_SAPI or engine is VoiceEngine.MAESTRO:
        # Maestro audio is generated with clips; SAPI covers our local stitch path.
        return synthesize_sapi(text, dest)
    if engine is VoiceEngine.PIPER:
        if not piper_model:
            try:
                from trendforge.bootstrap import ensure_app_dirs
                from trendforge.services.installer import piper_model_path

                found = piper_model_path(ensure_app_dirs(), "en_US-lessac-medium")
                piper_model = str(found) if found else ""
            except Exception:
                piper_model = ""
        if not piper_model:
            log.warning("Piper voice missing; falling back to Windows SAPI")
            return synthesize_sapi(text, dest)
        try:
            return synthesize_piper(text, dest, piper_model)
        except Exception as exc:
            log.warning("Piper failed (%s); using Windows SAPI", exc)
            return synthesize_sapi(text, dest)
    if engine is VoiceEngine.EDGE_TTS:
        if not allow_cloud:
            log.info("Edge TTS skipped because paid/cloud fallbacks are disabled")
            return synthesize_sapi(text, dest)
        return synthesize_edge(text, dest)
    # Coqui / XTTS: try only if packages exist
    if engine in {VoiceEngine.COQUI, VoiceEngine.XTTS}:
        try:
            return synthesize_sapi(text, dest)
        except Exception:
            raise RuntimeError(
                f"{engine.value} is listed as a local option but is not installed. "
                "Use Windows SAPI or Piper, or generate audio inside Maestro."
            )
    return synthesize_sapi(text, dest)


def concat_wavs(paths: list[Path], dest: Path, ffmpeg: str) -> Path:
    if not paths:
        raise ValueError("No audio clips to concat")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as handle:
        for path in paths:
            handle.write(f"file '{path.resolve().as_posix()}'\n")
        list_path = Path(handle.name)
    proc = subprocess.run(
        [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(dest)],
        capture_output=True,
        text=True,
        creationflags=_no_window(),
    )
    if proc.returncode != 0:
        proc = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_path),
                "-ar",
                "44100",
                "-ac",
                "2",
                str(dest),
            ],
            capture_output=True,
            text=True,
            creationflags=_no_window(),
        )
        list_path.unlink(missing_ok=True)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr[-1500:])
        return dest
    list_path.unlink(missing_ok=True)
    return dest


if __name__ == "__main__":
    _dest = Path(sys.argv[1])
    _rate = int(sys.argv[2])
    _text = " ".join(sys.argv[3:])
    _sapi_inprocess(_text, _dest, _rate)
