"""Channel-safety guardrails for mini-series meetings.

These are the house rules for staying inside typical YouTube spam, harassment,
and reused-content enforcement. The meeting UI requires a human to acknowledge
each one before Approve. Wording scans are soft: they surface warnings and do
not replace that acknowledgement.

Hard bans (Maestro, Quick Explainer text cards) are enforced in the produce
path, not here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Guardrail:
    id: str
    title: str
    detail: str


GUARDRAILS: tuple[Guardrail, ...] = (
    Guardrail(
        "truthful_packaging",
        "Truthful title and thumbnail",
        "The title, thumbnail, and hook describe what the episode actually covers. Misleading clickbait is how channels lose trust and recommendations.",
    ),
    Guardrail(
        "no_engagement_bait",
        "No engagement bait",
        "No fake giveaways, 'comment one word' prompts, sub-for-sub, or other artificial engagement. YouTube treats that as spam.",
    ),
    Guardrail(
        "original_commentary",
        "Original commentary",
        "Narration is original. The picture is generated for this episode. Reused clips without commentary are out of scope.",
    ),
    Guardrail(
        "no_harassment",
        "No harassment",
        "No slurs, threats, or harassment of private people. Critique ideas and public work, not identities.",
    ),
    Guardrail(
        "no_dangerous_advice",
        "No dangerous advice",
        "No medical, financial, or legal instructions presented as professional advice. Frame uncertainty and point viewers to primary sources.",
    ),
    Guardrail(
        "rights_and_spam",
        "Rights and spam",
        "No unlicensed copyrighted footage, mass-tag stuffing, or external spam links in the video or pinned comment.",
    ),
    Guardrail(
        "native_cinema_only",
        "Cinema pictures only",
        "ViralForge Cinema (native Wan/Cog) only. Maestro and text-card explainers are banned for this format.",
    ),
    Guardrail(
        "human_review",
        "Human watches before publish",
        "A person reviews the cut and this meeting before the episode is marked published.",
    ),
)


def guardrail_ids() -> list[str]:
    return [item.id for item in GUARDRAILS]


def default_acks() -> dict[str, bool]:
    return {item.id: False for item in GUARDRAILS}


_BAIT_RE = re.compile(
    r"(comment\s+(?:one|1|a)\s+word|sub\s*4\s*sub|subscribe\s+to\s+my|"
    r"fake\s+giveaway|you\s+won'?t\s+believe|gone\s+wrong|"
    r"comment\s+['\"]?\w+['\"]?\s+if\s+you)",
    re.IGNORECASE,
)
_ADVICE_RE = re.compile(
    r"(you\s+should\s+(?:buy|invest|take)|guaranteed\s+returns|"
    r"this\s+cures|not\s+medical\s+advice\s+but\s+take|"
    r"financial\s+advice:\s*(?:buy|sell))",
    re.IGNORECASE,
)
_HATE_RE = re.compile(
    r"(\bkill\s+yourself\b|\bkys\b|\bgo\s+die\b|\byou\s+should\s+die\b|"
    r"\bi\s+will\s+kill\b)",
    re.IGNORECASE,
)
_BANNED_PICTURE_RE = re.compile(
    r"(title\s+cards?|text\s+cards?|kinetic\s+typography|quick\s+explainer|\bmaestro\b)",
    re.IGNORECASE,
)
_NEGATED_RE = re.compile(r"\b(no|not|without|avoid|ban|banned|never)\s+$", re.IGNORECASE)


def _affirmed(text: str, match: re.Match[str]) -> bool:
    prefix = text[max(0, match.start() - 16) : match.start()]
    return _NEGATED_RE.search(prefix) is None


def meeting_warnings(*parts: str) -> list[str]:
    """Soft checks. Empty list means the scan found nothing to flag."""
    text = "\n".join(part for part in parts if part).strip()
    if not text:
        return []
    warnings: list[str] = []
    if any(_affirmed(text, match) for match in _BAIT_RE.finditer(text)):
        warnings.append(
            "Story notes look like engagement bait (giveaway, 'comment one word', sub-for-sub). Rewrite before you publish."
        )
    if any(_affirmed(text, match) for match in _ADVICE_RE.finditer(text)):
        warnings.append(
            "Notes read as medical or financial instructions. Keep the episode descriptive, not advisory."
        )
    if _HATE_RE.search(text):
        warnings.append("Notes include a threat or harassment phrase. Cut it before Approve.")
    if any(_affirmed(text, match) for match in _BANNED_PICTURE_RE.finditer(text)):
        warnings.append(
            "Notes mention Maestro or text cards. Mini Series locks the picture path to native Cinema."
        )
    return warnings
