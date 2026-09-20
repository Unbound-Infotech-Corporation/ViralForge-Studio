from __future__ import annotations

from trendforge.services.maestro_client import (
    MaestroClient,
    MaestroError,
    status_progress_message,
    status_progress_percent,
)


def test_progress_percent_accepts_director_dict() -> None:
    assert status_progress_percent(
        {"progress": {"current": 1, "total": 4, "message": "Planning with LLM..."}}
    ) == 25
    assert status_progress_percent({"progress": 40}) == 40
    assert status_progress_percent({"progress": None}) == 0
    assert status_progress_percent({"progress": {"current": 0, "total": 0}}) == 0
    assert status_progress_message(
        {"progress": {"message": "Generating video..."}},
        "running",
    ) == "Generating video..."


def test_wait_director_does_not_crash_on_progress_dict() -> None:
    client = MaestroClient("http://127.0.0.1:9")
    calls = {"n": 0}

    def fake_status(_pid: str) -> dict:
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "status": "running",
                "phase": "planning",
                "progress": {
                    "current": 0,
                    "total": 3,
                    "message": "Planning with LLM...",
                    "step": 0,
                    "total_steps": 0,
                },
            }
        return {
            "status": "completed",
            "progress": {"current": 3, "total": 3, "message": "Done"},
            "output_files": ["out.mp4"],
        }

    client.director_status = fake_status  # type: ignore[method-assign]
    seen: list[tuple[str, int]] = []
    result = client.wait_director("abc", on_progress=lambda msg, pct: seen.append((msg, pct)), poll=0)
    assert result["output_files"] == ["out.mp4"]
    assert seen[0] == ("Planning with LLM...", 0)
    assert calls["n"] == 2


def test_wait_director_surfaces_pipeline_error() -> None:
    client = MaestroClient("http://127.0.0.1:9")
    client.director_status = lambda _pid: {  # type: ignore[method-assign]
        "status": "failed",
        "progress": {"current": 0, "total": 1, "message": "Error: boom"},
        "error": "Planning produced no clip plans",
    }
    try:
        client.wait_director("dead", poll=0)
        raise AssertionError("expected MaestroError")
    except MaestroError as exc:
        assert "Planning produced no clip plans" in str(exc)


def test_pick_story_video_model_skips_wanmove() -> None:
    client = MaestroClient("http://127.0.0.1:9")
    client.models = lambda: {  # type: ignore[method-assign]
        "models": [
            {"model_type": "wanmove", "name": "Wan Move", "is_i2v": True},
            {
                "model_type": "ltx2_22B_distilled_1_1",
                "name": "LTX-2 Distilled",
                "is_t2v": True,
            },
        ]
    }
    assert client.pick_story_video_model("director") == "ltx2_22B_distilled_1_1"
    assert client.pick_story_video_model("") == "ltx2_22B_distilled_1_1"
    assert client.pick_image_model() is None


def test_start_director_retries_legacy_path_on_404() -> None:
    from trendforge.services.maestro_client import director_start_unreachable

    client = MaestroClient("http://127.0.0.1:42130")
    calls: list[str] = []

    def fake_request(method: str, path: str, **_kwargs):
        calls.append(path)
        if path == "/api/v1/director/pipeline/start":
            raise MaestroError("POST http://127.0.0.1:9/api/v1/director/pipeline/start -> 404: Not Found")
        return {"pipeline_id": "abc123"}

    client._request = fake_request  # type: ignore[method-assign]
    assert client.start_director({"pipeline_type": "short_film_story"}) == "abc123"
    assert calls[0] == "/api/v1/director/pipeline/start"
    assert director_start_unreachable(MaestroError("HTTP Error 404: Not Found"))
    assert not director_start_unreachable(MaestroError("Pipeline not found"))
