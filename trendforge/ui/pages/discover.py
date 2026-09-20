from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from trendforge.domain.enums import TrendCategory
from trendforge.domain.models import TrendItem
from trendforge.services.trends import fetch_category, search_topics
from trendforge.ui.widgets import TrendCard
from trendforge.ui.workers import FnWorker


class DiscoverPage(QWidget):
    topic_chosen = Signal(object)

    def __init__(self, region: str = "US", parent=None) -> None:
        super().__init__(parent)
        self.region = region
        self._workers: list[FnWorker] = []
        root = QVBoxLayout(self)
        kicker = QLabel("DISCOVER")
        kicker.setObjectName("kicker")
        title = QLabel("What's trending right now")
        title.setObjectName("title")
        sub = QLabel("Free public sources: YouTube, Google Trends, Reddit, news RSS. Click any card to start a video.")
        sub.setObjectName("subtitle")
        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search a topic or paste a YouTube URL…")
        go = QPushButton("Search")
        go.setObjectName("primary")
        go.clicked.connect(self._search)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.reload)
        search_row.addWidget(self.search, 1)
        search_row.addWidget(go)
        search_row.addWidget(refresh)
        self.tabs = QTabWidget()
        self._hosts: dict[TrendCategory, QVBoxLayout] = {}
        for cat, label in (
            (TrendCategory.YOUTUBE, "YouTube"),
            (TrendCategory.NEWS, "News"),
            (TrendCategory.MOVIES_TV, "Movies & TV"),
            (TrendCategory.VIRAL, "Viral"),
            (TrendCategory.CUSTOM, "Search results"),
        ):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            host = QWidget()
            lay = QVBoxLayout(host)
            lay.addStretch()
            scroll.setWidget(host)
            self._hosts[cat] = lay
            self.tabs.addTab(scroll, label)
        self.status = QLabel("Loading trends…")
        self.status.setObjectName("subtitle")
        root.addWidget(kicker)
        root.addWidget(title)
        root.addWidget(sub)
        root.addLayout(search_row)
        root.addWidget(self.tabs, 1)
        root.addWidget(self.status)

    def reload(self) -> None:
        self.status.setText("Refreshing…")
        for cat in (TrendCategory.YOUTUBE, TrendCategory.NEWS, TrendCategory.MOVIES_TV, TrendCategory.VIRAL):
            self._load(cat)

    def _load(self, category: TrendCategory) -> None:
        worker = FnWorker(lambda c=category: fetch_category(c, self.region))
        worker.ok.connect(lambda items, c=category: self._fill(c, items))
        worker.failed.connect(lambda msg, c=category: self._fill(c, [], msg))
        self._workers.append(worker)
        worker.start()

    def _search(self) -> None:
        q = self.search.text().strip()
        if not q:
            return
        self.status.setText("Searching…")
        worker = FnWorker(lambda: search_topics(q))
        worker.ok.connect(lambda items: self._fill(TrendCategory.CUSTOM, items))
        worker.failed.connect(lambda msg: self.status.setText(msg))
        self._workers.append(worker)
        worker.start()
        self.tabs.setCurrentIndex(4)

    def _fill(self, category: TrendCategory, items: list[TrendItem], error: str = "") -> None:
        lay = self._hosts[category]
        while lay.count() > 1:
            item = lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        if error:
            self.status.setText(error)
        elif not items:
            empty = QLabel("Nothing here yet. Try Refresh or Search.")
            empty.setObjectName("subtitle")
            lay.insertWidget(0, empty)
            self.status.setText("Some sources returned no items (network or rate limit).")
        else:
            for trend in items:
                lay.insertWidget(lay.count() - 1, TrendCard(trend, self._use))
            self.status.setText(f"Loaded {len(items)} items for {category.value}.")

    def _use(self, item: TrendItem) -> None:
        self.topic_chosen.emit(item)
