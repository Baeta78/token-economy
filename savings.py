"""Token-saving tools: automatic detection and reading of the measured savings.

The catalog (savings_tools.json) describes each tool: how to recognize it on this
machine (program on PATH, hook, MCP server, skill, plugin, data folder) and, when
it records its savings somewhere, which reader to use.

Only tools detected on the machine show up in the panel. Each one is in one of two states:
  - measured:     the tool records how much it saved; the panel shows tokens and US$;
  - not measured: detected and/or used by the agents, but it does not record its savings.
The panel never makes up a number for a tool that does not record one.

Readers (all return events {ts, agent, saved, folder} in estimated tokens):
  token_saver   %APPDATA%\\token-saver\\savings.db  (or ~/.token-saver, TOKEN_SAVER_DB_DIR)
  squeez        ~/.claude/squeez, ~/.codex/squeez, …  sessions/*.jsonl  (or SQUEEZ_DIR)
  context_mode  ~/.context-mode/projects/*/context.db (or CONTEXT_MODE_DATA_DIR)
RTK and Headroom have their own readers in the collector.
"""
from __future__ import annotations

import glob
import json
import os
import re
import sqlite3
import time
from pathlib import Path

import signals

BASE = Path(__file__).resolve().parent
CATALOG = BASE / "savings_tools.json"
HOME = Path.home()
WINDOW = 90 * 86400  # reads at most the last 90 days


def catalog() -> list[dict]:
    try:
        return json.loads(CATALOG.read_text(encoding="utf-8-sig")).get("tools") or []
    except (OSError, ValueError):
        return []


def _sqlite_ro(p: Path):
    return sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True, timeout=3)


# ----------------------------------------------------------------------------
# readers
# ----------------------------------------------------------------------------

def read_token_saver(since: float) -> list[dict]:
    """savings(timestamp REAL s, original_size, compressed_size in CHARACTERS, platform)."""
    folders = []
    if os.environ.get("TOKEN_SAVER_DB_DIR"):
        folders.append(Path(os.environ["TOKEN_SAVER_DB_DIR"]))
    folders += [signals.APPDATA / "token-saver", HOME / ".token-saver"]
    agents = {"claude_code": "claude", "antigravity_cli": "antigravity"}
    for folder in folders:
        db = folder / "savings.db"
        if not db.exists():
            continue
        out = []
        with _sqlite_ro(db) as c:
            for ts, orig, comp, plat in c.execute(
                    "select timestamp, original_size, compressed_size, platform from savings where timestamp >= ?", (since,)):
                saved = max(0, (orig or 0) - (comp or 0)) / 4  # characters -> tokens (same math as the tool)
                if saved:
                    out.append({"ts": float(ts), "agent": agents.get(plat, "unknown"), "saved": saved, "folder": ""})
        return out
    return []


def _squeez_folders() -> list[tuple[str, Path]]:
    if os.environ.get("SQUEEZ_DIR"):
        return [("unknown", Path(os.environ["SQUEEZ_DIR"]))]
    return [
        ("claude", HOME / ".claude" / "squeez"),
        ("codex", HOME / ".codex" / "squeez"),
        ("gemini", HOME / ".gemini" / "squeez"),
        ("copilot", HOME / ".copilot" / "squeez"),
        ("opencode", HOME / ".local" / "state" / "squeez" / "opencode"),
        ("pi", HOME / ".pi" / "agent" / "extensions" / "squeez"),
    ]


def read_squeez(since: float) -> list[dict]:
    """sessions/YYYY-MM-DD-HH.jsonl, one line per event; bash events carry in_tk/out_tk (estimated tokens)."""
    out = []
    for agent, folder in _squeez_folders():
        for path in glob.glob(str(folder / "sessions" / "*.jsonl")):
            try:
                if os.path.getmtime(path) < since:
                    continue
                with open(path, encoding="utf-8", errors="replace") as f:
                    for line in f:
                        if '"bash"' not in line:
                            continue
                        try:
                            d = json.loads(line)
                        except ValueError:
                            continue
                        ts = d.get("ts")
                        if d.get("type") != "bash" or not isinstance(ts, (int, float)):
                            continue
                        ts = ts / 1000 if ts > 1e11 else float(ts)
                        saved = max(0, (d.get("in_tk") or 0) - (d.get("out_tk") or 0))
                        if saved and ts >= since:
                            out.append({"ts": ts, "agent": agent, "saved": float(saved), "folder": ""})
            except OSError:
                continue
    return out


