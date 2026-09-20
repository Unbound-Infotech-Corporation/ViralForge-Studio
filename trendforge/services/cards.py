from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from trendforge.domain.enums import AspectRatio, VideoStyle


PALETTES = {
    VideoStyle.EXPLAINER: ((18, 22, 36), (88, 70, 196), (232, 165, 75)),
    VideoStyle.BREAKDOWN: ((12, 16, 28), (220, 80, 70), (240, 210, 160)),
    VideoStyle.CINEMATIC: ((8, 8, 12), (120, 40, 40), (210, 170, 110)),
    VideoStyle.DOCUMENTARY: ((20, 24, 22), (60, 90, 70), (210, 200, 170)),
    VideoStyle.REACTION: ((24, 10, 28), (230, 70, 140), (90, 200, 255)),
    VideoStyle.RANKING: ((16, 12, 32), (230, 170, 50), (250, 90, 70)),
    VideoStyle.NEWS_RECAP: ((12, 18, 28), (40, 90, 160), (220, 220, 230)),
    VideoStyle.STORY: ((22, 14, 18), (140, 50, 70), (230, 190, 140)),
    VideoStyle.EDUCATIONAL: ((18, 26, 32), (40, 120, 140), (230, 200, 120)),
    VideoStyle.REVIEW: ((14, 18, 28), (210, 120, 60), (240, 230, 210)),
}


def canvas_size(aspect: AspectRatio) -> tuple[int, int]:
    if aspect is AspectRatio.VERTICAL:
        return 1080, 1920
    if aspect is AspectRatio.SQUARE:
        return 1080, 1080
    return 1920, 1080


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = [
        "segoeuib.ttf" if bold else "segoeui.ttf",
        "SegoeUI-Bold.ttf" if bold else "SegoeUI.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
        "calibrib.ttf" if bold else "calibri.ttf",
    ]
    windir = Path(r"C:\Windows\Fonts")
    for name in names:
        path = windir / name
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                continue
    return ImageFont.load_default()


def _gradient(size: tuple[int, int], c1: tuple[int, int, int], c2: tuple[int, int, int]) -> Image.Image:
    w, h = size
    img = Image.new("RGB", size, c1)
    px = img.load()
    for y in range(h):
        t = y / max(h - 1, 1)
        r = int(c1[0] + (c2[0] - c1[0]) * t)
        g = int(c1[1] + (c2[1] - c1[1]) * t)
        b = int(c1[2] + (c2[2] - c1[2]) * t)
        for x in range(0, w, 8):
            for dx in range(8):
                if x + dx < w:
                    px[x + dx, y] = (r, g, b)
    return img


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> str:
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        trial = " ".join(current + [word])
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines[:10])


def render_card(
    dest: Path,
    kicker: str,
    title: str,
    body: str,
    aspect: AspectRatio,
    style: VideoStyle,
    footer: str = "TrendForge Studio",
    paint_copy: bool = True,
) -> Path:
    w, h = canvas_size(aspect)
    bg, accent, gold = PALETTES.get(style, PALETTES[VideoStyle.EXPLAINER])
    img = _gradient((w, h), bg, tuple(max(0, c - 18) for c in bg))  # type: ignore[arg-type]
    draw = ImageDraw.Draw(img, "RGBA")
    if not paint_copy:
        # Atmosphere plate for Ken Burns — never the spoken script.
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        shade = ImageDraw.Draw(overlay)
        shade.ellipse(
            [-w // 4, -h // 6, w + w // 4, h + h // 3],
            fill=accent + (40,),
        )
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        dest.parent.mkdir(parents=True, exist_ok=True)
        img.save(dest, "PNG", optimize=True)
        return dest
    # Accent bar
    bar = max(14, w // 80)
    draw.rectangle([0, 0, bar, h], fill=accent + (255,))
    draw.rectangle([0, 0, w, bar], fill=gold + (220,))
    kicker_font = _font(max(28, w // 38), bold=True)
    title_font = _font(max(54, w // 16), bold=True)
    body_font = _font(max(28, w // 36))
    foot_font = _font(max(20, w // 50))
    margin = w // 10
    y = h // 7
    draw.text((margin, y), kicker.upper(), font=kicker_font, fill=gold)
    y += 70
    wrapped_title = _wrap(draw, title, title_font, w - margin * 2)
    draw.multiline_text((margin, y), wrapped_title, font=title_font, fill=(245, 246, 250), spacing=8)
    bbox = draw.multiline_textbbox((margin, y), wrapped_title, font=title_font, spacing=8)
    y = bbox[3] + 48
    wrapped_body = _wrap(draw, body, body_font, w - margin * 2)
    draw.multiline_text((margin, y), wrapped_body, font=body_font, fill=(200, 206, 220), spacing=10)
    draw.text((margin, h - margin), footer, font=foot_font, fill=(160, 166, 180))
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, "PNG", optimize=True)
    return dest
