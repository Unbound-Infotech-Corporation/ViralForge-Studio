from __future__ import annotations

import shutil
from pathlib import Path

from trendforge.services.maestro_detect import (
    extract_local_urls,
    find_maestro_root,
    find_pinokio_home,
    normalize_local_url,
    urls_from_install,
)

_SCRATCH = Path(__file__).resolve().parent / "_scratch_maestro"


def _scratch() -> Path:
    if _SCRATCH.exists():
        shutil.rmtree(_SCRATCH, ignore_errors=True)
    _SCRATCH.mkdir(parents=True)
    return _SCRATCH


def test_normalize_rewrites_wildcard_bind() -> None:
    assert normalize_local_url("http://0.0.0.0:42130/") == "http://127.0.0.1:42130"
    assert normalize_local_url("http://localhost:7860") == "http://127.0.0.1:7860"


def test_extract_urls_from_pinokio_start_log() -> None:
    text = """
==================================================
  Maestro UI:    http://127.0.0.1:42130/
  Classic UI:    http://127.0.0.1:42130/classic/
  API docs:      http://127.0.0.1:42130/docs
==================================================
INFO:     Uvicorn running on http://127.0.0.1:42130 (Press CTRL+C to quit)
"""
    urls = extract_local_urls(text)
    assert "http://127.0.0.1:42130" in urls


def test_extract_urls_from_local_set_events() -> None:
    text = '{ "url": "http://127.0.0.1:42130" }'
    assert "http://127.0.0.1:42130" in extract_local_urls(text)


def test_finds_maestro_git_under_drive_home(monkeypatch) -> None:
    home = _scratch() / "pinokio"
    app = home / "api" / "Maestro.git" / "app"
    app.mkdir(parents=True)
    (app / "launch.py").write_text("# maestro", encoding="utf-8")
    (home / "api" / "Maestro.git" / "start.js").write_text("module.exports = {}", encoding="utf-8")
    (home / "api" / "Maestro.git" / "pinokio.js").write_text("title: 'Maestro'", encoding="utf-8")
    (home / "ENVIRONMENT").write_text("PINOKIO_DRIVE=./drive\n", encoding="utf-8")
    (home / "api" / "Maestro.git" / "ui").mkdir()

    try:
        assert find_maestro_root(home) == home / "api" / "Maestro.git"

        monkeypatch.setattr(
            "trendforge.services.maestro_detect.iter_drive_pinokio_homes",
            lambda: [home],
        )
        monkeypatch.setattr("trendforge.services.maestro_detect.pinokio_home_from_config", lambda: None)
        monkeypatch.delenv("PINOKIO_HOME", raising=False)
        assert find_pinokio_home() == home
    finally:
        shutil.rmtree(_SCRATCH, ignore_errors=True)


def test_urls_from_latest_start_log() -> None:
    maestro = _scratch() / "Maestro.git"
    log_dir = maestro / "logs" / "api" / "start.js"
    log_dir.mkdir(parents=True)
    (log_dir / "latest").write_text(
        "Maestro UI:    http://127.0.0.1:42130/\nUvicorn running on http://127.0.0.1:42130\n",
        encoding="utf-8",
    )
    try:
        urls = urls_from_install(maestro)
        assert urls[0] == "http://127.0.0.1:42130"
    finally:
        shutil.rmtree(_SCRATCH, ignore_errors=True)
