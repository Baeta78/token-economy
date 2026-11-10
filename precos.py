"""Preços por token de qualquer modelo, de qualquer provedor.

Ordem de prioridade (a primeira que tiver o modelo vence):
  1. precos.json            ajustes manuais do usuário (começa vazio)
  2. LiteLLM                tabela pública com milhares de modelos de todos os provedores
  3. OpenRouter             catálogo público de modelos com preço
  4. precos_padrao.json     tabela embutida, usada sem internet

As tabelas 2 e 3 são baixadas para .cache/ e atualizadas uma vez por semana
(ou na hora, pelo botão no painel). Todos os valores ficam em US$ por 1 milhão de tokens.
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
FONTES = {
    "litellm": "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json",
    "openrouter": "https://openrouter.ai/api/v1/models",
}
VALIDADE = 7 * 86400

_lock = threading.Lock()
_tabela: dict | None = None
_info: dict = {}


def _ler(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        return {}


def _converter_litellm(d: dict) -> dict:
    out = {}
    for nome, v in d.items():
        if not isinstance(v, dict) or v.get("input_cost_per_token") is None:
            continue
        m = 1_000_000
        out[nome.lower()] = {
            "input": v["input_cost_per_token"] * m,
            "output": (v.get("output_cost_per_token") or 0) * m,
            "cache_read": (v["cache_read_input_token_cost"] * m) if v.get("cache_read_input_token_cost") is not None else None,
            "cache_write": (v["cache_creation_input_token_cost"] * m) if v.get("cache_creation_input_token_cost") is not None else None,
        }
    return out


def _converter_openrouter(d: dict) -> dict:
    out = {}
    for mdl in d.get("data") or []:
        pr = mdl.get("pricing") or {}
        try:
            entrada = float(pr.get("prompt"))
        except (TypeError, ValueError):
            continue
        if entrada < 0:
            continue
        m = 1_000_000

        def f(k):
            try:
                return float(pr[k]) * m
            except (KeyError, TypeError, ValueError):
                return None

        out[str(mdl.get("id", "")).lower()] = {
            "input": entrada * m, "output": f("completion") or 0,
            "cache_read": f("input_cache_read"), "cache_write": f("input_cache_write"),
        }
    return out


def atualizar(forcar: bool = False) -> dict:
    """Baixa as tabelas públicas. Devolve {fonte: 'ok' | 'erro: ...' | 'em dia'}."""
    CACHE.mkdir(exist_ok=True)
    res = {}
    for nome, url in FONTES.items():
        destino = CACHE / f"precos_{nome}.json"
        if not forcar and destino.exists() and time.time() - destino.stat().st_mtime < VALIDADE:
            res[nome] = "em dia"
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "token-economy"})
            with urllib.request.urlopen(req, timeout=40) as r:
                bruto = json.loads(r.read().decode("utf-8"))
            conv = _converter_litellm(bruto) if nome == "litellm" else _converter_openrouter(bruto)
            if len(conv) < 20:
                raise ValueError("tabela vazia")
            tmp = destino.with_suffix(".tmp")
            tmp.write_text(json.dumps(conv), encoding="utf-8")
            tmp.replace(destino)
            res[nome] = "ok"
        except Exception as e:  # noqa: BLE001
            res[nome] = f"erro: {e}"
    global _tabela
    with _lock:
        _tabela = None  # recarrega na próxima consulta
    return res


def atualizar_em_segundo_plano():
    threading.Thread(target=atualizar, daemon=True).start()


def _carregar() -> dict:
    global _tabela, _info
    with _lock:
        if _tabela is not None:
            return _tabela
        camadas = []
        manual = _ler(BASE / "precos.json").get("modelos") or {}
        camadas.append(("manual", {k.lower(): v for k, v in manual.items()}))
        for nome in ("litellm", "openrouter"):
            p = CACHE / f"precos_{nome}.json"
            camadas.append((nome, _ler(p)))
        padrao = _ler(BASE / "precos_padrao.json").get("modelos") or {}
        camadas.append(("padrao", {k.lower(): v for k, v in padrao.items()}))
        _tabela = {"camadas": camadas}
        _info = {
            nome: {
                "modelos": len(t),
                "atualizado": (CACHE / f"precos_{nome}.json").stat().st_mtime if (CACHE / f"precos_{nome}.json").exists() else None,
            }
            for nome, t in camadas
        }
        return _tabela


def info() -> dict:
    _carregar()
    return _info


def _variantes(modelo: str) -> list[str]:
    m = modelo.lower().strip()
    sem_prov = m.split("/", 1)[1] if "/" in m else m
    v = [m, sem_prov]
    # "claude-opus-5.5" e "claude-opus-5-5" são o mesmo modelo
    v += [x.replace(".", "-") for x in v] + [x.replace("-", ".", 1) for x in v]
    # sufixos de data ou de variante: claude-x-20260101, model:free, model#thinking
    base = re.sub(r"(-\d{8}|@\d{8}|:[\w.-]+|#[\w.-]+)$", "", sem_prov)
    v.append(base)
    for prov in ("anthropic", "openai", "xai", "google", "gemini", "deepseek", "mistral", "qwen", "moonshotai", "x-ai"):
        v.append(f"{prov}/{sem_prov}")
    vistos, out = set(), []
    for x in v:
        if x and x not in vistos:
            vistos.add(x)
            out.append(x)
    return out


_memo: dict[str, tuple] = {}


def preco(modelo: str) -> tuple[dict | None, str | None]:
    """Devolve (preço em US$/1M tokens, fonte) ou (None, None)."""
    if not modelo:
        return None, None
    if modelo in _memo and _tabela is not None:
        return _memo[modelo]
    t = _carregar()
    vs = _variantes(modelo)
    achado = (None, None)
    for nome, tab in t["camadas"]:
        for v in vs:
            p = tab.get(v)
            if p and p.get("input") is not None:
                achado = (p, nome)
                break
        if achado[0]:
            break
    if not achado[0]:
        # último recurso: prefixo mais longo (ex.: "gpt-6.1-sol-2026-11-01")
        alvo = vs[1]
        for nome, tab in t["camadas"]:
            cands = [k for k in tab if alvo.startswith(k) and len(k) >= 6 and tab[k].get("input") is not None]
            if cands:
                k = max(cands, key=len)
                achado = (tab[k], nome)
                break
    _memo[modelo] = achado
    return achado
