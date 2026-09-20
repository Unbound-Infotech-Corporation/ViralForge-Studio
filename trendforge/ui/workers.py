from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, QThread, Signal


class FnWorker(QThread):
    ok = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:
        try:
            self.ok.emit(self._fn())
        except Exception as exc:
            self.failed.emit(str(exc))


class ProgressWorker(QThread):
    progressed = Signal(str, int)
    ok = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._fn = fn
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            result = self._fn(
                on_progress=lambda msg, pct: self.progressed.emit(str(msg), int(pct)),
                cancelled=lambda: self._cancel,
            )
            self.ok.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class PipelineWorker(QThread):
    progressed = Signal(object)
    ok = Signal(object)
    failed = Signal(str)

    def __init__(self, runner: Callable, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._runner = runner
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            result = self._runner(
                on_progress=lambda p: self.progressed.emit(p),
                cancelled=lambda: self._cancel,
            )
            self.ok.emit(result)
        except Exception as exc:
            if self._cancel:
                self.failed.emit("Cancelled")
            else:
                self.failed.emit(str(exc))
