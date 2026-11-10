"""Análise dos dados por uma IA escolhida pelo usuário.

Três jeitos de conectar:
  - CLI instalada (Claude Code, Codex, Gemini, Grok, Qwen, Cursor, Copilot, OpenCode,
    Ollama…). O catálogo fica em provedores_ia.json; o painel mostra as que estiverem no PATH.
    Usa a assinatura que a pessoa já tem, sem chave de API.
  - API compatível com OpenAI (OpenAI, xAI, OpenRouter, Groq, DeepSeek, Gemini, Mistral,
    Ollama, LM Studio…): URL base + chave + modelo.
  - Comando personalizado: qualquer programa que leia o prompt e responda o JSON.

A IA recebe só um resumo agregado (números por agente, modelo, comando, projeto), nunca
o conteúdo das conversas. O prompt fica em prompts/analise.md e pode ser editado.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shlex
import shutil
import subprocess
import threading
import time
import traceback
import urllib.request
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
CACHE = BASE / ".cache"
PASTA_TRAB = CACHE / "ia"
HISTORICO = CACHE / "ia_analises.json"
PROMPT = BASE / "prompts" / "analise.md"
CATALOGO = BASE / "provedores_ia.json"
TEMPO_MAX = 600

IDIOMAS = {"pt": "Brazilian Portuguese", "en": "English", "es": "Spanish"}

APIS = [
    {"id": "openai", "nome": "OpenAI", "url": "https://api.openai.com/v1"},
    {"id": "xai", "nome": "xAI (Grok)", "url": "https://api.x.ai/v1"},
    {"id": "openrouter", "nome": "OpenRouter", "url": "https://openrouter.ai/api/v1"},
    {"id": "gemini", "nome": "Google Gemini", "url": "https://generativelanguage.googleapis.com/v1beta/openai"},
    {"id": "groq", "nome": "Groq", "url": "https://api.groq.com/openai/v1"},
    {"id": "deepseek", "nome": "DeepSeek", "url": "https://api.deepseek.com/v1"},
    {"id": "mistral", "nome": "Mistral", "url": "https://api.mistral.ai/v1"},
    {"id": "ollama", "nome": "Ollama (local)", "url": "http://localhost:11434/v1"},
    {"id": "lmstudio", "nome": "LM Studio (local)", "url": "http://localhost:1234/v1"},
    {"id": "outra", "nome": "Other", "url": ""},
]

estado = {"rodando": False, "etapa": "", "inicio": None, "erro": None}
_lock = threading.Lock()


# ----------------------------------------------------------------------------
# catálogo
# ----------------------------------------------------------------------------

def catalogo() -> list[dict]:
    try:
        return json.loads(CATALOGO.read_text(encoding="utf-8-sig")).get("cli") or []
    except Exception:  # noqa: BLE001
        return []


def disponiveis() -> dict:
    clis = []
    for c in catalogo():
        caminho = shutil.which(c.get("exe") or "")
        if caminho:
            clis.append({"id": c["id"], "nome": c["nome"], "verificado": bool(c.get("verificado")),
                         "modelo_obrigatorio": bool(c.get("modelo_obrigatorio")), "caminho": caminho})
    return {"cli": clis, "apis": APIS}


# ----------------------------------------------------------------------------
# resumo dos dados para a IA
# ----------------------------------------------------------------------------

def _ts_hora(h: str) -> float:
    return time.mktime(time.strptime(h[:13], "%Y-%m-%dT%H"))


def _ts_dia(d: str) -> float:
    return time.mktime(time.strptime(d[:10], "%Y-%m-%d"))


def _r(x, n=1):
    return round(x, n) if isinstance(x, float) else x


def _agrega_periodo(snap: dict, ini: float, fim: float) -> dict:
    novos = lambda r: (r.get("input") or 0) + (r.get("cache_write") or 0) + (r.get("output") or 0)
    ag = defaultdict(lambda: defaultdict(float))
    mod = defaultdict(lambda: defaultdict(float))
    for r in snap["uso"]:
        t = _ts_hora(r["hora"])
        if not (ini <= t < fim):
            continue
        for alvo in (ag[r["agente"]], mod[(r["agente"], r["modelo"])]):
            alvo["calls"] += r.get("msgs") or 0
            alvo["new_tokens"] += novos(r)
            alvo["uncached_input"] += r.get("input") or 0
            alvo["cache_read"] += r.get("cache_read") or 0
            alvo["cache_write"] += r.get("cache_write") or 0
            alvo["output"] += r.get("output") or 0
            alvo["reasoning"] += r.get("reasoning") or 0
            alvo["api_usd"] += r.get("usd") or 0

    def fecha(o):
        entrada = o["uncached_input"] + o["cache_read"] + o["cache_write"]
        o = {k: _r(v, 2) if k == "api_usd" else int(v) for k, v in o.items()}
        o["cache_hit_pct"] = _r(100 * o["cache_read"] / entrada) if entrada else None
        o["avg_input_per_call"] = int(entrada / o["calls"]) if o["calls"] else None
        o["avg_output_per_call"] = int(o["output"] / o["calls"]) if o["calls"] else None
        return o

    rtk = defaultdict(lambda: defaultdict(float))
    for r in snap["rtk"]["hora"]:
        if ini <= _ts_hora(r["hora"]) < fim:
            for k in ("cmds", "input", "saved", "usd"):
                rtk[r["agente"]][k] += r.get(k) or 0
    hr = defaultdict(lambda: defaultdict(float))
    for r in snap["headroom"]["hora"]:
        if ini <= _ts_hora(r["hora"]) < fim:
            for k in ("reqs", "saved", "saved_medido", "antes", "usd"):
                hr[r["agente"]][k] += r.get(k) or 0

    return {
        "by_agent": {a: fecha(o) for a, o in ag.items()},
        "by_model": sorted(
            [{"agent": a, "model": m, **fecha(o)} for (a, m), o in mod.items()],
            key=lambda x: -x["new_tokens"])[:12],
        "rtk_by_agent": {a: {"commands": int(o["cmds"]), "tokens_saved": int(o["saved"]),
                             "reduction_pct": _r(100 * o["saved"] / o["input"]) if o["input"] else None,
                             "api_usd_saved_min": _r(o["usd"], 2)} for a, o in rtk.items()},
        "headroom_by_client": {a: {"requests": int(o["reqs"]), "tokens_saved": int(o["saved"]),
                                   "reduction_pct": _r(100 * o["saved_medido"] / o["antes"]) if o["antes"] else None,
                                   "usd_saved": _r(o["usd"], 3)} for a, o in hr.items()},
    }


def resumo_dados(snap: dict, dias: int = 7, anterior: dict | None = None) -> dict:
    agora = time.time()
    ini = agora - dias * 86400
    ini_ant = ini - dias * 86400

    # janelas de 5 h do Codex
    jan = {}
    for l in snap["limites"]["codex"]:
        if l.get("reset_5h") and l.get("p5h") is not None and l["ts"] >= ini:
            k = round(l["reset_5h"] / 300)
            j = jan.setdefault(k, {"start": l["reset_5h"] - (l.get("janela_min") or 300) * 60, "max_pct": 0, "last": l["ts"]})
            j["max_pct"] = max(j["max_pct"], l["p5h"])
            j["last"] = max(j["last"], l["ts"])
    janelas = []
    for j in sorted(jan.values(), key=lambda x: x["start"]):
        horas = max((j["last"] - j["start"]) / 3600, 0.05)
        janelas.append({"start": dt.datetime.fromtimestamp(j["start"]).strftime("%Y-%m-%d %H:%M"),
                        "max_pct": j["max_pct"], "pct_per_hour": _r(j["max_pct"] / horas)})
    ult = snap["limites"]["codex"][-1] if snap["limites"]["codex"] else None

    rtk_cmd = defaultdict(lambda: defaultdict(float))
    for r in snap["rtk"]["comandos"]:
        if _ts_dia(r["dia"]) + 86400 >= ini:
            for k in ("cmds", "input", "saved", "zero", "usd"):
                rtk_cmd[r["comando"]][k] += r.get(k) or 0
    cmds = sorted(rtk_cmd.items(), key=lambda x: -x[1]["cmds"])[:15]

    proj = defaultdict(lambda: defaultdict(float))
    for r in snap["uso_projetos"]:
        if _ts_dia(r["dia"]) + 86400 >= ini:
            proj[r["projeto"]]["tokens_incl_cache"] += r.get("tokens") or 0
            proj[r["projeto"]]["calls"] += r.get("msgs") or 0
            proj[r["projeto"]]["api_usd"] += r.get("usd") or 0
    sess = [s for s in snap["sessoes"] if s["fim"] >= ini]
    sess.sort(key=lambda s: -s["tokens"])

    dados = {
        "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "period_days": dias,
        "current_period": _agrega_periodo(snap, ini, agora + 3600),
        "previous_period": _agrega_periodo(snap, ini_ant, ini),
        "codex_limits": {
            "plan": ult.get("plano") if ult else None,
            "weekly_used_pct_now": ult.get("psemana") if ult and (ult.get("reset_semana") or 0) > agora else 0,
            "five_hour_windows": janelas[-15:],
        } if ult else None,
        "claude_limits": "not recorded in Claude Code logs",
        "rtk": {
            "top_commands": [{"command": k, "runs": int(o["cmds"]), "tokens_saved": int(o["saved"]),
                              "reduction_pct": _r(100 * o["saved"] / o["input"]) if o["input"] else None,
                              "no_gain_pct": _r(100 * o["zero"] / o["cmds"]) if o["cmds"] else None} for k, o in cmds],
            "failures_all_time": snap["rtk"]["falhas"][:8],
            "hook_decisions_all_time": snap["rtk"]["decisoes_hook"],
        },
        "shell_commands_by_agent_all_time": {a: dict(list(v.items())[:10]) for a, v in snap.get("comandos_shell", {}).items()},
        "tools_by_agent_all_time": {a: dict(list(v.items())[:15]) for a, v in snap.get("ferramentas", {}).items()},
        "top_projects": [{"project": k, **{kk: _r(vv, 2) if kk == "api_usd" else int(vv) for kk, vv in o.items()}}
                         for k, o in sorted(proj.items(), key=lambda x: -x[1]["tokens_incl_cache"])[:10]],
        "heaviest_sessions": [{"agent": s["agente"], "project": s["projeto"], "model": s["modelo"],
                               "hours": _r((s["fim"] - s["inicio"]) / 3600), "calls": s["msgs"],
                               "tokens_incl_cache": s["tokens"],
                               "avg_context": int((s["input"] + s["cache_read"] + s["cache_write"]) / max(s["msgs"], 1)),
                               "api_usd": _r(s["usd"], 2)} for s in sess[:8]],
        "graphify": {"projects_with_graph": len(snap["graphify"]["projetos"]), "calls_all_time": snap["graphify"]["chamadas"]},
        "ollama": {"installed_models": len(snap["ollama"].get("modelos") or [])},
    }
    import nota as nota_mod
    dados["optimization_score"] = nota_mod.calcular(snap, ini, agora)
    # ferramentas de economia encontradas na máquina e o que cada uma registrou no período
    poupado = defaultdict(float)
    for r in (snap.get("economia") or {}).get("hora") or []:
        if _ts_hora(r["hora"]) >= ini:
            poupado[r["ferramenta"]] += r.get("saved") or 0
    for r in snap["rtk"]["hora"]:
        if _ts_hora(r["hora"]) >= ini:
            poupado["rtk"] += r.get("saved") or 0
    for r in snap["headroom"]["hora"]:
        if _ts_hora(r["hora"]) >= ini:
            poupado["headroom"] += r.get("saved") or 0
    dados["token_saving_tools"] = [
        {"tool": f["nome"], "category": f.get("categoria"), "records_savings": bool(f.get("medida")),
         "tokens_saved_in_period": int(poupado.get(f["id"], 0)) if f.get("medida") else None,
         "agents": f.get("agentes"), "calls_by_agents_all_time": f.get("chamadas") or None}
        for f in (snap.get("economia") or {}).get("ferramentas") or []]
    dados["rtk"]["filterable_commands_that_bypassed_rtk"] = snap["rtk"].get("cobertura", {}).get("por_comando", {})
    if anterior:
        dados["previous_analysis"] = {
            "date": anterior.get("data"), "score": anterior.get("nota"),
            "items": [i.get("titulo") for i in anterior.get("itens") or []],
        }
    return dados


def montar_prompt(snap: dict, idioma: str, dias: int, anterior: dict | None) -> str:
    modelo = PROMPT.read_text(encoding="utf-8")
    dados = json.dumps(resumo_dados(snap, dias, anterior), ensure_ascii=False, separators=(",", ":"))
    return modelo.replace("{idioma}", IDIOMAS.get(idioma, "English")).replace("{dados}", dados)


# ----------------------------------------------------------------------------
# execução
# ----------------------------------------------------------------------------

def extrair_json(texto: str) -> dict:
    texto = texto.strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", texto, re.S)
    if m:
        texto = m.group(1)
    ini, fim = texto.find("{"), texto.rfind("}")
    if ini < 0 or fim <= ini:
        raise ValueError("a resposta não trouxe JSON")
    d = json.loads(texto[ini:fim + 1])
    itens = []
    for i in d.get("itens") or d.get("items") or []:
        nivel = str(i.get("nivel") or i.get("level") or "baixa").lower()
        itens.append({
            "nivel": nivel if nivel in ("alta", "media", "baixa", "ok") else "baixa",
            "titulo": str(i.get("titulo") or i.get("title") or "")[:200],
            "texto": str(i.get("texto") or i.get("text") or "")[:1200],
            "acao": str(i.get("acao") or i.get("action") or "")[:800],
        })
    nota = d.get("nota", d.get("score"))
    try:
        nota = max(0, min(100, int(nota)))
    except (TypeError, ValueError):
        nota = None
    return {"resumo": str(d.get("resumo") or d.get("summary") or "")[:1000], "nota": nota, "itens": itens[:10]}


def _rodar_cli(cfg: dict, prompt: str) -> str:
    entrada = next((c for c in catalogo() if c["id"] == cfg.get("cli")), None)
    if not entrada:
        raise ValueError("ferramenta não está no catálogo")
    exe = shutil.which(entrada["exe"])
    if not exe:
        raise ValueError(f"{entrada['exe']} não encontrado no PATH")
    PASTA_TRAB.mkdir(parents=True, exist_ok=True)
    arquivo = PASTA_TRAB / "prompt.md"
    arquivo.write_text(prompt, encoding="utf-8")
    modelo = (cfg.get("modelo") or "").strip()
    if entrada.get("modelo_obrigatorio") and not modelo:
        raise ValueError("escolha um modelo")
    args = []
    for a in entrada["args"]:
        a = a.replace("{arquivo}", str(arquivo)).replace("{modelo}", modelo)
        if "{prompt}" in a:
            a = a.replace("{prompt}", prompt)
        args.append(a)
    if modelo and entrada.get("modelo_arg") and "{modelo}" not in " ".join(entrada["args"]):
        args = [args[0], entrada["modelo_arg"], modelo, *args[1:]] if entrada["id"] in ("codex", "opencode", "droid") else [entrada["modelo_arg"], modelo, *args]
    return _executar([exe, *args], prompt if entrada["entrada"] == "stdin" else None)


def _rodar_personalizado(cfg: dict, prompt: str) -> str:
    modelo = (cfg.get("comando") or "").strip()
    if not modelo:
        raise ValueError("comando vazio")
    PASTA_TRAB.mkdir(parents=True, exist_ok=True)
    arquivo = PASTA_TRAB / "prompt.md"
    arquivo.write_text(prompt, encoding="utf-8")
    usa_arquivo = "{arquivo}" in modelo
    partes = shlex.split(modelo.replace("{arquivo}", str(arquivo).replace("\\", "/")), posix=True)
    exe = shutil.which(partes[0]) or partes[0]
    return _executar([exe, *partes[1:]], None if usa_arquivo else prompt)


def _executar(cmd: list[str], stdin: str | None) -> str:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    env = dict(os.environ, NO_COLOR="1", TERM="dumb")
    p = subprocess.run(
        cmd, input=stdin, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=TEMPO_MAX, cwd=str(PASTA_TRAB), creationflags=flags, env=env,
    )
    saida = (p.stdout or "").strip()
    if p.returncode != 0 and "{" not in saida:
        raise RuntimeError(f"saiu com código {p.returncode}: {(p.stderr or saida)[-600:]}")
    return saida


def _rodar_api(cfg: dict, prompt: str) -> str:
    url = (cfg.get("url") or "").rstrip("/")
    modelo = (cfg.get("modelo") or "").strip()
    if not url or not modelo:
        raise ValueError("informe a URL e o modelo")
    chave = (cfg.get("chave") or "").strip()
    if chave.startswith("$"):
        chave = os.environ.get(chave[1:], "")
    corpo = json.dumps({"model": modelo, "messages": [{"role": "user", "content": prompt}]}).encode("utf-8")
    cab = {"Content-Type": "application/json", "User-Agent": "token-economy"}
    if chave:
        cab["Authorization"] = f"Bearer {chave}"
    req = urllib.request.Request(url + "/chat/completions", data=corpo, headers=cab, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TEMPO_MAX) as r:
            d = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:400]}") from None
    return d["choices"][0]["message"]["content"]


def historico() -> list[dict]:
    try:
        return json.loads(HISTORICO.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []


def analisar(snap: dict, cfg: dict, idioma: str) -> None:
    """Roda em segundo plano. O resultado vai para .cache/ia_analises.json."""
    with _lock:
        if estado["rodando"]:
            return
        estado.update(rodando=True, etapa="preparando", inicio=time.time(), erro=None)

    def trabalho():
        try:
            dias = int(cfg.get("dias") or 7)
            hist = historico()
            prompt = montar_prompt(snap, idioma, dias, hist[0] if hist else None)
            estado["etapa"] = "aguardando a IA"
            tipo = cfg.get("tipo")
            if tipo == "cli":
                bruto = _rodar_cli(cfg, prompt)
                quem = next((c["nome"] for c in catalogo() if c["id"] == cfg.get("cli")), cfg.get("cli"))
            elif tipo == "api":
                bruto = _rodar_api(cfg, prompt)
                quem = next((a["nome"] for a in APIS if a["id"] == cfg.get("api")), "API")
            elif tipo == "personalizado":
                bruto = _rodar_personalizado(cfg, prompt)
                quem = (cfg.get("comando") or "").split()[0]
            else:
                raise ValueError("escolha uma IA")
            estado["etapa"] = "lendo a resposta"
            try:
                res = extrair_json(bruto)
            except Exception as e:  # noqa: BLE001
                raise RuntimeError(f"resposta fora do formato ({e}): {bruto[:300]}") from None
            import nota as nota_mod
            res["nota"] = nota_mod.calcular(snap, time.time() - dias * 86400, time.time())["nota"]
            res.update(data=time.time(), quem=quem, modelo=cfg.get("modelo") or "", dias=dias, idioma=idioma,
                       segundos=round(time.time() - estado["inicio"]), tamanho_prompt=len(prompt))
            CACHE.mkdir(exist_ok=True)
            HISTORICO.write_text(json.dumps([res, *hist][:20], ensure_ascii=False), encoding="utf-8")
            estado["erro"] = None
        except subprocess.TimeoutExpired:
            estado["erro"] = f"a IA não respondeu em {TEMPO_MAX // 60} minutos"
        except Exception as e:  # noqa: BLE001
            estado["erro"] = str(e)
            traceback.print_exc()
        finally:
            estado.update(rodando=False, etapa="")

    threading.Thread(target=trabalho, daemon=True).start()
