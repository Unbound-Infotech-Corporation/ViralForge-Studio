"""Produce and next-episode draft. Cinema native path only.

Maestro, Quick Explainer, and dry-run text cards are refused. Rendering itself
stays on ``ProductionPipeline`` and only runs when ``cinema_dry_run`` is off,
so this module can build a real project package without painting title cards.
"""

from __future__ import annotations

from trendforge.domain.enums import (
    AspectRatio,
    BackendKind,
    BrandVoice,
    CaptionStyle,
    ContentFormat,
    LengthPreset,
    ShotSegmentKind,
    TransitionStyle,
    TrendCategory,
    VideoStyle,
    VoiceEngine,
)
from trendforge.domain.mini_series import EpisodePhase, MiniEpisode, MiniSeries, new_episode
from trendforge.domain.models import GenerationRequest, Project, VideoScript
from trendforge.domain.serialize import script_from_dict
from trendforge.services.mini_series.comments import CommentProvider, ManualPasteProvider, rank_themes
from trendforge.services.mini_series.script_hook import (
    MAX_RUNTIME_SEC,
    MIN_RUNTIME_SEC,
    DraftRequest,
    ScriptDrafter,
    ScriptEngineDrafter,
    runtime_seconds,
)
from trendforge.services.mini_series.state import (
    GateError,
    can_draft_next,
    can_import_comments,
    can_produce,
    mark_render_ready,
    record_comments,
)
from trendforge.services.mini_series.store import script_plain
from trendforge.services.ollama_client import OllamaClient
from trendforge.services.projects import ProjectStore
from trendforge.services.visual_policy import _TEXT_MARKERS

_BANNED_BACKENDS = {
    BackendKind.MAESTRO_DIRECTOR,
    BackendKind.MAESTRO_STUDIO,
    BackendKind.QUICK_EXPLAINER,
}
_BANNED_MODELS = {"maestro_director", "maestro_studio", "quick_explainer"}
_NATIVE_MODEL = "viralforge_cinema"


def cinema_render_block_reason(settings: object) -> str | None:
    if bool(getattr(settings, "cinema_dry_run", True)):
        return (
            "Mini Series will not render dry-run text cards. "
            "Install Wan weights and set cinema_dry_run to false, then use Render with Cinema."
        )
    return None


def build_cinema_request(
    episode: MiniEpisode,
    series: MiniSeries,
    settings: object,
) -> GenerationRequest:
    tone = episode.meeting.tone or "documentary"
    try:
        brand = BrandVoice(tone)
    except ValueError:
        brand = BrandVoice.DOCUMENTARY
    return GenerationRequest(
        topic=episode.topic,
        category=TrendCategory.CUSTOM,
        style=VideoStyle.DOCUMENTARY,
        length=LengthPreset.MID,
        content_format=ContentFormat.VIDEO,
        aspect=AspectRatio.WIDE,
        backend=BackendKind.NATIVE_CINEMA,
        model_id=_NATIVE_MODEL,
        voice=_voice_engine(settings),
        piper_voice=str(getattr(settings, "last_piper_voice", "en_US-lessac-medium")),
        captions=CaptionStyle.NONE,
        transition=TransitionStyle.CROSSFADE,
        enable_voiceover=True,
        enable_captions=False,
        enable_music=bool(getattr(settings, "enable_music", True)),
        enable_intro=False,
        enable_outro=True,
        codec=str(getattr(settings, "codec", "h264")),
        music_volume=float(getattr(settings, "default_music_volume", 0.12)),
        series_title=series.title,
        episode_index=episode.index,
        episode_count=max(len(series.episodes), episode.index),
        brand_voice=brand,
        channel_name=series.channel_name or str(getattr(settings, "channel_name", "")),
        channel_cta=str(getattr(settings, "channel_cta", "Subscribe for the next episode.")),
    )


def assert_cinema_only(request: GenerationRequest) -> None:
    if request.backend in _BANNED_BACKENDS or request.backend is not BackendKind.NATIVE_CINEMA:
        raise GateError("Mini Series produce is locked to ViralForge Cinema. Maestro and card paths are banned.")
    if request.model_id in _BANNED_MODELS or request.model_id != _NATIVE_MODEL:
        raise GateError("Mini Series model is viralforge_cinema. Text-card and Maestro models are banned.")


def assert_footage_script(script: VideoScript) -> None:
    if not script.shots:
        raise GateError("Cinema script has no shots.")
    total = runtime_seconds(script)
    if total < MIN_RUNTIME_SEC - 0.05 or total > MAX_RUNTIME_SEC + 0.05:
        raise GateError(f"Episode runtime must be 5–10 minutes (got {total:.0f}s).")
    for shot in script.shots:
        if shot.segment_kind in {ShotSegmentKind.TITLE_CARD, ShotSegmentKind.CREDITS}:
            raise GateError(f"Shot {shot.title!r} is a text card. Mini Series refuses it.")
        visual = (shot.visual_prompt or "").lower()
        for marker in _TEXT_MARKERS:
            if marker in visual:
                raise GateError(f"Shot {shot.title!r} still describes a text card ({marker}).")


