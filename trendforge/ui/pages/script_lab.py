"""Script Lab — in-app browser plus Script AI draft for the episode script."""

from __future__ import annotations

import re

from PySide6.QtCore import QUrl, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from trendforge.bootstrap import AppDirs
from trendforge.domain.enums import ScriptAiTask
from trendforge.services.script_ai import TASK_LABELS, config_from_settings, generate_script_ai
from trendforge.services.script_import import insert_draft
from trendforge.settings import AppSettings
from trendforge.ui.pages.create import CreatePage
from trendforge.ui.script_ai_settings import ScriptAiSettingsForm
from trendforge.ui.workers import FnWorker

_CHIPS: tuple[tuple[str, str, str], ...] = (
    ("Grok", "https://grok.com", "Standalone Grok chat at grok.com. grok.x.ai is an older host and often misses features."),
    ("ChatGPT", "https://chatgpt.com", "Open chatgpt.com"),
    ("Claude", "https://claude.ai", "Open claude.ai"),
    ("Web", "https://www.google.com", "Research tab. Starts at Google."),
)

_WEBENGINE_HELP = (
    "Qt WebEngine is not installed, so Script Lab cannot open Grok, ChatGPT, or Claude inside Studio.\n\n"
    "Install it, then restart Studio:\n"
    "    pip install PySide6-Addons\n\n"
    "Paste-import and Script AI still work on this page. "
    "A chat-site subscription does not unlock the Script AI API."
)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def normalize_http_url(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", raw):
        raw = "https://" + raw
    return raw


class ScriptLabPage(QWidget):
    def __init__(
        self,
        settings: AppSettings,
        dirs: AppDirs,
        create_page: CreatePage,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings
        self.dirs = dirs
        self.create_page = create_page
        self._view = None
        self._profile = None
        self._worker: FnWorker | None = None
        self._loaded = False

        root = QVBoxLayout(self)
        kicker = QLabel("PRODUCE")
        kicker.setObjectName("kicker")
        title = QLabel("Script Lab")
        title.setObjectName("title")
        hint = QLabel(
            "Draft in Grok, ChatGPT, or Claude, then import the selection into the episode script. "
            "Script AI uses your own API key — a chat subscription does not unlock it."
        )
        hint.setObjectName("subtitle")
        hint.setWordWrap(True)

        toolbar = QFrame()
        toolbar.setObjectName("card")
        tools = QHBoxLayout(toolbar)
        tools.setContentsMargins(8, 8, 8, 8)
        self.back_btn = QPushButton("Back")
        self.forward_btn = QPushButton("Forward")
        self.reload_btn = QPushButton("Reload")
        self.url = QLineEdit()
        self.url.setPlaceholderText("https://")
        self.url.returnPressed.connect(self._go)
        self.go_btn = QPushButton("Go")
        self.back_btn.clicked.connect(self._back)
        self.forward_btn.clicked.connect(self._forward)
        self.reload_btn.clicked.connect(self._reload)
        self.go_btn.clicked.connect(self._go)
        for widget in (self.back_btn, self.forward_btn, self.reload_btn, self.go_btn):
            tools.addWidget(widget)
        tools.addWidget(self.url, 1)

        chips = QHBoxLayout()
        self._chip_buttons: list[tuple[QPushButton, str]] = []
        for label, target, tip in _CHIPS:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setToolTip(tip)
            button.clicked.connect(lambda _=False, url=target, btn=button: self._open_chip(url, btn))
            chips.addWidget(button)
            self._chip_buttons.append((button, target))
        chips.addStretch()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(0, 0, 0, 0)
        self.fallback = QLabel(_WEBENGINE_HELP)
        self.fallback.setWordWrap(True)
        self.fallback.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.fallback.setObjectName("subtitle")
        fallback_card = QFrame()
        fallback_card.setObjectName("card")
        fallback_l = QVBoxLayout(fallback_card)
        fallback_l.addWidget(self.fallback)
        fallback_l.addStretch()
        left_l.addWidget(fallback_card, 1)
        self._browser_host = left_l
        self._fallback_card = fallback_card

        right = QFrame()
        right.setObjectName("card")
        right_l = QVBoxLayout(right)
        draft_label = QLabel("Script draft")
        draft_label.setObjectName("kicker")
        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText(
            "Script AI inserts here. Select text in the browser, or paste, then import into the episode script."
        )
        self.import_btn = QPushButton("Import into episode script")
        self.import_btn.setObjectName("primary")
        self.import_btn.clicked.connect(self.import_into_episode)
        self.generate_btn = QPushButton("Generate with Script AI…")
        self.generate_btn.clicked.connect(self.generate_with_script_ai)
        self.settings_btn = QPushButton("Script AI settings…")
        self.settings_btn.clicked.connect(self._edit_settings)
        self.provider_label = QLabel("")
        self.provider_label.setObjectName("subtitle")
        self.provider_label.setWordWrap(True)
        right_l.addWidget(draft_label)
        right_l.addWidget(self.editor, 1)
        right_l.addWidget(self.import_btn)
        right_l.addWidget(self.generate_btn)
        right_l.addWidget(self.settings_btn)
        right_l.addWidget(self.provider_label)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        self.status = QLabel("Select a chat, or generate a draft with Script AI.")
        self.status.setObjectName("subtitle")
        self.status.setWordWrap(True)

        root.addWidget(kicker)
        root.addWidget(title)
        root.addWidget(hint)
        root.addWidget(toolbar)
        root.addLayout(chips)
        root.addWidget(splitter, 1)
        root.addWidget(self.status)

        self._mount_browser()
        self.refresh_provider_label()
        self._sync_nav()

    def ensure_loaded(self) -> None:
        if self._loaded or self._view is None:
            return
        self._loaded = True
        self._open(_CHIPS[0][1])

    def refresh_provider_label(self) -> None:
        config = config_from_settings(self.settings)
        if config.spec.needs_key:
            key_state = "API key saved" if config.api_key else "API key missing"
        else:
            key_state = "local, no API key"
        self.provider_label.setText(f"Script AI: {config.spec.label} · {config.model} · {key_state}")

    def import_into_episode(self) -> None:
        # Browser selection, then the draft selection, then a paste dialog.
        text = self._browser_selection() or self._editor_selection()
        if not text:
            prefill = self.editor.toPlainText().strip()
            pasted, ok = QInputDialog.getMultiLineText(
                self,
                "Import into episode script",
                "Nothing is selected in the browser or the draft. Paste the script or VO to import.",
                prefill,
            )
            if not ok:
                return
            text = pasted.strip()
            if not text:
                QMessageBox.warning(self, "Import into episode script", "Nothing to import.")
                return
        mode = self._choose_import_mode(text)
        if mode is None:
            return
        try:
            message = self.create_page.import_script_text(text, mode)
        except Exception as exc:
            QMessageBox.critical(self, "Import into episode script", str(exc))
            self.status.setText(str(exc))
            return
        self.status.setText(message)

    def generate_with_script_ai(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self.status.setText("Script AI is still writing.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Generate with Script AI")
        dialog.resize(560, 420)
        layout = QVBoxLayout(dialog)
        intro = QLabel(
            "Runs the provider saved in Settings → Script AI and inserts the result into the script draft. "
            "Chat-site logins are not used."
        )
        intro.setWordWrap(True)
        intro.setObjectName("subtitle")
        task = QComboBox()
        for kind, label in TASK_LABELS:
            task.addItem(label, kind.value)
        brief = QPlainTextEdit()
        selected = self._browser_selection() or self._editor_selection()
        if selected:
            brief.setPlainText(selected)
        else:
            topic = self.create_page.topic.text().strip()
            if topic:
                brief.setPlainText(topic)
        brief.setPlaceholderText("Episode idea, beats, or the lines you want rewritten.")
        include = QCheckBox("Include the current script draft as context")
        include.setChecked(bool(self.editor.toPlainText().strip()) and not selected)
        insert_mode = QComboBox()
        insert_mode.addItem("Append to script draft", "append")
        insert_mode.addItem("Replace script draft", "replace")
        if not self.editor.toPlainText().strip():
            insert_mode.setCurrentIndex(1)
        buttons = QHBoxLayout()
        run = QPushButton("Generate")
        run.setObjectName("primary")
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(dialog.reject)
        buttons.addWidget(run)
        buttons.addWidget(cancel)
        buttons.addStretch()
        layout.addWidget(intro)
        layout.addWidget(QLabel("Task"))
        layout.addWidget(task)
        layout.addWidget(QLabel("Brief"))
        layout.addWidget(brief, 1)
        layout.addWidget(include)
        layout.addWidget(QLabel("Insert"))
        layout.addWidget(insert_mode)
        layout.addLayout(buttons)

        def accept() -> None:
            if not brief.toPlainText().strip():
                QMessageBox.warning(dialog, "Brief required", "Describe the episode, topic, or beats to write.")
                return
            dialog.accept()

        run.clicked.connect(accept)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            kind = ScriptAiTask(task.currentData())
        except ValueError:
            QMessageBox.critical(self, "Script AI failed", "Unknown Script AI task.")
            return
        context = self.editor.toPlainText() if include.isChecked() else ""
        if len(context) > 12000:
            context = context[:12000] + "\n…[truncated]"
        brief_text = brief.toPlainText()
        mode = str(insert_mode.currentData() or "append")
        config = config_from_settings(self.settings)
        self.generate_btn.setEnabled(False)
        self.status.setText(f"Script AI is writing with {config.spec.label}…")

        def work() -> str:
            return generate_script_ai(config, kind, brief_text, context=context)

        self._worker = FnWorker(work, self)
        self._worker.ok.connect(lambda text, insert=mode: self._on_generated(text, insert))
        self._worker.failed.connect(self._on_generate_failed)
        self._worker.start()

    def _on_generated(self, text: str, mode: str) -> None:
        self.generate_btn.setEnabled(True)
        try:
            self.editor.setPlainText(insert_draft(self.editor.toPlainText(), str(text), mode))
        except Exception as exc:
            QMessageBox.critical(self, "Script AI failed", str(exc))
            self.status.setText(str(exc))
            return
        self.status.setText("Inserted Script AI result into the script draft.")

    def _on_generate_failed(self, message: str) -> None:
        self.generate_btn.setEnabled(True)
        detail = message or "Script AI failed."
        if not detail.startswith("Script AI"):
            detail = f"Script AI failed: {detail}"
        QMessageBox.critical(self, "Script AI failed", detail)
        self.status.setText(detail)

    def _edit_settings(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Script AI")
        dialog.resize(560, 480)
        layout = QVBoxLayout(dialog)
        form = ScriptAiSettingsForm(self.settings)
        form.saved.connect(self.refresh_provider_label)
        layout.addWidget(form)
        dialog.exec()
        self.refresh_provider_label()

    def _mount_browser(self) -> None:
        try:
            from PySide6.QtWebEngineCore import QWebEngineProfile
            from PySide6.QtWebEngineWidgets import QWebEngineView
        except Exception as exc:
            self._disable_browser(f"{_WEBENGINE_HELP}\n\n{exc}")
            return
        try:
            storage = self.dirs.cache / "scriptlab-web"
            storage.mkdir(parents=True, exist_ok=True)
            # The default profile outlives every page, so shutdown does not free it early.
            profile = QWebEngineProfile.defaultProfile()
            profile.setHttpUserAgent(_USER_AGENT)
            try:
                profile.setPersistentStoragePath(str(storage))
                profile.setCachePath(str(storage / "cache"))
            except Exception:
                pass
            policy = getattr(QWebEngineProfile, "PersistentCookiesPolicy", None)
            allow = getattr(policy, "AllowPersistentCookies", None) if policy is not None else None
            if allow is not None:
                try:
                    profile.setPersistentCookiesPolicy(allow)
                except Exception:
                    pass
            self._profile = profile
            view = QWebEngineView(self)
            view.urlChanged.connect(self._on_url_changed)
            view.loadFinished.connect(lambda _ok: self._sync_nav())
            self._view = view
            self._fallback_card.hide()
            self._browser_host.addWidget(view, 1)
            self.url.setText(_CHIPS[0][1])
        except Exception as exc:
            self._view = None
            self._disable_browser(f"{_WEBENGINE_HELP}\n\n{exc}")

    def _disable_browser(self, message: str) -> None:
        self.fallback.setText(message)
        self._fallback_card.show()
        for button in (self.back_btn, self.forward_btn, self.reload_btn):
            button.setEnabled(False)
        self.url.setReadOnly(True)
        self.url.setPlaceholderText("Browser unavailable until PySide6-Addons is installed")
        self.go_btn.setEnabled(False)
        for button, _target in self._chip_buttons:
            button.setEnabled(False)

    def _open_chip(self, url: str, button: QPushButton) -> None:
        for chip, _target in self._chip_buttons:
            chip.setChecked(chip is button)
        self._open(url)

    def _open(self, url: str) -> None:
        normalized = normalize_http_url(url)
        if not normalized:
            return
        self.url.setText(normalized)
        if self._view is None:
            self.status.setText("Browser unavailable. Paste a script or use Script AI.")
            return
        self._loaded = True
        self._view.setUrl(QUrl(normalized))
        self.status.setText(f"Loading {normalized}")

    def _go(self) -> None:
        self._open(self.url.text())

    def _back(self) -> None:
        if self._view is not None:
            self._view.back()

    def _forward(self) -> None:
        if self._view is not None:
            self._view.forward()

    def _reload(self) -> None:
        if self._view is not None:
            self._view.reload()

    def _on_url_changed(self, url: QUrl) -> None:
        self.url.setText(url.toString())
        host = url.host().lower()
        path = url.path().lower()
        for button, target in self._chip_buttons:
            button.setChecked(_chip_matches(button.text(), host, path, target))
        self._sync_nav()

    def _sync_nav(self) -> None:
        if self._view is None:
            self.back_btn.setEnabled(False)
            self.forward_btn.setEnabled(False)
            return
        history = self._view.history()
        self.back_btn.setEnabled(history.canGoBack())
        self.forward_btn.setEnabled(history.canGoForward())

    def _browser_selection(self) -> str:
        if self._view is None:
            return ""
        try:
            return self._view.page().selectedText().strip()
        except Exception:
            return ""

    def _editor_selection(self) -> str:
        text = self.editor.textCursor().selectedText().strip()
        return text.replace("\u2029", "\n")

    def _choose_import_mode(self, preview: str) -> str | None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Import into episode script")
        box.setText("Add this text to the active episode script on Create?")
        snippet = " ".join(preview.split())
        if len(snippet) > 180:
            snippet = snippet[:180] + "…"
        box.setInformativeText(
            f"{snippet}\n\nAppend adds shots. Replace overwrites the current episode shots."
        )
        append = box.addButton("Append", QMessageBox.ButtonRole.AcceptRole)
        replace = box.addButton("Replace", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked is append:
            return "append"
        if clicked is replace:
            return "replace"
        return None


def _chip_matches(label: str, host: str, path: str, target: str) -> bool:
    if label == "Grok":
        return "grok" in host or "grok" in path
    target_host = QUrl(target).host().lower()
    return bool(target_host) and host == target_host
