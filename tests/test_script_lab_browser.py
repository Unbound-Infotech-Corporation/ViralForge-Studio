"""Script Lab sign-in policy. No live OAuth and no real browser launch."""

from __future__ import annotations

import json

import pytest

from trendforge.services.script_lab_browser import (
    DESKTOP_CHROME_USER_AGENT,
    PAGE_SETTING_POLICY,
    REFUSED_CHROMIUM_FLAGS,
    accept_certificate_error,
    apply_chromium_environment,
    apply_web_settings,
    chromium_flags_for_script_lab,
    configure_persistent_profile,
    find_browser_executable,
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


class _Profile:
    def __init__(self, off_record: bool = False) -> None:
        self.off_record = off_record
        self.calls: list[tuple] = []

    def isOffTheRecord(self) -> bool:
        return self.off_record

    def setPersistentStoragePath(self, path: str) -> None:
        self.calls.append(("storage", path))

    def setCachePath(self, path: str) -> None:
        self.calls.append(("cache", path))

    def setHttpUserAgent(self, agent: str) -> None:
        self.calls.append(("ua", agent))

    def setPersistentCookiesPolicy(self, policy: object) -> None:
        self.calls.append(("cookies", policy))

    def setHttpCacheType(self, cache_type: object) -> None:
        self.calls.append(("http-cache", cache_type))


class _Settings:
    def __init__(self) -> None:
        self.values: list[tuple] = []

    def setAttribute(self, attribute: object, enabled: bool) -> None:
        self.values.append((attribute, enabled))


def test_user_agent_is_desktop_chrome_and_does_not_claim_to_be_qt():
    agent = DESKTOP_CHROME_USER_AGENT
    assert "Windows NT 10.0" in agent
    assert "Chrome/154.0.8037.57" in agent
    assert "Mobile" not in agent
    assert "QtWebEngine" not in agent
    assert "Android" not in agent


def test_chromium_flags_do_not_disable_https():
    assert chromium_flags_for_script_lab() == ""
    for flag in REFUSED_CHROMIUM_FLAGS:
        assert flag not in chromium_flags_for_script_lab().split()
    env = {"QTWEBENGINE_CHROMIUM_FLAGS": "--enable-logging"}
    assert apply_chromium_environment(env) == "--enable-logging"
    assert env["QTWEBENGINE_CHROMIUM_FLAGS"] == "--enable-logging"


def test_certificate_errors_are_never_accepted():
    assert accept_certificate_error() is False
    assert accept_certificate_error(object()) is False


def test_persistent_profile_uses_disk_storage(tmp_path):
    profile = _Profile()
    root = configure_persistent_profile(
        profile,
        tmp_path / "scriptlab-web",
        cookie_policy="force",
        cache_type="disk",
    )
    assert root.is_dir()
    assert (root / "cache").is_dir()
    kinds = [name for name, _value in profile.calls]
    assert kinds == ["storage", "cache", "ua", "cookies", "http-cache"]
    assert profile.calls[2][1] == DESKTOP_CHROME_USER_AGENT
    assert profile_storage_dir(tmp_path) == tmp_path / "scriptlab-web"


def test_off_record_profile_is_refused(tmp_path):
    with pytest.raises(RuntimeError, match="off-the-record"):
        configure_persistent_profile(_Profile(off_record=True), tmp_path / "web")


def test_web_settings_keep_insecure_content_off():
    settings = _Settings()
    applied = apply_web_settings(
        settings,
        attributes={name: name for name, _enabled in (
            ("JavascriptEnabled", True),
            ("LocalStorageEnabled", True),
            ("AllowRunningInsecureContent", False),
            ("ErrorPageEnabled", True),
        )},
    )
    assert ("AllowRunningInsecureContent", False) in PAGE_SETTING_POLICY
    assert ("LocalContentCanAccessRemoteUrls", False) in PAGE_SETTING_POLICY
    assert "AllowRunningInsecureContent=False" in applied
    assert ("AllowRunningInsecureContent", False) in settings.values
    assert ("JavascriptEnabled", True) in settings.values
    assert "LocalContentCanAccessRemoteUrls=True" not in applied


def test_permissions_allow_clipboard_and_deny_the_rest():
    assert permission_decision("ClipboardReadWrite") == "grant"
    assert permission_decision("clipboard-read") == "grant"
    assert permission_decision("Notifications") == "deny"
    assert permission_decision("Geolocation") == "deny"
    assert permission_decision("MediaAudioCapture") == "deny"


def test_login_wall_detects_blocked_google_and_chat_sign_in():
    blocked = login_wall_reason("https://accounts.google.com/signin/rejected?disallowed_useragent=1")
    assert blocked is not None
    assert blocked.kind == "blocked"
    assert "blocks sign-in" in blocked.message
    assert "Script AI" in blocked.message

    rejected = login_wall_reason("https://accounts.google.com/v3/signin/rejected")
    assert rejected is not None and rejected.kind == "blocked"

    titled = login_wall_reason("https://grok.com/", title="This browser or app may not be secure")
    assert titled is not None and titled.kind == "blocked"

    excerpt = login_wall_reason("https://chatgpt.com/", excerpt="Couldn't sign you in to this embedded browser")
    assert excerpt is not None and excerpt.kind == "blocked"

    google = login_wall_reason("https://accounts.google.com/ServiceLogin")
    assert google is not None and google.kind == "signin"

    openai = login_wall_reason("https://auth.openai.com/authorize")
    assert openai is not None and openai.kind == "signin"

    claude = login_wall_reason("https://claude.ai/login")
    assert claude is not None and claude.kind == "signin"

    xai = login_wall_reason("https://accounts.x.ai/sign-in")
    assert xai is not None and xai.kind == "signin"

    x_login = login_wall_reason("https://x.com/i/flow/login")
    assert x_login is not None and x_login.kind == "signin"
    assert popup_leaves_embed("https://x.com/i/flow/login") is True


def test_ordinary_chat_and_research_pages_stay_in_the_embed():
    for url in (
        "https://grok.com/",
        "https://chatgpt.com/",
        "https://claude.ai/new",
        "https://www.google.com/search?q=harbor+lights",
    ):
        assert login_wall_reason(url, title="Chat") is None
    assert popup_leaves_embed("https://en.wikipedia.org/wiki/Harbor") is False
    assert login_wall_reason("", "", "") is None


def test_probe_script_contains_the_blocked_phrase():
    script = login_wall_probe_script()
    assert "this browser or app may not be secure" in script
    assert "document.body" in script


def test_browser_preference_and_launch_do_not_start_a_process(tmp_path):
    assert normalize_browser_preference("Microsoft Edge") == "edge"
    assert normalize_browser_preference("Google Chrome") == "chrome"
    assert normalize_browser_preference("safari") == "default"
    assert normalize_http_url("grok.com") == "https://grok.com"
    assert normalize_http_url("localhost:8080/lab") == "https://localhost:8080/lab"
    assert normalize_http_url("javascript:alert(1)") == "javascript:alert(1)"

    program = tmp_path / "Microsoft" / "Edge" / "Application"
    program.mkdir(parents=True)
    real_edge = program / "msedge.exe"
    real_edge.write_text("", encoding="utf-8")
    launched: list[list[str]] = []
    opened: list[str] = []
    message = open_url_in_system_browser(
        "grok.com",
        "edge",
        environ={"PROGRAMFILES": str(tmp_path), "PROGRAMFILES(X86)": "", "LOCALAPPDATA": ""},
        path_exists=lambda path: path == real_edge,
        which=lambda _name: None,
        start_executable=launched.append,
        open_default=lambda url: opened.append(url) or True,
    )
    assert launched == [[str(real_edge), "https://grok.com"]]
    assert message == "Opened in Microsoft Edge."
    assert opened == []

    missing = open_url_in_system_browser(
        "https://claude.ai/login",
        "chrome",
        environ={},
        path_exists=lambda _path: False,
        which=lambda _name: None,
        start_executable=launched.append,
        open_default=lambda url: opened.append(url) or True,
    )
    assert "Google Chrome was not found" in missing
    assert opened == ["https://claude.ai/login"]
    assert find_browser_executable("default", path_exists=lambda _path: True) is None

    with pytest.raises(ValueError, match="http or https"):
        open_url_in_system_browser(
            "javascript:alert(1)",
            open_default=lambda _url: True,
        )


def test_settings_remember_browser_preference(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"script_lab_system_browser": "edge", "theme": "dark"}), encoding="utf-8")
    loaded = AppSettings._from_dict(json.loads(path.read_text(encoding="utf-8")))
    assert loaded.script_lab_system_browser == "edge"
    unknown = AppSettings._from_dict({"script_lab_system_browser": "lynx"})
    assert unknown.script_lab_system_browser == "default"
    fresh = AppSettings()
    fresh._path = path
    fresh.script_lab_system_browser = "chrome"
    fresh.save()
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["script_lab_system_browser"] == "chrome"
    assert raw["script_ai_provider"]


