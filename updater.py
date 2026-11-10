"""Checks for and installs new versions from the official GitHub repository.

- Check: asks GitHub for the latest release (at most every 6 hours, no data about you is sent).
- Install, git clone: fast-forwards to the release tag (refuses if you changed tracked files).
- Install, ZIP download: downloads that release's source ZIP from GitHub and copies it over
  the app folder. `.cache/` (your settings and history) is never touched.
The new version runs after Token Economy is restarted.
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
KEEP = {".cache", ".cache-demo", ".git", "graphify-out", "__pycache__", "prices.json"}  # never overwritten

_lock = threading.Lock()
_last = {"at": 0.0, "data": None}


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
    info = check(force=True)
    if not info.get("newer"):
        return {"ok": True, "updated": False, "current": VERSION}
    tag = info["tag"]
    if info["method"] == "git":
        _apply_git(tag)
    else:
        _apply_zip(tag)
    return {"ok": True, "updated": True, "version": info["latest"], "restart": True}
