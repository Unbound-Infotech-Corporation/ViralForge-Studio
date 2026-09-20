"""Download / document HF weights for ViralForge Cinema (Wan 2.2 + LTX-2.5)."""
from __future__ import annotations

import argparse
from pathlib import Path

from trendforge.cinema.config import DEFAULT_MODELS_DIR, LTX25_REPO, WAN_I2V_REPO, WAN_TI2V_REPO


def print_plan(models_dir: Path) -> None:
    print("ViralForge Cinema — Hugging Face model plan")
    print(f"  models_dir: {models_dir}")
    print(f"  Wan I2V:    {WAN_I2V_REPO}")
    print(f"  Wan TI2V:   {WAN_TI2V_REPO}")
    print(f"  LTX-2.5:    {LTX25_REPO}")
    print()
    print("Install (when ready for GPU weights):")
    print("  pip install -U huggingface_hub")
    print(f'  huggingface-cli download {WAN_I2V_REPO} --local-dir "{models_dir / "wan2.2-i2v"}"')
    print(f'  huggingface-cli download {LTX25_REPO} --local-dir "{models_dir / "ltx-2.5"}"')
    print()
    print("Dry-run pipeline needs no weights (uses ffmpeg kenburns cards).")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m trendforge.cinema.download")
    p.add_argument("--models-dir", type=Path, default=DEFAULT_MODELS_DIR)
    p.add_argument("--fetch", action="store_true", help="Actually download (large).")
    args = p.parse_args(argv)
    args.models_dir.mkdir(parents=True, exist_ok=True)
    print_plan(args.models_dir)
    if args.fetch:
        try:
            from huggingface_hub import snapshot_download
        except ImportError:
            print("Install huggingface_hub first: pip install huggingface_hub")
            return 1
        snapshot_download(WAN_I2V_REPO, local_dir=str(args.models_dir / "wan2.2-i2v"))
        snapshot_download(LTX25_REPO, local_dir=str(args.models_dir / "ltx-2.5"))
        print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
