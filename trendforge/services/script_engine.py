from __future__ import annotations

import json
import re
from typing import Any

from trendforge.domain.enums import BrandVoice, ContentFormat, LengthPreset, MediaType, ShotSegmentKind, VideoStyle
from trendforge.domain.models import EpisodeBrief, GenerationRequest, SeasonPlan, Shot, TrailerAttribution, VideoScript, YouTubePack
from trendforge.logging_setup import get_logger
from trendforge.services.ollama_client import OllamaClient
from trendforge.services.visual_policy import sanitize_visual_prompt

log = get_logger("script")

LENGTH_SECONDS = {
    LengthPreset.SHORTS: (22, 55),
    LengthPreset.MID: (180, 420),
    LengthPreset.LONG: (600, 1080),
    LengthPreset.DOCUSERIES: (1080, 2400),
}

SHOT_COUNTS = {
    LengthPreset.SHORTS: (5, 8),
    LengthPreset.MID: (10, 16),
    LengthPreset.LONG: (16, 24),
    LengthPreset.DOCUSERIES: (20, 32),
}

STYLE_LINE = {
    VideoStyle.EXPLAINER: "photographed b-roll of the subject, clear coverage, natural light",
    VideoStyle.BREAKDOWN: "scene-by-scene cinematic coverage, freeze-frame energy, key-moment inserts",
    VideoStyle.CINEMATIC: "dramatic lighting, slow pushes, filmic b-roll",
    VideoStyle.DOCUMENTARY: "observational documentary footage, archival texture, measured pacing",
    VideoStyle.REACTION: "cinematic coverage of real reactions in the world, punchy cuts",
    VideoStyle.EDUCATIONAL: "process close-ups and demonstration footage, calm authority, no diagrams",
    VideoStyle.RANKING: "cinematic montage of each item in the world, bold lighting, no countdown graphics",
    VideoStyle.NEWS_RECAP: "newsroom-adjacent documentary montage, streets, crowds, calm urgency",
    VideoStyle.STORY: "narrative wide shots, character close-ups, no chapter cards",
    VideoStyle.REVIEW: "review commentary cards, brief official trailer inserts, no invented opinions",
}

SYSTEM = """You are a YouTube channel producer. Return ONLY valid JSON with keys:
title, hook, summary, youtube_description, tags (array of strings),
chapters (array of {time, title}), style_notes,
titles (array of 5 clickable YouTube titles),
thumbnail_text (3-6 words),
pinned_comment, community_post, end_screen,
shots (array of {title, narration, visual_prompt, duration_sec, source_start_sec, source_end_sec}).
Narration is VOICEOVER only — speakable, addictive, open loops, specifics, no filler.
visual_prompt must describe PHOTOGRAPHED footage of the topic: camera, light, location, action.
Never title cards, kinetic typography, diagrams, end cards, infographics, captions,
or a presenter reading the script. Do not copy narration into visual_prompt.
When a timed source transcript is provided, each shot MUST include source_start_sec and source_end_sec
(seconds into the source video) that match the moment being narrated. Keep windows 3–45s.
No markdown."""

SOURCE_CLIP_SYSTEM = """You are a movie/show recap producer like a story-time YouTube channel.
Return ONLY valid JSON (same keys as a standard script).
Narration retells the source story in your own words — scene by scene, present tense, gripping.
Each shot uses REAL footage from the source: set source_start_sec and source_end_sec to the exact
segment you are narrating. Match the timed transcript. Do not invent timestamps.
visual_prompt is optional B-roll notes; footage comes from the source clip, not AI generation.
No markdown."""

SEASON_SYSTEM = """You are a docuseries showrunner. Return ONLY JSON:
series_title, logline, bible,
episodes: array of {index, title, hook, thesis, summary}.
Each episode must stand alone AND make the next one feel mandatory.
No markdown."""


def target_profile(length: LengthPreset, style: VideoStyle) -> dict[str, Any]:
    lo, hi = LENGTH_SECONDS.get(length, LENGTH_SECONDS[LengthPreset.MID])
    nlo, nhi = SHOT_COUNTS.get(length, SHOT_COUNTS[LengthPreset.MID])
    return {"min_sec": lo, "max_sec": hi, "min_shots": nlo, "max_shots": nhi, "style": style.value}


def _extract_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None


