from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from trendforge.bootstrap import AppDirs
from trendforge.services.script_lab_browser import normalize_browser_preference
from trendforge.domain.catalog import is_hidden_model
from trendforge.domain.enums import (
    AspectRatio,
    CaptionStyle,
    ContentFormat,
    LengthPreset,
    ThemeMode,
    TransitionStyle,
    BrandVoice,
    ScriptAiProvider,
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
    # Script AI (BYOK). The key stays in settings.json with the rest of the
    # local config and is omitted from repr so logs of the object stay clean.
    script_ai_provider: ScriptAiProvider = ScriptAiProvider.OLLAMA
    script_ai_api_key: str = field(default="", repr=False)
    script_ai_base_url: str = ""
    script_ai_model: str = ""
    # "default" uses the OS browser. "edge" and "chrome" launch that browser when it is installed.
    script_lab_system_browser: str = "default"
    show_console_on_produce: bool = True
    console_hint_shown: bool = False

    _path: Path | None = field(default=None, repr=False, compare=False)

    @classmethod
    def load(cls, dirs: AppDirs) -> AppSettings:
        path = dirs.settings_file
        if not path.exists():
            settings = cls()
            settings._path = path
            settings.save()
            return settings
        try:
            raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeError):
            settings = cls()
            settings._path = path
            return settings
        if not isinstance(raw, dict):
            settings = cls()
            settings._path = path
            return settings
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
        data["theme"] = _enum(ThemeMode, data.get("theme"), ThemeMode.DARK)
        data["last_style"] = _enum(VideoStyle, data.get("last_style"), VideoStyle.CINEMATIC)
        data["last_length"] = _enum(LengthPreset, data.get("last_length"), LengthPreset.SHORTS)
        data["last_format"] = _enum(ContentFormat, data.get("last_format"), ContentFormat.VIDEO)
        data["brand_voice"] = _enum(BrandVoice, data.get("brand_voice"), BrandVoice.DOCUMENTARY)
        data["last_aspect"] = _enum(AspectRatio, data.get("last_aspect"), AspectRatio.WIDE)
        data["last_voice"] = _enum(VoiceEngine, data.get("last_voice"), VoiceEngine.WINDOWS_SAPI)
        data["last_caption"] = _enum(CaptionStyle, data.get("last_caption"), CaptionStyle.NONE)
        data["last_transition"] = _enum(TransitionStyle, data.get("last_transition"), TransitionStyle.CROSSFADE)
        data["script_ai_provider"] = _enum(
            ScriptAiProvider, data.get("script_ai_provider"), ScriptAiProvider.OLLAMA
        )
        if data.get("script_ai_api_key") is None:
            data["script_ai_api_key"] = ""
        if data.get("script_ai_base_url") is None:
            data["script_ai_base_url"] = ""
        if data.get("script_ai_model") is None:
            data["script_ai_model"] = ""
        data["script_lab_system_browser"] = normalize_browser_preference(
            data.get("script_lab_system_browser", "default")
        )
        if is_hidden_model(str(data.get("last_model_id") or "")):
            data["last_model_id"] = "auto"
        if "installed_items" in data and not isinstance(data["installed_items"], list):
            data["installed_items"] = []
        if "extra_model_scan_dirs" in data and not isinstance(data["extra_model_scan_dirs"], list):
            data["extra_model_scan_dirs"] = []
        if "show_console_on_produce" in data:
            data["show_console_on_produce"] = bool(data["show_console_on_produce"])
        if "console_hint_shown" in data:
            data["console_hint_shown"] = bool(data["console_hint_shown"])
        if "prefer_native_cinema" in data:
            data["prefer_native_cinema"] = bool(data["prefer_native_cinema"])
        if "cinema_dry_run" in data:
            data["cinema_dry_run"] = bool(data["cinema_dry_run"])
        return cls(**data)


def _enum(enum_cls: type, value: Any, default: Any) -> Any:
    if value is None:
        return default
    try:
        return enum_cls(value)
    except (ValueError, TypeError, KeyError):
        return default
