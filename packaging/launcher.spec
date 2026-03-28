# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


project_root = Path(SPECPATH).resolve().parent

datas = [
    (str(project_root / "frontend" / "dist"), "frontend/dist"),
    (str(project_root / "tools"), "tools"),
    (str(project_root / ".tools"), ".tools"),
    (str(project_root / "design-system"), "design-system"),
    (str(project_root / "image.png"), "."),
    (str(project_root / "packaging" / "app.ico"), "."),
]

hiddenimports = [
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtPrintSupport",
    "mobi_manga_app.api",
    "mobi_manga_app.dashboard",
    "mobi_manga_app.workflow",
]


a = Analysis(
    [str(project_root / "packaging" / "launcher_entry.py")],
    pathex=[str(project_root), str(project_root / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MangaEnhancementLauncher",
    icon=str(project_root / "packaging" / "app.ico"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MangaEnhancementLauncher",
)
