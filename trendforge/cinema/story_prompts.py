"""Story-locked Wan prompts for native cinema.

Each shot is staged from its narrative role and its own voiceover line.
The raw headline is never the picture. Generic stock coverage (crowds,
phones, skylines, postcard coasts) is a constraint to avoid, not the scene.
"""

from __future__ import annotations

import re

from trendforge.services.visual_policy import CINEMATIC_LOOK

MUST_DEPICT = "Must depict:"
MUST_NOT_DEPICT = "Must not depict:"

_ROLES = ("setup", "conflict", "evidence", "turn", "payoff")

_TITLE_ROLES: tuple[tuple[str, str], ...] = (
    ("cold open", "setup"),
    ("pattern interrupt", "setup"),
    ("previously", "setup"),
    ("what happened", "setup"),
    ("hook", "setup"),
    ("the lie", "conflict"),
    ("why it matters", "conflict"),
    ("the question", "conflict"),
    ("official story", "conflict"),
    ("what didn't", "conflict"),
    ("my take", "conflict"),
    ("key moment", "evidence"),
    ("the evidence", "evidence"),
    ("the truth", "evidence"),
    ("the people", "evidence"),
    ("standout", "evidence"),
    ("what worked", "evidence"),
    ("hidden layer", "turn"),
    ("the twist", "turn"),
    ("first crack", "turn"),
    ("the fork", "turn"),
    ("counter-story", "turn"),
    ("the machine", "turn"),
    ("takeaway", "payoff"),
    ("what it means", "payoff"),
    ("the cost", "payoff"),
    ("verdict", "payoff"),
    ("what to watch", "payoff"),
    ("next episode", "payoff"),
    ("next time", "payoff"),
    ("outro", "payoff"),
    ("cta", "payoff"),
)

_CAMERAS: dict[str, tuple[str, ...]] = {
    "setup": (
        "slow 35mm push-in from a locked wide to a medium, tripod, eye level",
        "24mm establishing from the doorway, gentle dolly in, eye level",
    ),
        "conflict": (
            "50mm handheld lateral drift between two opposing figures",
            "low 35mm push-in with a slight handheld shake",
        ),
    "evidence": (
        "macro insert on the proof, then an 85mm locked close-up",
        "overhead 50mm of the documents, then a slow tilt up to the hands",
    ),
    "turn": (
        "24mm arc onto a new angle as the decision lands",
        "motivated move from a wide to a tight profile as the practicals shift",
    ),
    "payoff": (
        "slow 35mm pull-back that leaves the subject small in the real room",
        "static 50mm hold on the aftermath, shallow depth, no montage",
    ),
}

_MOOD = {
    "setup": "watchful, cool, and precise",
    "conflict": "tense, urgent, and unsmiling",
    "evidence": "forensic, quiet, and exact",
    "turn": "charged, as if the air just changed",
    "payoff": "grave, resolved, and lingering",
}

_ROLE_FRAME = {
    "setup": "The situation is still intact, before the argument",
    "conflict": "The disagreement is visible between people in the same room",
    "evidence": "The proof is in the hands and on the table, examined up close",
    "turn": "This is the instant the decision changes the room",
    "payoff": "This is the quiet consequence after the decision",
}

_POLITICS_SUBJECT = {
    "setup": "a minister and civil servants around a paper map and a closed file",
    "conflict": "two sides of a government row facing each other across a dispatch box",
    "evidence": "signed pages and a list of names being checked by hand",
    "turn": "a minister stopping mid-sentence as a decision becomes public",
    "payoff": "an emptied briefing room and the people the decision landed on",
}

_NEWS_SUBJECT = {
    "setup": "the people this report is about, in the real place it happened",
    "conflict": "the two sides of this report standing in the same real location",
    "evidence": "the object, document, or place that proves this report",
    "turn": "the moment this report says the situation changed",
    "payoff": "the people living with the outcome of this report",
}

_GAMING_SUBJECT = {
    "setup": "the in-world space this voiceover enters, no menus and no HUD",
    "conflict": "the fight or clash this voiceover describes, readable in bodies and space",
    "evidence": "the mechanic or object this voiceover points at, held in frame",
    "turn": "the moment the encounter turns, in the character and the environment",
    "payoff": "the in-world aftermath, quiet, no results screen",
}