def _voice_engine(settings: object) -> VoiceEngine:
    raw = getattr(settings, "last_voice", VoiceEngine.WINDOWS_SAPI)
    try:
        return raw if isinstance(raw, VoiceEngine) else VoiceEngine(str(raw))
    except ValueError:
        return VoiceEngine.WINDOWS_SAPI


def produce_episode(
    series: MiniSeries,
    episode: MiniEpisode,
    *,
    settings: object,
    project_store: ProjectStore,
    drafter: ScriptDrafter | None = None,
    ollama: OllamaClient | None = None,
    ollama_model: str = "",
) -> Project:
    """Draft a footage script, save a Cinema project, and open the publish gate."""
    decision = can_produce(episode)
    if not decision.allowed:
        raise GateError(decision.reason)
    drafter = drafter or ScriptEngineDrafter()
    request = build_cinema_request(episode, series, settings)
    assert_cinema_only(request)
    target = int(round(float(episode.target_minutes) * 60))
    draft = drafter.draft(
        DraftRequest(
            topic=episode.topic,
            series_title=series.title,
            episode_index=episode.index,
            episode_count=max(len(series.episodes), episode.index),
            tone=episode.meeting.tone,
            goals=episode.meeting.goals,
            storyline=episode.meeting.storyline,
            comment_themes=[],
            channel_name=request.channel_name,
            cta=request.channel_cta,
            target_seconds=target,
        ),
        ollama=ollama,
        ollama_model=ollama_model,
    )
    assert_footage_script(draft.script)
    project = Project.create((draft.script.title or episode.topic)[:80], request, "")
    folder = project_store.project_dir(project.id)
    folder.mkdir(parents=True, exist_ok=True)
    project.folder = str(folder)
    project.script = draft.script
    project.request = request
    project_store.save(project)
    episode.outline = draft.outline
    episode.script = script_plain(draft.script)
    episode.title = draft.script.title or episode.title
    mark_render_ready(episode, project.id)
    return project


def import_comments(
    episode: MiniEpisode,
    pasted_text: str,
    *,
    provider: CommentProvider | None = None,
) -> list:
    decision = can_import_comments(episode)
    if not decision.allowed:
        raise GateError(decision.reason)
    source = provider or ManualPasteProvider()
    comments = source.fetch(video_id=episode.video_id, pasted_text=pasted_text)
    themes = rank_themes(comments)
    record_comments(episode, comments, themes)
    return themes


def draft_next_episode(
    series: MiniSeries,
    episode: MiniEpisode,
    *,
    settings: object,
    drafter: ScriptDrafter | None = None,
    ollama: OllamaClient | None = None,
    ollama_model: str = "",
) -> MiniEpisode:
    """Create the next episode from ranked comments. It is not approved."""
    decision = can_draft_next(episode)
    if not decision.allowed:
        raise GateError(decision.reason)
    drafter = drafter or ScriptEngineDrafter()
    top = episode.themes[0]
    theme_names = [item.theme for item in episode.themes[:5]]
    topic = f"{series.topic}: {top.theme}"
    nxt = new_episode(episode.index + 1, topic, title=f"Episode {episode.index + 1}: {top.theme}")
    nxt.source_episode_id = episode.id
    nxt.target_minutes = episode.target_minutes
    cta = str(getattr(settings, "channel_cta", "Subscribe for the next episode."))
    channel = series.channel_name or str(getattr(settings, "channel_name", ""))
    draft = drafter.draft(
        DraftRequest(
            topic=topic,
            series_title=series.title,
            episode_index=nxt.index,
            episode_count=episode.index + 1,
            tone=episode.meeting.tone or "documentary",
            goals=f"Answer the top audience theme: {top.theme}.",
            storyline=(
                f"Follow episode {episode.index} by covering {', '.join(theme_names)}. "
                + " ".join(top.examples[:2])
            ),
            comment_themes=theme_names,
            channel_name=channel,
            cta=cta,
            target_seconds=int(round(float(nxt.target_minutes) * 60)),
        ),
        ollama=ollama,
        ollama_model=ollama_model,
    )
    assert_footage_script(draft.script)
    nxt.outline = draft.outline
    nxt.script = script_plain(draft.script)
    nxt.title = draft.script.title or nxt.title
    nxt.meeting.storyline = draft.outline
    nxt.meeting.goals = f"Answer the top audience theme: {top.theme}."
    nxt.meeting.tone = episode.meeting.tone or "documentary"
    nxt.meeting.notes = "Drafted from ranked comments. Approve this meeting before Produce."
    nxt.meeting.approved = False
    nxt.phase = EpisodePhase.IN_MEETING
    series.episodes.append(nxt)
    return nxt


def load_episode_script(episode: MiniEpisode) -> VideoScript | None:
    """Rehydrate the plain script stored on the episode. Produce writes a project copy too."""
    if not episode.script:
        return None
    return script_from_dict(episode.script)