def _pack_from_payload(data: dict[str, Any], topic: str, cta: str) -> YouTubePack:
    titles = [str(t) for t in (data.get("titles") or []) if str(t).strip()]
    if not titles:
        titles = default_titles(topic)
    return YouTubePack(
        titles=titles[:8],
        thumbnail_text=str(data.get("thumbnail_text") or topic.split()[:4] and " ".join(topic.split()[:4]).upper()),
        pinned_comment=str(data.get("pinned_comment") or f"Which part surprised you? Comment 1, 2, or 3. {cta}"),
        community_post=str(data.get("community_post") or f"New video on {topic} is up. The part at the midpoint will reframe the whole story."),
        end_screen=str(data.get("end_screen") or cta),
        hashtags=[str(t).lstrip("#") for t in (data.get("tags") or [])][:15],
    )


def default_titles(topic: str) -> list[str]:
    return [
        f"{topic}: What actually happened",
        f"The {topic} story nobody is explaining",
        f"Why {topic} is everywhere right now",
        f"{topic} explained — without the noise",
        f"If you only watch one {topic} video, watch this",
    ]


def script_from_payload(data: dict[str, Any], topic: str = "", cta: str = "") -> VideoScript:
    shots: list[Shot] = []
    for i, raw in enumerate(data.get("shots") or []):
        title = str(raw.get("title") or f"Shot {i + 1}")
        narration = str(raw.get("narration") or "")
        visual = sanitize_visual_prompt(
            str(raw.get("visual_prompt") or raw.get("prompt") or ""),
            topic=topic,
            title=title,
            narration=narration,
        )
        kind_raw = str(raw.get("segment_kind") or raw.get("kind") or ShotSegmentKind.COMMENTARY.value)
        try:
            segment_kind = ShotSegmentKind(kind_raw)
        except ValueError:
            segment_kind = ShotSegmentKind.COMMENTARY
        shots.append(
            Shot(
                index=i,
                title=title,
                narration=narration,
                visual_prompt=visual,
                duration_sec=float(raw.get("duration_sec") or 5.0),
                source_start_sec=float(raw.get("source_start_sec") or 0.0),
                source_end_sec=float(raw.get("source_end_sec") or 0.0),
                segment_kind=segment_kind,
            )
        )
    chapters = []
    for ch in data.get("chapters") or []:
        if isinstance(ch, dict):
            chapters.append((str(ch.get("time", "0:00")), str(ch.get("title", ""))))
    tags = [str(t) for t in (data.get("tags") or [])][:20]
    return VideoScript(
        title=str(data.get("title") or "Untitled Breakdown"),
        hook=str(data.get("hook") or ""),
        summary=str(data.get("summary") or ""),
        youtube_description=str(data.get("youtube_description") or ""),
        tags=tags,
        chapters=chapters,
        shots=shots,
        style_notes=str(data.get("style_notes") or ""),
        youtube=_pack_from_payload(data, topic, cta),
    )


def _brand_line(brand: BrandVoice) -> str:
    return {
        BrandVoice.DOCUMENTARY: "calm, precise, a little grave, like a late-night docuseries narrator",
        BrandVoice.WITTY: "sharp, lightly sarcastic, never cruel, always specific",
        BrandVoice.NEWS: "anchorman clarity, short sentences, timestamps, no hype words",
        BrandVoice.CALM_TEACHER: "patient, structured, defines terms the first time they appear",
        BrandVoice.BOLD: "high energy, pattern interrupts, direct address to camera",
    }[brand]


def template_script(
    topic: str,
    style: VideoStyle,
    length: LengthPreset,
    extra_context: str = "",
    content_format: ContentFormat = ContentFormat.VIDEO,
    brand: BrandVoice = BrandVoice.DOCUMENTARY,
    channel_name: str = "",
    cta: str = "Subscribe for the next episode.",
    episode_index: int = 1,
    episode_count: int = 1,
    series_title: str = "",
) -> VideoScript:
    if content_format is ContentFormat.SHORTS or length is LengthPreset.SHORTS:
        return _template_shorts(topic, style, extra_context, brand, cta, channel_name)
    if content_format in {ContentFormat.DOCUSERIES, ContentFormat.SEASON} or length is LengthPreset.DOCUSERIES:
        return _template_docuseries(
            topic, extra_context, brand, cta, channel_name, episode_index, episode_count, series_title
        )
    return _template_standard(topic, style, length, extra_context, brand, cta, channel_name)


