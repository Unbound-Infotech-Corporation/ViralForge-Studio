"""Mini Series — living episodes with a human approve gate.

Topic → virtual meeting → Approve → Cinema package (native Wan/Cog only).
After publish, paste comments, rank themes, and draft the next episode.
That draft stays unapproved until its own meeting is signed off.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
    QCheckBox,
)

from trendforge.bootstrap import AppDirs
from trendforge.domain.enums import BrandVoice
from trendforge.domain.mini_series import EpisodePhase, MeetingRecord, MiniEpisode, MiniSeries, new_series
from trendforge.services.mini_series.comments import comment_source_status
from trendforge.services.mini_series.guardrails import GUARDRAILS, meeting_warnings
from trendforge.services.mini_series.state import GateError, apply_meeting, mark_approved, mark_published, monitor_is_open
from trendforge.services.mini_series.store import MiniSeriesStore
from trendforge.services.mini_series.workflow import (
    cinema_render_block_reason,
    draft_next_episode,
    import_comments,
    produce_episode,
)
from trendforge.services.ollama_client import OllamaClient
from trendforge.services.pipeline import ProductionPipeline
from trendforge.services.projects import ProjectStore
from trendforge.settings import AppSettings
from trendforge.ui.workers import FnWorker, PipelineWorker


class MiniSeriesPage(QWidget):
    project_ready = Signal(object)

    def __init__(self, settings: AppSettings, dirs: AppDirs, store: ProjectStore, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.dirs = dirs
        self.projects = store
        self.series_store = MiniSeriesStore(dirs.root / "mini_series")
        self.series: MiniSeries | None = None
        self.episode: MiniEpisode | None = None
        self._loading = False
        self._dirty = False
        self._busy = False
        self._worker: FnWorker | PipelineWorker | None = None
        self._acks: dict[str, QCheckBox] = {}

        root = QVBoxLayout(self)
        kicker = QLabel("PRODUCE")
        kicker.setObjectName("kicker")
        title = QLabel("Mini Series")
        title.setObjectName("title")
        hint = QLabel(
            "One topic becomes a 5–10 minute Cinema episode. Approve the meeting before Produce or Publish. "
            "Maestro and text-card renders stay off. After you publish, paste comments and draft the next episode."
        )
        hint.setObjectName("subtitle")
        hint.setWordWrap(True)
        root.addWidget(kicker)
        root.addWidget(title)
        root.addWidget(hint)

        splitter = QSplitter()
        splitter.addWidget(self._build_series_column())
        splitter.addWidget(self._build_meeting_column())
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, 1)

        self.status = QLabel("Start a series, then fill the meeting.")
        self.status.setObjectName("miniStatus")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self._reload_combo("")

    def _build_series_column(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.series_combo = QComboBox()
        self.series_combo.setObjectName("miniSeriesCombo")
        self.series_combo.currentIndexChanged.connect(self._on_series_picked)
        self.series_title = QLineEdit()
        self.series_title.setObjectName("miniSeriesTitle")
        self.series_title.setPlaceholderText("Series title")
        self.series_topic = QLineEdit()
        self.series_topic.setObjectName("miniSeriesTopic")
        self.series_topic.setPlaceholderText("Topic for episode 1")
        self.start_btn = QPushButton("Start series")
        self.start_btn.setObjectName("miniStartSeries")
        self.start_btn.clicked.connect(self._start_series)
        self.episodes = QListWidget()
        self.episodes.setObjectName("miniEpisodeList")
        self.episodes.currentRowChanged.connect(self._on_episode_picked)
        layout.addWidget(QLabel("Series"))
        layout.addWidget(self.series_combo)
        layout.addWidget(self.series_title)
        layout.addWidget(self.series_topic)
        layout.addWidget(self.start_btn)
        layout.addWidget(QLabel("Episodes"))
        layout.addWidget(self.episodes, 1)
        panel.setMinimumWidth(280)
        return panel

    def _build_meeting_column(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._scroll = scroll
        inner = QWidget()
        layout = QVBoxLayout(inner)

        meeting = QGroupBox("Virtual meeting")
        form = QFormLayout(meeting)
        self.storyline = QPlainTextEdit()
        self.storyline.setObjectName("miniStoryline")
        self.storyline.setPlaceholderText("What happens in this episode, in order.")
        self.storyline.setMinimumHeight(90)
        self.goals = QPlainTextEdit()
        self.goals.setObjectName("miniGoals")
        self.goals.setPlaceholderText("What the viewer should understand or feel.")
        self.goals.setMinimumHeight(70)
        self.tone = QComboBox()
        self.tone.setObjectName("miniTone")
        for voice in BrandVoice:
            self.tone.addItem(voice.value.replace("_", " ").title(), voice.value)
        self.minutes = QDoubleSpinBox()
        self.minutes.setObjectName("miniMinutes")
        self.minutes.setRange(5.0, 10.0)
        self.minutes.setSingleStep(0.5)
        self.minutes.setValue(7.5)
        self.minutes.setSuffix(" min")
        self.notes = QPlainTextEdit()
        self.notes.setObjectName("miniNotes")
        self.notes.setPlaceholderText("Open questions, claims to avoid, names to get right.")
        self.notes.setMinimumHeight(70)
        form.addRow("Storyline", self.storyline)
        form.addRow("Goals", self.goals)
        form.addRow("Tone", self.tone)
        form.addRow("Length", self.minutes)
        form.addRow("Notes", self.notes)
        layout.addWidget(meeting)

        guards = QGroupBox("Guardrails — check each one to unlock Approve")
        guard_layout = QVBoxLayout(guards)
        intro = QLabel(
            "These are soft production rules against spam, harassment, reused content, and misleading packaging. "
            "Checking a box means a person accepts that rule for this episode."
        )
        intro.setWordWrap(True)
        intro.setObjectName("subtitle")
        guard_layout.addWidget(intro)
        for item in GUARDRAILS:
            box = QCheckBox(item.title)
            box.setObjectName(f"guardrail_{item.id}")
            box.setToolTip(item.detail)
            box.stateChanged.connect(self._on_meeting_edited)
            self._acks[item.id] = box
            detail = QLabel(item.detail)
            detail.setWordWrap(True)
            detail.setObjectName("subtitle")
            guard_layout.addWidget(box)
            guard_layout.addWidget(detail)
        self.warnings = QLabel("")
        self.warnings.setObjectName("miniWarnings")
        self.warnings.setWordWrap(True)
        guard_layout.addWidget(self.warnings)
        layout.addWidget(guards)

        actions = QHBoxLayout()
        self.approve_btn = QPushButton("Approve meeting")
        self.approve_btn.setObjectName("miniApprove")
        self.approve_btn.setStyleSheet(
            "QPushButton { background: #E8A54B; color: #1A1208; border: none; "
            "border-radius: 10px; padding: 12px 22px; font-size: 15px; font-weight: 700; }"
        )
        self.approve_btn.clicked.connect(self._approve)
        self.produce_btn = QPushButton("Produce Cinema package")
        self.produce_btn.setObjectName("miniProduce")
        self.produce_btn.clicked.connect(self._produce)
        self.render_btn = QPushButton("Render with Cinema")
        self.render_btn.setObjectName("miniRender")
        self.render_btn.clicked.connect(self._render)
        self.publish_btn = QPushButton("Mark published")
        self.publish_btn.setObjectName("miniPublish")
        self.publish_btn.clicked.connect(self._publish)
        for button in (self.approve_btn, self.produce_btn, self.render_btn, self.publish_btn):
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)

        self.outline = QPlainTextEdit()
        self.outline.setObjectName("miniOutline")
        self.outline.setReadOnly(True)
        self.outline.setPlaceholderText("The episode outline appears here after Produce, or when the next episode is drafted.")
        self.outline.setMinimumHeight(120)
        layout.addWidget(QLabel("Outline"))
        layout.addWidget(self.outline)

        comments = QGroupBox("Comments — 48 hours after publish")
        comment_layout = QVBoxLayout(comments)
        self.monitor_label = QLabel(comment_source_status(self.settings))
        self.monitor_label.setWordWrap(True)
        self.monitor_label.setObjectName("miniMonitor")
        self.video_id = QLineEdit()
        self.video_id.setObjectName("miniVideoId")
        self.video_id.setPlaceholderText("Optional YouTube video id (stored for a future CommentProvider)")
        self.paste = QPlainTextEdit()
        self.paste.setObjectName("miniPaste")
        self.paste.setPlaceholderText("Name: comment\nor Name | comment | likes")
        self.paste.setMinimumHeight(100)
        self.rank_btn = QPushButton("Rank comments")
        self.rank_btn.setObjectName("miniRank")
        self.rank_btn.clicked.connect(self._rank)
        self.themes = QListWidget()
        self.themes.setObjectName("miniThemes")
        self.draft_btn = QPushButton("Draft next episode from comments")
        self.draft_btn.setObjectName("miniDraftNext")
        self.draft_btn.clicked.connect(self._draft_next)
        comment_layout.addWidget(self.monitor_label)
        comment_layout.addWidget(self.video_id)
        comment_layout.addWidget(self.paste)
        comment_layout.addWidget(self.rank_btn)
        comment_layout.addWidget(self.themes)
        comment_layout.addWidget(self.draft_btn)
        layout.addWidget(comments)
        layout.addStretch()

        for editor in (self.storyline, self.goals, self.notes):
            editor.textChanged.connect(self._on_meeting_edited)
        self.tone.currentIndexChanged.connect(self._on_meeting_edited)
        self.minutes.valueChanged.connect(self._on_meeting_edited)
        self.video_id.textChanged.connect(self._on_video_id)

        scroll.setWidget(inner)
        self._sync_buttons()
        return scroll

    def reload(self) -> None:
        self._commit_form()
        self._save_series()
        selected = self.series.id if self.series else ""
        self._reload_combo(selected)

    def showEvent(self, event) -> None:  # type: ignore[override]
        self.reload()
        super().showEvent(event)

    def hideEvent(self, event) -> None:  # type: ignore[override]
        self._commit_form()
        self._save_series()
        super().hideEvent(event)

    def _reload_combo(self, select_id: str) -> None:
        self._loading = True
        self.series_combo.blockSignals(True)
        self.series_combo.clear()
        self.series_combo.addItem("New series", "")
        chosen = 0
        for series in self.series_store.list_series():
            self.series_combo.addItem(series.title or series.topic or series.id, series.id)
            if series.id == select_id:
                chosen = self.series_combo.count() - 1
        self.series_combo.setCurrentIndex(chosen)
        self.series_combo.blockSignals(False)
        self._loading = False
        self._apply_series_choice(self.series_combo.currentData() or "")

    def _on_series_picked(self, _index: int) -> None:
        if self._loading:
            return
        self._commit_form()
        self._save_series()
        self._apply_series_choice(self.series_combo.currentData() or "")

    def _apply_series_choice(self, series_id: str) -> None:
        self._loading = True
        if not series_id:
            self.series = None
            self.episode = None
            self.series_title.clear()
            self.series_topic.clear()
            self.episodes.clear()
            self._clear_meeting()
            self._loading = False
            self._sync_buttons()
            self.start_btn.setEnabled(True)
            return
        try:
            self.series = self.series_store.load(series_id)
        except (OSError, ValueError) as exc:
            self._loading = False
            self.status.setText(str(exc))
            return
        self.series_title.setText(self.series.title)
        self.series_topic.setText(self.series.topic)
        self._fill_episodes(self.series.episodes[0].id if self.series.episodes else "")
        self._loading = False
        self.start_btn.setEnabled(False)
        self._sync_buttons()

    def _fill_episodes(self, select_id: str) -> None:
        self.episodes.blockSignals(True)
        self.episodes.clear()
        chosen = 0
        if self.series:
            for row, episode in enumerate(self.series.episodes):
                label = f"{episode.index}. {episode.title} · {episode.phase.value.replace('_', ' ')}"
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, episode.id)
                self.episodes.addItem(item)
                if episode.id == select_id:
                    chosen = row
        self.episodes.blockSignals(False)
        if self.episodes.count():
            self.episodes.setCurrentRow(chosen)
            self._show_episode(self._episode_by_row(chosen))
        else:
            self._show_episode(None)

    def _episode_by_row(self, row: int) -> MiniEpisode | None:
        if not self.series or row < 0 or row >= len(self.series.episodes):
            return None
        item = self.episodes.item(row)
        if item is None:
            return self.series.episodes[row]
        episode_id = item.data(Qt.ItemDataRole.UserRole)
        for episode in self.series.episodes:
            if episode.id == episode_id:
                return episode
        return None

    def _on_episode_picked(self, row: int) -> None:
        if self._loading:
            return
        self._commit_form()
        self._save_series()
        self._show_episode(self._episode_by_row(row))

    def _clear_meeting(self) -> None:
        self._loading = True
        self.storyline.clear()
        self.goals.clear()
        self.notes.clear()
        self.minutes.setValue(7.5)
        self.tone.setCurrentIndex(max(0, self.tone.findData("documentary")))
        self.video_id.clear()
        self.paste.clear()
        self.outline.clear()
        self.themes.clear()
        for box in self._acks.values():
            box.setChecked(False)
        self.warnings.clear()
        self._dirty = False
        self._loading = False

    def _show_episode(self, episode: MiniEpisode | None) -> None:
        self.episode = episode
        self._loading = True
        if episode is None:
            self._clear_meeting()
            self._loading = False
            self._sync_buttons()
            return
        self.storyline.setPlainText(episode.meeting.storyline)
        self.goals.setPlainText(episode.meeting.goals)
        self.notes.setPlainText(episode.meeting.notes)
        self.minutes.setValue(float(episode.target_minutes))
        tone_index = self.tone.findData(episode.meeting.tone)
        if tone_index >= 0:
            self.tone.setCurrentIndex(tone_index)
        self.video_id.setText(episode.video_id)
        for guard_id, box in self._acks.items():
            box.setChecked(bool(episode.meeting.guardrail_acks.get(guard_id)))
        self.outline.setPlainText(episode.outline)
        self.themes.clear()
        for theme in episode.themes:
            self.themes.addItem(f"{theme.theme} · {theme.comment_count} comments · score {theme.score:.1f}")
        self.paste.clear()
        self._dirty = False
        self._loading = False
        self._refresh_warnings()
        self._refresh_monitor()
        self._sync_buttons()

    def _on_meeting_edited(self, *_) -> None:
        if self._loading:
            return
        self._dirty = True
        self._refresh_warnings()
        self._sync_buttons()

    def _on_video_id(self, _text: str) -> None:
        if self._loading or self.episode is None:
            return
        self.episode.video_id = self.video_id.text().strip()

    def _refresh_warnings(self) -> None:
        warnings = meeting_warnings(
            self.storyline.toPlainText(),
            self.goals.toPlainText(),
            self.notes.toPlainText(),
        )
        if warnings:
            self.warnings.setText("Check before you approve:\n" + "\n".join(f"• {item}" for item in warnings))
        else:
            self.warnings.setText("No soft-check warnings on the current notes.")

    def _refresh_monitor(self) -> None:
        base = comment_source_status(self.settings)
        episode = self.episode
        if episode is None or episode.phase is not EpisodePhase.MONITORING:
            self.monitor_label.setText(base)
            return
        window = "Comment window is still open." if monitor_is_open(episode) else (
            "The 48-hour window has closed. You can still paste comments."
        )
        until = episode.monitor_until.replace("T", " ")[:19]
        self.monitor_label.setText(f"{window} Watching until {until} UTC.\n{base}")

    def _read_meeting(self) -> MeetingRecord:
        acks = {guard_id: box.isChecked() for guard_id, box in self._acks.items()}
        return MeetingRecord(
            storyline=self.storyline.toPlainText(),
            goals=self.goals.toPlainText(),
            tone=str(self.tone.currentData() or "documentary"),
            notes=self.notes.toPlainText(),
            guardrail_acks=acks,
        )

    def _commit_form(self) -> None:
        if self._loading or self.series is None or self.episode is None:
            return
        title = self.series_title.text().strip()
        topic = self.series_topic.text().strip()
        if title:
            self.series.title = title
        if topic:
            self.series.topic = topic
        self.episode.video_id = self.video_id.text().strip()
        if self.episode.phase is EpisodePhase.MONITORING:
            return
        try:
            apply_meeting(self.episode, self._read_meeting(), target_minutes=float(self.minutes.value()))
        except GateError as exc:
            self.status.setText(exc.message)

    def _save_series(self) -> None:
        if self.series is None:
            return
        self.series_store.save(self.series)

    def _start_series(self) -> None:
        title = self.series_title.text().strip()
        topic = self.series_topic.text().strip()
        if not title or not topic:
            QMessageBox.warning(self, "Series needs a title and topic", "Enter both a series title and a topic.")
            return
        series = new_series(title, topic, self.settings.channel_name)
        self.series_store.save(series)
        self.series = series
        self.status.setText("Series started. Fill the meeting, acknowledge the guardrails, then Approve.")
        self._reload_combo(series.id)

    def _approve(self) -> None:
        if self.series is None or self.episode is None:
            return
        self._commit_form()
        try:
            mark_approved(self.episode)
        except GateError as exc:
            QMessageBox.warning(self, "Meeting is not ready", exc.message)
            self.status.setText(exc.message)
            return
        self._dirty = False
        self._save_series()
        self.status.setText("Meeting approved. Produce builds a native Cinema package. It does not render text cards.")
        self._fill_episodes(self.episode.id)
        self._reveal(self.produce_btn)
        self._sync_buttons()

    def _produce(self) -> None:
        if self.series is None or self.episode is None:
            return
        self._commit_form()
        series = self.series
        episode = self.episode

        def work() -> object:
            ollama = None
            model = ""
            client = OllamaClient(self.settings.ollama_url)
            if client.status().running:
                ollama = client
                model = self.settings.ollama_model
            return produce_episode(
                series,
                episode,
                settings=self.settings,
                project_store=self.projects,
                ollama=ollama,
                ollama_model=model,
            )

        self._run_fn(work, self._after_produce, "Writing a 5–10 minute Cinema script…")

    def _after_produce(self, project: object) -> None:
        self._busy = False
        self._save_series()
        self.project_ready.emit(project)
        if self.episode:
            self.status.setText(
                f"Cinema package ready ({getattr(project, 'id', '')}). "
                "Render with Cinema when Wan weights are installed, or mark published after you post the cut."
            )
            self._fill_episodes(self.episode.id)
            self._reveal(self.outline)
        self._sync_buttons()

    def _render(self) -> None:
        reason = cinema_render_block_reason(self.settings)
        if reason:
            QMessageBox.warning(self, "Cinema render blocked", reason)
            self.status.setText(reason)
            return
        if self.series is None or self.episode is None or not self.episode.project_id:
            return
        try:
            project = self.projects.load(self.episode.project_id)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Project missing", str(exc))
            return
        pipe = ProductionPipeline(self.settings, self.dirs, self.projects)

        def runner(on_progress, cancelled):
            return pipe.run(project, on_progress=on_progress, cancelled=cancelled)

        self.status.setText("Rendering with ViralForge Cinema…")
        self._busy = True
        self._sync_buttons()
        self._worker = PipelineWorker(runner, self)
        self._worker.ok.connect(self._after_render)
        self._worker.failed.connect(self._on_worker_fail)
        self._worker.start()

    def _after_render(self, project: object) -> None:
        self._busy = False
        if self.episode is not None:
            self.episode.output_path = str(getattr(project, "output_path", "") or "")
            self._save_series()
            self.status.setText("Cinema render finished. Review the cut, then Mark published.")
        self.project_ready.emit(project)
        self._sync_buttons()

    def _publish(self) -> None:
        if self.series is None or self.episode is None:
            return
        self._commit_form()
        try:
            mark_published(self.episode)
        except GateError as exc:
            QMessageBox.warning(self, "Publish blocked", exc.message)
            self.status.setText(exc.message)
            return
        self._save_series()
        self.status.setText("Published. Paste comments while the 48-hour window is open, then rank and draft the next episode.")
        self._fill_episodes(self.episode.id)

    def _rank(self) -> None:
        if self.episode is None:
            return
        self._commit_form()
        episode = self.episode
        pasted = self.paste.toPlainText()
        try:
            import_comments(episode, pasted)
        except (GateError, Exception) as exc:
            message = getattr(exc, "message", str(exc))
            QMessageBox.warning(self, "Comments not imported", message)
            self.status.setText(message)
            return
        self._save_series()
        if episode.themes:
            self.status.setText("Themes ranked. Draft the next episode, then Approve that meeting before any render.")
        else:
            self.status.setText("Every comment was filtered as spam or toxicity. Nothing to draft from yet.")
        self._fill_episodes(episode.id)

    def _draft_next(self) -> None:
        if self.series is None or self.episode is None:
            return
        self._commit_form()
        series = self.series
        episode = self.episode

        def work() -> object:
            ollama = None
            model = ""
            client = OllamaClient(self.settings.ollama_url)
            if client.status().running:
                ollama = client
                model = self.settings.ollama_model
            return draft_next_episode(
                series,
                episode,
                settings=self.settings,
                ollama=ollama,
                ollama_model=model,
            )

        self._run_fn(work, self._after_draft, "Drafting the next episode from comment themes…")

    def _after_draft(self, episode: object) -> None:
        self._busy = False
        self._save_series()
        episode_id = str(getattr(episode, "id", ""))
        self.status.setText("Next episode is a meeting draft. It cannot Produce until you Approve it.")
        self._fill_episodes(episode_id)
        self._reveal(self.storyline)
        self._sync_buttons()

    def _run_fn(self, fn, on_ok, status: str) -> None:
        self.status.setText(status)
        self._busy = True
        self._sync_buttons()
        worker = FnWorker(fn, self)
        self._worker = worker
        worker.ok.connect(on_ok)
        worker.failed.connect(self._on_worker_fail)
        worker.start()

    def _on_worker_fail(self, message: str) -> None:
        self._busy = False
        self.status.setText(message)
        QMessageBox.warning(self, "Mini Series", message)
        self._sync_buttons()

    def _reveal(self, widget: QWidget) -> None:
        scroll = getattr(self, "_scroll", None)
        if scroll is not None:
            scroll.ensureWidgetVisible(widget)

    def _sync_buttons(self) -> None:
        episode = self.episode
        has = self.series is not None and episode is not None and not self._busy
        phase = episode.phase if episode else None
        locked = phase is EpisodePhase.MONITORING
        for editor in (self.storyline, self.goals, self.notes):
            editor.setReadOnly(locked or self._busy)
        self.tone.setEnabled(has and not locked)
        self.minutes.setEnabled(has and not locked)
        for box in self._acks.values():
            box.setEnabled(has and not locked)
        self.approve_btn.setEnabled(has and not locked)
        self.produce_btn.setEnabled(
            has and not self._dirty and phase is EpisodePhase.APPROVED and bool(episode and episode.meeting.approved)
        )
        blocked = cinema_render_block_reason(self.settings)
        self.render_btn.setEnabled(has and not self._dirty and phase is EpisodePhase.RENDER_READY and not blocked)
        self.render_btn.setToolTip(blocked or "Render the saved package with native Wan/Cog. Dry-run text cards are refused.")
        self.publish_btn.setEnabled(has and not self._dirty and phase is EpisodePhase.RENDER_READY)
        self.rank_btn.setEnabled(has and phase is EpisodePhase.MONITORING)
        self.draft_btn.setEnabled(has and phase is EpisodePhase.MONITORING and bool(episode and episode.themes))
        self.start_btn.setEnabled(not self._busy and (self.series is None))
