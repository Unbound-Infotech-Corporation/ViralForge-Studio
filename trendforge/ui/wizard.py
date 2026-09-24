from __future__ import annotations

import webbrowser

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from trendforge.bootstrap import AppDirs
from trendforge.domain.enums import BrandVoice
from trendforge.services.hardware import detect_hardware
from trendforge.settings import AppSettings
from trendforge.ui.install_panel import InstallPanel


class _Intro(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Welcome to TrendForge Studio")
        lay = QVBoxLayout(self)
        t = QLabel(
            "Build a YouTube channel from one app: Shorts, long narrated videos, and multi-episode docuseries.\n\n"
            "This wizard detects your GPU, saves your channel voice, and downloads the free local models you check — "
            "Piper narration, Whisper captions, and Ollama scripts. "
            "Wan and CogVideoX weights go in the cinema models folder; Studio will not publish title-card stand-ins."
        )
        t.setWordWrap(True)
        lay.addWidget(t)


class _Hardware(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Your hardware")
        self.body = QLabel()
        self.body.setWordWrap(True)
        lay = QVBoxLayout(self)
        lay.addWidget(self.body)

    def initializePage(self) -> None:
        hw = detect_hardware()
        lines = [
            f"<b>GPU:</b> {hw.gpu_name}",
            f"<b>VRAM:</b> {hw.vram_total_gb} GB total, {hw.vram_free_gb} GB free" if hw.cuda_available else "<b>VRAM:</b> no NVIDIA GPU detected",
            f"<b>System RAM:</b> {hw.ram_available_gb} / {hw.ram_total_gb} GB available",
            f"<b>Recommended video path:</b> {hw.recommended_backend.value} / {hw.recommended_model_id}",
        ]
        lines += [f"• {n}" for n in hw.notes]
        self.body.setText("<br>".join(lines))


class _Channel(QWizardPage):
    def __init__(self, settings: AppSettings) -> None:
        super().__init__()
        self.settings = settings
        self.setTitle("Your channel")
        self.setSubTitle("Used in titles, outros, pinned comments, and docuseries continuity.")
        form = QFormLayout(self)
        self.name = QLineEdit(settings.channel_name)
        self.name.setPlaceholderText("e.g. Signal Cut")
        self.niche = QLineEdit(settings.channel_niche)
        self.niche.setPlaceholderText("e.g. tech + culture breakdowns")
        self.audience = QLineEdit(settings.channel_audience)
        self.audience.setPlaceholderText("e.g. curious people who hate fluff")
        self.cta = QLineEdit(settings.channel_cta)
        self.series = QLineEdit(settings.series_title)
        self.series.setPlaceholderText("Optional flagship series name")
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

    def save_into(self) -> None:
        self.settings.channel_name = self.name.text().strip()
        self.settings.channel_niche = self.niche.text().strip()
        self.settings.channel_audience = self.audience.text().strip()
        if self.cta.text().strip():
            self.settings.channel_cta = self.cta.text().strip()
        self.settings.series_title = self.series.text().strip()
        self.settings.brand_voice = BrandVoice(self.voice.currentData())


class _Install(QWizardPage):
    def __init__(self, settings: AppSettings, dirs: AppDirs) -> None:
        super().__init__()
        self.setTitle("Install models")
        self.setSubTitle(
            "Everything this PC can run is pre-checked. Uncheck what you do not want. "
            "Ollama script models need Ollama already running. No cloud API key."
        )
        lay = QVBoxLayout(self)
        links = QLabel(
            'Optional: keep <a href="https://ollama.com/download">Ollama</a> running for local Script AI. '
            "Cinematic video uses ViralForge Cinema. Put CogVideoX weights in the cinema models folder "
            "(<code>cogvideox</code>, beside Wan)."
        )
        links.setOpenExternalLinks(True)
        self.panel = InstallPanel(settings, dirs)
        pin = QPushButton("Open Ollama download page")
        pin.clicked.connect(lambda: webbrowser.open("https://ollama.com/download"))
        lay.addWidget(links)
        lay.addWidget(pin)
        lay.addWidget(self.panel)


class _Done(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("You're ready to grow a channel")
        lab = QLabel(
            "Create → pick a format from the dropdown:\n"
            "• YouTube Short for daily hooks\n"
            "• Standard / Long for subscriber sessions\n"
            "• Docuseries episode for narrated deep dives\n"
            "• Plan a season to outline 4–6 episodes, then generate each one\n\n"
            "Switch models anytime with the Model dropdown. Auto is fine for beginners.\n"
            "Job Console: View → Job Console, the status-bar Console button, or Ctrl+`."
        )
        lab.setWordWrap(True)
        lay = QVBoxLayout(self)
        lay.addWidget(lab)


class SetupWizard(QWizard):
    def __init__(self, settings: AppSettings, dirs: AppDirs, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.dirs = dirs
        self.setWindowTitle("TrendForge Studio setup")
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)
        self.addPage(_Intro())
        self.addPage(_Hardware())
        self.channel_page = _Channel(settings)
        self.addPage(self.channel_page)
        self.addPage(_Install(settings, dirs))
        self.addPage(_Done())
        self.resize(820, 680)

    def accept(self) -> None:
        self.channel_page.save_into()
        self.settings.wizard_complete = True
        self.settings.save()
        super().accept()
