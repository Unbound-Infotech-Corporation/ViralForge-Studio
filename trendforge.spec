# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None
root = Path(SPECPATH)

datas = collect_data_files("trendforge")
hidden = collect_submodules("trendforge")
hidden += [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtNetwork",
    "pyttsx3.drivers",
    "pyttsx3.drivers.sapi5",
    "imageio_ffmpeg",
]

a = Analysis(
    ["run.py"],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "torch", "tensorflow"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TrendForgeStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(root / "trendforge" / "assets" / "icons" / "trendforge.ico")
    if (root / "trendforge" / "assets" / "icons" / "trendforge.ico").exists()
    else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="TrendForgeStudio",
)
