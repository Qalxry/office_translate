"""GUI 启动器：启动 FastAPI 服务，用 pywebview 或默认浏览器打开界面。"""

from __future__ import annotations

import ipaddress
import logging
import os
import socket
import threading
import time
import webbrowser
from typing import Optional

import uvicorn

from .server import create_app

WEB_DIR = os.path.join(os.path.dirname(__file__), "web")
LOGGER = logging.getLogger(__name__)
_LOCALHOST_NAMES = {"localhost"}


def _validate_localhost(host: str) -> str:
    """Return a safe loopback bind host or reject a network-facing host.

    The GUI is a local desktop application.  Keeping this check in the
    launcher makes an accidental ``--host 0.0.0.0`` style exposure impossible
    even when the launcher is called programmatically rather than through the
    eventual desktop shell.
    """
    if not isinstance(host, str) or not host.strip():
        raise ValueError("GUI launcher host must be a localhost address")
    candidate = host.strip().lower().rstrip(".")
    if candidate in _LOCALHOST_NAMES:
        return candidate
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError as exc:
        raise ValueError(
            f"GUI launcher refuses non-localhost host {host!r}; use 127.0.0.1"
        ) from exc
    if not address.is_loopback:
        raise ValueError(
            f"GUI launcher refuses non-localhost host {host!r}; use 127.0.0.1"
        )
    return candidate


def _local_url(host: str, port: int) -> str:
    """Build a browser URL, including brackets for an IPv6 loopback host."""
    display_host = f"[{host}]" if ":" in host else host
    return f"http://{display_host}:{port}"


def _find_free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(host: str, port: int, timeout: float = 10.0) -> bool:
    """Wait briefly for uvicorn to accept connections before opening a UI."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.25):
                return True
        except OSError:
            time.sleep(0.05)
    return False


def _open_browser(url: str, host: str = "127.0.0.1", port: Optional[int] = None) -> None:
    # 先确认服务器就绪，避免固定延迟导致浏览器打开空白页
    def _open():
        if port is not None and not _wait_for_server(host, port):
            LOGGER.warning("Local GUI server did not become ready before browser launch: %s", url)
        try:
            opened = webbrowser.open(url)
            if not opened:
                LOGGER.warning("Browser refused to open local GUI URL: %s", url)
        except Exception:  # noqa: BLE001 - browser integration is best effort
            LOGGER.exception("Failed to open local GUI URL: %s", url)

    threading.Thread(target=_open, daemon=True).start()


def _open_webview(url: str) -> None:
    import webview  # 可选依赖，未装时回退浏览器

    webview.create_window("office_translate", url, width=1200, height=800)
    webview.start()


def launch(
    config_path: str = "config.yaml",
    glossary_path: str = "data/glossary.json",
    host: str = "127.0.0.1",
    port: Optional[int] = None,
    use_webview: bool = True,
) -> None:
    """启动 GUI。

    Args:
        config_path: 配置文件路径。
        glossary_path: 术语库路径。
        host/port: 服务监听地址；port 为 None 时自动选空闲端口。
        use_webview: 优先用 pywebview 原生窗口；不可用则回退浏览器。
    """
    host = _validate_localhost(host)
    port = port or _find_free_port()
    url = _local_url(host, port)

    LOGGER.info(
        "Starting office_translate GUI on loopback host=%s port=%s webview=%s",
        host,
        port,
        use_webview,
    )

    app = create_app(config_path=config_path, glossary_path=glossary_path)

    try:
        import webview  # noqa: F401

        webview_ok = True
    except ImportError:
        webview_ok = False

    if use_webview and webview_ok:
        # pywebview 需要服务在后台线程跑
        server_thread = threading.Thread(
            target=uvicorn.run,
            kwargs={"app": app, "host": host, "port": port, "log_level": "warning"},
            daemon=True,
        )
        server_thread.start()
        if not _wait_for_server(host, port):
            LOGGER.warning("Local GUI server did not become ready before WebView launch: %s", url)
        LOGGER.info("Opening GUI in local WebView: %s", url)
        _open_webview(url)
    else:
        if use_webview and not webview_ok:
            LOGGER.info("pywebview is unavailable; falling back to browser")
        _open_browser(url, host, port)
        uvicorn.run(app, host=host, port=port, log_level="warning")


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="office_translate GUI")
    p.add_argument("-c", "--config", default="config.yaml", help="配置文件路径")
    p.add_argument("-g", "--glossary", default="data/glossary.json", help="术语库路径")
    p.add_argument("--port", type=int, default=None, help="端口（默认自动选）")
    p.add_argument("--no-webview", action="store_true", help="强制用浏览器而非 pywebview")
    args = p.parse_args()
    launch(
        config_path=args.config,
        glossary_path=args.glossary,
        port=args.port,
        use_webview=not args.no_webview,
    )


if __name__ == "__main__":
    main()
