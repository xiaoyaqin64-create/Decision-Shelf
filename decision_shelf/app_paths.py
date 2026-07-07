from __future__ import annotations

import os
import sys
from pathlib import Path


APP_DIR_NAME = "Decision Shelf"


def user_data_dir() -> Path:
    """Return a stable, writable directory for desktop user data."""
    override = os.getenv("DECISION_SHELF_HOME", "").strip()
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
        if base:
            return Path(base) / APP_DIR_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    return Path.home() / ".decision-shelf"


def configure_desktop_environment() -> Path:
    """Point the database and settings at the current user's app directory."""
    root = user_data_dir()
    root.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("DECISION_SHELF_DB", str(root / "decision_shelf.db"))
    os.environ.setdefault("DECISION_SHELF_CONFIG", str(root / "settings.json"))
    return root


def bundled_static_dir() -> Path:
    """Locate Vite assets in source checkouts, PyInstaller, and py2app bundles."""
    resource_path = os.getenv("RESOURCEPATH", "").strip()
    bundle_root = Path(
        resource_path
        or getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)
    )
    return bundle_root / "frontend" / "dist"
