from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files


root = Path(SPECPATH).parent
webview_data = collect_data_files("webview")

a = Analysis(
    [str(root / "desktop_entry.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / "frontend" / "dist"), "frontend/dist"), *webview_data],
    hiddenimports=[
        "keyring.backends.Windows",
        "keyring.backends.chainer",
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan.on",
        "webview.platforms.edgechromium",
        "webview.platforms.winforms",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "cefpython3",
        "gi",
        "gtk",
        "tkinter",
        "IPython",
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
        "jupyter_client",
        "jupyter_core",
        "zmq",
        "qtpy",
        "keyring.backends.SecretService",
        "keyring.backends.kwallet",
        "keyring.backends.libsecret",
        "keyring.backends.macOS",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Decision Shelf",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(root / "build-assets" / "decision-shelf.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Decision Shelf",
)
