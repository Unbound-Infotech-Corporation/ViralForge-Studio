"""Script Lab — in-app browser plus Script AI draft for the episode script.

Grok, ChatGPT, and Claude sign-in is blocked inside Qt WebEngine. The page
keeps the embedded browser for research and for sites that allow it, stores
that profile on disk, and sends real account login to Chrome or Edge.
"""

from __future__ import annotations

import hashlib
import urllib.parse

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
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
from trendforge.services.script_lab_browser import (
    BROWSER_CHROME,
    BROWSER_DEFAULT,
    BROWSER_EDGE,
    DESKTOP_CHROME_USER_AGENT,
    PROFILE_STORAGE_NAME,
    accept_certificate_error,
    apply_web_settings,
    configure_persistent_profile,
    login_wall_probe_script,
    login_wall_reason,
    normalize_browser_preference,
    normalize_http_url,
    open_url_in_system_browser,
    permission_decision,
    popup_leaves_embed,
    profile_storage_dir,
)
from trendforge.settings import AppSettings
from trendforge.ui.pages.create import CreatePage
from trendforge.ui.script_ai_settings import ScriptAiSettingsForm
from trendforge.ui.workers import FnWorker

_CHIPS: tuple[tuple[str, str, str], ...] = (
    (
        "Grok",
        "https://grok.com",
        "Standalone Grok chat at grok.com. Sign-in that the site blocks has to use Open in browser.",
    ),
    ("ChatGPT", "https://chatgpt.com", "Open chatgpt.com. Sign-in uses Open in browser when the site blocks Studio."),
    ("Claude", "https://claude.ai", "Open claude.ai. Sign-in uses Open in browser when the site blocks Studio."),
    ("Web", "https://www.google.com", "Research tab. Starts at Google. Account sign-in uses Open in browser."),
)

_WEBENGINE_HELP = (
    "Qt WebEngine is not installed, so Script Lab cannot show Grok, ChatGPT, or Claude inside Studio.\n\n"
    "Install it, then restart Studio:\n"
    "    pip install PySide6-Addons\n\n"
    "Open in browser still sends the page to Chrome or Edge, where sign-in works. "
    "Paste the script into the draft. Script AI still uses Settings → Script AI, not the chat login."
)

