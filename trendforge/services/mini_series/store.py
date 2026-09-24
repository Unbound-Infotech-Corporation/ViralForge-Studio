"""JSON persistence for mini series, mirroring ``ProjectStore``."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from trendforge.domain.mini_series import (
    CommentItem,
    EpisodePhase,
    MeetingRecord,
    MiniEpisode,
    MiniSeries,
    RankedTheme,
)
from trendforge.domain.serialize import dumps, to_plain
from trendforge.services.mini_series.guardrails import default_acks


class MiniSeriesStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def series_dir(self, series_id: str) -> Path:
        return self.root / series_id

    def save(self, series: MiniSeries) -> Path:
        folder = self.series_dir(series.id)
        folder.mkdir(parents=True, exist_ok=True)
        series.updated_at = datetime.now(timezone.utc).isoformat()
        path = folder / "series.json"
        path.write_text(dumps(series), encoding="utf-8")
        return path

    def load(self, series_id: str) -> MiniSeries:
        path = self.series_dir(series_id) / "series.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        return series_from_dict(data)

    def list_series(self) -> list[MiniSeries]:
        items: list[MiniSeries] = []
        if not self.root.exists():
            return items
        children = [child for child in self.root.iterdir() if (child / "series.json").exists()]
        children.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        for child in children:
            try:
                data = json.loads((child / "series.json").read_text(encoding="utf-8"))
                items.append(series_from_dict(data))
            except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
        return items

    def delete(self, series_id: str) -> None:
        folder = self.series_dir(series_id)
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)


def series_from_dict(data: dict) -> MiniSeries:
    episodes = [episode_from_dict(raw) for raw in data.get("episodes") or []]
    return MiniSeries(
        id=str(data.get("id") or ""),
        title=str(data.get("title") or ""),
        topic=str(data.get("topic") or ""),
        channel_name=str(data.get("channel_name") or ""),
        created_at=str(data.get("created_at") or ""),
        updated_at=str(data.get("updated_at") or ""),
        episodes=episodes,
        schema_version=int(data.get("schema_version") or 1),
    )


def episode_from_dict(data: dict) -> MiniEpisode:
    try:
        phase = EpisodePhase(str(data.get("phase") or EpisodePhase.BRIEF.value))
    except ValueError:
        phase = EpisodePhase.BRIEF
    meeting_raw = data.get("meeting") or {}
    acks = default_acks()
    acks.update({str(key): bool(value) for key, value in (meeting_raw.get("guardrail_acks") or {}).items()})
    meeting = MeetingRecord(
        storyline=str(meeting_raw.get("storyline") or ""),
        goals=str(meeting_raw.get("goals") or ""),
        tone=str(meeting_raw.get("tone") or "documentary"),
        notes=str(meeting_raw.get("notes") or ""),
        guardrail_acks=acks,
        approved=bool(meeting_raw.get("approved")),
        approved_at=str(meeting_raw.get("approved_at") or ""),
    )
    comments = [
        CommentItem(
            author=str(item.get("author") or "viewer"),
            text=str(item.get("text") or ""),
            like_count=int(item.get("like_count") or 0),
            published_at=str(item.get("published_at") or ""),
        )
        for item in data.get("comments") or []
        if isinstance(item, dict)
    ]
    themes = [
        RankedTheme(
            theme=str(item.get("theme") or ""),
            score=float(item.get("score") or 0),
            comment_count=int(item.get("comment_count") or 0),
            examples=[str(example) for example in item.get("examples") or []],
        )
        for item in data.get("themes") or []
        if isinstance(item, dict)
    ]
    script = data.get("script")
    return MiniEpisode(
        id=str(data.get("id") or ""),
        index=int(data.get("index") or 1),
        topic=str(data.get("topic") or ""),
        title=str(data.get("title") or ""),
        phase=phase,
        target_minutes=float(data.get("target_minutes") or 7.5),
        meeting=meeting,
        outline=str(data.get("outline") or ""),
        script=script if isinstance(script, dict) else None,
        project_id=str(data.get("project_id") or ""),
        output_path=str(data.get("output_path") or ""),
        video_id=str(data.get("video_id") or ""),
        published_at=str(data.get("published_at") or ""),
        monitor_until=str(data.get("monitor_until") or ""),
        source_episode_id=str(data.get("source_episode_id") or ""),
        comments=comments,
        themes=themes,
        created_at=str(data.get("created_at") or ""),
        updated_at=str(data.get("updated_at") or ""),
    )


def script_plain(script: object) -> dict:
    plain = to_plain(script)
    if not isinstance(plain, dict):
        raise TypeError("Script did not serialize to an object")
    return plain
