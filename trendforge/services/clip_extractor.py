from __future__ import annotations

from pathlib import Path

from trendforge.logging_setup import get_logger
from trendforge.services.ffmpeg_tools import require_ok, run_ffmpeg
from trendforge.services.stitcher import probe_duration

log = get_logger("clip_extractor")


def _scale_pad_filter(width: int, height: int) -> str:
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,format=yuv420p"
    )


def trim_source_clip(
    source: Path,
    start_sec: float,
    end_sec: float,
    dest: Path,
    ffmpeg: str,
    size: tuple[int, int],
    *,
    fps: int = 30,
) -> Path:
    """Extract a segment from source footage, scaled to the target frame size."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    start = max(0.0, start_sec)
    end = max(start + 0.5, end_sec)
    duration = end - start
    w, h = size
    vf = _scale_pad_filter(w, h)
    proc = run_ffmpeg(
        [
            "-ss",
            f"{start:.3f}",
            "-i",
            str(source),
            "-t",
            f"{duration:.3f}",
            "-vf",
            vf,
            "-r",
            str(fps),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(dest),
        ],
        ffmpeg,
    )
    require_ok(proc, "trim source clip")
    return dest


def mux_narration(
    video: Path,
    narration: Path,
    dest: Path,
    ffmpeg: str,
    *,
    duck_original: float = 0.0,
) -> Path:
    """Replace or duck source audio and mux narration WAV/MP3."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if duck_original > 0.01:
        proc = run_ffmpeg(
            [
                "-i",
                str(video),
                "-i",
                str(narration),
                "-filter_complex",
                f"[0:a]volume={duck_original}[bg];"
                f"[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[vo];"
                f"[bg][vo]amix=inputs=2:duration=longest:dropout_transition=2[a]",
                "-map",
                "0:v",
                "-map",
                "[a]",
                "-shortest",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                str(dest),
            ],
            ffmpeg,
        )
        if proc.returncode != 0:
            log.warning("duck mix failed, replacing audio with narration only")
            duck_original = 0.0
    if duck_original <= 0.01:
        proc = run_ffmpeg(
            [
                "-i",
                str(video),
                "-i",
                str(narration),
                "-map",
                "0:v",
                "-map",
                "1:a",
                "-shortest",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                str(dest),
            ],
            ffmpeg,
        )
        require_ok(proc, "mux narration")
    return dest


def build_shot_clip(
    source: Path,
    start_sec: float,
    end_sec: float,
    narration: Path | None,
    dest: Path,
    ffmpeg: str,
    size: tuple[int, int],
    *,
    duck_original: float = 0.0,
) -> Path:
    """Trim source footage and attach narration audio."""
    work = dest.parent / "_work"
    work.mkdir(parents=True, exist_ok=True)
    trimmed = work / f"{dest.stem}_trim.mp4"
    trim_source_clip(source, start_sec, end_sec, trimmed, ffmpeg, size)
    if narration and narration.exists():
        mux_narration(trimmed, narration, dest, ffmpeg, duck_original=duck_original)
        trimmed.unlink(missing_ok=True)
        return dest
    dest.write_bytes(trimmed.read_bytes())
    trimmed.unlink(missing_ok=True)
    return dest


def sync_shot_duration(start_sec: float, end_sec: float, audio: Path, ffmpeg: str, pad: float = 0.35) -> float:
    """Return end timestamp extended to fit narration audio."""
    try:
        audio_len = probe_duration(audio, ffmpeg)
    except Exception:
        return end_sec
    needed = max(end_sec - start_sec, audio_len + pad)
    return start_sec + needed
