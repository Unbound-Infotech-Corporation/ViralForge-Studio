"""Append-only debug log for Maestro pipeline root-cause work.

Writes to DEBUG_LOG.md at the repo root. Also records structured JSONL
next to it so Phase 1 rows can be tallied without scraping prose.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEBUG_MD = REPO_ROOT / "DEBUG_LOG.md"
DEBUG_JSONL = REPO_ROOT / "debug_runs.jsonl"


def _now() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def _no_window() -> int:
    if sys.platform == "win32":
        return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return 0


def log(event: str, **fields: Any) -> None:
    """Append a timestamped line to DEBUG_LOG.md and a JSONL record."""
    ts = _now()
    compact = {k: v for k, v in fields.items() if v is not None}
    line = f"- `{ts}` **{event}**"
    if compact:
        payload = json.dumps(compact, default=str, ensure_ascii=True)
        if len(payload) > 4000:
            payload = payload[:4000] + "…"
        line += f" — `{payload}`"
    DEBUG_MD.parent.mkdir(parents=True, exist_ok=True)
    with DEBUG_MD.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    record = {"ts": ts, "event": event, **compact}
    with DEBUG_JSONL.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, default=str) + "\n")


def _run(cmd: list[str], timeout: float = 20.0) -> str:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=_no_window(),
        )
    except FileNotFoundError:
        return f"(command not found: {cmd[0]})"
    except subprocess.TimeoutExpired:
        return f"(timeout running {' '.join(cmd[:4])})"
    out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
    return out.strip() or f"(exit {proc.returncode}, empty output)"


def nvidia_smi_snapshot() -> str:
    text = _run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu,utilization.memory,temperature.gpu",
            "--format=csv",
        ]
    )
    xid = _run(["nvidia-smi", "-q"], timeout=25.0)
    xid_hits = [
        line.strip()
        for line in xid.splitlines()
        if "xid" in line.lower() or "ecc" in line.lower() or "retired" in line.lower()
    ]
    extra = "\n".join(xid_hits[:20])
    if extra:
        return text + "\n" + extra
    return text


def disk_snapshot(paths: list[Path]) -> dict[str, Any]:
    rows: dict[str, Any] = {}
    df = _run(["df", "-h"])
    if not df.startswith("(command not found"):
        rows["df_-h"] = df[:2500]
    seen_drives: set[str] = set()
    for path in paths:
        try:
            resolved = path.expanduser().resolve()
        except OSError:
            resolved = path
        drive = resolved.drive or str(resolved.anchor) or str(resolved)
        if drive in seen_drives:
            continue
        seen_drives.add(drive)
        try:
            usage = shutil.disk_usage(resolved if resolved.exists() else drive or "/")
        except OSError as exc:
            rows[str(drive)] = {"error": str(exc)}
            continue
        rows[str(drive) or str(resolved)] = {
            "path": str(resolved),
            "total_gb": round(usage.total / (1024**3), 2),
            "used_gb": round(usage.used / (1024**3), 2),
            "free_gb": round(usage.free / (1024**3), 2),
        }
    return rows


def host_snapshot(label: str, extra_paths: list[Path] | None = None) -> dict[str, Any]:
    paths = [REPO_ROOT, Path("F:/"), Path("C:/")]
    if extra_paths:
        paths.extend(extra_paths)
    snap = {
        "label": label,
        "nvidia_smi": nvidia_smi_snapshot(),
        "disk": disk_snapshot(paths),
    }
    log(f"host_snapshot:{label}", nvidia_smi=snap["nvidia_smi"], disk=snap["disk"])
    return snap


def validate_video(path: Path, ffmpeg: str, min_duration_sec: float = 0.4) -> dict[str, Any]:
    """Check file exists, is non-empty, has duration/fps, and is not a solid color."""
    from trendforge.services.ffmpeg_tools import find_ffprobe, run_ffmpeg
    from trendforge.services.stitcher import probe_duration

    result: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else 0,
        "duration_sec": None,
        "fps": None,
        "width": None,
        "height": None,
        "pixel_variance": None,
        "solid_color": None,
        "empty": None,
        "pass": False,
        "fail_reason": "",
    }
    if not path.exists():
        result["fail_reason"] = "file missing"
        log("output_validation_FAIL", **result)
        return result
    if result["size_bytes"] < 8_000:
        result["empty"] = True
        result["fail_reason"] = f"file too small ({result['size_bytes']} bytes)"
        log("output_validation_FAIL", **result)
        return result
    result["empty"] = False

    probe = find_ffprobe(ffmpeg)
    if probe:
        proc = subprocess.run(
            [
                probe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,r_frame_rate,duration",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            creationflags=_no_window(),
        )
        try:
            info = json.loads(proc.stdout or "{}")
            stream = (info.get("streams") or [{}])[0]
            fmt = info.get("format") or {}
            result["width"] = stream.get("width")
            result["height"] = stream.get("height")
            rate = str(stream.get("r_frame_rate") or "")
            if "/" in rate:
                num, den = rate.split("/", 1)
                if float(den):
                    result["fps"] = round(float(num) / float(den), 3)
            dur = stream.get("duration") or fmt.get("duration")
            if dur is not None:
                result["duration_sec"] = round(float(dur), 3)
        except (json.JSONDecodeError, ValueError, TypeError, IndexError, ZeroDivisionError) as exc:
            result["fail_reason"] = f"ffprobe parse failed: {exc}"

    if result["duration_sec"] is None:
        try:
            result["duration_sec"] = round(probe_duration(path, ffmpeg), 3)
        except Exception as exc:
            result["fail_reason"] = result["fail_reason"] or f"duration probe failed: {exc}"

    if result["duration_sec"] is not None and result["duration_sec"] < min_duration_sec:
        result["fail_reason"] = f"duration {result['duration_sec']}s < {min_duration_sec}s"
        log("output_validation_FAIL", **result)
        return result

    tmp = path.parent / f"{path.stem}.dbg_frames"
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        dest_pattern = str(tmp / "f_%02d.png")
        proc = run_ffmpeg(
            [
                "-i",
                str(path),
                "-vf",
                "select=not(mod(n\\,8)),scale=64:64",
                "-frames:v",
                "4",
                dest_pattern,
            ],
            ffmpeg,
        )
        if proc.returncode != 0:
            run_ffmpeg(["-i", str(path), "-frames:v", "1", str(tmp / "f_01.png")], ffmpeg)
        from PIL import Image
        import statistics

        variances: list[float] = []
        for png in sorted(tmp.glob("*.png")):
            img = Image.open(png).convert("L")
            pixels = list(img.getdata())
            if len(pixels) < 10:
                continue
            variances.append(float(statistics.pvariance(pixels)))
        if variances:
            result["pixel_variance"] = round(sum(variances) / len(variances), 3)
            result["solid_color"] = result["pixel_variance"] < 4.0
            if result["solid_color"]:
                result["fail_reason"] = (
                    f"solid-color / near-zero variance ({result['pixel_variance']})"
                )
                log("output_validation_FAIL", **result)
                return result
    except Exception as exc:
        result["fail_reason"] = result["fail_reason"] or f"frame sample failed: {exc}"
        log("output_validation_FAIL", **result)
        return result
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if not result["fps"]:
        result["fail_reason"] = "missing framerate"
        log("output_validation_FAIL", **result)
        return result

    result["pass"] = True
    log("output_validation_PASS", **result)
    return result
