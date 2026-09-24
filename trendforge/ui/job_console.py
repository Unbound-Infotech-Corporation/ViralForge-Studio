"""Docked Job Console for Produce progress."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QDockWidget, QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from trendforge.settings import AppSettings


class JobConsole(QDockWidget):
    def __init__(self, settings: AppSettings, parent=None) -> None:
        super().__init__("Job Console", parent)
        self.settings = settings
        self.setObjectName("jobConsole")
        self.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.TopDockWidgetArea)

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(8, 8, 8, 8)
        hint = QLabel("Open this panel from View → Job Console, the status-bar Console button, or Ctrl+`.")
        hint.setObjectName("subtitle")
        hint.setWordWrap(True)
        self.show_on_produce = QCheckBox("Show when Produce starts")
        self.show_on_produce.setChecked(bool(settings.show_console_on_produce))
        self.show_on_produce.toggled.connect(self._save_pref)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("Produce progress lands here.")
        layout.addWidget(hint)
        layout.addWidget(self.show_on_produce)
        layout.addWidget(self.log, 1)
        self.setWidget(body)
        self.append_line("Job Console ready.")

    def _save_pref(self, checked: bool) -> None:
        self.settings.show_console_on_produce = bool(checked)
        try:
            self.settings.save()
        except Exception:
            pass

    def append_line(self, text: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log.appendPlainText(f"{stamp}  {text}")
        bar = self.log.verticalScrollBar()
        bar.setValue(bar.maximum())
