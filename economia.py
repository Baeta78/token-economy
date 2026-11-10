"""Ferramentas de economia de tokens: detecção automática e leitura da economia medida.

O catálogo (ferramentas_economia.json) descreve cada ferramenta: como reconhecê-la nesta
máquina (programa no PATH, hook, servidor MCP, skill, plugin, pasta de dados) e, quando
ela grava a economia em algum lugar, qual leitor usar.

Só aparecem no painel as ferramentas detectadas. Cada uma fica em um de dois estados:
  - medida:      a ferramenta grava quanto economizou; o painel mostra tokens e US$;
  - sem medição: detectada e/ou usada pelos agentes, mas ela não registra quanto economiza.
O painel nunca inventa um número para quem não registra.

Leitores (todos devolvem eventos {ts, agente, poupados, pasta} em tokens estimados):
  token_saver   %APPDATA%\\token-saver\\savings.db  (ou ~/.token-saver, TOKEN_SAVER_DB_DIR)
  squeez        ~/.claude/squeez, ~/.codex/squeez, …  sessions/*.jsonl  (ou SQUEEZ_DIR)
  context_mode  ~/.context-mode/projects/*/context.db (ou CONTEXT_MODE_DATA_DIR)
O RTK e o Headroom têm leitores próprios no coletor.
"""
from __future__ import annotations

import glob
import json
import os
import re
import sqlite3
import time
from pathlib import Path

import sinais

BASE = Path(__file__).resolve().parent
CATALOGO = BASE / "ferramentas_economia.json"
HOME = Path.home()
JANELA = 90 * 86400  # lê no máximo os últimos 90 dias


def catalogo() -> list[dict]:
    try:
        return json.loads(CATALOGO.read_text(encoding="utf-8-sig")).get("ferramentas") or []
    except (OSError, ValueError):
        return []


def _sqlite_ro(p: Path):
    return sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True, timeout=3)


# ----------------------------------------------------------------------------
# leitores
# ----------------------------------------------------------------------------

def ler_token_saver(desde: float) -> list[dict]:
    """savings(timestamp REAL s, original_size, compressed_size em CARACTERES, platform)."""
    pastas = []
    if os.environ.get("TOKEN_SAVER_DB_DIR"):
        pastas.append(Path(os.environ["TOKEN_SAVER_DB_DIR"]))
    pastas += [sinais.APPDATA / "token-saver", HOME / ".token-saver"]
    agentes = {"claude_code": "claude", "antigravity_cli": "antigravity"}
    for pasta in pastas:
        db = pasta / "savings.db"
        if not db.exists():
            continue
        out = []
        with _sqlite_ro(db) as c:
            for ts, orig, comp, plat in c.execute(
                    "select timestamp, original_size, compressed_size, platform from savings where timestamp >= ?", (desde,)):
                poupado = max(0, (orig or 0) - (comp or 0)) / 4  # caracteres -> tokens (mesma conta da ferramenta)
                if poupado:
                    out.append({"ts": float(ts), "agente": agentes.get(plat, "desconhecido"), "poupados": poupado, "pasta": ""})
        return out
    return []


def _pastas_squeez() -> list[tuple[str, Path]]:
    if os.environ.get("SQUEEZ_DIR"):
        return [("desconhecido", Path(os.environ["SQUEEZ_DIR"]))]
    return [
        ("claude", HOME / ".claude" / "squeez"),
        ("codex", HOME / ".codex" / "squeez"),
        ("gemini", HOME / ".gemini" / "squeez"),
        ("copilot", HOME / ".copilot" / "squeez"),
        ("opencode", HOME / ".local" / "state" / "squeez" / "opencode"),
        ("pi", HOME / ".pi" / "agent" / "extensions" / "squeez"),
    ]


def ler_squeez(desde: float) -> list[dict]:
    """sessions/YYYY-MM-DD-HH.jsonl, uma linha por evento; bash traz in_tk/out_tk (tokens estimados)."""
    out = []
    for agente, pasta in _pastas_squeez():
        for arq in glob.glob(str(pasta / "sessions" / "*.jsonl")):
            try:
                if os.path.getmtime(arq) < desde:
                    continue
                with open(arq, encoding="utf-8", errors="replace") as f:
                    for linha in f:
                        if '"bash"' not in linha:
                            continue
                        try:
                            d = json.loads(linha)
                        except ValueError:
                            continue
                        ts = d.get("ts")
                        if d.get("type") != "bash" or not isinstance(ts, (int, float)):
                            continue
                        ts = ts / 1000 if ts > 1e11 else float(ts)
                        poupado = max(0, (d.get("in_tk") or 0) - (d.get("out_tk") or 0))
                        if poupado and ts >= desde:
                            out.append({"ts": ts, "agente": agente, "poupados": float(poupado), "pasta": ""})
            except OSError:
                continue
    return out