def test_help_explains_system_browser_sign_in():
    pytest.importorskip("PySide6.QtWidgets")
    from trendforge.ui.pages.help import GETTING_STARTED, TROUBLESHOOT

    assert "Open in browser" in GETTING_STARTED
    assert "cannot be fixed by pretending to be Chrome" in GETTING_STARTED
    assert "Script Lab sign-in blocked" in TROUBLESHOOT
    assert "not accepted" in TROUBLESHOOT


def test_script_lab_page_banner_copy_and_chips(tmp_path, monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("PySide6.QtWidgets")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from trendforge.bootstrap import AppDirs
    from trendforge.ui.main_window import MainWindow
    import trendforge.ui.pages.script_lab as script_lab_module

    calls: list[tuple[str, str]] = []

    def fake_open(url: str, preference: str = "default", **_kwargs) -> str:
        calls.append((url, preference))
        return f"opened:{url}"

    monkeypatch.setattr(script_lab_module, "open_url_in_system_browser", fake_open)
    _app = QApplication.instance() or QApplication([])
    root = tmp_path / "home"
    dirs = AppDirs(
        root=root,
        projects=root / "projects",
        gallery=root / "gallery",
        cache=root / "cache",
        logs=root / "logs",
        models=root / "models",
        music=root / "music",
        tmp=root / "tmp",
        settings_file=root / "settings.json",
    )
    for path in (dirs.projects, dirs.logs, dirs.models, dirs.music, dirs.cache, dirs.gallery, dirs.tmp):
        path.mkdir(parents=True, exist_ok=True)
    settings = AppSettings()
    settings._path = dirs.settings_file
    window = MainWindow(settings, dirs)
    window.show()
    _app.processEvents()
    lab_nav = next(btn for btn in window.nav_btns if btn.text() == "Script Lab")
    lab_nav.click()
    _app.processEvents()
    page = window.script_lab
    assert window.stack.currentWidget() is page
    assert [button.text() for button, _target in page._chip_buttons] == ["Grok", "ChatGPT", "Claude", "Web"]
    assert page.open_browser_btn.objectName() == "openInBrowser"
    assert page.open_browser_btn.isEnabled()
    assert page.copy_url_btn.isEnabled()
    assert page.import_btn.text() == "Import into episode script"
    assert page.settings_btn.text() == "Script AI settings…"
    assert page.generate_btn.text() == "Generate with Script AI…"
    assert page.login_banner.isHidden()

    page.url.setText("https://accounts.google.com/signin/rejected?disallowed_useragent=1")
    page._consider_login_wall(page.url.text())
    assert not page.login_banner.isHidden()
    assert "blocks sign-in" in page.login_banner_label.text()
    assert calls == []

    page.browser_choice.setCurrentIndex(page.browser_choice.findData("chrome"))
    _app.processEvents()
    page.open_browser_btn.click()
    _app.processEvents()
    assert calls == [("https://accounts.google.com/signin/rejected?disallowed_useragent=1", "chrome")]
    assert settings.script_lab_system_browser == "chrome"
    saved = json.loads(dirs.settings_file.read_text(encoding="utf-8"))
    assert saved["script_lab_system_browser"] == "chrome"

    page._copy_url()
    assert _app.clipboard().text().startswith("https://accounts.google.com/signin/rejected")
    page.banner_dismiss_btn.click()
    _app.processEvents()
    assert page.login_banner.isHidden()

    page._consider_login_wall("https://www.google.com/search?q=studio")
    assert page.login_banner.isHidden()
    error = _CertError()
    page._on_certificate_error(error)
    assert error.rejected is True
    assert error.accepted is False
    assert not page.login_banner.isHidden()
    assert "not accepted" in page.login_banner_label.text()
    assert "refused" in page.status.text().lower()
    window.close()


class _CertError:
    def __init__(self) -> None:
        self.rejected = False
        self.accepted = False

    def url(self):
        return _Url()

    def description(self) -> str:
        return "certificate authority is invalid"

    def rejectCertificate(self) -> None:
        self.rejected = True

    def acceptCertificate(self) -> None:
        self.accepted = True


class _Url:
    def toString(self) -> str:
        return "https://expired.example/login"
