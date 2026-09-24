from __future__ import annotations

from trendforge.domain.enums import AspectRatio, BackendKind, ContentFormat, LengthPreset, VideoStyle
from trendforge.domain.models import ModelOption


def dropdown_label(opt: ModelOption) -> str:
    if opt.id == "auto":
        return "Auto — pick the best model for this PC"
    vram = "0 GB VRAM" if opt.vram_gb <= 0 else f"~{opt.vram_gb:g} GB VRAM"
    disk = "tiny" if opt.disk_gb < 1 else f"~{opt.disk_gb:g} GB disk"
    speed = {1: "slow", 2: "slow", 3: "medium", 4: "fast", 5: "fastest"}.get(opt.speed, "medium")
    return f"{opt.name}  ·  {vram}  ·  {disk}  ·  {speed}"


def format_defaults(fmt: ContentFormat) -> dict:
    """Sensible YouTube defaults so beginners don't have to think."""
    if fmt is ContentFormat.SHORTS:
        return {
            "length": LengthPreset.SHORTS,
            "aspect": AspectRatio.VERTICAL,
            "style": VideoStyle.CINEMATIC,
            "enable_intro": False,
            "enable_outro": True,
            "enable_voiceover": True,
        }
    if fmt is ContentFormat.VIDEO:
        return {
            "length": LengthPreset.MID,
            "aspect": AspectRatio.WIDE,
            "style": VideoStyle.CINEMATIC,
            "enable_intro": True,
            "enable_outro": True,
            "enable_voiceover": True,
        }
    if fmt is ContentFormat.LONG:
        return {
            "length": LengthPreset.LONG,
            "aspect": AspectRatio.WIDE,
            "style": VideoStyle.DOCUMENTARY,
            "enable_intro": True,
            "enable_outro": True,
            "enable_voiceover": True,
        }
    if fmt is ContentFormat.REVIEW:
        return {
            "length": LengthPreset.MID,
            "aspect": AspectRatio.WIDE,
            "style": VideoStyle.REVIEW,
            "enable_intro": False,
            "enable_outro": False,
            "enable_voiceover": True,
        }
    return {
        "length": LengthPreset.DOCUSERIES,
        "aspect": AspectRatio.WIDE,
        "style": VideoStyle.DOCUMENTARY,
        "enable_intro": True,
        "enable_outro": True,
        "enable_voiceover": True,
    }


def format_choices() -> list[tuple[str, str]]:
    return [
        ("YouTube Short  ·  15–60s  ·  9:16 vertical", ContentFormat.SHORTS.value),
        ("Standard video  ·  3–8 min  ·  16:9", ContentFormat.VIDEO.value),
        ("Long video  ·  10–18 min  ·  16:9", ContentFormat.LONG.value),
        ("Movie / show / game review  ·  your opinion + official trailers", ContentFormat.REVIEW.value),
        ("Docuseries episode  ·  18–40 min narrated", ContentFormat.DOCUSERIES.value),
        ("Plan a full docuseries season  ·  4–6 episodes", ContentFormat.SEASON.value),
    ]


def style_choices() -> list[tuple[str, str]]:
    return [
        ("Explainer — teach it clearly", VideoStyle.EXPLAINER.value),
        ("Breakdown — scene-by-scene / key moments", VideoStyle.BREAKDOWN.value),
        ("Documentary — narrated, measured, cinematic", VideoStyle.DOCUMENTARY.value),
        ("News recap — what happened today", VideoStyle.NEWS_RECAP.value),
        ("Ranking / list — numbered hooks", VideoStyle.RANKING.value),
        ("Story — narrative arc", VideoStyle.STORY.value),
        ("Educational — lesson structure", VideoStyle.EDUCATIONAL.value),
        ("Cinematic — filmic b-roll energy", VideoStyle.CINEMATIC.value),
        ("Reaction — commentary energy", VideoStyle.REACTION.value),
        ("Review — honest take + official trailer clips", VideoStyle.REVIEW.value),
    ]