_GENERAL_SUBJECT = {
    "setup": "the specific person and place this voiceover is introducing",
    "conflict": "the specific clash this voiceover is describing",
    "evidence": "the specific proof this voiceover is pointing at",
    "turn": "the specific change this voiceover is revealing",
    "payoff": "the specific consequence this voiceover is leaving behind",
}

_STOP = {
    "a", "an", "the", "of", "to", "and", "or", "but", "if", "is", "are", "was",
    "were", "be", "been", "being", "this", "that", "those", "these", "it", "its",
    "in", "on", "for", "with", "from", "by", "as", "at", "into", "over", "under",
    "about", "not", "no", "nor", "so", "than", "then", "there", "their", "they",
    "them", "he", "she", "we", "you", "i", "our", "your", "his", "her", "who",
    "what", "when", "where", "why", "how", "just", "very", "really", "actually",
    "here", "stop", "scrolling", "everyone", "talking", "almost", "nobody",
    "understands", "short", "honest", "version", "story", "told", "remember",
    "one", "thing", "most", "some", "once", "watch", "which", "while", "still",
    "only", "before", "after", "around", "between", "next", "tonight", "follow",
    "subscribe", "comment", "click", "like", "channel", "episode", "will",
    "would", "could", "should", "have", "has", "had", "been", "being", "out",
    "up", "down", "off", "also", "too", "very", "just", "than", "then",
}

_GEO_WORDS = {
    "island", "islands", "coast", "coasts", "coastline", "beach", "beaches",
    "bay", "reef", "reefs", "atoll", "atolls", "ocean", "sea", "seas",
    "scuba", "shore", "shores", "tropical", "lagoon",
}

_NAME_SKIP = {
    "stop", "here", "this", "that", "then", "and", "the", "what", "when", "where",
    "why", "how", "if", "everyone", "almost", "follow", "tonight", "next", "before",
    "after", "around", "from", "real", "episode", "subscribe", "our", "your",
    "there", "they", "their", "about", "with", "into", "over", "under", "between",
    "most", "some", "once", "watch", "which", "while", "still", "just", "only",
    "hook", "shot", "outro", "intro",
    "british", "american", "english", "scottish", "welsh", "irish", "french",
    "german", "russian", "chinese", "indian", "african", "european",
}

_POLITICS_RE = re.compile(
    r"\b(ministers?|parliament|commons|lords|government|election|mps?|"
    r"labour|tory|tories|conservative|democrat|republican|senate|congress|"
    r"white house|downing street|prime minister|president|treaty|sovereignty|"
    r"deport\w*|immigration|chancellor|backbench|legislation|constituency|"
    r"whitehall|westminster|removed the people|displaced|colon(?:y|ial)|"
    r"citizenship|foreign secretary|home secretary|health secretary|"
    r"dispatch box)\b",
    re.IGNORECASE,
)

_GAMING_RE = re.compile(
    r"\b(gameplay|boss(?:\s+fight)?|speedrun|dlc|patch notes|steam|"
    r"playstation|xbox|nintendo|esports|open world|rpg|fps|nerf|buff|"
    r"hitbox|respawn|raid|mmo|heals?|in-world|hud)\b",
    re.IGNORECASE,
)

_NEWS_RE = re.compile(
    r"\b(breaking|newsroom|reported|according to|press conference|"
    r"this morning|last night|officials said)\b",
    re.IGNORECASE,
)

_VAGUE_RE = re.compile(
    r"\b(not the story you were told|real version is stranger|"
    r"what actually happened|where attention, money, and power|"
    r"could not look away|conversation exploded|context beats outrage|"
    r"still be trending|story is still moving|almost nobody understands|"
    r"short, honest version|who benefits if you stay mad|"
    r"one thing, remember this|viral version skips)\b",
    re.IGNORECASE,
)

_CTA_RE = re.compile(
    r"\b(subscribe|follow us|follow for|like and|comment below|link in bio)\b",
    re.IGNORECASE,
)

