"""Limites dos planos de assinatura, lidos das fontes oficiais.

Claude (Pro / Max / Ultra)
    GET https://api.anthropic.com/api/oauth/usage
    cabeçalho anthropic-beta: oauth-2025-04-20, autenticado com o login que o próprio
    Claude Code guarda em ~/.claude/.credentials.json (ou CLAUDE_CODE_OAUTH_TOKEN).
    É o mesmo endpoint que o Headroom e o ccassist usam. O token é lido na hora, só vai
    para a Anthropic e nunca é gravado nem mostrado pelo Token Economy. Se o login estiver
    vencido, nada é feito: o Claude Code renova sozinho na próxima vez que rodar.

    A resposta traz uma entrada por janela (five_hour, seven_day, seven_day_opus, …).
    Cada plano tem as suas: o Ultra, por exemplo, não tem a de 5 h. Este módulo lê
    qualquer janela que vier, então novos tipos aparecem sem mudar o código.

Codex
    Vem dos próprios registros do Codex (rate_limits em cada turno), lidos pelo coletor.

Para desligar a consulta ao Claude: em Ajustes, ou "limites_claude": false em .cache/config.json.
"""
from __future__ import annotations

import json
import re
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
CACHE = BASE / ".cache"
HIST_CLAUDE = CACHE / "limites_claude.jsonl"
CONFIG = CACHE / "config.json"
URL_CLAUDE = "https://api.anthropic.com/api/oauth/usage"
INTERVALO = 300  # consulta no máximo a cada 5 min

# duração conhecida de cada janela (horas); as desconhecidas são deduzidas do nome
DURACAO = {"five_hour": 5, "seven_day": 168}

_estado = {"claude": None, "consultado": 0.0}
_lock = threading.Lock()


def _ligado() -> bool:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8")).get("limites_claude", True) is not False
    except Exception:  # noqa: BLE001
        return True


def _login_claude() -> tuple[str | None, dict]:
    """(token, informações do plano sem segredos)."""
    tok = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip()
    pasta = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    info = {}
    try:
        cred = json.loads((pasta / ".credentials.json").read_text(encoding="utf-8")).get("claudeAiOauth") or {}
        info = {"tipo": cred.get("subscriptionType"), "tier": cred.get("rateLimitTier")}
        if not tok:
            vence = cred.get("expiresAt")
            if vence and float(vence) / 1000 < time.time() + 60:
                info["vencido"] = True
                return None, info
            tok = (cred.get("accessToken") or "").strip()
    except (OSError, ValueError):
        pass
    return tok or None, info


def nome_plano(perfil: str | None) -> str | None:
    """Nome do plano só quando a Anthropic informa o nome atual (perfil da conta).

    O login guarda apenas códigos antigos (subscriptionType "max", rateLimitTier
    "default_claude_max_20x"), que não acompanham as mudanças de nome nem de
    multiplicador dos planos. Por isso eles não são usados para dar nome: sem o nome
    real, o painel mostra só o agente, sem rótulo de plano.
    """
    return (perfil or "").strip() or None


_CAMPO_PLANO = re.compile(r"plan|subscription|tier|billing|organization_type|account_type", re.I)
_SEGREDO = re.compile(r"email|uuid|^id$|_id$|token|key|phone|^name$|full_name|first_name|last_name|display_name$(?<!plan_display_name)", re.I)


def _campos_plano(obj, caminho="") -> dict:
    """Campos do perfil que falam do plano (texto curto), sem dados pessoais."""
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            c = f"{caminho}.{k}" if caminho else k
            if isinstance(v, (dict, list)):
                out.update(_campos_plano(v, c))
            elif isinstance(v, (str, bool, int, float)) and _CAMPO_PLANO.search(c) and not _SEGREDO.search(k):
                if not isinstance(v, str) or len(v) <= 60:
                    out[c] = v
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:5]):
            out.update(_campos_plano(v, f"{caminho}[{i}]"))
    return out


def _nome_no_perfil(campos: dict) -> str | None:
    """Um nome de exibição de plano, se o perfil trouxer (ex.: '...plan.display_name')."""
    for k, v in campos.items():
        if isinstance(v, str) and re.search(r"(plan|subscription).*(display|label|name)|display_?name.*(plan|subscription)", k, re.I):
            return v.strip() or None
    return None


