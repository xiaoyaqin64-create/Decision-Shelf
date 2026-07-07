from __future__ import annotations

import ctypes
import logging
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

import uvicorn

from .app_paths import bundled_static_dir, configure_desktop_environment
from .settings import load_user_settings


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_until_ready(url: str, timeout: float = 12.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("本地服务启动超时。请重新打开应用；若仍失败，请查看 desktop.log。")


def _show_error(message: str) -> None:
    detail = f"Decision Shelf 无法启动\n\n{message}"
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, detail, "Decision Shelf", 0x10)
    elif sys.platform == "darwin":
        escaped = detail.replace("\\", "\\\\").replace('"', '\\"')
        subprocess.run(
            ["osascript", "-e", f'display alert "Decision Shelf" message "{escaped}"'],
            check=False,
        )
    else:
        print(detail, file=sys.stderr)


def _configure_logging(root: Path) -> None:
    logging.basicConfig(
        filename=root / "desktop.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        encoding="utf-8",
    )


def _run() -> None:
    root = configure_desktop_environment()
    _configure_logging(root)
    load_user_settings()

    static_dir = bundled_static_dir()
    if not (static_dir / "index.html").exists():
        raise RuntimeError("应用界面资源缺失，请重新下载并完整解压便携包。")

    # Import only after the per-user environment has been configured.
    from .webapp import create_app

    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    app = create_app(static_dir=static_dir)
    # A windowed PyInstaller app has no sys.stderr. Uvicorn's default formatter
    # probes stderr.isatty(), so desktop mode uses the file logger configured above.
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_config=None,
        access_log=False,
    )
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None
    thread = threading.Thread(target=server.run, name="decision-shelf-server", daemon=True)
    thread.start()
    try:
        _wait_until_ready(f"{url}/api/config")
        try:
            import webview
        except ImportError:
            webbrowser.open(url)
            thread.join()
            return

        window = webview.create_window(
            "Decision Shelf",
            url,
            width=1280,
            height=820,
            min_size=(960, 640),
            background_color="#f4efe6",
        )
        smoke_close_seconds = os.getenv("DECISION_SHELF_SMOKE_CLOSE_SECONDS", "").strip()
        close_timer: threading.Timer | None = None
        if smoke_close_seconds:
            close_timer = threading.Timer(float(smoke_close_seconds), window.destroy)
            close_timer.daemon = True
            close_timer.start()
        try:
            webview.start()
        except Exception as exc:
            if sys.platform == "win32":
                raise RuntimeError(
                    "无法创建桌面窗口。请安装或修复 Microsoft Edge WebView2 Runtime。"
                ) from exc
            raise
        finally:
            if close_timer:
                close_timer.cancel()
    finally:
        server.should_exit = True
        thread.join(timeout=3)


def main() -> None:
    try:
        _run()
    except Exception as exc:
        logging.exception("Desktop startup failed")
        _show_error(str(exc))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
