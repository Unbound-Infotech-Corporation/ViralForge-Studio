"""Episode plans that turn long acts into short Wan clips.

A single Wan 2.2 TI2V generation is about 5–8 seconds. A ~3 minute episode is
five acts of ~36 seconds, each act several of those clips stitched together.
"""

from __future__ import annotations

from dataclasses import dataclass

from trendforge.cinema.shots import CinemaEpisode, CinemaShot

CAMERA_BEATS: tuple[str, ...] = (
    "wide establishing shot, slow crane down",
    "medium tracking shot circling the ring",
    "close-up on scuffed chrome gloves and sparks",
    "low angle as a punch crosses the lens",
    "handheld follow through the ropes",
    "rack focus from the crowd back to the fighters",
)


@dataclass(frozen=True, slots=True)
class CinemaAct:
    title: str
    visual_prompt: str
    narration: str
    duration_sec: float = 36.0


ROBOT_BOXING_ACTS: tuple[CinemaAct, ...] = (
    CinemaAct(
        title="Walkout",
        visual_prompt=(
            "Photoreal cinematic wide shot of a rain-slick underground boxing arena. "
            "Two humanoid robots with brushed-chrome bodies and scuffed steel plating "
            "walk toward a neon-lit ring. Blue and magenta practical lights, haze, "
            "roaring crowd bokeh, no readable signage, no subtitles."
        ),
        narration="Two machines step into the light.",
    ),
    CinemaAct(
        title="Opening Bell",
        visual_prompt=(
            "Photoreal cinematic shot inside the neon boxing ring as the bell sounds. "
            "The chrome robots touch gloves, then explode into the first exchange. "
            "Sweatless metal, lens flares from overhead spots, motion blur on the jab, "
            "no readable signage, no subtitles."
        ),
        narration="The bell goes, and neither one blinks.",
    ),
    CinemaAct(
        title="Mid-Round",
        visual_prompt=(
            "Photoreal cinematic coverage of a brutal mid-round between two boxing robots. "
            "Combinations rattle the chassis, a clinch showers orange sparks off the plating, "
            "the ropes shudder, the crowd is a smear of color, no readable signage, no subtitles."
        ),
        narration="Halfway through, the ring is full of sparks.",
    ),
    CinemaAct(
        title="Knockdown",
        visual_prompt=(
            "Photoreal cinematic shot of a heavy cross landing on a boxing robot's jaw. "
            "The chrome fighter drops to one knee, oil like sweat on the canvas, "
            "the standing robot holds the follow-up, silence under the lights, "
            "no readable signage, no subtitles."
        ),
        narration="One knee hits the canvas.",
    ),
    CinemaAct(
        title="Decision",
        visual_prompt=(
            "Photoreal cinematic shot of the standing boxing robot raising a chrome fist "
            "as the referee robot steps aside. Confetti-less haze, the fallen fighter rises, "
            "the arena lights cool from magenta to white, no readable signage, no subtitles."
        ),
        narration="The decision is already in the room.",
    ),
)


def clips_per_act(act_sec: float, clip_sec: float) -> int:
    clip = max(0.5, float(clip_sec))
    return max(1, int(round(float(act_sec) / clip)))


def expand_act(
    *,
    index_start: int,
    act_index: int,
    title: str,
    visual_prompt: str,
    narration: str,
    act_sec: float,
    clip_sec: float,
    expand: bool,
) -> list[CinemaShot]:
    """Split one act into Wan-length shots. ``expand=False`` keeps a single clip."""
    prompt = visual_prompt.strip()
    if not prompt:
        raise ValueError(f"Act {act_index} ({title}) needs a visual prompt")
    if not expand:
        return [
            CinemaShot(
                index=index_start,
                title=f"Act {act_index} · {title}",
                narration=narration,
                visual_prompt=prompt,
                duration_sec=max(0.5, float(clip_sec)),
                kind="hero",
            )
        ]
    count = clips_per_act(act_sec, clip_sec)
    per = float(act_sec) / count
    shots: list[CinemaShot] = []
    for part in range(count):
        visual = prompt
        if count > 1:
            visual = f"{prompt} {CAMERA_BEATS[part % len(CAMERA_BEATS)]}."
        shot_title = f"Act {act_index} · {title}"
        if count > 1:
            shot_title = f"{shot_title} · {part + 1}/{count}"
        shots.append(
            CinemaShot(
                index=index_start + part,
                title=shot_title,
                narration=narration if part == 0 else "",
                visual_prompt=visual,
                duration_sec=per,
                kind="hero" if part == 0 else "beat",
            )
        )
    return shots


def episode_from_prompts(
    topic: str,
    prompts: list[str],
    *,
    title: str = "",
    clip_sec: float = 6.0,
    act_sec: float = 36.0,
    expand_acts: bool = False,
    act_titles: list[str] | None = None,
    narrations: list[str] | None = None,
) -> CinemaEpisode:
    """Build an episode from one prompt per act (or per shot when not expanded)."""
    if not prompts:
        raise ValueError("At least one shot prompt is required")
    cleaned = [p.strip() for p in prompts]
    if any(not p for p in cleaned):
        raise ValueError("Shot prompts must be non-empty")
    titles = list(act_titles) if act_titles is not None else [f"Shot {i}" for i in range(1, len(cleaned) + 1)]
    lines = list(narrations) if narrations is not None else [""] * len(cleaned)
    if len(titles) != len(cleaned) or len(lines) != len(cleaned):
        raise ValueError("act titles and narrations must match the prompt count")
    shots: list[CinemaShot] = []
    for i, prompt in enumerate(cleaned, start=1):
        shots.extend(
            expand_act(
                index_start=len(shots) + 1,
                act_index=i,
                title=titles[i - 1],
                visual_prompt=prompt,
                narration=lines[i - 1],
                act_sec=act_sec,
                clip_sec=clip_sec,
                expand=expand_acts,
            )
        )
    return CinemaEpisode(
        title=title or topic,
        topic=topic,
        series_title=title or topic,
        shots=shots,
    )


def robot_boxing_episode(
    topic: str = "Robot Boxing",
    *,
    clip_sec: float = 6.0,
    act_sec: float = 36.0,
    act_prompts: list[str] | None = None,
    expand_acts: bool = True,
) -> CinemaEpisode:
    """Five-act Robot Boxing plan, about three minutes when acts are 36s.

    Each act becomes ``round(act_sec / clip_sec)`` Wan clips (six 6s clips
    by default) so the stitch, not one generation, carries the act.
    """
    if len(ROBOT_BOXING_ACTS) != 5:
        raise RuntimeError("Robot Boxing plan must stay a 5-act structure")
    prompts = list(act_prompts) if act_prompts is not None else [act.visual_prompt for act in ROBOT_BOXING_ACTS]
    if len(prompts) != 5:
        raise ValueError("Robot Boxing expects exactly 5 act prompts")
    return episode_from_prompts(
        topic,
        prompts,
        title="Robot Boxing",
        clip_sec=clip_sec,
        act_sec=act_sec,
        expand_acts=expand_acts,
        act_titles=[act.title for act in ROBOT_BOXING_ACTS],
        narrations=[act.narration for act in ROBOT_BOXING_ACTS],
    )
