"""Signals of what is installed and active on this machine, used to detect tools.

Reads only NAMES and COMMANDS from the agents' configuration (hooks, MCP servers,
skills, plugins). Never reads environment variable values, tokens or credentials.

Sources:
  Claude Code : ~/.claude.json (global and per-project mcpServers), ~/.claude/settings.json
                (hooks, env with variable names only to know whether there is a proxy base URL),
                ~/.claude/skills/*, ~/.claude/plugins/installed_plugins.json
  Codex       : ~/.codex/config.toml ([mcp_servers.*]), ~/.codex/hooks.json, ~/.codex/skills/*
  OpenCode    : ~/.config/opencode/opencode.json (mcp, plugin), ~/.config/opencode/plugins/*
  Gemini CLI  : ~/.gemini/settings.json (mcpServers, hooks)
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
from pathlib import Path

import runtime

HOME = Path.home()
# %APPDATA% / %LOCALAPPDATA% in the catalog map to the matching folders on macOS and Linux
APPDATA = runtime.roaming_data()
LOCALAPPDATA = runtime.local_data()


def _json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        return None


def _toml(p: Path):
    try:
        import tomllib
        return tomllib.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        return None


def expand(path: str) -> Path:
    """Expands ~, %APPDATA%, %LOCALAPPDATA% and $XDG_* in a catalog path."""
    c = path.replace("%APPDATA%", str(APPDATA)).replace("%LOCALAPPDATA%", str(LOCALAPPDATA))
    c = c.replace("$XDG_DATA_HOME", os.environ.get("XDG_DATA_HOME") or str(HOME / ".local" / "share"))
    c = c.replace("$XDG_CONFIG_HOME", os.environ.get("XDG_CONFIG_HOME") or str(HOME / ".config"))
    return Path(os.path.expanduser(c))


def _hook_commands(hooks) -> list[str]:
    """Hook commands in the Claude Code / Codex / Gemini format:
    {"Event": [{"matcher": "...", "hooks": [{"type": "command", "command": "..."}]}]}"""
    out = []
    if isinstance(hooks, dict):
        for items in hooks.values():
            for group in items if isinstance(items, list) else []:
                for h in (group or {}).get("hooks") or []:
                    cmd = (h or {}).get("command")
                    if isinstance(cmd, str):
                        out.append(cmd)
    return out


def collect() -> dict:
    """Returns {'hooks': [(agent, command)], 'mcp': [(agent, name, command)],
    'skills': [(agent, name)], 'plugins': [(agent, name)], 'proxy_env': [(agent, var)]}."""
    s = {"hooks": [], "mcp": [], "skills": [], "plugins": [], "proxy_env": []}

    # ---------------- Claude Code
    cj = _json(HOME / ".claude.json") or {}
    blocks = [cj.get("mcpServers") or {}] + [(p or {}).get("mcpServers") or {} for p in (cj.get("projects") or {}).values()]
    seen = set()
    for block in blocks:
        for name, cfg in block.items():
            if name in seen:
                continue
            seen.add(name)
            cmd = " ".join([str((cfg or {}).get("command") or "")] + [str(a) for a in (cfg or {}).get("args") or []]) or str((cfg or {}).get("url") or "")
            s["mcp"].append(("claude", name, cmd[:300]))
    for f in (HOME / ".claude" / "settings.json", HOME / ".claude" / "settings.local.json"):
        st = _json(f) or {}
        s["hooks"] += [("claude", c) for c in _hook_commands(st.get("hooks"))]
        env = st.get("env") or {}
        for var in ("ANTHROPIC_BASE_URL", "OPENAI_BASE_URL"):
            if var in env:
                s["proxy_env"].append(("claude", f"{var}={env[var]}"[:120]))
        for name in (st.get("enabledPlugins") or {}):
            s["plugins"].append(("claude", name.split("@")[0]))
    skills_dir = HOME / ".claude" / "skills"
    if skills_dir.is_dir():
        s["skills"] += [("claude", p.name) for p in skills_dir.iterdir() if p.is_dir()]
    inst = _json(HOME / ".claude" / "plugins" / "installed_plugins.json") or {}
    for name in (inst.get("plugins") or inst if isinstance(inst, dict) else {}):
        if isinstance(name, str) and name not in ("version",):
            s["plugins"].append(("claude", name.split("@")[0]))

    # ---------------- Codex
    codex_home = Path(os.environ.get("CODEX_HOME") or HOME / ".codex")
    ct = _toml(codex_home / "config.toml") or {}
    for name, cfg in (ct.get("mcp_servers") or {}).items():
        cmd = " ".join([str((cfg or {}).get("command") or "")] + [str(a) for a in (cfg or {}).get("args") or []]) or str((cfg or {}).get("url") or "")
        s["mcp"].append(("codex", name, cmd[:300]))
    for prov in (ct.get("model_providers") or {}).values():
        if isinstance(prov, dict) and prov.get("base_url"):
            s["proxy_env"].append(("codex", f"base_url={prov['base_url']}"[:120]))
    s["hooks"] += [("codex", c) for c in _hook_commands((_json(codex_home / "hooks.json") or {}).get("hooks"))]
    if (codex_home / "skills").is_dir():
        s["skills"] += [("codex", p.name) for p in (codex_home / "skills").iterdir() if p.is_dir()]

    # ---------------- OpenCode
    oc_dir = expand("$XDG_CONFIG_HOME/opencode")
    oc = _json(oc_dir / "opencode.json") or {}
    mcp_oc = dict(oc.get("mcp") or {})
    nested = mcp_oc.pop("servers", None)  # some versions nest them under "servers"
    if isinstance(nested, dict):
        mcp_oc.update(nested)
    for name, cfg in mcp_oc.items():
        cmd = cfg.get("command") if isinstance(cfg, dict) else ""
        cmd = " ".join(cmd) if isinstance(cmd, list) else str(cmd or (cfg or {}).get("url") or "")
        s["mcp"].append(("opencode", name, cmd[:300]))
    for p in oc.get("plugin") or []:
        s["plugins"].append(("opencode", str(p)))
    if (oc_dir / "plugins").is_dir():
        s["plugins"] += [("opencode", p.stem) for p in (oc_dir / "plugins").iterdir()]
    prov = oc.get("provider") or {}
    for v in prov.values() if isinstance(prov, dict) else []:
        url = ((v or {}).get("options") or {}).get("baseURL")
        if url:
            s["proxy_env"].append(("opencode", f"baseURL={url}"[:120]))

    # ---------------- Gemini CLI
    gm = _json(HOME / ".gemini" / "settings.json") or {}
    for name, cfg in (gm.get("mcpServers") or {}).items():
        cmd = " ".join([str((cfg or {}).get("command") or "")] + [str(a) for a in (cfg or {}).get("args") or []])
        s["mcp"].append(("gemini", name, cmd[:300]))
    s["hooks"] += [("gemini", c) for c in _hook_commands(gm.get("hooks"))]
    for k in s:  # no duplicates
        s[k] = list(dict.fromkeys(s[k]))
    return s


def mcp_by_project(folders) -> dict[str, list[tuple[str, str]]]:
    """MCP servers registered for a single project: {lowercase folder: [(name, command)]}.
    Sources: ~/.claude.json (projects.<folder>.mcpServers) and <folder>/.mcp.json."""
    out: dict[str, list[tuple[str, str]]] = {}

    def _cmd(cfg) -> str:
        cfg = cfg or {}
        return (" ".join([str(cfg.get("command") or "")] + [str(a) for a in cfg.get("args") or []]) or str(cfg.get("url") or ""))[:300]

    def _key(p: str) -> str:
        return os.path.normcase(os.path.normpath(p)).lower()

    cj = _json(HOME / ".claude.json") or {}
    for folder, cfg in (cj.get("projects") or {}).items():
        for name, srv in ((cfg or {}).get("mcpServers") or {}).items():
            out.setdefault(_key(folder), []).append((name, _cmd(srv)))
    for folder in folders:
        if not folder:
            continue
        for name, srv in ((_json(Path(folder) / ".mcp.json") or {}).get("mcpServers") or {}).items():
            out.setdefault(_key(folder), []).append((name, _cmd(srv)))
    return out


_which: dict[str, tuple[float, str | None]] = {}
WHICH_TTL = 600  # each lookup checks every PATH folder: thousands of disk hits per collection


def find_exe(names: list[str]) -> str | None:
    now = time.time()
    for n in names:
        hit = _which.get(n)
        if hit is None or now - hit[0] > WHICH_TTL:
            hit = _which[n] = (now, shutil.which(n))
        if hit[1]:
            return hit[1]
    return None


def matches(text: str, patterns: list[str]) -> bool:
    """Word match: 'rtk' matches 'rtk hook claude' but not 'artk'."""
    t = (text or "").lower()
    return any(re.search(r"(?<![a-z0-9])" + re.escape(p.lower()) + r"(?![a-z0-9])", t) for p in patterns)
