"""Sinais do que está instalado e ativo nesta máquina, para detectar ferramentas.

Lê apenas NOMES e COMANDOS de configuração dos agentes (hooks, servidores MCP,
skills, plugins). Nunca lê valores de variáveis de ambiente, tokens ou credenciais.

Fontes:
  Claude Code : ~/.claude.json (mcpServers global e por projeto), ~/.claude/settings.json
                (hooks, env com nomes de variáveis só para saber se há base URL de proxy),
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
from pathlib import Path

HOME = Path.home()
APPDATA = Path(os.environ.get("APPDATA") or HOME / "AppData" / "Roaming")
LOCALAPPDATA = Path(os.environ.get("LOCALAPPDATA") or HOME / "AppData" / "Local")


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


def expandir(caminho: str) -> Path:
    """Expande ~, %APPDATA%, %LOCALAPPDATA% e $XDG_* de um caminho do catálogo."""
    c = caminho.replace("%APPDATA%", str(APPDATA)).replace("%LOCALAPPDATA%", str(LOCALAPPDATA))
    c = c.replace("$XDG_DATA_HOME", os.environ.get("XDG_DATA_HOME") or str(HOME / ".local" / "share"))
    c = c.replace("$XDG_CONFIG_HOME", os.environ.get("XDG_CONFIG_HOME") or str(HOME / ".config"))
    return Path(os.path.expanduser(c))


def _comandos_hooks(hooks) -> list[str]:
    """Comandos de hooks no formato do Claude Code / Codex / Gemini:
    {"Evento": [{"matcher": "...", "hooks": [{"type": "command", "command": "..."}]}]}"""
    out = []
    if isinstance(hooks, dict):
        for lista in hooks.values():
            for grupo in lista if isinstance(lista, list) else []:
                for h in (grupo or {}).get("hooks") or []:
                    cmd = (h or {}).get("command")
                    if isinstance(cmd, str):
                        out.append(cmd)
    return out


def coletar() -> dict:
    """Retorna {'hooks': [(agente, comando)], 'mcp': [(agente, nome, comando)],
    'skills': [(agente, nome)], 'plugins': [(agente, nome)], 'proxy_env': [(agente, var)]}."""
    s = {"hooks": [], "mcp": [], "skills": [], "plugins": [], "proxy_env": []}

    # ---------------- Claude Code
    cj = _json(HOME / ".claude.json") or {}
    blocos = [cj.get("mcpServers") or {}] + [(p or {}).get("mcpServers") or {} for p in (cj.get("projects") or {}).values()]
    vistos = set()
    for bloco in blocos:
        for nome, cfg in bloco.items():
            if nome in vistos:
                continue
            vistos.add(nome)
            cmd = " ".join([str((cfg or {}).get("command") or "")] + [str(a) for a in (cfg or {}).get("args") or []]) or str((cfg or {}).get("url") or "")
            s["mcp"].append(("claude", nome, cmd[:300]))
    for arq in (HOME / ".claude" / "settings.json", HOME / ".claude" / "settings.local.json"):
        st = _json(arq) or {}
        s["hooks"] += [("claude", c) for c in _comandos_hooks(st.get("hooks"))]
        env = st.get("env") or {}
        for var in ("ANTHROPIC_BASE_URL", "OPENAI_BASE_URL"):
            if var in env:
                s["proxy_env"].append(("claude", f"{var}={env[var]}"[:120]))
        for nome in (st.get("enabledPlugins") or {}):
            s["plugins"].append(("claude", nome.split("@")[0]))
    pasta_skills = HOME / ".claude" / "skills"
    if pasta_skills.is_dir():
        s["skills"] += [("claude", p.name) for p in pasta_skills.iterdir() if p.is_dir()]
    inst = _json(HOME / ".claude" / "plugins" / "installed_plugins.json") or {}
    for nome in (inst.get("plugins") or inst if isinstance(inst, dict) else {}):
        if isinstance(nome, str) and nome not in ("version",):
            s["plugins"].append(("claude", nome.split("@")[0]))

    # ---------------- Codex
    codex_home = Path(os.environ.get("CODEX_HOME") or HOME / ".codex")
    ct = _toml(codex_home / "config.toml") or {}
    for nome, cfg in (ct.get("mcp_servers") or {}).items():
        cmd = " ".join([str((cfg or {}).get("command") or "")] + [str(a) for a in (cfg or {}).get("args") or []]) or str((cfg or {}).get("url") or "")
        s["mcp"].append(("codex", nome, cmd[:300]))
    for prov in (ct.get("model_providers") or {}).values():
        if isinstance(prov, dict) and prov.get("base_url"):
            s["proxy_env"].append(("codex", f"base_url={prov['base_url']}"[:120]))
    s["hooks"] += [("codex", c) for c in _comandos_hooks((_json(codex_home / "hooks.json") or {}).get("hooks"))]
    if (codex_home / "skills").is_dir():
        s["skills"] += [("codex", p.name) for p in (codex_home / "skills").iterdir() if p.is_dir()]

    # ---------------- OpenCode
    oc_dir = expandir("$XDG_CONFIG_HOME/opencode")
    oc = _json(oc_dir / "opencode.json") or {}
    mcp_oc = dict(oc.get("mcp") or {})
    aninhados = mcp_oc.pop("servers", None)  # algumas versões aninham em "servers"
    if isinstance(aninhados, dict):
        mcp_oc.update(aninhados)
    for nome, cfg in mcp_oc.items():
        cmd = cfg.get("command") if isinstance(cfg, dict) else ""
        cmd = " ".join(cmd) if isinstance(cmd, list) else str(cmd or (cfg or {}).get("url") or "")
        s["mcp"].append(("opencode", nome, cmd[:300]))
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
    for nome, cfg in (gm.get("mcpServers") or {}).items():
        cmd = " ".join([str((cfg or {}).get("command") or "")] + [str(a) for a in (cfg or {}).get("args") or []])
        s["mcp"].append(("gemini", nome, cmd[:300]))
    s["hooks"] += [("gemini", c) for c in _comandos_hooks(gm.get("hooks"))]
    for k in s:  # sem repetições
        s[k] = list(dict.fromkeys(s[k]))
    return s


def mcp_por_projeto(pastas) -> dict[str, list[tuple[str, str]]]:
    """Servidores MCP registrados só para um projeto: {pasta em minúsculas: [(nome, comando)]}.
    Fontes: ~/.claude.json (projects.<pasta>.mcpServers) e <pasta>/.mcp.json."""
    out: dict[str, list[tuple[str, str]]] = {}

    def _cmd(cfg) -> str:
        cfg = cfg or {}
        return (" ".join([str(cfg.get("command") or "")] + [str(a) for a in cfg.get("args") or []]) or str(cfg.get("url") or ""))[:300]

    def _chave(p: str) -> str:
        return os.path.normcase(os.path.normpath(p)).lower()

    cj = _json(HOME / ".claude.json") or {}
    for pasta, cfg in (cj.get("projects") or {}).items():
        for nome, srv in ((cfg or {}).get("mcpServers") or {}).items():
            out.setdefault(_chave(pasta), []).append((nome, _cmd(srv)))
    for pasta in pastas:
        if not pasta:
            continue
        for nome, srv in ((_json(Path(pasta) / ".mcp.json") or {}).get("mcpServers") or {}).items():
            out.setdefault(_chave(pasta), []).append((nome, _cmd(srv)))
    return out


def tem_exe(nomes: list[str]) -> str | None:
    for n in nomes:
        caminho = shutil.which(n)
        if caminho:
            return caminho
    return None


def casa(texto: str, padroes: list[str]) -> bool:
    """Casa por palavra: 'rtk' casa 'rtk hook claude' mas não 'artk'."""
    t = (texto or "").lower()
    return any(re.search(r"(?<![a-z0-9])" + re.escape(p.lower()) + r"(?![a-z0-9])", t) for p in padroes)