def _perfil_claude(tok: str) -> dict:
    """Consulta o perfil da conta (mesmo endpoint que o Claude Code usa) uma vez a cada 6 h."""
    agora = time.time()
    if agora - _estado.get("perfil_em", 0) < 6 * 3600 and "perfil" in _estado:
        return _estado["perfil"]
    campos = {}
    try:
        req = urllib.request.Request("https://api.anthropic.com/api/oauth/profile", headers={
            "Authorization": f"Bearer {tok}", "anthropic-beta": "oauth-2025-04-20", "User-Agent": "token-economy"})
        with urllib.request.urlopen(req, timeout=15) as r:
            campos = _campos_plano(json.loads(r.read().decode("utf-8")))
    except Exception:  # noqa: BLE001
        pass
    _estado.update(perfil={"campos": campos, "nome": _nome_no_perfil(campos)}, perfil_em=agora)
    try:  # registra só os campos de plano, para diagnóstico
        (CACHE / "claude_perfil_campos.json").write_text(json.dumps(campos, indent=1, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return _estado["perfil"]


def _duracao(nome: str) -> float | None:
    if nome in DURACAO:
        return DURACAO[nome]
    if nome.startswith("seven_day"):
        return 168
    if nome.startswith("five_hour"):
        return 5
    return None


def _ts(v) -> float | None:
    if not v:
        return None
    try:
        import datetime as dt
        return dt.datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _consultar_claude() -> dict:
    tok, info = _login_claude()
    res = {"ok": False, "lido_em": time.time(), **info}
    if not tok:
        res["erro"] = "login_vencido" if info.get("vencido") else "sem_login"
        return res
    res["plano"] = nome_plano(_perfil_claude(tok).get("nome"))
    req = urllib.request.Request(URL_CLAUDE, headers={
        "Authorization": f"Bearer {tok}", "anthropic-beta": "oauth-2025-04-20", "User-Agent": "token-economy",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        res["erro"] = f"http_{e.code}"
        return res
    except Exception as e:  # noqa: BLE001
        res["erro"] = type(e).__name__
        return res
    # janelas fixas: five_hour, seven_day, seven_day_sonnet… Uma janela nula não existe
    # no plano (o Ultra verificado, por exemplo, não tem a de 5 h) e não aparece.
    janelas = []
    for nome, v in d.items():
        if (nome.startswith("five_hour") or nome.startswith("seven_day")) and isinstance(v, dict) and "utilization" in v:
            janelas.append({"id": nome, "pct": float(v.get("utilization") or 0),
                            "reset": _ts(v.get("resets_at")), "duracao_h": _duracao(nome)})
    # janelas semanais por modelo (ex.: Fable) vêm na lista "limits" como weekly_scoped
    for lim in d.get("limits") or []:
        if not isinstance(lim, dict) or lim.get("kind") != "weekly_scoped":
            continue
        modelo = ((lim.get("scope") or {}).get("model") or {}).get("display_name")
        if not modelo or lim.get("percent") is None:
            continue
        janelas.append({"id": "weekly_scoped:" + str(modelo)[:40], "pct": float(lim["percent"]),
                        "reset": _ts(lim.get("resets_at")), "duracao_h": 168})
    # créditos de uso extra do plano (valores em centavos de dólar na resposta)
    extra = None
    eu = d.get("extra_usage")
    if isinstance(eu, dict):
        def usd(v):
            try:
                return round(float(v) / 100, 2)
            except (TypeError, ValueError):
                return None
        casas = eu.get("decimal_places") if isinstance(eu.get("decimal_places"), int) and 0 <= eu.get("decimal_places") <= 4 else 2
        def usd(v):  # noqa: F811 - valores em unidades mínimas da moeda
            try:
                return round(float(v) / (10 ** casas), 2)
            except (TypeError, ValueError):
                return None
        extra = {"ativo": bool(eu.get("is_enabled")), "moeda": eu.get("currency") or "USD", "limite_usd": usd(eu.get("monthly_limit")),
                 "usado_usd": usd(eu.get("used_credits")),
                 "pct": float(eu["utilization"]) if isinstance(eu.get("utilization"), (int, float)) else None}
    # créditos de sessão na nuvem do Claude Code (bloco "iguana_necktie"), em dólares
    nuvem = None
    bloco = d.get("iguana_necktie")
    if isinstance(bloco, dict):
        def num(v):
            try:
                return round(float(v), 2)
            except (TypeError, ValueError):
                return None
        nuvem = {"limite_usd": num(bloco.get("limit_dollars")), "restante_usd": num(bloco.get("remaining_dollars")),
                 "reset": _ts(bloco.get("resets_at")), "bloqueado": bool(bloco.get("locked_reason"))}
        if nuvem["limite_usd"] is None and nuvem["restante_usd"] is None:
            nuvem = None
    res.update(ok=True, janelas=janelas, extra=extra, nuvem=nuvem)
    _grava_hist(HIST_CLAUDE, res["lido_em"], janelas)
    return res


def _podar(p: Path, max_linhas: int) -> None:
    linhas = p.read_text(encoding="utf-8").splitlines()
    if len(linhas) > max_linhas * 1.2:
        p.write_text("\n".join(linhas[-max_linhas:]) + "\n", encoding="utf-8")


def claude(forcar: bool = False) -> dict | None:
    """Última leitura dos limites do Claude (consulta se tiver passado o intervalo)."""
    if not _ligado():
        return {"ok": False, "erro": "desligado"}
    with _lock:
        if forcar or time.time() - _estado["consultado"] >= INTERVALO:
            _estado["consultado"] = time.time()
            _estado["claude"] = _consultar_claude()
        return _estado["claude"]


# ----------------------------------------------------------------------------
# Codex: endpoint oficial de uso (o mesmo que a CLI do Codex consulta)
# ----------------------------------------------------------------------------

URL_CODEX = "https://chatgpt.com/backend-api/wham/usage"
HIST_CODEX = CACHE / "limites_codex.jsonl"


def _login_codex() -> tuple[str | None, str | None]:
    """(access_token, account_id) do login que o Codex grava em ~/.codex/auth.json."""
    pasta = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    try:
        tokens = json.loads((pasta / "auth.json").read_text(encoding="utf-8")).get("tokens") or {}
        return (tokens.get("access_token") or "").strip() or None, tokens.get("account_id")
    except (OSError, ValueError):
        return None, None


def _id_por_duracao(seg) -> tuple[str, float | None]:
    """O Codex identifica as janelas pela duração, não pela posição na resposta."""
    try:
        h = float(seg) / 3600
    except (TypeError, ValueError):
        return "janela", None
    if abs(h - 5) < 0.6:
        return "five_hour", 5.0
    if abs(h - 168) < 12:
        return "seven_day", 168.0
    return f"janela_{round(h)}h", h


def _consultar_codex() -> dict:
    tok, conta = _login_codex()
    res = {"ok": False, "lido_em": time.time()}
    if not tok:
        res["erro"] = "sem_login"
        return res
    cab = {"Authorization": f"Bearer {tok}", "User-Agent": "codex-cli"}
    if conta:
        cab["ChatGPT-Account-Id"] = conta
    try:
        with urllib.request.urlopen(urllib.request.Request(URL_CODEX, headers=cab), timeout=15) as r:
            d = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        res["erro"] = f"http_{e.code}"
        return res
    except Exception as e:  # noqa: BLE001
        res["erro"] = type(e).__name__
        return res

    def ler_janelas(rl, prefixo=""):
        out = []
        for chave in ("primary_window", "secondary_window"):
            w = (rl or {}).get(chave)
            if not isinstance(w, dict) or w.get("used_percent") is None:
                continue
            ident, dur = _id_por_duracao(w.get("limit_window_seconds"))
            reset = w.get("reset_at")
            if not reset and w.get("reset_after_seconds") is not None:
                reset = time.time() + float(w["reset_after_seconds"])
            out.append({"id": prefixo + ident, "pct": float(w["used_percent"]),
                        "reset": float(reset) if reset else None, "duracao_h": dur})
        return out

    jans = ler_janelas(d.get("rate_limit"))
    for extra in d.get("additional_rate_limits") or []:
        nome = (extra or {}).get("limit_name") or (extra or {}).get("metered_feature")
        if nome:
            jans += ler_janelas(extra.get("rate_limit"), f"extra:{str(nome)[:40]}:")
    plano = (d.get("plan_type") or "").strip()
    res.update(ok=True, janelas=jans, plano=plano.capitalize() or None)
    _grava_hist(HIST_CODEX, res["lido_em"], jans)
    return res


def codex(forcar: bool = False) -> dict | None:
    if not _ligado():
        return {"ok": False, "erro": "desligado"}
    with _lock:
        if forcar or time.time() - _estado.get("codex_em", 0) >= INTERVALO:
            _estado["codex_em"] = time.time()
            _estado["codex"] = _consultar_codex()
        return _estado.get("codex")


def _grava_hist(arq: Path, ts: float, jans: list[dict]) -> None:
    try:
        CACHE.mkdir(exist_ok=True)
        with open(arq, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": ts, "janelas": jans}) + "\n")
        _podar(arq, 4000)
    except OSError:
        pass


def historico_claude(desde: float, arq: Path = HIST_CLAUDE) -> list[dict]:
    out = []
    try:
        for linha in arq.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(linha)
            except ValueError:
                continue
            if d.get("ts", 0) >= desde:
                out.append(d)
    except OSError:
        pass
    return out


# ----------------------------------------------------------------------------
# janelas unificadas, com ritmo e previsão
# ----------------------------------------------------------------------------

def _ritmo(amostras: list[tuple[float, float]], reset: float | None, duracao_h: float | None, pct: float, agora: float):
    """% por hora na janela atual. Usa as leituras desta janela; sem histórico,
    divide o uso pelo tempo desde o começo da janela."""
    # leituras recentes só valem se cobrirem um bom pedaço da janela: 40 minutos de
    # leituras numa janela semanal exageram qualquer pico (mínimo: 10% da janela, até 6 h)
    minimo = min(6 * 3600, (duracao_h or 5) * 3600 * 0.1)
    if len(amostras) >= 2 and amostras[-1][0] - amostras[0][0] >= minimo:
        (t0, p0), (t1, p1) = amostras[0], amostras[-1]
        if p1 >= p0:
            return (p1 - p0) / ((t1 - t0) / 3600)
    if reset and duracao_h:
        inicio = reset - duracao_h * 3600
        horas = (agora - inicio) / 3600
        if horas > 0.1:
            return pct / horas
    return None


def janelas(snap_codex: list[dict], claude_res: dict | None, codex_res: dict | None = None) -> list[dict]:
    """Lista única de janelas de limite de todos os agentes, com previsão."""
    agora = time.time()
    out = []

    # Codex pelo endpoint oficial; sem ele, pela última leitura nos registros do Codex
    if codex_res and codex_res.get("ok"):
        out += _janelas_api("codex", codex_res, historico_claude(agora - 8 * 86400, HIST_CODEX), agora)
    elif snap_codex:
        ult = snap_codex[-1]
        plano = (ult.get("plano") or "").capitalize() or None
        for campo_p, campo_r, ident, dur in (("p5h", "reset_5h", "five_hour", (ult.get("janela_min") or 300) / 60),
                                             ("psemana", "reset_semana", "seven_day", 168)):
            reset = ult.get(campo_r)
            if ult.get(campo_p) is None or not reset:
                continue
            ativa = reset > agora
            pct = ult[campo_p] if ativa else 0.0
            amostras = [(l["ts"], l[campo_p]) for l in snap_codex if l.get(campo_r) and abs(l[campo_r] - reset) < 120 and l.get(campo_p) is not None]
            out.append(_completa({"agente": "codex", "id": ident, "pct": pct, "reset": reset if ativa else None,
                                  "duracao_h": dur, "plano": plano, "lido_em": ult["ts"]},
                                 amostras if ativa else [], agora))

    if claude_res and claude_res.get("ok"):
        out += _janelas_api("claude", claude_res, historico_claude(agora - 8 * 86400), agora)
    return out


def _janelas_api(agente: str, res: dict, hist: list[dict], agora: float) -> list[dict]:
    out = []
    for j in res.get("janelas") or []:
        amostras = []
        for h in hist:
            for hj in h.get("janelas") or []:
                if hj.get("id") == j["id"] and hj.get("reset") and j.get("reset") and abs(hj["reset"] - j["reset"]) < 120:
                    amostras.append((h["ts"], hj["pct"]))
        out.append(_completa({"agente": agente, "id": j["id"], "pct": j["pct"], "reset": j.get("reset"),
                              "duracao_h": j.get("duracao_h"), "plano": res.get("plano"),
                              "lido_em": res.get("lido_em")}, amostras, agora))
    return out


def _completa(j: dict, amostras: list, agora: float) -> dict:
    ritmo = _ritmo(sorted(amostras), j.get("reset"), j.get("duracao_h"), j["pct"], agora)
    j["ritmo_h"] = round(ritmo, 3) if ritmo is not None else None
    if ritmo and ritmo > 0 and j.get("reset"):
        restante_h = max(0.0, (j["reset"] - agora) / 3600)
        j["previsto_no_reset"] = round(j["pct"] + ritmo * restante_h, 1)
        j["acaba_em_h"] = round((100 - j["pct"]) / ritmo, 2) if j["pct"] < 100 else 0.0
        j["acaba_antes"] = j["acaba_em_h"] < restante_h
    return j
