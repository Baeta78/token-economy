#!/bin/sh
# Token Economy on macOS / Linux.
#   sh start.sh            dashboard in the browser (same options as server.py: --port, --demo…)
#   sh start.sh --tray     menu bar / tray icon, in the background
cd "$(dirname "$0")" || exit 1
# a virtual environment next to the code (python3 -m venv .venv) wins over the system Python
if [ -x .venv/bin/python ]; then
    PY=.venv/bin/python
else
    PY=$(command -v python3 || command -v python)
fi
if [ -z "$PY" ]; then
    echo "Python 3.10+ not found. Install it from https://www.python.org/downloads/" >&2
    exit 1
fi
# macOS ships Python 3.9, which is too old
if ! "$PY" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
    echo "Token Economy needs Python 3.10+, but $PY is $("$PY" -V 2>&1)." >&2
    echo "On macOS: brew install python (or python.org), then recreate .venv with it." >&2
    exit 1
fi
if [ "$1" = "--tray" ]; then
    nohup "$PY" tray.py >/dev/null 2>&1 &
    echo "Token Economy is running in the menu bar / tray."
else
    exec "$PY" server.py "$@"
fi
