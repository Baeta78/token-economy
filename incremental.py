"""Reads only what is new in files and SQLite tables that other tools keep appending to.

The collection runs every minute. Reading whole logs and databases each time (RTK's
history, Context Mode's events, Ollama's logs) meant hundreds of MB of disk per
collection. Here each source keeps, in memory, what was already read and where it
stopped; the next call reads only the rest.

  lines(key, path, parse)            text file, one record per line (logs, jsonl)
  rows(key, db, table, cols, ...)    SQLite table that only grows (rows get new rowids)

Both return the full list of parsed records (old + new). Treat it as read-only: it is
the cached list itself.
"""
from __future__ import annotations

import os
import sqlite3
import threading

_state: dict[str, dict] = {}
_lock = threading.Lock()
_HEAD = 256  # bytes compared to tell that a log was rotated or recreated


def _sig(path: str) -> tuple:
    try:
        st = os.stat(path)
        return st.st_size, st.st_mtime_ns
    except OSError:
        return None, None


def lines(key: str, path: str, parse) -> list:
    """Records of a text file that only grows. `parse(line: str)` returns a record or None.
    Starts over when the file shrank or its first bytes changed (rotated or recreated)."""
    with _lock:
        s = _state.get(key)
        size, mtime = _sig(path)
        if size is None:
            _state.pop(key, None)
            return []
        if s and s["size"] == size and s["mtime"] == mtime:
            return s["items"]
        try:
            with open(path, "rb") as f:
                head = f.read(_HEAD)
                if not s or size < s["offset"] or head[: len(s["head"])] != s["head"]:
                    s = {"offset": 0, "items": [], "head": head}
                f.seek(s["offset"])
                data = f.read(size - s["offset"])
        except OSError:
            return s["items"] if s else []
        cut = data.rfind(b"\n")  # only complete lines; the rest is read next time
        if cut >= 0:
            for raw in data[: cut + 1].decode("utf-8", errors="replace").splitlines():
                if raw:
                    item = parse(raw)
                    if item is not None:
                        s["items"].append(item)
            s["offset"] += cut + 1
        if len(s["head"]) < _HEAD:
            s["head"] = head
        s["size"], s["mtime"] = size, mtime
        _state[key] = s
        return s["items"]


def rows(key: str, db, table: str, cols: str, where: str = "", conv=None) -> list:
    """Rows of a SQLite table that only grows, read by rowid. `conv(row)` turns each row
    (the columns in `cols`) into a record, or None to skip it. Rows deleted from the start
    of the table (old history cleaned up) are dropped from the cache too; if the table was
    emptied or recreated, everything is read again."""
    db = str(db)
    with _lock:
        s = _state.get(key)
        sig = (_sig(db), _sig(db + "-wal"))
        if sig[0][0] is None:
            _state.pop(key, None)
            return []
        if s and s["sig"] == sig:
            return s["records"]
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        try:
            lo = c.execute(f"select min(rowid) from {table}").fetchone()[0]
            hi = c.execute(f"select max(rowid) from {table}").fetchone()[0]
            if not s or lo is None or hi < s["max"]:
                s = {"max": 0, "items": []}  # (rowid, record)
            elif lo > s["min"]:
                s["items"] = [x for x in s["items"] if x[0] >= lo]
            cond = f"rowid > ?{' and (' + where + ')' if where else ''}"
            for r in c.execute(f"select rowid, {cols} from {table} where {cond} order by rowid", (s["max"],)):
                item = conv(r[1:]) if conv else r[1:]
                if item is not None:
                    s["items"].append((r[0], item))
            s["min"] = lo if lo is not None else 0
            s["max"] = max(s["max"], hi or 0)
        finally:
            c.close()
        s["sig"] = sig
        s["records"] = [x[1] for x in s["items"]]
        _state[key] = s
        return s["records"]