# One named profile per storage path, parented to the application so shutdown
# does not free it before the last page.
_SHARED_PROFILES: dict[str, object] = {}


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
        self._banner_kind = ""
        self._banner_dismissed: tuple[str, str] | None = None
        self._cert_host = ""
        self._page = None

        root = QVBoxLayout(self)
        kicker = QLabel("PRODUCE")
        kicker.setObjectName("kicker")
        title = QLabel("Script Lab")
        title.setObjectName("title")
        hint = QLabel(
            "Draft in Grok, ChatGPT, or Claude, then import the selection into the episode script. "
            "Those sites block sign-in inside this browser — use Open in browser for Chrome or Edge. "
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
        self.open_browser_btn = QPushButton("Open in browser")
        self.open_browser_btn.setObjectName("openInBrowser")
        self.open_browser_btn.setToolTip(
            "Sign in with Chrome or Edge. Google and the other chat sites block the in-app browser."
        )
        self.open_browser_btn.clicked.connect(self._open_in_system_browser)
        self.copy_url_btn = QPushButton("Copy URL")
        self.copy_url_btn.setObjectName("copyUrlButton")
        self.copy_url_btn.clicked.connect(self._copy_url)
        self.browser_choice = QComboBox()
        self.browser_choice.setObjectName("systemBrowserChoice")
        self.browser_choice.setToolTip("Where Open in browser sends chat sign-in. Studio remembers this choice.")
        self.browser_choice.addItem("System browser", BROWSER_DEFAULT)
        self.browser_choice.addItem("Microsoft Edge", BROWSER_EDGE)
        self.browser_choice.addItem("Google Chrome", BROWSER_CHROME)
        preference = normalize_browser_preference(getattr(self.settings, "script_lab_system_browser", BROWSER_DEFAULT))
        choice_index = self.browser_choice.findData(preference)
        self.browser_choice.blockSignals(True)
        if choice_index >= 0:
            self.browser_choice.setCurrentIndex(choice_index)
        self.browser_choice.blockSignals(False)
        self.browser_choice.currentIndexChanged.connect(self._save_browser_preference)
        for widget in (self.back_btn, self.forward_btn, self.reload_btn, self.go_btn):
            tools.addWidget(widget)
        tools.addWidget(self.url, 1)
        tools.addWidget(self.open_browser_btn)
        tools.addWidget(self.copy_url_btn)
        tools.addWidget(self.browser_choice)

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
        self.login_banner = QFrame()
        self.login_banner.setObjectName("loginBanner")
        self.login_banner.setStyleSheet(
            "QFrame#loginBanner { background: #2A2218; border: 1px solid #E8A54B; border-radius: 14px; }"
        )
        banner_layout = QVBoxLayout(self.login_banner)
        self.login_banner_label = QLabel("")
        self.login_banner_label.setObjectName("loginBannerLabel")
        self.login_banner_label.setWordWrap(True)
        self.login_banner_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        banner_buttons = QHBoxLayout()
        self.banner_open_btn = QPushButton("Open in browser")
        self.banner_open_btn.setObjectName("loginBannerOpen")
        self.banner_copy_btn = QPushButton("Copy URL")
        self.banner_dismiss_btn = QPushButton("Dismiss")
        self.banner_dismiss_btn.setObjectName("loginBannerDismiss")
        self.banner_open_btn.clicked.connect(self._open_in_system_browser)
        self.banner_copy_btn.clicked.connect(self._copy_url)
        self.banner_dismiss_btn.clicked.connect(self._dismiss_banner)
        banner_buttons.addWidget(self.banner_open_btn)
        banner_buttons.addWidget(self.banner_copy_btn)
        banner_buttons.addWidget(self.banner_dismiss_btn)
        banner_buttons.addStretch()
        banner_layout.addWidget(self.login_banner_label)
        banner_layout.addLayout(banner_buttons)
        self.login_banner.hide()
        left_l.addWidget(self.login_banner)
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
            from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
            from PySide6.QtWebEngineWidgets import QWebEngineView
        except Exception as exc:
            self._disable_browser(f"{_WEBENGINE_HELP}\n\n{exc}")
            return
        try:
            storage = profile_storage_dir(self.dirs.cache)
            profile = _shared_profile(storage, QWebEngineProfile)
            self._profile = profile
            page = _ScriptLabWebPage(QWebEnginePage, profile, self._on_popup_url, self._on_certificate_error, self._notify)
            self._page = page
            apply_web_settings(profile.settings())
            view = QWebEngineView(self)
            view.setPage(page)
            apply_web_settings(view.settings())
            view.urlChanged.connect(self._on_url_changed)
            view.titleChanged.connect(self._on_title_changed)
            view.loadFinished.connect(self._on_load_finished)
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
        self._view = None
        for button in (self.back_btn, self.forward_btn, self.reload_btn):
            button.setEnabled(False)
        self.url.setReadOnly(False)
        self.go_btn.setEnabled(True)
        self.open_browser_btn.setEnabled(True)
        self.copy_url_btn.setEnabled(True)
        for button, _target in self._chip_buttons:
            button.setEnabled(True)
        self.status.setText("In-app browser unavailable. Open in browser still works for sign-in.")

    def _open_chip(self, url: str, button: QPushButton) -> None:
        for chip, _target in self._chip_buttons:
            chip.setChecked(chip is button)
        self._open(url)

    def _open(self, url: str) -> None:
        normalized = normalize_http_url(url)
        parsed = urllib.parse.urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            self.status.setText("Enter an http or https URL.")
            return
        self.url.setText(normalized)
        self._consider_login_wall(normalized)
        if self._view is None:
            self._loaded = True
            self.status.setText("In-app browser unavailable. Opening in the system browser.")
            self._open_in_system_browser()
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
        text = url.toString()
        self.url.setText(text)
        host = url.host().lower()
        path = url.path().lower()
        for button, target in self._chip_buttons:
            button.setChecked(_chip_matches(button.text(), host, path, target))
        self._consider_login_wall(text)
        self._sync_nav()

    def _on_title_changed(self, title: str) -> None:
        self._consider_login_wall(self.url.text(), title=title)

    def _on_load_finished(self, _ok: bool) -> None:
        self._sync_nav()
        if self._view is None:
            return
        try:
            self._view.page().runJavaScript(login_wall_probe_script(), self._on_login_probe)
        except Exception:
            return

    def _on_login_probe(self, found: object) -> None:
        if isinstance(found, str) and found.strip():
            self._consider_login_wall(self.url.text(), excerpt=found)

    def _on_popup_url(self, url: str) -> None:
        normalized = normalize_http_url(url)
        if popup_leaves_embed(normalized):
            self.url.setText(normalized)
            self._consider_login_wall(normalized)
            message = self._open_in_system_browser()
            self.status.setText(f"Sign-in windows open in your browser. {message}")
            return
        self._open(normalized)

    def _on_certificate_error(self, error: object) -> None:
        if accept_certificate_error(error):
            accept = getattr(error, "acceptCertificate", None)
            if callable(accept):
                accept()
            return
        url = ""
        description = "The certificate is not trusted."
        try:
            url = error.url().toString()  # type: ignore[attr-defined]
        except Exception:
            url = ""
        try:
            text = error.description()  # type: ignore[attr-defined]
            if text:
                description = str(text)
        except Exception:
            pass
        try:
            error.rejectCertificate()  # type: ignore[attr-defined]
        except Exception as exc:
            description = f"{description} ({exc})"
        host = urllib.parse.urlparse(url).hostname or "this site"
        if url:
            self.url.setText(url)
        self._cert_host = host.casefold()
        self._show_banner(
            f"Studio refused {host} because the HTTPS certificate is not trusted. "
            f"{description} The certificate was not accepted.",
            kind="certificate",
        )
        self.status.setText(f"HTTPS certificate refused for {host}.")

    def _notify(self, message: str) -> None:
        self.status.setText(message)

    def _save_browser_preference(self) -> None:
        self.settings.script_lab_system_browser = normalize_browser_preference(self.browser_choice.currentData())
        if getattr(self.settings, "_path", None) is not None:
            self.settings.save()

    def _open_in_system_browser(self) -> str:
        try:
            message = open_url_in_system_browser(
                self.url.text(),
                str(self.browser_choice.currentData() or BROWSER_DEFAULT),
                open_default=self._open_with_desktop_services,
            )
        except Exception as exc:
            message = str(exc)
            QMessageBox.warning(self, "Open in browser", message)
        self.status.setText(message)
        return message

    def _open_with_desktop_services(self, url: str) -> bool:
        return bool(QDesktopServices.openUrl(QUrl(url)))

    def _copy_url(self) -> str:
        text = self.url.text().strip()
        QApplication.clipboard().setText(text)
        if text:
            self.status.setText("Copied the page URL.")
        else:
            self.status.setText("There is no URL to copy.")
        return text

    def _consider_login_wall(self, url: str, title: str = "", excerpt: str = "") -> None:
        wall = login_wall_reason(url, title, excerpt)
        if wall is None:
            host = (urllib.parse.urlparse(normalize_http_url(url)).hostname or "").casefold()
            if self._cert_host and host == self._cert_host:
                return
            self._cert_host = ""
            self._banner_kind = ""
            self.login_banner.hide()
            return
        if self._banner_dismissed == (url, wall.kind):
            return
        self._show_banner(wall.message, wall.kind)

    def _show_banner(self, message: str, kind: str) -> None:
        if self._banner_dismissed == (self.url.text(), kind):
            return
        self._banner_kind = kind
        self.login_banner_label.setText(message)
        self.login_banner.show()

    def _dismiss_banner(self) -> None:
        self._banner_dismissed = (self.url.text(), self._banner_kind)
        self._cert_host = ""
        self.login_banner.hide()

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


def _shared_profile(storage, profile_cls):
    key = str(storage.resolve())
    existing = _SHARED_PROFILES.get(key)
    if existing is not None:
        return existing
    # The first profile keeps a stable storage name. Later paths (tests) get a suffix
    # so Qt does not hand them the same on-disk profile.
    name = PROFILE_STORAGE_NAME
    if _SHARED_PROFILES:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
        name = f"{PROFILE_STORAGE_NAME}-{digest}"
    profile = profile_cls(name, QApplication.instance())
    policies = getattr(profile_cls, "PersistentCookiesPolicy", None)
    cookie_policy = getattr(policies, "ForcePersistentCookies", None) if policies is not None else None
    if cookie_policy is None and policies is not None:
        cookie_policy = getattr(policies, "AllowPersistentCookies", None)
    caches = getattr(profile_cls, "HttpCacheType", None)
    cache_type = getattr(caches, "DiskHttpCache", None) if caches is not None else None
    configure_persistent_profile(
        profile,
        storage,
        user_agent=DESKTOP_CHROME_USER_AGENT,
        cookie_policy=cookie_policy,
        cache_type=cache_type,
    )
    _SHARED_PROFILES[key] = profile
    return profile


def _ScriptLabWebPage(page_base, profile, on_popup, on_certificate, notify):
    """Build a page that rejects bad certificates and traps auth popups."""

    class ScriptLabWebPage(page_base):
        def __init__(self) -> None:
            super().__init__(profile, None)
            self._traps: list = []
            self._connect_optional(getattr(self, "certificateError", None), on_certificate, notify)
            self._connect_optional(getattr(self, "permissionRequested", None), self._on_permission, notify)
            self._connect_optional(getattr(self, "featurePermissionRequested", None), self._on_legacy_permission, notify)

        @staticmethod
        def _connect_optional(signal, slot, notify) -> None:
            if signal is None or not hasattr(signal, "connect"):
                return
            try:
                signal.connect(slot)
            except Exception as exc:
                notify(f"Could not attach a browser handler: {exc}")

        def createWindow(self, _window_type):  # noqa: N802 - Qt API
            trap = page_base(self.profile(), self)
            self._traps.append(trap)

            def _take(url, trapped=trap) -> None:
                text = url.toString()
                if not text or text == "about:blank":
                    return
                on_popup(text)
                if trapped in self._traps:
                    self._traps.remove(trapped)
                trapped.deleteLater()

            trap.urlChanged.connect(_take)
            return trap

        def _on_permission(self, request) -> None:
            feature = getattr(request, "feature", None)
            feature_value = feature() if callable(feature) else feature
            name = getattr(feature_value, "name", "")
            if not isinstance(name, str):
                name = str(feature_value or "")
            decision = permission_decision(name)
            try:
                if decision == "grant":
                    request.grant()
                else:
                    request.deny()
            except Exception as exc:
                notify(f"Could not answer a browser permission ({name or 'unknown'}): {exc}")
                return
            if decision == "deny":
                host = ""
                try:
                    host = request.origin().host()
                except Exception:
                    host = ""
                where = f" for {host}" if host else ""
                notify(
                    f"Denied {name or 'a browser permission'}{where}. "
                    "Studio does not grant that in the in-app browser."
                )

        def _on_legacy_permission(self, origin, feature) -> None:
            name = getattr(feature, "name", str(feature))
            decision = permission_decision(str(name))
            policy = page_base.PermissionPolicy
            chosen = (
                policy.PermissionGrantedByUser if decision == "grant" else policy.PermissionDeniedByUser
            )
            self.setFeaturePermission(origin, feature, chosen)
            if decision == "deny":
                host = ""
                try:
                    host = origin.host()
                except Exception:
                    host = ""
                where = f" for {host}" if host else ""
                notify(
                    f"Denied {name}{where}. Studio does not grant that in the in-app browser."
                )

    return ScriptLabWebPage()
