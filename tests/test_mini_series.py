"""State machine, approve gate, comment ranking, and Cinema-only produce."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from trendforge.domain.enums import BackendKind, ShotSegmentKind
from trendforge.domain.mini_series import EpisodePhase, new_series
from trendforge.domain.models import Shot, VideoScript
from trendforge.services.mini_series.comments import (
    CommentProviderUnavailable,
    ManualPasteProvider,
    YouTubeCommentProvider,
    comment_source_status,
    is_spam,
    is_toxic,
    parse_comment_paste,
    rank_themes,
)
from trendforge.services.mini_series.guardrails import GUARDRAILS, meeting_warnings
from trendforge.services.mini_series.script_hook import fit_runtime, lock_script_to_footage, runtime_seconds
from trendforge.services.mini_series.state import (
    GateError,
    apply_meeting,
    can_draft_next,
    can_produce,
    can_publish,
    mark_approved,
    mark_published,
    monitor_is_open,
)
from trendforge.services.mini_series.store import MiniSeriesStore
from trendforge.services.mini_series.workflow import (
    assert_cinema_only,
    build_cinema_request,
    cinema_render_block_reason,
    draft_next_episode,
    import_comments,
    produce_episode,
)
from trendforge.services.projects import ProjectStore
from trendforge.settings import AppSettings
from trendforge.domain.mini_series import MeetingRecord


def _settings() -> AppSettings:
    return AppSettings(cinema_dry_run=True, channel_name="Signal Cut")


def _fill(episode) -> None:
    episode.meeting.storyline = "A warehouse fire spreads overnight and a court filing names the contractor."
    episode.meeting.goals = "Show the timeline and the questions viewers still have."
    episode.meeting.tone = "documentary"
    episode.meeting.notes = "No text cards. Avoid maestro."
    episode.meeting.guardrail_acks = {item.id: True for item in GUARDRAILS}
    episode.target_minutes = 7.5
    episode.phase = EpisodePhase.IN_MEETING


def test_approve_gate_blocks_produce_and_publish(tmp_path):
    series = new_series("Night Desk", "warehouse fire")
    episode = series.episodes[0]
    with pytest.raises(GateError, match="Approve"):
        produce_episode(
            series,
            episode,
            settings=_settings(),
            project_store=ProjectStore(tmp_path / "projects"),
        )
    assert not can_produce(episode).allowed
    assert not can_publish(episode).allowed
    with pytest.raises(GateError, match="Produce"):
        mark_published(episode)


def test_missing_ack_blocks_approval_even_with_copy():
    series = new_series("Night Desk", "warehouse fire")
    episode = series.episodes[0]
    _fill(episode)
    episode.meeting.guardrail_acks["human_review"] = False
    with pytest.raises(GateError, match="Human watches"):
        mark_approved(episode)
    assert episode.phase is not EpisodePhase.APPROVED


def test_soft_warnings_do_not_replace_the_ack_gate():
    notes = "Comment one word if you watched. You should invest in the contractor."
    warnings = meeting_warnings(notes)
    assert any("engagement bait" in item for item in warnings)
    assert any("financial" in item for item in warnings)
    assert meeting_warnings("No text cards. Avoid maestro.") == []
    assert any("Maestro" in item or "text cards" in item for item in meeting_warnings("Switch the picture to maestro title cards."))

    series = new_series("Night Desk", "warehouse fire")
    episode = series.episodes[0]
    _fill(episode)
    episode.meeting.notes = notes
    mark_approved(episode)
    assert episode.phase is EpisodePhase.APPROVED


def test_editing_meeting_closes_the_gate_again():
    series = new_series("Night Desk", "warehouse fire")
    episode = series.episodes[0]
    _fill(episode)
    mark_approved(episode)
    edited = MeetingRecord(
        storyline="A different story about the harbor.",
        goals=episode.meeting.goals,
        tone=episode.meeting.tone,
        notes=episode.meeting.notes,
        guardrail_acks=dict(episode.meeting.guardrail_acks),
    )
    apply_meeting(episode, edited, target_minutes=8)
    assert episode.meeting.approved is False
    assert episode.phase is EpisodePhase.IN_MEETING
    assert not can_produce(episode).allowed


def test_comment_parse_rank_and_filters():
    pasted = "\n".join(
        [
            "Ava: The warehouse scene should be its own chapter",
            "Ben | I keep thinking about that warehouse | 4",
            "Cara: More warehouse detail on the night shift",
            "Dee: The court filing deserves its own episode",
            "Spam: Check my channel http://spam.test warehouse",
            "Troll: kys warehouse",
            "# ignored",
        ]
    )
    comments = parse_comment_paste(pasted)
    assert len(comments) == 6
    assert comments[1].like_count == 4
    assert is_spam(comments[4].text)
    assert is_toxic(comments[5].text)
    themes = rank_themes(comments)
    assert themes[0].theme == "warehouse"
    assert themes[0].comment_count == 3
    assert all("http" not in example for theme in themes for example in theme.examples)
    assert all("kys" not in example.lower() for theme in themes for example in theme.examples)
    assert any(theme.theme == "court" for theme in themes)


def test_youtube_provider_is_a_stub_and_paste_works():
    stub = YouTubeCommentProvider(api_key="secret")
    assert stub.configured
    with pytest.raises(CommentProviderUnavailable, match="Paste comments"):
        stub.fetch(video_id="abc123")
    manual = ManualPasteProvider()
    rows = manual.fetch(video_id="", pasted_text="Pat: The warehouse was the best part")
    assert rows[0].author == "Pat"
    settings = AppSettings._from_dict({"youtube_api_key": "secret", "youtube_credentials_path": "client.json"})
    assert settings.youtube_api_key == "secret"
    assert "not wired" in comment_source_status(settings)
    assert "Paste comments" in comment_source_status(AppSettings())


def test_publish_opens_48h_window_and_late_paste_still_imports():
    series = new_series("Night Desk", "warehouse fire")
    episode = series.episodes[0]
    _fill(episode)
    mark_approved(episode)
    episode.phase = EpisodePhase.RENDER_READY
    episode.project_id = "p-test"
    opened = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
    mark_published(episode, now=opened)
    assert episode.phase is EpisodePhase.MONITORING
    assert monitor_is_open(episode, now=opened + timedelta(hours=47))
    assert not monitor_is_open(episode, now=opened + timedelta(hours=49))
    import_comments(episode, "Ava: Tell me more about the warehouse\nBen: The court angle is unfinished")
    assert episode.themes
    assert can_draft_next(episode).allowed


def test_runtime_fit_and_text_cards_are_stripped():
    script = VideoScript(
        title="Cut",
        hook="Hook",
        summary="",
        youtube_description="",
        shots=[
            Shot(0, "Card", "Narration about the fire.", "dynamic title card, kinetic typography", 5, segment_kind=ShotSegmentKind.TITLE_CARD),
            Shot(1, "Coverage", "The street after midnight.", "handheld street coverage", 5),
        ],
    )
    lock_script_to_footage(script, topic="warehouse fire")
    fit_runtime(script, 450)
    assert script.shots[0].segment_kind is ShotSegmentKind.COMMENTARY
    assert "title card" not in script.shots[0].visual_prompt.lower()
    assert "kinetic typography" not in script.shots[0].visual_prompt.lower()
    assert 300 <= runtime_seconds(script) <= 600


def test_produce_locks_cinema_and_persists(tmp_path):
    series = new_series("Night Desk", "warehouse fire", channel_name="Signal Cut")
    episode = series.episodes[0]
    _fill(episode)
    settings = _settings()
    projects = ProjectStore(tmp_path / "projects")
    mini = MiniSeriesStore(tmp_path / "mini_series")
    request = build_cinema_request(episode, series, settings)
    assert request.backend is BackendKind.NATIVE_CINEMA
    assert request.model_id == "viralforge_cinema"
    request.backend = BackendKind.MAESTRO_DIRECTOR
    with pytest.raises(GateError, match="Cinema"):
        assert_cinema_only(request)
    request.backend = BackendKind.NATIVE_CINEMA
    request.model_id = "quick_explainer"
    with pytest.raises(GateError, match="banned"):
        assert_cinema_only(request)
    assert cinema_render_block_reason(settings)

    mark_approved(episode)
    project = produce_episode(series, episode, settings=settings, project_store=projects)
    assert episode.phase is EpisodePhase.RENDER_READY
    assert episode.project_id == project.id
    loaded = projects.load(project.id)
    assert loaded.request.backend is BackendKind.NATIVE_CINEMA
    assert loaded.request.model_id == "viralforge_cinema"
    assert loaded.script is not None
    total = sum(shot.duration_sec for shot in loaded.script.shots)
    assert 300 <= total <= 600
    for shot in loaded.script.shots:
        assert shot.segment_kind is not ShotSegmentKind.TITLE_CARD
        assert "title card" not in shot.visual_prompt.lower()
        assert "kinetic typography" not in shot.visual_prompt.lower()

    with pytest.raises(GateError, match="Produce"):
        produce_episode(series, episode, settings=settings, project_store=projects)

    mark_published(episode, now=datetime(2026, 4, 2, tzinfo=timezone.utc))
    import_comments(
        episode,
        "Ava: The warehouse scene should be its own chapter\n"
        "Ben | More on the warehouse night shift | 3\n"
        "Cara: The court filing is the real story\n"
        "Spam: subscribe to my channel http://spam.test",
    )
    nxt = draft_next_episode(series, episode, settings=settings)
    assert nxt.meeting.approved is False
    assert nxt.phase is EpisodePhase.IN_MEETING
    assert not can_produce(nxt).allowed
    assert nxt.source_episode_id == episode.id
    assert "warehouse" in nxt.topic

    mini.save(series)
    restored = mini.load(series.id)
    assert len(restored.episodes) == 2
    assert restored.episodes[0].phase is EpisodePhase.MONITORING
    assert restored.episodes[0].comments
    assert restored.episodes[1].meeting.approved is False
    assert restored.episodes[1].script
