import json

import pytest

from trendforge.domain.models import EpisodeBrief, SeasonPlan, Shot, VideoScript
from trendforge.services.script_import import apply_script_text, insert_draft, script_from_import_text


def test_outline_becomes_episode_shots():
    text = """TITLE: Harbor Lights
LOGLINE: A night shift on the docks goes wrong.
SYNOPSIS: The crew finds a sealed crate.
BEATS:
1. Cold open on the crane
2. The crate is not on the manifest
"""
    script = script_from_import_text(text, topic="docks")
    assert script.title == "Harbor Lights"
    assert "night shift" in script.hook
    assert [shot.narration for shot in script.shots] == [
        "Cold open on the crane",
        "The crate is not on the manifest",
    ]


def test_bracket_vo_and_visual_strips_text_cards():
    text = "[Hook]\nVO: Everyone is talking.\nVisual: dynamic title card, kinetic typography"
    script = script_from_import_text(text, topic="deepfakes")
    shot = script.shots[0]
    assert shot.title == "Hook"
    assert shot.narration == "Everyone is talking."
    visual = shot.visual_prompt.lower()
    assert "title card" not in visual
    assert "kinetic typography" not in visual
    assert "photoreal cinematic" in visual


def test_append_keeps_existing_voiceover_and_replace_drops_it():
    current = script_from_import_text("[Cold open] Keep this line.", topic="Harbor")
    appended = apply_script_text(current, "[Crate] Add this line.", mode="append", topic="Harbor")
    assert appended is current
    assert appended.shots[0].narration == "Keep this line."
    assert appended.shots[1].title == "Crate"
    assert appended.shots[1].narration == "Add this line."

    replaced = apply_script_text(current, "[Only] Fresh line.", mode="replace", topic="Harbor")
    assert [shot.narration for shot in replaced.shots] == ["Fresh line."]
    assert replaced.title


def test_replace_keeps_season_plan():
    current = VideoScript(
        title="Old",
        hook="old hook",
        summary="old summary",
        youtube_description="old",
        shots=[Shot(index=0, title="A", narration="keep me", visual_prompt="a dock at night")],
        season=SeasonPlan(
            series_title="Night Dock",
            logline="A crate arrives.",
            episodes=[EpisodeBrief(1, "Arrival", "hook", "thesis", "summary")],
        ),
    )
    replaced = apply_script_text(current, "The crane turns over black water.", mode="replace", topic="Harbor")
    assert replaced.season is not None
    assert replaced.season.series_title == "Night Dock"
    assert replaced.shots
    assert "keep me" not in replaced.shots[0].narration
    assert "crane" in replaced.shots[0].narration


def test_json_script_payload():
    raw = json.dumps(
        {
            "title": "Dock",
            "hook": "Look",
            "shots": [
                {
                    "title": "Hook",
                    "narration": "Look at the crane.",
                    "visual_prompt": "wide shot of a crane at night",
                    "duration_sec": 5,
                }
            ],
        }
    )
    script = script_from_import_text(raw, topic="docks")
    assert script.title == "Dock"
    assert script.shots[0].narration == "Look at the crane."


def test_import_rejects_empty_and_bad_mode():
    with pytest.raises(ValueError, match="Nothing to import"):
        apply_script_text(None, "  ", mode="append")
    with pytest.raises(ValueError, match="Unknown import mode"):
        apply_script_text(None, "Hello", mode="merge")


def test_insert_draft_append_and_replace():
    assert insert_draft("", "TITLE: Dock", "append") == "TITLE: Dock"
    assert insert_draft("existing", "TITLE: Dock", "append") == "existing\n\nTITLE: Dock"
    assert insert_draft("existing", "TITLE: Dock", "replace") == "TITLE: Dock"
