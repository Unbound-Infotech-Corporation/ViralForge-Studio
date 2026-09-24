from trendforge.domain.enums import BrandVoice, ContentFormat, LengthPreset, VideoStyle
from trendforge.domain.models import HardwareProfile
from trendforge.domain.install_catalog import recommend_ids
from trendforge.services.script_engine import generate_script, plan_season, script_from_payload, template_script

_BANNED_ON_PICTURE = (
    "title card",
    "kinetic typography",
    "kinetic text",
    "end card",
    "whiteboard",
    "labeled diagram",
    "countdown graphic",
    "logo lockup",
    "subscribe energy",
    "subscribe pulse",
    "chapter card",
)


def test_template_script_has_shots():
    script = template_script("AI video tools", VideoStyle.EXPLAINER, LengthPreset.SHORTS)
    assert script.title
    assert script.shots
    assert all(s.narration for s in script.shots)
    assert all(s.visual_prompt for s in script.shots)


def test_visual_prompts_are_footage_not_slides():
    for fmt, length, style in (
        (ContentFormat.SHORTS, LengthPreset.SHORTS, VideoStyle.CINEMATIC),
        (ContentFormat.VIDEO, LengthPreset.MID, VideoStyle.EXPLAINER),
        (ContentFormat.DOCUSERIES, LengthPreset.DOCUSERIES, VideoStyle.DOCUMENTARY),
    ):
        script = template_script("deepfakes", style, length, content_format=fmt)
        for shot in script.shots:
            vis = shot.visual_prompt.lower()
            body = vis.split("photoreal cinematic")[0]
            for banned in _BANNED_ON_PICTURE:
                assert banned not in body, f"{fmt} shot {shot.title!r} contains {banned!r}"
            assert vis != shot.narration.lower()
            assert "no letters" not in vis
            assert "no words" not in vis
            assert "photoreal cinematic" in vis


def test_script_from_payload_strips_text_cards():
    script = script_from_payload(
        {
            "title": "Test",
            "shots": [
                {
                    "title": "Hook",
                    "narration": "Everyone is talking about this.",
                    "visual_prompt": "dynamic title card, kinetic typography, end card",
                    "duration_sec": 4,
                }
            ],
        },
        topic="deepfakes",
    )
    vis = script.shots[0].visual_prompt.lower()
    assert "title card" not in vis
    assert "kinetic typography" not in vis
    assert vis != script.shots[0].narration.lower()



def test_template_script_has_shots():
    script = template_script("AI video tools", VideoStyle.EXPLAINER, LengthPreset.SHORTS)
    assert script.title
    assert script.shots
    assert all(s.narration for s in script.shots)
    assert all(s.visual_prompt for s in script.shots)


def test_generate_script_without_ollama_is_template():
    script = generate_script("Olympics recap", VideoStyle.BREAKDOWN, LengthPreset.MID, ollama=None)
    assert len(script.shots) >= 5
    assert "Olympics" in script.title or "Olympics" in script.summary


def test_shorts_template_is_vertical_length():
    script = template_script(
        "a viral clip",
        VideoStyle.BREAKDOWN,
        LengthPreset.SHORTS,
        content_format=ContentFormat.SHORTS,
    )
    assert 5 <= len(script.shots) <= 8
    assert sum(s.duration_sec for s in script.shots) <= 60
    assert "shorts" in script.tags or "#shorts" in script.youtube_description.lower()


def test_docuseries_has_long_narration():
    script = template_script(
        "the platform wars",
        VideoStyle.DOCUMENTARY,
        LengthPreset.DOCUSERIES,
        content_format=ContentFormat.DOCUSERIES,
        brand=BrandVoice.DOCUMENTARY,
        channel_name="Signal Cut",
        episode_index=2,
        episode_count=5,
        series_title="Signal Cut Investigations",
    )
    assert len(script.shots) >= 16
    assert script.episode_index == 2
    assert "Episode 2" in script.title or "Ep 2" in script.youtube.titles[0]
    assert any("Subscribe" in s.narration or "Signal Cut" in s.narration for s in script.shots)


def test_season_plan_fallback():
    season = plan_season("deepfakes", episode_count=5, ollama=None, channel_name="Signal Cut")
    assert season.series_title
    assert len(season.episodes) == 5
    assert all(ep.hook for ep in season.episodes)
    script = generate_script(
        "deepfakes",
        VideoStyle.DOCUMENTARY,
        LengthPreset.DOCUSERIES,
        content_format=ContentFormat.SEASON,
        episode_count=5,
        channel_name="Signal Cut",
    )
    assert script.season is not None
    assert len(script.season.episodes) >= 4
    assert script.shots == []


def test_recommend_ids_32gb_gpu():
    hw = HardwareProfile(gpu_name="RTX 5090", vram_total_gb=32, ram_total_gb=64, cuda_available=True)
    ids = recommend_ids(hw)
    assert "ffmpeg" in ids
    assert "piper_lessac" in ids
    assert "ollama_qwen7" in ids
    assert "ollama_qwen14" in ids
    assert "maestro_ltx25" not in ids
    assert "maestro_wana14b" not in ids
    assert "maestro_h3" not in ids
