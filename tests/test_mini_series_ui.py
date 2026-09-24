"""Offscreen walkthrough of the Mini Series approve → produce → comments flow."""

from __future__ import annotations

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QCheckBox, QLineEdit, QPlainTextEdit, QPushButton

from trendforge.bootstrap import AppDirs
from trendforge.domain.enums import BackendKind
from trendforge.domain.mini_series import EpisodePhase
from trendforge.services.mini_series.guardrails import GUARDRAILS
from trendforge.services.projects import ProjectStore
from trendforge.settings import AppSettings
from trendforge.ui.main_window import MainWindow


def _dirs(tmp_path) -> AppDirs:
    root = tmp_path / "home"
    dirs = AppDirs(
        root=root,
        projects=root / "projects",
        gallery=root / "gallery",
        cache=root / "cache",
        logs=root / "logs",
        models=root / "models",
        music=root / "music",
        tmp=root / "tmp",
        settings_file=root / "settings.json",
    )
    for path in (
        dirs.root,
        dirs.projects,
        dirs.gallery,
        dirs.cache,
        dirs.logs,
        dirs.models,
        dirs.music,
        dirs.tmp,
    ):
        path.mkdir(parents=True, exist_ok=True)
    return dirs


def _wait_idle(page, timeout: float = 25) -> None:
    app = QApplication.instance()
    assert app is not None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        worker = page._worker
        running = worker is not None and worker.isRunning()
        if page._busy or running:
            time.sleep(0.02)
            continue
        app.processEvents()
        return
    raise AssertionError(f"Mini Series page stayed busy: {page.status.text()}")


def test_mini_series_page_approve_produce_and_draft(tmp_path):
    app = QApplication.instance() or QApplication([])
    settings = AppSettings(channel_name="Signal Cut", cinema_dry_run=True)
    window = MainWindow(settings, _dirs(tmp_path))
    window.show()
    app.processEvents()

    mini_nav = next(btn for btn in window.nav_btns if btn.text() == "Mini Series")
    mini_nav.click()
    app.processEvents()
    page = window.mini
    assert window.stack.currentWidget() is page

    page.findChild(QLineEdit, "miniSeriesTitle").setText("Night Desk")
    page.findChild(QLineEdit, "miniSeriesTopic").setText("warehouse fire")
    page.findChild(QPushButton, "miniStartSeries").click()
    app.processEvents()
    assert page.series is not None
    assert page.episode is not None
    assert page.episode.phase is EpisodePhase.BRIEF

    page.findChild(QPlainTextEdit, "miniStoryline").setPlainText(
        "A warehouse fire spreads overnight and a court filing names the contractor."
    )
    page.findChild(QPlainTextEdit, "miniGoals").setPlainText(
        "Show the timeline and the questions viewers still have."
    )
    page.findChild(QPlainTextEdit, "miniNotes").setPlainText("Keep the narration descriptive.")
    for item in GUARDRAILS:
        box = page.findChild(QCheckBox, f"guardrail_{item.id}")
        assert box is not None
        box.setChecked(True)

    assert page.findChild(QPushButton, "miniProduce").isEnabled() is False
    page.findChild(QPushButton, "miniApprove").click()
    app.processEvents()
    assert page.episode.phase is EpisodePhase.APPROVED
    assert page.episode.meeting.approved is True
    assert page.findChild(QPushButton, "miniProduce").isEnabled() is True
    assert page.findChild(QPushButton, "miniPublish").isEnabled() is False

    page.findChild(QPushButton, "miniProduce").click()
    _wait_idle(page)
    assert page.episode.phase is EpisodePhase.RENDER_READY
    assert page.episode.project_id
    assert page.findChild(QPlainTextEdit, "miniOutline").toPlainText().strip()
    project = page.projects.load(page.episode.project_id)
    assert project.request.backend is BackendKind.NATIVE_CINEMA
    assert project.request.model_id == "viralforge_cinema"

    render = page.findChild(QPushButton, "miniRender")
    assert render.isEnabled() is False
    assert "text cards" in render.toolTip()

    page.findChild(QPushButton, "miniPublish").click()
    app.processEvents()
    assert page.episode.phase is EpisodePhase.MONITORING
    assert page.episode.monitor_until
    assert "Watching until" in page.monitor_label.text()

    page.findChild(QPlainTextEdit, "miniPaste").setPlainText(
        "\n".join(
            [
                "Ava: The warehouse scene should be its own chapter",
                "Ben | More on the warehouse night shift | 3",
                "Cara: The court filing is the real story",
                "Spam: subscribe to my channel http://spam.test",
            ]
        )
    )
    page.findChild(QPushButton, "miniRank").click()
    app.processEvents()
    assert page.episode.themes
    assert page.episode.themes[0].theme == "warehouse"
    assert page.findChild(QPushButton, "miniDraftNext").isEnabled() is True

    page.findChild(QPushButton, "miniDraftNext").click()
    _wait_idle(page)
    assert page.series is not None
    assert len(page.series.episodes) == 2
    nxt = page.series.episodes[1]
    assert page.episode is nxt
    assert nxt.phase is EpisodePhase.IN_MEETING
    assert nxt.meeting.approved is False
    assert page.findChild(QPushButton, "miniProduce").isEnabled() is False
    assert "warehouse" in nxt.topic

    window.close()
