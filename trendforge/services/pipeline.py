from __future__ import annotations

from pathlib import Path
from typing import Callable

from trendforge.bootstrap import AppDirs
from trendforge.domain.catalog import option_by_id
from trendforge.cinema.config import CinemaConfig
from trendforge.cinema.director import CinemaDirector, episode_from_script_shots
from trendforge.domain.enums import (
    BackendKind,
    ClipStatus,
    ContentFormat,
    PipelineStage,
    ShotSegmentKind,
    VoiceEngine,
)
from trendforge.domain.models import GenerationRequest, PipelineProgress, Project, Shot
from trendforge.logging_setup import get_logger
from trendforge.services.captions import write_ass, write_srt
from trendforge.services.cards import canvas_size, render_card
from trendforge.services.comfyui_client import ComfyUIClient
from trendforge.services.debug_trace import host_snapshot, log as dbg, validate_video
from trendforge.services.ffmpeg_tools import find_ffmpeg
from trendforge.services.maestro_client import (
    MaestroClient,
    MaestroError,
    director_start_unreachable,
)
from trendforge.services.maestro_detect import detect_maestro
from trendforge.services.music import ensure_bed_track
from trendforge.services.ollama_client import OllamaClient
from trendforge.services.projects import ProjectStore
from trendforge.services.clip_extractor import build_shot_clip, sync_shot_duration
from trendforge.services.review_validation import validate_review_request, validate_review_runtime
from trendforge.services.script_engine import assign_source_timestamps, generate_review_script, generate_script
from trendforge.services.trailer_allowlist import verify_trailer_url
from trendforge.services.stitcher import (
    assemble,
    extract_thumbnail,
    ken_burns_clip,
    probe_duration,
    youtube_encode,
)
from trendforge.services.tts_engine import synthesize
from trendforge.services.visual_policy import (
    STUDIO_NEGATIVE,
    director_pipeline_type as director_pipeline_type,
    director_visual_story as director_visual_story,
    footage_prompt as footage_prompt,
)
from trendforge.services.youtube_meta import render_thumbnail, write_sidecar
from trendforge.services.ytdlp_tools import download_source_video, source_research
from trendforge.settings import AppSettings


log = get_logger('pipeline')

ProgressCb = Callable[[PipelineProgress], None]


class CancelledError(RuntimeError):
    pass


