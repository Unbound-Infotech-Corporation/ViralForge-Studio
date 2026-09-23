from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from trendforge.domain.enums import CaptionStyle, TransitionStyle
from trendforge.logging_setup import get_logger
from trendforge.services.ffmpeg_tools import (
    has_audio_stream,
    require_audio_stream,
    require_ok,
    run_ffmpeg,
)

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
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(clips[0].read_bytes())
        return dest
    tmp_dir = dest.parent / "_xfade"
    tmp_dir.mkdir(exist_ok=True)
    # A video-only crossfade used to be the fallback even when narration was
    # already on the clips, which shipped a mute timeline. Keep that fallback
    # only when every input is silent. If any clip has audio, pad the rest
    # and cut instead of dropping the soundtrack.
    sequence = _with_audio_if_needed(clips, ffmpeg, tmp_dir)
    keep_audio = any(has_audio_stream(clip, ffmpeg) for clip in sequence)
    current = sequence[0]
    for i, nxt in enumerate(sequence[1:], start=1):
        offset = max(0.1, probe_duration(current, ffmpeg) - duration)
        out = tmp_dir / f"xf_{i}.mp4"
        if keep_audio:
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
                log.warning("xfade audio mix failed at step %s; cutting clips instead", i)
                return concat_cut(sequence, dest, ffmpeg)
        else:
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
                return concat_cut(sequence, dest, ffmpeg)
        current = out
    dest.write_bytes(current.read_bytes())
    return dest


def _with_audio_if_needed(clips: list[Path], ffmpeg: str, tmp_dir: Path) -> list[Path]:
    if not any(has_audio_stream(clip, ffmpeg) for clip in clips):
        return clips
    ready: list[Path] = []
    for i, clip in enumerate(clips):
        if has_audio_stream(clip, ffmpeg):
            ready.append(clip)
            continue
        ready.append(ensure_audio_track(clip, tmp_dir / f"sil_{i:03d}.mp4", ffmpeg))
    return ready


def mix_music(
    video: Path,
    music: Path,
    dest: Path,
    ffmpeg: str,
    volume: float = 0.12,
    allow_video_only: bool = True,
) -> Path:
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
        if not allow_video_only:
            require_ok(proc, "mix music with voiceover")
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
        require_ok(proc, "mix music")
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
    src_audio = has_audio_stream(src, ffmpeg)
    proc = run_ffmpeg(
        [
            "-i", str(src),
            "-map", "0:v:0",
            "-map", "0:a:0?",
            *vcodec,
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-movflags", "+faststart",
            "-max_muxing_queue_size", "1024",
            str(dest),
        ],
        ffmpeg,
    )
    require_ok(proc, "YouTube encode")
    if src_audio and not has_audio_stream(dest, ffmpeg):
        dest.unlink(missing_ok=True)
        raise RuntimeError("YouTube encode dropped the audio stream.")
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
    keep_voice: bool = False,
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
        mix_music(
            current,
            music,
            mixed,
            ffmpeg,
            music_volume,
            allow_video_only=not keep_voice,
        )
        current = mixed
    if captions_file and captions_file.exists() and caption_style is not CaptionStyle.NONE:
        capped = work / "_capped.mp4"
        burn_subs(current, captions_file, capped, ffmpeg)
        current = capped
    youtube_encode(current, dest, ffmpeg, codec)
    return dest


def probe_video_size(path: Path, ffmpeg: str) -> tuple[int, int]:
    from trendforge.services.ffmpeg_tools import find_ffprobe

    probe = find_ffprobe(ffmpeg)
    if probe:
        proc = subprocess.run(
            [
                probe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "csv=s=x:p=0",
                str(path),
            ],
            capture_output=True,
            text=True,
            creationflags=_flags(),
        )
        text = (proc.stdout or "").strip()
        if proc.returncode == 0 and "x" in text:
            width, height = text.split("x", 1)
            try:
                return int(width), int(height)
            except ValueError:
                pass
    return 1280, 720


def ensure_audio_track(video: Path, dest: Path, ffmpeg: str) -> Path:
    """Add a silent stereo track when a clip has picture only."""
    if has_audio_stream(video, ffmpeg):
        return video
    dest.parent.mkdir(parents=True, exist_ok=True)
    dur = max(0.2, probe_duration(video, ffmpeg))
    proc = run_ffmpeg(
        [
            "-i", str(video),
            "-f", "lavfi",
            "-t", f"{dur:.3f}",
            "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "128k",
            "-shortest",
            str(dest),
        ],
        ffmpeg,
    )
    require_ok(proc, "add silent audio")
    if not has_audio_stream(dest, ffmpeg):
        raise RuntimeError(f"Silent audio mux produced no audio stream for {video.name}.")
    return dest


