"""Collects the token usage and token savings data of the tools installed on this machine.

Sources read (read-only, nothing is changed):
  - Claude Code : ~/.claude/projects/**/*.jsonl          (usage per message)
  - Codex       : ~/.codex/sessions/**/rollout-*.jsonl   (usage per turn + 5h and weekly limits)
  - OpenCode    : ~/.local/share/opencode/opencode.db     (usage per message)
  - Ollama      : %LOCALAPPDATA%/Ollama/server*.log        (requests and duration; Ollama does not log tokens)
                  (~/.ollama/logs/server*.log on macOS and Linux)
  - RTK         : <local data>/rtk/history.db              (savings on command output; %LOCALAPPDATA% on
                  Windows, ~/Library/Application Support on macOS, ~/.local/share on Linux)
  - Headroom    : ~/.headroom/savings_events.jsonl and proxy_savings.json (savings in the proxy)
  - Graphify    : calls logged by the agents and projects with graphify-out/graph.json

The large files (Claude and Codex) are read incrementally: the cache in
.cache/ keeps how far each file has already been read.
"""
from __future__ import annotations

import bisect
import datetime as dt
import functools
import glob
import json
import os
import re
import sqlite3
import threading
import time
from collections import defaultdict

import incremental
import savings as savings_mod
import tool_versions
import limits as limits_mod
import signals as signals_mod
import prices as prices_mod
import runtime
from pathlib import Path

HOME = Path(os.environ.get("USERPROFILE") or Path.home())
LOCAL = runtime.local_data()
BASE = Path(__file__).resolve().parent
CACHE_DIR = runtime.CACHE
CACHE_FILE = CACHE_DIR / "file_index.json"
CACHE_VERSION = 5

PATHS = {
    "claude": HOME / ".claude" / "projects",
    "codex": HOME / ".codex" / "sessions",
    "codex_archived": HOME / ".codex" / "archived_sessions",
    "opencode": HOME / ".local" / "share" / "opencode" / "opencode.db",
    # Windows (and demo mode) keep the server logs in %LOCALAPPDATA%\Ollama; macOS and Linux in ~/.ollama/logs
    "ollama_logs": LOCAL / "Ollama" if runtime.WIN or os.environ.get("LOCALAPPDATA") else HOME / ".ollama" / "logs",
    "rtk": LOCAL / "rtk" / "history.db",
    "headroom": HOME / ".headroom",
}

AGENTS = {
    "claude": "Claude Code",
    "codex": "Codex",
    "opencode": "OpenCode",
    "ollama": "Ollama",
    "unknown": "Unidentified",
}


def load_prices() -> dict:
    return {}


# ----------------------------------------------------------------------------
# utilities
# ----------------------------------------------------------------------------

