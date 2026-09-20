from __future__ import annotations

from pathlib import Path

import pytest

from trendforge.cinema.config import CinemaConfig
from trendforge.cinema.director import CinemaDirector
from trendforge.cinema.shots import CinemaEpisode, CinemaShot


def _ffmpeg() -> str:
    from trendforge.services.ffmpeg_tools import find_ffmpeg

    ff = find_ffmpeg()
    if not ff:
        pytest.skip("ffmpeg not available")
    return ff


def test_native_cinema_three_shots_to_mp4(tmp_path: Path) -> None:
    ffmpeg = _ffmpeg()
    episode = CinemaEpisode(
        title="Robot Boxing Pilot",
        topic="Arena lights and chrome fists",
        shots=[
            CinemaShot(1, "Title", "Welcome to the arena", "neon boxing ring", 2.0, "title"),
            CinemaShot(2, "Hero", "Chrome fists clash", "robot boxers mid-punch", 3.0, "hero"),
            CinemaShot(3, "Close", "Crowd erupts", "crowd silhouettes under lights", 2.5, "hero"),
        ],
    )
    cfg = CinemaConfig(dry_run=True, bridge_with_ltx=True, xfade_sec=0.2)
    director = CinemaDirector(cfg, ffmpeg=ffmpeg)
    final = tmp_path / "final.mp4"
    result = director.run(episode, tmp_path / "work", final)
    assert result.final_path.exists()
    assert result.final_path.stat().st_size > 1000
    assert len(result.clip_paths) >= 3
    assert result.backend == "native_cinema"
