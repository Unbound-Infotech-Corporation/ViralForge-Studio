from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from trendforge.cinema.config import CinemaConfig
from trendforge.cinema.ltx_backend import DryRunLtxBackend, LtxBackend
from trendforge.cinema.shots import CinemaEpisode, CinemaShot
from trendforge.cinema.wan_backend import DryRunWanBackend, WanBackend
from trendforge.services.stitcher import concat_cut, concat_xfade


@dataclass
class CinemaResult:
    final_path: Path
    clip_paths: list[Path] = field(default_factory=list)
    dry_run: bool = True
    backend: str = "native_cinema"
    card_stand_in: bool = False


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

    def uses_card_standin(self) -> bool:
        """True when hero shots are ffmpeg title cards, not a video model."""
        return isinstance(self.wan, DryRunWanBackend)

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
            dry_run=self.config.dry_run or self.uses_card_standin(),
            backend="native_cinema",
            card_stand_in=self.uses_card_standin(),
        )


def episode_from_script_shots(
    title: str,
    topic: str,
    shots_payload: list[dict],
    *,
    series_title: str = "",
    episode_index: int = 1,
    episode_count: int = 1,
) -> CinemaEpisode:
    shots: list[CinemaShot] = []
    for i, s in enumerate(shots_payload):
        shots.append(
            CinemaShot(
                index=i + 1,
                title=str(s.get("title") or s.get("heading") or f"Shot {i + 1}"),
                narration=str(s.get("narration") or s.get("voiceover") or s.get("text") or ""),
                visual_prompt=str(
                    s.get("visual_prompt")
                    or s.get("prompt")
                    or s.get("visual")
                    or s.get("narration")
                    or ""
                ),
                duration_sec=float(s.get("duration_sec") or s.get("duration") or 4.0),
                kind=str(s.get("kind") or "hero"),
            )
        )
    if not shots:
        shots = [
            CinemaShot(
                index=1,
                title=title or "Opening",
                narration=topic,
                visual_prompt=topic,
                duration_sec=4.0,
            )
        ]
    return CinemaEpisode(
        title=title,
        topic=topic,
        series_title=series_title,
        episode_index=episode_index,
        episode_count=episode_count,
        shots=shots,
    )