def ler_context_mode(desde: float) -> list[dict]:
    """events por projeto: poupado = sandbox_bytes - returned_bytes (bytes; ~4 por token)."""
    raiz = Path(os.environ.get("CONTEXT_MODE_DATA_DIR") or HOME / ".context-mode") / "projects"
    agentes = {"claude-code": "claude", "codex": "codex", "opencode": "opencode", "gemini": "gemini",
               "qwen": "qwen", "copilot-cli": "copilot", "vscode": "copilot", "kiro": "kiro", "pi": "pi"}
    out = []
    for db in glob.glob(str(raiz / "*" / "context.db")):
        try:
            with _sqlite_ro(Path(db)) as c:
                for ts, ag, wt, sb, rb in c.execute(
                        "select created_at, agent, worktree, sandbox_bytes, returned_bytes from events "
                        "where tool is not null and kind <> 'cost' and tool <> 'ctx_stats' and created_at >= ?",
                        (int(desde * 1000),)):
                    poupado = max(0, (sb or 0) - (rb or 0)) / 4
                    if poupado:
                        out.append({"ts": ts / 1000, "agente": agentes.get(ag or "", "desconhecido"),
                                    "poupados": poupado, "pasta": wt or ""})
        except sqlite3.Error:
            continue
    return out


def _ts_qualquer(v) -> float | None:
    """Aceita epoch em segundos ou milissegundos, ou texto ISO-8601."""
    if isinstance(v, (int, float)):
        return v / 1000 if v > 1e11 else float(v)
    if isinstance(v, str) and v:
        try:
            import datetime as dt
            return dt.datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def ler_caveman(desde: float) -> list[dict]:
    """Proxy do Caveman: ~/.caveman/caveman.db, tabela requests (antes/depois por requisição).
    A skill sozinha não grava economia; nesse caso não há eventos."""
    db = Path(os.environ.get("CAVEMAN_DB") or Path(os.environ.get("CAVEMAN_HOME") or HOME / ".caveman") / "caveman.db")
    if not db.exists():
        return []
    agentes = {"claude": "claude", "claude-code": "claude", "codex": "codex", "opencode": "opencode", "gemini": "gemini"}
    out = []
    with _sqlite_ro(db) as c:
        cols = {r[1] for r in c.execute("pragma table_info(requests)")}
        par = next(((a, b) for a, b in (("request_tokens_before", "request_tokens_after"),
                                        ("compression_tokens_before", "compression_tokens_after")) if a in cols and b in cols), None)
        if not par or "ts" not in cols:
            return []
        ag = "agent_slug" if "agent_slug" in cols else "''"
        usd = "savings_usd" if "savings_usd" in cols else "null"
        for ts, slug, antes, depois, valor in c.execute(f"select ts, {ag}, {par[0]}, {par[1]}, {usd} from requests"):
            t = _ts_qualquer(ts)
            poupado = max(0, (antes or 0) - (depois or 0))
            if t and t >= desde and poupado:
                out.append({"ts": t, "agente": agentes.get((slug or "").lower(), "desconhecido"), "poupados": float(poupado),
                            "pasta": "", "usd_ferramenta": float(valor) if valor else None})
    return out


def ler_kompact() -> dict | None:
    """O Kompact guarda os números só na memória: lê o resumo do proxy, se estiver no ar."""
    import urllib.request
    porta = os.environ.get("KOMPACT_PORT", "7878")
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/metrics", timeout=1.5) as r:
            s = (json.loads(r.read().decode("utf-8")) or {}).get("summary") or {}
        return {"poupados": float(s.get("total_tokens_saved") or 0), "processados": float(s.get("total_tokens_processed") or 0),
                "requisicoes": int(s.get("total_requests") or 0)}
    except Exception:  # noqa: BLE001 - proxy desligado
        return None


def _meio_dia(data: str) -> float | None:
    """Total diário sem horário: conta ao meio-dia (hora local) daquele dia."""
    try:
        return time.mktime(time.strptime(data[:10] + " 12", "%Y-%m-%d %H"))
    except ValueError:
        return None


