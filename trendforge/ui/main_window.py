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
from trendforge.services.maestro_detect import detect_maestro
from trendforge.services.projects import ProjectStore
from trendforge.settings import AppSettings
from trendforge.ui.pages.channel import ChannelPage
from trendforge.ui.pages.create import CreatePage
from trendforge.ui.pages.discover import DiscoverPage
from trendforge.ui.pages.mini_series import MiniSeriesPage
from trendforge.ui.pages.gallery import GalleryPage
from trendforge.ui.pages.help import HelpPage
from trendforge.ui.pages.models import ModelsPage
from trendforge.ui.pages.projects import ProjectsPage
from trendforge.ui.wizard import SetupWizard


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
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

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
        self.channel = ChannelPage(settings)
        self.projects = ProjectsPage(self.store)
        self.gallery = GalleryPage(self.store)
        self.models = ModelsPage(settings, app_dirs)
        self.help = HelpPage()
        for page in (
            self.discover,
            self.create,
            self.mini,
            self.channel,
            self.projects,
            self.gallery,
            self.models,
            self.help,
        ):
            self.stack.addWidget(page)

        # Adobe-style sections, Maestro-style focus path
        self.nav_btns: list[QPushButton] = []
        sections = [
            ("IDEATE", (("Discover", 0),)),
            ("PRODUCE", (("Create", 1), ("Mini Series", 2), ("Channel", 3))),
            ("LIBRARY", (("Projects", 4), ("Gallery", 5))),
            ("SYSTEM", (("Models", 6), ("Help", 7))),
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

        self._build_menu()
        hw = detect_hardware()
        maestro = detect_maestro(settings.maestro_url, settings.pinokio_path)
        cinema = "ViralForge Cinema" if getattr(settings, "prefer_native_cinema", True) else "Maestro path"
        mae = "Maestro up" if maestro.running_url else "Maestro off"
        self.statusBar().showMessage(
            f"{hw.gpu_name} · {hw.vram_total_gb} GB · Engine: {cinema} · {mae} · {app_dirs.root}"
        )
        self._goto(1)

    def _goto(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_btns):
            btn.setChecked(i == index)
        if index == 0:
            self.discover.reload()
        if index == 2:
            self.mini.reload()
        if index == 3:
            self.channel.reload()
        if index == 4:
            self.projects.reload()
        if index == 5:
            self.gallery.reload()
        if index == 6:
            self.models.refresh_status()

    def _from_discover(self, item: TrendItem) -> None:
        self.create.apply_trend(item)
        self._goto(1)

    def _build_menu(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("&File")
        quit_act = QAction("Exit", self)
        quit_act.setShortcut(QKeySequence.StandardKey.Quit)
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)

        help_menu = bar.addMenu("&Help")
        gs = QAction("Getting Started", self)
        gs.triggered.connect(lambda: self._goto(7))
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
            "Primary engine: ViralForge Cinema (Wan 2.2 + LTX-2.5 + stitch).\n"
            "Maestro remains optional. Pinokio not required.\n"
            "No paid APIs required for core features.",
        )