def parse_ts(value) -> float | None:
    """Converts ISO-8601, epoch in seconds or in milliseconds to epoch in seconds."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        return v / 1000.0 if v > 1e11 else v
    s = str(value).strip()
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        # Python only accepts up to 6 decimal places in the seconds
        m = re.match(r"^(.*\.\d{6})\d+(.*)$", s)
        if m:
            s = m.group(1) + m.group(2)
        d = dt.datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d.timestamp()
    except Exception:
        return None


_hour_memo: dict[int, str] = {}


def hour_key(ts: float) -> str:
    """Local hour in the YYYY-MM-DDTHH format."""
    # every time zone offset is a multiple of 15 minutes: the whole quarter hour has the same key
    q = int(ts // 900)
    h = _hour_memo.get(q)
    if h is None:
        if len(_hour_memo) > 200_000:
            _hour_memo.clear()
        h = _hour_memo[q] = dt.datetime.fromtimestamp(q * 900).strftime("%Y-%m-%dT%H")
    return h


def norm_cmd(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def norm_path(p: str) -> str:
    if not p:
        return ""
    p = p.replace("\\\\?\\", "").replace("\\\\?\\", "")
    if p.startswith("\\\\?\\"):
        p = p[4:]
    p = p.replace("/", "\\").rstrip("\\")
    return p


_ANONYMOUS = re.compile(r"^([0-9a-f]{8}-[0-9a-f-]{20,}|[0-9a-f]{12,}|agent-[0-9a-f]+|scratchpad|worktrees|\.claude)$", re.I)


@functools.lru_cache(maxsize=4096)
def project_name(p: str) -> str:
    """Project name: the git repository root, or the last folder with a readable name."""
    p = norm_path(p)
    if not p:
        return "~none"
    low = p.lower()
    if "\\temp\\claude\\" in low or "\\appdata\\local\\temp" in low:
        return "~temp"
    # subagent worktree: .../repo/.claude/worktrees/agent-xxx -> repo
    m = re.search(r"\\([^\\]+)\\\.claude\\worktrees\\", p, re.I)
    if m:
        return m.group(1)
    # walks up to the git root, if there is one
    cur = p
    for _ in range(8):
        if os.path.isdir(os.path.join(cur, ".git")) or os.path.isfile(os.path.join(cur, ".git")):
            return os.path.basename(cur) or cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    parts = [x for x in p.split("\\") if x]
    while len(parts) > 1 and _ANONYMOUS.match(parts[-1]):
        parts.pop()
    return parts[-1] if parts else p


_WAIT = re.compile(r"wait|sleep|poll|status", re.I)


def count_tool_hour(th: dict, ts: float, name: str) -> None:
    """Tool calls per hour: [total, waits]."""
    h = hour_key(ts)
    v = th.setdefault(h, [0, 0])
    v[0] += 1
    if _WAIT.search(name or ""):
        v[1] += 1


def model_family(model: str) -> str:
    m = (model or "").lower()
    if not m:
        return "unknown"
    return m


def model_price(model: str, prices: dict | None = None) -> dict | None:
    return prices_mod.price(model)[0]


def cost_usd(model: str, u: dict, prices: dict) -> float | None:
    p = model_price(model, prices)
    if not p or p.get("input") is None:
        return None
    inp = p.get("input", 0) or 0
    cr = p.get("cache_read")
    cw = p.get("cache_write")
    cw1h = min(u.get("cache_write_1h", 0), u.get("cache_write", 0))
    return (
        u.get("input", 0) * inp
        + u.get("cache_read", 0) * (cr if cr is not None else inp * 0.1)
        + (u.get("cache_write", 0) - cw1h) * (cw if cw is not None else inp * 1.25)
        + cw1h * inp * 2
        + u.get("output", 0) * (p.get("output", 0) or 0)
    ) / 1_000_000


# ----------------------------------------------------------------------------
# incremental per-file cache
# ----------------------------------------------------------------------------

_cache_lock = threading.Lock()
# The index stays in memory between collections: reading and rewriting the whole file
# every minute was tens of MB of disk per collection. It goes to disk when it changed, at
# most every SAVE_EVERY seconds, and on flush() (closing or restarting the app).
SAVE_EVERY = 600
_mem = {"cache": None, "dirty": False, "saved_at": 0.0}


def load_cache() -> dict:
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        if data.get("version") == CACHE_VERSION:
            return data
    except Exception:
        pass
    return {"version": CACHE_VERSION, "files": {}}


def save_cache(cache: dict) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    tmp = CACHE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, CACHE_FILE)


def _index() -> dict:
    if _mem["cache"] is None:
        _mem["cache"] = load_cache()
        _mem["saved_at"] = time.time()
    return _mem["cache"]


def _save_index(force: bool = False) -> None:
    if _mem["cache"] is None or not _mem["dirty"]:
        return
    if force or time.time() - _mem["saved_at"] >= SAVE_EVERY:
        save_cache(_mem["cache"])
        _mem["dirty"] = False
        _mem["saved_at"] = time.time()


def _index_mark(cache: dict) -> tuple[int, int]:
    """Changes whenever a log file was read further or a new one showed up."""
    files = cache["files"]
    return len(files), sum(e.get("offset", 0) for e in files.values())


def flush() -> None:
    """Writes the in-memory index to disk if it changed (called when the app closes)."""
    with _cache_lock:
        _save_index(force=True)


def iter_new_lines(path: str, entry: dict):
    """Reads only the lines added since the last offset. Starts over if the file shrank."""
    size = os.path.getsize(path)
    offset = entry.get("offset", 0)
    if size < offset:
        entry.clear()
        offset = 0
    if size == offset:
        return
    with open(path, "rb") as f:
        f.seek(offset)
        data = f.read(size - offset)
    # only processes up to the last complete line break
    cut = data.rfind(b"\n")
    if cut < 0:
        return
    entry["offset"] = offset + cut + 1
    for raw in data[: cut + 1].split(b"\n"):
        if raw:
            yield raw


# ----------------------------------------------------------------------------
# Claude Code
# ----------------------------------------------------------------------------

def scan_claude(cache: dict, progress) -> None:
    root = PATHS["claude"]
    if not root.exists():
        return
    files = glob.glob(str(root / "**" / "*.jsonl"), recursive=True)
    for i, path in enumerate(files):
        key = "claude:" + path
        entry = cache["files"].setdefault(key, {})
        try:
            st = os.stat(path)
        except OSError:
            continue
        if entry.get("offset") == st.st_size:
            continue
        progress(f"Claude Code: {i + 1}/{len(files)} files")
        msgs = entry.setdefault("msgs", {})
        tools = entry.setdefault("tools", {})
        th = entry.setdefault("tools_h", {})
        cmds = entry.setdefault("cmds", [])
        is_sub = "subagents" in path.replace("\\", "/").split("/")
        for raw in iter_new_lines(path, entry):
            if b'"assistant"' not in raw:
                continue
            try:
                d = json.loads(raw)
            except Exception:
                continue
            if d.get("type") != "assistant":
                continue
            m = d.get("message") or {}
            u = m.get("usage")
            ts = parse_ts(d.get("timestamp"))
            if not u or ts is None:
                continue
            mid = m.get("id") or d.get("requestId") or d.get("uuid")
            model = m.get("model") or "?"
            if model == "<synthetic>":
                continue
            cc = u.get("cache_creation") or {}
            rec = [
                round(ts, 3),
                model,
                int(u.get("input_tokens") or 0),
                int(u.get("output_tokens") or 0),
                int(u.get("cache_read_input_tokens") or 0),
                int(u.get("cache_creation_input_tokens") or 0),
                int(cc.get("ephemeral_1h_input_tokens") or 0),
                d.get("cwd") or "",
                d.get("sessionId") or "",
                1 if is_sub else 0,
            ]
            prev = msgs.get(mid)
            # the same message shows up on several lines; keep the one with the largest output
            if prev is None or rec[3] >= prev[3]:
                msgs[mid] = rec
            for block in m.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    name = block.get("name") or "?"
                    inp = block.get("input") or {}
                    if name == "Skill":
                        name = "Skill:" + str(inp.get("skill") or "?")
                    tools[name] = tools.get(name, 0) + 1
                    count_tool_hour(th, ts, name)
                    if block.get("name") in ("Bash", "PowerShell"):
                        c = inp.get("command")
                        if c:
                            shell = "ps" if block.get("name") == "PowerShell" else "sh"
                            cmds.append([round(ts, 3), norm_cmd(c)[:600], shell])
        entry["mtime"] = st.st_mtime


# ----------------------------------------------------------------------------
# Codex
# ----------------------------------------------------------------------------

_CODEX_CMD_RES = [
    re.compile(r'(?:cmd|command)\s*:\s*"((?:[^"\\]|\\.)*)"'),
    re.compile(r'"(?:cmd|command)"\s*:\s*"((?:[^"\\]|\\.)*)"'),
]


def _codex_cmds(text: str) -> list[str]:
    out = []
    for rx in _CODEX_CMD_RES:
        for m in rx.finditer(text or ""):
            try:
                out.append(json.loads('"' + m.group(1) + '"'))
            except Exception:
                out.append(m.group(1))
    return out


def scan_codex(cache: dict, progress) -> None:
    files = []
    for k in ("codex", "codex_archived"):
        if PATHS[k].exists():
            files += glob.glob(str(PATHS[k] / "**" / "rollout-*.jsonl"), recursive=True)
    for i, path in enumerate(files):
        key = "codex:" + path
        entry = cache["files"].setdefault(key, {})
        try:
            st = os.stat(path)
        except OSError:
            continue
        if entry.get("offset") == st.st_size:
            continue
        progress(f"Codex: {i + 1}/{len(files)} files")
        turns = entry.setdefault("turns", [])
        limits = entry.setdefault("limits", [])
        tools = entry.setdefault("tools", {})
        th = entry.setdefault("tools_h", {})
        cmds = entry.setdefault("cmds", [])
        meta = entry.setdefault("meta", {})
        for raw in iter_new_lines(path, entry):
            try:
                d = json.loads(raw)
            except Exception:
                continue
            t = d.get("type")
            p = d.get("payload") or {}
            ts = parse_ts(d.get("timestamp"))
            if t == "session_meta":
                meta["cwd"] = p.get("cwd") or meta.get("cwd", "")
                meta["session"] = p.get("id") or p.get("session_id") or meta.get("session", "")
                meta["source"] = p.get("source") or p.get("originator") or ""
                meta["provider"] = p.get("model_provider") or ""
            elif t == "turn_context":
                if p.get("model"):
                    meta["model"] = p.get("model")
                if p.get("cwd"):
                    meta["cwd"] = p.get("cwd")
                if p.get("effort") or p.get("reasoning_effort"):
                    meta["effort"] = p.get("effort") or p.get("reasoning_effort")
            elif t == "event_msg" and p.get("type") == "token_count":
                info = p.get("info") or {}
                tot = info.get("total_token_usage")
                if tot and ts is not None:
                    prev = entry.get("last_total") or {}
                    delta = {k: int(tot.get(k) or 0) - int(prev.get(k) or 0) for k in (
                        "input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens")}
                    if any(v > 0 for v in delta.values()) and all(v >= 0 for v in delta.values()):
                        cached = delta["cached_input_tokens"]
                        turns.append([
                            round(ts, 3),
                            meta.get("model") or "?",
                            max(delta["input_tokens"] - cached, 0),
                            delta["output_tokens"],
                            cached,
                            delta["reasoning_output_tokens"],
                        ])
                    entry["last_total"] = tot
                rl = p.get("rate_limits") or {}
                pri, sec = rl.get("primary") or {}, rl.get("secondary") or {}
                if ts is not None and (pri or sec):
                    limits.append([
                        round(ts, 3),
                        pri.get("used_percent"), pri.get("window_minutes"), pri.get("resets_at"),
                        sec.get("used_percent"), sec.get("window_minutes"), sec.get("resets_at"),
                        rl.get("plan_type") or "",
                    ])
            elif t == "response_item" and p.get("type") in ("function_call", "custom_tool_call", "local_shell_call"):
                name = p.get("name") or p.get("type")
                body = p.get("input") or p.get("arguments") or json.dumps(p.get("action") or {})
                # Codex wraps tools in "exec": count the real tool
                inner = re.findall(r"tools\.([A-Za-z0-9_]+)\(", body or "")
                for n in inner or [name]:
                    tools[n] = tools.get(n, 0) + 1
                    if ts is not None:
                        count_tool_hour(th, ts, n)
                if ts is not None:
                    for c in _codex_cmds(body):
                        cmds.append([round(ts, 3), norm_cmd(c)[:600]])
        entry["mtime"] = st.st_mtime


# ----------------------------------------------------------------------------
# OpenCode
# ----------------------------------------------------------------------------

def scan_opencode() -> dict:
    out = {"msgs": [], "tools": defaultdict(int), "tools_dir": defaultdict(lambda: defaultdict(int)), "cmds": [], "ok": False, "error": None}
    db = PATHS["opencode"]
    if not db.exists():
        out["error"] = "database not found"
        return out
    try:
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        dirs = {sid: d for sid, d in c.execute("select id, directory from session_v2")}
        for sid, created, data in c.execute(
            "select session_id, time_created, data from session_message where type='assistant'"
        ):
            try:
                j = json.loads(data)
            except Exception:
                continue
            tk = j.get("tokens") or {}
            mdl = j.get("model") or {}
            ts = parse_ts((j.get("time") or {}).get("created") or created)
            cache = tk.get("cache") or {}
            provider = mdl.get("providerID") or ""
            out["msgs"].append([
                ts, mdl.get("id") or "?", provider,
                int(tk.get("input") or 0), int(tk.get("output") or 0),
                int(cache.get("read") or 0), int(cache.get("write") or 0),
                int(tk.get("reasoning") or 0), float(j.get("cost") or 0),
                dirs.get(sid, ""), sid,
            ])
            for part in j.get("content") or []:
                if isinstance(part, dict) and part.get("type") == "tool":
                    name = part.get("name") or "?"
                    inp = (part.get("state") or {}).get("input") or {}
                    folder = dirs.get(sid, "")
                    names = [name]
                    if name == "execute":
                        inner = re.findall(r"tools\[\"([^\"]+)\"\]\.([A-Za-z0-9_]+)", inp.get("code") or "")
                        names = [f"mcp:{srv}.{fn}" for srv, fn in inner] or [name]
                    for n in names:
                        out["tools"][n] += 1
                        out["tools_dir"][folder][n] += 1
                    cmd = inp.get("command") or inp.get("cmd")
                    if cmd and ts:
                        out["cmds"].append([ts, norm_cmd(cmd)[:600], folder])
        out["ok"] = True
    except Exception as e:  # noqa: BLE001
        out["error"] = str(e)
    return out


# ----------------------------------------------------------------------------
# Ollama
# ----------------------------------------------------------------------------

_GIN = re.compile(
    r"\[GIN\] (\d{4}/\d{2}/\d{2}) - (\d{2}:\d{2}:\d{2}) \|\s*(\d+) \|\s*([\d.]+)(µs|us|ms|s|m\d+[\d.]*s|h\d+m\d+[\d.]*s|\S+)\s*\|\s*\S+\s*\|\s*(\w+)\s+\"([^\"]+)\""
)


def _dur_s(num: str, unit: str) -> float:
    try:
        v = float(num)
    except ValueError:
        return 0.0
    if unit in ("µs", "us"):
        return v / 1e6
    if unit == "ms":
        return v / 1e3
    if unit == "s":
        return v
    m = re.match(r"m([\d.]+)s", unit)  # "1m20s" becomes num=1 unit=m20s
    if m:
        return v * 60 + float(m.group(1))
    m = re.match(r"h(\d+)m([\d.]+)s", unit)
    if m:
        return v * 3600 + int(m.group(1)) * 60 + float(m.group(2))
    return 0.0


def scan_ollama() -> dict:
    out = {"reqs": [], "models": [], "ok": False, "error": None}
    logdir = PATHS["ollama_logs"]
    seen = set()

    def request(line: str):
        if "[GIN]" not in line or "POST" not in line:
            return None
        m = _GIN.search(line)
        if not m:
            return None
        endpoint = m.group(7)
        if not any(x in endpoint for x in ("/api/chat", "/api/generate", "/v1/chat", "/v1/messages", "/v1/responses", "/v1/completions", "/api/embed")):
            return None
        try:
            d = dt.datetime.strptime(m.group(1) + " " + m.group(2), "%Y/%m/%d %H:%M:%S")
        except ValueError:
            return None
        return (m.group(1), m.group(2), endpoint, m.group(4)), [d.timestamp(), endpoint, int(m.group(3)), _dur_s(m.group(4), m.group(5))]

    for path in sorted(glob.glob(str(logdir / "server*.log"))):
        try:
            # only the lines added since the last collection are read
            for key, req in incremental.lines("ollama:" + path, path, request):
                if key in seen:  # rotated logs repeat lines
                    continue
                seen.add(key)
                out["reqs"].append(req)
            out["ok"] = True
        except Exception as e:  # noqa: BLE001
            out["error"] = str(e)
    if runtime.DEMO:  # demo mode: never runs the real ollama
        import demo
        out["models"], out["loaded"] = demo.ollama_models()
        return out
    try:
        import subprocess

        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        res = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=8, creationflags=flags)
        for line in res.stdout.splitlines()[1:]:
            cols = line.split()
            if len(cols) >= 4:
                out["models"].append({"name": cols[0], "size": " ".join(cols[2:4])})
        res = subprocess.run(["ollama", "ps"], capture_output=True, text=True, timeout=8, creationflags=flags)
        out["loaded"] = [l.split()[0] for l in res.stdout.splitlines()[1:] if l.strip()]
    except Exception:
        pass
    return out


# ----------------------------------------------------------------------------
# RTK
# ----------------------------------------------------------------------------

def scan_rtk() -> dict:
    out = {"rows": [], "failures": [], "hooks": [], "ok": False, "error": None}
    db = PATHS["rtk"]
    if not db.exists():
        out["error"] = "history.db not found"
        return out
    def command(row):
        ts = parse_ts(row[0])
        return None if ts is None else [ts, row[1] or "", row[2] or "", row[3] or 0, row[4] or 0, row[5] or 0, row[6] or 0, row[7] or ""]

    # only the rows added since the last collection are read (the history only grows)
    try:
        out["rows"] = incremental.rows("rtk:commands", db, "commands",
                                       "timestamp, original_cmd, rtk_cmd, input_tokens, output_tokens, saved_tokens, exec_time_ms, project_path",
                                       conv=command)
        out["failures"] = incremental.rows("rtk:failures", db, "parse_failures",
                                           "timestamp, raw_command, error_message, fallback_succeeded",
                                           conv=lambda r: [parse_ts(r[0]), r[1] or "", r[2] or "", r[3]])
        out["hooks"] = incremental.rows("rtk:hooks", db, "hook_decisions",
                                        "timestamp, session_id, tool_use_id, raw_cmd, decision",
                                        conv=lambda r: [parse_ts(r[0]), r[1], r[2] or "", norm_cmd(r[3] or ""), r[4] or ""])
        out["ok"] = True
    except Exception as e:  # noqa: BLE001
        out["error"] = str(e)
    return out


def _agent_from_tool_id(tid: str) -> str:
    if tid.startswith("toolu_"):
        return "claude"
    if tid.startswith("call_"):
        return "codex"
    return "unknown"


_WORD = re.compile(r"[a-z0-9_\-]{2,}")
_STOP = {"users", "dev", "null", "head", "tail", "rtk", "cd", "echo", "true"}


def _words(s: str) -> list[str]:
    # not cached between collections on purpose: it cut ~2 s of CPU per collection but kept
    # ~150 MB of memory with the words of every command in the history
    seen, out = set(), []
    for w in _WORD.findall((s or "").lower()):
        if w not in seen and w not in _STOP:
            seen.add(w)
            out.append(w)
    return out


# commands RTK knows how to compress, and their PowerShell equivalents (which RTK does
# not filter, but which can be swapped for the Bash version)
RTK_FILTERS = {
    "cat", "head", "tail", "grep", "rg", "ls", "find", "tree", "wc", "diff", "git", "gh", "curl",
    "cargo", "npm", "pnpm", "npx", "yarn", "bun", "tsc", "jest", "vitest", "eslint", "prettier", "next",
    "pytest", "ruff", "mypy", "pip", "go", "golangci-lint", "docker", "kubectl", "aws", "terraform",
    "dotnet", "mvn", "gradle", "gradlew", "rspec", "rubocop", "rake", "php", "phpunit", "composer",
}
PS_EQUIVALENT = {"get-content", "gc", "type", "select-string", "sls", "get-childitem", "gci", "dir", "measure-object"}


def cmd_head(c: str) -> str:
    """First useful word of a command (skips cd, &&, ; and |)."""
    for seg in re.split(r"&&|\|\||;|\|", c or ""):
        w = seg.strip().split()
        if not w or w[0].lower() in ("cd", "set-location", "sl"):
            continue
        head = w[0].strip("&'\"").lower()
        if head == "rtk" and len(w) > 1:
            head = w[1].lower()
        return head.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].removesuffix(".exe")
    return ""


_attribution = {"cut": 0.0, "check": None, "map": {}}  # see the RTK part of collect()


class CmdIndex:
    """Index of the commands run by each agent, sorted by time.

    RTK stores the command already rewritten (quotes changed, ~ expanded, only the
    filtered part of a compound command), so the comparison is done by words: the
    RTK command matches the agent's when most of its words appear in the agent's
    command, close in time.
    """

    def __init__(self):
        self.items: list[tuple[float, str, set]] = []
        self.activity: dict[str, list[float]] = defaultdict(list)

    def add(self, ts: float, agent: str, cmd: str, source: str = "log"):
        if ts and cmd:
            self.items.append((ts, agent, set(_words(cmd)), source, cmd_head(cmd)))

    def active(self, ts: float, agent: str):
        self.activity[agent].append(ts)

    def check(self, cut: float) -> tuple:
        """How many commands and activity marks are older than `cut`: if it did not change,
        everything find() saw for a command older than `cut` is still the same."""
        return (bisect.bisect_left(self.times, cut),
                tuple(sorted((ag, bisect.bisect_left(v, cut)) for ag, v in self.activity.items())))

    def build(self):
        self.items.sort(key=lambda x: x[0])
        self.times = [x[0] for x in self.items]
        for v in self.activity.values():
            v.sort()

    def find(self, ts: float, cmd: str, before: float = 1800, after: float = 15) -> tuple[str, str, int | None]:
        target = _words(cmd)[:10]
        if target:
            lo = bisect.bisect_left(self.times, ts - before)
            hi = bisect.bisect_right(self.times, ts + after)
            best, best_score, best_i = None, 0.0, None
            n = len(target)
            for i in range(lo, hi):
                t, ag, ws, _s, _h = self.items[i]
                hit = len(ws.intersection(target)) / n  # target has no repeated words
                if hit < 0.6:
                    continue
                # ties are broken by closeness in time
                score = hit - abs(ts - t) / (before * 10)
                if score > best_score:
                    best, best_score, best_i = ag, score, i
            if best:
                return best, "command", best_i
        # no similar command: if only one agent was active in the previous 10 minutes, it is that one's
        actives = []
        for ag, tss in self.activity.items():
            i = bisect.bisect_right(tss, ts + 60)
            if i and tss[i - 1] >= ts - 600:
                actives.append(ag)
        if len(actives) == 1:
            return actives[0], "activity", None
        return "unknown", "none", None


# ----------------------------------------------------------------------------
# Headroom
# ----------------------------------------------------------------------------

def scan_headroom() -> dict:
    out = {"events": [], "lifetime": {}, "subscription": None, "ok": False, "error": None}
    root = PATHS["headroom"]
    ev = root / "savings_events.jsonl"

    def event(line: str):
        try:
            d = json.loads(line)
        except Exception:
            return None
        ts = parse_ts(d.get("ts"))
        if ts is None:
            return None
        return {
                "ts": ts,
                "before": int(d.get("before") or 0),
                "after": int(d.get("after") or 0),
                "saved": int(d.get("saved") or 0),  # saved already includes saved_tool_schema
                "usd": float(d.get("cost_usd") or 0),
                "model": d.get("model") or "?",
                "client": d.get("client") or "?",
                "provider": d.get("provider") or "?",
                "cache_read": int((d.get("cache") or {}).get("cr") or 0),
            }

    if ev.exists():
        out["events"] = incremental.lines("headroom:events", str(ev), event)  # only the new lines
        out["ok"] = True
    ps = root / "proxy_savings.json"
    if ps.exists():
        try:
            j = json.loads(ps.read_text(encoding="utf-8"))
            out["lifetime"] = j.get("lifetime") or {}
            for h in j.get("history") or []:
                ts = parse_ts(h.get("timestamp"))
                if ts is None:
                    continue
                # the aggregated history fills in old events that are not in the jsonl
                out.setdefault("history", []).append({
                    "ts": ts,
                    "saved": int(h.get("total_tokens_saved") or 0),
                    "model": h.get("model") or "?",
                    "client": h.get("agent") or "?",
                    "provider": h.get("provider") or "?",
                    "usd": float(h.get("compression_savings_usd") or 0),
                })
            out["ok"] = True
        except Exception as e:  # noqa: BLE001
            out["error"] = str(e)
    ss = root / "subscription_state.json"
    if ss.exists():
        try:
            j = json.loads(ss.read_text(encoding="utf-8"))
            out["subscription"] = j.get("latest")
        except Exception:
            pass
    return out


# ----------------------------------------------------------------------------
# building the snapshot
# ----------------------------------------------------------------------------

def _headroom_client(c: str) -> str:
    c = (c or "").lower()
    if "claude" in c:
        return "claude"
    if "codex" in c:
        return "codex"
    if "opencode" in c:
        return "opencode"
    if "ollama" in c:
        return "ollama"
    return "unknown"


REUSE_FOR = 300  # with nothing new, the previous snapshot is served for at most this long
_last = {"snap": None, "mark": None, "at": 0.0}


def _inputs_mark(cache: dict, oc: dict, ol: dict, rtk: dict, hr: dict) -> tuple:
    """Changes when any source read by the collection got something new."""
    return (_index_mark(cache), len(oc.get("msgs") or ()), len(oc.get("cmds") or ()),
            len(ol["reqs"]), tuple(ol.get("loaded") or ()), len(ol["models"]),
            len(rtk["rows"]), len(rtk["hooks"]), len(rtk["failures"]),
            len(hr["events"]), len(hr.get("history") or ()),
            json.dumps([hr.get("subscription"), hr.get("lifetime"), prices_mod.info()], sort_keys=True, default=str))


def collect(progress=lambda msg: None, force: bool = False) -> dict:
    """Builds the snapshot. Without `force`, when no source got anything new since the last
    one (less than REUSE_FOR ago), returns that same snapshot object without rebuilding it."""
    t0 = time.time()
    prices = load_prices()
    prices_mod.refresh_in_background()  # downloads the tables if they are older than 7 days
    with _cache_lock:
        cache = _index()
        before = _index_mark(cache)
        progress("Reading Claude Code…")
        scan_claude(cache, progress)
        progress("Reading Codex…")
        scan_codex(cache, progress)
        if _index_mark(cache) != before:
            _mem["dirty"] = True
        _save_index()
    progress("Reading OpenCode, Ollama, RTK and Headroom…")
    oc = scan_opencode()
    ol = scan_ollama()
    rtk = scan_rtk()
    hr = scan_headroom()
    mark = _inputs_mark(cache, oc, ol, rtk, hr)
    if not force and _last["snap"] is not None and _last["mark"] == mark and time.time() - _last["at"] < REUSE_FOR:
        return _last["snap"]

    # --- usage per hour: (hour, agent, model) -> metrics
    usage_hour: dict[tuple, dict] = defaultdict(lambda: defaultdict(float))
    usage_proj: dict[tuple, dict] = defaultdict(lambda: defaultdict(float))
    sessions: dict[tuple, dict] = {}
    tools: dict[str, dict] = {"claude": defaultdict(int), "codex": defaultdict(int), "opencode": defaultdict(int)}
    cmd_index = CmdIndex()
    projects_seen: set[str] = set()
    heads: dict[str, dict] = {"claude": defaultdict(int), "codex": defaultdict(int), "opencode": defaultdict(int)}
    # per project folder: tools called and programs run in the shell (for the token-saving
    # tools that do not record how much they save: where and how much they were used)
    tools_by_folder: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    heads_by_folder: dict[str, dict] = defaultdict(lambda: defaultdict(int))

    # activity per hour and agent: tool calls, wait calls and shell commands
    activity: dict[tuple, dict] = defaultdict(lambda: defaultdict(float))

    def count_cmd(ag, c, ts=None, folder=""):
        if ts:
            activity[(hour_key(ts), ag)]["shell"] += 1
        for seg in re.split(r"&&|\|\||;|\|", c):
            w = seg.strip().split()
            if not w or w[0].lower() == "cd":
                continue
            head = w[0].strip("&'\"").lower()[:30]
            heads[ag][head] += 1
            if folder:
                heads_by_folder[folder][re.sub(r"\.(exe|cmd|bat)$", "", head.replace("\\", "/").rsplit("/", 1)[-1])] += 1
            break

    def main_folder(cwds) -> str:
        """Folder where the session worked the most (a session almost always stays in one project)."""
        cnt = defaultdict(int)
        for c in cwds:
            if c:
                cnt[norm_path(c)] += 1
        return max(cnt, key=cnt.get) if cnt else ""

    def add(ag, ts, model, inp, out_, cr, cw, reasoning, cwd, sess, usd=None, sub=0, cw1h=0):
        h = hour_key(ts)
        cmd_index.active(ts, ag)
        u = {"input": inp, "output": out_, "cache_read": cr, "cache_write": cw, "cache_write_1h": cw1h}
        cost = usd if usd is not None else cost_usd(model, u, prices)
        k = (h, ag, model)
        r = usage_hour[k]
        r["msgs"] += 1
        r["input"] += inp
        r["output"] += out_
        r["cache_read"] += cr
        r["cache_write"] += cw
        r["reasoning"] += reasoning
        r["sub"] += sub
        if cost is not None:
            r["usd"] += cost
        else:
            r["unpriced"] += inp + out_ + cr + cw
        proj = project_name(cwd)
        if cwd:
            projects_seen.add(norm_path(cwd))
        pk = (h[:10], ag, proj)
        p = usage_proj[pk]
        p["msgs"] += 1
        p["tokens"] += inp + out_ + cr + cw
        p["input"] += inp
        p["output"] += out_
        if cost is not None:
            p["usd"] += cost
        if sess:
            sk = (ag, sess)
            s = sessions.get(sk)
            if s is None:
                s = sessions[sk] = {"agent": ag, "id": sess, "project": proj, "folder": norm_path(cwd), "start": ts, "end": ts,
                                    "msgs": 0, "tokens": 0, "input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "usd": 0.0, "models": {}}
            s["start"] = min(s["start"], ts)
            s["end"] = max(s["end"], ts)
            s["msgs"] += 1
            s["tokens"] += inp + out_ + cr + cw
            s["input"] += inp
            s["output"] += out_
            s["cache_read"] += cr
            s["cache_write"] += cw
            s["usd"] += cost or 0
            s["models"][model] = s["models"].get(model, 0) + 1

    # Claude Code
    for key, e in cache["files"].items():
        if not key.startswith("claude:"):
            continue
        for rec in (e.get("msgs") or {}).values():
            ts, model, inp, out_, cr, cw, cw1h, cwd, sess, sub = rec
            add("claude", ts, model, inp, out_, cr, cw, 0, cwd, sess, sub=sub, cw1h=cw1h)
        folder = main_folder(rec[7] for rec in (e.get("msgs") or {}).values())
        for n, c in (e.get("tools") or {}).items():
            tools["claude"][n] += c
            if folder:
                tools_by_folder[folder][n] += c
        for h, (tot, wait) in (e.get("tools_h") or {}).items():
            activity[(h, "claude")]["tools"] += tot
            activity[(h, "claude")]["waits"] += wait
        for ts, c, *shell in e.get("cmds") or []:
            cmd_index.add(ts, "claude", c, "log-ps" if shell and shell[0] == "ps" else "log")
            count_cmd("claude", c, ts, folder)

    # Codex
    codex_limits = []
    for key, e in cache["files"].items():
        if not key.startswith("codex:"):
            continue
        meta = e.get("meta") or {}
        for ts, model, inp, out_, cr, reasoning in e.get("turns") or []:
            add("codex", ts, model, inp, out_, cr, 0, reasoning, meta.get("cwd", ""), meta.get("session", ""))
        codex_limits += e.get("limits") or []
        folder = norm_path(meta.get("cwd", ""))
        for n, c in (e.get("tools") or {}).items():
            tools["codex"][n] += c
            if folder:
                tools_by_folder[folder][n] += c
        for h, (tot, wait) in (e.get("tools_h") or {}).items():
            activity[(h, "codex")]["tools"] += tot
            activity[(h, "codex")]["waits"] += wait
        for ts, c, *shell in e.get("cmds") or []:
            cmd_index.add(ts, "codex", c)
            count_cmd("codex", c, ts, folder)

    # OpenCode (and Ollama when used through OpenCode)
    for ts, model, provider, inp, out_, cr, cw, reasoning, cost, cwd, sess in oc["msgs"]:
        if ts is None:
            continue
        ag = "opencode"
        add(ag, ts, model if provider != "ollama" else f"ollama/{model}", inp, out_, cr, cw, reasoning, cwd, sess,
            usd=cost if cost else None)
    for n, c in oc["tools"].items():
        tools["opencode"][n] += c
    for folder, tl in oc.get("tools_dir", {}).items():
        if folder:
            for n, c in tl.items():
                tools_by_folder[norm_path(folder)][n] += c
    for ts, c, *rest in oc["cmds"]:
        cmd_index.add(ts, "opencode", c)
        count_cmd("opencode", c, ts, norm_path(rest[0]) if rest else "")

    # RTK hooks (Claude Code records session_id + tool_use_id)
    for ts, _sess, tid, raw, _dec in rtk["hooks"]:
        if ts:
            cmd_index.add(ts, _agent_from_tool_id(tid), raw, "hook")
    cmd_index.build()

    # --- RTK: assigns each command to an agent
    rtk_hour: dict[tuple, dict] = defaultdict(lambda: defaultdict(float))
    rtk_cmd: dict[tuple, dict] = defaultdict(lambda: defaultdict(float))
    attribution_method = defaultdict(int)

    # Input price of the model each agent was using in each hour, to give a dollar
    # value to the tokens RTK kept out of the context. It is a minimum estimate:
    # it only counts the first time the output would be read; on later calls the same
    # text would still be re-read from the cache.
    weight_h: dict[tuple, list] = defaultdict(lambda: [0.0, 0.0])
    weight_ag: dict[str, list] = defaultdict(lambda: [0.0, 0.0])
    for (h, ag, model), v in usage_hour.items():
        p = model_price(model, prices)
        if not p or p.get("input") is None:
            continue
        for target in (weight_h[(h, ag)], weight_ag[ag], weight_ag["*"]):
            target[0] += p["input"] * v["msgs"]
            target[1] += v["msgs"]

    def input_price(h: str, ag: str) -> float | None:
        for target in (weight_h.get((h, ag)), weight_ag.get(ag), weight_ag.get("*") if ag == "unknown" else None):
            if target and target[1]:
                return target[0] / target[1]
        return None

    # Estimate with re-reads: a command's output stays in the history and is re-read from
    # the cache on every later call of the session. For each command, find the agent
    # session that was active and estimate how many calls still came after it.
    sess_by_hour: dict[tuple, list] = defaultdict(list)
    for (ag_s, _sid), sv in sessions.items():
        if sv["msgs"] < 2 or sv["end"] <= sv["start"]:
            continue
        model_s = max(sv["models"], key=sv["models"].get)
        p_s = model_price(model_s) or {}
        cr_s = p_s.get("cache_read")
        if cr_s is None and p_s.get("input") is not None:
            cr_s = p_s["input"] * 0.1
        cw_s = p_s.get("cache_write")
        if cw_s is None and p_s.get("input") is not None:
            cw_s = p_s["input"] * 1.25
        # how long a token stays in the context: the context grows on average by `new` tokens
        # per call and holds on average `ctx` tokens; a new token stays for about ctx/new
        # calls until compaction or the end of the conversation drops it
        ctx = (sv["input"] + sv["cache_read"] + sv["cache_write"]) / sv["msgs"]
        new = max((sv["input"] + sv["cache_write"] + sv["output"]) / sv["msgs"], 1)
        life = ctx / new
        item = (sv["start"], sv["end"], sv["msgs"], sv["folder"].lower(), cr_s, cw_s, life)
        t_h = int(sv["start"] // 3600)
        while t_h <= int(sv["end"] // 3600):
            sess_by_hour[(t_h, ag_s)].append(item)
            t_h += 1

    def rereads(ts: float, ag: str, folder: str):
        """(estimated remaining calls, cache read price, cache write price) or None."""
        cands = [x for x in sess_by_hour.get((int(ts // 3600), ag), ()) if x[0] <= ts <= x[1]]
        if not cands:
            return None
        folder = norm_path(folder).lower()
        same = [x for x in cands if folder and x[3] and (folder.startswith(x[3]) or x[3].startswith(folder))]
        start, end, msgs, _p, cr_s, cw_s, life = max(same or cands, key=lambda x: x[2])
        if cr_s is None:
            return None
        return min(msgs * (end - ts) / (end - start), life), cr_s, cw_s

    # Matching each RTK row to the agent's command was most of the collection's CPU, redone
    # every minute for the whole history. A row older than an hour always gets the same answer
    # while nothing older than that changes in the index: those answers are kept.
    memo = _attribution
    if memo["check"] is None or cmd_index.check(memo["cut"]) != memo["check"]:
        memo["map"] = {}
    memo["cut"] = time.time() - 3600
    memo["check"] = cmd_index.check(memo["cut"])
    keep_before = memo["cut"] - 60  # find() looks at most 60 s after the row
    covered: set[int] = set()
    for ts, orig, rtk_c, inp, out_, saved, ms, proj in rtk["rows"]:
        hit = memo["map"].get((ts, orig)) if ts < keep_before else None
        if hit is None:
            hit = cmd_index.find(ts, orig)
            if ts < keep_before:
                memo["map"][(ts, orig)] = hit
        ag, method, idx = hit
        # coverage: how many distinct agent commands went through RTK (a compound command
        # becomes several RTK rows and must not count more than once)
        if idx is not None and idx not in covered:
            covered.add(idx)
            activity[(hour_key(cmd_index.items[idx][0]), cmd_index.items[idx][1])]["shell_rtk"] += 1
        if ag == "unknown" and "\\temp\\claude\\" in (proj or "").lower():
            ag, method = "claude", "folder"
        attribution_method[method] += 1
        h = hour_key(ts)
        r = rtk_hour[(h, ag)]
        # same rule as `rtk gain`: above 7,500 tokens the agent would never read the
        # whole output (Bash's 30 thousand character limit), so it does not count
        if inp > 7500:
            r["large"] += 1
            continue
        saved = max(saved, 0)
        r["cmds"] += 1
        r["input"] += inp
        r["output"] += out_
        r["saved"] += saved
        r["ms"] += ms
        pin = input_price(h, ag)
        usd_rtk = saved * pin / 1_000_000 if pin is not None else None
        if usd_rtk is None:
            r["unpriced"] += saved
        else:
            r["usd"] += usd_rtk
        rel = rereads(ts, ag, proj) if saved else None
        if rel:
            remaining, cr_s, cw_s = rel
            usd_est = saved * ((cw_s or pin or 0) + remaining * cr_s) / 1_000_000
            r["usd_est"] += usd_est
            r["rereads"] += remaining * saved
        else:
            usd_est = usd_rtk or 0
            r["usd_est"] += usd_est
        base = (rtk_c or orig).split()
        name = " ".join(base[:2]) if base and base[0] == "rtk" else (base[0] if base else "?")
        if name.startswith("rtk ") and len(base) > 2 and base[1] in ("git", "cargo", "npm", "pnpm", "go", "docker", "gh", "kubectl"):
            name = " ".join(base[:3])
        c = rtk_cmd[(h[:10], name)]
        c["cmds"] += 1
        c["input"] += inp
        c["saved"] += saved
        c["usd"] += usd_rtk or 0
        c["usd_est"] += usd_est
        if saved <= 0:
            c["zero"] += 1

    # RTK coverage over the commands it knows how to filter
    #  - Claude Code (Bash): the hook records every command and whether it rewrote it
    #  - Claude Code (PowerShell), Codex and OpenCode: log commands that matched RTK
    coverage = {"by_command": defaultdict(lambda: [0, 0])}
    for ts, _sess, tid, raw, dec in rtk["hooks"]:
        head = cmd_head(raw)
        if ts and head in RTK_FILTERS:
            a = activity[(hour_key(ts), _agent_from_tool_id(tid))]
            a["sup"] += 1
            coverage["by_command"][head][0] += 1
            if dec in ("defer", "ask"):
                a["sup_rtk"] += 1
                coverage["by_command"][head][1] += 1
    for i, (ts, ag, _ws, source, head) in enumerate(cmd_index.items):
        if source == "hook" or (ag == "claude" and source == "log"):
            continue
        if head in RTK_FILTERS or head in PS_EQUIVALENT:
            a = activity[(hour_key(ts), ag)]
            a["sup"] += 1
            coverage["by_command"][head][0] += 1
            if i in covered:
                a["sup_rtk"] += 1
                coverage["by_command"][head][1] += 1
    coverage["by_command"] = dict(sorted(((k, v) for k, v in coverage["by_command"].items() if v[0] - v[1] > 0),
                                         key=lambda x: -(x[1][0] - x[1][1]))[:12])

    # --- Other token-saving tools: detects what exists on this machine and reads the savings
    # of the ones that record them. Same dollar math as RTK (minimum and estimate with re-reads).
    mcp_usage: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for ag_f, tl in tools.items():
        for name_f, n in tl.items():
            m = re.match(r"mcp(?:__|:)([^_.][^.]*?)(?:__|\.)", name_f)
            if m:
                mcp_usage[m.group(1).lower()][ag_f] += n
    try:
        detected = savings_mod.detect(signals_mod.collect(), mcp_usage)
    except Exception:  # noqa: BLE001
        detected = []
    try:
        mcp_proj = signals_mod.mcp_by_project(projects_seen)
    except Exception:  # noqa: BLE001
        mcp_proj = {}
    for f in detected:
        try:
            f["projects"] = savings_mod.by_project(f["id"], tools_by_folder, heads_by_folder, projects_seen, mcp_proj, project_name)
        except Exception:  # noqa: BLE001
            f["projects"] = []
    try:
        versions = tool_versions.status(detected, savings_mod.catalog())
    except Exception:  # noqa: BLE001
        versions = {}
    for f in detected:
        if f["id"] in versions:
            f["version"] = versions[f["id"]]
    savings_hour: dict[tuple, dict] = defaultdict(lambda: defaultdict(float))
    for f in detected:
        f["measured"] = f["measurement"] in ("rtk", "headroom")
        if f["measurement"] == "kompact":
            f["live"] = savings_mod.read_kompact()
            f["measured"] = bool(f["live"])
            continue
        evs = savings_mod.events(f["id"], f["measurement"])
        if not evs:
            continue
        f["measured"] = True
        for e in evs:
            ag_e = e["agent"]
            h_e = hour_key(e["ts"])
            pin_e = input_price(h_e, ag_e)
            usd_min = e["saved"] * pin_e / 1_000_000 if pin_e is not None else 0.0
            rel_e = rereads(e["ts"], ag_e, e.get("folder") or "")
            usd_est = e["saved"] * ((rel_e[2] or pin_e or 0) + rel_e[0] * rel_e[1]) / 1_000_000 if rel_e else usd_min
            if e.get("tool_usd") is not None:  # the tool itself computed the value
                usd_min = usd_est = e["tool_usd"]
            r_e = savings_hour[(h_e, ag_e, f["id"])]
            r_e["saved"] += e["saved"]
            r_e["events"] += 1
            r_e["usd"] += usd_min
            r_e["usd_est"] += usd_est

    failures = defaultdict(int)
    for ts, raw, err, ok in rtk["failures"]:
        base = (raw or "").split()
        failures[base[0] if base else "?"] += 1

    decisions = defaultdict(int)
    for ts, _s, tid, raw, dec in rtk["hooks"]:
        decisions[dec] += 1

    # --- Headroom
    hr_events = hr["events"]
    hr_hour = defaultdict(lambda: defaultdict(float))
    seen_ts = {round(e["ts"]) for e in hr_events}
    everything = list(hr_events) + [h for h in hr.get("history", []) if round(h["ts"]) not in seen_ts]
    for e in everything:
        ag = _headroom_client(e["client"])
        r = hr_hour[(hour_key(e["ts"]), ag, e["model"])]
        r["reqs"] += 1
        r["saved"] += e["saved"]
        if e.get("before"):
            r["before"] += e["before"]
            r["saved_measured"] += e["saved"]
        r["usd"] += e.get("usd", 0)

    # --- Ollama
    ol_hour = defaultdict(lambda: defaultdict(float))
    for ts, endpoint, status, dur in ol["reqs"]:
        r = ol_hour[(hour_key(ts), endpoint)]
        r["reqs"] += 1
        r["seconds"] += dur
        if status >= 400:
            r["errors"] += 1

    # --- Graphify: projects with a graph and calls
    graphify = {"projects": [], "calls": {}}
    for p in sorted(projects_seen):
        if p and os.path.exists(os.path.join(p, "graphify-out", "graph.json")):
            try:
                size = os.path.getsize(os.path.join(p, "graphify-out", "graph.json"))
            except OSError:
                size = 0
            if any(x["bytes"] == size and x["name"] == project_name(p) for x in graphify["projects"]):
                continue  # same folder seen through another path
            graphify["projects"].append({"folder": p, "name": project_name(p), "bytes": size,
                                         "updated": os.path.getmtime(os.path.join(p, "graphify-out", "graph.json"))})
    for ag, tl in tools.items():
        n = sum(c for name, c in tl.items() if "graphify" in name.lower())
        graphify["calls"][ag] = n + heads.get(ag, {}).get("graphify", 0)
    graphify["calls"]["shell"] = sum(1 for r in rtk["rows"] if r[1].strip().lower().startswith("graphify"))

    # --- Codex limits
    codex_limits.sort(key=lambda x: x[0])
    # --- Claude subscription (from Headroom, when it is running)
    subscription = hr.get("subscription")
    # --- Official Claude limits (Anthropic usage endpoint) and unified windows
    try:
        claude_api = limits_mod.claude()
    except Exception as e:  # noqa: BLE001
        claude_api = {"ok": False, "error": type(e).__name__}
    try:
        codex_api = limits_mod.codex()
    except Exception as e:  # noqa: BLE001
        codex_api = {"ok": False, "error": type(e).__name__}

    def rows(d: dict, cols: list[str]):
        out = []
        for k, v in d.items():
            item = dict(zip(cols, k))
            item.update({kk: (round(vv, 6) if isinstance(vv, float) else vv) for kk, vv in v.items()})
            out.append(item)
        return out

    sess_list = sorted(sessions.values(), key=lambda s: s["end"], reverse=True)
    for s in sess_list:
        s["model"] = max(s["models"], key=s["models"].get) if s["models"] else "?"
        del s["models"]

    snapshot = {
        "generated_at": time.time(),
        "collect_duration_s": round(time.time() - t0, 1),
        "agents": AGENTS,
        "sources": {
            "claude": {"ok": PATHS["claude"].exists(), "files": sum(1 for k in cache["files"] if k.startswith("claude:"))},
            "codex": {"ok": PATHS["codex"].exists(), "files": sum(1 for k in cache["files"] if k.startswith("codex:"))},
            "opencode": {"ok": oc["ok"], "error": oc["error"], "messages": len(oc["msgs"])},
            "ollama": {"ok": ol["ok"], "error": ol["error"], "requests": len(ol["reqs"]), "models": ol["models"]},
            "rtk": {"ok": rtk["ok"], "error": rtk["error"], "commands": len(rtk["rows"])},
            "headroom": {"ok": hr["ok"], "error": hr["error"], "events": len(everything)},
        },
        "usage": rows(usage_hour, ["hour", "agent", "model"]),
        "project_usage": rows(usage_proj, ["day", "agent", "project"]),
        "sessions": sess_list[:400],
        "rtk": {
            "hourly": rows(rtk_hour, ["hour", "agent"]),
            "activity": rows(activity, ["hour", "agent"]),
            "commands": rows(rtk_cmd, ["day", "command"]),
            "failures": sorted(([k, v] for k, v in failures.items()), key=lambda x: -x[1])[:15],
            "failures_total": len(rtk["failures"]),
            "hook_decisions": dict(decisions),
            "attribution": dict(attribution_method),
            "coverage": coverage,
        },
        "headroom": {
            "hourly": rows(hr_hour, ["hour", "agent", "model"]),
            "lifetime": hr["lifetime"],
        },
        "ollama": {"hourly": rows(ol_hour, ["hour", "endpoint"]), "models": ol["models"], "loaded": ol.get("loaded", [])},
        "tools": {ag: dict(sorted(tl.items(), key=lambda x: -x[1])[:40]) for ag, tl in tools.items()},
        "limits": {
            "codex": [
                {"ts": l[0], "p5h": l[1], "window_min": l[2], "reset_5h": l[3], "pweek": l[4], "reset_week": l[6], "plan": l[7]}
                for l in codex_limits
            ][-3000:],
            "claude": subscription,
            "claude_api": claude_api,
            "codex_api": codex_api,
        },
        "graphify": graphify,
        "savings": {"tools": detected, "available": savings_mod.available(detected),
                    "hourly": rows(savings_hour, ["hour", "agent", "tool"])},
        "shell_commands": {ag: dict(sorted(v.items(), key=lambda x: -x[1])[:15]) for ag, v in heads.items()},
        "prices": {
            "sources": prices_mod.info(),
            "unpriced": sorted({m for (_h, _a, m) in usage_hour if m not in ("?", "") and not model_price(m)}),
            "by_model": {m: dict(zip(("price", "source"), prices_mod.price(m))) for m in sorted({m for (_h, _a, m) in usage_hour})},
        },
    }
    snapshot["limits"]["windows"] = limits_mod.windows(snapshot["limits"]["codex"], claude_api, codex_api)
    snapshot["limits"]["series"] = limits_mod.series(snapshot["limits"]["codex"])
    _last.update(snap=snapshot, mark=mark, at=time.time())
    return snapshot


if __name__ == "__main__":
    import sys

    snap = collect(lambda m: print(m, file=sys.stderr))
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in snap.items() if k in ("usage", "project_usage", "sessions")}))
    print("sources:", json.dumps(snap["sources"], ensure_ascii=False))
    print("collected in", snap["collect_duration_s"], "s")
