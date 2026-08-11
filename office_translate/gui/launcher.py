"""GUI 启动器：启动 FastAPI 服务，用 pywebview 或默认浏览器打开界面。"""

from __future__ import annotations

import os
import socket
import threading
import time
import webbrowser
from typing import Optional

import uvicorn

from .server import create_app

WEB_DIR = os.path.join(os.path.dirname(__file__), "web")


def _find_free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _open_browser(url: str) -> None:
    # 稍等服务器就绪再开浏览器
    def _open():
        time.sleep(0.8)
        webbrowser.open(url)

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
    port = port or _find_free_port()
    url = f"http://{host}:{port}"

    app = create_app(config_path=config_path, glossary_path=glossary_path)

    use_webview = use_webview
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
        _open_webview(url)
    else:
        _open_browser(url)
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
