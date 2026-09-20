from trendforge.domain.models import Shot, VideoScript
from trendforge.services.script_engine import assign_source_timestamps
from trendforge.services.ytdlp_tools import VttCue, parse_vtt_text


VTT_SAMPLE = """WEBVTT

00:00:01.000 --> 00:00:04.000
The story starts in a bank in Switzerland.

00:00:04.500 --> 00:00:08.000
An old man walks in wearing a round necklace.

00:00:08.500 --> 00:00:12.000
He pulls out a gun and starts shooting.
"""


def test_parse_vtt_cues():
    cues = parse_vtt_text(VTT_SAMPLE)
    assert len(cues) == 3
    assert cues[0].start == 1.0
    assert cues[0].end == 4.0
    assert "bank" in cues[0].text.lower()


def test_assign_source_timestamps_even_split():
    script = VideoScript(
        title="Recap",
        hook="Hook",
        summary="Summary",
        youtube_description="",
        shots=[
            Shot(0, "Opening", "First beat of narration here.", "visual", 5.0),
            Shot(1, "Middle", "Second beat with more words in it.", "visual", 5.0),
        ],
    )
    assign_source_timestamps(script, duration_sec=120.0, cues=[])
    assert script.shots[0].source_start_sec == 0.0
    assert script.shots[0].source_end_sec > script.shots[0].source_start_sec
    assert script.shots[1].source_end_sec <= 120.0


def test_assign_source_timestamps_from_cues():
    cues = [
        VttCue(1.0, 4.0, "bank"),
        VttCue(4.5, 8.0, "necklace"),
        VttCue(8.5, 12.0, "gun"),
    ]
    script = VideoScript(
        title="Recap",
        hook="Hook",
        summary="Summary",
        youtube_description="",
        shots=[Shot(0, "Scene", "Narration", "visual", 5.0)],
    )
    assign_source_timestamps(script, duration_sec=60.0, cues=cues)
    assert script.shots[0].source_start_sec == 1.0
    assert script.shots[0].source_end_sec >= 4.0


def test_catalog_source_clip_backend():
    from trendforge.domain.catalog import option_by_id

    opt = option_by_id("source_clip")
    assert opt is not None
    assert opt.backend.value == "source_clip"
