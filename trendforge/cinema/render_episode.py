"""Render a ViralForge Cinema episode to final.mp4.

Examples:

    python -m trendforge.cinema.render_episode --dry-run --topic "Robot Boxing" \\
        --prompt "walkout" --prompt "bell" --prompt "mid-round" \\
        --prompt "knockdown" --prompt "decision" --output final.mp4

    python -m trendforge.cinema.render_episode --robot-boxing --gpu --output final.mp4

``--robot-boxing`` expands five ~36s acts into short Wan clips (~6s each).
``--gpu`` sets cinema dry-run off; without CUDA and a Diffusers snapshot the
director still writes a video using the ffmpeg dry-run path.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from trendforge.cinema.config import DEFAULT_MODELS_DIR, WAN_TI2V_DIFFUSERS_DIRNAME, CinemaConfig
from trendforge.cinema.director import CinemaDirector
from trendforge.cinema.plans import ROBOT_BOXING_ACTS, episode_from_prompts, robot_boxing_episode
from trendforge.cinema.wan_backend import DiffusersWanBackend
from trendforge.services.ffmpeg_tools import find_ffmpeg


def _settings_values() -> tuple[bool, Path]:
    """Read cinema_dry_run and cinema_models_dir without creating settings."""
    dry = True
    models = DEFAULT_MODELS_DIR
    try:
        from trendforge.bootstrap import resolve_data_root

        path = resolve_data_root() / "settings.json"
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                dry = bool(data.get("cinema_dry_run", True))
                raw_models = data.get("cinema_models_dir") or ""
                if str(raw_models).strip():
                    models = Path(str(raw_models))
    except Exception:
        return True, DEFAULT_MODELS_DIR
    return dry, models


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m trendforge.cinema.render_episode",
        description="Render a topic plus five shot prompts (or the Robot Boxing plan) to final.mp4.",
    )
    parser.add_argument("--topic", default="Robot Boxing", help="Episode topic.")
    parser.add_argument("--title", default="", help="Episode title. Defaults to the topic.")
    parser.add_argument(
        "--prompt",
        action="append",
        default=[],
        help="Shot or act prompt. Pass exactly five, unless --robot-boxing supplies them.",
    )
    parser.add_argument(
        "--robot-boxing",
        action="store_true",
        help="Use the built-in 5-act Robot Boxing plan (~3 min, six ~6s clips per act).",
    )
    parser.add_argument(
        "--expand-acts",
        action="store_true",
        help="Treat each of the five prompts as a ~36s act split into short Wan clips.",
    )
    parser.add_argument(
        "--no-expand",
        action="store_true",
        help="With --robot-boxing, render one short clip per act instead of a 3 minute stitch.",
    )
    parser.add_argument("--clip-sec", type=float, default=6.0, help="Length of one Wan clip (about 5–8s).")
    parser.add_argument("--act-sec", type=float, default=36.0, help="Length of one act when expanding.")
    parser.add_argument("--output", type=Path, default=Path("final.mp4"), help="Destination mp4.")
    parser.add_argument("--work-dir", type=Path, default=None, help="Per-shot clip directory.")
    parser.add_argument("--models-dir", type=Path, default=None, help="Cinema models root.")
    parser.add_argument("--dry-run", action="store_true", help="Force the ffmpeg stand-in. No GPU weights.")
    parser.add_argument(
        "--gpu",
        action="store_true",
        help="Request the Diffusers Wan backend (same as cinema_dry_run false).",
    )
    parser.add_argument(
        "--require-gpu",
        action="store_true",
        help="Exit with status 3 if the Diffusers backend cannot be selected.",
    )
    parser.add_argument("--steps", type=int, default=50, help="Wan inference steps (model card uses 50).")
    parser.add_argument("--height", type=int, default=704)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--xfade", type=float, default=0.35, help="Crossfade seconds. 0 cuts hard.")
    parser.add_argument(
        "--ltx-bridge",
        action="store_true",
        help="Insert dry-run LTX bridge cards between hero shots.",
    )
    parser.add_argument(
        "--no-offload",
        action="store_true",
        help="Keep the Wan pipeline on GPU instead of model CPU offload.",
    )
    return parser


def episode_for_args(args: argparse.Namespace):
    prompts: list[str] = list(args.prompt or [])
    expand = bool(args.expand_acts)
    if args.robot_boxing:
        if prompts and len(prompts) != len(ROBOT_BOXING_ACTS):
            raise SystemExit(
                f"--robot-boxing takes exactly {len(ROBOT_BOXING_ACTS)} --prompt overrides "
                f"(or none to use the built-in acts)."
            )
        return robot_boxing_episode(
            args.topic,
            clip_sec=args.clip_sec,
            act_sec=args.act_sec,
            act_prompts=prompts or None,
            expand_acts=not args.no_expand,
        )
    if len(prompts) != 5:
        raise SystemExit("Pass exactly 5 --prompt values, or use --robot-boxing.")
    if args.no_expand:
        expand = False
    return episode_from_prompts(
        args.topic,
        prompts,
        title=args.title or args.topic,
        clip_sec=args.clip_sec,
        act_sec=args.act_sec,
        expand_acts=expand,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.dry_run and args.gpu:
        print("Pass only one of --dry-run or --gpu.", file=sys.stderr)
        return 2
    if args.clip_sec <= 0 or args.act_sec <= 0:
        print("--clip-sec and --act-sec must be positive.", file=sys.stderr)
        return 2
    try:
        episode = episode_for_args(args)
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    settings_dry, settings_models = _settings_values()
    if args.dry_run:
        dry = True
    elif args.gpu or args.require_gpu:
        dry = False
    else:
        dry = settings_dry
    models_dir = args.models_dir if args.models_dir is not None else settings_models
    try:
        ffmpeg = find_ffmpeg()
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    config = CinemaConfig(
        models_dir=models_dir,
        dry_run=dry,
        bridge_with_ltx=bool(args.ltx_bridge),
        xfade_sec=max(0.0, float(args.xfade)),
        wan_height=args.height,
        wan_width=args.width,
        wan_steps=args.steps,
        wan_offload=not args.no_offload,
        wan_clip_sec=args.clip_sec,
        wan_seed=args.seed,
    )
    director = CinemaDirector(config, ffmpeg=ffmpeg)
    if args.require_gpu and not isinstance(director.wan, DiffusersWanBackend):
        print(director.fallback_reason or "Wan GPU backend was not selected.", file=sys.stderr)
        print(
            f"Download {config.wan_diffusers_repo} to "
            f"{config.models_dir / WAN_TI2V_DIFFUSERS_DIRNAME}",
            file=sys.stderr,
        )
        return 3

    output = args.output
    work = args.work_dir if args.work_dir is not None else output.parent / f"{output.stem}_work"
    result = director.run(episode, work, output)
    print("ViralForge Cinema")
    print(f"  topic:    {episode.topic}")
    print(f"  shots:    {len(episode.shots)} ({episode.target_duration:.1f}s)")
    print(f"  backend:  {result.wan_impl}")
    if result.fallback_reason:
        print(f"  fallback: {result.fallback_reason}")
    print(f"  output:   {result.final_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
