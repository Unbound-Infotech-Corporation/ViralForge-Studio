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


def request_from_dict(data: dict[str, Any]) -> GenerationRequest:
    fmt = data.get("content_format", ContentFormat.SHORTS)
    try:
        content_format = ContentFormat(fmt)
    except ValueError:
        content_format = ContentFormat.SHORTS
    length_raw = data.get("length", LengthPreset.SHORTS)
    try:
        length = LengthPreset(length_raw)
    except ValueError:
        length = LengthPreset.SHORTS
    try:
        brand = BrandVoice(data.get("brand_voice", BrandVoice.DOCUMENTARY))
    except ValueError:
        brand = BrandVoice.DOCUMENTARY
    try:
        media_type = MediaType(data.get("media_type", MediaType.MOVIE))
    except ValueError:
        media_type = MediaType.MOVIE
    return GenerationRequest(
        topic=data.get("topic", ""),
        category=TrendCategory(data.get("category", TrendCategory.CUSTOM)),
        source_url=data.get("source_url", ""),
        style=VideoStyle(data.get("style", VideoStyle.CINEMATIC)),
        length=length,
        content_format=content_format,
        aspect=AspectRatio(data.get("aspect", AspectRatio.WIDE)),
        backend=BackendKind(data.get("backend", BackendKind.AUTO)),
        model_id=data.get("model_id", "auto"),
        voice=VoiceEngine(data.get("voice", VoiceEngine.WINDOWS_SAPI)),
        piper_voice=data.get("piper_voice", "en_US-lessac-medium"),
        captions=CaptionStyle(data.get("captions", CaptionStyle.NONE)),
        transition=TransitionStyle(data.get("transition", TransitionStyle.CROSSFADE)),
        enable_voiceover=bool(data.get("enable_voiceover", True)),
        enable_captions=bool(data.get("enable_captions", False)),
        enable_music=bool(data.get("enable_music", True)),
        enable_intro=bool(data.get("enable_intro", True)),
        enable_outro=bool(data.get("enable_outro", True)),
        enable_upscale=bool(data.get("enable_upscale", False)),
        codec=data.get("codec", "h264"),
        music_volume=float(data.get("music_volume", 0.12)),
        series_title=data.get("series_title", ""),
        episode_index=int(data.get("episode_index", 1)),
        episode_count=int(data.get("episode_count", 1)),
        brand_voice=brand,
        channel_name=data.get("channel_name", ""),
        channel_cta=data.get("channel_cta", "Subscribe for the next episode."),
        media_type=media_type,
        review_subject=data.get("review_subject", ""),
        trailer_url=data.get("trailer_url", ""),
        allowlist_entry_id=data.get("allowlist_entry_id", ""),
        gameplay_path=data.get("gameplay_path", ""),
        user_rating=float(data.get("user_rating", 0)),
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
    for i, s in enumerate(data.get("shots", [])):
        try:
            segment_kind = ShotSegmentKind(s.get("segment_kind", ShotSegmentKind.COMMENTARY))
        except ValueError:
            segment_kind = ShotSegmentKind.COMMENTARY
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
            status=ClipStatus(s.get("status", ClipStatus.PENDING)),
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
    return Project(
        id=data.get("id", ""),
        title=data.get("title", "Untitled"),
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
        request=request_from_dict(data.get("request", {"topic": ""})),
        script=script_from_dict(data.get("script")),
        stage=PipelineStage(data.get("stage", PipelineStage.IDLE)),
        output_path=data.get("output_path", ""),
        thumbnail_path=data.get("thumbnail_path", ""),
        maestro_pipeline_id=data.get("maestro_pipeline_id", ""),
        maestro_job_ids=list(data.get("maestro_job_ids", [])),
        log_excerpt=data.get("log_excerpt", ""),
        folder=data.get("folder", ""),
    )
