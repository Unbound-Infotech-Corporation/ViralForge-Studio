from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from trendforge.bootstrap import assets_root, AppDirs


def ensure_bed_track(dirs: AppDirs, dest: Path | None = None) -> Path:
    """Create a soft royalty-free sine bed if no bundled music is present."""
    dest = dest or (dirs.music / "trendforge_bed.wav")
    if dest.exists() and dest.stat().st_size > 1000:
        return dest
    bundled = assets_root() / "music" / "bed.wav"
    if bundled.exists():
        return bundled
    dest.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 44100
    seconds = 90
    amplitude = 1800
    with wave.open(str(dest), "w") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        for i in range(sample_rate * seconds):
            t = i / sample_rate
            # Two-note pad, very quiet
            sample = int(
                amplitude
                * (
                    0.55 * math.sin(2 * math.pi * 110 * t)
                    + 0.35 * math.sin(2 * math.pi * 164.81 * t)
                    + 0.15 * math.sin(2 * math.pi * 220 * t)
                )
                * (0.85 + 0.15 * math.sin(2 * math.pi * 0.08 * t))
            )
            sample = max(-32767, min(32767, sample))
            wf.writeframes(struct.pack("<hh", sample, sample))
    return dest
