from __future__ import annotations

import os
import socket
import threading
import time
import urllib.request
from pathlib import Path

import uvicorn


_server: uvicorn.Server | None = None
_thread: threading.Thread | None = None
_port: int | None = None


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait(url: str, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("Decision Shelf mobile server failed to start")


def start_server(data_dir: str) -> int:
    global _server, _thread, _port
    if _thread and _thread.is_alive() and _port:
        return _port

    root = Path(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    os.environ["DECISION_SHELF_PLATFORM"] = "android"
    os.environ["DECISION_SHELF_HOME"] = str(root)
    os.environ["DECISION_SHELF_DB"] = str(root / "decision_shelf.db")
    os.environ["DECISION_SHELF_CONFIG"] = str(root / "settings.json")

    from .settings import load_user_settings
    from .webapp import create_app

    load_user_settings()
    static_dir = Path(__file__).resolve().parent.parent / "mobile_assets"
    if not (static_dir / "index.html").exists():
        raise RuntimeError("Mobile frontend assets are missing")

    _port = _free_port()
    app = create_app(static_dir=static_dir)
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=_port,
        log_config=None,
        access_log=False,
    )
    _server = uvicorn.Server(config)
    _server.install_signal_handlers = lambda: None
    _thread = threading.Thread(target=_server.run, name="decision-shelf-mobile", daemon=True)
    _thread.start()
    _wait(f"http://127.0.0.1:{_port}/api/config")
    return _port


def stop_server() -> None:
    global _server, _thread
    if _server:
        _server.should_exit = True
    if _thread:
        _thread.join(timeout=3)
    _server = None
    _thread = None
