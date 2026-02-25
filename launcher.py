"""Executable launcher for the Streamlit SHA compliance app."""

from __future__ import annotations

import os
import sys

from streamlit.web import cli as stcli


if __name__ == "__main__":
    app_path = os.path.join(os.path.dirname(__file__), "app.py")
    sys.argv = [
        "streamlit",
        "run",
        app_path,
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
    ]
    raise SystemExit(stcli.main())
