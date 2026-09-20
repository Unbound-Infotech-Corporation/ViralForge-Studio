from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from trendforge.cinema.shots import CinemaShot


class LtxBackend(ABC):
    @abstractmethod
    def bridge(self, prev_clip: Path, shot: CinemaShot, dest: Path) -> Path:
        raise NotImplementedError


class DryRunLtxBackend(LtxBackend):
    """Short crossfade-friendly bridge clip (dry-run)."""

    def __init__(self, ffmpeg: str) -> None:
        self.ffmpeg = ffmpeg

    def bridge(self, prev_clip: Path, shot: CinemaShot, dest: Path) -> Path:
        # Reuse Wan dry-run card for a 1.2s bridge beat
        from trendforge.cinema.wan_backend import DryRunWanBackend

        bridge_shot = CinemaShot(
            index=shot.index,
            title=f"Bridge {shot.index}",
            narration="",
            visual_prompt=shot.visual_prompt,
            duration_sec=1.2,
            kind="bridge",
        )
        return DryRunWanBackend(self.ffmpeg).generate(bridge_shot, None, dest)
