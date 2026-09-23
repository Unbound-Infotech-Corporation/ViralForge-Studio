from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class CinemaShot:
    index: int
    title: str
    narration: str
    visual_prompt: str
    duration_sec: float = 4.0
    kind: str = "hero"  # hero | bridge | beat | title | credits
    clip_path: str = ""
    keyframe_path: str = ""


def keyframe_for_shot(shot: CinemaShot) -> Path | None:
    """Return an existing still for TI2V image-to-video, if the shot has one."""
    raw = (shot.keyframe_path or "").strip()
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_file() else None


@dataclass
class CinemaEpisode:
    title: str
    topic: str
    series_title: str = ""
    episode_index: int = 1
    episode_count: int = 1
    shots: list[CinemaShot] = field(default_factory=list)

    @property
    def target_duration(self) -> float:
        return sum(s.duration_sec for s in self.shots)
