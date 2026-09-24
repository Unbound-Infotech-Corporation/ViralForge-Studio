"""Polish guards: visible models, settings migration, cinema publish refusal, empty projects."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from trendforge.bootstrap import AppDirs
from trendforge.cinema.director import CinemaDirector
from trendforge.cinema.publish import cinema_publish_block_reason
from trendforge.domain.catalog import is_hidden_model, visible_model_catalog
from trendforge.domain.enums import BackendKind, PipelineStage
from trendforge.domain.serialize import project_from_dict, request_from_dict
from trendforge.services.projects import ProjectStore
from trendforge.settings import AppSettings


def test_cogvideox_sits_beside_wan_and_legacy_is_hidden() -> None:
    ids = [item.id for item in visible_model_catalog()]
    assert "cogvideox" in ids
    assert "wan22_ti2v_5b" in ids
    assert ids.index("cogvideox") == ids.index("wan22_ti2v_5b") + 1
    assert "wan22_a14b" in ids
    for hidden in ("maestro_director", "ltx25_distilled", "minimax_h3", "hunyuan_15", "comfyui"):
        assert hidden not in ids
        assert is_hidden_model(hidden)
    cog = next(item for item in visible_model_catalog() if item.id == "cogvideox")
    wan = next(item for item in visible_model_catalog() if item.id == "wan22_ti2v_5b")
    assert cog.backend is BackendKind.NATIVE_CINEMA
    assert wan.backend is BackendKind.NATIVE_CINEMA
    assert cog.mark and wan.mark


def test_card_and_silent_cinema_are_refused(tmp_path: Path) -> None:
    models = tmp_path / "cinema"
    card = cinema_publish_block_reason(
        card_stand_in=True,
        require_audio=True,
        has_audio=False,
        model_id="cogvideox",
        models_dir=models,
    )
    assert card is not None
    assert "CogVideoX" in card
    assert "will not publish" in card
    assert "cogvideox" in card
    silent = cinema_publish_block_reason(
        card_stand_in=False,
        require_audio=True,
        has_audio=False,
        model_id="wan22_ti2v_5b",
        models_dir=models,
    )
    assert silent is not None
    assert "silent" in silent.lower()
    ok = cinema_publish_block_reason(
        card_stand_in=False,
        require_audio=True,
        has_audio=True,
        model_id="wan22_ti2v_5b",
        models_dir=models,
    )
    assert ok is None
    assert CinemaDirector.__dict__["uses_card_standin"]


def test_settings_migration_repairs_enums_and_legacy_model(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "theme": "nope",
                "last_style": "not-a-style",
                "last_model_id": "maestro_director",
                "last_format": "gone",
                "installed_items": "not-a-list",
                "show_console_on_produce": True,
                "console_hint_shown": False,
            }
        ),
        encoding="utf-8",
    )
    dirs = AppDirs(
        root=tmp_path,
        projects=tmp_path / "projects",
        gallery=tmp_path / "gallery",
        cache=tmp_path / "cache",
        logs=tmp_path / "logs",
        models=tmp_path / "models",
        music=tmp_path / "music",
        tmp=tmp_path / "tmp",
        settings_file=path,
    )
    settings = AppSettings.load(dirs)
    assert settings.last_model_id == "auto"
    assert settings.last_style.value == "cinematic"
    assert settings.last_format.value == "video"
    assert settings.installed_items == []
    assert settings.show_console_on_produce is True
    assert settings.console_hint_shown is False

    path.write_text("{", encoding="utf-8")
    broken = AppSettings.load(dirs)
    assert broken.last_model_id == "auto"
    assert broken.show_console_on_produce is True


def test_request_and_empty_project_do_not_crash(tmp_path: Path) -> None:
    req = request_from_dict(
        {
            "topic": None,
            "style": "nope",
            "backend": "nope",
            "voice": "nope",
            "episode_index": "x",
            "music_volume": "loud",
            "category": "nope",
        }
    )
    assert req.topic == ""
    assert req.episode_index == 1
    project = project_from_dict(
        {
            "title": None,
            "updated_at": None,
            "stage": "nope",
            "request": None,
            "script": {"shots": ["bad", {"title": "ok", "status": "nope", "duration_sec": "4"}]},
        }
    )
    assert project.title == "Untitled"
    assert project.updated_at == ""
    assert project.stage is PipelineStage.IDLE
    assert project.script is not None
    assert len(project.script.shots) == 1

    store = ProjectStore(tmp_path / "projects")
    (store.root / "empty").mkdir()
    (store.root / "empty" / "project.json").write_text(json.dumps({"title": None, "updated_at": None}), encoding="utf-8")
    listed = store.list_projects()
    assert listed
    assert listed[0].title == "Untitled"
    assert store.gallery_videos() == []


def test_job_console_menu_statusbar_and_produce(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("PySide6.QtWidgets")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from trendforge.ui.main_window import MainWindow

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
    view = next(action.menu() for action in window.menuBar().actions() if action.text().replace("&", "") == "View")
    assert view is not None
    labels = [action.text() for action in view.actions()]
    assert "Job Console" in labels
    shortcut = window.console_action.shortcut().toString()
    assert "Ctrl" in shortcut and "`" in shortcut
    assert window.console_btn.text() == "Console"
    assert window.console_btn.toolTip().startswith("Job Console")
    assert not window.hint_bar.isHidden()
    assert settings.show_console_on_produce is True
    assert window.console.isHidden()
    window.create.produce_started.emit()
    assert not window.console.isHidden()
    ids = [window.create.model.itemData(i) for i in range(window.create.model.count())]
    assert "cogvideox" in ids
    assert "maestro_director" not in ids
    assert window.create.format_row.objectName() == "choiceRow"
    assert window.create.model_row.objectName() == "choiceRow"
    assert window.create.style_row.objectName() == "choiceRow"
    window.close()
