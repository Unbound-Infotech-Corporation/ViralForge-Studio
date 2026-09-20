from __future__ import annotations

from pathlib import Path

from trendforge.domain.enums import CaptionStyle
from trendforge.domain.models import Shot
from trendforge.services.visual_policy import burned_caption_text


def _ass_header(width: int, height: int, style: CaptionStyle) -> str:
    font = "Segoe UI"
    size = 52 if style is CaptionStyle.BOLD else 42 if style is CaptionStyle.CLEAN else 36
    outline = 4 if style is CaptionStyle.BOLD else 2
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Alignment, MarginV, Outline, Shadow
Style: Default,{font},{size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,{"-1" if style is CaptionStyle.BOLD else "0"},0,2,80,{outline},0

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _ts(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def write_ass(shots: list[Shot], dest: Path, width: int, height: int, style: CaptionStyle) -> Path | None:
    if style is CaptionStyle.NONE:
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    lines = [_ass_header(width, height, style)]
    t = 0.0
    for shot in shots:
        caption = burned_caption_text(shot)
        if not caption:
            t += max(1.0, shot.duration_sec)
            continue
        text = caption.replace("\n", "\\N")
        text = text.replace("{", "\\{").replace("}", "\\}")
        start, end = t, t + max(1.0, shot.duration_sec)
        lines.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Default,,0,0,0,,{text}")
        t = end
    dest.write_text("\n".join(lines), encoding="utf-8")
    return dest


def write_srt(shots: list[Shot], dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    t = 0.0
    blocks: list[str] = []

    def srt_ts(seconds: float) -> str:
        ms = int(round(seconds * 1000))
        h, rem = divmod(ms, 3_600_000)
        m, rem = divmod(rem, 60_000)
        s, milli = divmod(rem, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"

    for i, shot in enumerate(shots, start=1):
        start, end = t, t + max(1.0, shot.duration_sec)
        text = shot.narration or shot.title
        blocks.append(f"{i}\n{srt_ts(start)} --> {srt_ts(end)}\n{text}\n")
        t = end
    dest.write_text("\n".join(blocks), encoding="utf-8")
    return dest


def whisper_transcribe(media: Path, dest_srt: Path) -> Path | None:
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except Exception:
        return None
    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, _info = model.transcribe(str(media))
    blocks: list[str] = []

    def srt_ts(seconds: float) -> str:
        ms = int(round(seconds * 1000))
        h, rem = divmod(ms, 3_600_000)
        m, rem = divmod(rem, 60_000)
        s, milli = divmod(rem, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"

    for i, seg in enumerate(segments, start=1):
        blocks.append(f"{i}\n{srt_ts(seg.start)} --> {srt_ts(seg.end)}\n{seg.text.strip()}\n")
    dest_srt.write_text("\n".join(blocks), encoding="utf-8")
    return dest_srt
