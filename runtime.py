"""Where Token Economy keeps its local data, and whether it runs in demo mode.

Every module takes the data folder from here, so one setting moves all of it:
  TOKEN_ECONOMY_CACHE   folder for the local data (default: .cache next to the code)
  TOKEN_ECONOMY_DEMO=1  demo mode, set by `python server.py --demo` (see demo.py): fictional
                        data, no calls to the official usage endpoints and no AI runs.
Both are read once, at import time; demo.py sets them before the other modules load.

It also says which OS it runs on and where that OS keeps per-user app data, so the
other modules don't hard-code Windows folders.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
CACHE = Path(os.environ.get("TOKEN_ECONOMY_CACHE") or BASE / ".cache")
DEMO = os.environ.get("TOKEN_ECONOMY_DEMO") == "1"
# `python server.py --agent`: collects for another machine's panel (see remote.py); set by server.py
AGENT = False

WIN = sys.platform == "win32"
MAC = sys.platform == "darwin"


def local_data() -> Path:
    """Per-user app data that stays on this machine: %LOCALAPPDATA% on Windows,
    ~/Library/Application Support on macOS, $XDG_DATA_HOME (~/.local/share) on Linux.
    The same folders Rust's `dirs::data_local_dir()` uses, so tools like RTK land there.
    LOCALAPPDATA wins when set (demo mode sets it on every OS)."""
    if os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"])
    home = Path.home()
    if WIN:
        return home / "AppData" / "Local"
    if MAC:
        return home / "Library" / "Application Support"
    return Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share")


def roaming_data() -> Path:
    """Per-user app settings: %APPDATA% on Windows, ~/Library/Application Support on
    macOS, $XDG_CONFIG_HOME (~/.config) on Linux. APPDATA wins when set."""
    if os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"])
    home = Path.home()
    if WIN:
        return home / "AppData" / "Roaming"
    if MAC:
        return home / "Library" / "Application Support"
    return Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