def read_context_mode(since: float) -> list[dict]:
    """events per project: saved = sandbox_bytes - returned_bytes (bytes; ~4 per token)."""
    root = Path(os.environ.get("CONTEXT_MODE_DATA_DIR") or HOME / ".context-mode") / "projects"
    agents = {"claude-code": "claude", "codex": "codex", "opencode": "opencode", "gemini": "gemini",
              "qwen": "qwen", "copilot-cli": "copilot", "vscode": "copilot", "kiro": "kiro", "pi": "pi"}
    out = []
    for db in glob.glob(str(root / "*" / "context.db")):
        try:
            with _sqlite_ro(Path(db)) as c:
                for ts, ag, wt, sb, rb in c.execute(
                        "select created_at, agent, worktree, sandbox_bytes, returned_bytes from events "
                        "where tool is not null and kind <> 'cost' and tool <> 'ctx_stats' and created_at >= ?",
                        (int(since * 1000),)):
                    saved = max(0, (sb or 0) - (rb or 0)) / 4
                    if saved:
                        out.append({"ts": ts / 1000, "agent": agents.get(ag or "", "unknown"),
                                    "saved": saved, "folder": wt or ""})
        except sqlite3.Error:
            continue
    return out


def _any_ts(v) -> float | None:
    """Accepts epoch in seconds or milliseconds, or ISO-8601 text."""
    if isinstance(v, (int, float)):
        return v / 1000 if v > 1e11 else float(v)
    if isinstance(v, str) and v:
        try:
            import datetime as dt
            return dt.datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def read_caveman(since: float) -> list[dict]:
    """Caveman proxy: ~/.caveman/caveman.db, requests table (before/after per request).
    The skill alone records no savings; in that case there are no events."""
    db = Path(os.environ.get("CAVEMAN_DB") or Path(os.environ.get("CAVEMAN_HOME") or HOME / ".caveman") / "caveman.db")
    if not db.exists():
        return []
    agents = {"claude": "claude", "claude-code": "claude", "codex": "codex", "opencode": "opencode", "gemini": "gemini"}
    out = []
    with _sqlite_ro(db) as c:
        cols = {r[1] for r in c.execute("pragma table_info(requests)")}
        pair = next(((a, b) for a, b in (("request_tokens_before", "request_tokens_after"),
                                         ("compression_tokens_before", "compression_tokens_after")) if a in cols and b in cols), None)
        if not pair or "ts" not in cols:
            return []
        ag = "agent_slug" if "agent_slug" in cols else "''"
        usd = "savings_usd" if "savings_usd" in cols else "null"
        for ts, slug, before, after, value in c.execute(f"select ts, {ag}, {pair[0]}, {pair[1]}, {usd} from requests"):
            t = _any_ts(ts)
            saved = max(0, (before or 0) - (after or 0))
            if t and t >= since and saved:
                out.append({"ts": t, "agent": agents.get((slug or "").lower(), "unknown"), "saved": float(saved),
                            "folder": "", "tool_usd": float(value) if value else None})
    return out


def read_kompact() -> dict | None:
    """Kompact keeps its numbers in memory only: reads the proxy summary, if it is running."""
    import urllib.request
    port = os.environ.get("KOMPACT_PORT", "7878")
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/metrics", timeout=1.5) as r:
            s = (json.loads(r.read().decode("utf-8")) or {}).get("summary") or {}
        return {"saved": float(s.get("total_tokens_saved") or 0), "processed": float(s.get("total_tokens_processed") or 0),
                "requests": int(s.get("total_requests") or 0)}
    except Exception:  # noqa: BLE001 - proxy is off
        return None


def _midday(date: str) -> float | None:
    """Daily total with no time of day: counts it at noon (local time) of that day."""
    try:
        return time.mktime(time.strptime(date[:10] + " 12", "%Y-%m-%d %H"))
    except ValueError:
        return None


def read_cce(since: float) -> list[dict]:
    """Code Context Engine: ~/.cce/projects/<project>/memory.db, savings_log(bucket, baseline, served, ts)."""
    out = []
    for db in glob.glob(str(HOME / ".cce" / "projects" / "*" / "memory.db")):
        try:
            with _sqlite_ro(Path(db)) as c:
                for ts, base, served in c.execute("select ts, baseline, served from savings_log"):
                    t = _any_ts(ts)
                    saved = max(0, (base or 0) - (served or 0))
                    if t and t >= since and saved:
                        out.append({"ts": t, "agent": "unknown", "saved": float(saved), "folder": ""})
        except sqlite3.Error:
            continue
    return out


