from __future__ import annotations

import socket
import threading
import time
import webbrowser

import uvicorn

from backend.main import app, setup_db


def _free_port(default: int = 8765) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", default))
            return default
        except OSError:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])


def _open_browser(url: str) -> None:
    time.sleep(1.5)
    webbrowser.open(url)


def main() -> None:
    setup_db()
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    threading.Thread(target=_open_browser, args=(url,), daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
