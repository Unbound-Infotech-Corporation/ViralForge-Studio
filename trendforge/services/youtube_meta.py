from __future__ import annotations

from pathlib import Path

from trendforge.domain.enums import ContentFormat
from trendforge.domain.models import GenerationRequest, VideoScript
from trendforge.services.cards import render_card


def build_description(script: VideoScript, topic: str, req: GenerationRequest | None = None) -> str:
    chapters = "\n".join(f"{t} {title}" for t, title in script.chapters)
    tags = " ".join(f"#{t.replace(' ', '')}" for t in script.tags[:15])
    titles = ""
    pin = ""
    end = ""
    if script.youtube:
        if script.youtube.titles:
            titles = "Title options:\n" + "\n".join(f"- {t}" for t in script.youtube.titles) + "\n\n"
        pin = script.youtube.pinned_comment
        end = script.youtube.end_screen
    cta = req.channel_cta if req else ""
    channel = req.channel_name if req else ""
    header = f"{channel}\n".strip() + ("\n" if channel else "")
    fmt = req.content_format.value if req else ""
    return (
        f"{header}{script.youtube_description.strip()}\n\n"
        f"{script.summary.strip()}\n\n"
        f"{titles}"
        f"Chapters:\n{chapters or '0:00 Intro'}\n\n"
        f"Pinned comment:\n{pin or cta}\n\n"
        f"End screen:\n{end or cta}\n\n"
        f"{tags}\n\n"
        f"Format: {fmt or 'youtube'}\n"
        "Created locally with TrendForge Studio."
    )


def write_sidecar(script: VideoScript, topic: str, dest: Path, req: GenerationRequest | None = None) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(build_description(script, topic, req), encoding="utf-8")
    folder = dest.parent
    (folder / "tags.txt").write_text(", ".join(script.tags), encoding="utf-8")
    if script.youtube:
        (folder / "titles.txt").write_text("\n".join(script.youtube.titles), encoding="utf-8")
        (folder / "pinned_comment.txt").write_text(script.youtube.pinned_comment, encoding="utf-8")
        (folder / "community_post.txt").write_text(script.youtube.community_post, encoding="utf-8")
        (folder / "end_screen.txt").write_text(script.youtube.end_screen, encoding="utf-8")
        (folder / "thumbnail_text.txt").write_text(script.youtube.thumbnail_text, encoding="utf-8")
    if script.season:
        lines = [script.season.series_title, script.season.logline, "", script.season.bible, ""]
        for ep in script.season.episodes:
            lines.append(f"Ep {ep.index}: {ep.title}\n  {ep.hook}\n  {ep.summary}\n")
        (folder / "season_bible.txt").write_text("\n".join(lines), encoding="utf-8")
    return dest


def render_thumbnail(script: VideoScript, dest: Path, req: GenerationRequest) -> Path:
    from trendforge.domain.enums import AspectRatio

    text = (script.youtube.thumbnail_text if script.youtube else "") or script.title
    aspect = AspectRatio.WIDE
    if req.content_format is ContentFormat.SHORTS:
        aspect = req.aspect
    return render_card(
        dest,
        req.channel_name or "TRENDFORGE",
        text,
        script.hook[:160],
        aspect,
        req.style,
        footer=req.channel_cta[:80],
    )
