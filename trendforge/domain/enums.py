from __future__ import annotations

from enum import StrEnum


class ThemeMode(StrEnum):
    DARK = "dark"
    LIGHT = "light"


class VideoStyle(StrEnum):
    EXPLAINER = "explainer"
    BREAKDOWN = "breakdown"
    CINEMATIC = "cinematic"
    DOCUMENTARY = "documentary"
    REACTION = "reaction"
    EDUCATIONAL = "educational"
    RANKING = "ranking"
    NEWS_RECAP = "news_recap"
    STORY = "story"
    REVIEW = "review"


class ContentFormat(StrEnum):
    """What the viewer is getting — drives length, aspect, and script shape."""

    SHORTS = "shorts"
    VIDEO = "video"
    LONG = "long"
    DOCUSERIES = "docuseries"
    SEASON = "season"
    REVIEW = "review"


class BrandVoice(StrEnum):
    DOCUMENTARY = "documentary"
    WITTY = "witty"
    NEWS = "news"
    CALM_TEACHER = "calm_teacher"
    BOLD = "bold"


class LengthPreset(StrEnum):
    SHORTS = "shorts"
    MID = "mid"
    LONG = "long"
    DOCUSERIES = "docuseries"


class AspectRatio(StrEnum):
    WIDE = "16:9"
    VERTICAL = "9:16"
    SQUARE = "1:1"


class CaptionStyle(StrEnum):
    CLEAN = "clean"
    BOLD = "bold"
    KARAOKE = "karaoke"
    MINIMAL = "minimal"
    NONE = "none"


class TransitionStyle(StrEnum):
    CUT = "cut"
    CROSSFADE = "crossfade"
    SLIDE = "slide"
    ZOOM = "zoom"


class VoiceEngine(StrEnum):
    WINDOWS_SAPI = "windows_sapi"
    PIPER = "piper"
    COQUI = "coqui"
    XTTS = "xtts"
    MAESTRO = "maestro"
    EDGE_TTS = "edge_tts"  # free cloud, optional, off by default
    NONE = "none"


class BackendKind(StrEnum):
    AUTO = "auto"
    SOURCE_CLIP = "source_clip"
    REVIEW = "review"
    MAESTRO_DIRECTOR = "maestro_director"
    MAESTRO_STUDIO = "maestro_studio"
    COMFYUI = "comfyui"
    QUICK_EXPLAINER = "quick_explainer"
    DIFFUSERS = "diffusers"
    NATIVE_CINEMA = "native_cinema"


class PipelineStage(StrEnum):
    IDLE = "idle"
    RESEARCH = "research"
    SCRIPT = "script"
    GENERATE = "generate"
    STITCH = "stitch"
    FINALIZE = "finalize"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ClipStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class TrendCategory(StrEnum):
    YOUTUBE = "youtube"
    NEWS = "news"
    MOVIES_TV = "movies_tv"
    GAMES = "games"
    VIRAL = "viral"
    CUSTOM = "custom"


class MediaType(StrEnum):
    MOVIE = "movie"
    SHOW = "show"
    GAME = "game"


class ShotSegmentKind(StrEnum):
    COMMENTARY = "commentary"
    TRAILER = "trailer"
    GAMEPLAY = "gameplay"
    TITLE_CARD = "title_card"
    CREDITS = "credits"
