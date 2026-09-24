"""Script draft hook for mini-series episodes.

``ScriptDrafter`` is the interface Script Lab should implement. The default
``ScriptEngineDrafter`` calls ``trendforge.services.script_engine.generate_script``
(Ollama when a client is passed, otherwise the local template). Picture prompts
go through the existing footage sanitizer so text cards never survive.

TODO(script-lab): replace ``ScriptEngineDrafter`` with the Script Lab module
once it lands. Keep ``draft(DraftRequest) -> DraftResult``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from trendforge.domain.enums import BrandVoice, ContentFormat, LengthPreset, ShotSegmentKind, VideoStyle
from trendforge.domain.models import VideoScript
from trendforge.services.ollama_client import OllamaClient
from trendforge.services.script_engine import generate_script
from trendforge.services.visual_policy import sanitize_visual_prompt

MIN_RUNTIME_SEC = 300.0
MAX_RUNTIME_SEC = 600.0
_MIN_SHOT_SEC = 4.0


@dataclass(slots=True)
class DraftRequest:
    topic: str
    series_title: str
    episode_index: int
    episode_count: int
    tone: str
    goals: str
    storyline: str
    comment_themes: list[str] = field(default_factory=list)
    channel_name: str = ""
    cta: str = "Subscribe for the next episode."
    target_seconds: int = 450


@dataclass(slots=True)
class DraftResult:
    script: VideoScript
    outline: str


class ScriptDrafter(Protocol):
    def draft(
        self,
        request: DraftRequest,
        *,
        ollama: OllamaClient | None = None,
        ollama_model: str = "",
    ) -> DraftResult:
        """Return a footage-only script and a human-readable outline."""


def brand_from_tone(tone: str) -> BrandVoice:
    try:
        return BrandVoice(tone)
    except ValueError:
        return BrandVoice.DOCUMENTARY


def outline_from_script(script: VideoScript) -> str:
    lines = [script.hook.strip(), ""]
    for shot in script.shots:
        narration = " ".join((shot.narration or "").split())
        if len(narration) > 180:
            narration = narration[:177] + "..."
        lines.append(f"- {shot.title}: {narration}")
    return "\n".join(lines).strip()


def lock_script_to_footage(script: VideoScript, *, topic: str) -> VideoScript:
    """Force commentary shots and sanitized photographed prompts."""
    for shot in script.shots:
        if shot.segment_kind in {ShotSegmentKind.TITLE_CARD, ShotSegmentKind.CREDITS}:
            shot.segment_kind = ShotSegmentKind.COMMENTARY
        shot.visual_prompt = sanitize_visual_prompt(
            shot.visual_prompt,
            topic=topic,
            title=shot.title,
            narration=shot.narration,
        )
    return script


def fit_runtime(script: VideoScript, target_seconds: float) -> VideoScript:
    """Scale shot durations into the 5–10 minute episode window."""
    if not script.shots:
        raise ValueError("Script has no shots to time.")
    target = min(MAX_RUNTIME_SEC, max(MIN_RUNTIME_SEC, float(target_seconds)))
    current = sum(max(0.1, shot.duration_sec) for shot in script.shots)
    scale = target / current
    for shot in script.shots:
        shot.duration_sec = round(max(_MIN_SHOT_SEC, shot.duration_sec * scale), 2)
    total = sum(shot.duration_sec for shot in script.shots)
    drift = round(target - total, 2)
    script.shots[-1].duration_sec = round(max(_MIN_SHOT_SEC, script.shots[-1].duration_sec + drift), 2)
    return script


def runtime_seconds(script: VideoScript) -> float:
    return round(sum(shot.duration_sec for shot in script.shots), 2)


class ScriptEngineDrafter:
    """Default drafter. Script Lab can substitute another ``ScriptDrafter``."""

    def draft(
        self,
        request: DraftRequest,
        *,
        ollama: OllamaClient | None = None,
        ollama_model: str = "",
    ) -> DraftResult:
        themes = ", ".join(request.comment_themes[:5]) or "none yet"
        extra = (
            f"Mini series episode. Target runtime {request.target_seconds} seconds "
            f"(hard window {int(MIN_RUNTIME_SEC)}-{int(MAX_RUNTIME_SEC)} seconds).\n"
            f"Storyline: {request.storyline.strip()}\n"
            f"Goals: {request.goals.strip()}\n"
            f"Audience themes to answer: {themes}\n"
            "Picture is photographed cinematic footage only. "
            "Do not request title cards, kinetic typography, Maestro, or explainer slides."
        )
        script = generate_script(
            request.topic,
            VideoStyle.DOCUMENTARY,
            LengthPreset.MID,
            extra_context=extra,
            ollama=ollama,
            ollama_model=ollama_model,
            content_format=ContentFormat.VIDEO,
            brand=brand_from_tone(request.tone),
            channel_name=request.channel_name,
            cta=request.cta,
            episode_index=request.episode_index,
            episode_count=max(request.episode_count, request.episode_index),
            series_title=request.series_title,
        )
        script.episode_index = request.episode_index
        lock_script_to_footage(script, topic=request.topic)
        fit_runtime(script, request.target_seconds)
        return DraftResult(script=script, outline=outline_from_script(script))
