from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from trendforge.logging_setup import get_logger

log = get_logger("ytdlp")


@dataclass(slots=True)
class VttCue:
    start: float
    end: float
    text: str


@dataclass(slots=True)
class SourceResearch:
    title: str
    channel: str
    duration_sec: float
    description: str
    transcript: str
    video_path: Path | None
    context_text: str


def _vtt_timestamp(value: str) -> float:
    value = value.strip()
    if not value:
        return 0.0
    parts = value.split(":")
    try:
        if len(parts) == 3:
            h, m, s = parts
            return int(h) * 3600 + int(m) * 60 + float(s.replace(",", "."))
        if len(parts) == 2:
            m, s = parts
            return int(m) * 60 + float(s.replace(",", "."))
        return float(value.replace(",", "."))
    except ValueError:
        return 0.0


def parse_vtt_text(raw: str) -> list[VttCue]:
    """Parse WebVTT cues into start/end/text tuples."""
    cues: list[VttCue] = []
    blocks = re.split(r"\n\s*\n", raw.replace("\r\n", "\n"))
    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        if lines[0].upper().startswith("WEBVTT") or lines[0].startswith("NOTE"):
            continue
        time_line = lines[0]
        if "-->" not in time_line and len(lines) > 1 and "-->" in lines[1]:
            time_line = lines[1]
            text_lines = lines[2:]
        else:
            text_lines = lines[1:]
        if "-->" not in time_line:
            continue
        start_raw, end_raw = [part.strip().split()[0] for part in time_line.split("-->", 1)]
        text = re.sub(r"<[^>]+>", "", " ".join(text_lines))
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        cues.append(VttCue(_vtt_timestamp(start_raw), _vtt_timestamp(end_raw), text))
    return cues


def _read_captions(workdir: Path) -> tuple[str, list[VttCue]]:
    for path in sorted(workdir.glob("*.vtt")):
        raw = path.read_text(encoding="utf-8", errors="ignore")
        cues = parse_vtt_text(raw)
        transcript = " ".join(c.text for c in cues)
        return transcript[:12000], cues
    return "", []


def _youtube_dl():
    try:
        from yt_dlp import YoutubeDL
    except Exception as exc:
        raise RuntimeError("yt-dlp is not installed") from exc
    return YoutubeDL


def extract_video_context(url: str, workdir: Path) -> str:
    """Download metadata + auto captions for breakdown-of-existing-video mode."""
    research = source_research(url, workdir, download_video=False)
    return research.context_text


def download_source_video(url: str, workdir: Path) -> Path:
    """Download the source MP4 for clip + narrate workflows."""
    research = source_research(url, workdir, download_video=True)
    if research.video_path is None or not research.video_path.exists():
        raise RuntimeError("Could not download source video — check the URL and yt-dlp.")
    return research.video_path


def source_research(url: str, workdir: Path, *, download_video: bool = False) -> SourceResearch:
    """Fetch metadata, captions, and optionally the source video file."""
    YoutubeDL = _youtube_dl()
    workdir.mkdir(parents=True, exist_ok=True)
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": not download_video,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en", "en-US", "en-GB"],
        "subtitlesformat": "vtt",
        "outtmpl": str(workdir / "%(id)s.%(ext)s"),
    }
    if download_video:
        opts.update(
            {
                "format": "bv*+ba/b",
                "merge_output_format": "mp4",
                "postprocessors": [{"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}],
            }
        )
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    title = str(info.get("title") or "")
    desc = str(info.get("description") or "")[:2500]
    duration = float(info.get("duration") or 0.0)
    channel = str(info.get("channel") or info.get("uploader") or "")
    transcript, cues = _read_captions(workdir)
    video_path: Path | None = None
    if download_video:
        vid = str(info.get("id") or "")
        for candidate in workdir.glob(f"{vid}.*"):
            if candidate.suffix.lower() in {".mp4", ".mkv", ".webm"}:
                video_path = candidate
                break
        if video_path is None:
            for candidate in sorted(workdir.glob("*.*")):
                if candidate.suffix.lower() in {".mp4", ".mkv", ".webm"} and candidate.name != "dummy":
                    video_path = candidate
                    break
    cue_lines = "\n".join(f"[{c.start:.1f}s–{c.end:.1f}s] {c.text}" for c in cues[:80])
    context = (
        f"Source video title: {title}\nChannel: {channel}\nDuration: {duration}s\n"
        f"Description:\n{desc}\n\nTranscript excerpt:\n{transcript[:6000]}\n\n"
        f"Timed transcript (use for source_start_sec / source_end_sec on each shot):\n{cue_lines}"
    )
    return SourceResearch(
        title=title,
        channel=channel,
        duration_sec=duration,
        description=desc,
        transcript=transcript,
        video_path=video_path,
        context_text=context,
    )
