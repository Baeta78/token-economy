"""Checks for and installs new versions from the official GitHub repository.

- Check: asks GitHub for the latest release (at most every 6 hours, no data about you is sent).
- Install, git clone: fast-forwards to the release tag (refuses if you changed tracked files).
- Install, ZIP download: downloads that release's source ZIP from GitHub and copies it over
  the app folder. `.cache/` (your settings and history) is never touched.
- Automatic (on unless the panel's setting turns it off): a background thread checks every
  6 hours and installs a new release by itself. Only published releases count, never plain
  commits on main.
After installing, Token Economy restarts itself (tray icon or server.py) to run the new version.
"""
from __future__ import annotations

import io
import json
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import runtime
from version import VERSION

REPO = "Baeta78/token-economy"
BASE = Path(__file__).resolve().parent
CHECK_EVERY_S = 6 * 3600
AUTO_FIRST_S = 120  # first automatic check a little after startup, not while the first collection runs
KEEP = {".cache", ".cache-demo", ".git", "graphify-out", "__pycache__", "prices.json"}  # never overwritten

_lock = threading.Lock()
_apply_lock = threading.Lock()  # the button and the automatic check never install at the same time
_last = {"at": 0.0, "data": None}
_restart = None  # set by whoever owns the process (tray.py or server.py main)


def _log(msg: str) -> None:
    try:
        runtime.CACHE.mkdir(parents=True, exist_ok=True)
        with open(runtime.CACHE / "update.log", "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except OSError:
        pass


def auto_enabled() -> bool:
    try:
        cfg = json.loads((runtime.CACHE / "config.json").read_text(encoding="utf-8"))
        return cfg.get("auto_update") is not False
    except Exception:  # noqa: BLE001
        return True  # no settings yet: on by default


def _get(url: str, timeout: int = 15) -> bytes:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": f"token-economy/{VERSION}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _vt(v: str) -> tuple:
    out = []
    for part in (v or "").lstrip("vV").split("."):
        num = "".join(ch for ch in part if ch.isdigit())
        out.append(int(num) if num else 0)
    return tuple(out)


def method() -> str:
    return "git" if (BASE / ".git").exists() and shutil.which("git") else "zip"


def check(force: bool = False) -> dict:
    with _lock:
        if not force and _last["data"] and time.time() - _last["at"] < CHECK_EVERY_S:
            return _last["data"]
        data = {"current": VERSION, "latest": None, "newer": False, "method": method(), "demo": runtime.DEMO}
        try:
            rel = json.loads(_get(f"https://api.github.com/repos/{REPO}/releases/latest"))
            tag = rel.get("tag_name") or ""
            data.update(latest=tag.lstrip("vV"), tag=tag, url=rel.get("html_url"),
                        notes=(rel.get("body") or "")[:4000], published=rel.get("published_at"),
                        newer=_vt(tag) > _vt(VERSION))
        except urllib.error.HTTPError as e:
            if e.code != 404:  # 404 = no release published yet
                data["error"] = f"GitHub HTTP {e.code}"
        except Exception as e:  # noqa: BLE001
            data["error"] = type(e).__name__
        _last.update(at=time.time(), data=data)
        return data


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(BASE), *args], capture_output=True, text=True, timeout=120)


def _apply_git(tag: str) -> None:
    if _git("status", "--porcelain", "--untracked-files=no").stdout.strip():
        raise RuntimeError("local_changes")
    r = _git("fetch", "--tags", "origin")
    if r.returncode:
        raise RuntimeError("git fetch: " + (r.stderr or r.stdout)[-300:])
    r = _git("merge", "--ff-only", f"refs/tags/{tag}")
    if r.returncode:
        raise RuntimeError("git merge: " + (r.stderr or r.stdout)[-300:])


def _apply_zip(tag: str) -> None:
    raw = _get(f"https://api.github.com/repos/{REPO}/zipball/{tag}", timeout=60)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        if not names:
            raise RuntimeError("empty download")
        root = names[0].split("/", 1)[0] + "/"  # GitHub puts everything in one top folder
        base = BASE.resolve()
        for n in names:
            if not n.startswith(root):
                continue
            rel = n[len(root):]
            if not rel or rel.split("/", 1)[0] in KEEP:
                continue
            dest = (BASE / rel).resolve()
            if base not in dest.parents:  # never write outside the app folder
                raise RuntimeError("unsafe path in download: " + rel)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(z.read(n))


def apply() -> dict:
    if runtime.DEMO:
        raise RuntimeError("demo")
    with _apply_lock:
        info = check(force=True)
        if not info.get("newer"):
            return {"ok": True, "updated": False, "current": VERSION}
        tag = info["tag"]
        if info["method"] == "git":
            _apply_git(tag)
        else:
            _apply_zip(tag)
        _log(f"installed {tag} over {VERSION} ({info['method']})")
        with _lock:  # the files are new now; don't offer the same version again before the restart
            _last["data"] = {**info, "newer": False, "installed": info["latest"]}
        return {"ok": True, "updated": True, "version": info["latest"], "restart": _restart is not None}


def restart_soon(delay: float = 1.5) -> bool:
    """Restarts Token Economy so the new files run. False if nobody registered a way to restart."""
    if _restart is None:
        return False
    threading.Timer(delay, _restart).start()
    return True


def _auto_loop() -> None:
    time.sleep(AUTO_FIRST_S)
    while True:
        if auto_enabled():
            try:
                if apply().get("updated") and restart_soon(0):
                    return
            except Exception as e:  # noqa: BLE001  (offline, local changes…): try again next time
                _log(f"automatic update skipped: {e}")
        time.sleep(CHECK_EVERY_S)


def start_auto(restart) -> None:
    """Registers how to restart the app and starts the automatic check (not in demo mode)."""
    global _restart
    _restart = restart
    if not runtime.DEMO:
        threading.Thread(target=_auto_loop, daemon=True, name="auto-update").start()