_ACTION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"removed the people|displaced|forced (?:them|the people).{0,40}(?:ship|boat)",
            re.IGNORECASE,
        ),
        "officials enforcing a removal while families carry coats and suitcases onto a working ship",
    ),
    (
        re.compile(r"waiting to go home|still waiting|go home", re.IGNORECASE),
        "the people the decision landed on, waiting with packed bags in a plain room",
    ),
    (
        re.compile(r"(told|addressed|facing) the (commons|parliament)|dispatch box", re.IGNORECASE),
        "{person} at the dispatch box addressing the chamber, papers gripped in one hand",
    ),
    (
        re.compile(r"\bmap\b", re.IGNORECASE),
        "a paper map on a ministerial desk, a finger marking one site in the file",
    ),
    (
        re.compile(r"treaty|already signed|signed the", re.IGNORECASE),
        "a signed treaty on the table between two people who will not look at each other",
    ),
    (
        re.compile(r"documents|the file|files list|list the families", re.IGNORECASE),
        "hands turning a file of family names beside a paper map on a ministerial desk",
    ),
    (
        re.compile(r"\b(boss|second phase|raid|respawn)\b", re.IGNORECASE),
        "the boss encounter this voiceover describes, bodies and space readable, no menus and no HUD",
    ),
    (
        re.compile(r"\b(gameplay|patch|nerf|buff|hitbox|heals?)\b", re.IGNORECASE),
        "the exact mechanic named in this voiceover, shown in the game world with no interface",
    ),
)


class CinemaPromptError(RuntimeError):
    """Cinema refused to invent a picture from the headline alone."""


def positive_picture(prompt: str) -> str:
    """The staged shot, without the negative constraint clause."""
    return prompt.split(MUST_NOT_DEPICT, 1)[0].strip()


def narrative_role(title: str, index: int, count: int) -> str:
    low = (title or "").lower()
    for needle, role in _TITLE_ROLES:
        if needle in low:
            return role
    if count <= 1:
        return "setup"
    slot = round(index * (len(_ROLES) - 1) / (count - 1))
    return _ROLES[max(0, min(slot, len(_ROLES) - 1))]


def detect_domain(
    topic: str,
    narration: str,
    *,
    style: str = "",
    category: str = "",
) -> str:
    blob = "\n".join((topic or "", narration or "", style or "", category or ""))
    cat = (category or "").strip().lower()
    style_l = (style or "").strip().lower()
    if cat in {"games", "game"} or (_GAMING_RE.search(blob) and not _POLITICS_RE.search(blob)):
        return "gaming"
    if _POLITICS_RE.search(blob) or _looks_like_political_row(blob):
        return "politics"
    if cat == "news" or style_l in {"news_recap", "news"} or _NEWS_RE.search(blob):
        return "news"
    return "general"


def synthesize_beats_from_vo(voiceover: str, *, topic: str = "") -> list[dict[str, str | float]]:
    """Split a voiceover into a minimal setup→payoff beat list.

    Raises CinemaPromptError when the only text is the headline.
    """
    raw = " ".join((voiceover or "").split())
    if not raw or _same(raw, topic):
        raise CinemaPromptError(_missing_beats_message())
    spoken = _excise(raw, topic)
    if not spoken or _is_vague(spoken):
        raise CinemaPromptError(_missing_beats_message())
    parts = _split_parts(spoken)
    if not parts:
        raise CinemaPromptError(_missing_beats_message())
    roles = _spread_roles(len(parts))
    titles = {
        "setup": "Setup",
        "conflict": "Conflict",
        "evidence": "Evidence",
        "turn": "Turn",
        "payoff": "Payoff",
    }
    beats: list[dict[str, str | float]] = []
    for role, part in zip(roles, parts, strict=True):
        beats.append(
            {
                "title": titles[role],
                "narration": part,
                "duration_sec": 4.0,
                "kind": "hero",
            }
        )
    return beats


