"""Wan 2.2 TI2V backends for ViralForge Cinema.

``DryRunWanBackend`` paints ffmpeg motion cards and needs no weights.

``DiffusersWanBackend`` loads a Diffusers snapshot (``model_index.json``) via
``WanPipeline`` for text-to-video and ``WanImageToVideoPipeline`` when a
keyframe image is supplied. Official Wan2.2 folders that only contain
WanModel shards, ``Wan2.2_VAE.pth``, and a T5 encoder are a different layout
and are not loaded here. Download ``Wan-AI/Wan2.2-TI2V-5B-Diffusers`` into
``models/cinema/wan2.2-ti2v-5b-diffusers``.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path

from trendforge.cinema.config import (
    WAN_TI2V_DIFFUSERS_DIRNAME,
    WAN_TI2V_DIFFUSERS_REPO,
)
from trendforge.cinema.shots import CinemaShot

log = logging.getLogger("trendforge.cinema.wan")

# Model-card negative prompt for Wan2.2 TI2V-5B.
WAN_NEGATIVE_PROMPT = (
    "色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，"
    "最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，"
    "画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，"
    "杂乱的背景，三条腿，背景人很多，倒着走"
)

_WAN_CLASS_NAMES = {"WanPipeline", "WanImageToVideoPipeline"}


class WanBackend(ABC):
    impl_id: str = "wan"

    @abstractmethod
    def generate(self, shot: CinemaShot, keyframe: Path | None, dest: Path) -> Path:
        raise NotImplementedError


class DryRunWanBackend(WanBackend):
    """Offline stand-in that renders a motion card via ffmpeg kenburns/color."""

    impl_id = "dry_run"

    def __init__(self, ffmpeg: str) -> None:
        self.ffmpeg = ffmpeg

    def generate(self, shot: CinemaShot, keyframe: Path | None, dest: Path) -> Path:
        from trendforge.services.stitcher import ken_burns_clip

        dest.parent.mkdir(parents=True, exist_ok=True)
        if keyframe and keyframe.exists():
            return ken_burns_clip(keyframe, dest, max(1.0, shot.duration_sec), (1280, 720), self.ffmpeg)
        # solid card with title burned via drawtext-less path: generate png then kenburns
        from PIL import Image, ImageDraw, ImageFont

        img_path = dest.with_suffix(".png")
        img = Image.new("RGB", (1280, 720), (12, 14, 22))
        draw = ImageDraw.Draw(img)
        title = (shot.title or f"Shot {shot.index}")[:80]
        body = (shot.visual_prompt or shot.narration or "")[:160]
        draw.rectangle((40, 40, 1240, 680), outline=(80, 160, 255), width=3)
        try:
            font = ImageFont.truetype("arial.ttf", 42)
            small = ImageFont.truetype("arial.ttf", 28)
        except Exception:
            font = ImageFont.load_default()
            small = font
        draw.text((70, 120), f"VF Cinema · {title}", fill=(240, 244, 255), font=font)
        draw.text((70, 220), body, fill=(180, 190, 210), font=small)
        img.save(img_path)
        out = ken_burns_clip(img_path, dest, max(1.0, shot.duration_sec), (1280, 720), self.ffmpeg)
        return out


def align_wan_dim(value: int) -> int:
    """Snap a spatial size to a multiple of 32 (Wan TI2V requirement)."""
    return max(64, (int(value) // 32) * 32)


def frames_for_duration(duration_sec: float, fps: int = 24, *, max_sec: float = 8.0) -> int:
    """Frame count for one Wan clip: 4n+1, capped at ``max_sec``.

    TI2V-5B samples at 24 fps. The model card's 121-frame clip is about 5s;
    193 frames is about 8s. Longer acts are several of these clips stitched.
    """
    fps_i = max(1, int(fps))
    dur = max(0.5, min(float(duration_sec), float(max_sec)))
    raw = max(5, int(round(dur * fps_i)))
    steps = max(1, int(round((raw - 1) / 4)))
    return 4 * steps + 1


def diffusers_importable() -> bool:
    try:
        import diffusers  # noqa: F401
        import torch  # noqa: F401
    except ImportError:
        return False
    return True


def cuda_available() -> bool:
    try:
        import torch
    except ImportError:
        return False
    try:
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _is_wan_diffusers_dir(path: Path) -> bool:
    index = path / "model_index.json"
    if not index.is_file():
        return False
    try:
        data = json.loads(index.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    return str(data.get("_class_name", "")) in _WAN_CLASS_NAMES


def find_diffusers_wan_snapshot(models_dir: Path) -> Path | None:
    """Locate a local Diffusers Wan snapshot under ``models_dir``.

    Prefers ``wan2.2-ti2v-5b-diffusers``. A sibling official folder such as
    ``wan2.2-ti2v-5b`` (pth shards, no ``model_index.json``) is ignored.
    """
    root = Path(models_dir)
    if _is_wan_diffusers_dir(root):
        return root
    preferred = (
        WAN_TI2V_DIFFUSERS_DIRNAME,
        "Wan2.2-TI2V-5B-Diffusers",
        "wan2.2-ti2v-5b",
    )
    for name in preferred:
        candidate = root / name
        if _is_wan_diffusers_dir(candidate):
            return candidate
    if not root.is_dir():
        return None
    for child in sorted(p for p in root.iterdir() if p.is_dir()):
        if _is_wan_diffusers_dir(child):
            return child
    return None


class DiffusersWanBackend(WanBackend):
    """Local Wan 2.2 TI2V-5B via Diffusers. Weights load on the first generate()."""

    impl_id = "diffusers_wan"

    def __init__(
        self,
        model_path: Path,
        *,
        device: str = "cuda",
        ffmpeg: str = "ffmpeg",
        height: int = 704,
        width: int = 1280,
        fps: int = 24,
        num_inference_steps: int = 50,
        guidance_scale: float = 5.0,
        offload: bool = True,
        max_clip_sec: float = 8.0,
        seed: int | None = None,
        negative_prompt: str = WAN_NEGATIVE_PROMPT,
        local_files_only: bool = True,
    ) -> None:
        self.model_path = Path(model_path)
        if not _is_wan_diffusers_dir(self.model_path):
            raise FileNotFoundError(
                f"{self.model_path} is not a Diffusers Wan snapshot "
                f"(missing model_index.json with _class_name WanPipeline). "
                f"Download {WAN_TI2V_DIFFUSERS_REPO}."
            )
        self.device = device or "cuda"
        self.ffmpeg = ffmpeg
        snapped_h = align_wan_dim(height)
        snapped_w = align_wan_dim(width)
        if snapped_h != int(height) or snapped_w != int(width):
            log.info("Wan size %sx%s snapped to %sx%s", width, height, snapped_w, snapped_h)
        self.height = snapped_h
        self.width = snapped_w
        self.fps = max(1, int(fps))
        self.num_inference_steps = max(1, int(num_inference_steps))
        self.guidance_scale = float(guidance_scale)
        self.offload = bool(offload)
        self.max_clip_sec = float(max_clip_sec)
        self.seed = seed
        self.negative_prompt = negative_prompt
        self.local_files_only = bool(local_files_only)
        self._text = None
        self._image = None

    def generate(self, shot: CinemaShot, keyframe: Path | None, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        prompt = (shot.visual_prompt or shot.narration or shot.title or "cinematic shot").strip()
        if shot.duration_sec > self.max_clip_sec + 0.05:
            log.warning(
                "Shot %s is %.1fs; a single Wan TI2V clip is capped at %.1fs. "
                "Stitch several clips per act (see robot_boxing_episode).",
                shot.index,
                shot.duration_sec,
                self.max_clip_sec,
            )
        num_frames = frames_for_duration(shot.duration_sec, self.fps, max_sec=self.max_clip_sec)
        common = {
            "prompt": prompt,
            "negative_prompt": self.negative_prompt,
            "height": self.height,
            "width": self.width,
            "num_frames": num_frames,
            "guidance_scale": self.guidance_scale,
            "num_inference_steps": self.num_inference_steps,
        }
        generator = self._generator(shot)
        if generator is not None:
            common["generator"] = generator
        try:
            if keyframe is not None and Path(keyframe).is_file():
                image = self._load_image(Path(keyframe))
                pipe = self._image_pipeline()
                result = pipe(image=image, **common)
            else:
                pipe = self._text_pipeline()
                result = pipe(**common)
        except Exception as exc:
            raise RuntimeError(
                f"Wan Diffusers generate failed for shot {shot.index} ({shot.title}): {exc}"
            ) from exc
        frames = result.frames[0] if hasattr(result, "frames") else result[0]
        if frames is None or len(frames) == 0:
            raise RuntimeError(f"Wan Diffusers returned no frames for shot {shot.index}")
        self._export(frames, dest)
        if not dest.is_file():
            raise RuntimeError(f"Wan Diffusers did not write {dest}")
        return dest

    def _generator(self, shot: CinemaShot):
        if self.seed is None:
            return None
        import torch

        # CPU generator stays valid with enable_model_cpu_offload.
        gen = torch.Generator(device="cpu")
        gen.manual_seed(int(self.seed) + int(shot.index))
        return gen

    def _load_image(self, path: Path):
        from diffusers.utils import load_image

        return load_image(str(path))

    def _export(self, frames, dest: Path) -> None:
        from diffusers.utils import export_to_video

        export_to_video(frames, str(dest), fps=self.fps)

    def _text_pipeline(self):
        if self._text is not None:
            return self._text
        self._forget("_image")
        torch, WanPipeline, _image_cls, AutoencoderKLWan = _import_wan(need_image=False)
        model = str(self.model_path)
        try:
            vae = AutoencoderKLWan.from_pretrained(
                model,
                subfolder="vae",
                torch_dtype=torch.float32,
                local_files_only=self.local_files_only,
            )
            pipe = WanPipeline.from_pretrained(
                model,
                vae=vae,
                torch_dtype=_pipe_dtype(torch, self.device),
                local_files_only=self.local_files_only,
            )
        except Exception as exc:
            raise RuntimeError(_load_error(self.model_path, exc)) from exc
        _place_pipe(pipe, self.device, self.offload)
        self._text = pipe
        return pipe

    def _image_pipeline(self):
        if self._image is not None:
            return self._image
        self._forget("_text")
        torch, _text_cls, WanImageToVideoPipeline, AutoencoderKLWan = _import_wan(need_image=True)
        if WanImageToVideoPipeline is None:
            raise RuntimeError(
                "This diffusers build has no WanImageToVideoPipeline. "
                "Install diffusers from git main to run TI2V image-to-video."
            )
        model = str(self.model_path)
        try:
            vae = AutoencoderKLWan.from_pretrained(
                model,
                subfolder="vae",
                torch_dtype=torch.float32,
                local_files_only=self.local_files_only,
            )
            pipe = WanImageToVideoPipeline.from_pretrained(
                model,
                vae=vae,
                torch_dtype=_pipe_dtype(torch, self.device),
                local_files_only=self.local_files_only,
            )
        except Exception as exc:
            raise RuntimeError(_load_error(self.model_path, exc)) from exc
        _place_pipe(pipe, self.device, self.offload)
        self._image = pipe
        return pipe

    def _forget(self, attr: str) -> None:
        pipe = getattr(self, attr)
        if pipe is None:
            return
        setattr(self, attr, None)
        del pipe
        try:
            import gc

            import torch

            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            return


def _import_wan(need_image: bool):
    try:
        import torch
        from diffusers import AutoencoderKLWan, WanPipeline
    except ImportError as exc:
        raise RuntimeError(
            "Diffusers Wan backend needs torch and a recent diffusers "
            "(WanPipeline, AutoencoderKLWan). Install with:\n"
            "  pip install -r requirements-cinema-gpu.txt"
        ) from exc
    image_cls = None
    if need_image:
        try:
            from diffusers import WanImageToVideoPipeline
        except ImportError as exc:
            raise RuntimeError(
                "This diffusers build has no WanImageToVideoPipeline. "
                "Install diffusers from git main to run TI2V image-to-video."
            ) from exc
        image_cls = WanImageToVideoPipeline
    return torch, WanPipeline, image_cls, AutoencoderKLWan


def _pipe_dtype(torch, device: str):
    if device.startswith("cuda") and torch.cuda.is_available():
        supported = getattr(torch.cuda, "is_bf16_supported", lambda: False)
        if supported():
            return torch.bfloat16
        return torch.float16
    return torch.float32


def _place_pipe(pipe, device: str, offload: bool) -> None:
    vae = getattr(pipe, "vae", None)
    if vae is not None and hasattr(vae, "enable_tiling"):
        vae.enable_tiling()
    if offload and device.startswith("cuda"):
        pipe.enable_model_cpu_offload()
        return
    pipe.to(device)


def _load_error(model_path: Path, exc: BaseException) -> str:
    return (
        f"Could not load Diffusers Wan snapshot at {model_path}. "
        f"Download {WAN_TI2V_DIFFUSERS_REPO} so this folder contains model_index.json. "
        f"Official Wan2.2 pth shards are a different layout. ({exc})"
    )


def resolve_wan_backend(config, ffmpeg: str) -> tuple[WanBackend, str]:
    """Pick Diffusers Wan when dry-run is off and CUDA plus a snapshot exist.

    Any miss falls back to ``DryRunWanBackend``. The reason string is empty
    when dry-run was requested or the GPU backend was selected.
    """
    if config.dry_run:
        return DryRunWanBackend(ffmpeg), ""
    if not diffusers_importable():
        reason = (
            "torch and diffusers are not installed "
            "(pip install -r requirements-cinema-gpu.txt)"
        )
        log.warning("cinema_dry_run is false but Wan GPU cannot start: %s", reason)
        return DryRunWanBackend(ffmpeg), reason
    if not cuda_available():
        reason = "CUDA is not available"
        log.warning("cinema_dry_run is false but Wan GPU cannot start: %s", reason)
        return DryRunWanBackend(ffmpeg), reason
    snapshot = find_diffusers_wan_snapshot(config.models_dir)
    if snapshot is None:
        reason = (
            f"No Diffusers Wan snapshot under {config.models_dir}. "
            f"Expected {WAN_TI2V_DIFFUSERS_DIRNAME}/model_index.json from {WAN_TI2V_DIFFUSERS_REPO}. "
            "Official Wan2.2 folders with WanModel shards, Wan2.2_VAE.pth, and T5 weights "
            "are not WanPipeline layout."
        )
        log.warning("cinema_dry_run is false but Wan GPU cannot start: %s", reason)
        return DryRunWanBackend(ffmpeg), reason
    backend = DiffusersWanBackend(
        snapshot,
        device=config.device,
        ffmpeg=ffmpeg,
        height=config.wan_height,
        width=config.wan_width,
        fps=config.wan_fps,
        num_inference_steps=config.wan_steps,
        guidance_scale=config.wan_guidance,
        offload=config.wan_offload,
        max_clip_sec=config.wan_max_clip_sec,
        seed=config.wan_seed,
    )
    log.info("Wan GPU backend: %s", snapshot)
    return backend, ""
