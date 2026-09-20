from __future__ import annotations

from dataclasses import dataclass

from trendforge.domain.enums import MediaType, ShotSegmentKind
from trendforge.domain.models import GenerationRequest, VideoScript
from trendforge.services.trailer_allowlist import verify_trailer_url

MIN_OPINION_CHARS = 80
MIN_DETAIL_FIELDS = 2
MAX_TRAILER_RUNTIME_FRACTION = 0.25
MAX_TRAILER_CLIP_SEC = 6.0


@dataclass(slots=True)
class ReviewValidationResult:
    ok: bool
    errors: list[str]
    warnings: list[str]


def opinion_text_blob(req: GenerationRequest) -> str:
    return "\n".join(
        part.strip()
        for part in (
            req.user_opinion,
            req.user_liked,
            req.user_disliked,
            req.user_moments,
            req.user_verdict,
        )
        if part.strip()
    )


def validate_opinion_input(req: GenerationRequest) -> ReviewValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    if not req.opinion_completed:
        errors.append(
            "Complete your genuine review opinion first — check the confirmation box after entering your rating and notes."
        )

    blob = opinion_text_blob(req)
    if len(blob) < MIN_OPINION_CHARS:
        errors.append(
            f"Your opinion is too short ({len(blob)} chars). Add what you liked, disliked, key moments, "
            f"and a verdict — at least {MIN_OPINION_CHARS} characters total. TrendForge will not invent opinions."
        )

    filled = sum(
        1
        for part in (req.user_opinion, req.user_liked, req.user_disliked, req.user_moments, req.user_verdict)
        if len(part.strip()) >= 20
    )
    if filled < MIN_DETAIL_FIELDS:
        warnings.append(
            "Add more detail in at least two fields (liked, disliked, moments, verdict) so the review reflects your real take."
        )

    if req.user_rating <= 0:
        errors.append("Enter your rating/score — the pipeline does not generate one for you.")

    if not req.review_subject.strip():
        errors.append("Enter the movie, show, or game title you are reviewing.")

    if not req.trailer_url.strip():
        errors.append("Paste the official trailer URL from an allowlisted studio channel.")

    if not req.allowlist_entry_id.strip():
        errors.append("Select the official studio/publisher from the allowlist — search results are not used.")

    if req.media_type is MediaType.GAME and req.gameplay_path.strip():
        from pathlib import Path

        if not Path(req.gameplay_path.strip()).exists():
            warnings.append("Gameplay capture path not found — trailer clips will be used instead.")

    return ReviewValidationResult(not errors, errors, warnings)


def validate_trailer_source(req: GenerationRequest) -> ReviewValidationResult:
    result = verify_trailer_url(req.trailer_url, req.allowlist_entry_id)
    if not result.ok:
        return ReviewValidationResult(False, [result.reason], [])
    return ReviewValidationResult(True, [], [])


def validate_review_request(req: GenerationRequest) -> ReviewValidationResult:
    opinion = validate_opinion_input(req)
    if not opinion.ok:
        return opinion
    trailer = validate_trailer_source(req)
    if not trailer.ok:
        return ReviewValidationResult(False, trailer.errors, opinion.warnings)
    return ReviewValidationResult(True, [], opinion.warnings)


def validate_review_runtime(script: VideoScript) -> ReviewValidationResult:
    if not script.shots:
        return ReviewValidationResult(False, ["Review script has no shots."], [])

    total = sum(s.duration_sec for s in script.shots)
    trailer = sum(
        s.duration_sec
        for s in script.shots
        if s.segment_kind is ShotSegmentKind.TRAILER
    )
    if total <= 0:
        return ReviewValidationResult(False, ["Review has zero runtime."], [])

    fraction = trailer / total
    errors: list[str] = []
    warnings: list[str] = []
    if fraction > MAX_TRAILER_RUNTIME_FRACTION:
        errors.append(
            f"Trailer footage is {fraction:.0%} of runtime (max {MAX_TRAILER_RUNTIME_FRACTION:.0%}). "
            "Commentary must carry the review."
        )
    long_trailer_shots = [
        s for s in script.shots if s.segment_kind is ShotSegmentKind.TRAILER and s.duration_sec > MAX_TRAILER_CLIP_SEC
    ]
    if long_trailer_shots:
        warnings.append(
            f"{len(long_trailer_shots)} trailer clip(s) exceed {MAX_TRAILER_CLIP_SEC}s — shorten to punctuate points."
        )
    return ReviewValidationResult(not errors, errors, warnings)
