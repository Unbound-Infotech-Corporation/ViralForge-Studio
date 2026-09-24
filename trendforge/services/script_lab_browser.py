"""Script Lab browser policy.

Qt WebEngine cannot complete Google, OpenAI, Anthropic, or xAI account
sign-in. Those sites reject embedded webviews (``disallowed_useragent`` /
"not a secure browser"). A desktop Chrome user-agent does not remove that
block. Script Lab keeps an in-app browser for research and sites that allow
it, and sends real sign-in to the operating-system browser.

This module is Qt-free so tests can cover the policy without WebEngine.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.parse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

# Current desktop Chrome stable as of September 2026 (154.0.8037.57).
# Desktop only: no Mobile token, and no QtWebEngine token. Replacing the
# default Qt user-agent avoids an obviously embedded UA, but Google still
# blocks OAuth inside WebEngine. Do not treat this string as a login fix.
DESKTOP_CHROME_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/154.0.8037.57 Safari/537.36"
)

PROFILE_STORAGE_NAME = "ViralForgeScriptLab"
PROFILE_DIR_NAME = "scriptlab-web"

BROWSER_DEFAULT = "default"
BROWSER_EDGE = "edge"
BROWSER_CHROME = "chrome"

# Chromium flags Script Lab will not set. Bad certificates stay rejected.
REFUSED_CHROMIUM_FLAGS: tuple[str, ...] = (
    "--ignore-certificate-errors",
    "--ignore-ssl-errors",
    "--ignore-certificate-errors-spki-list",
    "--disable-web-security",
    "--allow-running-insecure-content",
)

# In-app page settings. Insecure content stays off.
PAGE_SETTING_POLICY: tuple[tuple[str, bool], ...] = (
    ("JavascriptEnabled", True),
    ("LocalStorageEnabled", True),
    ("LocalContentCanAccessRemoteUrls", False),
    ("AllowRunningInsecureContent", False),
    ("ErrorPageEnabled", True),
    ("JavascriptCanOpenWindows", True),
    ("AllowWindowActivationFromJavaScript", True),
    ("FocusOnNavigationEnabled", True),
    ("FullScreenSupportEnabled", True),
    ("PluginsEnabled", False),
    ("PdfViewerEnabled", True),
    ("ScrollAnimatorEnabled", True),
    ("HyperlinkAuditingEnabled", False),
    ("DnsPrefetchEnabled", True),
    ("AutoLoadImages", True),
)

LOGIN_WALL_PHRASES: tuple[str, ...] = (
    "this browser or app may not be secure",
    "couldn't sign you in",
    "could not sign you in",
    "browser isn't supported",
    "browser is not supported",
    "unsupported browser",
    "not a secure browser",
    "sign-in is blocked",
    "signin is blocked",
    "disallowed_useragent",
    "use a different browser",
    "try using a different browser",
    "try a different browser",
    "embedded browser",
)

BLOCKED_LOGIN_MESSAGE = (
    "This site blocks sign-in in Studio's in-app browser. "
    "Google, OpenAI, Anthropic, and xAI reject embedded browsers, so this page "
    "cannot be made secure enough for that login. Open it in Chrome or Edge, "
    "sign in there, and paste the script into the draft. Studio does not receive "
    "that browser's cookies. The chat login is not an API key — Script AI still "
    "uses Settings → Script AI."
)

SIGN_IN_MESSAGE = (
    "Sign-in usually fails inside Studio. Open this page in Chrome or Edge, "
    "finish login there, and paste the script into the draft. Studio keeps a "
    "separate in-app profile and does not share cookies with that browser. "
    "Script AI uses your API key, not this login."
)

_SIGN_IN_HOSTS = frozenset(
    {
        "accounts.google.com",
        "accounts.youtube.com",
        "auth.openai.com",
        "auth0.openai.com",
        "accounts.x.ai",
        "login.x.ai",
    }
)

_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


@dataclass(frozen=True, slots=True)
class LoginWall:
    """Why the in-app browser should hand this page to the system browser."""

    kind: str
    message: str


def normalize_http_url(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    if _SCHEME_RE.match(raw):
        return raw
    # javascript: and data: stay intact so callers can reject them.
    # localhost:8080 is a host and port, not a scheme.
    head = raw.split("/", 1)[0]
    if ":" in head:
        scheme, rest = head.split(":", 1)
        if scheme.isalpha() and not rest[:1].isdigit():
            return raw
    return "https://" + raw


def chromium_flags_for_script_lab() -> str:
    """Extra Chromium flags. Empty: Qt's HTTPS checks stay in force."""
    return ""


def apply_chromium_environment(environ: dict[str, str] | None = None) -> str:
    """Merge Script Lab's Chromium flags, refusing flags that disable HTTPS."""
    env = os.environ if environ is None else environ
    extra = chromium_flags_for_script_lab()
    for flag in REFUSED_CHROMIUM_FLAGS:
        if flag in extra.split():
            raise RuntimeError(f"Refusing Chromium flag {flag}")
    current = env.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    if not extra.strip():
        return current
    merged = " ".join(part for part in (current, extra) if part.strip()).strip()
    env["QTWEBENGINE_CHROMIUM_FLAGS"] = merged
    return merged


