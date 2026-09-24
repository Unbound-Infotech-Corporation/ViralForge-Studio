"""Cinema deliverables must carry voice and music, or fail the job."""

from __future__ import annotations

import math
import struct
import subprocess
import wave
from pathlib import Path

import pytest

from trendforge.bootstrap import AppDirs
from trendforge.domain.enums import (
    BackendKind,
    CaptionStyle,
    PipelineStage,
    TransitionStyle,
    VoiceEngine,
)
from trendforge.domain.models import GenerationRequest, Project, Shot, VideoScript
from trendforge.services.ffmpeg_tools import find_ffmpeg, has_audio_stream, run_ffmpeg
from trendforge.services.pipeline import ProductionPipeline
from trendforge.services.projects import ProjectStore
from trendforge.services.stitcher import (
    concat_cut,
    deliver_cinema_audio,
    lay_cinema_soundtrack,
    mux_soft_captions,
    probe_duration,
)
from trendforge.services.tts_engine import synthesize
from trendforge.settings import AppSettings


def _ffmpeg() -> str:
    ff = find_ffmpeg()
    if not ff:
        pytest.skip("ffmpeg not available")
    return ff


def _ffprobe_streams(path: Path, ffmpeg: str) -> str:
    from trendforge.services.ffmpeg_tools import find_ffprobe

    probe = find_ffprobe(ffmpeg)
    if not probe:
        pytest.skip("ffprobe not available")
    proc = subprocess.run(
        [
            probe,
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,codec_name",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def _color_clip(path: Path, ffmpeg: str, seconds: float = 0.45) -> Path:
    proc = run_ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x123456:s=320x240:d={seconds}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(path),
        ],
        ffmpeg,
    )
    assert proc.returncode == 0, proc.stderr[-500:]
    return path


