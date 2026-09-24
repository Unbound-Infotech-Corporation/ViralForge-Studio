from __future__ import annotations

import argparse
import sys


def _prepare_environment() -> None:
    """Make Qt behave on high-DPI Windows before QApplication exists."""
    import os

    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")
    # Avoid Qt logging noise in packaged builds
    os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.fonts.warning=false")


def main(argv: list[str] | None = None) -> int:
    _prepare_environment()
    argv = list(sys.argv if argv is None else argv)

    parser = argparse.ArgumentParser(prog="trendforge", description="TrendForge Studio")
    parser.add_argument("--offscreen", action="store_true", help="Use Qt offscreen platform (CI / smoke tests)")
    parser.add_argument("--smoke", action="store_true", help="Boot UI, verify widgets, then exit")
    parser.add_argument("--reset-wizard", action="store_true", help="Show the first-run wizard again")
    parser.add_argument(
        "--install-models",
        action="store_true",
        help="Download local models into TRENDFORGE_HOME (default F:\\TrendForge) and exit",
    )
    args, qt_args = parser.parse_known_args(argv[1:])

    import os

    os.environ.setdefault("TRENDFORGE_HOME", r"F:\TrendForge")

    if args.install_models:
        return _install_models_cli()

    if args.offscreen or args.smoke:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    _preload_webengine()

    from trendforge import __app_name__, __org_name__, __version__
    from trendforge.bootstrap import ensure_app_dirs, install_exception_hook
    from trendforge.logging_setup import setup_logging
    from trendforge.settings import AppSettings
    from trendforge.ui.main_window import MainWindow
    from trendforge.ui.theme import apply_theme, load_app_icon

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    QApplication.setApplicationName(__app_name__)
    QApplication.setOrganizationName(__org_name__)
    QApplication.setApplicationVersion(__version__)
    QApplication.setDesktopFileName("trendforge-studio")

    qt_argv = [argv[0], *qt_args]
    app = QApplication(qt_argv)
    app.setWindowIcon(load_app_icon())

    dirs = ensure_app_dirs()
    setup_logging(dirs.logs / "trendforge.log")
    install_exception_hook()

    settings = AppSettings.load(dirs)
    if args.reset_wizard:
        settings.wizard_complete = False
        settings.save()

    apply_theme(app, settings.theme)

    window = MainWindow(settings=settings, app_dirs=dirs)
    if not args.smoke:
        window.show()
        if not settings.wizard_complete:
            window.show_setup_wizard()
        return app.exec()

    # Headless smoke: construct, show, process events, quit.
    window.show()
    app.processEvents()
    from trendforge.services.hardware import detect_hardware

    hw = detect_hardware()
    print(f"SMOKE_OK version={__version__} gpu={hw.gpu_name!r} vram={hw.vram_total_gb}")
    return 0


def _preload_webengine() -> None:
    """Import Qt WebEngine before QApplication. Missing Addons must not block Studio."""
    try:
        import PySide6.QtWebEngineWidgets  # noqa: F401
    except Exception:
        return


def _install_models_cli() -> int:
    from trendforge.bootstrap import ensure_app_dirs
    from trendforge.logging_setup import setup_logging
    from trendforge.services.installer import ids_that_fit, install_items
    from trendforge.settings import AppSettings

    dirs = ensure_app_dirs()
    setup_logging(dirs.logs / "trendforge.log")
    settings = AppSettings.load(dirs)
    print(f"TRENDFORGE_HOME={dirs.root}")
    print(f"models={dirs.models}")
    ids = ids_that_fit(dirs, settings, reserve_gb=8.0, local_only=True)
    if not ids:
        print("Nothing new to install (already present, or not enough disk).")
        return 0
    print("Installing: " + ", ".join(ids))

    def progress(msg: str, pct: int) -> None:
        print(f"[{pct:3d}%] {msg}", flush=True)

    notes = install_items(ids, dirs, settings, on_progress=progress)
    for note in notes:
        print(note)
    failed = any(str(n).startswith("Failed:") for n in notes)
    return 1 if failed and not any(str(n).startswith("Installed:") for n in notes) else 0


if __name__ == "__main__":
    raise SystemExit(main())
