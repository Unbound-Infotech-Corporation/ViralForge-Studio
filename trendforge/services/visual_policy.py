from __future__ import annotations

import re

from trendforge.domain.enums import ContentFormat
from trendforge.domain.models import Shot, VideoScript

# Positive-prompt quality tag only. Stacked "no letters, no words" in the
# positive prompt makes Flux / LTX / Wan emit a black frame.
CINEMATIC_LOOK = (
    "photoreal cinematic footage, natural camera, production lighting"
)

STUDIO_NEGATIVE = (
    "text, titles, captions, subtitles, writing, typography, "
    "logo, watermark, UI, infographic, lower third, end card, kinetic type, "
    "closed captions, powerpoint, slide, diagram, chart"
)

_TEXT_MARKERS = (
    "title card",
    "end card",
    "kinetic typography",
    "kinetic text",
    "kinetic type",
    "whiteboard",
    "labeled diagram",
    "countdown graphic",
    "logo lockup",
    "subscribe energy",
    "subscribe pulse",
    "on-screen text",
    "on screen text",
    "infographic",
    "lower third",
    "motion graphics",
    "big graphic",
    "red x over",
    "headline",
    "username",
    "chapter card",
    "chapter cards",
)

_MARKER_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(m) for m in _TEXT_MARKERS) + r")s?\b",
    re.IGNORECASE,
)

_POSITIVE_NO_TEXT_PILE_RE = re.compile(
    r"(?:,\s*)?no\s+"
    r"(?:texts?|titles?|captions?|subtitles?|letters?|words?|"
    r"typography|logos?|ui|watermarks?|infographics?|"
    r"lower[- ]thirds?|end cards?|"
    r"on[- ]screen\s+(?:texts?|writing|graphics)(?:\s+of any kind)?|"
    r"s(?![a-z]))"
    r"(?:\s+of any kind)?",
    re.IGNORECASE,
)


def looks_like_spoken_copy(visual: str, narration: str) -> bool:
    vis = (visual or "").strip()
    narr = (narration or "").strip()
    if not vis:
        return True
    if not narr:
        return False
    if vis.lower() == narr.lower():
        return True
    head = narr[:48].strip().lower()
    return bool(head) and vis.lower().startswith(head)


def sanitize_visual_prompt(
    visual: str,
    *,
    topic: str = "",
    title: str = "",
    narration: str = "",
) -> str:
    raw = (visual or "").strip()
    cleaned = _MARKER_RE.sub("", raw)
    previous = None
    while previous != cleaned:
        previous = cleaned
        cleaned = _POSITIVE_NO_TEXT_PILE_RE.sub("", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,;.")
    cleaned = re.sub(r"[,;\s]*\bno\s*$", "", cleaned, flags=re.IGNORECASE).strip(" ,;.")
    if looks_like_spoken_copy(cleaned, narration) or len(cleaned) < 12:
        subject = title.strip() or topic.strip() or "the subject"
        cleaned = (
            f"cinematic photographed coverage of {topic or subject}: "
            f"{subject}, real location, natural light, camera moving slowly"
        )
    if CINEMATIC_LOOK not in cleaned.lower():
        cleaned = f"{cleaned}, {CINEMATIC_LOOK}"
    return cleaned


def footage_prompt(shot: Shot, topic: str = "") -> str:
    return sanitize_visual_prompt(
        shot.visual_prompt,
        topic=topic,
        title=shot.title,
        narration=shot.narration,
    )


def director_visual_story(script: VideoScript, topic: str, content_format: ContentFormat) -> str:
    lines = [
        f"Cinematic visual coverage of: {topic}.",
        "This is picture for a voiceover documentary — not a lecture, not a talking-head reading a script, not kinetic typography, not title cards.",
        "Describe photographed footage of the subject: camera, light, location, action.",
        "Do not stage a presenter reciting the narration. Voiceover will be mixed later. Picture of the subject only.",
        "Silent or ambient production sound. No on-camera dialogue that restates the voiceover.",
        "",
        "Shot coverage:",
    ]
    for shot in script.shots:
        prompt = footage_prompt(shot, topic)
        lines.append(f"{shot.index + 1}. [{shot.duration_sec:.0f}s] {prompt}")
    if content_format is ContentFormat.SHORTS:
        lines.append("")
        lines.append("Optimize as a vertical cinematic short: hook on the first frame with an image, not a title.")
    return "\n".join(lines)


def director_pipeline_type(content_format: ContentFormat) -> str:
    # Maestro only accepts music_video / short_film_audio / short_film_story.
    return "short_film_story"


def burned_caption_text(shot: Shot) -> str:
    """Short title only. Never the spoken paragraph."""
    title = (shot.title or "").strip()
    if not title:
        return ""
    words = title.split()
    return " ".join(words[:8])