def _tone(path: Path, seconds: float = 1.05, freq: float = 440.0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rate = 48000
    with wave.open(str(path), "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        frames = bytearray()
        for i in range(int(rate * seconds)):
            sample = int(8000 * math.sin(2 * math.pi * freq * (i / rate)))
            frames += struct.pack("<h", sample)
        handle.writeframes(frames)
    return path


def test_video_only_stitch_rejected_when_voice_or_music_required(tmp_path: Path) -> None:
    ffmpeg = _ffmpeg()
    silent = _color_clip(tmp_path / "silent.mp4", ffmpeg)
    joined = tmp_path / "joined.mp4"
    concat_cut([silent, silent], joined, ffmpeg)
    assert not has_audio_stream(joined, ffmpeg)
    streams = _ffprobe_streams(joined, ffmpeg)
    assert "audio" not in streams

    with pytest.raises(RuntimeError, match="no narration audio"):
        deliver_cinema_audio(
            [joined],
            tmp_path / "final.mp4",
            ffmpeg,
            transition=TransitionStyle.CUT,
            music=None,
            music_volume=0.12,
            captions_file=None,
            caption_style=CaptionStyle.NONE,
            codec="h264",
            require_voice=True,
            require_music=False,
        )
    assert not (tmp_path / "final.mp4").exists()

    with pytest.raises(RuntimeError, match="music bed"):
        deliver_cinema_audio(
            [joined],
            tmp_path / "final.mp4",
            ffmpeg,
            transition=TransitionStyle.CUT,
            music=None,
            music_volume=0.12,
            captions_file=None,
            caption_style=CaptionStyle.NONE,
            codec="h264",
            require_voice=False,
            require_music=True,
        )
    assert not (tmp_path / "final.mp4").exists()


def test_happy_path_mux_has_audio_stream(tmp_path: Path) -> None:
    ffmpeg = _ffmpeg()
    picture = _color_clip(tmp_path / "pic.mp4", ffmpeg, seconds=0.45)
    bridge = _color_clip(tmp_path / "bridge.mp4", ffmpeg, seconds=0.8)
    voice = _tone(tmp_path / "vo.wav", seconds=1.05, freq=440)
    music = _tone(tmp_path / "bed.wav", seconds=0.8, freq=110)
    laid = lay_cinema_soundtrack(
        [picture, bridge],
        [voice, None],
        tmp_path / "work",
        ffmpeg,
        require_voice=True,
    )
    assert probe_duration(laid[0], ffmpeg) >= 1.0
    assert has_audio_stream(laid[0], ffmpeg)
    assert has_audio_stream(laid[1], ffmpeg)

    final = tmp_path / "final.mp4"
    deliver_cinema_audio(
        laid,
        final,
        ffmpeg,
        transition=TransitionStyle.CROSSFADE,
        music=music,
        music_volume=0.2,
        captions_file=None,
        caption_style=CaptionStyle.NONE,
        codec="h264",
        require_voice=True,
        require_music=True,
    )
    streams = _ffprobe_streams(final, ffmpeg)
    assert "audio" in streams
    assert "h264" in streams


def test_soft_captions_keep_audio(tmp_path: Path) -> None:
    ffmpeg = _ffmpeg()
    picture = _color_clip(tmp_path / "pic.mp4", ffmpeg, seconds=0.4)
    voice = _tone(tmp_path / "vo.wav", seconds=0.4, freq=330)
    laid = lay_cinema_soundtrack(
        [picture],
        [voice],
        tmp_path / "work",
        ffmpeg,
        require_voice=True,
    )
    srt = tmp_path / "captions.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:00,400\nChagos\n", encoding="utf-8")
    dest = tmp_path / "with_subs.mp4"
    mux_soft_captions(laid[0], srt, dest, ffmpeg)
    streams = _ffprobe_streams(dest, ffmpeg)
    assert "audio" in streams
    assert "subtitle" in streams or "mov_text" in streams


def test_piper_failure_does_not_fall_back_when_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_args, **_kwargs):
        raise RuntimeError("piper boom")

    monkeypatch.setattr("trendforge.services.tts_engine.synthesize_piper", _boom)
    with pytest.raises(RuntimeError, match="piper boom"):
        synthesize(
            "hello from the islands",
            tmp_path / "vo.wav",
            VoiceEngine.PIPER,
            piper_model="missing.onnx",
            allow_fallback=False,
        )
    assert not (tmp_path / "vo.wav").exists()


def _dirs(root: Path) -> AppDirs:
    music = root / "music"
    music.mkdir(parents=True)
    _tone(music / "trendforge_bed.wav", seconds=1.2, freq=98)
    return AppDirs(
        root=root,
        projects=root / "projects",
        gallery=root / "gallery",
        cache=root / "cache",
        logs=root / "logs",
        models=root / "models",
        music=music,
        tmp=root / "tmp",
        settings_file=root / "settings.json",
    )


def _cinema_project(folder: Path) -> Project:
    request = GenerationRequest(
        topic="Chagos Islands",
        backend=BackendKind.NATIVE_CINEMA,
        model_id="viralforge_cinema",
        voice=VoiceEngine.PIPER,
        piper_voice="en_US-lessac-medium",
        captions=CaptionStyle.BOLD,
        transition=TransitionStyle.CROSSFADE,
        enable_voiceover=True,
        enable_captions=True,
        enable_music=True,
    )
    project = Project.create("Chagos", request, str(folder))
    project.script = VideoScript(
        title="The Chagos story",
        hook="A withheld colony.",
        summary="What happened to the islands.",
        youtube_description="",
        shots=[
            Shot(
                index=0,
                title="Chagos",
                narration="Britain kept the islands and removed the people.",
                visual_prompt="aerial ocean over a remote atoll",
                duration_sec=1.0,
            )
        ],
    )
    return project