def _template_standard(
    topic: str,
    style: VideoStyle,
    length: LengthPreset,
    extra_context: str,
    brand: BrandVoice,
    cta: str,
    channel_name: str,
) -> VideoScript:
    profile = target_profile(length, style)
    n = profile["min_shots"]
    avg = (profile["min_sec"] + profile["max_sec"]) / 2
    each = max(3.5, round(avg / (n + 2), 1))
    style_line = STYLE_LINE.get(style, STYLE_LINE[VideoStyle.EXPLAINER])
    voice = _brand_line(brand)
    context_bit = f" Extra context: {extra_context[:1200]}" if extra_context else ""
    host = channel_name or "this channel"
    beats = [
        ("Hook", f"Stop scrolling. {topic} is not the story you were told — and the real version is stranger.", f"handheld crash zoom into the real-world subject of {topic}, crowded location, natural light"),
        ("What happened", f"Here is the short, honest version of what actually happened with {topic}.", f"documentary coverage of {topic}: crowds, cameras, streets, cinematic b-roll"),
        ("Why it matters", f"This is not a blip. {topic} is a tell for where attention, money, and power are moving.", "wide dusk city skyline, slow aerial push, thoughtful lighting"),
        ("Key moment 1", f"The first turning point is the moment people could not look away.", "macro close-up of a key object, dramatic rim light, slow orbit"),
        ("Key moment 2", f"Then the conversation exploded. Clips, takes, and counter-takes stacked on each other.", "rapid montage of real people reacting in public, phones, crowds"),
        ("The hidden layer", f"What most recaps skip: incentives. Who benefits if you stay mad about {topic}?", "quiet office at night, papers on a desk, practical lamp"),
        ("The takeaway", f"If you remember one thing, remember this: context beats outrage.", "lone figure walking away from camera at golden hour, shallow depth of field"),
        ("What to watch next", f"The story is still moving. {host} will be here when the next chapter drops.", "forward-looking aerial over a city at sunrise"),
        ("Outro", cta, "empty cinematic location after the event, lingering wide shot"),
    ]
    shots = [
        Shot(
            i,
            title,
            narration,
            sanitize_visual_prompt(f"{visual}, {style_line}", topic=topic, title=title, narration=narration),
            each,
        )
        for i, (title, narration, visual) in enumerate(beats[:n])
    ]
    tags = [w.strip("#,. ") for w in re.split(r"\W+", topic) if len(w) > 2][:8]
    tags += ["explained", "breakdown", "youtube", "documentary"]
    script = VideoScript(
        title=f"{topic}: Explained",
        hook=beats[0][1],
        summary=f"A {style.value} breakdown of {topic}.",
        youtube_description=f"{topic} explained.\n\n{beats[1][1]}\n\n{cta}\n{context_bit}",
        tags=tags,
        chapters=[("0:00", "Hook"), ("0:08", "What happened"), ("0:20", "Why it matters")],
        shots=shots,
        style_notes=f"{style_line}; {voice}{context_bit}",
        youtube=YouTubePack(
            titles=default_titles(topic),
            thumbnail_text=topic[:28].upper(),
            pinned_comment=f"What should we cover next? {cta}",
            community_post=f"New {host} video: {topic}.",
            end_screen=cta,
            hashtags=tags,
        ),
    )
    return script


