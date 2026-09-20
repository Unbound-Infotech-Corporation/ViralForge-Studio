from __future__ import annotations

import json
import os
import re
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from trendforge.logging_setup import get_logger
from trendforge.settings import DEFAULT_MAESTRO_PORTS

log = get_logger("maestro.detect")

_LOCAL_URL_RE = re.compile(
    r"https?://(?:127\.0\.0\.1|localhost|0\.0\.0\.0|\[::1?\])[:/]\d+",
    re.IGNORECASE,
)
_PORT_IN_TEXT_RE = re.compile(
    r"(?:Maestro UI|Uvicorn running on|Classic UI|API docs)\s*:\s*https?://[^\s/]+[:/](\d+)",
    re.IGNORECASE,
)

PINOKIO_EXE_CANDIDATES = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Pinokio" / "Pinokio.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "pinokio" / "Pinokio.exe",
    Path("C:/Program Files/Pinokio/Pinokio.exe"),
    Path("C:/Program Files (x86)/Pinokio/Pinokio.exe"),
]

LOG_RELATIVE_PATHS = (
    "logs/api/start.js/latest",
    "logs/api/start.js/events",
    "logs/api/start_sol.js/latest",
    "logs/api/start_sol.js/events",
    "logs/api/start_classic.js/latest",
    "logs/api/start_classic.js/events",
)


@dataclass(slots=True)
class MaestroInstall:
    found: bool
    pinokio_exe: Path | None = None
    pinokio_home: Path | None = None
    maestro_root: Path | None = None
    env_dir: Path | None = None
    running_url: str = ""
    notes: list[str] = field(default_factory=list)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_text_tail(path: Path, max_chars: int = 24_000) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - max_chars))
            return handle.read()
    except OSError:
        return ""


def normalize_local_url(url: str) -> str:
    raw = url.strip().rstrip("/")
    if not raw:
        return ""
    if "://" not in raw:
        raw = "http://" + raw
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if host in {"0.0.0.0", "::", "::1", "[::1]", "[::]"}:
        host = "127.0.0.1"
    if host in {"localhost"}:
        host = "127.0.0.1"
    if not host or parsed.port is None:
        return raw
    scheme = parsed.scheme or "http"
    return f"{scheme}://{host}:{parsed.port}"


def extract_local_urls(text: str) -> list[str]:
    found: list[str] = []
    for match in _LOCAL_URL_RE.findall(text):
        url = normalize_local_url(match)
        if url:
            found.append(url)
    for match in re.finditer(r'"url"\s*:\s*"(https?://[^"]+)"', text):
        url = normalize_local_url(match.group(1))
        if url:
            found.append(url)
    for match in _PORT_IN_TEXT_RE.finditer(text):
        found.append(f"http://127.0.0.1:{match.group(1)}")
    return found


def _is_pinokio_home(path: Path) -> bool:
    try:
        if not path.is_dir():
            return False
    except OSError:
        return False
    return (path / "api").is_dir() or (path / "ENVIRONMENT").exists() or (path / "drive").is_dir()


def pinokio_home_from_config() -> Path | None:
    appdata = Path(os.environ.get("APPDATA", ""))
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    candidates = [
        appdata / "Pinokio" / "config.json",
        appdata / "pinokio" / "config.json",
        local / "Pinokio" / "config.json",
        Path.home() / ".pinokio" / "config.json",
    ]
    for roaming in candidates:
        data = _read_json(roaming) if roaming.exists() else None
        if not data:
            continue
        for key in ("home", "HOME", "path", "drive"):
            value = data.get(key)
            if isinstance(value, str) and value:
                path = Path(value)
                if _is_pinokio_home(path) or path.exists():
                    return path
    return None


def iter_drive_pinokio_homes() -> list[Path]:
    homes: list[Path] = []
    for code in range(ord("C"), ord("Z") + 1):
        candidate = Path(f"{chr(code)}:/pinokio")
        try:
            if _is_pinokio_home(candidate):
                homes.append(candidate)
        except OSError:
            continue
    return homes


def find_pinokio_exe() -> Path | None:
    for path in PINOKIO_EXE_CANDIDATES:
        if path and path.exists():
            return path
    return None


