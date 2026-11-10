"""One-time migration of the .cache/ folder written by older (Portuguese) versions.

Older versions used Portuguese file names and JSON keys. At startup this renames the
files and maps the keys, so existing installs keep their settings, limit history, AI
analyses, file index and price tables. Files already in the new format are left alone,
and running it again does nothing.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

CACHE = Path(__file__).resolve().parent / ".cache"

# files whose content did not change, only their name
RENAMES = {
    "arquivos.json": "file_index.json",
    "claude_perfil_campos.json": "claude_profile_fields.json",
    "precos_litellm.json": "prices_litellm.json",
    "precos_openrouter.json": "prices_openrouter.json",
    "ia": "ai",
}
LIMIT_HISTORIES = {"limites_claude.jsonl": "claude_limits.jsonl", "limites_codex.jsonl": "codex_limits.jsonl"}
OLD_ANALYSES, NEW_ANALYSES = "ia_analises.json", "ai_analyses.json"

_AI_KEYS = {"tipo": "type", "modelo": "model", "comando": "command", "dias": "days", "chave": "key"}
_AI_TYPES = {"personalizado": "custom"}
_SUBSCRIPTION_KEYS = {"nome": "name", "agente": "agent", "mensal": "monthly"}
_ANALYSIS_KEYS = {"resumo": "summary", "nota": "score", "itens": "items", "data": "date", "quem": "by", "modelo": "model",
                  "dias": "days", "idioma": "language", "segundos": "seconds", "tamanho_prompt": "prompt_size"}
_ITEM_KEYS = {"nivel": "level", "titulo": "title", "texto": "text", "acao": "action"}
_LEVELS = {"alta": "high", "media": "medium", "baixa": "low"}


def _write_json(p: Path, data) -> None:
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def _keys(d: dict, mapping: dict) -> dict:
    """Renames the keys of a dict; a key already present under its new name wins."""
    out = {mapping.get(k, k): v for k, v in d.items() if mapping.get(k, k) == k or mapping[k] not in d}
    return out


def config(cfg: dict) -> dict:
    """Maps the settings in config.json to the new keys."""
    cfg = _keys(cfg, {"idioma": "language", "ia": "ai", "limites_claude": "claude_limits", "assinaturas": "subscriptions"})
    if isinstance(cfg.get("ai"), dict):
        ai = _keys(cfg["ai"], _AI_KEYS)
        if "type" in ai:
            ai["type"] = _AI_TYPES.get(ai["type"], ai["type"])
        if ai.get("api") == "outra":
            ai["api"] = "other"
        if isinstance(ai.get("command"), str):
            ai["command"] = ai["command"].replace("{arquivo}", "{file}")
        cfg["ai"] = ai
    if isinstance(cfg.get("subscriptions"), list):
        subs = []
        for s in cfg["subscriptions"]:
            if isinstance(s, dict):
                s = _keys(s, _SUBSCRIPTION_KEYS)
                if s.get("agent") == "desconhecido":
                    s["agent"] = "unknown"
            subs.append(s)
        cfg["subscriptions"] = subs
    return cfg


def analysis(a: dict) -> dict:
    """Maps one saved AI analysis to the new keys."""
    a = _keys(a, _ANALYSIS_KEYS)
    items = []
    for i in a.get("items") or []:
        if isinstance(i, dict):
            i = _keys(i, _ITEM_KEYS)
            i["level"] = _LEVELS.get(i.get("level"), i.get("level"))
        items.append(i)
    if "items" in a:
        a["items"] = items
    return a


def _window_id(ident):
    # windows of unknown duration were called "janela" / "janela_<n>h"
    return re.sub(r"(^|:)janela", r"\1window", ident) if isinstance(ident, str) else ident


def limit_line(d: dict) -> dict:
    """Maps one line of a limit history (.jsonl) to the new keys."""
    d = _keys(d, {"janelas": "windows"})
    wins = []
    for w in d.get("windows") or []:
        if isinstance(w, dict):
            w = _keys(w, {"duracao_h": "duration_h"})
            w["id"] = _window_id(w.get("id"))
        wins.append(w)
    if "windows" in d:
        d["windows"] = wins
    return d


def migrate(cache: Path = CACHE) -> None:
    """Runs every step; a failing step is skipped without touching the others."""
    if not cache.is_dir():
        return
    for old, new in RENAMES.items():
        try:
            if (cache / old).exists() and not (cache / new).exists():
                os.replace(cache / old, cache / new)
        except OSError:
            pass

    for old, new in LIMIT_HISTORIES.items():
        try:
            src = cache / old
            if not src.exists():
                continue
            lines = []
            for p in (src, cache / new):
                if not p.exists():
                    continue
                for line in p.read_text(encoding="utf-8").splitlines():
                    try:
                        lines.append(limit_line(json.loads(line)))
                    except (ValueError, AttributeError):
                        continue
            lines.sort(key=lambda d: d.get("ts") or 0)
            tmp = cache / (new + ".tmp")
            tmp.write_text("".join(json.dumps(d) + "\n" for d in lines), encoding="utf-8")
            os.replace(tmp, cache / new)
            src.unlink()
        except OSError:
            pass

    try:
        src = cache / OLD_ANALYSES
        if src.exists() and not (cache / NEW_ANALYSES).exists():
            hist = json.loads(src.read_text(encoding="utf-8"))
            _write_json(cache / NEW_ANALYSES, [analysis(a) if isinstance(a, dict) else a for a in hist])
            src.unlink()
    except (OSError, ValueError):
        pass

    try:
        p = cache / "config.json"
        if p.exists():
            cfg = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(cfg, dict):
                new_cfg = config(cfg)
                if new_cfg != cfg:
                    _write_json(p, new_cfg)
    except (OSError, ValueError):
        pass
