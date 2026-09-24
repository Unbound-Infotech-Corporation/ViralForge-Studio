"""Comment intake and theme ranking.

``CommentProvider`` is the plug-in point. ``ManualPasteProvider`` works with
no network. ``YouTubeCommentProvider`` is a stub until OAuth exists — it never
pretends a live download succeeded.

Deferred: YouTube ``commentThreads.list`` and a 48-hour scheduler. The meeting
state machine records the window; import stays manual.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Protocol

from trendforge.domain.mini_series import CommentItem, RankedTheme


class CommentProviderUnavailable(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class CommentProvider(Protocol):
    name: str

    def fetch(self, *, video_id: str, pasted_text: str = "") -> list[CommentItem]:
        """Return comments for one published episode."""


_SPAM_RE = re.compile(
    r"(https?://|www\.|bit\.ly|sub\s*4\s*sub|subscribe\s+to\s+my|"
    r"check\s+(?:out\s+)?my\s+channel|giveaway|crypto\s+airdrop|onlyfans)",
    re.IGNORECASE,
)
_TOXIC_RE = re.compile(
    r"(\bkill\s+yourself\b|\bkys\b|\bgo\s+die\b|\byou\s+should\s+die\b|"
    r"\bi\s+will\s+kill\b|\bretard(?:ed)?\b)",
    re.IGNORECASE,
)
_STOP = frozenset(
    """
    the a an and or but if to of for on in with this that those these your you
    our we they them it is are was were be been being what when where how why
    more next please about from just really very like want wanna episode video
    series watch watched watching loved love great good nice awesome thanks
    thank please follow follow-up
    """.split()
)


def is_spam(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return True
    if _SPAM_RE.search(raw):
        return True
    if re.search(r"(.)\1{6,}", raw):
        return True
    letters = [ch for ch in raw if ch.isalpha()]
    if len(letters) >= 12 and sum(1 for ch in letters if ch.isupper()) / len(letters) > 0.85:
        return True
    return False


def is_toxic(text: str) -> bool:
    return bool(_TOXIC_RE.search(text or ""))


def parse_comment_paste(text: str) -> list[CommentItem]:
    """Parse ``Name: comment`` lines or ``Name | comment | likes`` rows."""
    items: list[CommentItem] = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "|" in line:
            parts = [part.strip() for part in line.split("|")]
            author = parts[0] or "viewer"
            body = parts[1] if len(parts) > 1 else ""
            likes = 0
            if len(parts) > 2:
                try:
                    likes = int(float(parts[2]))
                except ValueError:
                    likes = 0
            if body:
                items.append(CommentItem(author=author, text=body, like_count=max(0, likes)))
            continue
        if ":" in line:
            author, body = line.split(":", 1)
            if body.strip():
                items.append(CommentItem(author=author.strip() or "viewer", text=body.strip()))
            continue
        items.append(CommentItem(author="viewer", text=line))
    if not items:
        raise ValueError("No comments found. Use 'Name: comment' or 'Name | comment | likes'.")
    return items


def significant_tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9']+", (text or "").lower())
    return [word for word in words if len(word) > 3 and word not in _STOP]


def rank_themes(comments: list[CommentItem], *, limit: int = 5) -> list[RankedTheme]:
    """Drop spam and toxicity, then rank remaining themes by support and likes."""
    kept = [item for item in comments if not is_spam(item.text) and not is_toxic(item.text)]
    tokenized: list[list[str]] = []
    doc_freq: Counter[str] = Counter()
    for item in kept:
        tokens = significant_tokens(item.text)
        tokenized.append(tokens)
        doc_freq.update(set(tokens))

    buckets: dict[str, list[CommentItem]] = {}
    for item, tokens in zip(kept, tokenized):
        if not tokens:
            key = "general"
        else:
            key = max(tokens, key=lambda token: (doc_freq[token], -tokens.index(token)))
        buckets.setdefault(key, []).append(item)

    ranked: list[RankedTheme] = []
    for key, group in buckets.items():
        score = sum(1.0 + math.log1p(max(0, item.like_count)) for item in group)
        ranked.append(
            RankedTheme(
                theme=key,
                score=round(score, 3),
                comment_count=len(group),
                examples=[item.text.strip()[:180] for item in group[:3]],
            )
        )
    ranked.sort(key=lambda theme: (-theme.score, -theme.comment_count, theme.theme))
    return ranked[:limit]


class ManualPasteProvider:
    name = "manual_paste"

    def fetch(self, *, video_id: str, pasted_text: str = "") -> list[CommentItem]:
        del video_id
        if not (pasted_text or "").strip():
            raise CommentProviderUnavailable("Paste comments to import them.")
        try:
            return parse_comment_paste(pasted_text)
        except ValueError as exc:
            raise CommentProviderUnavailable(str(exc)) from exc


class YouTubeCommentProvider:
    """Stub. Live ``commentThreads.list`` waits on OAuth that this app does not have.

    TODO(script-lab-adjacent): when settings carry a real OAuth client secret,
    implement fetch and keep ``ManualPasteProvider`` as the fallback.
    """

    name = "youtube"

    def __init__(self, api_key: str = "", credentials_path: str = "") -> None:
        self.api_key = (api_key or "").strip()
        self.credentials_path = (credentials_path or "").strip()

    @property
    def configured(self) -> bool:
        return bool(self.api_key or self.credentials_path)

    def fetch(self, *, video_id: str, pasted_text: str = "") -> list[CommentItem]:
        del video_id, pasted_text
        raise CommentProviderUnavailable(
            "YouTube comment download is not available yet. Paste comments from the video."
        )


def comment_source_status(settings: object) -> str:
    provider = YouTubeCommentProvider(
        api_key=str(getattr(settings, "youtube_api_key", "") or ""),
        credentials_path=str(getattr(settings, "youtube_credentials_path", "") or ""),
    )
    if provider.configured:
        return (
            "YouTube credentials are saved, but live comment download is not wired yet. "
            "Paste comments for this 48-hour pass."
        )
    return (
        "No YouTube OAuth in settings. Paste comments — CommentProvider will accept a "
        "YouTube implementation later without changing this page."
    )
