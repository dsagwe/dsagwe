from __future__ import annotations

import socket
import threading
import time
import webbrowser

import uvicorn

from backend.main import app


def _free_port(default: int = 8765) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", default))
            return default
        except OSError:
            s.bind(("127.0.0.1", 0))
            return int(s.getsockname()[1])


def _open_browser(url: str) -> None:
    time.sleep(1.5)
    webbrowser.open(url)


def main() -> None:
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    t = threading.Thread(target=_open_browser, args=(url,), daemon=True)
    t.start()

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
