from __future__ import annotations

from pathlib import Path

from setuptools import setup


ROOT = Path(__file__).resolve().parent.parent


def data_files(directory: Path, destination: str) -> list[tuple[str, list[str]]]:
    groups: list[tuple[str, list[str]]] = []
    for folder in [directory, *sorted(path for path in directory.rglob("*") if path.is_dir())]:
        files = [str(path) for path in sorted(folder.iterdir()) if path.is_file()]
        if files:
            relative = folder.relative_to(directory)
            target = str(Path(destination) / relative)
            groups.append((target, files))
    return groups


setup(
    name="Decision Shelf",
    version="0.3.1",
    app=[str(ROOT / "desktop_entry.py")],
    data_files=data_files(ROOT / "frontend" / "dist", "frontend/dist"),
    options={
        "py2app": {
            "argv_emulation": False,
            "iconfile": str(ROOT / "build-assets" / "decision-shelf.icns"),
            "packages": ["decision_shelf", "keyring.backends", "webview"],
            "includes": ["WebKit", "Foundation", "Quartz", "Security"],
            "excludes": ["PyQt5", "PyQt6", "PySide2", "PySide6", "tkinter"],
            "plist": {
                "CFBundleName": "Decision Shelf",
                "CFBundleDisplayName": "Decision Shelf",
                "CFBundleIdentifier": "com.decisionshelf.desktop",
                "CFBundleShortVersionString": "0.3.1",
                "LSMinimumSystemVersion": "12.0",
                "NSHighResolutionCapable": True,
            },
        }
    },
    setup_requires=["py2app"],
)
