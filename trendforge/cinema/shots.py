from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class CinemaShot:
    index: int
    title: str
    narration: str
    visual_prompt: str
    duration_sec: float = 4.0
    kind: str = "hero"  # hero | bridge | title | credits
    clip_path: str = ""


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
