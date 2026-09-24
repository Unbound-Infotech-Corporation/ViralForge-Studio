from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from trendforge.bootstrap import AppDirs
from trendforge.domain.catalog import (
    FORMAT_MARKS,
    STYLE_MARKS,
    dropdown_label,
    format_choices,
    format_defaults,
    model_catalog,
    style_choices,
    visible_model_catalog,
)
from trendforge.domain.enums import (
    AspectRatio,
    BackendKind,
    CaptionStyle,
    ContentFormat,
    MediaType,
    PipelineStage,
    TransitionStyle,
    TrendCategory,
    VideoStyle,
    VoiceEngine,
)
from trendforge.domain.models import GenerationRequest, PipelineProgress, Project, TrendItem
from trendforge.services.hardware import detect_hardware
from trendforge.services.pipeline import ProductionPipeline
from trendforge.services.projects import ProjectStore
from trendforge.services.review_validation import validate_opinion_input, validate_review_request
from trendforge.services.script_engine import generate_review_script, generate_script
from trendforge.services.script_import import apply_script_text
from trendforge.services.trailer_allowlist import list_entries, match_entry_for_subject
from trendforge.settings import AppSettings
from trendforge.ui.widgets import ChoiceRow, PipelineStrip, mark_icon
from trendforge.ui.workers import FnWorker, PipelineWorker


