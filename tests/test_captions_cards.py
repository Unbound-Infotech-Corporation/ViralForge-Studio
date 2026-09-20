from pathlib import Path
import tempfile

from trendforge.domain.enums import VideoStyle, AspectRatio, CaptionStyle
from trendforge.domain.models import Shot
from trendforge.services.captions import write_ass, write_srt
from trendforge.services.cards import canvas_size, render_card


def test_canvas_sizes():
    assert canvas_size(AspectRatio.WIDE) == (1920, 1080)
    assert canvas_size(AspectRatio.VERTICAL) == (1080, 1920)
    assert canvas_size(AspectRatio.SQUARE) == (1080, 1080)


def test_srt_and_card():
    shots = [
        Shot(0, "Hook", "Hello world.", "wide shot", 4.0),
        Shot(1, "Body", "More words here.", "close up", 5.0),
    ]
    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw)
        srt = write_srt(shots, folder / "c.srt")
        text = srt.read_text(encoding="utf-8")
        assert "Hello world." in text
        png = render_card(
            folder / "card.png",
            "SCENE 1",
            "Hook",
            "Hello world.",
            AspectRatio.WIDE,
            VideoStyle.EXPLAINER,
        )
        assert png.exists() and png.stat().st_size > 1000
        atmosphere = render_card(
            folder / "atmosphere.png",
            "SCENE 1",
            "Hook",
            "Hello world.",
            AspectRatio.WIDE,
            VideoStyle.CINEMATIC,
            paint_copy=False,
        )
        assert atmosphere.exists() and atmosphere.stat().st_size > 1000
        ass = write_ass(shots, folder / "c.ass", 1920, 1080, CaptionStyle.CLEAN)
        assert ass is not None
        burned = ass.read_text(encoding="utf-8")
        assert "Hello world." not in burned
        assert "Hook" in burned



def test_canvas_sizes():
    assert canvas_size(AspectRatio.WIDE) == (1920, 1080)
    assert canvas_size(AspectRatio.VERTICAL) == (1080, 1920)
    assert canvas_size(AspectRatio.SQUARE) == (1080, 1080)


def test_srt_and_card():
    shots = [
        Shot(0, "Hook", "Hello world.", "wide shot", 4.0),
        Shot(1, "Body", "More words here.", "close up", 5.0),
    ]
    with tempfile.TemporaryDirectory() as raw:
        folder = Path(raw)
        srt = write_srt(shots, folder / "c.srt")
        text = srt.read_text(encoding="utf-8")
        assert "Hello world." in text
        png = render_card(
            folder / "card.png",
            "SCENE 1",
            "Hook",
            "Hello world.",
            AspectRatio.WIDE,
            VideoStyle.EXPLAINER,
        )
        assert png.exists() and png.stat().st_size > 1000

