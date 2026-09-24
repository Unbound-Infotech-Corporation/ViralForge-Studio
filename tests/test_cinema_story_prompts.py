"""Native cinema prompts stay locked to the beat, not the headline."""

from __future__ import annotations

import re

import pytest

from trendforge.cinema.director import episode_from_script_shots
from trendforge.cinema.story_prompts import (
    CinemaPromptError,
    positive_picture,
    synthesize_beats_from_vo,
)
from trendforge.services.visual_policy import CINEMATIC_LOOK

HEADLINE = "Chagos Islands: Streeting faces a row over the deal"

_BEATS = [
    ("Hook", "Britain kept the islands and removed the people."),
    ("Why it matters", "Wes Streeting told the Commons the treaty was already signed."),
    ("The evidence", "The documents list the families who were forced onto the ship."),
    ("The twist", "The map in the file still marks the base as British."),
    ("The takeaway", "The people are still waiting to go home."),
]

_BANNED_PICTURE = (
    "scuba",
    "phone",
    "skyline",
    "b-roll",
    "broll",
    "title card",
    "kinetic typography",
    "end card",
    "holiday beach",
)


def _episode(shots: list[tuple[str, str]], *, category: str = "news", style: str = "news_recap"):
    payload = [
        {
            "title": title,
            "narration": narration,
            "visual_prompt": HEADLINE,
            "duration_sec": 4.0,
        }
        for title, narration in shots
    ]
    return episode_from_script_shots(
        "Chagos explainer",
        HEADLINE,
        payload,
        style=style,
        category=category,
    )


def _roles(prompts: list[str]) -> list[str]:
    found = []
    for prompt in prompts:
        match = re.search(r"Narrative role: (\w+)", prompt)
        assert match, prompt
        found.append(match.group(1))
    return found


def test_headline_is_not_the_visual_prompt():
    episode = _episode([_BEATS[0]])
    prompt = episode.shots[0].visual_prompt
    picture = positive_picture(prompt).lower()

    assert prompt != HEADLINE
    assert not prompt.lower().startswith(HEADLINE.lower())
    assert HEADLINE.lower() not in prompt.lower()
    assert "removed" in prompt.lower()
    assert "must depict:" in prompt.lower()
    assert "must not depict:" in prompt.lower()
    assert CINEMATIC_LOOK in prompt.lower()
    for banned in _BANNED_PICTURE:
        assert banned not in picture, banned
    assert "scuba" in prompt.lower()
    assert "phones" in prompt.lower()


def test_vo_line_changes_the_prompt():
    topic_only = "documentary coverage of the headline: crowds, cameras, streets, cinematic b-roll"
    commons = episode_from_script_shots(
        "Chagos explainer",
        HEADLINE,
        [
            {
                "title": "The evidence",
                "narration": "Wes Streeting told the Commons the treaty was already signed.",
                "visual_prompt": topic_only,
            }
        ],
        category="news",
        style="news_recap",
    ).shots[0].visual_prompt
    documents = episode_from_script_shots(
        "Chagos explainer",
        HEADLINE,
        [
            {
                "title": "The evidence",
                "narration": "The documents list the families who were forced onto the ship.",
                "visual_prompt": topic_only,
            }
        ],
        category="news",
        style="news_recap",
    ).shots[0].visual_prompt

    assert commons != documents
    assert "commons" in commons.lower()
    assert "streeting" in commons.lower()
    assert "documents" in documents.lower()
    assert "families" in documents.lower()
    assert "commons" not in positive_picture(documents).lower()
    assert "cinematic b-roll" not in positive_picture(commons).lower()
    assert "cinematic b-roll" not in positive_picture(documents).lower()
    assert HEADLINE.lower() not in commons.lower()
    assert HEADLINE.lower() not in documents.lower()


def test_multi_shot_prompts_are_diverse():
    episode = _episode(_BEATS)
    prompts = [shot.visual_prompt for shot in episode.shots]
    pictures = [positive_picture(prompt) for prompt in prompts]

    assert len(set(prompts)) == len(prompts)
    assert len({picture.split(" on ", 1)[0] for picture in pictures}) == len(pictures)
    assert _roles(prompts) == ["setup", "conflict", "evidence", "turn", "payoff"]
    assert "removed" in prompts[0].lower()
    assert "commons" in prompts[1].lower()
    assert "documents" in prompts[2].lower()
    assert "map" in prompts[3].lower()
    assert "waiting" in prompts[4].lower()
    for prompt in prompts:
        picture = positive_picture(prompt).lower()
        assert HEADLINE.lower() not in prompt.lower()
        assert "narrative role:" in prompt.lower()
        for banned in _BANNED_PICTURE:
            assert banned not in picture


def test_missing_beats_fail_loud_instead_of_headline_prompt():
    with pytest.raises(CinemaPromptError, match="headline-only"):
        episode_from_script_shots("Chagos explainer", HEADLINE, [])
    with pytest.raises(CinemaPromptError, match="headline-only"):
        episode_from_script_shots("Chagos explainer", HEADLINE, [], voiceover=HEADLINE)
    with pytest.raises(CinemaPromptError, match="headline-only"):
        episode_from_script_shots(
            "Chagos explainer",
            HEADLINE,
            [{"title": "Hook", "narration": HEADLINE, "visual_prompt": HEADLINE}],
        )


def test_voiceover_without_shots_synthesizes_beats():
    voiceover = (
        f"{HEADLINE}. "
        "Britain kept the islands and removed the people. "
        "Wes Streeting told the Commons the treaty was already signed. "
        "The people are still waiting to go home."
    )
    beats = synthesize_beats_from_vo(voiceover, topic=HEADLINE)
    assert len(beats) >= 3
    episode = episode_from_script_shots(
        "Chagos explainer",
        HEADLINE,
        [],
        voiceover=voiceover,
        category="news",
    )
    prompts = [shot.visual_prompt for shot in episode.shots]
    assert len(prompts) == len(beats)
    assert len(set(prompts)) == len(prompts)
    assert _roles(prompts)[0] == "setup"
    assert _roles(prompts)[-1] == "payoff"
    joined = " ".join(prompts).lower()
    assert "removed" in joined
    assert "commons" in joined
    assert HEADLINE.lower() not in joined


def test_gaming_beat_stays_in_the_game_world():
    prompt = episode_from_script_shots(
        "Raid recap",
        "The raid boss is broken",
        [
            {
                "title": "The twist",
                "narration": "The boss punishes greedy heals in the second phase.",
                "visual_prompt": "The raid boss is broken",
            }
        ],
        category="games",
        style="breakdown",
    ).shots[0].visual_prompt
    picture = positive_picture(prompt).lower()
    assert "boss" in picture
    assert "heals" in prompt.lower() or "second" in prompt.lower()
    assert "parliament" not in picture
    assert "scuba" not in picture
    assert "the raid boss is broken" not in prompt.lower()
