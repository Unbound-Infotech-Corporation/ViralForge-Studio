"""Merge Script Lab text into the episode VideoScript Create / Produce stores."""

from __future__ import annotations

import re

from trendforge.domain.models import Shot, VideoScript
from trendforge.services.script_engine import _extract_json, script_from_payload
from trendforge.services.visual_policy import sanitize_visual_prompt

_BEAT = re.compile(r"^\[(?P<title>[^\]]+)\]\s*(?P<rest>.*)$")
_VISUAL = re.compile(r"^(?:visual|picture|shot)\s*:\s*(?P<body>.+)$", re.IGNORECASE)
_VO = re.compile(r"^(?:vo|voiceover|narration|dialogue)\s*:\s*(?P<body>.+)$", re.IGNORECASE)
_FIELD = re.compile(r"^(?P<name>title|logline|synopsis|summary)\s*:\s*(?P<body>.*)$", re.IGNORECASE)
_BEATS_HEADER = re.compile(r"^beats?\s*:\s*$", re.IGNORECASE)
_NUMBERED = re.compile(r"^\d+[\).\]]\s+(?P<body>.*)$")


def apply_script_text(
    script: VideoScript | None,
    text: str,
    *,
    mode: str,
    topic: str = "",
) -> VideoScript:
    """Append or replace episode shots. Raises ValueError on empty input or a bad mode."""
    choice = (mode or "").strip().lower()
    if choice not in {"append", "replace"}:
        raise ValueError(f"Unknown import mode {choice!r}. Use append or replace.")
    cleaned = (text or "").strip()
    if not cleaned:
        raise ValueError("Nothing to import.")
    incoming = script_from_import_text(cleaned, topic=topic or "Imported episode")
    if choice == "replace" or script is None:
        if script is not None:
            if script.season is not None and incoming.season is None:
                incoming.season = script.season
                incoming.episode_index = script.episode_index
            if not incoming.tags and script.tags:
                incoming.tags = list(script.tags)
            if not incoming.youtube.titles and script.youtube.titles:
                incoming.youtube = script.youtube
        return incoming
    start = len(script.shots)
    for offset, shot in enumerate(incoming.shots):
        shot.index = start + offset
        script.shots.append(shot)
    if incoming.summary and incoming.summary not in (script.summary or ""):
        script.summary = (f"{script.summary}\n\n{incoming.summary}").strip() if script.summary else incoming.summary
    return script


def script_from_import_text(text: str, topic: str = "") -> VideoScript:
    cleaned = (text or "").strip()
    if not cleaned:
        raise ValueError("Nothing to import.")
    subject = topic.strip() or "Imported episode"
    if cleaned.startswith("{") or cleaned.startswith("```"):
        payload = _extract_json(cleaned)
        if isinstance(payload, dict) and (payload.get("shots") or payload.get("title") or payload.get("hook")):
            script = script_from_payload(payload, topic=subject)
            if script.title == "Untitled Breakdown":
                script.title = str(payload.get("title") or subject)
            if not script.shots:
                script.shots = _shots_from_narration(
                    "\n\n".join(part for part in (script.hook, script.summary) if part) or cleaned,
                    subject,
                    script.title,
                )
            return script
    if _looks_like_outline(cleaned):
        return _script_from_outline(cleaned, subject)
    return _script_from_blocks(cleaned, subject)


def insert_draft(existing: str, generated: str, mode: str) -> str:
    """Insert a Script AI result into the Script Lab draft editor."""
    choice = (mode or "").strip().lower()
    if choice not in {"append", "replace"}:
        raise ValueError(f"Unknown insert mode {choice!r}. Use append or replace.")
    body = (generated or "").strip()
    if not body:
        raise ValueError("Script AI returned nothing to insert.")
    current = existing or ""
    if choice == "replace" or not current.strip():
        return body
    return current.rstrip() + "\n\n" + body


def _looks_like_outline(text: str) -> bool:
    head = text[:1200].lower()
    return "title:" in head and ("beats:" in head or "logline:" in head or "synopsis:" in head)