def model_catalog() -> list[ModelOption]:
    """Built-in catalog. Maestro live models are merged on top at runtime."""
    return [
        ModelOption(
            id="auto",
            name="Auto (recommended for your GPU)",
            backend=BackendKind.AUTO,
            family="Smart",
            description="Picks ViralForge Cinema (native) by default; Quick Explainer if needed.",
            vram_gb=0,
            disk_gb=0,
            quality=4,
            speed=4,
            tooltip="Uses this PC's hardware. Cinematic models publish real footage only — title-card stand-ins are refused. Pick Quick Explainer for cards that always work.",
            mark="AU",
        ),
        ModelOption(
            id="viralforge_cinema",
            name="ViralForge Cinema (native)",
            backend=BackendKind.NATIVE_CINEMA,
            family="ViralForge",
            description="Native engine: Wan 2.2 heroes, CogVideoX when selected, LTX bridges, then stitch.",
            vram_gb=0,
            disk_gb=0,
            quality=5,
            speed=3,
            tooltip="Wan 2.2 and CogVideoX weights live in the cinema models folder. Missing weights are refused instead of published as title cards.",
            mark="VF",
        ),
        ModelOption(
            id="quick_explainer",
            name="Quick Explainer (works immediately)",
            backend=BackendKind.QUICK_EXPLAINER,
            family="Local motion graphics",
            description="Ken-Burns explainer cards + local voiceover. No multi-GB model download.",
            vram_gb=0,
            disk_gb=0.05,
            quality=3,
            speed=5,
            tooltip="Best first-run path. Produces a real YouTube-ready MP4 in minutes on CPU.",
            installable=False,
            mark="QE",
        ),
        ModelOption(
            id="source_clip",
            name="Clip + narrate (YouTube URL)",
            backend=BackendKind.SOURCE_CLIP,
            family="Source footage",
            description="Download a YouTube video, cut it into scenes, and overlay your voiceover.",
            vram_gb=0,
            disk_gb=0.5,
            quality=4,
            speed=4,
            tooltip="Paste a YouTube URL as the topic. Works like movie recap / story-time channels — clips existing footage with new narration.",
            installable=False,
            mark="YT",
        ),
        ModelOption(
            id="media_review",
            name="Media review (official trailers + your opinion)",
            backend=BackendKind.REVIEW,
            family="Review",
            description="Your genuine review with brief official trailer clips — never full-film footage or AI opinions.",
            vram_gb=0,
            disk_gb=0.5,
            quality=4,
            speed=4,
            tooltip="Requires your written opinion, rating, and an official trailer URL from the allowlisted studio channel.",
            installable=False,
            mark="RV",
        ),
        ModelOption(
            id="maestro_director",
            name="Maestro Director mode",
            backend=BackendKind.MAESTRO_DIRECTOR,
            family="Maestro",
            description="Full multi-clip Director pipeline (plan → keyframes → clips → combine).",
            vram_gb=8,
            disk_gb=20,
            quality=5,
            speed=2,
            maestro_type_hint="ltx2",
            supports_audio=True,
            tooltip="Legacy engine. Hidden from Create.",
            hidden=True,
            mark="MS",
        ),
        ModelOption(
            id="ltx25_distilled",
            name="LTX-2.5 Distilled (fast, synced audio)",
            backend=BackendKind.MAESTRO_STUDIO,
            family="LTX",
            description="Fast distilled LTX-2.5 with native synchronized audio when Maestro has it.",
            vram_gb=8,
            disk_gb=18,
            quality=4,
            speed=4,
            maestro_type_hint="ltx2.5",
            supports_audio=True,
            tooltip="Legacy engine. Hidden from Create.",
            hidden=True,
            mark="LT",
        ),
        ModelOption(
            id="ltx23",
            name="LTX-2.3",
            backend=BackendKind.MAESTRO_STUDIO,
            family="LTX",
            description="Proven LTX-2.3 video path via Maestro Studio.",
            vram_gb=8,
            disk_gb=16,
            quality=4,
            speed=3,
            maestro_type_hint="ltx2.3",
            tooltip="Legacy engine. Hidden from Create.",
            hidden=True,
            mark="LT",
        ),
        ModelOption(
            id="wan22_ti2v_5b",
            name="Wan 2.2 TI2V-5B",
            backend=BackendKind.NATIVE_CINEMA,
            family="Wan",
            description="Lighter Wan 2.2 text/image-to-video. Fits more GPUs than A14B.",
            vram_gb=10,
            disk_gb=12,
            quality=4,
            speed=3,
            maestro_type_hint="ti2v-5b",
            tooltip="Place Wan 2.2 TI2V-5B weights in the cinema models folder (wan2.2-ti2v-5b). Studio will not publish a title-card stand-in.",
            mark="W5",
        ),
        ModelOption(
            id="cogvideox",
            name="CogVideoX",
            backend=BackendKind.NATIVE_CINEMA,
            family="CogVideoX",
            description="CogVideoX text-to-video, listed beside Wan. Weights stay in the cinema models folder.",
            vram_gb=12,
            disk_gb=20,
            quality=4,
            speed=3,
            tooltip="Place CogVideoX weights in the cinema models folder (cogvideox), next to Wan. Missing weights are refused — no card final.",
            mark="CX",
        ),
        ModelOption(
            id="wan22_a14b",
            name="Wan 2.2 A14B",
            backend=BackendKind.NATIVE_CINEMA,
            family="Wan",
            description="Larger Wan 2.2 model. Higher quality, much heavier.",
            vram_gb=16,
            disk_gb=28,
            quality=5,
            speed=2,
            maestro_type_hint="a14b",
            tooltip="Needs a 16 GB+ card. Weights go in the cinema models folder (wan2.2-i2v). Title-card stand-ins are not published.",
            mark="WA",
        ),
        ModelOption(
            id="minimax_h3",
            name="MiniMax H3 (FL2VA / Omni)",
            backend=BackendKind.MAESTRO_STUDIO,
            family="MiniMax",
            description="H3 variants with audio and multi-window continuation when Maestro exposes them.",
            vram_gb=12,
            disk_gb=24,
            quality=5,
            speed=2,
            maestro_type_hint="h3",
            supports_audio=True,
            tooltip="Legacy engine. Hidden from Create.",
            hidden=True,
            mark="H3",
        ),
        ModelOption(
            id="hunyuan_15",
            name="HunyuanVideo-1.5",
            backend=BackendKind.MAESTRO_STUDIO,
            family="Hunyuan",
            description="Hunyuan video via Maestro / WanGP.",
            vram_gb=12,
            disk_gb=25,
            quality=4,
            speed=2,
            maestro_type_hint="hunyuan",
            tooltip="Legacy engine. Hidden from Create.",
            hidden=True,
            mark="HY",
        ),
        ModelOption(
            id="comfyui",
            name="ComfyUI (if running)",
            backend=BackendKind.COMFYUI,
            family="ComfyUI",
            description="Submit a bundled T2V workflow to a local ComfyUI server.",
            vram_gb=8,
            disk_gb=0,
            quality=4,
            speed=3,
            tooltip="Legacy engine. Hidden from Create.",
            hidden=True,
            mark="CF",
        ),
    ]


