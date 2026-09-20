from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

import httpx

from trendforge.logging_setup import get_logger
from trendforge.services.debug_trace import host_snapshot, log as dbg

log = get_logger("maestro.client")

ProgressFn = Callable[[str, int], None]

# I2V / motion-control models are not story T2V. Matching "director" used to
# fall through to whatever was first in the registry (often Wan Move).
_NOT_STORY_VIDEO = (
    "wanmove",
    "wan_move",
    "wan-move",
    "recammaster",
    "recam_master",
    "phantom",
    "vace",
    "funcontrol",
)


def status_progress_percent(status: dict[str, Any]) -> int:
    """Maestro Director returns progress as a dict; Studio jobs may use an int."""
    raw = status.get("progress")
    if isinstance(raw, dict):
        current = raw.get("current")
        total = raw.get("total")
        step = raw.get("step")
        total_steps = raw.get("total_steps")
        try:
            if total:
                return max(0, min(100, int(100 * float(current or 0) / float(total))))
            if total_steps:
                return max(0, min(100, int(100 * float(step or 0) / float(total_steps))))
            if current is not None:
                return max(0, min(100, int(float(current))))
        except (TypeError, ValueError):
            return 0
        return 0
    try:
        return max(0, min(100, int(raw or 0)))
    except (TypeError, ValueError):
        return 0


def status_progress_message(status: dict[str, Any], fallback: str = "") -> str:
    raw = status.get("progress")
    if isinstance(raw, dict):
        msg = str(raw.get("message") or "").strip()
        if msg:
            return msg
    return fallback


class MaestroError(RuntimeError):
    pass


def director_start_unreachable(exc: BaseException) -> bool:
    """True when Director never started (missing route / dead proxy), not a later pipeline miss."""
    text = str(exc).lower()
    if "pipeline not found" in text:
        return False
    return "404" in text or "not found" in text or "405" in text or "http error 404" in text


