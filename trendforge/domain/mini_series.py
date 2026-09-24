"""Living mini-series: episodes, pre-publish meetings, and comment-driven drafts.

Persisted as ``series.json`` under the app data root. Script bodies are plain
dicts produced by ``trendforge.domain.serialize.to_plain`` so Script Lab can
replace the drafter without changing this schema.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum

from trendforge.domain.models import new_id


MIN_EPISODE_MINUTES = 5.0
MAX_EPISODE_MINUTES = 10.0
DEFAULT_EPISODE_MINUTES = 7.5
MONITOR_WINDOW_HOURS = 48


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EpisodePhase(StrEnum):
    """Approve gate sits between ``in_meeting`` and ``render_ready``."""

    BRIEF = "brief"
    IN_MEETING = "in_meeting"
    APPROVED = "approved"
    RENDER_READY = "render_ready"
    MONITORING = "monitoring"


@dataclass(slots=True)
class CommentItem:
    author: str
    text: str
    like_count: int = 0
    published_at: str = ""


@dataclass(slots=True)
class RankedTheme:
    theme: str
    score: float
    comment_count: int
    examples: list[str] = field(default_factory=list)


@dataclass(slots=True)
class MeetingRecord:
    storyline: str = ""
    goals: str = ""
    tone: str = "documentary"
    notes: str = ""
    guardrail_acks: dict[str, bool] = field(default_factory=dict)
    approved: bool = False
    approved_at: str = ""


@dataclass(slots=True)
class MiniEpisode:
    id: str
    index: int
    topic: str
    title: str = ""
    phase: EpisodePhase = EpisodePhase.BRIEF
    target_minutes: float = DEFAULT_EPISODE_MINUTES
    meeting: MeetingRecord = field(default_factory=MeetingRecord)
    outline: str = ""
    script: dict | None = None
    project_id: str = ""
    output_path: str = ""
    video_id: str = ""
    published_at: str = ""
    monitor_until: str = ""
    source_episode_id: str = ""
    comments: list[CommentItem] = field(default_factory=list)
    themes: list[RankedTheme] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class MiniSeries:
    id: str
    title: str
    topic: str
    channel_name: str = ""
    created_at: str = ""
    updated_at: str = ""
    episodes: list[MiniEpisode] = field(default_factory=list)
    schema_version: int = 1


def new_episode(index: int, topic: str, *, title: str = "") -> MiniEpisode:
    now = _now_iso()
    return MiniEpisode(
        id=new_id("ep"),
        index=index,
        topic=topic,
        title=title or f"Episode {index}",
        created_at=now,
        updated_at=now,
    )


def new_series(title: str, topic: str, channel_name: str = "") -> MiniSeries:
    now = _now_iso()
    return MiniSeries(
        id=new_id("ms"),
        title=title.strip(),
        topic=topic.strip(),
        channel_name=channel_name.strip(),
        created_at=now,
        updated_at=now,
        episodes=[new_episode(1, topic.strip())],
    )