def find_pinokio_home() -> Path | None:
    configured = pinokio_home_from_config()
    if configured:
        return configured
    env_home = os.environ.get("PINOKIO_HOME") or ""
    ordered: list[Path] = []
    if env_home:
        ordered.append(Path(env_home))
    ordered.extend(
        [
            Path.home() / "pinokio",
            Path(os.environ.get("USERPROFILE", "")) / "pinokio",
        ]
    )
    ordered.extend(iter_drive_pinokio_homes())
    seen: set[Path] = set()
    for path in ordered:
        try:
            resolved = path.resolve() if path.exists() else path
        except OSError:
            resolved = path
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            if _is_pinokio_home(path):
                return path
        except OSError:
            continue
    return None


def _looks_like_maestro(folder: Path) -> bool:
    markers = [
        folder / "pinokio.js",
        folder / "start.js",
        folder / "app" / "launch.py",
        folder / "app" / "wgp.py",
    ]
    if any(m.exists() for m in markers):
        text_files = [folder / "pinokio.js", folder / "README.md", folder / "package.json"]
        blob = ""
        for tf in text_files:
            if tf.exists():
                try:
                    blob += tf.read_text(encoding="utf-8", errors="ignore")[:4000].lower()
                except OSError:
                    continue
        if "maestro" in blob or "blizaine" in blob or "wangp" in blob or "wgp.py" in blob:
            return True
        if (folder / "app" / "launch.py").exists() and (folder / "ui").exists():
            return True
    name = folder.name.lower().replace(".", "")
    return "maestro" in name and (folder / "app").exists()


def find_maestro_root(home: Path | None) -> Path | None:
    if not home:
        return None
    try:
        if _looks_like_maestro(home):
            return home
    except OSError:
        pass
    search_roots: list[Path] = []
    api = home / "api"
    if api.is_dir():
        search_roots.append(api)
    if home.name.lower() == "api":
        search_roots.append(home)
    ranked: list[Path] = []
    for root in search_roots:
        try:
            children = list(root.iterdir())
        except OSError:
            continue
        for child in children:
            try:
                if child.is_dir() and _looks_like_maestro(child):
                    ranked.append(child)
            except OSError:
                continue
    if ranked:
        ranked.sort(key=lambda p: (0 if "maestro" in p.name.lower() else 1, p.name.lower()))
        return ranked[0]
    return None


def pick_env_dir(maestro_root: Path | None) -> Path | None:
    if not maestro_root:
        return None
    app = maestro_root / "app"
    for name in ("env-sol", "env-rtx50", "env"):
        candidate = app / name
        if candidate.exists():
            return candidate
    return None


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.2):
            return True
    except OSError:
        return False


def urls_from_install(maestro_root: Path | None) -> list[str]:
    if not maestro_root:
        return []
    found: list[str] = []
    static_rels = (
        "pinokio.json",
        "url.txt",
        "app/server.json",
        "app/local.json",
        "cache/url.txt",
    )
    for rel in (*static_rels, *LOG_RELATIVE_PATHS):
        path = maestro_root / rel
        if not path.is_file():
            continue
        text = _read_text_tail(path)
        if text:
            found.extend(extract_local_urls(text))
    # Newest log lines are at the end; keep last-seen first after reverse.
    unique: list[str] = []
    seen: set[str] = set()
    for url in reversed(found):
        if url in seen:
            continue
        seen.add(url)
        unique.append(url)
    return unique