def _template_shorts(
    topic: str,
    style: VideoStyle,
    extra_context: str,
    brand: BrandVoice,
    cta: str,
    channel_name: str,
) -> VideoScript:
    voice = _brand_line(brand)
    style_line = STYLE_LINE.get(style, STYLE_LINE[VideoStyle.BREAKDOWN])
    beats = [
        ("Pattern interrupt", f"Everyone is talking about {topic}. Almost nobody understands it.", "extreme close-up of eyes then smash zoom onto the subject, high contrast"),
        ("The lie", f"The viral version skips the part that actually matters.", "freeze-frame of a crowded street, then whip pan to the real scene"),
        ("The truth", f"Here is the 20-second version of what is really going on with {topic}.", f"one strong cinematic image of {topic}, punchy cut"),
        ("The twist", f"And this is why it will still be trending tomorrow.", "cut between then and now in the same real location, rising energy"),
        ("CTA", f"Follow {channel_name or 'us'} for the full breakdown. {cta}", "subject walks toward camera then past it, lingering empty frame"),
    ]
    shots = [
        Shot(
            i,
            t,
            n,
            sanitize_visual_prompt(
                f"{v}, vertical 9:16, {style_line}, {topic}",
                topic=topic,
                title=t,
                narration=n,
            ),
            7.0,
        )
        for i, (t, n, v) in enumerate(beats)
    ]
    tags = [w for w in re.split(r"\W+", topic) if len(w) > 2][:6] + ["shorts", "fyp", "explained"]
    return VideoScript(
        title=f"{topic} in 40 seconds",
        hook=beats[0][1],
        summary=f"A Short on {topic}.",
        youtube_description=f"{topic} — the part the timeline skipped.\n\n{cta}\n#shorts",
        tags=tags,
        chapters=[("0:00", "Hook")],
        shots=shots,
        style_notes=f"shorts; {voice}",
        youtube=YouTubePack(
            titles=[
                f"{topic} in 40 seconds",
                f"The {topic} detail everyone missed",
                f"Wait for the last line — {topic}",
            ],
            thumbnail_text="WAIT FOR IT",
            pinned_comment="Want the long version? Comment LONG.",
            community_post=f"Shorts drop on {topic}. Full episode next.",
            end_screen=cta,
            hashtags=tags,
        ),
    )


def _template_docuseries(
    topic: str,
    extra_context: str,
    brand: BrandVoice,
    cta: str,
    channel_name: str,
    episode_index: int,
    episode_count: int,
    series_title: str,
) -> VideoScript:
    voice = _brand_line(brand)
    series = series_title or f"{topic}: The Full Story"
    ep = max(1, episode_index)
    total = max(ep, episode_count)
    acts = [
        ("Cold open", f"Episode {ep}. Before the headlines, there was a quieter fact about {topic} that made everything after it inevitable."),
        ("Previously", f"If you are new: {topic} did not appear overnight. Pressure built, then it broke into public view."),
        ("The question", f"Tonight we ask a simple question, and we will not leave until it has an answer."),
        ("The official story", f"This is the version most people were handed. It is not fake. It is incomplete."),
        ("The first crack", f"The official story starts to slip the moment you look at who had something to gain."),
        ("The people", f"Zoom in on the people inside {topic} — not as memes, as humans under pressure."),
        ("The machine", f"Around them: platforms, money, and an audience that rewards the loudest frame."),
        ("The counter-story", f"There is a competing narrative. Some of it is good faith. Some of it is strategy."),
        ("The evidence", f"Here is what we can actually verify — dates, documents, and outcomes, not vibes."),
        ("The cost", f"Real people absorbed the cost while the timeline moved on."),
        ("The pattern", f"{topic} rhymes with older stories. Once you see the pattern, you cannot unsee it."),
        ("The fork", f"From here the story can go two ways. One is comforting. One is true."),
        ("What it means", f"This is bigger than a news cycle. It is a test of how we decide what is real."),
        ("What to watch", f"Between now and the next episode, watch who changes their story, and who goes quiet."),
        ("Next episode", f"Next time on {series}: we follow the money and the silence around {topic}."),
        ("Outro", f"I'm {channel_name or 'your host'}. {cta} Episode {ep} of {total}."),
    ]
    each = 48.0
    shots = []
    for i, (title, narration) in enumerate(acts):
        shots.append(
            Shot(
                i,
                title,
                narration,
                sanitize_visual_prompt(
                    f"cinematic documentary footage of {topic}, {title.lower()}, archival texture, observational camera",
                    topic=topic,
                    title=title,
                    narration=narration,
                ),
                each,
            )
        )
    chapters = [
        ("0:00", "Cold open"),
        ("2:00", "The official story"),
        ("8:00", "The crack"),
        ("14:00", "The evidence"),
        ("20:00", "What it means"),
        ("24:00", "Next episode"),
    ]
    tags = [w for w in re.split(r"\W+", topic) if len(w) > 2][:8] + ["docuseries", "documentary", "explained", "fullstory"]
    return VideoScript(
        title=f"{series} — Episode {ep}: {topic}",
        hook=acts[0][1],
        summary=f"Episode {ep} of {series}, a narrated investigation of {topic}.",
        youtube_description=(
            f"{series}  |  Episode {ep} of {total}\n\n{acts[2][1]}\n\n"
            f"{extra_context[:1500]}\n\n{cta}\n"
        ),
        tags=tags,
        chapters=chapters,
        shots=shots,
        style_notes=f"docuseries episode {ep}/{total}; {voice}",
        youtube=YouTubePack(
            titles=[
                f"{series} Ep {ep}: {topic}",
                f"{topic} — the episode that connects the dots",
                f"Docuseries: {topic} (Episode {ep})",
            ],
            thumbnail_text=f"EP {ep}",
            pinned_comment=f"Watch episode {max(1, ep - 1)} first if you are new. {cta}",
            community_post=f"Episode {ep} of {series} is live. Next one is already in the cut.",
            end_screen=f"Next episode →  |  {cta}",
            hashtags=tags,
        ),
        episode_index=ep,
    )


