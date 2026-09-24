"""Settings → Script AI form. Shared by Models and Script Lab."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from trendforge.domain.enums import ScriptAiProvider
from trendforge.services.script_ai import (
    PROVIDER_ORDER,
    SPECS,
    known_default_base,
    known_default_model,
)
from trendforge.settings import AppSettings

HELP = (
    "Script AI calls the provider API with your own key. A subscription on grok.com, "
    "chatgpt.com, or claude.ai does not unlock that API — those sites are only the "
    "Script Lab browser. The key is saved in local settings.json and is not written to the log. "
    "Ollama runs on this machine and does not need a cloud key. Base URL overrides the default host."
)


class ScriptAiSettingsForm(QWidget):
    saved = Signal()

    def __init__(self, settings: AppSettings, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        root = QVBoxLayout(self)
        help_label = QLabel(HELP)
        help_label.setObjectName("subtitle")
        help_label.setWordWrap(True)

        form = QFormLayout()
        self.provider = QComboBox()
        for kind in PROVIDER_ORDER:
            self.provider.addItem(SPECS[kind].label, kind.value)
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("Paste an API key — chat login is not enough")
        self.show_key = QCheckBox("Show API key")
        self.show_key.toggled.connect(self._toggle_key)
        self.base_url = QLineEdit()
        self.model = QLineEdit()
        form.addRow("Provider", self.provider)
        form.addRow("API key", self.api_key)
        form.addRow("", self.show_key)
        form.addRow("Base URL", self.base_url)
        form.addRow("Model", self.model)

        box = QGroupBox("Script AI")
        box.setLayout(form)
        save = QPushButton("Save Script AI")
        save.setObjectName("primary")
        save.clicked.connect(self._save)
        self.provider.currentIndexChanged.connect(self._on_provider_changed)

        root.addWidget(help_label)
        root.addWidget(box)
        root.addWidget(save)
        root.addStretch()
        self.load_from_settings()

    def load_from_settings(self) -> None:
        provider = self.settings.script_ai_provider
        if provider not in SPECS:
            provider = ScriptAiProvider.OLLAMA
        index = self.provider.findData(provider.value)
        self.provider.blockSignals(True)
        if index >= 0:
            self.provider.setCurrentIndex(index)
        self.provider.blockSignals(False)
        self.api_key.setText(self.settings.script_ai_api_key)
        self.base_url.setText(self.settings.script_ai_base_url)
        self.model.setText(self.settings.script_ai_model)
        self._apply_placeholders()

    def _current_provider(self) -> ScriptAiProvider:
        try:
            return ScriptAiProvider(self.provider.currentData())
        except ValueError:
            return ScriptAiProvider.OLLAMA

    def _apply_placeholders(self) -> None:
        spec = SPECS[self._current_provider()]
        base_hint = spec.default_base_url
        model_hint = spec.default_model
        if self._current_provider() is ScriptAiProvider.OLLAMA:
            base_hint = (self.settings.ollama_url or "").strip() or spec.default_base_url
            model_hint = (self.settings.ollama_model or "").strip() or spec.default_model
        self.base_url.setPlaceholderText(base_hint)
        self.model.setPlaceholderText(model_hint)
        if spec.needs_key:
            self.api_key.setEnabled(True)
            self.api_key.setPlaceholderText("Paste an API key — chat login is not enough")
        else:
            self.api_key.setEnabled(False)
            self.api_key.setPlaceholderText("Not used for Ollama")

    def _on_provider_changed(self) -> None:
        spec = SPECS[self._current_provider()]
        if known_default_model(self.model.text()) or not self.model.text().strip():
            self.model.setText(spec.default_model)
        if known_default_base(self.base_url.text()) or not self.base_url.text().strip():
            self.base_url.setText(spec.default_base_url if self._current_provider() is not ScriptAiProvider.OLLAMA else "")
        self._apply_placeholders()

    def _toggle_key(self, show: bool) -> None:
        self.api_key.setEchoMode(QLineEdit.EchoMode.Normal if show else QLineEdit.EchoMode.Password)

    def _save(self) -> None:
        provider = self._current_provider()
        self.settings.script_ai_provider = provider
        self.settings.script_ai_api_key = self.api_key.text().strip()
        self.settings.script_ai_base_url = self.base_url.text().strip()
        self.settings.script_ai_model = self.model.text().strip()
        try:
            self.settings.save()
        except Exception as exc:
            QMessageBox.critical(self, "Script AI", f"Could not save settings.\n\n{exc}")
            return
        QMessageBox.information(self, "Script AI", "Script AI settings saved.")
        self.saved.emit()
