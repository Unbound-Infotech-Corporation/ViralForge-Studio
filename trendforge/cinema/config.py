from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

WAN_I2V_REPO = "Wan-AI/Wan2.2-I2V-A14B"
WAN_TI2V_REPO = "Wan-AI/Wan2.2-TI2V-5B"
# Diffusers layout (model_index.json). The official TI2V repo above is WanModel shards + VAE/T5 pth.
WAN_TI2V_DIFFUSERS_REPO = "Wan-AI/Wan2.2-TI2V-5B-Diffusers"
WAN_TI2V_DIFFUSERS_DIRNAME = "wan2.2-ti2v-5b-diffusers"
LTX25_REPO = "Lightricks/LTX-2.5-Diffusers"

DEFAULT_MODELS_DIR = Path(r"F:\TrendForge\models\cinema")


@dataclass(slots=True)
class CinemaConfig:
    models_dir: Path = DEFAULT_MODELS_DIR
    dry_run: bool = True
    device: str = "cuda"
    wan_repo: str = WAN_I2V_REPO
    wan_diffusers_repo: str = WAN_TI2V_DIFFUSERS_REPO
    ltx_repo: str = LTX25_REPO
    bridge_with_ltx: bool = True
    xfade_sec: float = 0.35
    # Wan 2.2 TI2V-5B is 720p-class at 1280x704 (both dims divisible by 32), 24 fps.
    wan_height: int = 704
    wan_width: int = 1280
    wan_fps: int = 24
    wan_steps: int = 50
    wan_guidance: float = 5.0
    wan_offload: bool = True
    wan_clip_sec: float = 6.0
    wan_max_clip_sec: float = 8.0
    wan_seed: int | None = None

    @classmethod
    def from_settings(cls, settings) -> "CinemaConfig":
        models = getattr(settings, "cinema_models_dir", "") or str(DEFAULT_MODELS_DIR)
        dry = bool(getattr(settings, "cinema_dry_run", True))
        return cls(models_dir=Path(models), dry_run=dry)
