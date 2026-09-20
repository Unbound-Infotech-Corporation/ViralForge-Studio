from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from trendforge.domain.enums import PipelineStage
from trendforge.domain.models import TrendItem


class Card(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)


class TrendCard(Card):
    def __init__(self, item: TrendItem, on_use, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        kicker = QLabel(f"{item.source}  ·  {item.score_label or item.category.value}")
        kicker.setObjectName("kicker")
        title = QLabel(item.title)
        title.setWordWrap(True)
        title.setObjectName("title")
        title.setStyleSheet("font-size: 16px; font-weight: 650;")
        summary = QLabel(item.summary[:180] if item.summary else item.url)
        summary.setWordWrap(True)
        summary.setObjectName("subtitle")
        btn = QPushButton("Create breakdown video")
        btn.setObjectName("primary")
        btn.clicked.connect(lambda: on_use(item))
        layout.addWidget(kicker)
        layout.addWidget(title)
        layout.addWidget(summary)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignLeft)


class PipelineStrip(QWidget):
    STAGES = [
        (PipelineStage.RESEARCH, "Research"),
        (PipelineStage.SCRIPT, "Script"),
        (PipelineStage.GENERATE, "Generate"),
        (PipelineStage.STITCH, "Stitch"),
        (PipelineStage.FINALIZE, "Finalize"),
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._labels: dict[PipelineStage, QLabel] = {}
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        for i, (stage, name) in enumerate(self.STAGES):
            lab = QLabel(f"{i + 1}. {name}")
            lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lab.setStyleSheet("padding: 8px; border-radius: 8px; background: #1A1D27; color: #8B93A7;")
            self._labels[stage] = lab
            row.addWidget(lab)

    def set_stage(self, stage: PipelineStage) -> None:
        reached = False
        for st, lab in self._labels.items():
            if st is stage:
                lab.setStyleSheet("padding: 8px; border-radius: 8px; background: #E8A54B; color: #1A1208; font-weight: 700;")
                reached = True
            elif not reached:
                lab.setStyleSheet("padding: 8px; border-radius: 8px; background: #2A4A38; color: #3DDC97;")
            else:
                lab.setStyleSheet("padding: 8px; border-radius: 8px; background: #1A1D27; color: #8B93A7;")
        if stage in {PipelineStage.DONE}:
            for lab in self._labels.values():
                lab.setStyleSheet("padding: 8px; border-radius: 8px; background: #2A4A38; color: #3DDC97;")
        if stage in {PipelineStage.FAILED, PipelineStage.CANCELLED}:
            for lab in self._labels.values():
                lab.setStyleSheet("padding: 8px; border-radius: 8px; background: #3A2222; color: #FF8A8A;")
