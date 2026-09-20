from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from trendforge.domain.models import Project
from trendforge.services.projects import ProjectStore


class ProjectsPage(QWidget):
    open_project = Signal(object)

    def __init__(self, store: ProjectStore, parent=None) -> None:
        super().__init__(parent)
        self.store = store
        root = QVBoxLayout(self)
        title = QLabel("Projects")
        title.setObjectName("title")
        self.list = QListWidget()
        btns = QHBoxLayout()
        refresh = QPushButton("Refresh")
        open_btn = QPushButton("Open folder")
        play = QPushButton("Play output")
        delete = QPushButton("Delete")
        refresh.clicked.connect(self.reload)
        open_btn.clicked.connect(self._open_folder)
        play.clicked.connect(self._play)
        delete.clicked.connect(self._delete)
        btns.addWidget(refresh)
        btns.addWidget(open_btn)
        btns.addWidget(play)
        btns.addWidget(delete)
        btns.addStretch()
        root.addWidget(title)
        root.addWidget(self.list, 1)
        root.addLayout(btns)
        self.reload()

    def reload(self) -> None:
        self.list.clear()
        for project in self.store.list_projects():
            label = f"{project.title}  ·  {project.stage.value}  ·  {project.updated_at[:19].replace('T', ' ')}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, project.id)
            self.list.addItem(item)

    def _current(self) -> Project | None:
        item = self.list.currentItem()
        if not item:
            return None
        try:
            return self.store.load(item.data(Qt.ItemDataRole.UserRole))
        except Exception as exc:
            QMessageBox.warning(self, "Load failed", str(exc))
            return None

    def _open_folder(self) -> None:
        project = self._current()
        if project and project.folder:
            os.startfile(project.folder)  # type: ignore[attr-defined]

    def _play(self) -> None:
        project = self._current()
        if project and project.output_path and Path(project.output_path).exists():
            os.startfile(project.output_path)  # type: ignore[attr-defined]
        else:
            QMessageBox.information(self, "No output", "This project has no finished MP4 yet.")

    def _delete(self) -> None:
        project = self._current()
        if not project:
            return
        if QMessageBox.question(self, "Delete project", f"Delete {project.title}?") == QMessageBox.StandardButton.Yes:
            self.store.delete(project.id)
            self.reload()
