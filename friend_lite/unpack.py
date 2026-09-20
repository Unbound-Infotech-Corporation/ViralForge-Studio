"""Unpack friend_lite/sources.tgz.b64 into the repo root."""

from __future__ import annotations

import base64
import io
import tarfile
from pathlib import Path

raw = base64.b64decode(Path("friend_lite/sources.tgz.b64").read_text())
tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz").extractall(".")
print("unpacked Lite setup sources")