def option_by_id(model_id: str) -> ModelOption | None:
    for item in model_catalog():
        if item.id == model_id:
            return item
    return None


def visible_model_catalog() -> list[ModelOption]:
    """Create-page models. Legacy Maestro / Comfy rows stay in the full catalog but hidden."""
    return [item for item in model_catalog() if not item.hidden]


def is_hidden_model(model_id: str | None) -> bool:
    if not model_id:
        return False
    item = option_by_id(model_id)
    return bool(item and item.hidden)


FORMAT_MARKS = {
    ContentFormat.SHORTS.value: "SH",
    ContentFormat.VIDEO.value: "SV",
    ContentFormat.LONG.value: "LV",
    ContentFormat.REVIEW.value: "RV",
    ContentFormat.DOCUSERIES.value: "DS",
    ContentFormat.SEASON.value: "SE",
}

STYLE_MARKS = {
    VideoStyle.EXPLAINER.value: "EX",
    VideoStyle.BREAKDOWN.value: "BD",
    VideoStyle.DOCUMENTARY.value: "DC",
    VideoStyle.NEWS_RECAP.value: "NW",
    VideoStyle.RANKING.value: "RK",
    VideoStyle.STORY.value: "ST",
    VideoStyle.EDUCATIONAL.value: "ED",
    VideoStyle.CINEMATIC.value: "CM",
    VideoStyle.REACTION.value: "RC",
    VideoStyle.REVIEW.value: "RV",
}
