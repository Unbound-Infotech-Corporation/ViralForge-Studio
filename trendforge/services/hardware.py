from __future__ import annotations

import shutil
import subprocess
from typing import Any

import psutil

from trendforge.domain.enums import BackendKind
from trendforge.domain.models import HardwareProfile
from trendforge.logging_setup import get_logger

log = get_logger("hardware")


def _bytes_to_gb(value: float) -> float:
    return round(value / (1024**3), 2)


def _nvidia_smi() -> dict[str, Any] | None:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        proc = subprocess.run(
            [
                exe,
                "--query-gpu=name,memory.total,memory.free,driver_version",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=_no_window_flags(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("nvidia-smi failed: %s", exc)
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    line = proc.stdout.strip().splitlines()[0]
    parts = [p.strip() for p in line.split(",")]
    if len(parts) < 4:
        return None
    name, total_mb, free_mb, driver = parts[0], parts[1], parts[2], parts[3]
    try:
        total_gb = round(float(total_mb) / 1024, 2)
        free_gb = round(float(free_mb) / 1024, 2)
    except ValueError:
        return None
    return {
        "name": name,
        "vram_total_gb": total_gb,
        "vram_free_gb": free_gb,
        "driver": driver,
    }


def _no_window_flags() -> int:
    import sys

    if sys.platform == "win32":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


def _pynvml() -> dict[str, Any] | None:
    try:
        import pynvml  # type: ignore
    except Exception:
        return None
    try:
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        name = pynvml.nvmlDeviceGetName(handle)
        if isinstance(name, bytes):
            name = name.decode("utf-8", errors="replace")
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        try:
            driver = pynvml.nvmlSystemGetDriverVersion()
            if isinstance(driver, bytes):
                driver = driver.decode("utf-8", errors="replace")
        except Exception:
            driver = ""
        return {
            "name": str(name),
            "vram_total_gb": _bytes_to_gb(mem.total),
            "vram_free_gb": _bytes_to_gb(mem.free),
            "driver": str(driver),
        }
    except Exception as exc:
        log.info("pynvml unavailable: %s", exc)
        return None
    finally:
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass


def recommend_for_vram(vram_gb: float, has_nvidia: bool) -> tuple[BackendKind, str, list[str]]:
    notes: list[str] = []
    if not has_nvidia or vram_gb < 6:
        notes.append(
            "No NVIDIA GPU with 6 GB+ VRAM detected. Use Quick Explainer now; install Pinokio + Maestro later for cinematic AI."
        )
        return BackendKind.QUICK_EXPLAINER, "quick_explainer", notes
    if vram_gb < 10:
        notes.append("8 GB class GPU: Maestro Director / LTX distilled is the sweet spot. Avoid Wan A14B.")
        return BackendKind.MAESTRO_DIRECTOR, "ltx25_distilled", notes
    if vram_gb < 16:
        notes.append("12 GB class GPU: MiniMax H3 or Wan 2.2 5B when Maestro is running.")
        return BackendKind.MAESTRO_DIRECTOR, "minimax_h3", notes
    notes.append("16 GB+ GPU: you can run larger Wan / Hunyuan models comfortably.")
    return BackendKind.MAESTRO_DIRECTOR, "wan22_a14b", notes


def detect_hardware() -> HardwareProfile:
    vm = psutil.virtual_memory()
    nvidia = _nvidia_smi() or _pynvml()
    profile = HardwareProfile(
        ram_total_gb=_bytes_to_gb(vm.total),
        ram_available_gb=_bytes_to_gb(vm.available),
    )
    if nvidia:
        profile.gpu_name = nvidia["name"]
        profile.gpu_vendor = "nvidia"
        profile.vram_total_gb = float(nvidia["vram_total_gb"])
        profile.vram_free_gb = float(nvidia["vram_free_gb"])
        profile.nvidia_driver = nvidia.get("driver", "")
        profile.cuda_available = True
    backend, model_id, notes = recommend_for_vram(profile.vram_total_gb, profile.cuda_available)
    profile.recommended_backend = backend
    profile.recommended_model_id = model_id
    profile.notes = notes
    return profile
