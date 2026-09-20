from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

WAN_I2V_REPO = "Wan-AI/Wan2.2-I2V-A14B"
WAN_TI2V_REPO = "Wan-AI/Wan2.2-TI2V-5B"
LTX25_REPO = "Lightricks/LTX-2.5-Diffusers"

DEFAULT_MODELS_DIR = Path(r"F:\TrendForge\models\cinema")


@dataclass(slots=True)
class CinemaConfig:
    models_dir: Path = DEFAULT_MODELS_DIR
    dry_run: bool = True
    device: str = "cuda"
    wan_repo: str = WAN_I2V_REPO
    ltx_repo: str = LTX25_REPO
    bridge_with_ltx: bool = True
    xfade_sec: float = 0.35

    @classmethod
    def from_settings(cls, settings) -> "CinemaConfig":
        models = getattr(settings, "cinema_models_dir", "") or str(DEFAULT_MODELS_DIR)
        dry = bool(getattr(settings, "cinema_dry_run", True))
        return cls(models_dir=Path(models), dry_run=dry)
