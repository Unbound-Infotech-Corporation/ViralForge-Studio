from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from trendforge import __app_name__, __version__
from trendforge.bootstrap import AppDirs
from trendforge.domain.models import TrendItem
from trendforge.logging_setup import read_log_tail
from trendforge.services.hardware import detect_hardware
from trendforge.services.projects import ProjectStore
from trendforge.settings import AppSettings
from trendforge.ui.job_console import JobConsole
from trendforge.ui.pages.channel import ChannelPage
from trendforge.ui.pages.create import CreatePage
from trendforge.ui.pages.discover import DiscoverPage
from trendforge.ui.pages.mini_series import MiniSeriesPage
from trendforge.ui.pages.gallery import GalleryPage
from trendforge.ui.pages.help import HelpPage
from trendforge.ui.pages.models import ModelsPage
from trendforge.ui.pages.projects import ProjectsPage
from trendforge.ui.pages.script_lab import ScriptLabPage
from trendforge.ui.wizard import SetupWizard

PAGE_DISCOVER = 0
PAGE_CREATE = 1
PAGE_MINI_SERIES = 2
PAGE_SCRIPT_LAB = 3
PAGE_CHANNEL = 4
PAGE_PROJECTS = 5
PAGE_GALLERY = 6
PAGE_MODELS = 7
PAGE_HELP = 8


