"""Phase 1: run the same Maestro Studio T2V job many times back-to-back.

Does not change generation logic. Logs disk/VRAM snapshots and output
validation for each attempt into DEBUG_LOG.md / debug_runs.jsonl.
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from trendforge.services.debug_trace import host_snapshot, log as dbg, validate_video
from trendforge.services.ffmpeg_tools import find_ffmpeg
from trendforge.services.maestro_client import MaestroClient, MaestroError
from trendforge.services.maestro_detect import detect_maestro
from trendforge.services.visual_policy import STUDIO_NEGATIVE

PROMPT = (
    "photoreal cinematic footage of a lone fishing boat on a dark lake at dawn, "
    "low fog, slow camera push-in, natural light, production lighting"
)


def classify(check: dict, error: str | None) -> str:
    if error:
        lowered = error.lower()
        if any(token in lowered for token in ("load", "oom", "cuda", "not found", "missing")):
            return "load_or_runtime_fail"
        return "failed"
    if not check.get("pass"):
        reason = str(check.get("fail_reason") or "")
        if check.get("empty"):
            return "empty"
        if check.get("solid_color"):
            var = check.get("pixel_variance")
            if var is not None and float(var) < 1.0:
                return "black_or_near_black"
            return "solid_color"
        return f"invalid:{reason[:80]}"
    return "success"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=16)
    parser.add_argument("--url", default="")
    args = parser.parse_args()

    dbg("phase1_start", runs=args.runs, prompt=PROMPT[:200])
    install = detect_maestro(args.url)
    url = args.url or install.running_url
    extra = []
    if install.maestro_root:
        extra.append(install.maestro_root)
    host_snapshot("phase1_session_start", extra_paths=extra)
    dbg(
        "maestro_detect",
        found=install.found,
        running_url=install.running_url,
        maestro_root=str(install.maestro_root) if install.maestro_root else "",
        notes=install.notes[:8],
    )
    if not url:
        dbg("phase1_blocked", reason="Maestro is not running; no URL to hit")
        print("Maestro is not running. Start it in Pinokio, then re-run this script.")
        return 2

    client = MaestroClient(url)
    if not client.ping():
        dbg("phase1_blocked", reason="ping failed", url=url)
        print(f"Maestro did not answer ping at {url}")
        return 2

    try:
        ffmpeg = find_ffmpeg()
    except FileNotFoundError as exc:
        dbg("phase1_blocked", reason=str(exc))
        print(exc)
        return 2

    model = client.pick_story_video_model("ltx") or client.match_model("ltx")
    dbg("phase1_model", model=model, url=url)
    if not model:
        dbg("phase1_blocked", reason="no story T2V model in Maestro registry")
        print("No story video model found in Maestro.")
        return 2

    out_dir = ROOT / "debug_runs" / "phase1"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "prompt": PROMPT,
        "negative_prompt": STUDIO_NEGATIVE,
        "model_type": model,
        "resolution": "1280x720",
    }

    summary: list[dict] = []
    for i in range(1, args.runs + 1):
        label = f"run_{i:02d}"
        dest = out_dir / f"{label}.mp4"
        dbg("phase1_run_start", run=i, dest=str(dest))
        host_snapshot(f"phase1_{label}_before", extra_paths=extra)
        error = None
        check: dict = {}
        try:
            result = client.generate(payload)
            job_id = str(result.get("job_id") or "")
            dbg("phase1_job_accepted", run=i, job_id=job_id, result_keys=list(result) if isinstance(result, dict) else None)
            if job_id:
                status = client.wait_job(job_id)
                files = status.get("output_files") or status.get("files") or []
            else:
                status = result
                files = result.get("output_files") or result.get("files") or []
            if not files:
                raise MaestroError(f"run {i}: completed with no output files: {status}")
            dbg("file_write_start", run=i, remote=str(files[0]), dest=str(dest))
            try:
                client.download_file(str(files[0]), dest)
            except MaestroError:
                src = Path(str(files[0]))
                if src.exists():
                    dest.write_bytes(src.read_bytes())
                else:
                    raise
            dbg(
                "file_write_finish",
                run=i,
                dest=str(dest),
                size_bytes=dest.stat().st_size if dest.exists() else 0,
            )
            check = validate_video(dest, ffmpeg)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            dbg("phase1_run_exception", run=i, error=error, traceback=traceback.format_exc()[-2500:])
        host_snapshot(f"phase1_{label}_after", extra_paths=extra)
        kind = classify(check, error)
        row = {
            "run": i,
            "class": kind,
            "error": error,
            "pass": bool(check.get("pass")),
            "fail_reason": check.get("fail_reason"),
            "size_bytes": check.get("size_bytes"),
            "duration_sec": check.get("duration_sec"),
            "fps": check.get("fps"),
            "pixel_variance": check.get("pixel_variance"),
            "solid_color": check.get("solid_color"),
            "dest": str(dest) if dest.exists() else "",
        }
        summary.append(row)
        dbg("phase1_run_result", **row)

    counts: dict[str, int] = {}
    for row in summary:
        counts[row["class"]] = counts.get(row["class"], 0) + 1
    dbg("phase1_complete", counts=counts, runs=len(summary))
    print("Phase 1 complete:", counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
