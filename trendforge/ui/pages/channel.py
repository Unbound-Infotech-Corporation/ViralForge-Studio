from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from trendforge.domain.enums import BrandVoice
from trendforge.settings import AppSettings


class ChannelPage(QWidget):
    saved = Signal()

    def __init__(self, settings: AppSettings, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        root = QVBoxLayout(self)
        kicker = QLabel("CHANNEL")
        kicker.setObjectName("kicker")
        title = QLabel("Make uploads feel like one show")
        title.setObjectName("title")
        sub = QLabel(
            "Name, niche, and CTA are written into outros, pinned comments, "
            "thumbnails, and docuseries continuity. Save once — Create uses them automatically."
        )
        sub.setObjectName("subtitle")
        sub.setWordWrap(True)

        form = QFormLayout()
        self.name = QLineEdit(settings.channel_name)
        self.name.setPlaceholderText("e.g. Signal Cut")
        self.niche = QLineEdit(settings.channel_niche)
        self.niche.setPlaceholderText("e.g. tech + culture breakdowns")
        self.audience = QLineEdit(settings.channel_audience)
        self.audience.setPlaceholderText("e.g. curious people who hate fluff")
        self.cta = QLineEdit(settings.channel_cta)
        self.series = QLineEdit(settings.series_title)
        self.series.setPlaceholderText("Flagship docuseries name")
        self.voice = QComboBox()
        for v in BrandVoice:
            self.voice.addItem(v.value.replace("_", " ").title(), v.value)
        idx = self.voice.findData(settings.brand_voice.value)
        if idx >= 0:
            self.voice.setCurrentIndex(idx)
        form.addRow("Channel name", self.name)
        form.addRow("Niche", self.niche)
        form.addRow("Audience", self.audience)
        form.addRow("Subscribe CTA", self.cta)
        form.addRow("Brand voice", self.voice)
        form.addRow("Docuseries name", self.series)

        box = QGroupBox("Brand kit")
        box.setLayout(form)

        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMaximumHeight(180)
        for widget in (self.name, self.niche, self.audience, self.cta, self.series):
            widget.textChanged.connect(self._preview)
        self.voice.currentIndexChanged.connect(self._preview)

        save = QPushButton("Save channel kit")
        save.setObjectName("primary")
        save.clicked.connect(self._save)

        root.addWidget(kicker)
        root.addWidget(title)
        root.addWidget(sub)
        root.addWidget(box)
        root.addWidget(QLabel("How this shows up on YouTube"))
        root.addWidget(self.preview)
        root.addWidget(save)
        root.addStretch()
        self._preview()

    def reload(self) -> None:
        self.name.setText(self.settings.channel_name)
        self.niche.setText(self.settings.channel_niche)
        self.audience.setText(self.settings.channel_audience)
        self.cta.setText(self.settings.channel_cta)
        self.series.setText(self.settings.series_title)
        idx = self.voice.findData(self.settings.brand_voice.value)
        if idx >= 0:
            self.voice.setCurrentIndex(idx)
        self._preview()

    def _preview(self) -> None:
        name = self.name.text().strip() or "Your channel"
        niche = self.niche.text().strip() or "trending breakdowns"
        cta = self.cta.text().strip() or "Subscribe for the next episode."
        series = self.series.text().strip() or f"{name} Investigations"
        voice = (self.voice.currentData() or "documentary").replace("_", " ")
        self.preview.setPlainText(
            f"End screen: {cta}\n"
            f"Pinned comment: New on {name} — {niche}. {cta}\n"
            f"Community post: {series} episode is live.\n"
            f"Narration voice: {voice}\n"
            f"Thumbnail kicker: {name.upper()}"
        )

    def _save(self) -> None:
        self.settings.channel_name = self.name.text().strip()
        self.settings.channel_niche = self.niche.text().strip()
        self.settings.channel_audience = self.audience.text().strip()
        if self.cta.text().strip():
            self.settings.channel_cta = self.cta.text().strip()
        self.settings.series_title = self.series.text().strip()
        self.settings.brand_voice = BrandVoice(self.voice.currentData())
        self.settings.save()
        QMessageBox.information(self, "Saved", "Channel kit saved. Create will use it on the next generate.")
        self.saved.emit()