def mux_narration_on_clip(video: Path, narration: Path, dest: Path, ffmpeg: str) -> Path:
    """Mux narration onto a cinema clip.

    The picture stays at least as long as the rendered shot. When the
    voiceover is longer, the last frame is held so the line is not cut off.
    When the voiceover is shorter, silence fills the rest of the shot.
    """
    if not narration.exists() or narration.stat().st_size < 100:
        raise RuntimeError(f"Narration audio is missing: {narration}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    picture = max(0.2, probe_duration(video, ffmpeg))
    spoken = max(0.2, probe_duration(narration, ffmpeg))
    target = max(picture, spoken)
    video_pad = max(0.0, target - picture)
    if video_pad >= 0.05:
        video_chain = (
            f"[0:v]tpad=stop_mode=clone:stop_duration={video_pad:.3f},"
            f"format=yuv420p[v]"
        )
    else:
        video_chain = "[0:v]format=yuv420p[v]"
    audio_chain = (
        "[1:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
        f"apad=whole_dur={target:.3f},atrim=0:{target:.3f}[a]"
    )
    proc = run_ffmpeg(
        [
            "-i", str(video),
            "-i", str(narration),
            "-filter_complex",
            f"{video_chain};{audio_chain}",
            "-map", "[v]",
            "-map", "[a]",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-t", f"{target:.3f}",
            str(dest),
        ],
        ffmpeg,
    )
    require_ok(proc, "mux narration onto cinema clip")
    if not has_audio_stream(dest, ffmpeg):
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"Narration mux produced no audio stream for {video.name}.")
    return dest


def lay_cinema_soundtrack(
    clips: list[Path],
    narration_wavs: list[Path | None],
    work_dir: Path,
    ffmpeg: str,
    *,
    require_voice: bool,
) -> list[Path]:
    """Attach per-shot narration. Bridge clips get silence so the stitch keeps audio."""
    if len(clips) != len(narration_wavs):
        raise RuntimeError("Narration tracks do not match the cinema clips.")
    if require_voice and not any(narration_wavs):
        raise RuntimeError(
            "Voiceover is enabled but no narration audio was produced. Refusing a silent export."
        )
    work_dir.mkdir(parents=True, exist_ok=True)
    need_track = any(narration_wavs)
    prepared: list[Path] = []
    for i, (clip, wav) in enumerate(zip(clips, narration_wavs, strict=True)):
        if wav is not None:
            if not wav.exists() or wav.stat().st_size < 100:
                raise RuntimeError(f"Voiceover file for clip {i + 1} is missing or empty.")
            prepared.append(mux_narration_on_clip(clip, wav, work_dir / f"vo_{i:03d}.mp4", ffmpeg))
        elif need_track:
            prepared.append(ensure_audio_track(clip, work_dir / f"sil_{i:03d}.mp4", ffmpeg))
        else:
            prepared.append(clip)
    if require_voice:
        for i, (clip, wav) in enumerate(zip(prepared, narration_wavs, strict=True)):
            if wav is not None and not has_audio_stream(clip, ffmpeg):
                raise RuntimeError(f"Voiceover mux produced no audio on clip {i + 1}.")
    return prepared


def mux_soft_captions(video: Path, srt: Path, dest: Path, ffmpeg: str) -> Path:
    """Mux an SRT as a mov_text track. Used when captions are on and burn style is none."""
    if not srt.exists():
        raise RuntimeError(f"Caption file is missing: {srt}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    inplace = dest.resolve() == video.resolve()
    target = dest.with_name(dest.stem + "_soft.mp4") if inplace else dest
    had_audio = has_audio_stream(video, ffmpeg)
    proc = run_ffmpeg(
        [
            "-i", str(video),
            "-i", str(srt),
            "-map", "0:v:0",
            "-map", "0:a:0?",
            "-map", "1:0",
            "-c:v", "copy",
            "-c:a", "copy",
            "-c:s", "mov_text",
            "-metadata:s:s:0", "language=eng",
            str(target),
        ],
        ffmpeg,
    )
    require_ok(proc, "mux soft captions")
    if had_audio and not has_audio_stream(target, ffmpeg):
        target.unlink(missing_ok=True)
        raise RuntimeError("Soft caption mux dropped the audio stream.")
    if inplace:
        target.replace(dest)
    return dest


def deliver_cinema_audio(
    clips: list[Path],
    dest: Path,
    ffmpeg: str,
    *,
    transition: TransitionStyle,
    music: Path | None,
    music_volume: float,
    captions_file: Path | None,
    caption_style: CaptionStyle,
    codec: str,
    require_voice: bool,
    require_music: bool,
) -> Path:
    """Stitch cinema clips, mix the bed, burn captions, and refuse a mute export."""
    if require_voice and not any(has_audio_stream(clip, ffmpeg) for clip in clips):
        raise RuntimeError(
            "Voiceover is enabled but the cinema picture has no narration audio. "
            "Refusing a silent export."
        )
    if require_music and (music is None or not music.exists()):
        raise RuntimeError("Music is enabled but the music bed is missing. Refusing a silent export.")
    try:
        assemble(
            clips,
            dest,
            ffmpeg,
            transition,
            music,
            music_volume,
            captions_file,
            caption_style,
            codec,
            keep_voice=require_voice,
        )
        if require_voice or require_music:
            require_audio_stream(dest, ffmpeg, "Cinema deliverable")
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    return dest
