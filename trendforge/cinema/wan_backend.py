from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from trendforge.cinema.shots import CinemaShot


class WanBackend(ABC):
    @abstractmethod
    def generate(self, shot: CinemaShot, keyframe: Path | None, dest: Path) -> Path:
        raise NotImplementedError


class DryRunWanBackend(WanBackend):
    """Offline stand-in that renders a motion card via ffmpeg kenburns/color."""

    def __init__(self, ffmpeg: str) -> None:
        self.ffmpeg = ffmpeg

    def generate(self, shot: CinemaShot, keyframe: Path | None, dest: Path) -> Path:
        from trendforge.services.stitcher import ken_burns_clip

        dest.parent.mkdir(parents=True, exist_ok=True)
        if keyframe and keyframe.exists():
            return ken_burns_clip(keyframe, dest, max(1.0, shot.duration_sec), (1280, 720), self.ffmpeg)
        # solid card with title burned via drawtext-less path: generate png then kenburns
        from PIL import Image, ImageDraw, ImageFont

        img_path = dest.with_suffix(".png")
        img = Image.new("RGB", (1280, 720), (12, 14, 22))
        draw = ImageDraw.Draw(img)
        title = (shot.title or f"Shot {shot.index}")[:80]
        body = (shot.visual_prompt or shot.narration or "")[:160]
        draw.rectangle((40, 40, 1240, 680), outline=(80, 160, 255), width=3)
        try:
            font = ImageFont.truetype("arial.ttf", 42)
            small = ImageFont.truetype("arial.ttf", 28)
        except Exception:
            font = ImageFont.load_default()
            small = font
        draw.text((70, 120), f"VF Cinema · {title}", fill=(240, 244, 255), font=font)
        draw.text((70, 220), body, fill=(180, 190, 210), font=small)
        img.save(img_path)
        out = ken_burns_clip(img_path, dest, max(1.0, shot.duration_sec), (1280, 720), self.ffmpeg)
        return out
