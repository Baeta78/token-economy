"""Installed and latest version of each token-saving tool found on this machine.

- Installed: runs the tool's own version command (`version_cmd` in savings_tools.json, e.g.
  `rtk --version`) on the program already found on PATH. Nothing is installed or changed.
- Latest: asks the package registry the tool is installed from (PyPI, npm, crates.io) or, when
  there is none, the project's latest GitHub release. Only the package name is sent.
Results are cached for 12 hours in .cache/tool_versions.json and refreshed in a background
thread, so a collection never waits on the network. Demo mode makes no calls.
"""
from __future__ import annotations

import json
import re
import subprocess
import threading
import time
import urllib.parse
import urllib.request

import runtime
import savings
import signals
from version import VERSION

CACHE = runtime.CACHE / "tool_versions.json"
EVERY_S = 12 * 3600
_VER = re.compile(r"\d+\.\d+(?:\.\d+)?")
_lock = threading.Lock()
_running = {"on": False}


def _get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": f"token-economy/{VERSION}",
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read())


def _vt(v: str) -> tuple:
    return tuple(int(x) for x in (v.split(".") + ["0", "0"])[:3])


def installed(tool: dict) -> str | None:
    cmd = tool.get("version_cmd") or []
    exe = signals.find_exe(cmd[:1]) if cmd else None
    if not exe:
        return None
    try:
        r = subprocess.run([exe, *cmd[1:]], capture_output=True, text=True, timeout=8,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None
    m = _VER.search((r.stdout or "") + " " + (r.stderr or ""))
    return m.group(0) if m else None


def latest(tool: dict) -> str | None:
    reg = tool.get("registry") or ""
    kind, _, name = reg.partition(":")
    q = urllib.parse.quote(name, safe="@/")
    try:
        if kind == "pypi":
            v = _get_json(f"https://pypi.org/pypi/{q}/json")["info"]["version"]
        elif kind == "npm":
            v = _get_json(f"https://registry.npmjs.org/{q}/latest")["version"]
        elif kind == "crates":
            v = _get_json(f"https://crates.io/api/v1/crates/{q}")["crate"]["max_stable_version"]
        elif tool.get("releases") and "github.com/" in (tool.get("url") or ""):
            repo = tool["url"].split("github.com/", 1)[1].strip("/")
            v = _get_json(f"https://api.github.com/repos/{repo}/releases/latest")["tag_name"]
        else:
            return None
    except Exception:  # noqa: BLE001  (offline, rate limit, package renamed: just no answer)
        return None
    m = _VER.search(v or "")
    return m.group(0) if m else None


def _read() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _refresh(tools: list[dict]):
    try:
        data = _read()
        for t in tools:
            data[t["id"]] = {"installed": installed(t), "latest": latest(t), "at": time.time()}
        CACHE.parent.mkdir(exist_ok=True)
        CACHE.write_text(json.dumps(data), encoding="utf-8")
    finally:
        _running["on"] = False


def status(detected: list[dict], catalog: list[dict]) -> dict[str, dict]:
    """{tool_id: {installed, latest, newer, update}} from the cache; refreshes it in the background."""
    if runtime.DEMO:  # fictional: one tool behind, one up to date, no command run and no network
        demo = {"rtk": ("1.1.0", "1.2.0"), "graphify": ("0.9.106", "0.9.106")}
        by_id = {c["id"]: c for c in catalog}
        return {i: {"installed": a, "latest": b, "newer": _vt(b) > _vt(a), "update": savings.for_os(by_id[i], "update"),
                    "path": r"C:\Users\dev\AppData\Local\Programs" + "\\" + i, "check": " ".join(by_id[i].get("version_cmd") or [])}
                for i, (a, b) in demo.items() if i in by_id and any(f["id"] == i for f in detected)}
    by_id = {c["id"]: c for c in catalog}
    tools = [by_id[f["id"]] for f in detected if f["id"] in by_id and by_id[f["id"]].get("version_cmd")]
    data = _read()
    stale = [t for t in tools if time.time() - (data.get(t["id"]) or {}).get("at", 0) > EVERY_S]
    with _lock:
        if stale and not _running["on"]:
            _running["on"] = True
            threading.Thread(target=_refresh, args=(stale,), daemon=True).start()
    out = {}
    for t in tools:
        d = data.get(t["id"]) or {}
        inst, last = d.get("installed"), d.get("latest")
        out[t["id"]] = {"installed": inst, "latest": last,
                        "newer": bool(inst and last and _vt(last) > _vt(inst)),
                        "update": savings.for_os(t, "update"),
                        "path": signals.find_exe((t.get("version_cmd") or [])[:1]) or "", "check": " ".join(t.get("version_cmd") or [])}
    return out
