from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from trendforge.logging_setup import get_logger

log = get_logger("ollama")


@dataclass(slots=True)
class OllamaStatus:
    running: bool
    models: list[str]
    url: str
    error: str = ""


class OllamaClient:
    def __init__(self, base_url: str = "http://127.0.0.1:11434") -> None:
        self.base_url = base_url.rstrip("/")

    def status(self) -> OllamaStatus:
        try:
            with httpx.Client(timeout=2.0) as client:
                res = client.get(f"{self.base_url}/api/tags")
                res.raise_for_status()
                data = res.json()
            names = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
            return OllamaStatus(True, names, self.base_url)
        except Exception as exc:
            return OllamaStatus(False, [], self.base_url, error=str(exc))

    def generate_json(self, model: str, prompt: str, system: str = "") -> str:
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.6},
        }
        if system:
            payload["system"] = system
        with httpx.Client(timeout=180) as client:
            res = client.post(f"{self.base_url}/api/generate", json=payload)
            res.raise_for_status()
            data = res.json()
        return str(data.get("response") or "")

    def pick_model(self, preferred: str = "") -> str:
        st = self.status()
        if preferred and preferred in st.models:
            return preferred
        ranking = (
            "qwen2.5:14b",
            "qwen2.5:7b",
            "llama3.1:8b",
            "llama3.3",
            "gemma3:12b",
            "gemma2:9b",
            "mistral",
            "qwen2.5",
            "llama3.1",
            "gemma",
        )
        for name in ranking:
            for installed in st.models:
                if name in installed:
                    return installed
        return st.models[0] if st.models else ""

    def pull(
        self,
        tag: str,
        on_progress: Callable[[str, int], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> None:
        with httpx.Client(timeout=None) as client:
            with client.stream("POST", f"{self.base_url}/api/pull", json={"name": tag, "stream": True}) as res:
                res.raise_for_status()
                for line in res.iter_lines():
                    if cancelled and cancelled():
                        raise RuntimeError("Cancelled")
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    status = str(data.get("status") or "")
                    completed = int(data.get("completed") or 0)
                    total = int(data.get("total") or 0)
                    pct = int(completed * 100 / total) if total else 20
                    if on_progress:
                        on_progress(f"Ollama {tag}: {status}", min(99, pct))
                    if status.lower() in {"success", "complete"}:
                        return

