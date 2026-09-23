"""Diffusers Wan backend selection, frame math, and Robot Boxing plan.

GPU weights are not loaded. CUDA and diffusers are monkeypatched or skipped.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from trendforge.cinema.config import CinemaConfig
from trendforge.cinema.director import CinemaDirector
from trendforge.cinema.download import main as download_main
from trendforge.cinema.plans import robot_boxing_episode
from trendforge.cinema.render_episode import main as render_main
from trendforge.cinema.shots import CinemaEpisode, CinemaShot
from trendforge.cinema.wan_backend import (
    DiffusersWanBackend,
    DryRunWanBackend,
    align_wan_dim,
    find_diffusers_wan_snapshot,
    frames_for_duration,
    resolve_wan_backend,
)


def _ffmpeg() -> str:
    from trendforge.services.ffmpeg_tools import find_ffmpeg

    try:
        return find_ffmpeg()
    except FileNotFoundError:
        pytest.skip("ffmpeg not available")


def _write_index(directory: Path, class_name: str = "WanPipeline") -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "model_index.json").write_text(
        json.dumps({"_class_name": class_name}),
        encoding="utf-8",
    )


def test_official_pth_folder_is_not_a_diffusers_snapshot(tmp_path: Path) -> None:
    official = tmp_path / "wan2.2-ti2v-5b"
    official.mkdir()
    (official / "Wan2.2_VAE.pth").write_bytes(b"vae")
    (official / "models_t5_umt5-xxl-enc-bf16.pth").write_bytes(b"t5")
    (official / "diffusion_pytorch_model.safetensors.index.json").write_text("{}", encoding="utf-8")
    assert find_diffusers_wan_snapshot(tmp_path) is None

    snapshot = tmp_path / "wan2.2-ti2v-5b-diffusers"
    _write_index(snapshot)
    assert find_diffusers_wan_snapshot(tmp_path) == snapshot


def test_non_wan_model_index_is_ignored(tmp_path: Path) -> None:
    _write_index(tmp_path / "ltx-2.5", class_name="LTXPipeline")
    assert find_diffusers_wan_snapshot(tmp_path) is None


@pytest.mark.parametrize(
    ("duration", "expected"),
    [
        (5.0, 121),
        (6.0, 145),
        (8.0, 193),
        (36.0, 193),
        (2.0, 49),
    ],
)
def test_frames_for_duration_snaps_to_4n_plus_1(duration: float, expected: int) -> None:
    frames = frames_for_duration(duration, 24, max_sec=8.0)
    assert frames == expected
    assert frames % 4 == 1


def test_align_wan_dim_drops_720_to_704() -> None:
    assert align_wan_dim(720) == 704
    assert align_wan_dim(1280) == 1280
    assert align_wan_dim(704) == 704


def test_robot_boxing_plan_is_five_acts_about_three_minutes() -> None:
    episode = robot_boxing_episode()
    assert episode.topic == "Robot Boxing"
    assert len(episode.shots) == 30
    assert episode.target_duration == pytest.approx(180.0)
    assert all(shot.duration_sec == pytest.approx(6.0) for shot in episode.shots)
    assert all(shot.duration_sec <= 8.0 for shot in episode.shots)
    act_titles = {shot.title.split("·")[1].strip() for shot in episode.shots}
    assert act_titles == {"Walkout", "Opening Bell", "Mid-Round", "Knockdown", "Decision"}
    heroes = [shot for shot in episode.shots if shot.kind == "hero"]
    assert len(heroes) == 5
    prompts = [shot.visual_prompt for shot in episode.shots]
    assert len(set(prompts)) == 30


def test_robot_boxing_prompt_override_must_be_five() -> None:
    with pytest.raises(ValueError):
        robot_boxing_episode(act_prompts=["only one"])


def test_resolve_stays_dry_when_requested(tmp_path: Path) -> None:
    backend, reason = resolve_wan_backend(CinemaConfig(dry_run=True, models_dir=tmp_path), "ffmpeg")
    assert isinstance(backend, DryRunWanBackend)
    assert reason == ""


def test_resolve_falls_back_without_gpu_stack(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("trendforge.cinema.wan_backend.diffusers_importable", lambda: False)
    monkeypatch.setattr("trendforge.cinema.wan_backend.cuda_available", lambda: True)
    backend, reason = resolve_wan_backend(CinemaConfig(dry_run=False, models_dir=tmp_path), "ffmpeg")
    assert isinstance(backend, DryRunWanBackend)
    assert "diffusers" in reason.lower()


def test_resolve_falls_back_without_cuda(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_index(tmp_path / "wan2.2-ti2v-5b-diffusers")
    monkeypatch.setattr("trendforge.cinema.wan_backend.diffusers_importable", lambda: True)
    monkeypatch.setattr("trendforge.cinema.wan_backend.cuda_available", lambda: False)
    backend, reason = resolve_wan_backend(CinemaConfig(dry_run=False, models_dir=tmp_path), "ffmpeg")
    assert isinstance(backend, DryRunWanBackend)
    assert "CUDA" in reason


def test_resolve_rejects_official_weights_even_with_cuda(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    official = tmp_path / "wan2.2-ti2v-5b"
    official.mkdir()
    (official / "Wan2.2_VAE.pth").write_bytes(b"vae")
    monkeypatch.setattr("trendforge.cinema.wan_backend.diffusers_importable", lambda: True)
    monkeypatch.setattr("trendforge.cinema.wan_backend.cuda_available", lambda: True)
    backend, reason = resolve_wan_backend(CinemaConfig(dry_run=False, models_dir=tmp_path), "ffmpeg")
    assert isinstance(backend, DryRunWanBackend)
    assert "model_index.json" in reason


def test_resolve_selects_diffusers_when_snapshot_and_cuda(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_index(tmp_path / "wan2.2-ti2v-5b-diffusers")
    monkeypatch.setattr("trendforge.cinema.wan_backend.diffusers_importable", lambda: True)
    monkeypatch.setattr("trendforge.cinema.wan_backend.cuda_available", lambda: True)
    backend, reason = resolve_wan_backend(
        CinemaConfig(dry_run=False, models_dir=tmp_path, wan_steps=4, wan_height=720),
        "ffmpeg",
    )
    assert reason == ""
    assert isinstance(backend, DiffusersWanBackend)
    assert backend.height == 704
    assert backend.num_inference_steps == 4
    assert backend.model_path == tmp_path / "wan2.2-ti2v-5b-diffusers"


def test_diffusers_generate_text_and_keyframe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = tmp_path / "snap"
    _write_index(snapshot)
    backend = DiffusersWanBackend(snapshot, device="cpu", num_inference_steps=3, fps=24, max_clip_sec=8.0)
    seen: dict[str, dict] = {}

    def text_pipe():
        def run(**kwargs):
            seen["text"] = kwargs
            return SimpleNamespace(frames=[["frame"]])

        return run

    def image_pipe():
        def run(**kwargs):
            seen["image"] = kwargs
            return SimpleNamespace(frames=[["frame"]])

        return run

    monkeypatch.setattr(backend, "_text_pipeline", text_pipe)
    monkeypatch.setattr(backend, "_image_pipeline", image_pipe)
    monkeypatch.setattr(backend, "_load_image", lambda path: f"image:{path.name}")
    monkeypatch.setattr(backend, "_export", lambda frames, dest: dest.write_bytes(b"mp4"))

    shot = CinemaShot(1, "Bell", "narration", "robots boxing under neon", 6.0)
    text_out = backend.generate(shot, None, tmp_path / "a.mp4")
    assert text_out.is_file()
    assert seen["text"]["prompt"] == "robots boxing under neon"
    assert seen["text"]["num_frames"] == 145
    assert seen["text"]["height"] == 704
    assert seen["text"]["width"] == 1280
    assert seen["text"]["num_inference_steps"] == 3
    assert "image" not in seen["text"]

    keyframe = tmp_path / "key.png"
    keyframe.write_bytes(b"png")
    long_shot = CinemaShot(2, "Long", "", "one long round", 36.0)
    backend.generate(long_shot, keyframe, tmp_path / "b.mp4")
    assert seen["image"]["image"] == "image:key.png"
    assert seen["image"]["num_frames"] == 193
    assert seen["image"]["prompt"] == "one long round"


def test_director_selects_diffusers_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_index(tmp_path / "wan2.2-ti2v-5b-diffusers")
    monkeypatch.setattr("trendforge.cinema.wan_backend.diffusers_importable", lambda: True)
    monkeypatch.setattr("trendforge.cinema.wan_backend.cuda_available", lambda: True)
    director = CinemaDirector(CinemaConfig(dry_run=False, models_dir=tmp_path), ffmpeg="ffmpeg")
    assert isinstance(director.wan, DiffusersWanBackend)
    assert director.fallback_reason == ""


def test_director_passes_existing_keyframe(tmp_path: Path) -> None:
    ffmpeg = _ffmpeg()
    still = tmp_path / "still.png"
    from PIL import Image

    Image.new("RGB", (64, 64), (20, 40, 80)).save(still)
    seen: list[Path | None] = []

    class _Recording(DryRunWanBackend):
        def generate(self, shot: CinemaShot, keyframe: Path | None, dest: Path) -> Path:
            seen.append(keyframe)
            return super().generate(shot, keyframe, dest)

    episode = CinemaEpisode(
        title="Keyframe",
        topic="Robot Boxing",
        shots=[CinemaShot(1, "Hero", "", "chrome jab", 1.5, "hero", keyframe_path=str(still))],
    )
    cfg = CinemaConfig(dry_run=True, bridge_with_ltx=False, xfade_sec=0.0)
    director = CinemaDirector(cfg, wan=_Recording(ffmpeg), ffmpeg=ffmpeg)
    final = tmp_path / "final.mp4"
    result = director.run(episode, tmp_path / "work", final)
    assert seen == [still]
    assert result.final_path.exists()


def test_missing_keyframe_is_text_only(tmp_path: Path) -> None:
    from trendforge.cinema.shots import keyframe_for_shot

    shot = CinemaShot(1, "Hero", "", "prompt", keyframe_path=str(tmp_path / "missing.png"))
    assert keyframe_for_shot(shot) is None


def test_director_gpu_request_falls_back_and_still_renders(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ffmpeg = _ffmpeg()
    monkeypatch.setattr("trendforge.cinema.wan_backend.diffusers_importable", lambda: False)
    episode = robot_boxing_episode(clip_sec=2.0, act_sec=2.0, expand_acts=False)
    assert len(episode.shots) == 5
    cfg = CinemaConfig(dry_run=False, models_dir=tmp_path, bridge_with_ltx=False, xfade_sec=0.0)
    director = CinemaDirector(cfg, ffmpeg=ffmpeg)
    assert isinstance(director.wan, DryRunWanBackend)
    assert director.fallback_reason
    final = tmp_path / "final.mp4"
    result = director.run(episode, tmp_path / "work", final)
    assert result.final_path.exists()
    assert result.final_path.stat().st_size > 1000
    assert result.dry_run is True
    assert result.wan_impl == "dry_run"
    assert result.backend == "native_cinema"
    assert len(result.clip_paths) == 5


def test_render_episode_five_prompts_dry(tmp_path: Path) -> None:
    _ffmpeg()
    output = tmp_path / "final.mp4"
    code = render_main(
        [
            "--dry-run",
            "--topic",
            "Robot Boxing",
            "--prompt",
            "walk into the neon arena",
            "--prompt",
            "opening bell",
            "--prompt",
            "mid-round sparks",
            "--prompt",
            "knockdown",
            "--prompt",
            "decision",
            "--clip-sec",
            "2",
            "--xfade",
            "0",
            "--output",
            str(output),
            "--work-dir",
            str(tmp_path / "work"),
            "--models-dir",
            str(tmp_path / "models"),
        ]
    )
    assert code == 0
    assert output.exists()
    assert output.stat().st_size > 1000


def test_render_episode_robot_boxing_short_acts(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _ffmpeg()
    output = tmp_path / "final.mp4"
    code = render_main(
        [
            "--robot-boxing",
            "--dry-run",
            "--no-expand",
            "--clip-sec",
            "2",
            "--xfade",
            "0",
            "--output",
            str(output),
            "--work-dir",
            str(tmp_path / "work"),
            "--models-dir",
            str(tmp_path / "models"),
        ]
    )
    assert code == 0
    captured = capsys.readouterr().out
    assert "shots:    5" in captured
    assert "backend:  dry_run" in captured
    assert output.exists()


def test_render_episode_requires_five_prompts() -> None:
    code = render_main(["--dry-run", "--topic", "x", "--prompt", "only one", "--output", "ignored.mp4"])
    assert code == 2


def test_require_gpu_exits_when_unavailable(tmp_path: Path) -> None:
    code = render_main(
        [
            "--require-gpu",
            "--robot-boxing",
            "--no-expand",
            "--output",
            str(tmp_path / "final.mp4"),
            "--models-dir",
            str(tmp_path / "models"),
        ]
    )
    assert code == 3
    assert not (tmp_path / "final.mp4").exists()


def test_download_plan_mentions_diffusers_snapshot(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = download_main(["--models-dir", str(tmp_path)])
    assert code == 0
    out = capsys.readouterr().out
    assert "Wan-AI/Wan2.2-TI2V-5B-Diffusers" in out
    assert "model_index.json" in out
    assert "wan2.2-ti2v-5b-diffusers" in out