def plan_season(
    topic: str,
    episode_count: int = 5,
    ollama: OllamaClient | None = None,
    ollama_model: str = "",
    brand: BrandVoice = BrandVoice.DOCUMENTARY,
    channel_name: str = "",
) -> SeasonPlan:
    fallback = _fallback_season(topic, episode_count, channel_name)
    if ollama is None:
        return fallback
    model = ollama.pick_model(ollama_model)
    if not model:
        return fallback
    prompt = f"""Design a {episode_count}-episode YouTube docuseries about: {topic}
Channel: {channel_name or 'independent'}
Voice: {_brand_line(brand)}
Each episode 18-35 minutes, stand-alone, with a cliffhanger.
"""
    try:
        raw = ollama.generate_json(model, prompt, SEASON_SYSTEM)
        data = _extract_json(raw)
        if not data or not data.get("episodes"):
            return fallback
        eps = [
            EpisodeBrief(
                index=int(e.get("index") or i + 1),
                title=str(e.get("title") or f"Episode {i + 1}"),
                hook=str(e.get("hook") or ""),
                thesis=str(e.get("thesis") or ""),
                summary=str(e.get("summary") or ""),
            )
            for i, e in enumerate(data.get("episodes") or [])
        ]
        return SeasonPlan(
            series_title=str(data.get("series_title") or fallback.series_title),
            logline=str(data.get("logline") or ""),
            episodes=eps or fallback.episodes,
            bible=str(data.get("bible") or ""),
        )
    except Exception as exc:
        log.warning("Season plan failed: %s", exc)
        return fallback


def _fallback_season(topic: str, n: int, channel_name: str) -> SeasonPlan:
    n = max(3, min(n, 8))
    templates = [
        ("The spark", "How it started — the moment that made {t} inevitable."),
        ("The machine", "Who amplified {t}, and why the incentives lined up."),
        ("The people", "The human cost and the faces inside {t}."),
        ("The counter-attack", "The competing story, and what it was designed to protect."),
        ("The money", "Follow the money around {t}."),
        ("The aftermath", "What is left when the timeline moves on."),
        ("The pattern", "Where {t} fits in a longer historical rhyme."),
        ("The choice", "What happens next — and who decides."),
    ]
    episodes = [
        EpisodeBrief(i + 1, title, hook.format(t=topic), f"Episode {i + 1} thesis on {topic}.", hook.format(t=topic))
        for i, (title, hook) in enumerate(templates[:n])
    ]
    return SeasonPlan(
        series_title=f"{topic}: The Full Story",
        logline=f"A {n}-part narrated investigation of {topic} from {channel_name or 'TrendForge Studio'}.",
        episodes=episodes,
        bible=f"Stay specific. Name incentives. End every episode on a question the next one answers.",
    )


