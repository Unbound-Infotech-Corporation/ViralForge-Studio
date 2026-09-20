from __future__ import annotations

import webbrowser

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
from trendforge.domain.catalog import dropdown_label, model_catalog
from trendforge.logging_setup import read_log_tail
from trendforge.services.hardware import detect_hardware
from trendforge.services.maestro_detect import detect_maestro
from trendforge.services.ollama_client import OllamaClient
from trendforge.services.comfyui_client import ComfyUIClient
from trendforge.settings import AppSettings
from trendforge.ui.install_panel import InstallPanel
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

        tabs = QTabWidget()
        self.install = InstallPanel(settings, dirs)
        self.install.finished.connect(self._on_installed)

        conn = QWidget()
        conn_l = QVBoxLayout(conn)
        self.status = QTextEdit()
        self.status.setReadOnly(True)
        refresh = QPushButton("Re-detect stack")
        refresh.clicked.connect(self.refresh_status)
        pin = QPushButton("Start Maestro")
        pin.clicked.connect(self._start_maestro)
        row = QHBoxLayout()
        row.addWidget(refresh)
        row.addWidget(pin)
        row.addStretch()

        form = QFormLayout()
        self.maestro_url = QLineEdit(settings.maestro_url)
        self.maestro_url.setPlaceholderText("Leave blank to auto-detect")
        self.pinokio_home = QLineEdit(settings.pinokio_path)
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
        form.addRow("Maestro URL", self.maestro_url)
        form.addRow("Maestro install folder", self.pinokio_home)
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
        for m in model_catalog():
            paid = " [OPTIONAL/PAID]" if m.is_paid else ""
            lines.append(
                f"{dropdown_label(m)}{paid}\n  Backend: {m.backend.value} · Quality {m.quality}/5\n  {m.description}\n"
            )
        catalog.setPlainText("\n".join(lines))
        logs_btn = QPushButton("Copy logs")
        logs_btn.clicked.connect(self._copy_logs)
        cat_w = QWidget()
        cat_l = QVBoxLayout(cat_w)
        cat_l.addWidget(QLabel("Create → Model dropdown (same catalog)"))
        cat_l.addWidget(catalog, 1)
        cat_l.addWidget(logs_btn)

        tabs.addTab(self.install, "Install models")
        tabs.addTab(conn, "Connection")
        tabs.addTab(cat_w, "Catalog")

        root.addWidget(title)
        root.addWidget(sub)
        root.addWidget(tabs, 1)
        self.refresh_status()

    def refresh_status(self) -> None:
        hw = detect_hardware()
        inst = detect_maestro(self.settings.maestro_url, self.settings.pinokio_path)
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
            "",
            *inst.notes,
            "",
            f"Ollama: {'yes — ' + ', '.join(oll.models[:8]) if oll.running else 'no (install from ollama.com, then pull in Install models)'}",
            f"ComfyUI: {'yes' if comfy else 'no'} at {self.settings.comfyui_url}",
        ]
        self.status.setPlainText("\n".join(lines))
        if inst.running_url:
            self.maestro_url.setPlaceholderText(inst.running_url)
        if inst.pinokio_home:
            self.pinokio_home.setPlaceholderText(str(inst.pinokio_home))
        if not (self.install._worker and self.install._worker.isRunning()):
            self.install.reload()

    def _on_installed(self, _notes: list) -> None:
        self.refresh_status()
        self.catalogs_updated.emit()

    def _save(self) -> None:
        self.settings.maestro_url = self.maestro_url.text().strip()
        self.settings.pinokio_path = self.pinokio_home.text().strip()
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

    def _start_maestro(self) -> None:
        """Launch Maestro standalone (no Pinokio). Prefer repo start_maestro.bat."""
        import os
        import subprocess
        from pathlib import Path

        candidates = [
            Path(__file__).resolve().parents[3] / "start_maestro.bat",
            Path(r"F:\ViralForge\VisualCreatorUnbound\start_maestro.bat"),
        ]
        bat = next((p for p in candidates if p.exists()), None)
        if bat is not None:
            subprocess.Popen(["cmd", "/c", "start", "", str(bat)], shell=False)
            return
        # Fallback: launch.py in detected Maestro app folder
        inst = detect_maestro(self.settings.maestro_url, self.settings.pinokio_path)
        root = inst.maestro_root
        if root is None and self.settings.pinokio_path:
            root = Path(self.settings.pinokio_path) / "api" / "Maestro.git"
        app = (Path(root) / "app") if root else None
        if app and (app / "launch.py").exists():
            py = app / "env-rtx50" / "Scripts" / "python.exe"
            if not py.exists():
                py = app / "env" / "Scripts" / "python.exe"
            env = os.environ.copy()
            env["SERVER_PORT"] = "42130"
            env["SERVER_NAME"] = "127.0.0.1"
            subprocess.Popen([str(py), "launch.py"], cwd=str(app), env=env)
            return
        webbrowser.open("http://127.0.0.1:42130")

    def _copy_logs(self) -> None:
        text = read_log_tail(self.dirs.logs / "trendforge.log")
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(text)
        QMessageBox.information(self, "Logs", "Log tail copied to clipboard.")
