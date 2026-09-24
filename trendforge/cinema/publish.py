"""Guards so cinema jobs never ship title-card or silent finals."""

from __future__ import annotations

from pathlib import Path

from trendforge.cinema.config import CinemaConfig


_MODEL_NAMES = {
    "cogvideox": "CogVideoX",
    "wan22_ti2v_5b": "Wan 2.2 TI2V-5B",
    "wan22_a14b": "Wan 2.2 A14B",
    "viralforge_cinema": "ViralForge Cinema",
}


def weight_dir_for(model_id: str, models_dir: Path) -> Path:
    folder = {
        "cogvideox": "cogvideox",
        "wan22_ti2v_5b": "wan2.2-ti2v-5b",
        "wan22_a14b": "wan2.2-i2v",
    }.get(model_id, "")
    return models_dir / folder if folder else models_dir


def cinema_publish_block_reason(
    *,
    card_stand_in: bool,
    require_audio: bool,
    has_audio: bool | None,
    model_id: str,
    models_dir: Path,
) -> str | None:
    """Return an error string when this export must not be published.

    ``has_audio is None`` skips the soundtrack check (used before render).
    """
    if card_stand_in:
        name = _MODEL_NAMES.get(model_id, "ViralForge Cinema")
        dest = weight_dir_for(model_id, models_dir)
        return (
            f"{name} would only render title cards, so this job will not publish a card final. "
            f"Put the model weights in {dest} and run again, "
            "or choose Quick Explainer when you want intentional motion-graphics cards."
        )
    if require_audio and has_audio is False:
        return (
            "Voice or music was requested, but the cinema export has no audio. "
            "Refusing a silent final."
        )
    return None


def models_dir_from_settings(settings: object) -> Path:
    return CinemaConfig.from_settings(settings).models_dir