def ler_cce(desde: float) -> list[dict]:
    """Code Context Engine: ~/.cce/projects/<projeto>/memory.db, savings_log(bucket, baseline, served, ts)."""
    out = []
    for db in glob.glob(str(HOME / ".cce" / "projects" / "*" / "memory.db")):
        try:
            with _sqlite_ro(Path(db)) as c:
                for ts, base, servido in c.execute("select ts, baseline, served from savings_log"):
                    t = _ts_qualquer(ts)
                    poupado = max(0, (base or 0) - (servido or 0))
                    if t and t >= desde and poupado:
                        out.append({"ts": t, "agente": "desconhecido", "poupados": float(poupado), "pasta": ""})
        except sqlite3.Error:
            continue
    return out


def ler_jcodemunch(desde: float) -> list[dict]:
    """jCodeMunch: ~/.code-index/_savings.json, chave "daily" {AAAA-MM-DD: tokens}."""
    raiz = Path(os.environ.get("CODE_INDEX_PATH") or HOME / ".code-index")
    d = None
    try:
        d = json.loads((raiz / "_savings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for data, v in (d.get("daily") or {}).items():
        n = v.get("tokens_saved", v.get("total_tokens_saved")) if isinstance(v, dict) else v
        t = _meio_dia(str(data))
        if isinstance(n, (int, float)) and n > 0 and t and t >= desde:
            out.append({"ts": t, "agente": "desconhecido", "poupados": float(n), "pasta": "", "diario": True})
    return out


def ler_lean_ctx(desde: float) -> list[dict]:
    """lean-ctx: stats.json, daily[{date, input_tokens, output_tokens}] (economia = entrada − saída)."""
    cands = [os.environ.get("LEAN_CTX_STATE_DIR"), os.environ.get("XDG_STATE_HOME") and str(Path(os.environ["XDG_STATE_HOME"]) / "lean-ctx"),
             str(HOME / ".local" / "state" / "lean-ctx"), str(sinais.LOCALAPPDATA / "lean-ctx"), str(sinais.APPDATA / "lean-ctx"),
             str(HOME / ".lean-ctx")]
    for pasta in [c for c in cands if c]:
        try:
            d = json.loads((Path(pasta) / "stats.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out = []
        for dia in d.get("daily") or []:
            t = _meio_dia(str(dia.get("date") or ""))
            poupado = max(0, (dia.get("input_tokens") or 0) - (dia.get("output_tokens") or 0))
            if t and t >= desde and poupado:
                out.append({"ts": t, "agente": "desconhecido", "poupados": float(poupado), "pasta": "", "diario": True})
        return out
    return []


def ler_token_optimizer(desde: float) -> list[dict]:
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
                    t = _ts_qualquer(ts)
                    if t and t >= desde and (n or 0) > 0:
                        out.append({"ts": t, "agente": "claude", "poupados": float(n), "pasta": "",
                                    "usd_ferramenta": float(usd) if usd else None})
        except sqlite3.Error:
            continue
        return out
    return []


LEITORES = {"token_saver": ler_token_saver, "squeez": ler_squeez, "context_mode": ler_context_mode, "caveman": ler_caveman,
            "cce": ler_cce, "jcodemunch": ler_jcodemunch, "lean_ctx": ler_lean_ctx, "token_optimizer": ler_token_optimizer}


# ----------------------------------------------------------------------------
# detecção
# ----------------------------------------------------------------------------

def detectar(sinais_maquina: dict, uso_mcp: dict[str, dict[str, int]]) -> list[dict]:
    """Ferramentas do catálogo encontradas nesta máquina.

    uso_mcp: {nome_servidor_mcp_normalizado: {agente: chamadas}} vindo dos registros dos agentes.
    """
    achadas = []
    for f in catalogo():
        d = f.get("deteccao") or {}
        provas = []
        exe = sinais.tem_exe(d.get("exes") or [])
        if exe:
            provas.append({"tipo": "programa", "valor": Path(exe).name})
        for agente, cmd in sinais_maquina["hooks"]:
            if d.get("hooks") and sinais.casa(cmd, d["hooks"]):
                provas.append({"tipo": "hook", "agente": agente})
        nomes_mcp = [n.lower() for n in d.get("mcp") or []]
        for agente, nome, cmd in sinais_maquina["mcp"]:
            if nome.lower() in nomes_mcp or (d.get("mcp_comando") and sinais.casa(cmd, d["mcp_comando"])):
                provas.append({"tipo": "mcp", "agente": agente})
        for agente, nome in sinais_maquina["skills"]:
            if nome.lower() in [n.lower() for n in d.get("skills") or []]:
                provas.append({"tipo": "skill", "agente": agente})
        for agente, nome in sinais_maquina["plugins"]:
            if nome.lower() in [n.lower() for n in d.get("plugins") or []]:
                provas.append({"tipo": "plugin", "agente": agente})
        for agente, valor in sinais_maquina["proxy_env"]:
            if d.get("proxy") and any(x.lower() in valor.lower() for x in d["proxy"]):
                provas.append({"tipo": "proxy", "agente": agente})
        for p in d.get("pastas") or []:
            if any(Path(x).exists() for x in glob.glob(str(sinais.expandir(p)))):
                provas.append({"tipo": "dados", "valor": p})
                break
        uso: dict[str, int] = {}
        for prefixo in [n.lower() for n in (d.get("uso_mcp") or d.get("mcp") or [])]:
            for agente, n in (uso_mcp.get(prefixo) or {}).items():
                uso[agente] = uso.get(agente, 0) + n
        if uso:
            provas.append({"tipo": "uso"})
        if not provas:
            continue
        agentes = sorted({p["agente"] for p in provas if p.get("agente")} | set(uso))
        achadas.append({
            "id": f["id"], "nome": f["nome"], "url": f.get("url"), "categoria": f.get("categoria"),
            "medicao": f.get("medicao"), "provas": sorted({p["tipo"] for p in provas}), "agentes": agentes,
            "chamadas": uso,
        })
    return achadas


_PREFIXO_MCP = re.compile(r"mcp(?:__|:)([^_.][^.]*?)(?:__|\.)")


def _e_da_ferramenta(nome_chamada: str, d: dict) -> bool:
    """A chamada de ferramenta registrada pelo agente é desta ferramenta de economia?
    mcp__<servidor>__x / mcp:<servidor>.x pelo nome do servidor; Skill:<nome> pelas skills."""
    n = nome_chamada.lower()
    m = _PREFIXO_MCP.match(n)
    if m:
        return m.group(1) in [x.lower() for x in (d.get("uso_mcp") or []) + (d.get("mcp") or [])]
    if n.startswith("skill:"):
        return n[6:] in [x.lower() for x in d.get("skills") or []]
    return False


def por_projeto(ferramenta_id: str, ferr_pasta: dict, cab_pasta: dict, pastas, mcp_proj: dict, nome_projeto) -> list[dict]:
    """Em quais projetos a ferramenta está configurada e quantas vezes foi consultada em cada um.

    ferr_pasta: {pasta: {nome_da_chamada: n}}, cab_pasta: {pasta: {programa_rodado_no_shell: n}},
    pastas: pastas de projeto vistas nos registros dos agentes, mcp_proj: sinais.mcp_por_projeto().
    Consultas = chamadas de MCP/skill da ferramenta + execuções do programa dela no shell.
    """
    f = next((x for x in catalogo() if x["id"] == ferramenta_id), None)
    if not f:
        return []
    d = f.get("deteccao") or {}
    exes = [x.lower() for x in d.get("exes") or []]
    nomes_mcp = [x.lower() for x in d.get("mcp") or []]
    marcas = d.get("projeto") or []
    por_nome: dict[str, dict] = {}
    for pasta in set(pastas) | set(ferr_pasta) | set(cab_pasta):
        if not pasta:
            continue
        n = sum(c for nome, c in (ferr_pasta.get(pasta) or {}).items() if _e_da_ferramenta(nome, d))
        n += sum(c for cab, c in (cab_pasta.get(pasta) or {}).items() if cab in exes)
        chave = os.path.normcase(os.path.normpath(pasta)).lower()
        inst = any((Path(pasta) / m).exists() for m in marcas) or any(
            nome.lower() in nomes_mcp or (d.get("mcp_comando") and sinais.casa(cmd, d["mcp_comando"]))
            for nome, cmd in mcp_proj.get(chave) or [])
        if not n and not inst:
            continue
        proj = nome_projeto(pasta)
        if proj.startswith("~"):  # pasta temporária ou sem nome: não é um projeto do usuário
            continue
        r = por_nome.setdefault(proj, {"projeto": proj, "pasta": pasta, "instalado": False, "consultas": 0})
        r["consultas"] += n
        r["instalado"] = r["instalado"] or inst
        if inst:
            r["pasta"] = pasta
    return sorted(por_nome.values(), key=lambda r: (-r["consultas"], r["projeto"]))


def eventos(ferramenta_id: str, medicao: str | None, desde: float | None = None) -> list[dict]:
    leitor = LEITORES.get(medicao or "")
    if not leitor:
        return []
    try:
        return leitor(desde if desde is not None else time.time() - JANELA)
    except Exception:  # noqa: BLE001 - uma ferramenta com dados estranhos não derruba o painel
        return []