def story_locked_prompt(
    *,
    topic: str,
    narration: str,
    shot_title: str,
    role: str,
    index: int = 0,
    script_title: str = "",
    style: str = "",
    category: str = "",
) -> str:
    """Build one cinematic Wan prompt locked to this beat and this VO line."""
    spoken = _excise(narration or "", topic, script_title)
    if not spoken or _same(narration, topic) or _same(narration, script_title):
        raise CinemaPromptError(
            f"Shot {index + 1} ({shot_title or 'untitled'}) has no voiceover beat. "
            "Refusing a headline-only prompt."
        )
    if role not in _ROLES:
        role = narrative_role(shot_title, index, max(index + 1, 1))
    domain = detect_domain(topic, spoken, style=style, category=category)
    action = _action_image(spoken, role, domain)
    anchor = _vo_anchor(spoken, topic)
    if _is_vague(spoken) and not action:
        action = _role_subject(domain, role)
        anchor = anchor or _role_frame_anchor(role)
    if not action and not anchor:
        raise CinemaPromptError(
            f"Shot {index + 1} ({shot_title or 'untitled'}) has no concrete voiceover beat. "
            "Refusing a headline-only prompt."
        )
    person = _lead_person(spoken)
    subject = action or _role_subject(domain, role)
    if person and person.lower() not in subject.lower():
        subject = f"{person}: {action or subject}"
    if not anchor:
        anchor = subject
    frame = _ROLE_FRAME[role]
    frame = frame[:1].upper() + frame[1:]
    camera = _CAMERAS[role][index % len(_CAMERAS[role])]
    setting = _setting(domain, role, spoken)
    mood = _MOOD[role]
    must = f"{anchor}. {frame}"
    about = _about_clause(topic, spoken, subject)
    if about:
        must = f"{must}. {about}"
    must_not = _must_not(domain, spoken)
    prompt = (
        f"{camera}, showing {subject}. "
        f"Setting: {setting}. "
        f"Mood: {mood}. "
        f"Narrative role: {role}. "
        f"{MUST_DEPICT} {must}. "
        f"{MUST_NOT_DEPICT} {must_not}. "
        f"{CINEMATIC_LOOK}"
    )
    prompt = _scrub_headlines(prompt, topic, script_title)
    if _same(prompt, topic) or (topic and topic.strip().lower() in prompt.lower() and len(topic.strip()) >= 12):
        raise CinemaPromptError(
            "Story lock would have pasted the headline into the shot prompt. Refusing to render."
        )
    return prompt


def _missing_beats_message() -> str:
    return (
        "Cinema has no script beats or voiceover to lock shots to. "
        "Refusing to render a headline-only prompt."
    )


def _same(a: str, b: str) -> bool:
    left = _norm(a)
    right = _norm(b)
    return bool(left) and left == right


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _excise(text: str, *blocks: str) -> str:
    out = " ".join((text or "").split())
    for raw in blocks:
        block = (raw or "").strip()
        if len(block) < 12:
            continue
        out = re.sub(re.escape(block), " ", out, flags=re.IGNORECASE)
    out = re.sub(r"\s{2,}", " ", out).strip(" ,;.-:")
    out = re.sub(r"\b(with|about|over|on)\s*$", "", out, flags=re.IGNORECASE).strip(" ,;.-:")
    return out


def _is_vague(text: str) -> bool:
    spoken = (text or "").strip()
    if len(spoken.split()) < 4:
        return True
    return _VAGUE_RE.search(spoken) is not None and len(spoken.split()) < 18


def _split_parts(text: str) -> list[str]:
    sentences = [s.strip(" ,;") for s in re.split(r"(?<=[.!?])\s+", text) if s.strip(" ,;")]
    if len(sentences) >= 2:
        return sentences[:8]
    one = sentences[0] if sentences else text
    chunks = [
        c.strip(" ,;")
        for c in re.split(r"\s+[—–;]\s+|\s+\band\b\s+", one)
        if len(c.split()) >= 3
    ]
    return chunks[:8] or ([one] if one else [])


def _spread_roles(count: int) -> list[str]:
    if count <= 1:
        return ["setup"]
    indexes = [round(i * (len(_ROLES) - 1) / (count - 1)) for i in range(count)]
    return [_ROLES[i] for i in indexes]


def _looks_like_political_row(text: str) -> bool:
    if not re.search(
        r"\b(deal|row|backlash|vote|bill|law|policy|nhs|quits|sacked|resigns?|defends)\b",
        text,
        re.IGNORECASE,
    ):
        return False
    return _lead_person(text) != ""