def accept_certificate_error(*_args: object, **_kwargs: object) -> bool:
    """Never accept an invalid certificate in the in-app browser."""
    return False


def permission_decision(feature_name: str) -> str:
    """Clipboard helps copy a script out. Everything else is denied out loud."""
    if "clipboard" in (feature_name or "").casefold():
        return "grant"
    return "deny"


def normalize_browser_preference(value: object) -> str:
    text = str(value or "").strip().casefold()
    if text in {"edge", "msedge", "microsoft edge"}:
        return BROWSER_EDGE
    if text in {"chrome", "google chrome", "google-chrome"}:
        return BROWSER_CHROME
    return BROWSER_DEFAULT


def profile_storage_dir(cache_dir: Path) -> Path:
    return Path(cache_dir) / PROFILE_DIR_NAME


def configure_persistent_profile(
    profile: object,
    storage: Path,
    *,
    user_agent: str = DESKTOP_CHROME_USER_AGENT,
    cookie_policy: object | None = None,
    cache_type: object | None = None,
) -> Path:
    """Point a named profile at disk cookies, localStorage, and HTTP cache.

    ``storage`` must be set before the profile loads a page. The default
    Qt profile ignores a late storage-path change, which drops sign-in
    cookies on exit.
    """
    off_record = getattr(profile, "isOffTheRecord", None)
    if callable(off_record) and off_record():
        raise RuntimeError(
            "Script Lab browser profile is off-the-record, so cookies would be discarded on exit."
        )
    root = Path(storage)
    cache = root / "cache"
    root.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    profile.setPersistentStoragePath(str(root))  # type: ignore[attr-defined]
    profile.setCachePath(str(cache))  # type: ignore[attr-defined]
    profile.setHttpUserAgent(user_agent)  # type: ignore[attr-defined]
    if cookie_policy is not None and hasattr(profile, "setPersistentCookiesPolicy"):
        profile.setPersistentCookiesPolicy(cookie_policy)  # type: ignore[attr-defined]
    if cache_type is not None and hasattr(profile, "setHttpCacheType"):
        profile.setHttpCacheType(cache_type)  # type: ignore[attr-defined]
    return root


def apply_web_settings(settings: object, attributes: Mapping[str, object] | None = None) -> list[str]:
    """Apply :data:`PAGE_SETTING_POLICY`. Unknown attributes are skipped."""
    resolved = attributes
    if resolved is None:
        from PySide6.QtWebEngineCore import QWebEngineSettings

        web_attribute = QWebEngineSettings.WebAttribute
        resolved = {
            name: getattr(web_attribute, name)
            for name, _enabled in PAGE_SETTING_POLICY
            if hasattr(web_attribute, name)
        }
    applied: list[str] = []
    for name, enabled in PAGE_SETTING_POLICY:
        if name not in resolved:
            continue
        settings.setAttribute(resolved[name], enabled)  # type: ignore[attr-defined]
        applied.append(f"{name}={enabled}")
    return applied


def login_wall_probe_script() -> str:
    """Return JS that yields the first blocked-login phrase, or ''."""
    phrases = json.dumps(list(LOGIN_WALL_PHRASES))
    return (
        "(function(){"
        "try{"
        "var text=((document.body&&document.body.innerText)||'').slice(0,6000).toLowerCase();"
        f"var phrases={phrases};"
        "for(var i=0;i<phrases.length;i++){if(text.indexOf(phrases[i])!==-1)return phrases[i];}"
        "}catch(e){}"
        "return '';"
        "})()"
    )


def login_wall_reason(url: str, title: str = "", excerpt: str = "") -> LoginWall | None:
    """Classify a navigation. ``None`` means ordinary browsing."""
    if _hard_block(url, title, excerpt):
        return LoginWall("blocked", BLOCKED_LOGIN_MESSAGE)
    if _is_sign_in_url(url):
        return LoginWall("signin", SIGN_IN_MESSAGE)
    return None


def popup_leaves_embed(url: str) -> bool:
    """Auth popups go to the system browser. Other new windows stay in Script Lab."""
    return login_wall_reason(url) is not None


def find_browser_executable(
    preference: str,
    *,
    environ: Mapping[str, str] | None = None,
    path_exists: Callable[[Path], bool] | None = None,
    which: Callable[[str], str | None] | None = None,
) -> Path | None:
    """Locate Edge or Chrome. ``default`` always returns None (OS handler)."""
    choice = normalize_browser_preference(preference)
    if choice == BROWSER_DEFAULT:
        return None
    env = os.environ if environ is None else environ
    exists = path_exists or (lambda path: Path(path).is_file())
    which_fn = which if which is not None else shutil.which
    relative = (
        Path("Microsoft/Edge/Application/msedge.exe")
        if choice == BROWSER_EDGE
        else Path("Google/Chrome/Application/chrome.exe")
    )
    names: Sequence[str] = (
        ("msedge", "msedge.exe") if choice == BROWSER_EDGE else ("chrome", "chrome.exe", "google-chrome", "google-chrome-stable")
    )
    candidates: list[Path] = []
    for key in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        root = env.get(key)
        if root:
            candidates.append(Path(root) / relative)
    for root in (Path(r"C:\Program Files"), Path(r"C:\Program Files (x86)")):
        candidates.append(root / relative)
    for candidate in candidates:
        if exists(candidate):
            return candidate
    for name in names:
        found = which_fn(name)
        if found and exists(Path(found)):
            return Path(found)
    return None


