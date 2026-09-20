from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from trendforge.bootstrap import AppDirs
from trendforge.domain.install_catalog import install_catalog, recommend_ids
from trendforge.services.hardware import detect_hardware
from trendforge.services.installer import free_gb, install_items, item_installed
from trendforge.settings import AppSettings
from trendforge.ui.workers import ProgressWorker


class InstallPanel(QWidget):
    finished = Signal(list)

    def __init__(self, settings: AppSettings, dirs: AppDirs, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.dirs = dirs
        self._worker: ProgressWorker | None = None
        self.boxes: dict[str, QCheckBox] = {}
        root = QVBoxLayout(self)
        self.disk = QLabel()
        self.disk.setObjectName("subtitle")
        rec = QPushButton("Select recommended for this GPU")
        rec.clicked.connect(self.select_recommended)
        all_btn = QPushButton("Select all that fit")
        all_btn.clicked.connect(self.select_all_that_fit)
        row = QHBoxLayout()
        row.addWidget(rec)
        row.addWidget(all_btn)
        row.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        self.list_l = QVBoxLayout(host)
        scroll.setWidget(host)
        self.progress = QProgressBar()
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(140)
        self.start = QPushButton("Install selected models")
        self.start.setObjectName("primary")
        self.start.clicked.connect(self.run_install)
        root.addWidget(QLabel("Setup will download free local models you check. Large cinematic weights go through Maestro when it is running."))
        root.addWidget(self.disk)
        root.addLayout(row)
        root.addWidget(scroll, 1)
        root.addWidget(self.start)
        root.addWidget(self.progress)
        root.addWidget(self.log)
        self.reload()

    def reload(self) -> None:
        hw = detect_hardware()
        while self.list_l.count():
            item = self.list_l.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.boxes.clear()
        rec = recommend_ids(hw)
        for spec in install_catalog():
            have = item_installed(spec, self.dirs, self.settings)
            label = f"{spec.name}  ·  ~{spec.size_gb:g} GB"
            if have:
                label += "  ✓ installed"
            box = QCheckBox(label)
            box.setToolTip(spec.description)
            fits_vram = (not spec.requires_gpu) or (hw.cuda_available and hw.vram_total_gb + 0.4 >= spec.min_vram_gb)
            fits_ram = hw.ram_total_gb + 0.4 >= spec.min_ram_gb
            # First-run default: every model this PC can actually run.
            box.setChecked(fits_vram and fits_ram and not have)
            if spec.id in rec and not have:
                box.setChecked(True)
            if have:
                box.setEnabled(True)
                box.setChecked(False)
            self.boxes[spec.id] = box
            self.list_l.addWidget(box)
        self.list_l.addStretch()
        self.disk.setText(
            f"{hw.gpu_name} · {hw.vram_total_gb:g} GB VRAM · "
            f"{free_gb(self.dirs.models)} GB free on the models drive · "
            f"recommended + every model this GPU can run is pre-checked"
        )

    def select_recommended(self) -> None:
        rec = recommend_ids(detect_hardware())
        for ident, box in self.boxes.items():
            have = item_installed(next(i for i in install_catalog() if i.id == ident), self.dirs, self.settings)
            box.setChecked(ident in rec and not have)

    def select_all_that_fit(self) -> None:
        hw = detect_hardware()
        for spec in install_catalog():
            box = self.boxes.get(spec.id)
            if not box:
                continue
            if item_installed(spec, self.dirs, self.settings):
                box.setChecked(False)
                continue
            fits_vram = (not spec.requires_gpu) or (hw.cuda_available and hw.vram_total_gb + 0.4 >= spec.min_vram_gb)
            fits_ram = hw.ram_total_gb + 0.4 >= spec.min_ram_gb
            box.setChecked(fits_vram and fits_ram)

    def run_install(self) -> None:
        ids = [i for i, box in self.boxes.items() if box.isChecked()]
        if not ids:
            self.log.setPlainText("Nothing selected.")
            return
        total = sum(s.size_gb for s in install_catalog() if s.id in ids)
        free = free_gb(self.dirs.models)
        if total > free - 2:
            self.log.setPlainText(f"Not enough disk: need ~{total:.1f} GB, have {free:.1f} GB free.")
            return
        self.start.setEnabled(False)
        self.log.setPlainText("Starting installs…")
        self.progress.setValue(1)

        def work(on_progress, cancelled):
            return install_items(ids, self.dirs, self.settings, on_progress=on_progress, cancelled=cancelled)

        self._worker = ProgressWorker(work, self)
        self._worker.progressed.connect(self._tick)
        self._worker.ok.connect(self._done)
        self._worker.failed.connect(self._fail)
        self._worker.start()

    def _tick(self, msg: str, pct: int) -> None:
        self.progress.setValue(max(1, min(99, pct)))
        self.log.appendPlainText(msg)

    def _done(self, notes: list) -> None:
        self.start.setEnabled(True)
        self.progress.setValue(100)
        self.log.setPlainText("\n".join(str(n) for n in notes))
        self.reload()
        self.finished.emit(list(notes))

    def _fail(self, msg: str) -> None:
        self.start.setEnabled(True)
        self.log.appendPlainText(msg)
        self.reload()