def _names(text: str) -> list[str]:
    pattern = re.compile(r"\b[A-Z][a-z]+(?:\s+(?:[A-Z][a-z]+|of|the|and|de|van))*\b")
    found: list[str] = []
    for match in pattern.finditer(text or ""):
        parts = match.group(0).split()
        while parts and parts[-1].lower() in {"of", "the", "and", "de", "van"}:
            parts.pop()
        while parts and parts[0].lower() in {"of", "the", "and"} | _NAME_SKIP:
            parts.pop(0)
        if not parts:
            continue
        if all(part.lower() in _NAME_SKIP for part in parts):
            continue
        name = " ".join(parts)
        if name.lower() in _NAME_SKIP or name in found:
            continue
        found.append(name)
    return found


def _is_geo_name(name: str) -> bool:
    tokens = [part.lower() for part in name.split() if part.lower() not in {"of", "the", "and"}]
    return bool(tokens) and any(token in _GEO_WORDS for token in tokens)


def _lead_person(text: str) -> str:
    for name in _story_names(text):
        return name
    return ""


def _story_names(text: str) -> list[str]:
    """People and story-specific names, without postcard place phrases."""
    found: list[str] = []
    for name in _names(text):
        if _is_geo_name(name):
            leftovers = [
                part
                for part in name.split()
                if part.lower() not in _GEO_WORDS and part.lower() not in {"of", "the", "and"}
            ]
            name = " ".join(leftovers)
        if not name or name.lower() in _NAME_SKIP or _is_geo_name(name):
            continue
        if name not in found:
            found.append(name)
    return found


def _about_clause(topic: str, spoken: str, subject: str) -> str:
    blob = f"{spoken} {subject}".lower()
    missing = [name for name in _story_names(topic) if name.lower() not in blob]
    if not missing:
        return ""
    return "About " + ", ".join(missing[:3])


def _action_image(spoken: str, role: str, domain: str) -> str:
    if _CTA_RE.search(spoken) and len(_content_tokens(spoken)) < 4:
        return _role_subject(domain, role)
    for pattern, image in _ACTION_PATTERNS:
        if pattern.search(spoken):
            person = _lead_person(spoken) or (
                "the minister" if domain in {"politics", "news"} else "the subject"
            )
            return image.format(person=person)
    if _is_vague(spoken):
        return ""
    return _literal_scene(spoken)


def _literal_scene(spoken: str) -> str:
    words = [word for word in re.findall(r"[A-Za-z']+", spoken) if word.lower() not in _GEO_WORDS]
    clause = " ".join(words).strip()
    if len(clause.split()) < 4:
        return ""
    return clause[:180]


def _role_subject(domain: str, role: str) -> str:
    table = {
        "politics": _POLITICS_SUBJECT,
        "news": _NEWS_SUBJECT,
        "gaming": _GAMING_SUBJECT,
    }.get(domain, _GENERAL_SUBJECT)
    return table.get(role, table["setup"])


def _role_frame_anchor(role: str) -> str:
    return _ROLE_FRAME.get(role, _ROLE_FRAME["setup"])


def _content_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for word in re.findall(r"[A-Za-z']+", text or ""):
        low = word.lower()
        if low in _STOP or low in _GEO_WORDS or low in seen:
            continue
        if _CTA_RE.search(word):
            continue
        seen.add(low)
        tokens.append(word)
    return tokens


def _vo_anchor(spoken: str, topic: str) -> str:
    if _is_vague(spoken):
        return ""
    if _CTA_RE.search(spoken) and len(_content_tokens(spoken)) < 4:
        return ""
    clause = _degeo(_excise(spoken, topic)).strip(" ,;.")
    if len(clause.split()) < 3:
        return ""
    return clause[:180]


def _degeo(text: str) -> str:
    """Keep the political or story fact without handing Wan a postcard noun."""
    out = re.sub(
        r"\b(?:islands?|atolls?|coastlines?|coasts?|beaches?|reefs?|bays?|lagoons?|shores?)\b",
        "territory",
        text or "",
        flags=re.IGNORECASE,
    )
    out = re.sub(r"\b(?:oceans?|seas?|scuba)\b", "water", out, flags=re.IGNORECASE)
    out = re.sub(r"\b(territory)(?:\s+\1\b)+", r"\1", out, flags=re.IGNORECASE)
    out = re.sub(r"\s{2,}", " ", out)
    return out.strip()


