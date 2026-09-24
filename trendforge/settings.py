from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from trendforge.bootstrap import AppDirs
from trendforge.domain.enums import (
    AspectRatio,
    CaptionStyle,
    ContentFormat,
    LengthPreset,
    ThemeMode,
    TransitionStyle,
    BrandVoice,
    VideoStyle,
    VoiceEngine,
)


DEFAULT_MAESTRO_PORTS = (42130, 7860, 8000, 8080, 8188, 8888, 7861, 3000, 5173)


@dataclass
class AppSettings:
    theme: ThemeMode = ThemeMode.DARK
    wizard_complete: bool = False
    last_backend: str = "auto"
    last_model_id: str = "auto"
    last_style: VideoStyle = VideoStyle.CINEMATIC
    last_length: LengthPreset = LengthPreset.SHORTS
    last_format: ContentFormat = ContentFormat.VIDEO
    last_aspect: AspectRatio = AspectRatio.WIDE
    last_voice: VoiceEngine = VoiceEngine.WINDOWS_SAPI
    last_piper_voice: str = "en_US-lessac-medium"
    last_caption: CaptionStyle = CaptionStyle.NONE
    last_transition: TransitionStyle = TransitionStyle.CROSSFADE
    enable_voiceover: bool = True
    enable_captions: bool = False
    enable_music: bool = True
    enable_intro: bool = True
    enable_outro: bool = True
    enable_upscale: bool = False
    codec: str = "h264"
    trend_region: str = "US"
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = ""
    comfyui_url: str = "http://127.0.0.1:8188"
    prefer_native_cinema: bool = True
    cinema_models_dir: str = r"F:\TrendForge\models\cinema"
    cinema_dry_run: bool = True
    maestro_url: str = ""
    maestro_install_path: str = ""
    pinokio_path: str = ""
    ffmpeg_path: str = ""
    extra_model_scan_dirs: list[str] = field(default_factory=list)
    paid_fallbacks_enabled: bool = False
    confirm_large_downloads: bool = True
    default_music_volume: float = 0.12
    default_voice_volume: float = 1.0
    channel_name: str = ""
    channel_niche: str = ""
    channel_audience: str = ""
    channel_cta: str = "Subscribe so you don't miss the next episode."
    brand_voice: BrandVoice = BrandVoice.DOCUMENTARY
    # Optional. Live comment download is not implemented; ManualPasteProvider is the working path.
    youtube_api_key: str = ""
    youtube_credentials_path: str = ""
    series_title: str = ""
    installed_items: list[str] = field(default_factory=list)

    _path: Path | None = field(default=None, repr=False, compare=False)

    @classmethod
    def load(cls, dirs: AppDirs) -> AppSettings:
        path = dirs.settings_file
        if not path.exists():
            settings = cls()
            settings._path = path
            settings.save()
            return settings
        raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        settings = cls._from_dict(raw)
        settings._path = path
        return settings

    def save(self) -> None:
        if self._path is None:
            raise RuntimeError("Settings path is not bound")
        payload = asdict(self)
        payload.pop("_path", None)
        for key, value in list(payload.items()):
            if hasattr(value, "value"):
                payload[key] = value.value
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @classmethod
    def _from_dict(cls, raw: dict[str, Any]) -> AppSettings:
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        data: dict[str, Any] = {}
        for key, value in raw.items():
            if key not in known or key == "_path":
                continue
            data[key] = value
        if "theme" in data:
            data["theme"] = ThemeMode(data["theme"])
        if "last_style" in data:
            data["last_style"] = VideoStyle(data["last_style"])
        if "last_length" in data:
            data["last_length"] = LengthPreset(data["last_length"])
        if "last_format" in data:
            try:
                data["last_format"] = ContentFormat(data["last_format"])
            except ValueError:
                data["last_format"] = ContentFormat.VIDEO
        if "brand_voice" in data:
            try:
                data["brand_voice"] = BrandVoice(data["brand_voice"])
            except ValueError:
                data["brand_voice"] = BrandVoice.DOCUMENTARY
        if "last_aspect" in data:
            data["last_aspect"] = AspectRatio(data["last_aspect"])
        if "last_voice" in data:
            data["last_voice"] = VoiceEngine(data["last_voice"])
        if "last_caption" in data:
            data["last_caption"] = CaptionStyle(data["last_caption"])
        if "last_transition" in data:
            data["last_transition"] = TransitionStyle(data["last_transition"])
        return cls(**data)