class MaestroClient:
    """Thin REST client for Maestro's FastAPI (`/api/v1/...`)."""

    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _client(self, timeout: float | None = None) -> httpx.Client:
        return httpx.Client(timeout=timeout or self.timeout, follow_redirects=True)

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self.base_url}{path}"
        try:
            with self._client() as client:
                res = client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise MaestroError(f"Maestro request failed: {exc}") from exc
        if res.status_code >= 400:
            detail = res.text
            try:
                payload = res.json()
                detail = str(payload.get("detail") or payload.get("error") or payload)
            except Exception:
                pass
            dbg(
                "maestro_http_error",
                method=method,
                url=url,
                status=res.status_code,
                detail=detail[:500],
            )
            raise MaestroError(f"{method} {url} -> {res.status_code}: {detail[:800]}")
        dbg("maestro_http_ok", method=method, path=path, status=res.status_code)
        if res.headers.get("content-type", "").startswith("application/json"):
            return res.json()
        return res.content

    def ping(self) -> bool:
        try:
            self._request("GET", "/api/v1/models")
            return True
        except MaestroError:
            return False

    def models(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/models")

    def system_detect(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/system-detect")

    def system_stats(self) -> dict[str, Any]:
        try:
            return self._request("GET", "/api/v1/system-stats")
        except MaestroError:
            return {}

    def llm_status(self) -> dict[str, Any]:
        try:
            return self._request("GET", "/api/v1/llm/status")
        except MaestroError:
            return {}

    def generate(self, params: dict[str, Any], hold: bool = False) -> dict[str, Any]:
        body = {**params, "_queue_mode": "held" if hold else "now"}
        dbg(
            "maestro_generate_start",
            model_type=body.get("model_type"),
            resolution=body.get("resolution"),
            prompt=(str(body.get("prompt") or "")[:240]),
            hold=hold,
            url=self.base_url,
        )
        host_snapshot("before_generate")
        try:
            result = self._request("POST", "/api/v1/generate", json=body)
        except Exception:
            host_snapshot("after_generate_http_error")
            raise
        dbg(
            "maestro_generate_accepted",
            job_id=result.get("job_id") if isinstance(result, dict) else None,
            keys=list(result) if isinstance(result, dict) else type(result).__name__,
        )
        host_snapshot("after_generate_accepted")
        return result

    def job_status(self, job_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/v1/status/{job_id}")

    def cancel_job(self, job_id: str) -> None:
        self._request("POST", f"/api/v1/cancel/{job_id}")

    def wait_job(
        self,
        job_id: str,
        on_progress: ProgressFn | None = None,
        cancelled: Callable[[], bool] | None = None,
        poll: float = 2.0,
        timeout_sec: float = 60 * 60 * 6,
    ) -> dict[str, Any]:
        started = time.time()
        last_phase = ""
        host_snapshot(f"before_wait_job:{job_id[:12]}")
        while True:
            if cancelled and cancelled():
                try:
                    self.cancel_job(job_id)
                except MaestroError:
                    pass
                raise MaestroError("Cancelled")
            status = self.job_status(job_id)
            state = str(status.get("status", ""))
            pct = status_progress_percent(status)
            msg = status_progress_message(
                status,
                str(status.get("message") or status.get("phase") or state),
            )
            phase = str(status.get("phase") or msg or state)
            if phase != last_phase:
                dbg(
                    "maestro_job_phase",
                    job_id=job_id,
                    phase=phase[:400],
                    state=state,
                    pct=pct,
                )
                lowered = phase.lower()
                if any(token in lowered for token in ("load", "loading model", "unet", "vae", "text encoder")):
                    host_snapshot(f"job_model_load:{job_id[:12]}")
                last_phase = phase
            if on_progress:
                on_progress(msg, pct)
            if state in {"completed", "failed", "cancelled"}:
                dbg(
                    "maestro_job_terminal",
                    job_id=job_id,
                    state=state,
                    error=status.get("error"),
                    output_files=status.get("output_files") or status.get("files"),
                    elapsed_sec=round(time.time() - started, 1),
                )
                host_snapshot(f"after_wait_job:{job_id[:12]}")
                if state != "completed":
                    raise MaestroError(status.get("error") or f"Maestro job {state}")
                return status
            if time.time() - started > timeout_sec:
                raise MaestroError("Timed out waiting for Maestro job")
            time.sleep(poll)

    def start_director(self, params: dict[str, Any]) -> str:
        last_error: MaestroError | None = None
        for path in (
            "/api/v1/director/pipeline/start",
            "/api/v1/director/pipelines/start",
        ):
            try:
                data = self._request("POST", path, json=params)
            except MaestroError as exc:
                if director_start_unreachable(exc):
                    last_error = exc
                    continue
                raise
            pid = data.get("pipeline_id") or data.get("id") or data.get("pipeline_id")
            if not pid:
                raise MaestroError(f"Director start did not return pipeline_id: {data}")
            dbg("maestro_director_started", pipeline_id=str(pid), path=path, url=self.base_url)
            return str(pid)
        raise last_error or MaestroError(
            f"Director start URL not found on {self.base_url}"
        )

    def director_status(self, pid: str) -> dict[str, Any]:
        last_error: MaestroError | None = None
        for path in (
            f"/api/v1/director/pipeline/{pid}",
            f"/api/v1/director/pipelines/{pid}",
        ):
            try:
                return self._request("GET", path)
            except MaestroError as exc:
                if director_start_unreachable(exc) or "pipeline not found" in str(exc).lower():
                    last_error = exc
                    continue
                raise
        raise last_error or MaestroError(f"Director status URL not found for {pid}")

    def stop_director(self, pid: str) -> None:
        self._request("POST", f"/api/v1/director/pipeline/{pid}/stop")

    def resume_director(self, pid: str) -> None:
        self._request("POST", f"/api/v1/director/pipeline/{pid}/resume")

    def rerun_clip_video(self, pid: str, index: int, prompt: str = "") -> dict[str, Any]:
        return self._request(
            "POST",
            f"/api/v1/director/pipelines/{pid}/clips/{index}/rerun-video",
            json={"prompt": prompt or None},
        )

    def wait_director(
        self,
        pid: str,
        on_progress: ProgressFn | None = None,
        cancelled: Callable[[], bool] | None = None,
        poll: float = 3.0,
        timeout_sec: float = 60 * 60 * 12,
    ) -> dict[str, Any]:
        started = time.time()
        host_snapshot(f'before_wait_director:{pid[:12]}')
        last_phase = ''
        while True:
            if cancelled and cancelled():
                try:
                    self.stop_director(pid)
                except MaestroError:
                    pass
                raise MaestroError("Cancelled")
            try:
                status = self.director_status(pid)
            except MaestroError as exc:
                if time.time() - started < 90 and (
                    "404" in str(exc) or "not found" in str(exc).lower()
                ):
                    time.sleep(poll)
                    continue
                raise
            state = str(status.get("status") or status.get("state") or "")
            phase = status_progress_message(
                status,
                str(status.get("phase") or status.get("message") or state),
            )
            pct = status_progress_percent(status)
            if on_progress:
                on_progress(phase, pct)
            done_states = {"completed", "complete", "done", "failed", "error", "cancelled", "stopped"}
            if state.lower() in done_states:
                dbg(
                    "maestro_director_terminal",
                    pipeline_id=pid,
                    state=state,
                    phase=phase,
                    error=status.get("error"),
                    output_files=status.get("output_files") or status.get("output_files"),
                    elapsed_sec=round(time.time() - started, 1),
                )
                host_snapshot(f'after_wait_director:{pid[:12]}')
                if state.lower() in {"failed", "error", "cancelled", "stopped"}:
                    raise MaestroError(status.get("error") or phase or f"Director {state}")
                return status
            outputs = status.get("output_files") or status.get("output_files") or []
            if outputs and state.lower() in {"", "idle"} and pct >= 100:
                return status
            if time.time() - started > timeout_sec:
                raise MaestroError("Timed out waiting for Director pipeline")
            time.sleep(poll)

    def download_file(self, remote_path: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        safe = remote_path.lstrip("/").replace("\\", "/")
        url = f"{self.base_url}/api/v1/file/{safe}"
        dbg("maestro_download_start", remote_path=remote_path, dest=str(dest), url=url)
        with self._client(timeout=120) as client:
            with client.stream("GET", url) as res:
                if res.status_code >= 400:
                    dbg("maestro_download_error", status=res.status_code, remote_path=remote_path)
                    raise MaestroError(f"Download failed {res.status_code} for {remote_path}")
                with dest.open("wb") as handle:
                    for chunk in res.iter_bytes():
                        handle.write(chunk)
        size = dest.stat().st_size if dest.exists() else 0
        dbg("maestro_download_finish", dest=str(dest), size_bytes=size)
        return dest

    def _model_rows(self) -> list[dict[str, Any]]:
        try:
            payload = self.models()
        except MaestroError:
            return []
        models = payload.get("models") or []
        return [item for item in models if isinstance(item, dict)]

    def match_model(self, hint: str) -> str | None:
        hint_l = hint.lower()
        models = self._model_rows()
        scored: list[tuple[int, str]] = []
        for item in models:
            mtype = str(item.get("model_type") or item.get("id") or "")
            name = str(item.get("name") or "")
            blob = f"{mtype} {name}".lower()
            score = 0
            if hint_l and hint_l in blob:
                score += 10
            for token in hint_l.replace("-", " ").split():
                if token and token in blob:
                    score += 2
            if item.get("is_t2v") or item.get("is_i2v"):
                score += 1
            if score:
                scored.append((score, mtype))
        scored.sort(reverse=True)
        return scored[0][1] if scored else (str(models[0].get("model_type")) if models else None)

    def pick_story_video_model(self, hint: str = "") -> str | None:
        """Pick an LTX-style T2V id. Never Wan Move / control models."""
        hint_l = (hint or "").strip().lower()
        if hint_l in {"", "director", "auto", "maestro"}:
            hint_l = "ltx2"
        ranked: list[tuple[int, str]] = []
        for item in self._model_rows():
            mtype = str(item.get("model_type") or item.get("id") or "").strip()
            if not mtype:
                continue
            name = str(item.get("name") or "")
            blob = f"{mtype} {name}".lower()
            if any(token in blob for token in _NOT_STORY_VIDEO):
                continue
            score = 0
            if hint_l and hint_l in blob:
                score += 20
            for token in hint_l.replace("-", " ").replace("_", " ").split():
                if token and token in blob:
                    score += 3
            if "ltx2" in blob or "ltx-2" in blob:
                score += 16
            elif "ltx" in blob:
                score += 10
            if "distilled" in blob:
                score += 4
            if item.get("is_t2v"):
                score += 5
            if item.get("is_i2v") and not item.get("is_t2v"):
                score -= 8
            if score > 0:
                ranked.append((score, mtype))
        ranked.sort(reverse=True)
        return ranked[0][1] if ranked else None

    def pick_image_model(self) -> str | None:
        for hint in ("flux2_klein", "flux2", "qwen_image", "flux"):
            found = self.match_model(hint)
            if found and "wan" not in found.lower():
                return found
        return None

    def start_weight_download(self, model_type: str) -> dict[str, Any]:
        return self._request("POST", f"/api/v1/models/{model_type}/download")

    def weight_downloads(self) -> dict[str, Any]:
        return self._request("GET", "/api/v1/models/downloads/status")