def _solid_director(ffmpeg: str):
    from trendforge.cinema.config import CinemaConfig
    from trendforge.cinema.director import CinemaDirector
    from trendforge.cinema.ltx_backend import DryRunLtxBackend
    from trendforge.cinema.wan_backend import WanBackend
    from trendforge.services.ffmpeg_tools import run_ffmpeg

    class SolidWan(WanBackend):
        def __init__(self, exe: str) -> None:
            self.ffmpeg = exe

        def generate(self, shot, keyframe, dest):
            dest.parent.mkdir(parents=True, exist_ok=True)
            proc = run_ffmpeg(
                [
                    "-f",
                    "lavfi",
                    "-i",
                    f"color=c=0x123456:s=320x240:d={max(0.4, float(shot.duration_sec))}",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-an",
                    str(dest),
                ],
                self.ffmpeg,
            )
            assert proc.returncode == 0, proc.stderr
            return dest

    def factory(_self, cfg: CinemaConfig, exe: str) -> CinemaDirector:
        return CinemaDirector(cfg, wan=SolidWan(exe), ltx=DryRunLtxBackend(exe), ffmpeg=exe)

    return factory


def test_native_cinema_refuses_card_final(tmp_path: Path) -> None:
    dirs = _dirs(tmp_path / "app")
    store = ProjectStore(dirs.projects)
    pipeline = ProductionPipeline(AppSettings(cinema_dry_run=True), dirs, store)
    project = _cinema_project(tmp_path / "proj")
    with pytest.raises(RuntimeError, match="will not publish"):
        pipeline.run(project)
    assert project.stage is PipelineStage.FAILED
    assert not (Path(project.folder) / "output" / "final.mp4").exists()
    assert not (Path(project.folder) / "output" / "youtube.mp4").exists()


def test_native_cinema_tts_failure_marks_project_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*_args, **_kwargs):
        raise RuntimeError("piper executable not found")

    monkeypatch.setattr("trendforge.services.pipeline.synthesize", _boom)
    monkeypatch.setattr(
        "trendforge.services.pipeline.ProductionPipeline._cinema_director",
        _solid_director(_ffmpeg()),
    )
    dirs = _dirs(tmp_path / "app")
    store = ProjectStore(dirs.projects)
    pipeline = ProductionPipeline(AppSettings(cinema_dry_run=True, ffmpeg_path=_ffmpeg()), dirs, store)
    project = _cinema_project(tmp_path / "proj")
    with pytest.raises(RuntimeError, match="Voiceover failed"):
        pipeline.run(project)
    assert project.stage is PipelineStage.FAILED
    assert "Voiceover failed" in project.log_excerpt
    assert not (Path(project.folder) / "output" / "final.mp4").exists()
    assert not (Path(project.folder) / "output" / "youtube.mp4").exists()


def test_native_cinema_produce_muxes_voice_music_and_captions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fake_tts(text, dest, engine, piper_model="", allow_cloud=False, allow_fallback=True):
        return _tone(Path(dest), seconds=0.7, freq=523)

    monkeypatch.setattr("trendforge.services.pipeline.synthesize", _fake_tts)
    ffmpeg = _ffmpeg()
    monkeypatch.setattr(
        "trendforge.services.pipeline.ProductionPipeline._cinema_director",
        _solid_director(ffmpeg),
    )
    dirs = _dirs(tmp_path / "app")
    store = ProjectStore(dirs.projects)
    pipeline = ProductionPipeline(AppSettings(cinema_dry_run=True, ffmpeg_path=ffmpeg), dirs, store)
    project = _cinema_project(tmp_path / "proj")
    finished = pipeline.run(project)
    assert finished.stage is PipelineStage.DONE
    final = Path(finished.folder) / "output" / "final.mp4"
    youtube = Path(finished.folder) / "output" / "youtube.mp4"
    assert final.exists()
    assert youtube.exists()
    for path in (final, youtube):
        streams = _ffprobe_streams(path, ffmpeg)
        assert "audio" in streams
        assert "h264" in streams
    assert (Path(finished.folder) / "audio" / "vo_000.wav").exists()
    assert (Path(finished.folder) / "captions" / "captions.ass").exists()
    assert (Path(finished.folder) / "captions" / "captions.srt").exists()
    assert finished.script is not None
    assert finished.script.shots[0].audio_path
