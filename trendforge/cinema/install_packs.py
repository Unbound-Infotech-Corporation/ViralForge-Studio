"""ViralForge install packs — Lite / Regular / Maximum."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelSpec:
    repo_id: str
    local_name: str
    approx_gb: float
    required: bool = True


@dataclass(frozen=True)
class InstallPack:
    id: str
    name: str
    tagline: str
    approx_gb: float
    vram_tip: str
    models: tuple[ModelSpec, ...] = field(default_factory=tuple)


LITE = InstallPack(
    id="lite",
    name="Lite",
    tagline="Try Studio now — dry-run cinema + voice/captions",
    approx_gb=6,
    vram_tip="Any GPU / CPU OK",
    models=(
        ModelSpec("rhasspy/piper-voices", "piper", 1.5, required=False),
        ModelSpec("openai/whisper-base", "whisper-base", 0.15, required=False),
    ),
)

REGULAR = InstallPack(
    id="regular",
    name="Regular",
    tagline="Pro local cinema — recommended for RTX 5090",
    approx_gb=70,
    vram_tip="16 GB+ VRAM recommended",
    models=(
        ModelSpec("Wan-AI/Wan2.2-TI2V-5B", "wan2.2-ti2v-5b", 25),
        ModelSpec("Lightricks/LTX-2.5-Diffusers", "ltx-2.5", 40),
        ModelSpec("rhasspy/piper-voices", "piper", 1.5, required=False),
        ModelSpec("openai/whisper-base", "whisper-base", 0.15, required=False),
    ),
)

MAXIMUM = InstallPack(
    id="maximum",
    name="Maximum",
    tagline="Highest quality heroes — needs huge disk",
    approx_gb=180,
    vram_tip="24 GB+ VRAM; A14B is heavy even with offload",
    models=(
        ModelSpec("Wan-AI/Wan2.2-TI2V-5B", "wan2.2-ti2v-5b", 25),
        ModelSpec("Wan-AI/Wan2.2-I2V-A14B", "wan2.2-i2v-a14b", 80),
        ModelSpec("Lightricks/LTX-2.5-Diffusers", "ltx-2.5", 40),
        ModelSpec("rhasspy/piper-voices", "piper", 1.5, required=False),
        ModelSpec("openai/whisper-base", "whisper-base", 0.15, required=False),
    ),
)

PACKS = (LITE, REGULAR, MAXIMUM)


def pack_by_id(pack_id: str) -> InstallPack:
    for p in PACKS:
        if p.id == pack_id:
            return p
    raise KeyError(pack_id)
