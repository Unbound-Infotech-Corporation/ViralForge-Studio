from trendforge.domain.enums import BackendKind, ContentFormat, MediaType, ShotSegmentKind
from trendforge.domain.models import GenerationRequest
from trendforge.services.review_validation import (
    MAX_TRAILER_RUNTIME_FRACTION,
    validate_opinion_input,
    validate_review_request,
    validate_review_runtime,
)
from trendforge.services.script_engine import template_review_script
from trendforge.services.trailer_allowlist import (
    AllowlistEntry,
    TrailerVerificationResult,
    YoutubeVideoMeta,
    verify_trailer_url,
)


def _sample_request(**overrides) -> GenerationRequest:
    base = dict(
        topic="Dune: Part Two",
        content_format=ContentFormat.REVIEW,
        backend=BackendKind.REVIEW,
        model_id="media_review",
        media_type=MediaType.MOVIE,
        review_subject="Dune: Part Two",
        trailer_url="https://www.youtube.com/watch?v=U2Qp5pL3ovA",
        allowlist_entry_id="warner_bros",
        user_rating=8.5,
        user_opinion="A visually stunning sequel that mostly delivers on the first film's promise.",
        user_liked="The worm-riding sequence and Hans Zimmer's score hit hard.",
        user_disliked="Some middle-act pacing sags and a few side characters get shortchanged.",
        user_moments="The arena fight and Paul's desert walk are the peaks.",
        user_verdict="Worth seeing on the biggest screen you can find if you liked Part One.",
        opinion_completed=True,
    )
    base.update(overrides)
    return GenerationRequest(**base)


def test_opinion_required_before_assembly():
    req = _sample_request(opinion_completed=False, user_opinion="")
    result = validate_review_request(req)
    assert not result.ok
    assert any("genuine review opinion" in err for err in result.errors)


def test_sparse_opinion_rejected():
    req = _sample_request(user_opinion="It was ok.", user_liked="", user_disliked="", user_moments="", user_verdict="")
    result = validate_opinion_input(req)
    assert not result.ok
    assert any("too short" in err.lower() for err in result.errors)


def test_fan_trailer_blocked_by_allowlist():
    fan_meta = YoutubeVideoMeta(
        video_id="fan123",
        title="Dune Part Two TRAILER (fan edit)",
        channel_id="UC_FAKE_FAN_CHANNEL",
        channel_name="FanEdits Daily",
        upload_date="20240101",
        duration_sec=120.0,
    )
    result = verify_trailer_url(
        "https://www.youtube.com/watch?v=fakefan",
        "warner_bros",
        meta=fan_meta,
    )
    assert not result.ok
    assert "not on the official allowlist" in result.reason


def test_official_trailer_accepted():
    official_meta = YoutubeVideoMeta(
        video_id="official",
        title="Dune: Part Two | Official Trailer",
        channel_id="UCq-Fj5jwhLhHu_iKL_vid",
        channel_name="Warner Bros. Pictures",
        upload_date="20230915",
        duration_sec=150.0,
    )
    result = verify_trailer_url(
        "https://www.youtube.com/watch?v=official",
        "warner_bros",
        meta=official_meta,
    )
    assert result.ok
    assert result.attribution is not None
    assert result.attribution.studio == "Warner Bros. Pictures"


def test_review_script_trailer_minority():
    req = _sample_request()
    script = template_review_script(req)
    total = sum(s.duration_sec for s in script.shots)
    trailer = sum(s.duration_sec for s in script.shots if s.segment_kind is ShotSegmentKind.TRAILER)
    assert trailer / total <= MAX_TRAILER_RUNTIME_FRACTION
    runtime = validate_review_runtime(script)
    assert runtime.ok


def test_review_script_uses_user_words():
    req = _sample_request()
    script = template_review_script(req)
    blob = " ".join(s.narration for s in script.shots if s.segment_kind is ShotSegmentKind.COMMENTARY)
    assert "worm-riding" in blob or "worm riding" in blob.lower() or "Hans Zimmer" in blob
    assert "8.5" in script.title or "8.5" in blob


def test_unknown_allowlist_entry_rejected():
    result = verify_trailer_url("https://www.youtube.com/watch?v=x", "not_a_real_entry")
    assert not result.ok
    assert "Unknown allowlist entry" in result.reason
