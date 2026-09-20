from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from trendforge.domain.enums import MediaType
from trendforge.domain.models import TrailerAttribution
from trendforge.logging_setup import get_logger

log = get_logger("trailer_allowlist")

ALLOWLIST_PATH = Path(__file__).resolve().parent.parent / "assets" / "trailer_allowlist.json"


@dataclass(slots=True)
class AllowlistEntry:
    id: str
    studio: str
    media_types: list[str]
    franchises: list[str]
    channel_ids: list[str]
    channel_names: list[str]


@dataclass(slots=True)
class TrailerVerificationResult:
    ok: bool
    reason: str = ""
    attribution: TrailerAttribution | None = None
    entry: AllowlistEntry | None = None


@dataclass(slots=True)
class YoutubeVideoMeta:
    video_id: str
    title: str
    channel_id: str
    channel_name: str
    upload_date: str
    duration_sec: float


def _parse_entry(raw: dict[str, Any]) -> AllowlistEntry:
    return AllowlistEntry(
        id=str(raw.get("id") or ""),
        studio=str(raw.get("studio") or ""),
        media_types=[str(x).lower() for x in (raw.get("media_types") or [])],
        franchises=[str(x) for x in (raw.get("franchises") or [])],
        channel_ids=[str(x) for x in (raw.get("channel_ids") or [])],
        channel_names=[str(x) for x in (raw.get("channel_names") or [])],
    )


@lru_cache(maxsize=1)
def load_allowlist(path: Path | None = None) -> list[AllowlistEntry]:
    src = path or ALLOWLIST_PATH
    if not src.exists():
        log.warning("Trailer allowlist missing at %s", src)
        return []
    data = json.loads(src.read_text(encoding="utf-8"))
    return [_parse_entry(item) for item in data.get("entries") or []]


def get_entry(entry_id: str, path: Path | None = None) -> AllowlistEntry | None:
    for entry in load_allowlist(path):
        if entry.id == entry_id:
            return entry
    return None


def list_entries(media_type: MediaType | None = None, path: Path | None = None) -> list[AllowlistEntry]:
    entries = load_allowlist(path)
    if media_type is None:
        return entries
    key = media_type.value
    return [e for e in entries if key in e.media_types]


def match_entry_for_subject(subject: str, media_type: MediaType | None = None) -> AllowlistEntry | None:
    subject_lower = subject.lower().strip()
    if not subject_lower:
        return None
    best: AllowlistEntry | None = None
    best_score = 0
    for entry in list_entries(media_type):
        for franchise in entry.franchises:
            token = franchise.lower()
            if token in subject_lower or subject_lower in token:
                score = len(token)
                if score > best_score:
                    best = entry
                    best_score = score
    return best


def fetch_youtube_video_meta(url: str) -> YoutubeVideoMeta:
    """Resolve channel ID from a YouTube URL — never trust title text alone."""
    try:
        from yt_dlp import YoutubeDL
    except Exception as exc:
        raise RuntimeError("yt-dlp is not installed") from exc

    opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return YoutubeVideoMeta(
        video_id=str(info.get("id") or ""),
        title=str(info.get("title") or ""),
        channel_id=str(info.get("channel_id") or info.get("uploader_id") or ""),
        channel_name=str(info.get("channel") or info.get("uploader") or ""),
        upload_date=str(info.get("upload_date") or ""),
        duration_sec=float(info.get("duration") or 0.0),
    )


def verify_trailer_url(
    url: str,
    allowlist_entry_id: str,
    *,
    meta: YoutubeVideoMeta | None = None,
    path: Path | None = None,
) -> TrailerVerificationResult:
    """Reject any trailer not uploaded by an allowlisted official channel."""
    if not url.strip():
        return TrailerVerificationResult(False, "Trailer URL is required.")
    entry = get_entry(allowlist_entry_id, path)
    if entry is None:
        return TrailerVerificationResult(
            False,
            f"Unknown allowlist entry '{allowlist_entry_id}'. Add the studio channel to trailer_allowlist.json first.",
        )
    try:
        video = meta or fetch_youtube_video_meta(url)
    except Exception as exc:
        return TrailerVerificationResult(False, f"Could not resolve trailer metadata: {exc}")

    if not video.channel_id:
        return TrailerVerificationResult(False, "Could not determine uploader channel ID for this URL.")

    if video.channel_id not in entry.channel_ids:
        return TrailerVerificationResult(
            False,
            (
                f"Trailer rejected: uploader '{video.channel_name}' ({video.channel_id}) is not on the "
                f"official allowlist for {entry.studio}. Fan reuploads, leaks, and bootlegs are blocked."
            ),
        )

    release = video.upload_date
    if len(release) == 8 and release.isdigit():
        release = f"{release[0:4]}-{release[4:6]}-{release[6:8]}"

    attribution = TrailerAttribution(
        studio=entry.studio,
        channel_name=video.channel_name or (entry.channel_names[0] if entry.channel_names else entry.studio),
        channel_id=video.channel_id,
        video_title=video.title,
        video_url=url,
        release_date=release,
        allowlist_entry_id=entry.id,
    )
    return TrailerVerificationResult(True, "Official trailer verified.", attribution, entry)


def format_attribution_credit(attr: TrailerAttribution) -> str:
    parts = [f"Trailer: {attr.video_title}"]
    if attr.studio:
        parts.append(f"Studio/Publisher: {attr.studio}")
    if attr.channel_name:
        parts.append(f"Official channel: {attr.channel_name}")
    if attr.release_date:
        parts.append(f"Release date: {attr.release_date}")
    if attr.video_url:
        parts.append(f"Source: {attr.video_url}")
    return " · ".join(parts)
