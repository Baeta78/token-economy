"""Live feed for the animated office: what each agent is doing right now.

The main collector reads every log once a minute and adds things up by hour. The office
needs the opposite: only the sessions active in the last minutes, read every couple of
seconds, as a stream of small events (a tool call, a prompt, tokens, the end of a turn).

It keeps its own read position per log file, starting near the end of a file the first
time it sees it, so a poll only reads the lines written since the last one. Nothing is
stored on disk. Commands and file names stay on this machine like everything else.

    feed(after)  -> {"seq", "now", "sessions": [...], "events": [events with seq > after]}
"""
from __future__ import annotations

import glob
import json
import os
import re
import sqlite3
import threading
import time
from collections import deque
from pathlib import Path

import collector
import prices
import savings

ACTIVE_S = 20 * 60       # a session counts as present while its log changed this recently
LIST_EVERY_S = 15        # how often the list of log files is refreshed
TAIL_BYTES = 128 * 1024  # how much of a file is read the first time it is seen
MAX_EVENTS = 600
LABEL_MAX = 90

_lock = threading.Lock()
_files: dict[str, dict] = {}     # path -> {"offset", "agent", "session", "cwd", "sub"}
_listed_at = 0.0
_listed: list[tuple[str, str]] = []
_sessions: dict[str, dict] = {}
_events: deque = deque(maxlen=MAX_EVENTS)
_seq = 0
_rtk_after = None

_WAIT = re.compile(r"\b(sleep|wait|poll)\b|Start-Sleep|Monitor", re.I)

_KIND = {
    "Bash": "terminal", "PowerShell": "terminal", "shell": "terminal", "exec_command": "terminal",
    "local_shell_call": "terminal", "Read": "read", "NotebookRead": "read", "view_image": "read",
    "Edit": "edit", "Write": "edit", "MultiEdit": "edit", "NotebookEdit": "edit", "apply_patch": "edit",
    "Grep": "search", "Glob": "search", "ToolSearch": "search",
    "WebFetch": "web", "WebSearch": "web", "web_search": "web",
    "Agent": "bot", "Task": "bot", "TodoWrite": "read", "update_plan": "read",
}


def _catalog() -> list[dict]:
    try:
        return savings.catalog()
    except Exception:  # noqa: BLE001
        return []


def _saving_for(name: str, command: str) -> tuple[str, str] | None:
    """(tool_id, display name) of the token-saving tool behind a call, if any."""
    heads = set()
    for seg in re.split(r"&&|\|\||;|\|", command or ""):
        w = seg.strip().split()
        if w:
            heads.add(w[0].strip("&'\"").lower().rsplit("/", 1)[-1].rsplit("\\", 1)[-1].removesuffix(".exe"))
    for f in _catalog():
        d = f.get("detection") or {}
        if savings._belongs_to_tool(name, d):
            return f["id"], f["name"]
        if heads & {x.lower() for x in d.get("exes") or []}:
            return f["id"], f["name"]
    return None


def _category(tool_id: str) -> str:
    f = next((x for x in _catalog() if x["id"] == tool_id), None)
    return (f or {}).get("category") or "mcp"


def _short(s: str) -> str:
    s = " ".join((s or "").split())
    return s if len(s) <= LABEL_MAX else s[: LABEL_MAX - 1] + "…"


def _label(name: str, inp: dict) -> str:
    for k in ("command", "cmd", "file_path", "path", "pattern", "query", "url", "description", "skill",
              "intent", "prompt", "code"):
        v = inp.get(k)
        if isinstance(v, str) and v:
            if k in ("file_path", "path"):
                v = os.path.basename(v.rstrip("/\\")) or v
            return _short(v)
        if isinstance(v, list) and v and isinstance(v[0], str):
            return _short(" ".join(v))
    return ""


