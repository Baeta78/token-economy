#!/bin/sh
# Token Economy on macOS / Linux.
#   ./start.sh            dashboard in the browser (same options as server.py: --port, --demo…)
#   ./start.sh --tray     menu bar / tray icon, in the background
cd "$(dirname "$0")" || exit 1
PY=$(command -v python3 || command -v python)
if [ -z "$PY" ]; then
    echo "Python 3.10+ not found. Install it from https://www.python.org/downloads/" >&2
    exit 1
fi
if [ "$1" = "--tray" ]; then
    nohup "$PY" tray.py >/dev/null 2>&1 &
    echo "Token Economy is running in the menu bar / tray."
else
    exec "$PY" server.py "$@"
fi
