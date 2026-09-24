from pathlib import Path

from trendforge.domain.enums import BackendKind
from trendforge.services.hardware import recommend_for_vram


def test_no_gpu_uses_quick():
    backend, model, notes = recommend_for_vram(0, False)
    assert backend is BackendKind.QUICK_EXPLAINER
    assert model == "quick_explainer"
    assert notes


def test_8gb_avoids_a14b():
    backend, model, notes = recommend_for_vram(8, True)
    assert backend is BackendKind.NATIVE_CINEMA
    assert model != "wan22_a14b"
    assert notes
    assert "Pinokio" not in " ".join(notes)


def test_24gb_can_use_large():
    backend, model, _ = recommend_for_vram(24, True)
    assert backend is BackendKind.NATIVE_CINEMA
    assert model == "wan22_a14b"


def test_data_root_honors_env(monkeypatch):
    target = Path(r"F:\TrendForge\_env_home")
    monkeypatch.setenv("TRENDFORGE_HOME", str(target))
    from trendforge.bootstrap import resolve_data_root

    assert resolve_data_root() == target.resolve()
