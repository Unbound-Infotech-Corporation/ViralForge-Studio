from trendforge.domain.enums import ContentFormat
from trendforge.domain.models import Shot, VideoScript
from trendforge.services.visual_policy import (
    CINEMATIC_LOOK,
    STUDIO_NEGATIVE,
    director_pipeline_type,
    director_visual_story,
    footage_prompt,
    sanitize_visual_prompt,
)


def test_footage_prompt_never_uses_narration():
    shot = Shot(
        0,
        "Hook",
        "Everyone is talking about deepfakes and nobody understands them.",
        "",
        5.0,
    )
    prompt = footage_prompt(shot, "deepfakes")
    assert prompt != shot.narration
    assert "everyone is talking" not in prompt.lower()
    assert "no letters" not in prompt.lower()
    assert "no words" not in prompt.lower()
    assert CINEMATIC_LOOK in prompt.lower()
    assert "deepfakes" in prompt.lower()


def test_sanitize_strips_slide_language():
    out = sanitize_visual_prompt(
        "clean end card, logo lockup, subscribe energy",
        topic="Olympics",
        title="Outro",
        narration="Subscribe for the next episode.",
    )
    lowered = out.lower().split("photoreal cinematic")[0]
    assert "end card" not in lowered
    assert "logo lockup" not in lowered
    assert "subscribe energy" not in lowered
    assert "olympics" in out.lower()
    assert "no letters" not in out.lower()


def test_sanitize_is_idempotent_and_does_not_emit_no_s():
    first = sanitize_visual_prompt(
        "handheld crash zoom into a crowd",
        topic="deepfakes",
        title="Hook",
    )
    second = sanitize_visual_prompt(first, topic="deepfakes", title="Hook")
    assert first == second
    assert "no s" not in second.lower()
    assert "no text" not in second.lower()
    assert CINEMATIC_LOOK in second.lower()


def test_director_story_is_visual_only():
    script = VideoScript(
        title="Deepfakes",
        hook="The viral version is a lie.",
        summary="A recap.",
        youtube_description="",
        shots=[
            Shot(0, "Hook", "The viral version is a lie.", "handheld crash zoom into a crowd", 6.0),
            Shot(1, "Truth", "Here is what actually happened.", "aerial dusk city", 8.0),
        ],
    )
    story = director_visual_story(script, "deepfakes", ContentFormat.VIDEO)
    assert "The viral version is a lie." not in story
    assert "Here is what actually happened." not in story
    assert "voiceover" in story.lower()
    assert "handheld crash zoom" in story.lower()
    assert "no letters" not in story.lower()
    assert director_pipeline_type(ContentFormat.SHORTS) == "short_film_story"
    assert director_pipeline_type(ContentFormat.VIDEO) == "short_film_story"
    assert "text" in STUDIO_NEGATIVE
    assert "letters" not in STUDIO_NEGATIVE
    assert "words" not in {part.strip() for part in STUDIO_NEGATIVE.split(",")}