def read_jcodemunch(since: float) -> list[dict]:
    """jCodeMunch: ~/.code-index/_savings.json, "daily" key {YYYY-MM-DD: tokens}."""
    root = Path(os.environ.get("CODE_INDEX_PATH") or HOME / ".code-index")
    d = None
    try:
        d = json.loads((root / "_savings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for date, v in (d.get("daily") or {}).items():
        n = v.get("tokens_saved", v.get("total_tokens_saved")) if isinstance(v, dict) else v
        t = _midday(str(date))
        if isinstance(n, (int, float)) and n > 0 and t and t >= since:
            out.append({"ts": t, "agent": "unknown", "saved": float(n), "folder": "", "daily": True})
    return out


def read_lean_ctx(since: float) -> list[dict]:
    """lean-ctx: stats.json, daily[{date, input_tokens, output_tokens}] (savings = input − output)."""
    cands = [os.environ.get("LEAN_CTX_STATE_DIR"), os.environ.get("XDG_STATE_HOME") and str(Path(os.environ["XDG_STATE_HOME"]) / "lean-ctx"),
             str(HOME / ".local" / "state" / "lean-ctx"), str(signals.LOCALAPPDATA / "lean-ctx"), str(signals.APPDATA / "lean-ctx"),
             str(HOME / ".lean-ctx")]
    for folder in [c for c in cands if c]:
        try:
            d = json.loads((Path(folder) / "stats.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out = []
        for day in d.get("daily") or []:
            t = _midday(str(day.get("date") or ""))
            saved = max(0, (day.get("input_tokens") or 0) - (day.get("output_tokens") or 0))
            if t and t >= since and saved:
                out.append({"ts": t, "agent": "unknown", "saved": float(saved), "folder": "", "daily": True})
        return out
    return []


def read_token_optimizer(since: float) -> list[dict]:
    """Token Optimizer: trends.db, savings_events(timestamp, tokens_saved, cost_saved_usd)."""
    cands = []
    if os.environ.get("TOKEN_OPTIMIZER_SNAPSHOT_DIR"):
        cands.append(Path(os.environ["TOKEN_OPTIMIZER_SNAPSHOT_DIR"]) / "trends.db")
    cands += [Path(p) for p in glob.glob(str(HOME / ".claude" / "plugins" / "data" / "*token-optimizer*" / "data" / "trends.db"))]
    cands.append(HOME / ".claude" / "_backups" / "token-optimizer" / "trends.db")
    for db in cands:
        if not db.exists():
            continue
        out = []
        try:
            with _sqlite_ro(db) as c:
                for ts, n, usd in c.execute("select timestamp, tokens_saved, cost_saved_usd from savings_events"):
                    t = _any_ts(ts)
                    if t and t >= since and (n or 0) > 0:
                        out.append({"ts": t, "agent": "claude", "saved": float(n), "folder": "",
                                    "tool_usd": float(usd) if usd else None})
        except sqlite3.Error:
            continue
        return out
    return []


READERS = {"token_saver": read_token_saver, "squeez": read_squeez, "context_mode": read_context_mode, "caveman": read_caveman,
           "cce": read_cce, "jcodemunch": read_jcodemunch, "lean_ctx": read_lean_ctx, "token_optimizer": read_token_optimizer}


# ----------------------------------------------------------------------------
# detection
# ----------------------------------------------------------------------------

def detect(machine_signals: dict, mcp_usage: dict[str, dict[str, int]]) -> list[dict]:
    """Catalog tools found on this machine.

    mcp_usage: {normalized_mcp_server_name: {agent: calls}} taken from the agents' logs.
    """
    found = []
    for f in catalog():
        d = f.get("detection") or {}
        evidence = []
        exe = signals.find_exe(d.get("exes") or [])
        if exe:
            evidence.append({"type": "program", "value": Path(exe).name})
        for agent, cmd in machine_signals["hooks"]:
            if d.get("hooks") and signals.matches(cmd, d["hooks"]):
                evidence.append({"type": "hook", "agent": agent})
        mcp_names = [n.lower() for n in d.get("mcp") or []]
        for agent, name, cmd in machine_signals["mcp"]:
            if name.lower() in mcp_names or (d.get("mcp_command") and signals.matches(cmd, d["mcp_command"])):
                evidence.append({"type": "mcp", "agent": agent})
        for agent, name in machine_signals["skills"]:
            if name.lower() in [n.lower() for n in d.get("skills") or []]:
                evidence.append({"type": "skill", "agent": agent})
        for agent, name in machine_signals["plugins"]:
            if name.lower() in [n.lower() for n in d.get("plugins") or []]:
                evidence.append({"type": "plugin", "agent": agent})
        for agent, value in machine_signals["proxy_env"]:
            if d.get("proxy") and any(x.lower() in value.lower() for x in d["proxy"]):
                evidence.append({"type": "proxy", "agent": agent})
        for p in d.get("paths") or []:
            if any(Path(x).exists() for x in glob.glob(str(signals.expand(p)))):
                evidence.append({"type": "data", "value": p})
                break
        usage: dict[str, int] = {}
        for prefix in [n.lower() for n in (d.get("mcp_usage") or d.get("mcp") or [])]:
            for agent, n in (mcp_usage.get(prefix) or {}).items():
                usage[agent] = usage.get(agent, 0) + n
        if usage:
            evidence.append({"type": "usage"})
        if not evidence:
            continue
        agents = sorted({p["agent"] for p in evidence if p.get("agent")} | set(usage))
        found.append({
            "id": f["id"], "name": f["name"], "url": f.get("url"), "category": f.get("category"),
            "measurement": f.get("measurement"), "evidence": sorted({p["type"] for p in evidence}), "agents": agents,
            "calls": usage,
        })
    return found


_MCP_PREFIX = re.compile(r"mcp(?:__|:)([^_.][^.]*?)(?:__|\.)")


def _belongs_to_tool(call_name: str, d: dict) -> bool:
    """Is the tool call logged by the agent one of this token-saving tool's calls?
    mcp__<server>__x / mcp:<server>.x by server name; Skill:<name> by the skills."""
    n = call_name.lower()
    m = _MCP_PREFIX.match(n)
    if m:
        return m.group(1) in [x.lower() for x in (d.get("mcp_usage") or []) + (d.get("mcp") or [])]
    if n.startswith("skill:"):
        return n[6:] in [x.lower() for x in d.get("skills") or []]
    return False


def by_project(tool_id: str, tools_by_folder: dict, heads_by_folder: dict, folders, mcp_proj: dict, project_name) -> list[dict]:
    """Which projects the tool is set up in and how many times it was queried in each one.

    tools_by_folder: {folder: {call_name: n}}, heads_by_folder: {folder: {program_run_in_shell: n}},
    folders: project folders seen in the agents' logs, mcp_proj: signals.mcp_by_project().
    Queries = the tool's MCP/skill calls + runs of its program in the shell.
    """
    f = next((x for x in catalog() if x["id"] == tool_id), None)
    if not f:
        return []
    d = f.get("detection") or {}
    exes = [x.lower() for x in d.get("exes") or []]
    mcp_names = [x.lower() for x in d.get("mcp") or []]
    markers = d.get("project") or []
    by_name: dict[str, dict] = {}
    for folder in set(folders) | set(tools_by_folder) | set(heads_by_folder):
        if not folder:
            continue
        n = sum(c for name, c in (tools_by_folder.get(folder) or {}).items() if _belongs_to_tool(name, d))
        n += sum(c for head, c in (heads_by_folder.get(folder) or {}).items() if head in exes)
        key = os.path.normcase(os.path.normpath(folder)).lower()
        inst = any((Path(folder) / m).exists() for m in markers) or any(
            name.lower() in mcp_names or (d.get("mcp_command") and signals.matches(cmd, d["mcp_command"]))
            for name, cmd in mcp_proj.get(key) or [])
        if not n and not inst:
            continue
        proj = project_name(folder)
        if proj.startswith("~"):  # temporary or unnamed folder: not a user project
            continue
        r = by_name.setdefault(proj, {"project": proj, "folder": folder, "installed": False, "queries": 0})
        r["queries"] += n
        r["installed"] = r["installed"] or inst
        if inst:
            r["folder"] = folder
    return sorted(by_name.values(), key=lambda r: (-r["queries"], r["project"]))


def events(tool_id: str, measurement: str | None, since: float | None = None) -> list[dict]:
    reader = READERS.get(measurement or "")
    if not reader:
        return []
    try:
        return reader(since if since is not None else time.time() - WINDOW)
    except Exception:  # noqa: BLE001 - a tool with odd data must not bring the panel down
        return []