def urls_from_running_processes() -> list[str]:
    try:
        import psutil
    except ImportError:
        return []
    urls: list[str] = []
    for proc in psutil.process_iter(["pid", "name", "exe", "cwd", "cmdline"]):
        try:
            info = proc.info
        except (psutil.Error, OSError):
            continue
        blob = " ".join(
            part
            for part in (
                str(info.get("exe") or ""),
                str(info.get("cwd") or ""),
                " ".join(str(item) for item in (info.get("cmdline") or [])),
            )
            if part
        ).lower()
        if "maestro" not in blob:
            continue
        if "launch.py" not in blob and "wgp.py" not in blob and "uvicorn" not in blob:
            continue
        try:
            connections = proc.net_connections(kind="inet")
        except (psutil.Error, OSError):
            continue
        for conn in connections:
            if getattr(conn, "status", "") != "LISTEN" or not conn.laddr:
                continue
            host = conn.laddr.ip
            if host in {"0.0.0.0", "::", "::1"}:
                host = "127.0.0.1"
            if host not in {"127.0.0.1", "localhost"}:
                continue
            urls.append(f"http://127.0.0.1:{conn.laddr.port}")
    unique: list[str] = []
    seen: set[str] = set()
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        unique.append(url)
    return unique


def _json_from_response(res: httpx.Response) -> Any:
    try:
        return res.json()
    except Exception:
        return None


def is_maestro_api(url: str, timeout: float = 2.0) -> bool:
    """True when this HTTP origin is a running Maestro FastAPI server."""
    base = normalize_local_url(url)
    if not base:
        return False
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            detect = client.get(base + "/api/v1/system-detect")
            if detect.status_code == 200:
                payload = _json_from_response(detect)
                if isinstance(payload, dict) and (
                    "hardware" in payload or "recommended" in payload or "gpu" in payload
                ):
                    return True
            models = client.get(base + "/api/v1/models")
            if models.status_code == 200:
                payload = _json_from_response(models)
                if isinstance(payload, dict) and ("models" in payload or "families" in payload):
                    return True
                if isinstance(payload, list):
                    return True
            docs = client.get(base + "/docs")
            if docs.status_code == 200 and "maestro" in docs.text.lower():
                return True
    except httpx.HTTPError:
        return False
    except Exception:
        return False
    return False


def discover_running_url(preferred: str = "", maestro_root: Path | None = None) -> str:
    candidates: list[str] = []
    env_url = os.environ.get("TRENDFORGE_MAESTRO_URL") or os.environ.get("MAESTRO_URL") or ""
    if preferred:
        candidates.append(normalize_local_url(preferred))
    if env_url:
        candidates.append(normalize_local_url(env_url))
    candidates.extend(urls_from_running_processes())
    candidates.extend(urls_from_install(maestro_root))
    for port in DEFAULT_MAESTRO_PORTS:
        if _port_open("127.0.0.1", port):
            candidates.append(f"http://127.0.0.1:{port}")

    seen: set[str] = set()
    for url in candidates:
        url = normalize_local_url(url)
        if not url or url in seen:
            continue
        seen.add(url)
        parsed = urlparse(url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port
        if port is not None and not _port_open(host, port):
            continue
        if is_maestro_api(url):
            return url
    return ""


def detect_maestro(preferred_url: str = "", extra_home: str = "") -> MaestroInstall:
    pinokio = find_pinokio_exe()
    home = find_pinokio_home()
    if extra_home:
        extra = Path(extra_home)
        try:
            if extra.exists():
                home = extra
        except OSError:
            pass
    maestro = find_maestro_root(home)
    if maestro is None:
        for drive_home in iter_drive_pinokio_homes():
            maestro = find_maestro_root(drive_home)
            if maestro:
                home = drive_home
                break
    env = pick_env_dir(maestro)
    running = discover_running_url(preferred_url, maestro)
    notes: list[str] = []
    if pinokio:
        notes.append(f"Pinokio found at {pinokio}")
    else:
        notes.append("Pinokio desktop app not found — OK; Maestro can run standalone.")
    if home:
        notes.append(f"Pinokio home: {home}")
    if maestro:
        notes.append(f"Maestro app: {maestro}")
    else:
        notes.append("Maestro folder was not found under pinokio/api.")
    if env:
        notes.append(f"Maestro env: {env.name}")
    if running:
        notes.append(f"Maestro API is reachable at {running}")
    else:
        notes.append("Maestro does not appear to be running. Start it from Pinokio.")
    return MaestroInstall(
        found=bool(maestro or running),
        pinokio_exe=pinokio,
        pinokio_home=home,
        maestro_root=maestro,
        env_dir=env,
        running_url=running,
        notes=notes,
    )
