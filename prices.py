"""Per-token prices for any model, from any provider.

Priority order (the first one that has the model wins):
  1. prices.json            the user's manual overrides (starts empty)
  2. LiteLLM                public table with thousands of models from every provider
  3. OpenRouter             public catalog of models with prices
  4. default_prices.json    built-in table, used with no internet

Tables 2 and 3 are downloaded to .cache/ and refreshed once a week
(or right away, with the button in the panel). All values are in US$ per 1 million tokens.
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
CACHE = BASE / ".cache"
SOURCES = {
    "litellm": "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json",
    "openrouter": "https://openrouter.ai/api/v1/models",
}
MAX_AGE = 7 * 86400

_lock = threading.Lock()
_table: dict | None = None
_info: dict = {}


def _read(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        return {}


def _convert_litellm(d: dict) -> dict:
    out = {}
    for name, v in d.items():
        if not isinstance(v, dict) or v.get("input_cost_per_token") is None:
            continue
        m = 1_000_000
        out[name.lower()] = {
            "input": v["input_cost_per_token"] * m,
            "output": (v.get("output_cost_per_token") or 0) * m,
            "cache_read": (v["cache_read_input_token_cost"] * m) if v.get("cache_read_input_token_cost") is not None else None,
            "cache_write": (v["cache_creation_input_token_cost"] * m) if v.get("cache_creation_input_token_cost") is not None else None,
        }
    return out


def _convert_openrouter(d: dict) -> dict:
    out = {}
    for mdl in d.get("data") or []:
        pr = mdl.get("pricing") or {}
        try:
            inp = float(pr.get("prompt"))
        except (TypeError, ValueError):
            continue
        if inp < 0:
            continue
        m = 1_000_000

        def f(k):
            try:
                return float(pr[k]) * m
            except (KeyError, TypeError, ValueError):
                return None

        out[str(mdl.get("id", "")).lower()] = {
            "input": inp * m, "output": f("completion") or 0,
            "cache_read": f("input_cache_read"), "cache_write": f("input_cache_write"),
        }
    return out


def refresh(force: bool = False) -> dict:
    """Downloads the public tables. Returns {source: 'ok' | 'error: ...' | 'up to date'}."""
    CACHE.mkdir(exist_ok=True)
    res = {}
    for name, url in SOURCES.items():
        dest = CACHE / f"prices_{name}.json"
        if not force and dest.exists() and time.time() - dest.stat().st_mtime < MAX_AGE:
            res[name] = "up to date"
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "token-economy"})
            with urllib.request.urlopen(req, timeout=40) as r:
                raw = json.loads(r.read().decode("utf-8"))
            conv = _convert_litellm(raw) if name == "litellm" else _convert_openrouter(raw)
            if len(conv) < 20:
                raise ValueError("empty table")
            tmp = dest.with_suffix(".tmp")
            tmp.write_text(json.dumps(conv), encoding="utf-8")
            tmp.replace(dest)
            res[name] = "ok"
        except Exception as e:  # noqa: BLE001
            res[name] = f"error: {e}"
    global _table
    with _lock:
        _table = None  # reloaded on the next lookup
    return res


def refresh_in_background():
    threading.Thread(target=refresh, daemon=True).start()


def _models(p: Path) -> dict:
    # "modelos" is the key used before the English translation
    d = _read(p)
    return d.get("models") or d.get("modelos") or {}


def _load() -> dict:
    global _table, _info
    with _lock:
        if _table is not None:
            return _table
        layers = []
        manual = _models(BASE / "prices.json")
        layers.append(("manual", {k.lower(): v for k, v in manual.items()}))
        for name in ("litellm", "openrouter"):
            p = CACHE / f"prices_{name}.json"
            layers.append((name, _read(p)))
        default = _models(BASE / "default_prices.json")
        layers.append(("default", {k.lower(): v for k, v in default.items()}))
        _table = {"layers": layers}
        _info = {
            name: {
                "models": len(t),
                "updated": (CACHE / f"prices_{name}.json").stat().st_mtime if (CACHE / f"prices_{name}.json").exists() else None,
            }
            for name, t in layers
        }
        return _table


def info() -> dict:
    _load()
    return _info


def _variants(model: str) -> list[str]:
    m = model.lower().strip()
    no_prov = m.split("/", 1)[1] if "/" in m else m
    v = [m, no_prov]
    # "claude-opus-5.5" and "claude-opus-5-5" are the same model
    v += [x.replace(".", "-") for x in v] + [x.replace("-", ".", 1) for x in v]
    # date or variant suffixes: claude-x-20260101, model:free, model#thinking
    base = re.sub(r"(-\d{8}|@\d{8}|:[\w.-]+|#[\w.-]+)$", "", no_prov)
    v.append(base)
    for prov in ("anthropic", "openai", "xai", "google", "gemini", "deepseek", "mistral", "qwen", "moonshotai", "x-ai"):
        v.append(f"{prov}/{no_prov}")
    seen, out = set(), []
    for x in v:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


_memo: dict[str, tuple] = {}


def price(model: str) -> tuple[dict | None, str | None]:
    """Returns (price in US$/1M tokens, source) or (None, None)."""
    if not model:
        return None, None
    if model in _memo and _table is not None:
        return _memo[model]
    t = _load()
    vs = _variants(model)
    found = (None, None)
    for name, tab in t["layers"]:
        for v in vs:
            p = tab.get(v)
            if p and p.get("input") is not None:
                found = (p, name)
                break
        if found[0]:
            break
    if not found[0]:
        # last resort: longest prefix (e.g. "gpt-6.1-sol-2026-11-01")
        target = vs[1]
        for name, tab in t["layers"]:
            cands = [k for k in tab if target.startswith(k) and len(k) >= 6 and tab[k].get("input") is not None]
            if cands:
                k = max(cands, key=len)
                found = (tab[k], name)
                break
    _memo[model] = found
    return found