def _push(ev: dict) -> None:
    global _seq
    _seq += 1
    ev["seq"] = _seq
    _events.append(ev)
    s = _sessions.get(ev["session"])
    if s is not None:
        s["last"] = max(s["last"], ev["ts"])
        if ev["kind"] == "tokens":
            s["tokens"] += ev.get("total", 0)
            usd = _cost(s["model"], ev)
            if usd is not None:
                ev["usd"] = usd
                s["usd"] += usd
        elif ev["kind"] == "saved":
            s["saved"] += ev.get("saved", 0)
            pin = _input_price(s["model"])
            if pin is not None:
                ev["usd"] = ev.get("saved", 0) * pin / 1_000_000
                s["saved_usd"] += ev["usd"]


# what the tokens cost, at the price of the session's model (None when the model has no price)
def _cost(model: str, ev: dict) -> float | None:
    try:
        return collector.cost_usd(model, ev, None)
    except Exception:  # noqa: BLE001
        return None


def _input_price(model: str) -> float | None:
    # a saved token is one the model did not have to read: valued at its input price
    try:
        p = prices.price(model)[0]
        return p.get("input") if p else None
    except Exception:  # noqa: BLE001
        return None


def _session(sid: str, agent: str, cwd: str, ts: float, model: str = "") -> None:
    s = _sessions.get(sid)
    if s is None:
        s = _sessions[sid] = {"id": sid, "agent": agent, "cwd": cwd, "project": "", "model": model,
                              "start": ts, "last": ts, "tokens": 0, "usd": 0.0, "saved": 0, "saved_usd": 0.0}
    if cwd and not s["cwd"]:
        s["cwd"] = cwd
    if s["cwd"] and not s["project"]:
        s["project"] = collector.project_name(s["cwd"])
    if model:
        s["model"] = model


def _tool_event(base: dict, name: str, inp: dict) -> dict:
    cmd = ""
    if isinstance(inp, dict):
        cmd = inp.get("command") or inp.get("cmd") or ""
        if isinstance(cmd, list):
            cmd = " ".join(cmd)
    label = _label(name, inp if isinstance(inp, dict) else {})
    ev = dict(base, kind="tool", tool=name, label=label)
    if name.startswith("mcp__") or name.startswith("mcp:"):
        ev["icon"] = "plug"
    else:
        ev["icon"] = _KIND.get(name, "plug" if "__" in name else "terminal")
    if name.startswith("Skill"):
        ev["icon"] = "idea"
    if _WAIT.search(cmd or "") or name in ("Monitor", "ScheduleWakeup"):
        ev["icon"] = "wait"
    sv = _saving_for(name, cmd)
    if sv:
        ev["saving"], ev["saving_name"] = sv
        ev["category"] = _category(sv[0])
    return ev


# ----------------------------------------------------------------------------
# Claude Code
# ----------------------------------------------------------------------------

def _claude_line(d: dict, f: dict, sub: bool) -> None:
    ts = collector.parse_ts(d.get("timestamp"))
    sid = d.get("sessionId") or f.get("session") or ""
    if ts is None or not sid:
        return
    t = d.get("type")
    cwd = d.get("cwd") or ""
    m = d.get("message") or {}
    _session(sid, "claude", cwd, ts, "" if sub else (m.get("model") or "") if t == "assistant" else "")
    base = {"ts": ts, "session": sid, "agent": "claude", "sub": sub}
    if t == "user" and not sub and not d.get("isMeta") and not d.get("toolUseResult"):
        c = m.get("content")
        text = c if isinstance(c, str) else " ".join(
            b.get("text", "") for b in c or [] if isinstance(b, dict) and b.get("type") == "text")
        if text and not text.lstrip().startswith("<"):
            _push(dict(base, kind="prompt", label=_short(text)))
        return
    if t != "assistant":
        return
    if m.get("model") == "<synthetic>":
        return
    for b in m.get("content") or []:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "tool_use":
            _push(_tool_event(base, b.get("name") or "?", b.get("input") or {}))
        elif b.get("type") == "thinking":
            _push(dict(base, kind="think"))
        elif b.get("type") == "text" and (b.get("text") or "").strip():
            _push(dict(base, kind="say", label=_short(b["text"])))
    u = m.get("usage") or {}
    if u.get("output_tokens"):
        tot = {"input": int(u.get("input_tokens") or 0), "output": int(u.get("output_tokens") or 0),
               "cache_read": int(u.get("cache_read_input_tokens") or 0),
               "cache_write": int(u.get("cache_creation_input_tokens") or 0)}
        _push(dict(base, kind="tokens", total=sum(tot.values()), **tot))
    if m.get("stop_reason") == "end_turn" and not sub:
        _push(dict(base, kind="done"))


