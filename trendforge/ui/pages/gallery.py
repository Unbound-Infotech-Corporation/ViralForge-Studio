from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget

from trendforge.services.projects import ProjectStore


class GalleryPage(QWidget):
    def __init__(self, store: ProjectStore, parent=None) -> None:
        super().__init__(parent)
        self.store = store
        root = QVBoxLayout(self)
        title = QLabel("Gallery")
        title.setObjectName("title")
        sub = QLabel("Finished MP4s from your local projects.")
        sub.setObjectName("subtitle")
        self.list = QListWidget()
        play = QPushButton("Play selected")
        play.setObjectName("primary")
        play.clicked.connect(self._play)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.reload)
        root.addWidget(title)
        root.addWidget(sub)
        root.addWidget(self.list, 1)
        root.addWidget(play)
        root.addWidget(refresh)
        self.reload()

    def reload(self) -> None:
        self.list.clear()
        for path in self.store.gallery_videos():
            item = QListWidgetItem(str(path))
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self.list.addItem(item)

    def _play(self) -> None:
        item = self.list.currentItem()
        if not item:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        if path and Path(path).exists():
            os.startfile(path)  # type: ignore[attr-defined]
