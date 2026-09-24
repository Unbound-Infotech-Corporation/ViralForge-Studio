from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from trendforge.domain.enums import (
    AspectRatio,
    BackendKind,
    BrandVoice,
    CaptionStyle,
    ClipStatus,
    ContentFormat,
    LengthPreset,
    MediaType,
    PipelineStage,
    ShotSegmentKind,
    TransitionStyle,
    TrendCategory,
    VideoStyle,
    VoiceEngine,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str = "") -> str:
    token = uuid4().hex[:12]
    return f"{prefix}{token}" if prefix else token


@dataclass(slots=True)
class HardwareProfile:
    gpu_name: str = "Unknown"
    gpu_vendor: str = "unknown"
    vram_total_gb: float = 0.0
    vram_free_gb: float = 0.0
    ram_total_gb: float = 0.0
    ram_available_gb: float = 0.0
    cuda_available: bool = False
    nvidia_driver: str = ""
    recommended_backend: BackendKind = BackendKind.QUICK_EXPLAINER
    recommended_model_id: str = "quick_explainer"
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ModelOption:
    id: str
    name: str
    backend: BackendKind
    family: str
    description: str
    vram_gb: float
    disk_gb: float
    quality: int  # 1-5
    speed: int  # 1-5, higher is faster
    maestro_type_hint: str = ""
    supports_audio: bool = False
    is_paid: bool = False
    downloaded: bool | None = None
    tooltip: str = ""
    installable: bool = False
    install_id: str = ""
    hidden: bool = False
    mark: str = ""

    def fits(self, vram_gb: float) -> bool:
        if self.vram_gb <= 0:
            return True
        return vram_gb + 0.4 >= self.vram_gb


@dataclass(slots=True)
class TrendItem:
    id: str
    title: str
    category: TrendCategory
    source: str
    url: str = ""
    thumbnail: str = ""
    score_label: str = ""
    summary: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TrailerAttribution:
    studio: str = ""
    channel_name: str = ""
    channel_id: str = ""
    video_title: str = ""
    video_url: str = ""
    release_date: str = ""
    allowlist_entry_id: str = ""


@dataclass(slots=True)
class Shot:
    index: int
    title: str
    narration: str
    visual_prompt: str
    duration_sec: float = 5.0
    source_start_sec: float = 0.0
    source_end_sec: float = 0.0
    segment_kind: ShotSegmentKind = ShotSegmentKind.COMMENTARY
    status: ClipStatus = ClipStatus.PENDING
    clip_path: str = ""
    image_path: str = ""
    audio_path: str = ""
    error: str = ""
    notes: str = ""


@dataclass(slots=True)
class EpisodeBrief:
    index: int
    title: str
    hook: str
    thesis: str
    summary: str


@dataclass(slots=True)
class SeasonPlan:
    series_title: str
    logline: str
    episodes: list[EpisodeBrief] = field(default_factory=list)
    bible: str = ""


@dataclass(slots=True)
class YouTubePack:
    titles: list[str] = field(default_factory=list)
    thumbnail_text: str = ""
    pinned_comment: str = ""
    community_post: str = ""
    end_screen: str = ""
    hashtags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class VideoScript:
    title: str
    hook: str
    summary: str
    youtube_description: str
    tags: list[str] = field(default_factory=list)
    chapters: list[tuple[str, str]] = field(default_factory=list)  # (timestamp, title)
    shots: list[Shot] = field(default_factory=list)
    style_notes: str = ""
    youtube: YouTubePack = field(default_factory=YouTubePack)
    season: SeasonPlan | None = None
    episode_index: int = 1
    trailer_attributions: list[TrailerAttribution] = field(default_factory=list)


@dataclass(slots=True)
class GenerationRequest:
    topic: str
    category: TrendCategory = TrendCategory.CUSTOM
    source_url: str = ""
    style: VideoStyle = VideoStyle.CINEMATIC
    length: LengthPreset = LengthPreset.SHORTS
    content_format: ContentFormat = ContentFormat.SHORTS
    aspect: AspectRatio = AspectRatio.WIDE
    backend: BackendKind = BackendKind.AUTO
    model_id: str = "auto"
    voice: VoiceEngine = VoiceEngine.WINDOWS_SAPI
    piper_voice: str = "en_US-lessac-medium"
    captions: CaptionStyle = CaptionStyle.NONE
    transition: TransitionStyle = TransitionStyle.CROSSFADE
    enable_voiceover: bool = True
    enable_captions: bool = False
    enable_music: bool = True
    enable_intro: bool = True
    enable_outro: bool = True
    enable_upscale: bool = False
    codec: str = "h264"
    music_volume: float = 0.12
    series_title: str = ""
    episode_index: int = 1
    episode_count: int = 1
    brand_voice: BrandVoice = BrandVoice.DOCUMENTARY
    channel_name: str = ""
    channel_cta: str = "Subscribe for the next episode."
    # Movie / show / game review pipeline
    media_type: MediaType = MediaType.MOVIE
    review_subject: str = ""
    trailer_url: str = ""
    allowlist_entry_id: str = ""
    gameplay_path: str = ""
    user_rating: float = 0.0
    user_rating_scale: str = "10"
    user_opinion: str = ""
    user_liked: str = ""
    user_disliked: str = ""
    user_moments: str = ""
    user_verdict: str = ""
    opinion_completed: bool = False


@dataclass(slots=True)
class PipelineProgress:
    stage: PipelineStage = PipelineStage.IDLE
    percent: int = 0
    message: str = "Ready"
    clip_index: int = 0
    clip_total: int = 0
    eta_label: str = ""
    cancellable: bool = False
    resumable: bool = False


@dataclass(slots=True)
class Project:
    id: str
    title: str
    created_at: str
    updated_at: str
    request: GenerationRequest
    script: VideoScript | None = None
    stage: PipelineStage = PipelineStage.IDLE
    output_path: str = ""
    thumbnail_path: str = ""
    maestro_pipeline_id: str = ""
    maestro_job_ids: list[str] = field(default_factory=list)
    log_excerpt: str = ""
    folder: str = ""

    @staticmethod
    def create(title: str, request: GenerationRequest, folder: str) -> Project:
        now = _now_iso()
        return Project(
            id=new_id("p"),
            title=title,
            created_at=now,
            updated_at=now,
            request=request,
            folder=folder,
        )