# ----------------------------------------------------------------------------
# Codex
# ----------------------------------------------------------------------------

def _codex_meta(path: str, f: dict) -> None:
    try:
        with open(path, "rb") as fh:
            first = json.loads(fh.readline() or b"{}")
    except Exception:  # noqa: BLE001
        return
    p = first.get("payload") or {}
    if first.get("type") == "session_meta":
        f["session"] = p.get("id") or p.get("session_id") or ""
        f["cwd"] = p.get("cwd") or ""


def _codex_line(d: dict, f: dict) -> None:
    ts = collector.parse_ts(d.get("timestamp"))
    sid = f.get("session") or ""
    if ts is None or not sid:
        return
    t, p = d.get("type"), d.get("payload") or {}
    if t == "turn_context":
        f["model"] = p.get("model") or f.get("model", "")
        f["cwd"] = p.get("cwd") or f.get("cwd", "")
    _session(sid, "codex", f.get("cwd", ""), ts, f.get("model", ""))
    base = {"ts": ts, "session": sid, "agent": "codex", "sub": False}
    if t == "response_item" and p.get("type") in ("function_call", "custom_tool_call", "local_shell_call"):
        name = p.get("name") or p.get("type")
        raw = p.get("arguments") or p.get("input") or ""
        try:
            inp = json.loads(raw) if isinstance(raw, str) and raw.startswith("{") else {"command": raw}
        except Exception:  # noqa: BLE001
            inp = {"command": raw}
        if p.get("action"):
            inp = {"command": " ".join((p["action"] or {}).get("command") or [])}
        _push(_tool_event(base, name, inp if isinstance(inp, dict) else {}))
    elif t == "event_msg":
        k = p.get("type")
        if k == "user_message" and p.get("message"):
            _push(dict(base, kind="prompt", label=_short(p["message"])))
        elif k == "agent_reasoning":
            _push(dict(base, kind="think"))
        elif k == "agent_message" and p.get("message"):
            _push(dict(base, kind="say", label=_short(p["message"])))
        elif k == "task_complete":
            _push(dict(base, kind="done"))
        elif k == "token_count":
            last = (p.get("info") or {}).get("last_token_usage") or {}
            if last:
                cached = int(last.get("cached_input_tokens") or 0)
                tot = {"input": max(int(last.get("input_tokens") or 0) - cached, 0),
                       "output": int(last.get("output_tokens") or 0), "cache_read": cached, "cache_write": 0}
                if any(tot.values()):
                    _push(dict(base, kind="tokens", total=sum(tot.values()), **tot))


# ----------------------------------------------------------------------------
# RTK: its own log says how much each command saved
# ----------------------------------------------------------------------------

def _rtk(now: float) -> None:
    global _rtk_after
    db = collector.PATHS.get("rtk")
    if not db or not Path(db).exists():
        return
    if _rtk_after is None:
        _rtk_after = now - 120
    try:
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=1)
        # as raw bytes: RTK may write the folder in the Windows code page instead of UTF-8
        rows = c.execute("select timestamp, cast(original_cmd as blob), saved_tokens, cast(project_path as blob) "
                         "from commands order by id desc limit 50").fetchall()
        c.close()
    except Exception:  # noqa: BLE001
        return
    newest = _rtk_after
    for ts_raw, cmd, saved, proj in reversed(rows):
        ts = collector.parse_ts(ts_raw)
        if ts is None or ts <= _rtk_after:
            continue
        newest = max(newest, ts)
        cmd, proj = _text(cmd), _text(proj)
        sid = _session_for_folder(proj, ts)
        if sid:
            _push({"ts": ts, "session": sid, "agent": _sessions[sid]["agent"], "sub": False, "kind": "saved",
                   "saving": "rtk", "saving_name": "RTK", "category": "command_output",
                   "saved": int(saved or 0), "label": _short(cmd or "")})
    _rtk_after = newest


