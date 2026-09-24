from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from trendforge.cinema.config import CinemaConfig
from trendforge.cinema.ltx_backend import DryRunLtxBackend, LtxBackend
from trendforge.cinema.shots import CinemaEpisode, CinemaShot
from trendforge.cinema.story_prompts import (
    CinemaPromptError,
    narrative_role,
    story_locked_prompt,
    synthesize_beats_from_vo,
)
from trendforge.cinema.wan_backend import DryRunWanBackend, WanBackend
from trendforge.services.stitcher import concat_cut, concat_xfade


@dataclass
class CinemaResult:
    final_path: Path
    clip_paths: list[Path] = field(default_factory=list)
    dry_run: bool = True
    backend: str = "native_cinema"


class CinemaDirector:
    """Maestro-like multi-shot director: Wan heroes + LTX bridges + stitch."""

    def __init__(
        self,
        config: CinemaConfig,
        wan: WanBackend | None = None,
        ltx: LtxBackend | None = None,
        ffmpeg: str = "ffmpeg",
    ) -> None:
        self.config = config
        self.ffmpeg = ffmpeg
        if wan is None:
            wan = DryRunWanBackend(ffmpeg)
        if ltx is None:
            ltx = DryRunLtxBackend(ffmpeg)
        self.wan = wan
        self.ltx = ltx

    def run(self, episode: CinemaEpisode, work_dir: Path, final_path: Path) -> CinemaResult:
        work_dir.mkdir(parents=True, exist_ok=True)
        clips: list[Path] = []
        prev: Path | None = None
        for shot in episode.shots:
            dest = work_dir / f"shot_{shot.index:03d}.mp4"
            clip = self.wan.generate(shot, None, dest)
            shot.clip_path = str(clip)
            if (
                self.config.bridge_with_ltx
                and prev is not None
                and shot.kind == "hero"
            ):
                bridge_dest = work_dir / f"bridge_{shot.index:03d}.mp4"
                bridge = self.ltx.bridge(prev, shot, bridge_dest)
                clips.append(bridge)
            clips.append(clip)
            prev = clip

        final_path.parent.mkdir(parents=True, exist_ok=True)
        if len(clips) == 1:
            import shutil

            shutil.copy2(clips[0], final_path)
        elif self.config.xfade_sec > 0 and len(clips) >= 2:
            try:
                concat_xfade(clips, final_path, self.ffmpeg, self.config.xfade_sec)
            except Exception:
                concat_cut(clips, final_path, self.ffmpeg)
        else:
            concat_cut(clips, final_path, self.ffmpeg)

        return CinemaResult(
            final_path=final_path,
            clip_paths=clips,
            dry_run=self.config.dry_run,
            backend="native_cinema",
        )


def episode_from_script_shots(
    title: str,
    topic: str,
    shots_payload: list[dict],
    *,
    series_title: str = "",
    episode_index: int = 1,
    episode_count: int = 1,
    style: str = "",
    category: str = "",
    voiceover: str = "",
) -> CinemaEpisode:
    """Build an episode whose Wan prompt is locked to each beat.

    Incoming ``visual_prompt`` values are ignored. A headline, or a stock
    B-roll line that merely repeats the headline, must not become the picture.
    Missing beats raise CinemaPromptError unless ``voiceover`` can be split
    into a minimal beat list.
    """
    rows = [_shot_row(i, raw) for i, raw in enumerate(shots_payload or [])]
    if not rows:
        rows = [
            _shot_row(i, raw)
            for i, raw in enumerate(synthesize_beats_from_vo(voiceover, topic=topic))
        ]
    if not rows:
        raise CinemaPromptError(
            "Cinema has no script beats or voiceover to lock shots to. "
            "Refusing to render a headline-only prompt."
        )
    shots: list[CinemaShot] = []
    count = len(rows)
    for i, row in enumerate(rows):
        role = narrative_role(row["title"], i, count)
        prompt = story_locked_prompt(
            topic=topic,
            script_title=title,
            shot_title=row["title"],
            narration=row["narration"],
            role=role,
            index=i,
            style=style,
            category=category,
        )
        shots.append(
            CinemaShot(
                index=i + 1,
                title=row["title"],
                narration=row["narration"],
                visual_prompt=prompt,
                duration_sec=row["duration_sec"],
                kind=row["kind"],
            )
        )
    return CinemaEpisode(
        title=title,
        topic=topic,
        series_title=series_title,
        episode_index=episode_index,
        episode_count=episode_count,
        shots=shots,
    )


def _shot_row(index: int, raw: dict) -> dict:
    duration = raw.get("duration_sec", raw.get("duration", 4.0))
    try:
        seconds = float(duration or 4.0)
    except (TypeError, ValueError):
        seconds = 4.0
    return {
        "title": str(raw.get("title") or raw.get("heading") or f"Shot {index + 1}"),
        "narration": str(raw.get("narration") or raw.get("voiceover") or raw.get("text") or ""),
        "duration_sec": seconds,
        "kind": str(raw.get("kind") or "hero"),
    }
