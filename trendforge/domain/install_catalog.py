from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from trendforge.domain.models import HardwareProfile

ProgressFn = Callable[[str, int], None]


@dataclass(slots=True)
class InstallItem:
    id: str
    name: str
    kind: str  # ffmpeg, piper, whisper, ollama, maestro, pinokio
    description: str
    size_gb: float
    recommended: bool = True
    requires_gpu: bool = False
    min_vram_gb: float = 0
    min_ram_gb: float = 0
    ollama_tag: str = ""
    piper_voice: str = ""
    maestro_hint: str = ""
    urls: list[tuple[str, str]] = field(default_factory=list)  # (filename, url)


PIPER_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"


def _piper(voice: str, quality: str, size: float) -> list[tuple[str, str]]:
    # en_US-lessac-medium → en/en_US/lessac/medium
    lang = "en_US" if voice.startswith("en_US") else "en_GB"
    name = voice.split("-")[1]
    folder = f"en/{lang}/{name}/{quality}"
    stem = f"{lang}-{name}-{quality}"
    return [
        (f"{stem}.onnx", f"{PIPER_BASE}/{folder}/{stem}.onnx"),
        (f"{stem}.onnx.json", f"{PIPER_BASE}/{folder}/{stem}.onnx.json"),
    ]


def install_catalog() -> list[InstallItem]:
    return [
        InstallItem(
            id="ffmpeg",
            name="ffmpeg (video encoder)",
            kind="ffmpeg",
            description="Required to stitch and encode YouTube MP4s. Uses the bundled imageio-ffmpeg copy.",
            size_gb=0.08,
            recommended=True,
        ),
        InstallItem(
            id="piper_runtime",
            name="Piper TTS engine (Windows)",
            kind="piper_runtime",
            description="Local speech engine used with the Piper voices. ~20 MB zip.",
            size_gb=0.03,
            recommended=True,
        ),
        InstallItem(
            id="piper_lessac",
            name="Piper voice — Lessac (clear narrator)",
            kind="piper",
            description="Local TTS for explainers and Shorts. ~63 MB.",
            size_gb=0.07,
            recommended=True,
            piper_voice="en_US-lessac-medium",
            urls=_piper("en_US-lessac-medium", "medium", 0.07),
        ),
        InstallItem(
            id="piper_ryan",
            name="Piper voice — Ryan (deeper, documentary)",
            kind="piper",
            description="Local TTS for long narrated docuseries.",
            size_gb=0.07,
            recommended=True,
            piper_voice="en_US-ryan-medium",
            urls=_piper("en_US-ryan-medium", "medium", 0.07),
        ),
        InstallItem(
            id="piper_amy",
            name="Piper voice — Amy (warm)",
            kind="piper",
            description="Alternate local narrator.",
            size_gb=0.07,
            recommended=False,
            piper_voice="en_US-amy-medium",
            urls=_piper("en_US-amy-medium", "medium", 0.07),
        ),
        InstallItem(
            id="whisper_base",
            name="Whisper base (captions from audio)",
            kind="whisper",
            description="Optional local transcription if you want captions from the finished mix.",
            size_gb=0.15,
            recommended=True,
        ),
        InstallItem(
            id="ollama_qwen7",
            name="Ollama Qwen2.5 7B (scripts & titles)",
            kind="ollama",
            description="Strong free local LLM for scripts, titles, and season outlines. ~4.7 GB.",
            size_gb=4.7,
            recommended=True,
            min_ram_gb=8,
            ollama_tag="qwen2.5:7b",
        ),
        InstallItem(
            id="ollama_qwen14",
            name="Ollama Qwen2.5 14B (richer long-form writing)",
            kind="ollama",
            description="Better docuseries writing on high-RAM PCs. ~9 GB.",
            size_gb=9.0,
            recommended=False,
            min_ram_gb=24,
            ollama_tag="qwen2.5:14b",
        ),
        InstallItem(
            id="maestro_ltx25",
            name="Maestro — LTX-2.5 Distilled (fast cinematic)",
            kind="maestro",
            description="Queued through Maestro when it is running. Downloads inside Maestro.",
            size_gb=18,
            recommended=True,
            requires_gpu=True,
            min_vram_gb=8,
            maestro_hint="ltx2.5",
        ),
        InstallItem(
            id="maestro_wan5b",
            name="Maestro — Wan 2.2 TI2V-5B",
            kind="maestro",
            description="Lighter Wan via Maestro.",
            size_gb=12,
            recommended=False,
            requires_gpu=True,
            min_vram_gb=10,
            maestro_hint="ti2v-5b",
        ),
        InstallItem(
            id="maestro_wana14b",
            name="Maestro — Wan 2.2 A14B (highest quality)",
            kind="maestro",
            description="16 GB+ VRAM. Queued through Maestro.",
            size_gb=28,
            recommended=False,
            requires_gpu=True,
            min_vram_gb=16,
            maestro_hint="a14b",
        ),
        InstallItem(
            id="maestro_h3",
            name="Maestro — MiniMax H3",
            kind="maestro",
            description="Dialogue / longer windows via Maestro.",
            size_gb=24,
            recommended=False,
            requires_gpu=True,
            min_vram_gb=12,
            maestro_hint="h3",
        ),
        InstallItem(
            id="maestro_hunyuan",
            name="Maestro — HunyuanVideo-1.5",
            kind="maestro",
            description="Cinematic look via Maestro.",
            size_gb=25,
            recommended=False,
            requires_gpu=True,
            min_vram_gb=12,
            maestro_hint="hunyuan",
        ),
    ]


def recommend_ids(hw: HardwareProfile) -> set[str]:
    picks = {"ffmpeg", "piper_runtime", "piper_lessac", "piper_ryan", "whisper_base", "ollama_qwen7"}
    if hw.ram_total_gb >= 24:
        picks.add("ollama_qwen14")
    return picks


def piper_dir(models_root: Path) -> Path:
    path = models_root / "piper"
    path.mkdir(parents=True, exist_ok=True)
    return path


def whisper_dir(models_root: Path) -> Path:
    path = models_root / "whisper"
    path.mkdir(parents=True, exist_ok=True)
    return path