def _script_from_outline(text: str, topic: str) -> VideoScript:
    fields: dict[str, str] = {}
    beats: list[str] = []
    section: str | None = None
    beat_buf: list[str] = []

    def flush_beat() -> None:
        joined = " ".join(part for part in beat_buf if part).strip()
        beat_buf.clear()
        if joined:
            beats.append(joined)

    for raw in text.splitlines():
        line = raw.strip()
        field = _FIELD.match(line)
        if field:
            flush_beat()
            section = field.group("name").lower()
            if section == "summary":
                section = "synopsis"
            fields[section] = field.group("body").strip()
            continue
        if _BEATS_HEADER.match(line):
            flush_beat()
            section = "beats"
            continue
        if section == "beats":
            numbered = _NUMBERED.match(line)
            if numbered:
                flush_beat()
                if numbered.group("body").strip():
                    beat_buf.append(numbered.group("body").strip())
            elif not line:
                flush_beat()
            elif beat_buf:
                beat_buf.append(line)
            elif line:
                beat_buf.append(line)
        elif section in fields and line:
            fields[section] = f"{fields[section]} {line}".strip()
    flush_beat()

    title = fields.get("title") or topic
    hook = fields.get("logline") or ""
    summary = fields.get("synopsis") or ""
    shots = [
        _make_shot(index, f"Beat {index + 1}", beat, "", topic, title)
        for index, beat in enumerate(beats)
    ]
    if not shots:
        narration = " ".join(part for part in (hook, summary) if part).strip() or text.strip()
        shots = _shots_from_narration(narration, topic, title)
    return _finish(title, hook, summary, shots)


def _script_from_blocks(text: str, topic: str) -> VideoScript:
    title = topic
    body = text
    lines = text.splitlines()
    if len(lines) > 1 and lines[1].strip() == "" and lines[0].strip() and not lines[0].strip().startswith("["):
        title = lines[0].strip()[:120]
        body = "\n".join(lines[2:]).strip() or text
    blocks = _blocks_from_plain(body)
    if not blocks:
        blocks = [{"title": "Beat 1", "narration": body.strip(), "visual": ""}]
    shots = [
        _make_shot(index, block["title"], block["narration"], block["visual"], topic, title)
        for index, block in enumerate(blocks)
        if block["narration"] or block["visual"]
    ]
    if not shots:
        shots = _shots_from_narration(body, topic, title)
    hook = shots[0].narration
    summary = " ".join(shot.narration for shot in shots if shot.narration)
    return _finish(title, hook, summary, shots)


def _blocks_from_plain(text: str) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    current: dict[str, str] | None = None

    def start(title: str, narration: str = "", visual: str = "") -> None:
        nonlocal current
        current = {"title": title, "narration": narration, "visual": visual}
        blocks.append(current)

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            current = None
            continue
        beat = _BEAT.match(line)
        if beat:
            start(beat.group("title").strip() or f"Beat {len(blocks) + 1}", beat.group("rest").strip())
            continue
        visual = _VISUAL.match(line)
        if visual and current is not None:
            current["visual"] = f"{current['visual']} {visual.group('body')}".strip()
            continue
        spoken = _VO.match(line)
        if spoken and current is not None:
            current["narration"] = f"{current['narration']} {spoken.group('body')}".strip()
            continue
        if spoken and current is None:
            start(f"Beat {len(blocks) + 1}", spoken.group("body").strip())
            continue
        if current is None:
            start(f"Beat {len(blocks) + 1}", line)
        else:
            current["narration"] = f"{current['narration']} {line}".strip()
    return blocks


def _shots_from_narration(text: str, topic: str, title: str) -> list[Shot]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if not paragraphs:
        paragraphs = [text.strip()]
    return [
        _make_shot(index, f"Beat {index + 1}", paragraph, "", topic, title)
        for index, paragraph in enumerate(paragraphs)
    ]


def _make_shot(
    index: int,
    title: str,
    narration: str,
    visual: str,
    topic: str,
    script_title: str,
) -> Shot:
    spoken = (narration or "").strip()
    return Shot(
        index=index,
        title=(title or f"Beat {index + 1}").strip()[:120],
        narration=spoken,
        visual_prompt=sanitize_visual_prompt(
            visual,
            topic=topic or script_title,
            title=title,
            narration=spoken,
        ),
        duration_sec=_duration_for(spoken),
    )


def _duration_for(narration: str) -> float:
    words = max(1, len(narration.split()))
    return round(min(18.0, max(4.0, words / 2.5)), 1)


def _finish(title: str, hook: str, summary: str, shots: list[Shot]) -> VideoScript:
    for index, shot in enumerate(shots):
        shot.index = index
    blurb = (summary or hook or title).strip()
    return VideoScript(
        title=(title or "Imported episode").strip()[:180] or "Imported episode",
        hook=(hook or (shots[0].narration if shots else "")).strip(),
        summary=blurb,
        youtube_description=blurb[:1500],
        shots=shots,
        style_notes="Imported from Script Lab.",
    )