class MainWindow(QMainWindow):
    def __init__(self, settings: AppSettings, app_dirs: AppDirs) -> None:
        super().__init__()
        self.settings = settings
        self.app_dirs = app_dirs
        self.store = ProjectStore(app_dirs.projects)
        self.setWindowTitle(f"{__app_name__} {__version__}")
        self.resize(1280, 820)
        self.setMinimumSize(1024, 680)

        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.hint_bar = self._build_hint_bar()
        outer.addWidget(self.hint_bar)
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        outer.addLayout(layout, 1)

        nav = QFrame()
        nav.setObjectName("nav")
        nav.setFixedWidth(220)
        nav_l = QVBoxLayout(nav)
        brand = QLabel("VIRALFORGE")
        brand.setObjectName("kicker")
        name = QLabel("Studio")
        name.setObjectName("title")
        name.setStyleSheet("font-size: 22px;")
        tag = QLabel("Clear panels · one primary action")
        tag.setObjectName("subtitle")
        nav_l.addWidget(brand)
        nav_l.addWidget(name)
        nav_l.addWidget(tag)
        nav_l.addSpacing(8)

        self.stack = QStackedWidget()
        self.discover = DiscoverPage(settings.trend_region)
        self.create = CreatePage(settings, app_dirs, self.store)
        self.mini = MiniSeriesPage(settings, app_dirs, self.store)
        self.script_lab = ScriptLabPage(settings, app_dirs, self.create)
        self.channel = ChannelPage(settings)
        self.projects = ProjectsPage(self.store)
        self.gallery = GalleryPage(self.store)
        self.models = ModelsPage(settings, app_dirs)
        self.help = HelpPage()
        for page in (
            self.discover,
            self.create,
            self.mini,
            self.script_lab,
            self.channel,
            self.projects,
            self.gallery,
            self.models,
            self.help,
        ):
            self.stack.addWidget(page)

        self.nav_btns: list[QPushButton] = []
        sections = [
            ("IDEATE", (("Discover", PAGE_DISCOVER),)),
            (
                "PRODUCE",
                (
                    ("Script Lab", PAGE_SCRIPT_LAB),
                    ("Create", PAGE_CREATE),
                    ("Mini Series", PAGE_MINI_SERIES),
                    ("Channel", PAGE_CHANNEL),
                ),
            ),
            ("LIBRARY", (("Projects", PAGE_PROJECTS), ("Gallery", PAGE_GALLERY))),
            ("SYSTEM", (("Models", PAGE_MODELS), ("Help", PAGE_HELP))),
        ]
        for section, items in sections:
            hdr = QLabel(section)
            hdr.setObjectName("kicker")
            hdr.setStyleSheet("margin-top: 10px; color: #6A7286;")
            nav_l.addWidget(hdr)
            for label, idx in items:
                btn = QPushButton(label)
                btn.setObjectName("nav")
                btn.setCheckable(True)
                btn.clicked.connect(lambda _=False, i=idx: self._goto(i))
                nav_l.addWidget(btn)
                while len(self.nav_btns) <= idx:
                    self.nav_btns.append(btn)
                self.nav_btns[idx] = btn
        nav_l.addStretch()
        ver = QLabel(f"v{__version__}\nCinema native · Local")
        ver.setObjectName("subtitle")
        nav_l.addWidget(ver)

        layout.addWidget(nav)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        self.discover.topic_chosen.connect(self._from_discover)
        self.create.project_ready.connect(lambda _: self.projects.reload())
        self.create.project_ready.connect(lambda _: self.gallery.reload())
        self.mini.project_ready.connect(lambda _: self.projects.reload())
        self.mini.project_ready.connect(lambda _: self.gallery.reload())
        self.channel.saved.connect(self.create.refresh_dropdowns)
        self.models.catalogs_updated.connect(self.create.refresh_dropdowns)
        self.create.produce_started.connect(self._on_produce_started)
        self.create.job_event.connect(self._on_job_event)

        self.console = JobConsole(settings, self)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.console)
        self.console.setVisible(False)
        self.console.visibilityChanged.connect(self._sync_console_checks)

        self._build_menu()
        self._build_status_console()
        hw = detect_hardware()
        self.statusBar().showMessage(
            f"{hw.gpu_name} · {hw.vram_total_gb} GB · ViralForge Cinema · Job Console: Ctrl+` · {app_dirs.root}"
        )
        self._goto(PAGE_CREATE)
        if not settings.console_hint_shown:
            self.hint_bar.setVisible(True)
        else:
            self.hint_bar.setVisible(False)

    def _goto(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_btns):
            btn.setChecked(i == index)
        if index == PAGE_DISCOVER:
            self.discover.reload()
        elif index == PAGE_MINI_SERIES:
            self.mini.reload()
        elif index == PAGE_SCRIPT_LAB:
            self.script_lab.ensure_loaded()
            self.script_lab.refresh_provider_label()
        elif index == PAGE_CHANNEL:
            self.channel.reload()
        elif index == PAGE_PROJECTS:
            self.projects.reload()
        elif index == PAGE_GALLERY:
            self.gallery.reload()
        elif index == PAGE_MODELS:
            self.models.refresh_status()
            self.models.reload_script_ai()

    def _from_discover(self, item: TrendItem) -> None:
        self.create.apply_trend(item)
        self._goto(PAGE_CREATE)

    def _build_hint_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("hintBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(12, 8, 12, 8)
        text = QLabel(
            "Job Console tracks Produce. Open it from View → Job Console, "
            "the Console button on the status bar, or Ctrl+`."
        )
        text.setWordWrap(True)
        dismiss = QPushButton("Got it")
        dismiss.clicked.connect(self._dismiss_console_hint)
        row.addWidget(text, 1)
        row.addWidget(dismiss)
        return bar

    def _dismiss_console_hint(self) -> None:
        self.hint_bar.setVisible(False)
        self.settings.console_hint_shown = True
        try:
            self.settings.save()
        except Exception:
            pass

    def _build_status_console(self) -> None:
        self.console_btn = QPushButton("Console")
        self.console_btn.setObjectName("consoleToggle")
        self.console_btn.setCheckable(True)
        self.console_btn.setToolTip("Job Console (Ctrl+`)")
        self.console_btn.toggled.connect(self._set_console_visible)
        self.statusBar().addPermanentWidget(self.console_btn)

    def _set_console_visible(self, visible: bool) -> None:
        self.console.setVisible(visible)
        self._sync_console_checks(visible)

    def _sync_console_checks(self, visible: bool) -> None:
        if hasattr(self, "console_action"):
            self.console_action.blockSignals(True)
            self.console_action.setChecked(visible)
            self.console_action.blockSignals(False)
        if hasattr(self, "console_btn"):
            self.console_btn.blockSignals(True)
            self.console_btn.setChecked(visible)
            self.console_btn.blockSignals(False)

    def _on_produce_started(self) -> None:
        if self.settings.show_console_on_produce:
            self._set_console_visible(True)
            self.console.raise_()

    def _on_job_event(self, text: str) -> None:
        self.console.append_line(text)

    def _build_menu(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("&File")
        quit_act = QAction("Exit", self)
        quit_act.setShortcut(QKeySequence.StandardKey.Quit)
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)

        settings_menu = bar.addMenu("&Settings")
        script_ai = QAction("Script AI", self)
        script_ai.triggered.connect(self._open_script_ai_settings)
        settings_menu.addAction(script_ai)

        view_menu = bar.addMenu("&View")
        self.console_action = QAction("Job Console", self)
        self.console_action.setCheckable(True)
        self.console_action.setShortcut(QKeySequence("Ctrl+`"))
        self.console_action.setStatusTip("Show the Job Console — View menu, status-bar Console, or Ctrl+`")
        self.console_action.toggled.connect(self._set_console_visible)
        view_menu.addAction(self.console_action)

        help_menu = bar.addMenu("&Help")
        gs = QAction("Getting Started", self)
        gs.triggered.connect(lambda: self._goto(PAGE_HELP))
        help_menu.addAction(gs)
        wiz = QAction("Run setup wizard again", self)
        wiz.triggered.connect(self.show_setup_wizard)
        help_menu.addAction(wiz)
        logs = QAction("Copy logs", self)
        logs.triggered.connect(self._copy_logs)
        help_menu.addAction(logs)
        about = QAction("About", self)
        about.triggered.connect(self._about)
        help_menu.addAction(about)

    def _open_script_ai_settings(self) -> None:
        self._goto(PAGE_MODELS)
        self.models.focus_script_ai()

    def show_setup_wizard(self) -> None:
        wiz = SetupWizard(self.settings, self.app_dirs, self)
        wiz.exec()
        self.channel.reload()
        self.models.refresh_status()
        self.create.refresh_dropdowns()

    def _copy_logs(self) -> None:
        text = read_log_tail(self.app_dirs.logs / "trendforge.log")
        QApplication.clipboard().setText(text)
        self.statusBar().showMessage("Logs copied", 3000)

    def _about(self) -> None:
        QMessageBox.about(
            self,
            __app_name__,
            f"{__app_name__} {__version__}\n\n"
            "Local trending-topic video studio.\n"
            "Shorts, long videos, and narrated docuseries.\n"
            "Primary engine: ViralForge Cinema (Wan 2.2 and CogVideoX).\n"
            "Job Console: View → Job Console, the status-bar Console button, or Ctrl+`.\n"
            "Script Lab is under Produce. Settings → Script AI stores a bring-your-own key "
            "(or local Ollama). A chat subscription is not an API key.\n"
            "Mini Series sits between Create and Channel. Approve the meeting before Produce Cinema.\n"
            "No paid APIs required for core features.",
        )
