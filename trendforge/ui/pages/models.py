from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from trendforge.bootstrap import AppDirs
from trendforge.domain.enums import ThemeMode
from trendforge.domain.catalog import dropdown_label, visible_model_catalog
from trendforge.logging_setup import read_log_tail
from trendforge.services.hardware import detect_hardware
from trendforge.services.ollama_client import OllamaClient
from trendforge.services.comfyui_client import ComfyUIClient
from trendforge.settings import AppSettings
from trendforge.ui.install_panel import InstallPanel
from trendforge.ui.script_ai_settings import ScriptAiSettingsForm
from trendforge.ui.theme import apply_theme


class ModelsPage(QWidget):
    catalogs_updated = Signal()

    def __init__(self, settings: AppSettings, dirs: AppDirs, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.dirs = dirs
        root = QVBoxLayout(self)
        title = QLabel("Models & Settings")
        title.setObjectName("title")
        sub = QLabel(
            "Install local models here (same list as first-run setup). "
            "Then pick them from the Create dropdowns — labels include VRAM, disk, and speed."
        )
        sub.setObjectName("subtitle")
        sub.setWordWrap(True)

        self.tabs = QTabWidget()
        tabs = self.tabs
        self.install = InstallPanel(settings, dirs)
        self.install.finished.connect(self._on_installed)

        conn = QWidget()
        conn_l = QVBoxLayout(conn)
        self.status = QTextEdit()
        self.status.setReadOnly(True)
        refresh = QPushButton("Re-detect stack")
        refresh.clicked.connect(self.refresh_status)
        row = QHBoxLayout()
        row.addWidget(refresh)
        row.addStretch()

        form = QFormLayout()
        self.cinema_dir = QLineEdit(settings.cinema_models_dir)
        self.cinema_dir.setPlaceholderText(r"F:\TrendForge\models\cinema")
        self.ollama_url = QLineEdit(settings.ollama_url)
        self.ollama_model = QComboBox()
        self.ollama_model.setEditable(True)
        self.comfy_url = QLineEdit(settings.comfyui_url)
        self.ffmpeg = QLineEdit(settings.ffmpeg_path)
        self.theme = QComboBox()
        self.theme.addItem("Dark", ThemeMode.DARK.value)
        self.theme.addItem("Light", ThemeMode.LIGHT.value)
        self.theme.setCurrentIndex(0 if settings.theme is ThemeMode.DARK else 1)
        self.cloud = QCheckBox("Enable optional free-cloud fallbacks (Edge TTS). Disabled by default.")
        self.cloud.setChecked(settings.paid_fallbacks_enabled)
        form.addRow("Cinema models folder", self.cinema_dir)
        form.addRow("Ollama URL", self.ollama_url)
        form.addRow("Script model", self.ollama_model)
        form.addRow("ComfyUI URL", self.comfy_url)
        form.addRow("ffmpeg path", self.ffmpeg)
        form.addRow("Theme", self.theme)
        form.addRow(self.cloud)
        save = QPushButton("Save settings")
        save.clicked.connect(self._save)
        box = QGroupBox("Connection")
        box.setLayout(form)
        conn_l.addLayout(row)
        conn_l.addWidget(self.status, 1)
        conn_l.addWidget(box)
        conn_l.addWidget(save)

        catalog = QTextEdit()
        catalog.setReadOnly(True)
        lines = []
        for m in visible_model_catalog():
            paid = " [OPTIONAL/PAID]" if m.is_paid else ""
            lines.append(
                f"{dropdown_label(m)}{paid}\n  Backend: {m.backend.value} · Quality {m.quality}/5\n  {m.description}\n"
            )
        catalog.setPlainText("\n".join(lines))
        logs_btn = QPushButton("Copy logs")
        logs_btn.clicked.connect(self._copy_logs)
        cat_w = QWidget()
        cat_l = QVBoxLayout(cat_w)
        cat_l.addWidget(QLabel("Create → Model dropdown (legacy engines hidden)"))
        cat_l.addWidget(catalog, 1)
        cat_l.addWidget(logs_btn)

        self.script_ai = ScriptAiSettingsForm(settings)
        tabs.addTab(self.install, "Install models")
        tabs.addTab(conn, "Connection")
        tabs.addTab(self.script_ai, "Script AI")
        tabs.addTab(cat_w, "Catalog")

        root.addWidget(title)
        root.addWidget(sub)
        root.addWidget(tabs, 1)
        self.refresh_status()

    def focus_script_ai(self) -> None:
        self.tabs.setCurrentWidget(self.script_ai)
        self.script_ai.load_from_settings()

    def reload_script_ai(self) -> None:
        self.script_ai.load_from_settings()

    def refresh_status(self) -> None:
        hw = detect_hardware()
        oll = OllamaClient(self.settings.ollama_url).status()
        comfy = ComfyUIClient(self.settings.comfyui_url).ping()
        current = self.ollama_model.currentText().strip() or self.settings.ollama_model
        self.ollama_model.blockSignals(True)
        self.ollama_model.clear()
        self.ollama_model.addItem("(auto — first local model)", "")
        for name in oll.models:
            self.ollama_model.addItem(name, name)
        self.ollama_model.blockSignals(False)
        if current:
            idx = self.ollama_model.findData(current) if current else 0
            if idx < 0:
                idx = self.ollama_model.findText(current)
            if idx >= 0:
                self.ollama_model.setCurrentIndex(idx)
            elif current:
                self.ollama_model.setEditText(current)
        lines = [
            f"GPU: {hw.gpu_name}",
            f"VRAM: {hw.vram_free_gb} / {hw.vram_total_gb} GB",
            f"RAM: {hw.ram_available_gb} / {hw.ram_total_gb} GB",
            f"Recommended: {hw.recommended_backend.value} / {hw.recommended_model_id}",
            f"Cinema models: {self.settings.cinema_models_dir}",
            "  CogVideoX → cogvideox    Wan 5B → wan2.2-ti2v-5b    Wan A14B → wan2.2-i2v",
            "Job Console: View → Job Console, status-bar Console, or Ctrl+`",
            "",
            f"Ollama script model: {'yes — ' + ', '.join(oll.models[:8]) if oll.running else 'no (install from ollama.com — no cloud API key)'}",
            f"ComfyUI (legacy, hidden from Create): {'yes' if comfy else 'no'} at {self.settings.comfyui_url}",
        ]
        self.status.setPlainText("\n".join(lines))
        if not (self.install._worker and self.install._worker.isRunning()):
            self.install.reload()

    def _on_installed(self, _notes: list) -> None:
        self.refresh_status()
        self.catalogs_updated.emit()

    def _save(self) -> None:
        self.settings.cinema_models_dir = self.cinema_dir.text().strip() or self.settings.cinema_models_dir
        self.settings.ollama_url = self.ollama_url.text().strip() or "http://127.0.0.1:11434"
        self.settings.ollama_model = self.ollama_model.currentText().strip()
        if self.settings.ollama_model.startswith("(auto"):
            self.settings.ollama_model = ""
        self.settings.comfyui_url = self.comfy_url.text().strip() or "http://127.0.0.1:8188"
        self.settings.ffmpeg_path = self.ffmpeg.text().strip()
        self.settings.theme = ThemeMode(self.theme.currentData())
        self.settings.paid_fallbacks_enabled = self.cloud.isChecked()
        self.settings.save()
        from PySide6.QtWidgets import QApplication

        apply_theme(QApplication.instance(), self.settings.theme)  # type: ignore[arg-type]
        QMessageBox.information(self, "Saved", "Settings saved.")
        self.refresh_status()
        self.catalogs_updated.emit()

    def _copy_logs(self) -> None:
        text = read_log_tail(self.dirs.logs / "trendforge.log")
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(text)
        QMessageBox.information(self, "Logs", "Log tail copied to clipboard.")
