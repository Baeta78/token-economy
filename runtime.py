"""Where Token Economy keeps its local data, and whether it runs in demo mode.

Every module takes the data folder from here, so one setting moves all of it:
  TOKEN_ECONOMY_CACHE   folder for the local data (default: .cache next to the code)
  TOKEN_ECONOMY_DEMO=1  demo mode, set by `python server.py --demo` (see demo.py): fictional
                        data, no calls to the official usage endpoints and no AI runs.
Both are read once, at import time; demo.py sets them before the other modules load.
"""
from __future__ import annotations

import os
from pathlib import Path

BASE = Path(__file__).resolve().parent
CACHE = Path(os.environ.get("TOKEN_ECONOMY_CACHE") or BASE / ".cache")
DEMO = os.environ.get("TOKEN_ECONOMY_DEMO") == "1"