def spawn_browser(argv: list[str]) -> None:
    """Start a browser and return without waiting."""
    kwargs: dict[str, object] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if os.name == "nt":
        flags = 0
        flags |= int(getattr(subprocess, "DETACHED_PROCESS", 0))
        flags |= int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        if flags:
            kwargs["creationflags"] = flags
    subprocess.Popen(argv, **kwargs)  # type: ignore[arg-type]


def open_url_in_system_browser(
    url: str,
    preference: str = BROWSER_DEFAULT,
    *,
    environ: Mapping[str, str] | None = None,
    path_exists: Callable[[Path], bool] | None = None,
    which: Callable[[str], str | None] | None = None,
    start_executable: Callable[[list[str]], None] | None = None,
    open_default: Callable[[str], bool] | None = None,
) -> str:
    """Open ``url`` in Edge, Chrome, or the OS default browser.

    Returns a status sentence. Raises ``ValueError`` for a non-http URL and
    ``RuntimeError`` when nothing could open it.
    """
    normalized = normalize_http_url(url)
    parsed = urllib.parse.urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or any(ch.isspace() for ch in parsed.netloc):
        raise ValueError("Enter an http or https URL to open in Chrome or Edge.")
    choice = normalize_browser_preference(preference)
    label = {BROWSER_EDGE: "Microsoft Edge", BROWSER_CHROME: "Google Chrome"}.get(
        choice, "the system default browser"
    )
    starter = start_executable or spawn_browser
    if open_default is None:
        raise RuntimeError("No system browser handler is available.")
    if choice != BROWSER_DEFAULT:
        exe = find_browser_executable(choice, environ=environ, path_exists=path_exists, which=which)
        if exe is not None:
            starter([str(exe), normalized])
            return f"Opened in {label}."
        if not open_default(normalized):
            raise RuntimeError(f"{label} was not found, and the system default browser did not open.")
        return f"{label} was not found. Opened in the system default browser instead."
    if not open_default(normalized):
        raise RuntimeError("The system default browser did not open this URL.")
    return "Opened in the system default browser."


def _split_url(url: str) -> tuple[str, str, str]:
    raw = normalize_http_url(url)
    parsed = urllib.parse.urlparse(raw)
    host = (parsed.hostname or "").casefold()
    path = urllib.parse.unquote(parsed.path or "").casefold()
    query = urllib.parse.unquote(parsed.query or "").casefold()
    return host, path, query


def _hard_block(url: str, title: str, excerpt: str) -> bool:
    blob = f"{url}\n{title}\n{excerpt}".casefold()
    if "disallowed_useragent" in blob:
        return True
    if _phrase_hit(title) or _phrase_hit(excerpt):
        return True
    host, path, query = _split_url(url)
    if "unsupported_browser" in path or "unsupported_browser" in query:
        return True
    if "browser_not_supported" in path or "browser_not_supported" in query:
        return True
    if host in {"accounts.google.com", "accounts.youtube.com"} or host.endswith(".accounts.google.com"):
        markers = (
            "/signin/rejected",
            "/signin/oauth/error",
            "/info/unknownerror",
            "/v3/signin/rejected",
        )
        if any(marker in path for marker in markers):
            return True
    return False


def _phrase_hit(text: str) -> bool:
    folded = (text or "").casefold()
    if not folded:
        return False
    return any(phrase in folded for phrase in LOGIN_WALL_PHRASES)


def _is_sign_in_url(url: str) -> bool:
    host, path, _query = _split_url(url)
    if not host:
        return False
    if host in _SIGN_IN_HOSTS or host.endswith(".accounts.google.com"):
        return True
    if host in {"claude.ai", "www.claude.ai"} and ("/login" in path or path.startswith("/login")):
        return True
    if host in {"chatgpt.com", "www.chatgpt.com", "chat.openai.com"} and (
        path.startswith("/auth") or "/login" in path or "/sign-in" in path
    ):
        return True
    if host in {"grok.com", "www.grok.com", "grok.x.ai"} and (
        "/login" in path or "/sign-in" in path or path.startswith("/signin")
    ):
        return True
    if host in {"x.com", "www.x.com", "twitter.com", "www.twitter.com", "mobile.twitter.com"} and (
        "/login" in path or "/i/flow/login" in path or "/i/flow/signup" in path
    ):
        return True
    return False
