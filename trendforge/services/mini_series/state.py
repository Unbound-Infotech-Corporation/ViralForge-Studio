"""Episode state machine and the human approve gate.

Produce and Publish are refused until the meeting is approved. A published
episode stays in the 48-hour comment window; the next episode is a new row
that must be approved on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from trendforge.domain.mini_series import (
    MAX_EPISODE_MINUTES,
    MIN_EPISODE_MINUTES,
    MONITOR_WINDOW_HOURS,
    CommentItem,
    EpisodePhase,
    MeetingRecord,
    MiniEpisode,
    RankedTheme,
)
from trendforge.services.mini_series.guardrails import GUARDRAILS, default_acks


class GateError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True, slots=True)
class GateDecision:
    allowed: bool
    reason: str = ""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def ensure_acks(meeting: MeetingRecord) -> None:
    defaults = default_acks()
    defaults.update({key: bool(value) for key, value in meeting.guardrail_acks.items()})
    meeting.guardrail_acks = defaults


def meeting_blockers(episode: MiniEpisode) -> list[str]:
    """Reasons Approve must be refused. Empty means the gate can open."""
    if episode.phase is EpisodePhase.MONITORING:
        return ["This episode is already published. Draft the next episode instead of re-approving it."]
    meeting = episode.meeting
    ensure_acks(meeting)
    blockers: list[str] = []
    if not meeting.storyline.strip():
        blockers.append("Storyline is required.")
    if not meeting.goals.strip():
        blockers.append("Goals are required.")
    if not (meeting.tone or "").strip():
        blockers.append("Tone is required.")
    if not (MIN_EPISODE_MINUTES <= float(episode.target_minutes) <= MAX_EPISODE_MINUTES):
        blockers.append(
            f"Target length must be {MIN_EPISODE_MINUTES:.0f}–{MAX_EPISODE_MINUTES:.0f} minutes."
        )
    missing = [item.title for item in GUARDRAILS if not meeting.guardrail_acks.get(item.id)]
    if missing:
        blockers.append("Acknowledge every guardrail: " + "; ".join(missing) + ".")
    return blockers


def meeting_material(episode: MiniEpisode) -> tuple:
    meeting = episode.meeting
    ensure_acks(meeting)
    acks = tuple(sorted((key, bool(value)) for key, value in meeting.guardrail_acks.items()))
    return (
        meeting.storyline.strip(),
        meeting.goals.strip(),
        meeting.tone.strip(),
        meeting.notes.strip(),
        acks,
        round(float(episode.target_minutes), 1),
    )


def _has_meeting_content(episode: MiniEpisode) -> bool:
    meeting = episode.meeting
    return bool(meeting.storyline.strip() or meeting.goals.strip() or meeting.notes.strip())


def apply_meeting(episode: MiniEpisode, meeting: MeetingRecord, *, target_minutes: float) -> None:
    """Copy meeting fields. Material edits after approval send the episode back to the meeting."""
    if episode.phase is EpisodePhase.MONITORING:
        raise GateError(
            "This episode is already published. Draft the next episode instead of editing this meeting."
        )
    previous = meeting_material(episode)
    episode.meeting.storyline = meeting.storyline
    episode.meeting.goals = meeting.goals
    episode.meeting.tone = meeting.tone or "documentary"
    episode.meeting.notes = meeting.notes
    episode.meeting.guardrail_acks = dict(meeting.guardrail_acks)
    ensure_acks(episode.meeting)
    episode.target_minutes = float(target_minutes)
    if meeting_material(episode) == previous:
        return
    episode.meeting.approved = False
    episode.meeting.approved_at = ""
    episode.project_id = ""
    episode.output_path = ""
    episode.script = None
    episode.phase = EpisodePhase.IN_MEETING if _has_meeting_content(episode) else EpisodePhase.BRIEF


def can_approve(episode: MiniEpisode) -> GateDecision:
    blockers = meeting_blockers(episode)
    if blockers:
        return GateDecision(False, " ".join(blockers))
    return GateDecision(True)


def mark_approved(episode: MiniEpisode, *, now: datetime | None = None) -> MiniEpisode:
    decision = can_approve(episode)
    if not decision.allowed:
        raise GateError(decision.reason)
    moment = _as_aware(now or _utc_now())
    episode.meeting.approved = True
    episode.meeting.approved_at = moment.isoformat()
    if episode.phase is not EpisodePhase.RENDER_READY:
        episode.phase = EpisodePhase.APPROVED
    episode.updated_at = moment.isoformat()
    return episode


def can_produce(episode: MiniEpisode) -> GateDecision:
    if episode.phase is EpisodePhase.MONITORING:
        return GateDecision(False, "This episode is already published.")
    if episode.phase is not EpisodePhase.APPROVED or not episode.meeting.approved:
        return GateDecision(False, "Approve the virtual meeting before Produce.")
    blockers = meeting_blockers(episode)
    if blockers:
        return GateDecision(False, " ".join(blockers))
    return GateDecision(True)


def mark_render_ready(
    episode: MiniEpisode,
    project_id: str,
    *,
    now: datetime | None = None,
) -> MiniEpisode:
    decision = can_produce(episode)
    if not decision.allowed:
        raise GateError(decision.reason)
    if not project_id:
        raise GateError("Cinema produce did not create a project.")
    moment = _as_aware(now or _utc_now())
    episode.project_id = project_id
    episode.phase = EpisodePhase.RENDER_READY
    episode.updated_at = moment.isoformat()
    return episode


def can_publish(episode: MiniEpisode) -> GateDecision:
    if episode.phase is not EpisodePhase.RENDER_READY or not episode.project_id:
        return GateDecision(False, "Produce the Cinema package before Publish.")
    if not episode.meeting.approved:
        return GateDecision(False, "Approve the virtual meeting before Publish.")
    return GateDecision(True)


def mark_published(episode: MiniEpisode, *, now: datetime | None = None) -> MiniEpisode:
    decision = can_publish(episode)
    if not decision.allowed:
        raise GateError(decision.reason)
    moment = _as_aware(now or _utc_now())
    episode.published_at = moment.isoformat()
    episode.monitor_until = (moment + timedelta(hours=MONITOR_WINDOW_HOURS)).isoformat()
    episode.phase = EpisodePhase.MONITORING
    episode.updated_at = moment.isoformat()
    return episode


def monitor_is_open(episode: MiniEpisode, *, now: datetime | None = None) -> bool:
    if episode.phase is not EpisodePhase.MONITORING or not episode.monitor_until:
        return False
    moment = _as_aware(now or _utc_now())
    end = datetime.fromisoformat(episode.monitor_until)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return moment < end


def can_import_comments(episode: MiniEpisode) -> GateDecision:
    if episode.phase is not EpisodePhase.MONITORING:
        return GateDecision(False, "Publish the episode before importing comments.")
    return GateDecision(True)


def record_comments(
    episode: MiniEpisode,
    comments: list[CommentItem],
    themes: list[RankedTheme],
) -> MiniEpisode:
    decision = can_import_comments(episode)
    if not decision.allowed:
        raise GateError(decision.reason)
    episode.comments = list(comments)
    episode.themes = list(themes)
    episode.updated_at = _utc_now().isoformat()
    return episode


def can_draft_next(episode: MiniEpisode) -> GateDecision:
    if episode.phase is not EpisodePhase.MONITORING:
        return GateDecision(False, "Publish this episode and import comments before drafting the next one.")
    if not episode.themes:
        return GateDecision(False, "No usable themes after the spam and toxicity filters.")
    return GateDecision(True)