class CreatePage(QWidget):
    project_ready = Signal(object)
    produce_started = Signal()
    job_event = Signal(str)

    def __init__(self, settings: AppSettings, dirs: AppDirs, store: ProjectStore, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.dirs = dirs
        self.store = store
        self._worker: PipelineWorker | None = None
        self._plan_worker: FnWorker | None = None
        self._project: Project | None = None
        self.hw = detect_hardware()

        root = QVBoxLayout(self)
        kicker = QLabel("PRODUCE")
        kicker.setObjectName("kicker")
        title = QLabel("What do you want to make?")
        title.setObjectName("title")
        hint = QLabel("One topic → script → ViralForge Cinema stitches a short. GPU gen takes longer; dry-run is instant.")
        hint.setObjectName("subtitle")
        hint.setWordWrap(True)
        self.topic = QLineEdit()
        self.topic.setPlaceholderText("A trending topic, a headline, or a YouTube URL to break down…")
        self.topic.setMinimumHeight(44)
        self.topic.textChanged.connect(self._on_topic_changed)

        form = QFormLayout()
        self.fmt = QComboBox()
        for label, value in format_choices():
            self.fmt.addItem(mark_icon(FORMAT_MARKS.get(value, "FMT")), label, value)
        self.model = QComboBox()
        self._fill_models()
        self.style = QComboBox()
        for label, value in style_choices():
            self.style.addItem(mark_icon(STYLE_MARKS.get(value, "ST")), label, value)
        self.aspect = QComboBox()
        for a in AspectRatio:
            self.aspect.addItem(a.value, a.value)
        self.voice = QComboBox()
        self._fill_voices()
        self.captions = QComboBox()
        for c in CaptionStyle:
            self.captions.addItem(c.value.title(), c.value)
        self.transition = QComboBox()
        for t in TransitionStyle:
            self.transition.addItem(t.value.replace("_", " ").title(), t.value)
        self.series = QLineEdit()
        self.series.setPlaceholderText("Flagship series name (docuseries)")
        self.episode = QSpinBox()
        self.episode.setRange(1, 12)
        self.episode.setValue(1)
        self.episodes = QSpinBox()
        self.episodes.setRange(3, 8)
        self.episodes.setValue(5)
        self.format_row = ChoiceRow("Format", self.fmt)
        self.model_row = ChoiceRow("Model", self.model)
        self.style_row = ChoiceRow("Style", self.style)
        form.addRow(self.format_row)
        form.addRow(self.model_row)
        form.addRow(self.style_row)
        form.addRow("Aspect", self.aspect)
        form.addRow("Voice", self.voice)
        form.addRow("Captions", self.captions)
        form.addRow("Transitions", self.transition)
        form.addRow("Series", self.series)
        form.addRow("Episode #", self.episode)
        form.addRow("Season length", self.episodes)

        self.review_box = QWidget()
        review_form = QFormLayout(self.review_box)
        self.media_type = QComboBox()
        for mt in MediaType:
            self.media_type.addItem(mt.value.title(), mt.value)
        self.review_subject = QLineEdit()
        self.review_subject.setPlaceholderText("e.g. Dune: Part Two")
        self.studio_allowlist = QComboBox()
        self._fill_studio_allowlist()
        self.trailer_url = QLineEdit()
        self.trailer_url.setPlaceholderText("Official trailer URL from the studio channel above")
        self.user_rating = QDoubleSpinBox()
        self.user_rating.setRange(0, 10)
        self.user_rating.setSingleStep(0.5)
        self.user_rating.setValue(7.0)
        self.user_opinion = QPlainTextEdit()
        self.user_opinion.setPlaceholderText("Your overall take — required. TrendForge will not invent opinions.")
        self.user_opinion.setMaximumHeight(90)
        self.user_liked = QPlainTextEdit()
        self.user_liked.setPlaceholderText("What you liked (specific beats, performances, mechanics…)")
        self.user_liked.setMaximumHeight(70)
        self.user_disliked = QPlainTextEdit()
        self.user_disliked.setPlaceholderText("What didn't work for you")
        self.user_disliked.setMaximumHeight(70)
        self.user_moments = QPlainTextEdit()
        self.user_moments.setPlaceholderText("Scenes or moments you want to reference")
        self.user_moments.setMaximumHeight(70)
        self.user_verdict = QPlainTextEdit()
        self.user_verdict.setPlaceholderText("Bottom line — who should watch/play this?")
        self.user_verdict.setMaximumHeight(70)
        self.gameplay_path = QLineEdit()
        self.gameplay_path.setPlaceholderText("Optional: path to your gameplay capture (.mp4) for game reviews")
        self.opinion_lock = QCheckBox("This is my genuine opinion — required before generating")
        review_form.addRow("Media type", self.media_type)
        review_form.addRow("Title", self.review_subject)
        review_form.addRow("Official studio", self.studio_allowlist)
        review_form.addRow("Trailer URL", self.trailer_url)
        review_form.addRow("Your rating /10", self.user_rating)
        review_form.addRow("Overall opinion", self.user_opinion)
        review_form.addRow("What you liked", self.user_liked)
        review_form.addRow("What you disliked", self.user_disliked)
        review_form.addRow("Key moments", self.user_moments)
        review_form.addRow("Verdict", self.user_verdict)
        review_form.addRow("Gameplay file", self.gameplay_path)
        review_form.addRow("", self.opinion_lock)
        self.review_box.setVisible(False)
        self.review_subject.textChanged.connect(self._on_review_subject_changed)
        self.media_type.currentIndexChanged.connect(self._on_media_type_changed)

        toggles = QHBoxLayout()
        self.vo = QCheckBox("Voiceover")
        self.vo.setChecked(True)
        self.cap = QCheckBox("Captions")
        self.cap.setChecked(False)
        self.mus = QCheckBox("Background music")
        self.mus.setChecked(True)
        self.intro = QCheckBox("Intro")
        self.intro.setChecked(True)
        self.outro = QCheckBox("Outro")
        self.outro.setChecked(True)
        for w in (self.vo, self.cap, self.mus, self.intro, self.outro):
            toggles.addWidget(w)
        toggles.addStretch()

        self.hw_label = QLabel(
            f"{self.hw.gpu_name} · {self.hw.vram_free_gb}/{self.hw.vram_total_gb} GB VRAM · "
            f"recommend {self.hw.recommended_model_id}"
        )
        self.hw_label.setObjectName("subtitle")

        btns = QHBoxLayout()
        self.generate = QPushButton("Generate Video")
        self.generate.setObjectName("primary")
        self.generate.clicked.connect(self.start_generation)
        self.plan = QPushButton("Write script only")
        self.plan.clicked.connect(self.plan_script)
        self.regen = QPushButton("Regenerate selected shot")
        self.regen.clicked.connect(self.regenerate_shot)
        self.cancel = QPushButton("Cancel")
        self.cancel.setEnabled(False)
        self.cancel.clicked.connect(self._cancel)
        self.resume = QPushButton("Resume")
        self.resume.setEnabled(False)
        self.resume.clicked.connect(lambda: self.start_generation(resume=True))
        btns.addWidget(self.generate)
        btns.addWidget(self.plan)
        btns.addWidget(self.regen)
        btns.addWidget(self.cancel)
        btns.addWidget(self.resume)
        btns.addStretch()

        self.strip = PipelineStrip()
        self.progress = QProgressBar()
        self.status = QLabel("Ready. Paste a YouTube URL for clip + narrate, or use Auto for AI footage.")
        self.status.setObjectName("subtitle")

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_l = QVBoxLayout(left)
        left_l.addWidget(QLabel("Script (editable before / during planning)"))
        self.script_edit = QPlainTextEdit()
        self.script_edit.setPlaceholderText("The generated script and narration will appear here. You can edit shot narration after planning.")
        left_l.addWidget(self.script_edit)
        right = QWidget()
        right_l = QVBoxLayout(right)
        right_l.addWidget(QLabel("Shot list"))
        self.shots = QTableWidget(0, 5)
        self.shots.setHorizontalHeaderLabels(["#", "Title", "Timing", "Narration", "Status"])
        self.shots.horizontalHeader().setStretchLastSection(True)
        self.shots.currentCellChanged.connect(self._on_shot_row)
        right_l.addWidget(self.shots)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([520, 380])

        root.addWidget(kicker)
        root.addWidget(title)
        root.addWidget(hint)
        root.addWidget(self.topic)
        root.addLayout(form)
        root.addWidget(self.review_box)
        root.addLayout(toggles)
        root.addWidget(self.hw_label)
        root.addLayout(btns)
        root.addWidget(self.strip)
        root.addWidget(self.progress)
        root.addWidget(self.status)
        root.addWidget(splitter, 1)

        self._showing_season = False
        self._apply_settings_defaults()
        self.fmt.currentIndexChanged.connect(self._on_format_changed)
        self._update_format_chrome()

    def _fill_models(self) -> None:
        current = self.model.currentData() if self.model.count() else self.settings.last_model_id
        self.model.blockSignals(True)
        self.model.clear()
        for opt in visible_model_catalog():
            self.model.addItem(mark_icon(opt.mark or opt.family[:2]), dropdown_label(opt), opt.id)
            self.model.setItemData(self.model.count() - 1, opt.tooltip, Qt.ItemDataRole.ToolTipRole)
        self.model.blockSignals(False)
        self._set_combo(self.model, current or "auto")
        if hasattr(self, "model_row"):
            self.model_row.sync_mark()

    def _fill_voices(self) -> None:
        current = self.voice.currentData() if self.voice.count() else None
        self.voice.blockSignals(True)
        self.voice.clear()
        self.voice.addItem("Windows SAPI (built-in narrator)", "sapi")
        try:
            from trendforge.services.installer import installed_piper_voices

            for voice in installed_piper_voices(self.dirs):
                nice = voice.replace("en_US-", "").replace("-medium", "").replace("-", " ").title()
                self.voice.addItem(f"Piper — {nice} (local, installed)", f"piper:{voice}")
        except Exception:
            pass
        self.voice.addItem("Piper — auto (install in Setup if missing)", "piper:en_US-lessac-medium")
        self.voice.addItem("Edge TTS (free cloud — enable in Settings)", "edge")
        self.voice.blockSignals(False)
        if current:
            self._set_combo(self.voice, current)

    def refresh_dropdowns(self) -> None:
        """Reload model/voice lists after setup installs Piper or Ollama."""
        self._fill_models()
        self._fill_voices()
        self._apply_settings_defaults()
        self._update_format_chrome()

    def _fill_studio_allowlist(self) -> None:
        self.studio_allowlist.blockSignals(True)
        self.studio_allowlist.clear()
        for entry in list_entries():
            label = f"{entry.studio} ({', '.join(entry.channel_names[:1])})"
            self.studio_allowlist.addItem(label, entry.id)
        self.studio_allowlist.blockSignals(False)

    def _is_review_mode(self) -> bool:
        return self._current_format() is ContentFormat.REVIEW

    def _on_media_type_changed(self) -> None:
        try:
            media = MediaType(self.media_type.currentData())
        except Exception:
            return
        self._fill_studio_allowlist_for(media)
        self.gameplay_path.setEnabled(media is MediaType.GAME)

    def _fill_studio_allowlist_for(self, media: MediaType | None = None) -> None:
        current = self.studio_allowlist.currentData() if self.studio_allowlist.count() else ""
        self.studio_allowlist.blockSignals(True)
        self.studio_allowlist.clear()
        for entry in list_entries(media):
            label = f"{entry.studio} ({', '.join(entry.channel_names[:1])})"
            self.studio_allowlist.addItem(label, entry.id)
        self.studio_allowlist.blockSignals(False)
        if current:
            self._set_combo(self.studio_allowlist, current)

    def _on_review_subject_changed(self, text: str) -> None:
        if not self._is_review_mode() or not text.strip():
            return
        try:
            media = MediaType(self.media_type.currentData())
        except Exception:
            media = None
        match = match_entry_for_subject(text, media)
        if match:
            self._set_combo(self.studio_allowlist, match.id)

    def _on_format_changed(self) -> None:
        try:
            fmt = ContentFormat(self.fmt.currentData())
        except Exception:
            return
        defaults = format_defaults(fmt)
        self._set_combo(self.style, defaults["style"].value)
        self._set_combo(self.aspect, defaults["aspect"].value)
        self.intro.setChecked(bool(defaults["enable_intro"]))
        self.outro.setChecked(bool(defaults["enable_outro"]))
        self.vo.setChecked(True)
        if fmt is ContentFormat.REVIEW:
            self._set_combo(self.model, "media_review")
            self.review_box.setVisible(True)
            self._on_media_type_changed()
        else:
            self.review_box.setVisible(False)
        self._update_format_chrome()

    def _update_format_chrome(self) -> None:
        try:
            fmt = ContentFormat(self.fmt.currentData())
        except Exception:
            return
        self.episode.setEnabled(fmt in {ContentFormat.DOCUSERIES, ContentFormat.SEASON})
        self.episodes.setEnabled(fmt is ContentFormat.SEASON)
        self.series.setEnabled(fmt in {ContentFormat.DOCUSERIES, ContentFormat.SEASON, ContentFormat.LONG})
        if fmt is ContentFormat.SHORTS:
            self.generate.setText("Generate Short")
            self.status.setText("Shorts: vertical, punchy hook, 15–60s. Post daily to pull new subscribers.")
        elif fmt is ContentFormat.DOCUSERIES:
            self.generate.setText("Generate episode")
            self.status.setText("Docuseries episode: long narrated investigation. Voiceover stays on.")
        elif fmt is ContentFormat.SEASON:
            self.generate.setText("Plan season")
            self.status.setText("Season plan: writes 4–6 episode briefs. Then pick an episode and Generate.")
        elif fmt is ContentFormat.LONG:
            self.generate.setText("Generate long video")
            self.status.setText("Long video: 10–18 min session that binge-watchers finish.")
        elif fmt is ContentFormat.REVIEW:
            self.generate.setText("Generate review")
            self.status.setText(
                "Review mode: your genuine opinion + brief official trailer clips only. "
                "Add your rating and notes, then paste an allowlisted studio trailer URL."
            )
        else:
            self.generate.setText("Generate Video")
            self.status.setText("Standard video: 3–8 min — the workhorse upload for a growing channel.")
        channel = self.settings.channel_name or "your channel"
        self.hw_label.setText(
            f"{self.hw.gpu_name} · {self.hw.vram_free_gb}/{self.hw.vram_total_gb} GB VRAM · "
            f"{channel} · recommend {self.hw.recommended_model_id}"
        )

    def _apply_settings_defaults(self) -> None:
        self._set_combo(self.fmt, self.settings.last_format.value)
        self._set_combo(self.model, self.settings.last_model_id)
        self._set_combo(self.style, self.settings.last_style.value)
        self._set_combo(self.aspect, self.settings.last_aspect.value)
        self._set_combo(self.captions, self.settings.last_caption.value)
        self._set_combo(self.transition, self.settings.last_transition.value)
        self.cap.setChecked(bool(self.settings.enable_captions))
        self.series.setText(self.settings.series_title)
        self._restore_voice()

    def _restore_voice(self) -> None:
        voice = self.settings.last_voice
        if voice is VoiceEngine.PIPER:
            key = f"piper:{self.settings.last_piper_voice or 'en_US-lessac-medium'}"
            if self.voice.findData(key) < 0:
                key = "piper:en_US-lessac-medium"
            self._set_combo(self.voice, key)
        elif voice is VoiceEngine.EDGE_TTS:
            self._set_combo(self.voice, "edge")
        elif voice is VoiceEngine.MAESTRO:
            self._set_combo(self.voice, "sapi")
        else:
            self._set_combo(self.voice, "sapi")

    def _voice_from_combo(self) -> tuple[VoiceEngine, str]:
        raw = self.voice.currentData() or "sapi"
        if raw == "sapi":
            return VoiceEngine.WINDOWS_SAPI, self.settings.last_piper_voice
        if raw == "maestro":
            return VoiceEngine.MAESTRO, ""
        if raw == "edge":
            return VoiceEngine.EDGE_TTS, ""
        if isinstance(raw, str) and raw.startswith("piper:"):
            return VoiceEngine.PIPER, raw.split(":", 1)[1]
        try:
            return VoiceEngine(raw), self.settings.last_piper_voice
        except ValueError:
            return VoiceEngine.WINDOWS_SAPI, ""

    def _current_format(self) -> ContentFormat:
        try:
            return ContentFormat(self.fmt.currentData())
        except Exception:
            return ContentFormat.VIDEO

    def _set_combo(self, combo: QComboBox, value: str) -> None:
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _on_topic_changed(self, text: str) -> None:
        if text.strip().startswith("http"):
            self._set_combo(self.model, "source_clip")
            self._set_combo(self.style, VideoStyle.BREAKDOWN.value)
            self.status.setText(
                "YouTube URL detected — Clip + narrate will cut the source video and overlay your voiceover."
            )

    def apply_trend(self, item: TrendItem) -> None:
        self.topic.setText(item.title)
        if item.url:
            self.topic.setPlaceholderText(item.url)

    def _request(self) -> GenerationRequest:
        topic = self.topic.text().strip()
        url = topic if topic.startswith("http") else ""
        model_id = self.model.currentData() or "auto"
        backend = BackendKind.AUTO
        for opt in model_catalog():
            if opt.id == model_id:
                backend = opt.backend
                break
        fmt = self._current_format()
        defaults = format_defaults(fmt)
        voice, piper = self._voice_from_combo()
        series = self.series.text().strip() or self.settings.series_title
        review_subject = self.review_subject.text().strip()
        try:
            media_type = MediaType(self.media_type.currentData())
        except Exception:
            media_type = MediaType.MOVIE
        topic_value = review_subject or topic
        if fmt is ContentFormat.REVIEW:
            backend = BackendKind.REVIEW
            model_id = "media_review"
        return GenerationRequest(
            topic=topic_value,
            category=TrendCategory.CUSTOM,
            source_url=url if fmt is not ContentFormat.REVIEW else "",
            style=VideoStyle(self.style.currentData() or defaults["style"].value),
            length=defaults["length"],
            content_format=fmt,
            aspect=AspectRatio(self.aspect.currentData() or defaults["aspect"].value),
            backend=backend,
            model_id=model_id,
            voice=voice,
            piper_voice=piper or self.settings.last_piper_voice,
            captions=CaptionStyle(self.captions.currentData() or CaptionStyle.NONE.value),
            transition=TransitionStyle(self.transition.currentData() or TransitionStyle.CROSSFADE.value),
            enable_voiceover=self.vo.isChecked(),
            enable_captions=self.cap.isChecked(),
            enable_music=self.mus.isChecked(),
            enable_intro=self.intro.isChecked(),
            enable_outro=self.outro.isChecked(),
            codec=self.settings.codec,
            music_volume=self.settings.default_music_volume,
            series_title=series,
            episode_index=self.episode.value(),
            episode_count=self.episodes.value(),
            brand_voice=self.settings.brand_voice,
            channel_name=self.settings.channel_name,
            channel_cta=self.settings.channel_cta,
            media_type=media_type,
            review_subject=review_subject,
            trailer_url=self.trailer_url.text().strip(),
            allowlist_entry_id=str(self.studio_allowlist.currentData() or ""),
            gameplay_path=self.gameplay_path.text().strip(),
            user_rating=float(self.user_rating.value()),
            user_rating_scale="10",
            user_opinion=self.user_opinion.toPlainText().strip(),
            user_liked=self.user_liked.toPlainText().strip(),
            user_disliked=self.user_disliked.toPlainText().strip(),
            user_moments=self.user_moments.toPlainText().strip(),
            user_verdict=self.user_verdict.toPlainText().strip(),
            opinion_completed=self.opinion_lock.isChecked(),
        )

    def _apply_table_edits(self, project: Project) -> None:
        if not project.script:
            return
        for i, shot in enumerate(project.script.shots):
            if i >= self.shots.rowCount():
                break
            title = self.shots.item(i, 1)
            dur = self.shots.item(i, 2)
            narr = self.shots.item(i, 3)
            if title:
                shot.title = title.text()
            if dur:
                try:
                    shot.duration_sec = float(dur.text())
                except ValueError:
                    pass
            if narr:
                shot.narration = narr.text()

    def _validate_before_run(self, req: GenerationRequest) -> bool:
        if req.content_format is ContentFormat.REVIEW:
            check = validate_review_request(req)
            if not check.ok:
                QMessageBox.warning(self, "Review incomplete", "\n".join(check.errors))
                return False
            if check.warnings:
                self.status.setText(check.warnings[0])
            return True
        if not req.topic:
            QMessageBox.warning(self, "Topic required", "Type a topic or pick one from Discover.")
            return False
        return True

    def plan_script(self) -> None:
        req = self._request()
        if not self._validate_before_run(req):
            return
        self.status.setText("Writing script…")
        from trendforge.services.ollama_client import OllamaClient
        from trendforge.services.ytdlp_tools import extract_video_context

        def work():
            ollama = OllamaClient(self.settings.ollama_url)
            if req.content_format is ContentFormat.REVIEW:
                return generate_review_script(
                    req,
                    ollama=ollama if ollama.status().running else None,
                    ollama_model=self.settings.ollama_model,
                    channel_name=req.channel_name,
                    cta=req.channel_cta,
                )
            extra = ""
            if req.source_url:
                extra = extract_video_context(req.source_url, self.dirs.cache / "research")
            return generate_script(
                req.topic,
                req.style,
                req.length,
                extra_context=extra,
                ollama=ollama if ollama.status().running else None,
                ollama_model=self.settings.ollama_model,
                content_format=req.content_format,
                brand=req.brand_voice,
                channel_name=req.channel_name,
                cta=req.channel_cta,
                episode_index=req.episode_index,
                episode_count=req.episode_count,
                series_title=req.series_title,
                source_clip_mode=bool(req.source_url),
            )

        self._plan_worker = FnWorker(work, self)
        self._plan_worker.ok.connect(self._on_script)
        self._plan_worker.failed.connect(self._on_plan_fail)
        self._plan_worker.start()

    def _on_plan_fail(self, msg: str) -> None:
        self.status.setText(msg)
        self.job_event.emit(f"Script failed · {msg}")
        self._show_failure(msg)

    def _on_script(self, script) -> None:
        req = self._request()
        if self._project is None:
            project = Project.create(req.topic[:80], req, "")
            folder = self.dirs.projects / project.id
            folder.mkdir(parents=True, exist_ok=True)
            project.folder = str(folder)
            self._project = project
        self._project.request = req
        self._project.script = script
        self.store.save(self._project)
        self._fill_script(self._project)
        if script.season:
            self.status.setText("Season mapped — select an episode row, switch to Docuseries episode, then Generate.")
        else:
            self.status.setText("Script ready — edit shots, then Generate.")
        self.strip.set_stage(PipelineStage.SCRIPT)

    def regenerate_shot(self) -> None:
        if not self._project or not self._project.script:
            QMessageBox.information(self, "No project", "Generate or plan a script first.")
            return
        row = self.shots.currentRow()
        if row < 0:
            QMessageBox.information(self, "Select a shot", "Click a row in the shot list.")
            return
        self._apply_table_edits(self._project)
        pipe = ProductionPipeline(self.settings, self.dirs, self.store)
        project = self._project
        self.generate.setEnabled(False)

        def runner(on_progress, cancelled):
            return pipe.regenerate_shot(project, row, on_progress=on_progress, cancelled=cancelled)

        self._worker = PipelineWorker(runner, self)
        self._worker.progressed.connect(self._on_progress)
        self._worker.ok.connect(self._on_ok)
        self._worker.failed.connect(self._on_fail)
        self._worker.start()

    def start_generation(self, resume: bool = False) -> None:
        voice, _piper = self._voice_from_combo()
        if voice is VoiceEngine.EDGE_TTS and not self.settings.paid_fallbacks_enabled:
            QMessageBox.information(
                self,
                "Cloud TTS disabled",
                "Edge TTS is a free online service. Enable optional cloud fallbacks in Models & Settings first, or pick Windows SAPI / Piper.",
            )
            return
        req = self._request()
        if not self._validate_before_run(req):
            return
        season = self._project.script.season if self._project and self._project.script else None
        if req.content_format is ContentFormat.DOCUSERIES and season and not resume:
            ep = self._selected_episode()
            if ep:
                req.episode_index = ep.index
                req.series_title = season.series_title or req.series_title
            self._project = None
        reuse_script = (
            not resume
            and self._project is not None
            and self._project.script is not None
            and not self._project.script.season
            and req.content_format is not ContentFormat.SEASON
        )
        if resume and self._project:
            project = self._project
            project.request = req
            self._apply_table_edits(project)
        elif reuse_script:
            project = self._project
            project.request = req
            project.title = req.topic[:80]
            self._apply_table_edits(project)
            self.store.save(project)
        else:
            project = Project.create(req.topic[:80], req, str(self.dirs.projects / "pending"))
            folder = self.dirs.projects / project.id
            folder.mkdir(parents=True, exist_ok=True)
            project.folder = str(folder)
            self.store.save(project)
        self._project = project
        self._persist_last(req)
        self.produce_started.emit()
        self.job_event.emit(f"Produce started · {req.model_id} · {req.topic[:80]}")
        pipe = ProductionPipeline(self.settings, self.dirs, self.store)
        self.generate.setEnabled(False)
        self.cancel.setEnabled(True)
        self.resume.setEnabled(False)

        def runner(on_progress, cancelled):
            return pipe.run(project, on_progress=on_progress, cancelled=cancelled, resume=resume)

        self._worker = PipelineWorker(runner, self)
        self._worker.progressed.connect(self._on_progress)
        self._worker.ok.connect(self._on_ok)
        self._worker.failed.connect(self._on_fail)
        self._worker.start()

    def _persist_last(self, req: GenerationRequest) -> None:
        self.settings.last_model_id = req.model_id
        self.settings.last_style = req.style
        self.settings.last_length = req.length
        self.settings.last_format = req.content_format
        self.settings.last_aspect = req.aspect
        self.settings.last_voice = req.voice
        self.settings.last_piper_voice = req.piper_voice or self.settings.last_piper_voice
        self.settings.last_caption = req.captions
        self.settings.last_transition = req.transition
        self.settings.enable_captions = req.enable_captions
        if req.series_title:
            self.settings.series_title = req.series_title
        self.settings.save()

    def _on_progress(self, prog: PipelineProgress) -> None:
        self.progress.setValue(prog.percent)
        self.status.setText(prog.message)
        self.strip.set_stage(prog.stage)
        self.job_event.emit(f"{prog.percent:>3}%  {prog.stage.value}  {prog.message}")
        if self._project and self._project.script:
            self._fill_script(self._project)
            # Reload from disk so shot statuses update
            try:
                fresh = self.store.load(self._project.id)
                self._project = fresh
                self._fill_script(fresh)
            except Exception:
                pass

    def _fill_script(self, project: Project) -> None:
        if not project.script:
            return
        if project.script.season and not project.script.shots:
            self._fill_season(project)
            return
        self._showing_season = False
        self.script_edit.setPlainText(
            f"{project.script.title}\n\n{project.script.hook}\n\n{project.script.summary}\n\n"
            + "\n\n".join(f"[{s.title}] {s.narration}" for s in project.script.shots)
        )
        self.shots.setRowCount(len(project.script.shots))
        for i, shot in enumerate(project.script.shots):
            self.shots.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.shots.setItem(i, 1, QTableWidgetItem(shot.title))
            if shot.source_end_sec > shot.source_start_sec:
                dur_label = f"{shot.source_start_sec:.1f}–{shot.source_end_sec:.1f}s"
            elif shot.segment_kind.value != "commentary":
                dur_label = f"{shot.segment_kind.value} · {shot.duration_sec:.1f}s"
            else:
                dur_label = str(shot.duration_sec)
            self.shots.setItem(i, 2, QTableWidgetItem(dur_label))
            self.shots.setItem(i, 3, QTableWidgetItem(shot.narration))
            self.shots.setItem(i, 4, QTableWidgetItem(shot.status.value))

    def _fill_season(self, project: Project) -> None:
        season = project.script.season if project.script else None
        if not season:
            return
        self._showing_season = True
        lines = [
            season.series_title,
            "",
            season.logline,
            "",
            season.bible,
            "",
        ]
        for ep in season.episodes:
            lines.append(f"Episode {ep.index}: {ep.title}\n{ep.hook}\n{ep.thesis}\n{ep.summary}\n")
        self.script_edit.setPlainText("\n".join(lines))
        self.shots.setRowCount(len(season.episodes))
        for i, ep in enumerate(season.episodes):
            self.shots.setItem(i, 0, QTableWidgetItem(str(ep.index)))
            self.shots.setItem(i, 1, QTableWidgetItem(ep.title))
            self.shots.setItem(i, 2, QTableWidgetItem("ep"))
            self.shots.setItem(i, 3, QTableWidgetItem(ep.hook))
            self.shots.setItem(i, 4, QTableWidgetItem("planned"))
        self.series.setText(season.series_title)
        self.fmt.blockSignals(True)
        self._set_combo(self.fmt, ContentFormat.DOCUSERIES.value)
        self.fmt.blockSignals(False)
        self._update_format_chrome()
        if season.episodes:
            self.episode.setValue(season.episodes[0].index)
            self.episodes.setValue(len(season.episodes))

    def _on_shot_row(self, row: int, _col: int, _prev_row: int, _prev_col: int) -> None:
        if not self._showing_season or row < 0:
            return
        ep = self._selected_episode()
        if ep:
            self.episode.setValue(ep.index)

    def _selected_episode(self):
        if not self._project or not self._project.script or not self._project.script.season:
            return None
        eps = self._project.script.season.episodes
        if not eps:
            return None
        row = self.shots.currentRow()
        if 0 <= row < len(eps):
            return eps[row]
        for ep in eps:
            if ep.index == self.episode.value():
                return ep
        return eps[0]

    def _on_ok(self, project: Project) -> None:
        self._project = project
        self.generate.setEnabled(True)
        self.cancel.setEnabled(False)
        self.resume.setEnabled(False)
        self.progress.setValue(100)
        self.strip.set_stage(PipelineStage.DONE)
        self._fill_script(project)
        if project.script and project.script.season and not project.output_path:
            self.status.setText("Season planned — select an episode, then Generate episode.")
        else:
            self.status.setText(f"Done → {project.output_path}")
            self.job_event.emit(f"Done · {project.output_path}")
        self.project_ready.emit(project)

    def _on_fail(self, msg: str) -> None:
        self.generate.setEnabled(True)
        self.cancel.setEnabled(False)
        self.resume.setEnabled(True)
        self.status.setText(msg)
        self.job_event.emit(f"Failed · {msg}")
        if msg != "Cancelled":
            self.strip.set_stage(PipelineStage.FAILED)
            self._show_failure(msg)

    def _show_failure(self, msg: str) -> None:
        text = (msg or "The job failed.").strip()
        refused = "will not publish" in text or text.startswith("Refusing") or "Refusing" in text
        title = "Export refused" if refused else "Generation failed"
        if len(text) > 900:
            text = text[:900] + "…"
        text += "\n\nFull lines are in the Job Console: View → Job Console, the status-bar Console button, or Ctrl+`."
        QMessageBox.warning(self, title, text)

    def import_script_text(self, text: str, mode: str) -> str:
        """Append or replace the active episode script and persist it for Create."""
        cleaned = (text or "").strip()
        if not cleaned:
            raise ValueError("Nothing to import.")
        if self._project is None:
            if not self.topic.text().strip():
                first = next((line.strip() for line in cleaned.splitlines() if line.strip()), "Imported episode")
                self.topic.setText(first[:80])
            req = self._request()
            project = Project.create((req.topic or "Imported episode")[:80], req, "")
            folder = self.dirs.projects / project.id
            folder.mkdir(parents=True, exist_ok=True)
            project.folder = str(folder)
            self._project = project
        topic = self.topic.text().strip() or self._project.title or "Imported episode"
        self._project.script = apply_script_text(
            self._project.script,
            cleaned,
            mode=mode,
            topic=topic,
        )
        if self._project.script and self._project.script.title:
            self._project.title = self._project.script.title[:80]
        self.store.save(self._project)
        self._fill_script(self._project)
        self.strip.set_stage(PipelineStage.SCRIPT)
        count = len(self._project.script.shots) if self._project.script else 0
        verb = "Replaced" if mode.strip().lower() == "replace" else "Appended to"
        noun = "shot" if count == 1 else "shots"
        message = f"{verb} the episode script ({count} {noun})."
        self.status.setText(message)
        self.project_ready.emit(self._project)
        return message

    def _cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
            self.status.setText("Cancelling…")
