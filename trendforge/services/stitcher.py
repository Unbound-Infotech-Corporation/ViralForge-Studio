from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from trendforge.domain.enums import CaptionStyle, TransitionStyle
from trendforge.logging_setup import get_logger
from trendforge.services.ffmpeg_tools import find_ffmpeg, require_ok, run_ffmpeg

log = get_logger("stitcher")


def _flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


def probe_duration(path: Path, ffmpeg: str) -> float:
    # Prefer ffprobe; fall back to ffmpeg -i parse
    from trendforge.services.ffmpeg_tools import find_ffprobe

    probe = find_ffprobe(ffmpeg)
    if probe:
        proc = subprocess.run(
            [
                probe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            creationflags=_flags(),
        )
        if proc.returncode == 0:
            try:
                return float(proc.stdout.strip())
            except ValueError:
                pass
    proc = subprocess.run(
        [ffmpeg, "-i", str(path)],
        capture_output=True,
        text=True,
        creationflags=_flags(),
    )
    import re

    match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", proc.stderr or "")
    if not match:
        return 5.0
    h, m, s = match.groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def ken_burns_clip(
    image: Path,
    dest: Path,
    duration: float,
    size: tuple[int, int],
    ffmpeg: str,
    audio: Path | None = None,
    fps: int = 30,
) -> Path:
    w, h = size
    dur = max(1.2, duration)
    # zoompan uses frames; d is frame count
    frames = max(int(dur * fps), fps)
    filter_v = (
        f"scale={w * 2}:{h * 2},zoompan=z='min(zoom+0.0008,1.12)':d={frames}:"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={fps},"
        f"format=yuv420p"
    )
    args = ["-loop", "1", "-i", str(image)]
    if audio and audio.exists():
        args += ["-i", str(audio), "-filter_complex", f"[0:v]{filter_v}[v]", "-map", "[v]", "-map", "1:a"]
        args += ["-shortest", "-t", f"{dur:.3f}"]
    else:
        args += ["-filter_complex", filter_v, "-t", f"{dur:.3f}", "-an"]
    args += [
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(dest),
    ]
    proc = run_ffmpeg(args, ffmpeg)
    if proc.returncode != 0:
        # Simpler fallback without zoompan
        log.warning("zoompan failed, using static scale: %s", (proc.stderr or "")[-400:])
        args = ["-loop", "1", "-i", str(image), "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,format=yuv420p", "-t", f"{dur:.3f}"]
        if audio and audio.exists():
            args = ["-loop", "1", "-i", str(image), "-i", str(audio),
                    "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
                    "-shortest", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                    "-c:a", "aac", "-b:a", "192k", str(dest)]
        else:
            args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-an", str(dest)]
        proc = run_ffmpeg(args, ffmpeg)
        require_ok(proc, "clip encode")
    else:
        require_ok(proc, "ken burns encode")
    return dest


def concat_cut(clips: list[Path], dest: Path, ffmpeg: str) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as handle:
        for clip in clips:
            handle.write(f"file '{clip.resolve().as_posix()}'\n")
        lst = Path(handle.name)
    proc = run_ffmpeg(
        ["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(dest)],
        ffmpeg,
    )
    if proc.returncode != 0:
        proc = run_ffmpeg(
            ["-f", "concat", "-safe", "0", "-i", str(lst),
             "-c:v", "libx264", "-preset", "fast", "-crf", "18",
             "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p", str(dest)],
            ffmpeg,
        )
        lst.unlink(missing_ok=True)
        require_ok(proc, "concat re-encode")
        return dest
    lst.unlink(missing_ok=True)
    return dest


def concat_xfade(clips: list[Path], dest: Path, ffmpeg: str, duration: float = 0.4) -> Path:
    if len(clips) == 1:
        dest.write_bytes(clips[0].read_bytes())
        return dest
    current = clips[0]
    tmp_dir = dest.parent / "_xfade"
    tmp_dir.mkdir(exist_ok=True)
    for i, nxt in enumerate(clips[1:], start=1):
        offset = max(0.1, probe_duration(current, ffmpeg) - duration)
        out = tmp_dir / f"xf_{i}.mp4"
        proc = run_ffmpeg(
            [
                "-i", str(current), "-i", str(nxt),
                "-filter_complex",
                f"[0:v][1:v]xfade=transition=fade:duration={duration}:offset={offset:.3f}[v];"
                f"[0:a][1:a]acrossfade=d={duration}[a]",
                "-map", "[v]", "-map", "[a]",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p",
                str(out),
            ],
            ffmpeg,
        )
        if proc.returncode != 0:
            proc = run_ffmpeg(
                [
                    "-i", str(current), "-i", str(nxt),
                    "-filter_complex",
                    f"[0:v][1:v]xfade=transition=fade:duration={duration}:offset={offset:.3f},format=yuv420p[v]",
                    "-map", "[v]", "-an",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                    str(out),
                ],
                ffmpeg,
            )
        if proc.returncode != 0:
            log.warning("xfade failed at step %s, falling back to cut", i)
            return concat_cut(clips, dest, ffmpeg)
        current = out
    dest.write_bytes(current.read_bytes())
    return dest


def mix_music(video: Path, music: Path, dest: Path, ffmpeg: str, volume: float = 0.12) -> Path:
    proc = run_ffmpeg(
        [
            "-i", str(video), "-stream_loop", "-1", "-i", str(music),
            "-filter_complex",
            f"[1:a]volume={volume},aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[bg];"
            f"[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[vo];"
            f"[vo][bg]amix=inputs=2:duration=first:dropout_transition=2,dynaudnorm[a]",
            "-map", "0:v", "-map", "[a]", "-shortest",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            str(dest),
        ],
        ffmpeg,
    )
    if proc.returncode != 0:
        # video may have no audio
        proc = run_ffmpeg(
            [
                "-i", str(video), "-stream_loop", "-1", "-i", str(music),
                "-filter_complex",
                f"[1:a]volume={volume},dynaudnorm[a]",
                "-map", "0:v", "-map", "[a]", "-shortest",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                str(dest),
            ],
            ffmpeg,
        )
        require_ok(proc, "mix music (video-only)")
    return dest


def burn_subs(video: Path, ass_file: Path, dest: Path, ffmpeg: str) -> Path:
    # Escape path for subtitles filter on Windows
    escaped = ass_file.resolve().as_posix().replace(":", "\\:")
    proc = run_ffmpeg(
        ["-i", str(video), "-vf", f"ass='{escaped}'", "-c:a", "copy",
         "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p", str(dest)],
        ffmpeg,
    )
    if proc.returncode != 0:
        log.warning("ASS burn failed, trying subtitles filter")
        escaped2 = str(ass_file.resolve()).replace("\\", "/").replace(":", "\\:")
        proc = run_ffmpeg(
            ["-i", str(video), "-vf", f"subtitles='{escaped2}'", "-c:a", "copy",
             "-c:v", "libx264", "-preset", "fast", "-crf", "18", str(dest)],
            ffmpeg,
        )
        require_ok(proc, "burn captions")
    return dest


def youtube_encode(src: Path, dest: Path, ffmpeg: str, codec: str = "h264") -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if codec == "h265":
        vcodec = ["-c:v", "libx265", "-crf", "20", "-tag:v", "hvc1", "-pix_fmt", "yuv420p"]
    else:
        vcodec = ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p"]
    proc = run_ffmpeg(
        [
            "-i", str(src),
            *vcodec,
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-movflags", "+faststart",
            "-max_muxing_queue_size", "1024",
            str(dest),
        ],
        ffmpeg,
    )
    require_ok(proc, "YouTube encode")
    return dest


def extract_thumbnail(video: Path, dest: Path, ffmpeg: str) -> Path:
    proc = run_ffmpeg(["-ss", "1", "-i", str(video), "-frames:v", "1", str(dest)], ffmpeg)
    if proc.returncode != 0:
        proc = run_ffmpeg(["-i", str(video), "-frames:v", "1", str(dest)], ffmpeg)
        require_ok(proc, "thumbnail")
    return dest


def assemble(
    clips: list[Path],
    dest: Path,
    ffmpeg: str,
    transition: TransitionStyle,
    music: Path | None,
    music_volume: float,
    captions_file: Path | None,
    caption_style: CaptionStyle,
    codec: str,
) -> Path:
    work = dest.parent
    work.mkdir(parents=True, exist_ok=True)
    joined = work / "_joined.mp4"
    if transition is TransitionStyle.CROSSFADE and len(clips) > 1:
        concat_xfade(clips, joined, ffmpeg)
    else:
        concat_cut(clips, joined, ffmpeg)
    current = joined
    if music and music.exists():
        mixed = work / "_mixed.mp4"
        mix_music(current, music, mixed, ffmpeg, music_volume)
        current = mixed
    if captions_file and captions_file.exists() and caption_style is not CaptionStyle.NONE:
        capped = work / "_capped.mp4"
        burn_subs(current, captions_file, capped, ffmpeg)
        current = capped
    youtube_encode(current, dest, ffmpeg, codec)
    return dest