def _setting(domain: str, role: str, spoken: str) -> str:
    low = spoken.lower()
    if domain == "gaming":
        return {
            "setup": "inside the game world at the entrance to this encounter, in-world light, no HUD",
            "conflict": "the arena of this fight, dust and practical light, no interface",
            "evidence": "a close pocket of the game world where the mechanic is visible, no menus",
            "turn": "the same in-world space the moment the encounter turns",
            "payoff": "the in-world aftermath, quiet, no results screen",
        }[role]
    if domain == "politics":
        if re.search(r"\b(nhs|hospital|ward|nurse|doctor)\b", low):
            place = "an NHS corridor and a ministerial briefing room, fluorescent practicals"
        elif re.search(r"\b(white house|capitol|senate|congress)\b", low):
            place = "a Washington hearing room and the corridor outside, cool practical light"
        elif re.search(r"\b(court|trial|judge|tribunal)\b", low):
            place = "a courtroom well, wood, papers, and a quiet gallery"
        elif re.search(r"\b(protest|rally|march|picket)\b", low):
            place = "the real street of the protest, banners turned away from camera"
        elif role in {"setup", "payoff"} and re.search(
            r"removed the people|displaced|onto the ship|suitcases", low
        ):
            place = "a dim government office with a paper map, then an overcast working dock"
        else:
            place = {
                "setup": "a lived-in ministerial office, practical lamp, paper map, closed file",
                "conflict": "the chamber edge and the press pen just outside the doors",
                "evidence": "a desk of signed pages under a cool overhead practical",
                "turn": "a doorway between the chamber and a private office",
                "payoff": "the emptied briefing room, one chair pushed back",
            }[role]
        return f"{place}, no glamour and no resort"
    if domain == "news":
        return {
            "setup": "the real location where this report starts, press practicals, people in frame",
            "conflict": "one real location holding both sides of this report, no montage",
            "evidence": "a table-level view of the proof this report cites",
            "turn": "that same place at the moment the report says everything changed",
            "payoff": "the people left in that place after the report moves on",
        }[role]
    return {
        "setup": "the real room or street this beat takes place in, lived-in detail, practical light",
        "conflict": "one location holding both sides of the disagreement, no montage",
        "evidence": "a table-level view of the object this beat is about",
        "turn": "the same place at the moment the situation changes",
        "payoff": "that place after the decision, quieter and still specific",
    }[role]


def _must_not(domain: str, spoken: str) -> str:
    low = spoken.lower()

    def mentioned(pattern: str) -> bool:
        return re.search(pattern, low) is not None

    bans: list[str] = []
    if not mentioned(r"\b(scuba|diver|diving|snorkel|reefs?)\b"):
        bans.append("scuba divers")
    if not mentioned(r"\b(beach(?:es)?|coast(?:line)?s?|holiday|resort|atolls?)\b"):
        bans.append("postcard atolls and holiday beaches")
    if not mentioned(r"\b(phones?|tiktok|scrolling)\b"):
        bans.append("crowds filming on phones")
    if not mentioned(r"\bskylines?\b"):
        bans.append("generic city skylines")
    bans.append("empty scenery with nobody and no decision in frame")
    if domain in {"politics", "news"}:
        bans.append("a vacation reading of a political or news story")
        if not mentioned(r"\b(gameplay|boss|hud)\b"):
            bans.append("unrelated video-game footage")
    if domain == "gaming":
        bans.append("a parliamentary chamber")
        bans.append("a news desk")
        bans.append("menus, HUD, and results screens")
    return ", ".join(bans)


def _scrub_headlines(prompt: str, topic: str, script_title: str) -> str:
    out = prompt
    for raw in (topic, script_title):
        block = (raw or "").strip()
        if len(block) < 12:
            continue
        out = re.sub(re.escape(block), " ", out, flags=re.IGNORECASE)
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\s+([,.;:])", r"\1", out)
    return out.strip()