class ProductionPipeline:
    def __init__(self, settings: AppSettings, dirs: AppDirs, store: ProjectStore) -> None:
        self.settings = settings
        self.dirs = dirs
        self.store = store

    def _check(self, cancelled: Callable[[], bool]) -> None:
        if cancelled():
            raise CancelledError("Cancelled by user")

    def _emit(self, cb: ProgressCb | None, **kwargs) -> None:
        if cb:
            cb(PipelineProgress(**kwargs))

    def resolve_backend(self, request: GenerationRequest) -> tuple[BackendKind, str, MaestroClient | None]:
        maestro = detect_maestro(self.settings.maestro_url, self.settings.pinokio_path)
        client = MaestroClient(maestro.running_url) if maestro.running_url else None
        if request.backend is BackendKind.REVIEW or request.model_id == "media_review":
            return BackendKind.REVIEW, "media_review", client
        if request.content_format is ContentFormat.REVIEW:
            return BackendKind.REVIEW, "media_review", client
        if request.source_url and request.backend in {BackendKind.AUTO, BackendKind.SOURCE_CLIP}:
            return BackendKind.SOURCE_CLIP, "source_clip", client
        if request.backend is BackendKind.SOURCE_CLIP:
            if not request.source_url:
                raise RuntimeError("Clip + narrate needs a YouTube URL in the topic field.")
            return BackendKind.SOURCE_CLIP, "source_clip", client
        if request.backend is BackendKind.NATIVE_CINEMA or request.model_id == "viralforge_cinema":
            return BackendKind.NATIVE_CINEMA, "viralforge_cinema", client
        if request.backend is BackendKind.AUTO or request.model_id == "auto":
            prefer_native = bool(getattr(self.settings, "prefer_native_cinema", True))
            if prefer_native:
                return BackendKind.NATIVE_CINEMA, "viralforge_cinema", client
            if client and client.ping():
                return BackendKind.MAESTRO_DIRECTOR, "maestro_director", client
            comfy = ComfyUIClient(self.settings.comfyui_url)
            if comfy.ping():
                return BackendKind.COMFYUI, "comfyui", client
            return BackendKind.QUICK_EXPLAINER, "quick_explainer", client
        if request.backend in {BackendKind.MAESTRO_DIRECTOR, BackendKind.MAESTRO_STUDIO}:
            if not client or not client.ping():
                raise MaestroError("Maestro is not running. Run start_maestro.bat (or launch.py in the Maestro app folder), then generate again.")
            return request.backend, request.model_id, client
        if request.backend is BackendKind.COMFYUI:
            comfy = ComfyUIClient(self.settings.comfyui_url)
            if not comfy.ping():
                raise RuntimeError("ComfyUI is not reachable. Start it, or pick Auto / Maestro.")
            return request.backend, request.model_id, client
        return request.backend, request.model_id, client

    def run(
        self,
        project: Project,
        on_progress: ProgressCb | None = None,
        cancelled: Callable[[], bool] | None = None,
        resume: bool = False,
    ) -> Project:
        cancelled = cancelled or (lambda: False)
        folder = Path(project.folder)
        req = project.request
        try:
            self._check(cancelled)
            backend, model_id, maestro = self.resolve_backend(req)
            if backend is BackendKind.REVIEW:
                review_check = validate_review_request(req)
                if not review_check.ok:
                    raise RuntimeError("\n".join(review_check.errors))
            extra = ""
            source_research_data = None
            trailer_verification = None
            if backend is BackendKind.REVIEW and req.trailer_url:
                self._emit(
                    on_progress,
                    stage=PipelineStage.RESEARCH,
                    percent=6,
                    message="Verifying official trailer source…",
                    cancellable=True,
                )
                trailer_verification = verify_trailer_url(req.trailer_url, req.allowlist_entry_id)
                if not trailer_verification.ok:
                    raise RuntimeError(trailer_verification.reason)
                self._emit(
                    on_progress,
                    stage=PipelineStage.RESEARCH,
                    percent=10,
                    message="Downloading official trailer…",
                    cancellable=True,
                )
                source_research_data = source_research(
                    req.trailer_url,
                    folder / "research",
                    download_video=True,
                )
                extra = source_research_data.context_text
            elif req.source_url:
                self._emit(on_progress, stage=PipelineStage.RESEARCH, percent=8, message="Analyzing source video…", cancellable=True)
                try:
                    download = req.backend is BackendKind.SOURCE_CLIP or req.backend is BackendKind.AUTO
                    source_research_data = source_research(
                        req.source_url,
                        folder / "research",
                        download_video=download,
                    )
                    extra = source_research_data.context_text
                except Exception as exc:
                    log.warning("Source analysis failed: %s", exc)
                    extra = f"Source URL: {req.source_url}"

            if project.script is None:
                self._emit(on_progress, stage=PipelineStage.SCRIPT, percent=18, message="Writing script and shot list…", cancellable=True)
                ollama = OllamaClient(self.settings.ollama_url)
                if backend is BackendKind.REVIEW:
                    project.script = generate_review_script(
                        req,
                        extra_context=extra,
                        ollama=ollama if ollama.status().running else None,
                        ollama_model=self.settings.ollama_model,
                        attribution=trailer_verification.attribution if trailer_verification else None,
                        channel_name=req.channel_name or self.settings.channel_name,
                        cta=req.channel_cta or self.settings.channel_cta,
                    )
                    if source_research_data and project.script:
                        from trendforge.services.ytdlp_tools import parse_vtt_text

                        cues = []
                        for path in (folder / "research").glob("*.vtt"):
                            cues = parse_vtt_text(path.read_text(encoding="utf-8", errors="ignore"))
                            break
                        assign_source_timestamps(
                            project.script,
                            duration_sec=source_research_data.duration_sec,
                            cues=cues,
                        )
                    runtime_check = validate_review_runtime(project.script) if project.script else None
                    if runtime_check and not runtime_check.ok:
                        raise RuntimeError("\n".join(runtime_check.errors))
                else:
                    project.script = generate_script(
                        req.topic,
                        req.style,
                        req.length,
                        extra_context=extra,
                        ollama=ollama if ollama.status().running else None,
                        ollama_model=self.settings.ollama_model,
                        content_format=req.content_format,
                        brand=req.brand_voice,
                        channel_name=req.channel_name or self.settings.channel_name,
                        cta=req.channel_cta or self.settings.channel_cta,
                        episode_index=req.episode_index,
                        episode_count=req.episode_count,
                        series_title=req.series_title or self.settings.series_title,
                        source_clip_mode=backend is BackendKind.SOURCE_CLIP,
                    )
                    if backend is BackendKind.SOURCE_CLIP and project.script:
                        from trendforge.services.ytdlp_tools import parse_vtt_text

                        cues = []
                        for path in (folder / "research").glob("*.vtt"):
                            cues = parse_vtt_text(path.read_text(encoding="utf-8", errors="ignore"))
                            break
                        duration = source_research_data.duration_sec if source_research_data else 0.0
                        assign_source_timestamps(project.script, duration_sec=duration, cues=cues)
                project.stage = PipelineStage.SCRIPT
                self.store.save(project)

            if req.content_format is ContentFormat.SEASON and project.script and project.script.season:
                self._emit(on_progress, stage=PipelineStage.FINALIZE, percent=90, message="Writing season bible…")
                folder = Path(project.folder)
                write_sidecar(
                    project.script,
                    req.topic,
                    folder / "output" / "youtube_description.txt",
                    req,
                )
                project.stage = PipelineStage.DONE
                self.store.save(project)
                self._emit(on_progress, stage=PipelineStage.DONE, percent=100, message="Season planned — pick an episode and Generate")
                return project

            self._check(cancelled)
            log.info("Using backend=%s model=%s", backend, model_id)
            self._emit(
                on_progress,
                stage=PipelineStage.GENERATE,
                percent=28,
                message=f"Generating clips ({backend.value})…",
                clip_total=len(project.script.shots) if project.script else 0,
                cancellable=True,
            )

            if backend is BackendKind.NATIVE_CINEMA:
                self._run_native_cinema(project, on_progress, cancelled)
            if backend is BackendKind.MAESTRO_DIRECTOR:
                try:
                    self._run_maestro_director(project, maestro, on_progress, cancelled)
                except MaestroError as exc:
                    if str(exc) == "Cancelled":
                        raise CancelledError("Cancelled by user") from exc
                    if director_start_unreachable(exc):
                        log.warning(
                            "Director API did not start (%s); generating shots with Maestro Studio T2V",
                            exc,
                        )
                        self._emit(
                            on_progress,
                            stage=PipelineStage.GENERATE,
                            percent=32,
                            message="Director API missing — generating shots with LTX…",
                            cancellable=True,
                        )
                        self._run_maestro_studio(project, maestro, "ltx25_distilled", on_progress, cancelled)
                    else:
                        log.warning("Director path failed (%s)", exc)
                        raise MaestroError(
                            f"Maestro Director did not produce footage: {exc}. "
                            "Pick Quick Explainer for readable cards, or fix Director and retry. "
                            "TrendForge will not replace footage with a blank color plate."
                        ) from exc
            elif backend is BackendKind.MAESTRO_STUDIO:
                try:
                    self._run_maestro_studio(project, maestro, model_id, on_progress, cancelled)
                except MaestroError as exc:
                    if str(exc) == "Cancelled":
                        raise CancelledError("Cancelled by user") from exc
                    log.warning("Studio path failed (%s)", exc)
                    raise MaestroError(
                        f"Maestro Studio did not produce footage: {exc}. "
                        "TrendForge will not replace it with a blank color plate."
                    ) from exc
            elif backend is BackendKind.COMFYUI:
                try:
                    self._run_comfy(project, on_progress, cancelled)
                except Exception as exc:
                    if req.backend is BackendKind.COMFYUI:
                        raise
                    log.warning("ComfyUI failed (%s); using Quick Explainer cards", exc)
                    self._run_quick(project, on_progress, cancelled)
            elif backend is BackendKind.SOURCE_CLIP:
                self._run_source_clip(
                    project,
                    on_progress,
                    cancelled,
                    source_research_data,
                )
            elif backend is BackendKind.REVIEW:
                self._run_review(
                    project,
                    on_progress,
                    cancelled,
                    source_research_data,
                )
            else:
                self._run_quick(project, on_progress, cancelled)

            self._check(cancelled)
            self._finalize(project, on_progress)
            project.stage = PipelineStage.DONE
            self.store.save(project)
            self._emit(on_progress, stage=PipelineStage.DONE, percent=100, message="Video ready")
            return project
        except CancelledError:
            project.stage = PipelineStage.CANCELLED
            self.store.save(project)
            self._emit(on_progress, stage=PipelineStage.CANCELLED, percent=0, message="Cancelled", resumable=True)
            raise
        except Exception as exc:
            project.stage = PipelineStage.FAILED
            project.log_excerpt = str(exc)
            self.store.save(project)
            self._emit(on_progress, stage=PipelineStage.FAILED, percent=0, message=str(exc), resumable=True)
            raise

    def _run_quick(self, project: Project, on_progress: ProgressCb | None, cancelled: Callable[[], bool]) -> None:
        assert project.script
        ffmpeg = find_ffmpeg(self.settings.ffmpeg_path)
        folder = Path(project.folder)
        clips_dir = folder / "clips"
        audio_dir = folder / "audio"
        size = canvas_size(project.request.aspect)
        shots = project.script.shots
        total = len(shots)
        if project.request.enable_intro:
            intro = Shot(index=-1, title=project.script.title, narration=project.script.hook or project.request.topic,
                         visual_prompt="intro", duration_sec=3.5)
            shots_full = [intro, *shots]
        else:
            shots_full = list(shots)
        if project.request.enable_outro:
            cta = project.request.channel_cta or self.settings.channel_cta
            shots_full.append(
                Shot(index=999, title="Next up", narration=cta,
                     visual_prompt="outro", duration_sec=3.5)
            )

        clip_paths: list[Path] = []
        usable_shots: list[Shot] = []
        for i, shot in enumerate(shots_full):
            self._check(cancelled)
            pct = 30 + int(50 * (i / max(len(shots_full), 1)))
            self._emit(
                on_progress,
                stage=PipelineStage.GENERATE,
                percent=pct,
                message=f"Rendering shot {i + 1}/{len(shots_full)}: {shot.title}",
                clip_index=i + 1,
                clip_total=len(shots_full),
                cancellable=True,
            )
            img = clips_dir / f"card_{i:03d}.png"
            kicker = "INTRO" if shot.index < 0 else "OUTRO" if shot.index >= 999 else f"SCENE {i}"
            render_card(
                img,
                kicker,
                shot.title,
                shot.narration,
                project.request.aspect,
                project.request.style,
                paint_copy=True,
            )
            audio = None
            if project.request.enable_voiceover and shot.narration:
                try:
                    piper = ""
                    if project.request.voice is VoiceEngine.PIPER:
                        from trendforge.services.installer import piper_model_path

                        found = piper_model_path(self.dirs, project.request.piper_voice)
                        piper = str(found) if found else ""
                    audio = synthesize(
                        shot.narration,
                        audio_dir / f"vo_{i:03d}.wav",
                        project.request.voice,
                        piper_model=piper,
                        allow_cloud=self.settings.paid_fallbacks_enabled,
                    )
                except Exception as exc:
                    log.warning("TTS failed on shot %s: %s", i, exc)
            dest = clips_dir / f"clip_{i:03d}.mp4"
            if dest.exists() and dest.stat().st_size > 1000 and shot.status is ClipStatus.DONE:
                clip_paths.append(dest)
                usable_shots.append(shot)
                continue
            duration = shot.duration_sec
            if audio and Path(audio).exists():
                try:
                    duration = max(duration, probe_duration(Path(audio), ffmpeg) + 0.35)
                    shot.duration_sec = duration
                except Exception:
                    pass
            ken_burns_clip(img, dest, duration, size, ffmpeg, audio)
            shot.clip_path = str(dest)
            shot.image_path = str(img)
            shot.audio_path = str(audio) if audio else ""
            shot.status = ClipStatus.DONE
            clip_paths.append(dest)
            usable_shots.append(shot)
            self.store.save(project)

        self._stitch(project, clip_paths, usable_shots, ffmpeg, on_progress)

    def _run_source_clip(
        self,
        project: Project,
        on_progress: ProgressCb | None,
        cancelled: Callable[[], bool],
        research=None,
    ) -> None:
        assert project.script
        if not project.request.source_url:
            raise RuntimeError("Clip + narrate requires a YouTube URL.")
        ffmpeg = find_ffmpeg(self.settings.ffmpeg_path)
        folder = Path(project.folder)
        research_dir = folder / "research"
        source = research.video_path if research and research.video_path else None
        if source is None or not source.exists():
            self._emit(
                on_progress,
                stage=PipelineStage.GENERATE,
                percent=30,
                message="Downloading source video…",
                cancellable=True,
            )
            source = download_source_video(project.request.source_url, research_dir)
        duration = research.duration_sec if research else probe_duration(source, ffmpeg)
        from trendforge.services.ytdlp_tools import parse_vtt_text

        cues = []
        for path in research_dir.glob("*.vtt"):
            cues = parse_vtt_text(path.read_text(encoding="utf-8", errors="ignore"))
            break
        assign_source_timestamps(project.script, duration_sec=duration, cues=cues)
        self.store.save(project)

        clips_dir = folder / "clips"
        audio_dir = folder / "audio"
        size = canvas_size(project.request.aspect)
        shots = list(project.script.shots)
        clip_paths: list[Path] = []
        usable_shots: list[Shot] = []
        total = len(shots)
        for i, shot in enumerate(shots):
            self._check(cancelled)
            pct = 30 + int(50 * (i / max(total, 1)))
            self._emit(
                on_progress,
                stage=PipelineStage.GENERATE,
                percent=pct,
                message=f"Clipping shot {i + 1}/{total}: {shot.title}",
                clip_index=i + 1,
                clip_total=total,
                cancellable=True,
            )
            dest = clips_dir / f"clip_{i:03d}.mp4"
            if dest.exists() and dest.stat().st_size > 1000 and shot.status is ClipStatus.DONE:
                clip_paths.append(dest)
                usable_shots.append(shot)
                continue
            start = max(0.0, shot.source_start_sec)
            end = shot.source_end_sec if shot.source_end_sec > start else start + max(shot.duration_sec, 4.0)
            audio = None
            if project.request.enable_voiceover and shot.narration:
                try:
                    piper = ""
                    if project.request.voice is VoiceEngine.PIPER:
                        from trendforge.services.installer import piper_model_path

                        found = piper_model_path(self.dirs, project.request.piper_voice)
                        piper = str(found) if found else ""
                    audio = synthesize(
                        shot.narration,
                        audio_dir / f"vo_{i:03d}.wav",
                        project.request.voice,
                        piper_model=piper,
                        allow_cloud=self.settings.paid_fallbacks_enabled,
                    )
                    end = sync_shot_duration(start, end, Path(audio), ffmpeg)
                except Exception as exc:
                    log.warning("TTS failed on shot %s: %s", i, exc)
            build_shot_clip(source, start, end, Path(audio) if audio else None, dest, ffmpeg, size)
            shot.clip_path = str(dest)
            shot.audio_path = str(audio) if audio else ""
            shot.source_start_sec = start
            shot.source_end_sec = end
            shot.duration_sec = round(end - start, 2)
            shot.status = ClipStatus.DONE
            clip_paths.append(dest)
            usable_shots.append(shot)
            self.store.save(project)
        self._stitch(project, clip_paths, usable_shots, ffmpeg, on_progress)

    def _synthesize_shot_audio(
        self,
        project: Project,
        shot: Shot,
        index: int,
        audio_dir: Path,
    ) -> Path | None:
        if not project.request.enable_voiceover or not shot.narration:
            return None
        piper = ""
        if project.request.voice is VoiceEngine.PIPER:
            from trendforge.services.installer import piper_model_path

            found = piper_model_path(self.dirs, project.request.piper_voice)
            piper = str(found) if found else ""
        return synthesize(
            shot.narration,
            audio_dir / f"vo_{index:03d}.wav",
            project.request.voice,
            piper_model=piper,
            allow_cloud=self.settings.paid_fallbacks_enabled,
        )

    def _render_commentary_shot(
        self,
        project: Project,
        shot: Shot,
        index: int,
        clips_dir: Path,
        audio_dir: Path,
        size: tuple[int, int],
        ffmpeg: str,
        kicker: str,
    ) -> Path:
        img = clips_dir / f"card_{index:03d}.png"
        render_card(
            img,
            kicker,
            shot.title,
            shot.narration,
            project.request.aspect,
            project.request.style,
            paint_copy=True,
        )
        audio = None
        try:
            audio = self._synthesize_shot_audio(project, shot, index, audio_dir)
        except Exception as exc:
            log.warning("TTS failed on shot %s: %s", index, exc)
        dest = clips_dir / f"clip_{index:03d}.mp4"
        duration = shot.duration_sec
        if audio and Path(audio).exists():
            try:
                duration = max(duration, probe_duration(Path(audio), ffmpeg) + 0.35)
                shot.duration_sec = duration
            except Exception:
                pass
        ken_burns_clip(img, dest, duration, size, ffmpeg, Path(audio) if audio else None)
        shot.clip_path = str(dest)
        shot.image_path = str(img)
        shot.audio_path = str(audio) if audio else ""
        return dest

    def _run_review(
        self,
        project: Project,
        on_progress: ProgressCb | None,
        cancelled: Callable[[], bool],
        research=None,
    ) -> None:
        assert project.script
        req = project.request
        check = validate_review_request(req)
        if not check.ok:
            raise RuntimeError("\n".join(check.errors))
        runtime_check = validate_review_runtime(project.script)
        if not runtime_check.ok:
            raise RuntimeError("\n".join(runtime_check.errors))

        ffmpeg = find_ffmpeg(self.settings.ffmpeg_path)
        folder = Path(project.folder)
        research_dir = folder / "research"
        trailer = research.video_path if research and research.video_path else None
        if trailer is None or not trailer.exists():
            trailer = download_source_video(req.trailer_url, research_dir)

        gameplay = Path(req.gameplay_path.strip()) if req.gameplay_path.strip() else None
        if gameplay and not gameplay.exists():
            gameplay = None

        clips_dir = folder / "clips"
        audio_dir = folder / "audio"
        size = canvas_size(project.request.aspect)
        shots = list(project.script.shots)
        clip_paths: list[Path] = []
        usable_shots: list[Shot] = []
        total = len(shots)

        for i, shot in enumerate(shots):
            self._check(cancelled)
            pct = 30 + int(50 * (i / max(total, 1)))
            self._emit(
                on_progress,
                stage=PipelineStage.GENERATE,
                percent=pct,
                message=f"Review shot {i + 1}/{total}: {shot.title}",
                clip_index=i + 1,
                clip_total=total,
                cancellable=True,
            )
            dest = clips_dir / f"clip_{i:03d}.mp4"
            if dest.exists() and dest.stat().st_size > 1000 and shot.status is ClipStatus.DONE:
                clip_paths.append(dest)
                usable_shots.append(shot)
                continue

            kind = shot.segment_kind
            if kind in {ShotSegmentKind.COMMENTARY, ShotSegmentKind.TITLE_CARD, ShotSegmentKind.CREDITS}:
                kicker = {
                    ShotSegmentKind.TITLE_CARD: "REVIEW",
                    ShotSegmentKind.CREDITS: "CREDITS",
                }.get(kind, f"MY TAKE {i + 1}")
                dest = self._render_commentary_shot(project, shot, i, clips_dir, audio_dir, size, ffmpeg, kicker)
            elif kind is ShotSegmentKind.GAMEPLAY and gameplay:
                start = max(0.0, shot.source_start_sec)
                end = shot.source_end_sec if shot.source_end_sec > start else start + min(shot.duration_sec, 12.0)
                audio = None
                try:
                    audio = self._synthesize_shot_audio(project, shot, i, audio_dir)
                    if audio:
                        end = sync_shot_duration(start, end, Path(audio), ffmpeg)
                except Exception as exc:
                    log.warning("TTS failed on gameplay shot %s: %s", i, exc)
                build_shot_clip(gameplay, start, end, Path(audio) if audio else None, dest, ffmpeg, size)
                shot.clip_path = str(dest)
                shot.audio_path = str(audio) if audio else ""
            elif kind is ShotSegmentKind.TRAILER:
                start = max(0.0, shot.source_start_sec)
                end = shot.source_end_sec if shot.source_end_sec > start else start + min(shot.duration_sec, 5.0)
                end = min(end, start + 6.0)
                audio = None
                try:
                    audio = self._synthesize_shot_audio(project, shot, i, audio_dir)
                    if audio:
                        end = max(end, min(start + 6.0, sync_shot_duration(start, end, Path(audio), ffmpeg)))
                except Exception as exc:
                    log.warning("TTS failed on trailer shot %s: %s", i, exc)
                build_shot_clip(trailer, start, end, Path(audio) if audio else None, dest, ffmpeg, size)
                shot.clip_path = str(dest)
                shot.audio_path = str(audio) if audio else ""
                shot.source_start_sec = start
                shot.source_end_sec = end
            else:
                dest = self._render_commentary_shot(project, shot, i, clips_dir, audio_dir, size, ffmpeg, f"SCENE {i + 1}")

            shot.duration_sec = round(probe_duration(dest, ffmpeg), 2)
            shot.status = ClipStatus.DONE
            clip_paths.append(dest)
            usable_shots.append(shot)
            self.store.save(project)

        final_runtime = validate_review_runtime(project.script)
        if not final_runtime.ok:
            raise RuntimeError("\n".join(final_runtime.errors))
        self._stitch(project, clip_paths, usable_shots, ffmpeg, on_progress)

    def _stitch(
        self,
        project: Project,
        clip_paths: list[Path],
        shots: list[Shot],
        ffmpeg: str,
        on_progress: ProgressCb | None,
    ) -> None:
        assert project.script
        folder = Path(project.folder)
        self._emit(on_progress, stage=PipelineStage.STITCH, percent=82, message="Stitching and mixing…", cancellable=True)
        size = canvas_size(project.request.aspect)
        ass = None
        if project.request.enable_captions:
            ass = write_ass(shots, folder / "captions" / "captions.ass", size[0], size[1], project.request.captions)
            write_srt(shots, folder / "captions" / "captions.srt")
        music = None
        if project.request.enable_music:
            music = ensure_bed_track(self.dirs)
        out = folder / "output" / "final.mp4"
        assemble(
            clip_paths,
            out,
            ffmpeg,
            project.request.transition,
            music,
            project.request.music_volume,
            ass,
            project.request.captions,
            project.request.codec,
        )
        project.output_path = str(out)

    def _finalize(self, project: Project, on_progress: ProgressCb | None) -> None:
        assert project.script
        ffmpeg = find_ffmpeg(self.settings.ffmpeg_path)
        folder = Path(project.folder)
        self._emit(on_progress, stage=PipelineStage.FINALIZE, percent=94, message="Writing YouTube metadata…")
        thumb = folder / "output" / "thumb.jpg"
        if project.output_path:
            try:
                extract_thumbnail(Path(project.output_path), thumb, ffmpeg)
                project.thumbnail_path = str(thumb)
            except Exception as exc:
                log.warning("Thumbnail failed: %s", exc)
        write_sidecar(
            project.script,
            project.request.topic,
            folder / "output" / "youtube_description.txt",
            project.request,
        )
        try:
            yt_thumb = folder / "output" / "youtube_thumb.png"
            render_thumbnail(project.script, yt_thumb, project.request)
        except Exception as exc:
            log.warning("YouTube thumb card failed: %s", exc)

    def _run_native_cinema(
        self,
        project: Project,
        on_progress: ProgressCb | None,
        cancelled: Callable[[], bool],
    ) -> None:
        """Wan 2.2 I2V + LTX-2.5 bridges + stitch — no Maestro app."""
        assert project.script
        ffmpeg = find_ffmpeg(self.settings.ffmpeg_path)
        folder = Path(project.folder)
        work = folder / "cinema_work"
        out_dir = folder / "output"
        work.mkdir(parents=True, exist_ok=True)
        out_dir.mkdir(parents=True, exist_ok=True)
        final = out_dir / "final.mp4"

        shots_payload = [
            {
                "title": s.title or "",
                "narration": s.narration or "",
                "visual_prompt": s.visual_prompt or s.narration or "",
                "duration_sec": float(s.duration_sec or 4.0),
                "kind": "hero",
            }
            for s in project.script.shots
        ]
        title = project.script.title or project.request.topic or "Episode"
        topic = project.request.topic or title
        cfg = CinemaConfig.from_settings(self.settings)
        self._emit(
            on_progress,
            stage=PipelineStage.GENERATE,
            percent=20,
            message="ViralForge Cinema: rendering shots",
            clip_total=len(shots_payload),
            cancellable=True,
        )
        self._check(cancelled)
        episode = episode_from_script_shots(str(title), str(topic), shots_payload)
        director = CinemaDirector(cfg, ffmpeg=ffmpeg)
        result = director.run(episode, work, final)

        heroes = [p for p in result.clip_paths if not p.name.startswith("bridge_")]
        for shot, clip in zip(project.script.shots, heroes):
            shot.clip_path = str(clip)
            shot.status = ClipStatus.DONE

        self._emit(
            on_progress,
            stage=PipelineStage.STITCH,
            percent=85,
            message=f"Stitched {len(result.clip_paths)} cinema clips",
            cancellable=False,
        )
        try:
            yt = out_dir / "youtube.mp4"
            codec = getattr(project.request, "codec", "h264") or "h264"
            youtube_encode(result.final_path, yt, ffmpeg, codec)
            project.output_path = str(yt if yt.exists() else result.final_path)
        except Exception as exc:
            project.output_path = str(result.final_path)
            log.warning("native cinema youtube encode warn: %s", exc)


    def _run_maestro_director(
        self,
        project: Project,
        client: MaestroClient | None,
        on_progress: ProgressCb | None,
        cancelled: Callable[[], bool],
    ) -> None:
        if client is None:
            raise MaestroError("Maestro is not running")
        assert project.script
        option = option_by_id(project.request.model_id)
        hint = (option.maestro_type_hint if option else "") or "ltx2"
        video_model = (
            client.pick_story_video_model(hint)
            or client.pick_story_video_model("ltx")
            or "ltx2_22B_distilled_1_1"
        )
        image_model = client.pick_image_model() or ""
        visual_story = director_visual_story(
            project.script,
            project.request.topic,
            project.request.content_format,
        )
        dbg("prompt_received", path="director", prompt=visual_story[:800])
        host_snapshot("before_director_start")
        pipeline_type = director_pipeline_type(project.request.content_format)
        total = sum(s.duration_sec for s in project.script.shots)
        params = {
            "pipeline_type": pipeline_type,
            "skill_type": "short_film",
            "story_description": visual_story,
            "scene_description": visual_story,
            "concept": project.request.topic,
            "visual_style": "cinematic",
            "style": "cinematic",
            "narrative_mode": False,
            "platform": "shorts" if project.request.content_format is ContentFormat.SHORTS else "general",
            "target_duration": int(total),
            "auto_mode": True,
            "seamless": False,
            "video_model": video_model,
            "image_model": image_model,
            "shot_image_guidance": "prompt_only",
            "resolution": _maestro_resolution(project.request.aspect),
            "negative_prompt": STUDIO_NEGATIVE,
        }
        log.info(
            "Director url=%s video_model=%s image_model=%s workflow=%s policy=prompt_only",
            client.base_url,
            video_model,
            image_model or "(none)",
            pipeline_type,
        )
        self._emit(on_progress, stage=PipelineStage.GENERATE, percent=32, message="Starting Maestro Director…", cancellable=True)
        pid = client.start_director(params)
        project.maestro_pipeline_id = pid
        self.store.save(project)

        def prog(msg: str, pct: int) -> None:
            self._emit(
                on_progress,
                stage=PipelineStage.GENERATE,
                percent=min(80, 32 + int(pct * 0.48)),
                message=f"Director: {msg}",
                cancellable=True,
            )

        status = client.wait_director(pid, on_progress=prog, cancelled=cancelled)
        outputs = status.get("output_files") or status.get("output_files") or []
        if not outputs:
            raise MaestroError("Director finished without output files")
        folder = Path(project.folder) / "output"
        folder.mkdir(parents=True, exist_ok=True)
        last = None
        for name in outputs:
            dest = folder / Path(str(name)).name
            try:
                client.download_file(str(name), dest)
                last = dest
            except MaestroError:
                # Maybe it's already a local path inside Maestro
                src = Path(str(name))
                if src.exists():
                    dest.write_bytes(src.read_bytes())
                    last = dest
        if last is None:
            raise MaestroError("Could not copy Director outputs")
        # If Director already combined, treat as final then still wrap metadata
        project.output_path = str(last)
        ffmpeg = find_ffmpeg(self.settings.ffmpeg_path)
        final = Path(project.folder) / "output" / "final.mp4"
        from trendforge.services.stitcher import youtube_encode

        youtube_encode(last, final, ffmpeg, project.request.codec)
        project.output_path = str(final)
        check = validate_video(final, ffmpeg)
        dbg("director_output_validation", **check)
        if not check.get("pass"):
            raise MaestroError(
                f"Director output failed validation: {check.get('fail_reason')}"
            )

    def _run_maestro_studio(
        self,
        project: Project,
        client: MaestroClient | None,
        model_id: str,
        on_progress: ProgressCb | None,
        cancelled: Callable[[], bool],
    ) -> None:
        if client is None:
            raise MaestroError("Maestro is not running")
        assert project.script
        option = option_by_id(model_id)
        hint = (option.maestro_type_hint if option else model_id) or "ltx2"
        model_type = (
            client.pick_story_video_model(hint)
            or client.pick_story_video_model("ltx")
            or client.match_model("ltx")
        )
        if not model_type:
            raise MaestroError(
                "No story video model found in Maestro. Install LTX-2 Distilled, then retry."
            )
        ffmpeg = find_ffmpeg(self.settings.ffmpeg_path)
        folder = Path(project.folder)
        dbg("studio_start", model_type=model_type, shots=len(project.script.shots))
        host_snapshot("before_studio_shots")
        clips: list[Path] = []
        done_shots: list[Shot] = []
        for i, shot in enumerate(project.script.shots):
            self._check(cancelled)
            if shot.status is ClipStatus.DONE and shot.clip_path and Path(shot.clip_path).exists():
                clips.append(Path(shot.clip_path))
                done_shots.append(shot)
                continue
            self._emit(
                on_progress,
                stage=PipelineStage.GENERATE,
                percent=30 + int(50 * i / max(len(project.script.shots), 1)),
                message=f"Maestro generating shot {i + 1}/{len(project.script.shots)}",
                clip_index=i + 1,
                clip_total=len(project.script.shots),
                cancellable=True,
            )
            prompt = footage_prompt(shot, project.request.topic)
            dbg(
                "prompt_received",
                shot=i,
                prompt=prompt[:400],
                model_type=model_type,
            )
            payload = {
                "prompt": prompt,
                "negative_prompt": STUDIO_NEGATIVE,
                "model_type": model_type,
                "resolution": _maestro_resolution(project.request.aspect),
            }
            result = client.generate(payload)
            job_id = str(result.get("job_id") or "")
            if job_id:
                project.maestro_job_ids.append(job_id)
                status = client.wait_job(job_id, cancelled=cancelled)
                files = status.get("output_files") or []
            else:
                files = result.get("output_files") or []
            if not files:
                raise MaestroError(f"No output for shot {i}")
            dest = folder / "clips" / f"maestro_{i:03d}{Path(str(files[0])).suffix or '.mp4'}"
            dbg("file_write_start", dest=str(dest), remote=str(files[0]))
            dest.parent.mkdir(parents=True, exist_ok=True)
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
                dest=str(dest),
                size_bytes=dest.stat().st_size if dest.exists() else 0,
            )
            shot.clip_path = str(dest)
            shot.status = ClipStatus.DONE
            check = validate_video(dest, ffmpeg)
            dbg("studio_shot_validation", shot=i, **check)
            if not check.get("pass"):
                raise MaestroError(
                    f"Studio shot {i} failed output validation: {check.get('fail_reason')}"
                )
            clips.append(dest)
            done_shots.append(shot)
            self.store.save(project)
        self._stitch(project, clips, done_shots, ffmpeg, on_progress)

    def _run_comfy(
        self,
        project: Project,
        on_progress: ProgressCb | None,
        cancelled: Callable[[], bool],
    ) -> None:
        assert project.script
        client = ComfyUIClient(self.settings.comfyui_url)
        workflow_path = Path(__file__).resolve().parent.parent / "assets" / "comfy" / "t2v_workflow.json"
        ffmpeg = find_ffmpeg(self.settings.ffmpeg_path)
        folder = Path(project.folder)
        clips: list[Path] = []
        if workflow_path.exists():
            base = client.load_workflow_file(workflow_path)
        else:
            raise RuntimeError(
                "No ComfyUI workflow found. Add assets/comfy/t2v_workflow.json or use Quick Explainer / Maestro."
            )
        for i, shot in enumerate(project.script.shots):
            self._check(cancelled)
            wf = _inject_prompt(base, footage_prompt(shot, project.request.topic))
            pid = client.submit_prompt(wf)
            hist = client.wait(pid, cancelled=cancelled)
            files = client.download_outputs(hist, folder / "clips")
            if not files:
                raise RuntimeError("ComfyUI produced no files")
            shot.clip_path = str(files[0])
            shot.status = ClipStatus.DONE
            clips.append(files[0])
            self.store.save(project)
        self._stitch(project, clips, project.script.shots, ffmpeg, on_progress)

    def regenerate_shot(
        self,
        project: Project,
        index: int,
        on_progress: ProgressCb | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> Project:
        cancelled = cancelled or (lambda: False)
        if not project.script or not (0 <= index < len(project.script.shots)):
            raise ValueError("Invalid shot index")
        shot = project.script.shots[index]
        shot.status = ClipStatus.PENDING
        ffmpeg = find_ffmpeg(self.settings.ffmpeg_path)
        folder = Path(project.folder)
        size = canvas_size(project.request.aspect)
        self._emit(on_progress, stage=PipelineStage.GENERATE, percent=20, message=f"Regenerating shot {index + 1}", cancellable=True)
        img = folder / "clips" / f"card_{index:03d}.png"
        render_card(
            img,
            f"SCENE {index + 1}",
            shot.title,
            shot.narration,
            project.request.aspect,
            project.request.style,
            paint_copy=True,
        )
        audio = None
        if project.request.enable_voiceover and shot.narration:
            piper = ""
            if project.request.voice is VoiceEngine.PIPER:
                from trendforge.services.installer import piper_model_path

                found = piper_model_path(self.dirs, project.request.piper_voice)
                piper = str(found) if found else ""
            audio = synthesize(
                shot.narration,
                folder / "audio" / f"vo_{index:03d}.wav",
                project.request.voice,
                piper_model=piper,
                allow_cloud=self.settings.paid_fallbacks_enabled,
            )
        dest = folder / "clips" / f"clip_{index:03d}.mp4"
        ken_burns_clip(img, dest, shot.duration_sec, size, ffmpeg, audio)
        shot.clip_path = str(dest)
        shot.status = ClipStatus.DONE
        clips = [Path(s.clip_path) for s in project.script.shots if s.clip_path and Path(s.clip_path).exists()]
        if clips:
            self._stitch(project, clips, [s for s in project.script.shots if s.clip_path], ffmpeg, on_progress)
            self._finalize(project, on_progress)
        self.store.save(project)
        self._emit(on_progress, stage=PipelineStage.DONE, percent=100, message="Shot regenerated")
        return project


def _maestro_resolution(aspect) -> str:
    from trendforge.domain.enums import AspectRatio

    if aspect is AspectRatio.VERTICAL:
        return "720x1280"
    if aspect is AspectRatio.SQUARE:
        return "720x720"
    return "1280x720"


def _inject_prompt(workflow: dict, prompt: str) -> dict:
    import copy

    wf = copy.deepcopy(workflow)
    # Comfy API format: {node_id: {inputs: {text: ...}}}
    nodes = wf.get("prompt") or wf
    if isinstance(nodes, dict):
        for node in nodes.values():
            if not isinstance(node, dict):
                continue
            inputs = node.get("inputs") or {}
            if "text" in inputs and node.get("class_type") in {"CLIPTextEncode", "CLIPTextEncodeSDXL"}:
                if "blurry" not in str(inputs.get("text", "")).lower():
                    inputs["text"] = prompt
                    break
    return wf.get("prompt") if "prompt" in wf and isinstance(wf["prompt"], dict) else wf
