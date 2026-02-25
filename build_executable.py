"""Build a standalone executable using PyInstaller."""

from __future__ import annotations

import os
import subprocess
import sys


ADD_DATA_ARG = f"app.py{os.pathsep}."

COMMAND = [
    sys.executable,
    "-m",
    "PyInstaller",
    "--noconfirm",
    "--clean",
    "--name",
    "sha_compliance_app",
    "--add-data",
    ADD_DATA_ARG,
    "launcher.py",
]


def main() -> int:
    print("Running:", " ".join(COMMAND))
    return subprocess.call(COMMAND)


if __name__ == "__main__":
    raise SystemExit(main())