def assign_source_timestamps(
    script: VideoScript,
    *,
    duration_sec: float,
    cues: list | None = None,
) -> VideoScript:
    """Fill missing source_start_sec/source_end_sec on shots."""
    if duration_sec <= 0 or not script.shots:
        return script
    shots = script.shots
    if all(s.source_end_sec > s.source_start_sec for s in shots):
        return script

    from trendforge.services.ytdlp_tools import VttCue

    typed_cues: list[VttCue] = []
    if cues:
        for cue in cues:
            if isinstance(cue, VttCue):
                typed_cues.append(cue)
            elif isinstance(cue, (list, tuple)) and len(cue) >= 3:
                typed_cues.append(VttCue(float(cue[0]), float(cue[1]), str(cue[2])))

    if typed_cues:
        chunk = max(1, len(typed_cues) // max(len(shots), 1))
        for i, shot in enumerate(shots):
            if shot.source_end_sec > shot.source_start_sec:
                continue
            start_idx = min(i * chunk, len(typed_cues) - 1)
            end_idx = min(start_idx + chunk, len(typed_cues)) - 1
            end_idx = max(end_idx, start_idx)
            shot.source_start_sec = typed_cues[start_idx].start
            shot.source_end_sec = typed_cues[end_idx].end
            shot.duration_sec = max(3.0, shot.source_end_sec - shot.source_start_sec)
        if all(s.source_end_sec > s.source_start_sec for s in shots):
            return script

    weights = [max(1, len(s.narration.split())) for s in shots]
    total_weight = sum(weights)
    cursor = 0.0
    usable = max(duration_sec - 1.0, 10.0)
    for shot, weight in zip(shots, weights):
        if shot.source_end_sec > shot.source_start_sec:
            cursor = max(cursor, shot.source_end_sec)
            continue
        span = usable * (weight / total_weight)
        span = max(3.0, min(span, 45.0))
        if cursor + span > duration_sec:
            span = max(3.0, duration_sec - cursor)
        shot.source_start_sec = round(cursor, 2)
        shot.source_end_sec = round(min(duration_sec, cursor + span), 2)
        shot.duration_sec = round(shot.source_end_sec - shot.source_start_sec, 2)
        cursor = shot.source_end_sec
    return script


def generate_script(
    topic: str,
    style: VideoStyle,
    length: LengthPreset,
    extra_context: str = "",
    ollama: OllamaClient | None = None,
    ollama_model: str = "",
    content_format: ContentFormat = ContentFormat.VIDEO,
    brand: BrandVoice = BrandVoice.DOCUMENTARY,
    channel_name: str = "",
    cta: str = "Subscribe for the next episode.",
    episode_index: int = 1,
    episode_count: int = 1,
    series_title: str = "",
    source_clip_mode: bool = False,
) -> VideoScript:
    if content_format is ContentFormat.SEASON:
        season = plan_season(topic, max(4, episode_count), ollama, ollama_model, brand, channel_name)
        return VideoScript(
            title=season.series_title,
            hook=season.logline,
            summary=season.logline,
            youtube_description=season.bible + "\n\n" + "\n".join(
                f"Ep {e.index}: {e.title} — {e.hook}" for e in season.episodes
            ),
            tags=[w for w in re.split(r"\W+", topic) if len(w) > 2][:8] + ["docuseries"],
            shots=[],
            style_notes="season bible — generate each episode separately",
            youtube=YouTubePack(
                titles=[f"{season.series_title} | Trailer", f"{topic}: the full series"],
                thumbnail_text="SEASON 1",
                pinned_comment="Which episode should we drop first?",
                community_post=f"{season.series_title} is mapped. Episode 1 is next.",
                end_screen=cta,
                hashtags=["docuseries", "youtube"],
            ),
            season=season,
        )
    fallback = template_script(
        topic,
        style,
        length,
        extra_context,
        content_format,
        brand,
        channel_name,
        cta,
        episode_index,
        episode_count,
        series_title,
    )
    if ollama is None:
        return fallback
    model = ollama.pick_model(ollama_model)
    if not model:
        return fallback
    profile = target_profile(length, style)
    prompt = f"""Create a YouTube {content_format.value} / {style.value} plan.
Topic: {topic}
Channel: {channel_name or 'independent'}
Voice: {_brand_line(brand)}
Target length: {profile['min_sec']}-{profile['max_sec']} seconds
Shot count: {profile['min_shots']}-{profile['max_shots']}
Episode {episode_index} of {episode_count}. Series: {series_title or 'n/a'}
CTA: {cta}
{extra_context[:4000]}
Make narration add up roughly to the target length. Open with a hook that stops a scroll.
{"Each shot must include source_start_sec and source_end_sec from the timed transcript." if source_clip_mode else "Visual prompts are cinematic B-roll of the subject. Do not describe text on screen."}
"""
    system = SOURCE_CLIP_SYSTEM if source_clip_mode else SYSTEM
    try:
        raw = ollama.generate_json(model, prompt, system)
        data = _extract_json(raw)
        if not data or not data.get("shots"):
            log.warning("Ollama returned unusable JSON; using template script")
            return fallback
        script = script_from_payload(data, topic, cta)
        if not script.shots:
            return fallback
        script.episode_index = episode_index
        return script
    except Exception as exc:
        log.warning("Ollama script failed: %s", exc)
        return fallback


REVIEW_SYSTEM = """You are a YouTube review editor. Return ONLY valid JSON with keys:
title, hook, summary, youtube_description, tags, chapters, style_notes,
titles, thumbnail_text, pinned_comment, community_post, end_screen,
shots (array of {title, narration, visual_prompt, duration_sec, segment_kind,
source_start_sec, source_end_sec}).

CRITICAL RULES:
- segment_kind is one of: commentary, trailer, gameplay, title_card, credits
- At least 70% of total duration must be segment_kind=commentary using ONLY the user's supplied opinion text
- trailer clips are 3-6 seconds each, used sparingly to illustrate a specific point being narrated
- NEVER invent opinions, scores, praise, or criticism not present in the user notes
- You may polish grammar and pacing but every claim must trace to user input
- For games, prefer segment_kind=gameplay when discussing mechanics the user mentioned
- Include a title_card shot and a credits shot at the end
No markdown."""


def _review_user_context(req: GenerationRequest) -> str:
    scale = req.user_rating_scale or "10"
    return (
        f"Subject: {req.review_subject}\n"
        f"Media type: {req.media_type.value}\n"
        f"User rating: {req.user_rating}/{scale}\n"
        f"Overall opinion:\n{req.user_opinion}\n\n"
        f"What they liked:\n{req.user_liked}\n\n"
        f"What they disliked:\n{req.user_disliked}\n\n"
        f"Key moments to reference:\n{req.user_moments}\n\n"
        f"Verdict:\n{req.user_verdict}\n"
    )


def _split_commentary_sections(req: GenerationRequest) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    if req.user_opinion.strip():
        sections.append(("My take", req.user_opinion.strip()))
    if req.user_liked.strip():
        sections.append(("What worked", req.user_liked.strip()))
    if req.user_disliked.strip():
        sections.append(("What didn't", req.user_disliked.strip()))
    if req.user_moments.strip():
        sections.append(("Standout moments", req.user_moments.strip()))
    if req.user_verdict.strip():
        sections.append(("Verdict", req.user_verdict.strip()))
    return sections


def enforce_trailer_budget(script: VideoScript, max_fraction: float = 0.25, max_clip_sec: float = 6.0) -> VideoScript:
    total = sum(s.duration_sec for s in script.shots) or 1.0
    for shot in script.shots:
        if shot.segment_kind is ShotSegmentKind.TRAILER:
            shot.duration_sec = min(shot.duration_sec, max_clip_sec)
            span = shot.source_end_sec - shot.source_start_sec
            if span > max_clip_sec:
                shot.source_end_sec = shot.source_start_sec + max_clip_sec
    total = sum(s.duration_sec for s in script.shots) or 1.0
    trailer_total = sum(s.duration_sec for s in script.shots if s.segment_kind is ShotSegmentKind.TRAILER)
    if trailer_total / total <= max_fraction:
        return script
    commentary = [s for s in script.shots if s.segment_kind is ShotSegmentKind.COMMENTARY]
    if commentary:
        boost = (trailer_total / max_fraction - total) / len(commentary)
        for shot in commentary:
            shot.duration_sec = max(shot.duration_sec + boost, 8.0)
    return script


def template_review_script(
    req: GenerationRequest,
    attribution: TrailerAttribution | None = None,
    channel_name: str = "",
    cta: str = "Subscribe for more honest reviews.",
) -> VideoScript:
    subject = req.review_subject or req.topic
    scale = req.user_rating_scale or "10"
    sections = _split_commentary_sections(req)
    shots: list[Shot] = []
    idx = 0
    shots.append(
        Shot(
            idx,
            f"{subject} — Review",
            f"My honest review of {subject}. I rated it {req.user_rating:g}/{scale}.",
            "review title card",
            4.0,
            segment_kind=ShotSegmentKind.TITLE_CARD,
        )
    )
    idx += 1
    trailer_cursor = 0.0
    for title, text in sections:
        shots.append(
            Shot(
                idx,
                title,
                text,
                f"commentary card about {subject}",
                max(10.0, min(28.0, len(text.split()) * 0.45)),
                segment_kind=ShotSegmentKind.COMMENTARY,
            )
        )
        idx += 1
        if title in {"Standout moments", "What worked"}:
            shots.append(
                Shot(
                    idx,
                    f"Trailer beat — {title}",
                    text[:120],
                    "official trailer clip",
                    4.5,
                    source_start_sec=trailer_cursor,
                    source_end_sec=trailer_cursor + 4.5,
                    segment_kind=ShotSegmentKind.TRAILER,
                )
            )
            trailer_cursor += 8.0
            idx += 1
    if req.media_type is MediaType.GAME and req.gameplay_path.strip():
        shots.append(
            Shot(
                idx,
                "Gameplay",
                req.user_moments or req.user_opinion,
                "user gameplay capture",
                12.0,
                segment_kind=ShotSegmentKind.GAMEPLAY,
            )
        )
        idx += 1
    credit_line = ""
    if attribution:
        from trendforge.services.trailer_allowlist import format_attribution_credit

        credit_line = format_attribution_credit(attribution)
    shots.append(
        Shot(
            idx,
            "Credits",
            credit_line or f"Review by {channel_name or 'TrendForge Studio'}. {cta}",
            "trailer credits",
            5.0,
            segment_kind=ShotSegmentKind.CREDITS,
        )
    )
    script = VideoScript(
        title=f"{subject} Review — {req.user_rating:g}/{scale}",
        hook=f"I watched {subject} so you know if it's worth your time.",
        summary=f"Personal review of {subject}. Rating: {req.user_rating:g}/{scale}.",
        youtube_description=(
            f"{subject} review — my genuine opinion.\n\n"
            f"Rating: {req.user_rating:g}/{scale}\n\n"
            f"{req.user_verdict or req.user_opinion}\n\n"
            f"{credit_line}\n\n{cta}"
        ),
        tags=[w for w in re.split(r"\W+", subject) if len(w) > 2][:6] + ["review", req.media_type.value],
        chapters=[("0:00", "Intro"), ("0:20", "My take"), ("1:00", "Verdict")],
        shots=shots,
        style_notes="review; user opinion only; trailer clips minority",
        youtube=YouTubePack(
            titles=[
                f"{subject} Review — Is It Worth It?",
                f"I rated {subject} {req.user_rating:g}/{scale}",
                f"My honest {subject} review",
            ],
            thumbnail_text=f"{req.user_rating:g}/{scale}",
            pinned_comment=f"What did you think of {subject}? {cta}",
            community_post=f"New review: {subject}",
            end_screen=cta,
            hashtags=["review", req.media_type.value, "honestreview"],
        ),
        trailer_attributions=[attribution] if attribution else [],
    )
    return enforce_trailer_budget(script)


def generate_review_script(
    req: GenerationRequest,
    extra_context: str = "",
    ollama: OllamaClient | None = None,
    ollama_model: str = "",
    attribution: TrailerAttribution | None = None,
    channel_name: str = "",
    cta: str = "Subscribe for more honest reviews.",
) -> VideoScript:
    fallback = template_review_script(req, attribution, channel_name, cta)
    if ollama is None:
        return fallback
    model = ollama.pick_model(ollama_model)
    if not model:
        return fallback
    prompt = f"""Create a YouTube review video plan for:
{_review_user_context(req)}

Trailer context (for clip timestamps only — do NOT copy trailer narration as your opinion):
{extra_context[:3000]}

Channel: {channel_name or 'independent'}
CTA: {cta}
Keep trailer segments under 25% of total runtime. Use the user's words for commentary.
"""
    try:
        raw = ollama.generate_json(model, prompt, REVIEW_SYSTEM)
        data = _extract_json(raw)
        if not data or not data.get("shots"):
            return fallback
        script = script_from_payload(data, req.review_subject, cta)
        if attribution:
            script.trailer_attributions = [attribution]
        script = enforce_trailer_budget(script)
        if not script.shots:
            return fallback
        return script
    except Exception as exc:
        log.warning("Review script generation failed: %s", exc)
        return fallback