def _text(raw) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def _folder_key(folder: str) -> str:
    f = folder or ""
    # RTK keeps Windows' long-path prefix (\\?\D:\... or \\?\UNC\server\...)
    if f.startswith("\\\\?\\UNC\\"):
        f = "\\\\" + f[8:]
    elif f.startswith("\\\\?\\"):
        f = f[4:]
    return os.path.normcase(os.path.normpath(f)) if f else ""


def _session_for_folder(folder: str, ts: float) -> str | None:
    """The session that ran a command in this folder: same folder first, else one working in a
    parent or child folder of it. The closest in time wins."""
    key = _folder_key(folder)
    if not key:
        return None
    exact, near = None, None
    for s in _sessions.values():
        cwd = _folder_key(s["cwd"])
        if not cwd:
            continue
        closer = lambda b: b is None or abs(s["last"] - ts) < abs(b["last"] - ts)  # noqa: E731
        if cwd == key:
            if closer(exact):
                exact = s
        elif (key.startswith(cwd + os.sep) or cwd.startswith(key + os.sep)) and closer(near):
            near = s
    best = exact or near
    return best["id"] if best else None


# ----------------------------------------------------------------------------

def _list_files(now: float) -> list[tuple[str, str]]:
    global _listed_at, _listed
    if now - _listed_at < LIST_EVERY_S:
        return _listed
    out = []
    root = collector.PATHS["claude"]
    if root.exists():
        out += [("claude", p) for p in glob.glob(str(root / "**" / "*.jsonl"), recursive=True)]
    for k in ("codex",):
        if collector.PATHS[k].exists():
            out += [("codex", p) for p in glob.glob(str(collector.PATHS[k] / "**" / "rollout-*.jsonl"), recursive=True)]
    fresh = []
    for agent, p in out:
        try:
            if now - os.path.getmtime(p) < ACTIVE_S:
                fresh.append((agent, p))
        except OSError:
            pass
    _listed, _listed_at = fresh, now
    return fresh


def _read(agent: str, path: str) -> None:
    try:
        size = os.path.getsize(path)
    except OSError:
        return
    f = _files.get(path)
    if f is None:
        f = _files[path] = {"offset": max(0, size - TAIL_BYTES), "skip_partial": size > TAIL_BYTES,
                            "sub": "subagents" in path.replace("\\", "/").split("/")}
        if agent == "codex":
            _codex_meta(path, f)
    if size < f["offset"]:
        f["offset"] = 0
    if size == f["offset"]:
        return
    with open(path, "rb") as fh:
        fh.seek(f["offset"])
        data = fh.read(size - f["offset"])
    cut = data.rfind(b"\n")
    if cut < 0:
        return
    f["offset"] += cut + 1
    lines = data[: cut + 1].split(b"\n")
    if f.pop("skip_partial", False):
        lines = lines[1:]
    for raw in lines:
        if not raw:
            continue
        try:
            d = json.loads(raw)
        except Exception:  # noqa: BLE001
            continue
        if agent == "claude":
            _claude_line(d, f, f["sub"])
        else:
            _codex_line(d, f)


def poll() -> None:
    now = time.time()
    with _lock:
        for agent, path in _list_files(now):
            _read(agent, path)
        _rtk(now)
        for sid in [k for k, s in _sessions.items() if now - s["last"] > ACTIVE_S]:
            del _sessions[sid]


def feed(after: int = 0) -> dict:
    poll()
    now = time.time()
    with _lock:
        evs = [e for e in _events if e["seq"] > after and now - e["ts"] < ACTIVE_S]
        sessions = sorted(_sessions.values(), key=lambda s: s["start"])
        return {"seq": _seq, "now": now, "sessions": [dict(s) for s in sessions], "events": evs}
