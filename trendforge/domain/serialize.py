from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any

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
from trendforge.domain.models import (
    EpisodeBrief,
    GenerationRequest,
    Project,
    SeasonPlan,
    Shot,
    TrailerAttribution,
    VideoScript,
    YouTubePack,
)


def to_plain(obj: Any) -> Any:
    if is_dataclass(obj):
        return {k: to_plain(v) for k, v in asdict(obj).items()}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, list):
        return [to_plain(x) for x in obj]
    if isinstance(obj, tuple):
        return [to_plain(x) for x in obj]
    if isinstance(obj, dict):
        return {k: to_plain(v) for k, v in obj.items()}
    return obj


def dumps(obj: Any, **kwargs: Any) -> str:
    return json.dumps(to_plain(obj), indent=2, **kwargs)


def _enum(enum_cls: type, value: Any, default: Any) -> Any:
    try:
        return enum_cls(value)
    except (ValueError, TypeError, KeyError):
        return default


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _num(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def request_from_dict(data: dict[str, Any]) -> GenerationRequest:
    if not isinstance(data, dict):
        data = {}
    content_format = _enum(ContentFormat, data.get("content_format", ContentFormat.SHORTS), ContentFormat.SHORTS)
    length = _enum(LengthPreset, data.get("length", LengthPreset.SHORTS), LengthPreset.SHORTS)
    brand = _enum(BrandVoice, data.get("brand_voice", BrandVoice.DOCUMENTARY), BrandVoice.DOCUMENTARY)
    media_type = _enum(MediaType, data.get("media_type", MediaType.MOVIE), MediaType.MOVIE)
    topic = data.get("topic") or ""
    return GenerationRequest(
        topic=str(topic),
        category=_enum(TrendCategory, data.get("category", TrendCategory.CUSTOM), TrendCategory.CUSTOM),
        source_url=str(data.get("source_url") or ""),
        style=_enum(VideoStyle, data.get("style", VideoStyle.CINEMATIC), VideoStyle.CINEMATIC),
        length=length,
        content_format=content_format,
        aspect=_enum(AspectRatio, data.get("aspect", AspectRatio.WIDE), AspectRatio.WIDE),
        backend=_enum(BackendKind, data.get("backend", BackendKind.AUTO), BackendKind.AUTO),
        model_id=str(data.get("model_id") or "auto"),
        voice=_enum(VoiceEngine, data.get("voice", VoiceEngine.WINDOWS_SAPI), VoiceEngine.WINDOWS_SAPI),
        piper_voice=str(data.get("piper_voice") or "en_US-lessac-medium"),
        captions=_enum(CaptionStyle, data.get("captions", CaptionStyle.NONE), CaptionStyle.NONE),
        transition=_enum(TransitionStyle, data.get("transition", TransitionStyle.CROSSFADE), TransitionStyle.CROSSFADE),
        enable_voiceover=bool(data.get("enable_voiceover", True)),
        enable_captions=bool(data.get("enable_captions", False)),
        enable_music=bool(data.get("enable_music", True)),
        enable_intro=bool(data.get("enable_intro", True)),
        enable_outro=bool(data.get("enable_outro", True)),
        enable_upscale=bool(data.get("enable_upscale", False)),
        codec=data.get("codec", "h264"),
        music_volume=_num(data.get("music_volume", 0.12), 0.12),
        series_title=data.get("series_title", ""),
        episode_index=_int(data.get("episode_index", 1), 1),
        episode_count=_int(data.get("episode_count", 1), 1),
        brand_voice=brand,
        channel_name=data.get("channel_name", ""),
        channel_cta=data.get("channel_cta", "Subscribe for the next episode."),
        media_type=media_type,
        review_subject=data.get("review_subject", ""),
        trailer_url=data.get("trailer_url", ""),
        allowlist_entry_id=data.get("allowlist_entry_id", ""),
        gameplay_path=data.get("gameplay_path", ""),
        user_rating=_num(data.get("user_rating", 0), 0.0),
        user_rating_scale=str(data.get("user_rating_scale", "10")),
        user_opinion=data.get("user_opinion", ""),
        user_liked=data.get("user_liked", ""),
        user_disliked=data.get("user_disliked", ""),
        user_moments=data.get("user_moments", ""),
        user_verdict=data.get("user_verdict", ""),
        opinion_completed=bool(data.get("opinion_completed", False)),
    )


def script_from_dict(data: dict[str, Any] | None) -> VideoScript | None:
    if not data:
        return None
    shots = []
    for i, s in enumerate(data.get("shots") or []):
        if not isinstance(s, dict):
            continue
        segment_kind = _enum(ShotSegmentKind, s.get("segment_kind", ShotSegmentKind.COMMENTARY), ShotSegmentKind.COMMENTARY)
        shots.append(
        Shot(
            index=int(s.get("index", i)),
            title=s.get("title", f"Shot {i + 1}"),
            narration=s.get("narration", ""),
            visual_prompt=s.get("visual_prompt", ""),
            duration_sec=float(s.get("duration_sec", 5)),
            source_start_sec=float(s.get("source_start_sec", 0)),
            source_end_sec=float(s.get("source_end_sec", 0)),
            segment_kind=segment_kind,
            status=_enum(ClipStatus, s.get("status", ClipStatus.PENDING), ClipStatus.PENDING),
            clip_path=s.get("clip_path", ""),
            image_path=s.get("image_path", ""),
            audio_path=s.get("audio_path", ""),
            error=s.get("error", ""),
            notes=s.get("notes", ""),
        )
        )
    chapters = []
    for ch in data.get("chapters", []):
        if isinstance(ch, (list, tuple)) and len(ch) >= 2:
            chapters.append((str(ch[0]), str(ch[1])))
        elif isinstance(ch, dict):
            chapters.append((str(ch.get("time", "0:00")), str(ch.get("title", ""))))
    yt_raw = data.get("youtube") or {}
    youtube = YouTubePack(
        titles=list(yt_raw.get("titles", [])),
        thumbnail_text=str(yt_raw.get("thumbnail_text", "")),
        pinned_comment=str(yt_raw.get("pinned_comment", "")),
        community_post=str(yt_raw.get("community_post", "")),
        end_screen=str(yt_raw.get("end_screen", "")),
        hashtags=list(yt_raw.get("hashtags", [])),
    )
    season = None
    if data.get("season"):
        eps = [
            EpisodeBrief(
                index=int(e.get("index", i + 1)),
                title=str(e.get("title", f"Episode {i + 1}")),
                hook=str(e.get("hook", "")),
                thesis=str(e.get("thesis", "")),
                summary=str(e.get("summary", "")),
            )
            for i, e in enumerate(data["season"].get("episodes") or [])
        ]
        season = SeasonPlan(
            series_title=str(data["season"].get("series_title", "")),
            logline=str(data["season"].get("logline", "")),
            episodes=eps,
            bible=str(data["season"].get("bible", "")),
        )
    attributions = [
        TrailerAttribution(
            studio=str(a.get("studio", "")),
            channel_name=str(a.get("channel_name", "")),
            channel_id=str(a.get("channel_id", "")),
            video_title=str(a.get("video_title", "")),
            video_url=str(a.get("video_url", "")),
            release_date=str(a.get("release_date", "")),
            allowlist_entry_id=str(a.get("allowlist_entry_id", "")),
        )
        for a in (data.get("trailer_attributions") or [])
    ]
    return VideoScript(
        title=data.get("title", ""),
        hook=data.get("hook", ""),
        summary=data.get("summary", ""),
        youtube_description=data.get("youtube_description", ""),
        tags=list(data.get("tags", [])),
        chapters=chapters,
        shots=shots,
        style_notes=data.get("style_notes", ""),
        youtube=youtube,
        season=season,
        episode_index=int(data.get("episode_index", 1)),
        trailer_attributions=attributions,
    )


def project_from_dict(data: dict[str, Any]) -> Project:
    if not isinstance(data, dict):
        data = {}
    request_raw = data.get("request")
    if not isinstance(request_raw, dict):
        request_raw = {"topic": ""}
    return Project(
        id=str(data.get("id") or ""),
        title=str(data.get("title") or "Untitled"),
        created_at=str(data.get("created_at") or ""),
        updated_at=str(data.get("updated_at") or ""),
        request=request_from_dict(request_raw),
        script=script_from_dict(data.get("script")),
        stage=_enum(PipelineStage, data.get("stage", PipelineStage.IDLE), PipelineStage.IDLE),
        output_path=data.get("output_path", ""),
        thumbnail_path=data.get("thumbnail_path", ""),
        maestro_pipeline_id=data.get("maestro_pipeline_id", ""),
        maestro_job_ids=list(data.get("maestro_job_ids", [])),
        log_excerpt=data.get("log_excerpt", ""),
        folder=data.get("folder", ""),
    )
