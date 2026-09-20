from __future__ import annotations

import json
import re
from html import unescape
from typing import Iterable
from urllib.parse import quote_plus
from xml.etree import ElementTree as ET

import httpx

from trendforge.domain.enums import TrendCategory
from trendforge.domain.models import TrendItem, new_id
from trendforge.logging_setup import get_logger

log = get_logger("trends")

USER_AGENT = "TrendForgeStudio/1.0 (Windows desktop; local; +https://github.com/)"
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json, application/rss+xml, text/xml, */*"}


def _client() -> httpx.Client:
    return httpx.Client(timeout=12.0, headers=HEADERS, follow_redirects=True)


def _clean(text: str) -> str:
    text = unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def _rss_items(xml_text: str, category: TrendCategory, source: str, limit: int = 20) -> list[TrendItem]:
    items: list[TrendItem] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items
    nodes = root.findall(".//item")
    if not nodes:
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for entry in root.findall(".//{http://www.w3.org/2005/Atom}entry"):
            title = _clean(entry.findtext("{http://www.w3.org/2005/Atom}title") or "")
            link_el = entry.find("{http://www.w3.org/2005/Atom}link")
            url = link_el.get("href") if link_el is not None else ""
            summary = _clean(entry.findtext("{http://www.w3.org/2005/Atom}summary") or "")
            if title:
                items.append(
                    TrendItem(
                        id=new_id("t"),
                        title=title,
                        category=category,
                        source=source,
                        url=url or "",
                        summary=summary,
                    )
                )
            if len(items) >= limit:
                break
        return items
    for node in nodes[:limit]:
        title = _clean(node.findtext("title") or "")
        url = _clean(node.findtext("link") or "")
        summary = _clean(node.findtext("description") or node.findtext("summary") or "")
        thumb = ""
        enclosure = node.find("enclosure")
        if enclosure is not None:
            thumb = enclosure.get("url") or ""
        media = node.find("{http://search.yahoo.com/mrss/}thumbnail")
        if media is not None:
            thumb = media.get("url") or thumb
        if not title:
            continue
        items.append(
            TrendItem(
                id=new_id("t"),
                title=title,
                category=category,
                source=source,
                url=url,
                thumbnail=thumb,
                summary=summary[:400],
            )
        )
    return items


def fetch_google_trends(geo: str = "US") -> list[TrendItem]:
    url = f"https://trends.google.com/trending/rss?geo={geo}"
    alt = f"https://trends.google.com/trends/trendingsearches/daily/rss?geo={geo}"
    with _client() as client:
        for candidate in (url, alt):
            try:
                res = client.get(candidate)
                if res.status_code == 200 and "<" in res.text:
                    items = _rss_items(res.text, TrendCategory.VIRAL, "Google Trends")
                    for it in items:
                        it.score_label = "Trending search"
                    if items:
                        return items
            except httpx.HTTPError as exc:
                log.info("Google Trends failed (%s): %s", candidate, exc)
    return []


def fetch_news() -> list[TrendItem]:
    feeds = [
        ("BBC News", "https://feeds.bbci.co.uk/news/rss.xml"),
        ("NPR", "https://feeds.npr.org/1001/rss.xml"),
        ("Google News", "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"),
    ]
    out: list[TrendItem] = []
    with _client() as client:
        for source, url in feeds:
            try:
                res = client.get(url)
                if res.status_code == 200:
                    out.extend(_rss_items(res.text, TrendCategory.NEWS, source, limit=12))
            except httpx.HTTPError as exc:
                log.info("News feed failed %s: %s", source, exc)
    return out[:30]


def fetch_reddit(subreddits: Iterable[str], category: TrendCategory, source_label: str) -> list[TrendItem]:
    out: list[TrendItem] = []
    with _client() as client:
        for sub in subreddits:
            url = f"https://www.reddit.com/r/{sub}/hot.json?limit=15&raw_json=1"
            try:
                res = client.get(url)
                if res.status_code != 200:
                    continue
                data = res.json()
            except Exception as exc:
                log.info("Reddit %s failed: %s", sub, exc)
                continue
            for child in data.get("data", {}).get("children", []):
                post = child.get("data") or {}
                title = _clean(post.get("title") or "")
                if not title or post.get("stickied"):
                    continue
                thumb = post.get("thumbnail") or ""
                if thumb in {"self", "default", "nsfw", "spoiler"}:
                    thumb = ""
                preview = (((post.get("preview") or {}).get("images") or [{}])[0].get("source") or {}).get("url")
                if preview:
                    thumb = preview.replace("&amp;", "&")
                score = int(post.get("score") or 0)
                permalink = post.get("permalink") or ""
                out.append(
                    TrendItem(
                        id=new_id("t"),
                        title=title,
                        category=category,
                        source=f"r/{sub}",
                        url=f"https://www.reddit.com{permalink}" if permalink else post.get("url") or "",
                        thumbnail=thumb,
                        score_label=f"{score:,} upvotes",
                        summary=_clean(post.get("selftext") or "")[:400],
                        extra={"subreddit": sub, "score": score},
                    )
                )
    return out


def fetch_youtube_trending() -> list[TrendItem]:
    """Use yt-dlp when present; otherwise fall back to YouTube RSS popular feed."""
    try:
        from yt_dlp import YoutubeDL  # type: ignore
    except Exception:
        YoutubeDL = None  # type: ignore

    if YoutubeDL is not None:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "skip_download": True,
            "playlistend": 20,
        }
        try:
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info("https://www.youtube.com/feed/trending", download=False)
            entries = info.get("entries") or []
            items: list[TrendItem] = []
            for entry in entries[:20]:
                if not entry:
                    continue
                vid = entry.get("id") or ""
                title = entry.get("title") or "Untitled"
                views = entry.get("view_count")
                items.append(
                    TrendItem(
                        id=new_id("t"),
                        title=title,
                        category=TrendCategory.YOUTUBE,
                        source="YouTube Trending",
                        url=entry.get("url") or (f"https://www.youtube.com/watch?v={vid}" if vid else ""),
                        thumbnail=f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if vid else "",
                        score_label=f"{int(views):,} views" if views else "Trending",
                        extra={"video_id": vid},
                    )
                )
            if items:
                return items
        except Exception as exc:
            log.info("yt-dlp trending failed: %s", exc)

    # Public RSS fallback — not official trending, but always free
    rss = "https://www.youtube.com/feeds/videos.xml?chart=mostPopular"
    with _client() as client:
        try:
            res = client.get(rss)
            if res.status_code == 200:
                items = _rss_items(res.text, TrendCategory.YOUTUBE, "YouTube")
                for it in items:
                    it.score_label = "Popular"
                return items
        except httpx.HTTPError as exc:
            log.info("YouTube RSS failed: %s", exc)
    return []


def search_topics(query: str) -> list[TrendItem]:
    q = query.strip()
    if not q:
        return []
    url = f"https://news.google.com/rss/search?q={quote_plus(q)}&hl=en-US&gl=US&ceid=US:en"
    with _client() as client:
        try:
            res = client.get(url)
            if res.status_code == 200:
                items = _rss_items(res.text, TrendCategory.CUSTOM, "Search")
                return items
        except httpx.HTTPError as exc:
            log.info("Search failed: %s", exc)
    return [
        TrendItem(
            id=new_id("t"),
            title=q,
            category=TrendCategory.CUSTOM,
            source="Custom",
            summary=f"Custom topic: {q}",
        )
    ]


def fetch_category(category: TrendCategory, region: str = "US") -> list[TrendItem]:
    if category is TrendCategory.YOUTUBE:
        return fetch_youtube_trending()
    if category is TrendCategory.NEWS:
        return fetch_news()
    if category is TrendCategory.MOVIES_TV:
        return fetch_reddit(("movies", "television", "boxoffice"), TrendCategory.MOVIES_TV, "Movies & TV")
    if category is TrendCategory.VIRAL:
        viral = fetch_google_trends(region)
        viral += fetch_reddit(("videos", "nextfuckinglevel", "interestingasfuck"), TrendCategory.VIRAL, "Viral")
        return viral
    return fetch_google_trends(region)


def fetch_all(region: str = "US") -> dict[TrendCategory, list[TrendItem]]:
    return {
        TrendCategory.YOUTUBE: fetch_youtube_trending(),
        TrendCategory.NEWS: fetch_news(),
        TrendCategory.MOVIES_TV: fetch_reddit(
            ("movies", "television"), TrendCategory.MOVIES_TV, "Movies & TV"
        ),
        TrendCategory.VIRAL: fetch_google_trends(region)
        + fetch_reddit(("videos",), TrendCategory.VIRAL, "Viral"),
    }
