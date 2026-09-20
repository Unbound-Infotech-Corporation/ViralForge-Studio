from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import httpx

from trendforge.logging_setup import get_logger

log = get_logger("comfyui")
ProgressFn = Callable[[str, int], None]


DEFAULT_T2V_WORKFLOW = {
    "prompt": {
        "6": {
            "inputs": {"text": "PLACEHOLDER_PROMPT", "clip": ["11", 0]},
            "class_type": "CLIPTextEncode",
        },
        "7": {
            "inputs": {"text": "blurry, low quality, watermark, text", "clip": ["11", 0]},
            "class_type": "CLIPTextEncode",
        },
    }
}


class ComfyUIClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8188") -> None:
        self.base_url = base_url.rstrip("/")

    def ping(self) -> bool:
        try:
            with httpx.Client(timeout=1.5) as client:
                res = client.get(f"{self.base_url}/system_stats")
                return res.status_code == 200
        except httpx.HTTPError:
            return False

    def submit_prompt(self, workflow: dict[str, Any]) -> str:
        client_id = str(uuid.uuid4())
        with httpx.Client(timeout=30) as client:
            res = client.post(
                f"{self.base_url}/prompt",
                json={"prompt": workflow, "client_id": client_id},
            )
            res.raise_for_status()
            data = res.json()
        pid = data.get("prompt_id")
        if not pid:
            raise RuntimeError(f"ComfyUI did not return prompt_id: {data}")
        return str(pid)

    def wait(
        self,
        prompt_id: str,
        on_progress: ProgressFn | None = None,
        cancelled: Callable[[], bool] | None = None,
        timeout_sec: float = 60 * 60 * 4,
    ) -> dict[str, Any]:
        started = time.time()
        with httpx.Client(timeout=15) as client:
            while True:
                if cancelled and cancelled():
                    raise RuntimeError("Cancelled")
                res = client.get(f"{self.base_url}/history/{prompt_id}")
                res.raise_for_status()
                hist = res.json()
                if prompt_id in hist:
                    return hist[prompt_id]
                if on_progress:
                    on_progress("ComfyUI is generating…", 40)
                if time.time() - started > timeout_sec:
                    raise TimeoutError("ComfyUI timed out")
                time.sleep(2.0)

    def download_outputs(self, history: dict[str, Any], dest_dir: Path) -> list[Path]:
        dest_dir.mkdir(parents=True, exist_ok=True)
        files: list[Path] = []
        outputs = history.get("outputs") or {}
        with httpx.Client(timeout=120) as client:
            for node in outputs.values():
                for key in ("gifs", "videos", "images"):
                    for item in node.get(key) or []:
                        filename = item.get("filename")
                        if not filename:
                            continue
                        params = {
                            "filename": filename,
                            "subfolder": item.get("subfolder", ""),
                            "type": item.get("type", "output"),
                        }
                        res = client.get(f"{self.base_url}/view", params=params)
                        res.raise_for_status()
                        path = dest_dir / filename
                        path.write_bytes(res.content)
                        files.append(path)
        return files

    def load_workflow_file(self, path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))
