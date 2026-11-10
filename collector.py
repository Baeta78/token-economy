"""Coleta os dados de uso e economia de tokens das ferramentas instaladas nesta máquina.

Fontes lidas (somente leitura, nada é alterado):
  - Claude Code : ~/.claude/projects/**/*.jsonl          (uso por mensagem)
  - Codex       : ~/.codex/sessions/**/rollout-*.jsonl   (uso por turno + limites de 5h e semanal)
  - OpenCode    : ~/.local/share/opencode/opencode.db     (uso por mensagem)
  - Ollama      : %LOCALAPPDATA%/Ollama/server*.log        (requisições e duração; o Ollama não registra tokens)
  - RTK         : %LOCALAPPDATA%/rtk/history.db            (economia na saída de comandos)
  - Headroom    : ~/.headroom/savings_events.jsonl e proxy_savings.json (economia no proxy)
  - Graphify    : chamadas registradas pelos agentes e projetos com graphify-out/graph.json

Os arquivos grandes (Claude e Codex) são lidos de forma incremental: o cache em
.cache/ guarda até onde cada arquivo já foi lido.
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

import economia as economia_mod
import limites as limites_mod
import sinais as sinais_mod
import precos as precos_mod
from pathlib import Path

HOME = Path(os.environ.get("USERPROFILE") or Path.home())
LOCAL = Path(os.environ.get("LOCALAPPDATA") or HOME / "AppData" / "Local")
BASE = Path(__file__).resolve().parent
CACHE_DIR = BASE / ".cache"
CACHE_FILE = CACHE_DIR / "arquivos.json"
CACHE_VERSION = 5

PATHS = {
    "claude": HOME / ".claude" / "projects",
    "codex": HOME / ".codex" / "sessions",
    "codex_archived": HOME / ".codex" / "archived_sessions",
    "opencode": HOME / ".local" / "share" / "opencode" / "opencode.db",
    "ollama_logs": LOCAL / "Ollama",
    "rtk": LOCAL / "rtk" / "history.db",
    "headroom": HOME / ".headroom",
}

AGENTES = {
    "claude": "Claude Code",
    "codex": "Codex",
    "opencode": "OpenCode",
    "ollama": "Ollama",
    "desconhecido": "Não identificado",
}


def load_precos() -> dict:
    return {}


# ----------------------------------------------------------------------------
# utilidades
# ----------------------------------------------------------------------------

def parse_ts(value) -> float | None:
    """Converte ISO-8601, epoch em segundos ou em milissegundos para epoch em segundos."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        return v / 1000.0 if v > 1e11 else v
    s = str(value).strip()
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        # Python só aceita até 6 casas decimais nos segundos
        m = re.match(r"^(.*\.\d{6})\d+(.*)$", s)
        if m:
            s = m.group(1) + m.group(2)
        d = dt.datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=dt.timezone.utc)
        return d.timestamp()
    except Exception:
        return None


def hour_key(ts: float) -> str:
    """Hora local no formato AAAA-MM-DDTHH."""
    return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%dT%H")


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


_ANONIMO = re.compile(r"^([0-9a-f]{8}-[0-9a-f-]{20,}|[0-9a-f]{12,}|agent-[0-9a-f]+|scratchpad|worktrees|\.claude)$", re.I)


@functools.lru_cache(maxsize=4096)
def projeto_nome(p: str) -> str:
    """Nome do projeto: a raiz do repositório git, ou a última pasta com nome legível."""
    p = norm_path(p)
    if not p:
        return "~sem"
    low = p.lower()
    if "\\temp\\claude\\" in low or "\\appdata\\local\\temp" in low:
        return "~temp"
    # worktree de subagente: .../repo/.claude/worktrees/agent-xxx -> repo
    m = re.search(r"\\([^\\]+)\\\.claude\\worktrees\\", p, re.I)
    if m:
        return m.group(1)
    # sobe até a raiz do git, se existir
    cur = p
    for _ in range(8):
        if os.path.isdir(os.path.join(cur, ".git")) or os.path.isfile(os.path.join(cur, ".git")):
            return os.path.basename(cur) or cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    parts = [x for x in p.split("\\") if x]
    while len(parts) > 1 and _ANONIMO.match(parts[-1]):
        parts.pop()
    return parts[-1] if parts else p


_ESPERA = re.compile(r"wait|sleep|poll|status", re.I)


def conta_ferramenta_hora(th: dict, ts: float, nome: str) -> None:
    """Chamadas de ferramenta por hora: [total, espera]."""
    h = hour_key(ts)
    v = th.setdefault(h, [0, 0])
    v[0] += 1
    if _ESPERA.search(nome or ""):
        v[1] += 1


def familia_modelo(model: str) -> str:
    m = (model or "").lower()
    if not m:
        return "desconhecido"
    return m


def preco_modelo(model: str, precos: dict | None = None) -> dict | None:
    return precos_mod.preco(model)[0]


def custo_usd(model: str, u: dict, precos: dict) -> float | None:
    p = preco_modelo(model, precos)
    if not p or p.get("input") is None:
        return None
    entrada = p.get("input", 0) or 0
    cr = p.get("cache_read")
    cw = p.get("cache_write")
    cw1h = min(u.get("cache_write_1h", 0), u.get("cache_write", 0))
    return (
        u.get("input", 0) * entrada
        + u.get("cache_read", 0) * (cr if cr is not None else entrada * 0.1)
        + (u.get("cache_write", 0) - cw1h) * (cw if cw is not None else entrada * 1.25)
        + cw1h * entrada * 2
        + u.get("output", 0) * (p.get("output", 0) or 0)
    ) / 1_000_000


# ----------------------------------------------------------------------------
# cache incremental por arquivo
# ----------------------------------------------------------------------------

_cache_lock = threading.Lock()


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


def iter_new_lines(path: str, entry: dict):
    """Lê só as linhas novas desde o último offset. Recomeça se o arquivo encolheu."""
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
    # só processa até a última quebra de linha completa
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
        progress(f"Claude Code: {i + 1}/{len(files)} arquivos")
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
            # a mesma mensagem aparece em várias linhas; fica a de maior saída
            if prev is None or rec[3] >= prev[3]:
                msgs[mid] = rec
            for block in m.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    name = block.get("name") or "?"
                    inp = block.get("input") or {}
                    if name == "Skill":
                        name = "Skill:" + str(inp.get("skill") or "?")
                    tools[name] = tools.get(name, 0) + 1
                    conta_ferramenta_hora(th, ts, name)
                    if block.get("name") in ("Bash", "PowerShell"):
                        c = inp.get("command")
                        if c:
                            ferr = "ps" if block.get("name") == "PowerShell" else "sh"
                            cmds.append([round(ts, 3), norm_cmd(c)[:600], ferr])
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
        progress(f"Codex: {i + 1}/{len(files)} arquivos")
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
                # o Codex embrulha as ferramentas em "exec": conta a ferramenta real
                inner = re.findall(r"tools\.([A-Za-z0-9_]+)\(", body or "")
                for n in inner or [name]:
                    tools[n] = tools.get(n, 0) + 1
                    if ts is not None:
                        conta_ferramenta_hora(th, ts, n)
                if ts is not None:
                    for c in _codex_cmds(body):
                        cmds.append([round(ts, 3), norm_cmd(c)[:600]])
        entry["mtime"] = st.st_mtime


# ----------------------------------------------------------------------------
# OpenCode
# ----------------------------------------------------------------------------

def scan_opencode() -> dict:
    out = {"msgs": [], "tools": defaultdict(int), "tools_dir": defaultdict(lambda: defaultdict(int)), "cmds": [], "ok": False, "erro": None}
    db = PATHS["opencode"]
    if not db.exists():
        out["erro"] = "banco não encontrado"
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
                    pasta = dirs.get(sid, "")
                    nomes = [name]
                    if name == "execute":
                        inner = re.findall(r"tools\[\"([^\"]+)\"\]\.([A-Za-z0-9_]+)", inp.get("code") or "")
                        nomes = [f"mcp:{srv}.{fn}" for srv, fn in inner] or [name]
                    for n in nomes:
                        out["tools"][n] += 1
                        out["tools_dir"][pasta][n] += 1
                    cmd = inp.get("command") or inp.get("cmd")
                    if cmd and ts:
                        out["cmds"].append([ts, norm_cmd(cmd)[:600], pasta])
        out["ok"] = True
    except Exception as e:  # noqa: BLE001
        out["erro"] = str(e)
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
    m = re.match(r"m([\d.]+)s", unit)  # "1m20s" vira num=1 unit=m20s
    if m:
        return v * 60 + float(m.group(1))
    m = re.match(r"h(\d+)m([\d.]+)s", unit)
    if m:
        return v * 3600 + int(m.group(1)) * 60 + float(m.group(2))
    return 0.0


def scan_ollama() -> dict:
    out = {"reqs": [], "modelos": [], "ok": False, "erro": None}
    logdir = PATHS["ollama_logs"]
    seen = set()
    for path in sorted(glob.glob(str(logdir / "server*.log"))):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if "[GIN]" not in line or "POST" not in line:
                        continue
                    m = _GIN.search(line)
                    if not m:
                        continue
                    endpoint = m.group(7)
                    if not any(x in endpoint for x in ("/api/chat", "/api/generate", "/v1/chat", "/v1/messages", "/v1/responses", "/v1/completions", "/api/embed")):
                        continue
                    key = (m.group(1), m.group(2), endpoint, m.group(4))
                    if key in seen:
                        continue
                    seen.add(key)
                    try:
                        d = dt.datetime.strptime(m.group(1) + " " + m.group(2), "%Y/%m/%d %H:%M:%S")
                    except ValueError:
                        continue
                    out["reqs"].append([d.timestamp(), endpoint, int(m.group(3)), _dur_s(m.group(4), m.group(5))])
            out["ok"] = True
        except Exception as e:  # noqa: BLE001
            out["erro"] = str(e)
    try:
        import subprocess

        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        res = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=8, creationflags=flags)
        for line in res.stdout.splitlines()[1:]:
            cols = line.split()
            if len(cols) >= 4:
                out["modelos"].append({"nome": cols[0], "tamanho": " ".join(cols[2:4])})
        res = subprocess.run(["ollama", "ps"], capture_output=True, text=True, timeout=8, creationflags=flags)
        out["carregados"] = [l.split()[0] for l in res.stdout.splitlines()[1:] if l.strip()]
    except Exception:
        pass
    return out


# ----------------------------------------------------------------------------
# RTK
# ----------------------------------------------------------------------------

def scan_rtk() -> dict:
    out = {"rows": [], "falhas": [], "hooks": [], "ok": False, "erro": None}
    db = PATHS["rtk"]
    if not db.exists():
        out["erro"] = "history.db não encontrado"
        return out
    try:
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        for row in c.execute(
            "select timestamp, original_cmd, rtk_cmd, input_tokens, output_tokens, saved_tokens, exec_time_ms, project_path from commands"
        ):
            ts = parse_ts(row[0])
            if ts is None:
                continue
            out["rows"].append([ts, row[1] or "", row[2] or "", row[3] or 0, row[4] or 0, row[5] or 0, row[6] or 0, row[7] or ""])
        for row in c.execute("select timestamp, raw_command, error_message, fallback_succeeded from parse_failures"):
            out["falhas"].append([parse_ts(row[0]), row[1] or "", row[2] or "", row[3]])
        for row in c.execute("select timestamp, session_id, tool_use_id, raw_cmd, decision from hook_decisions"):
            out["hooks"].append([parse_ts(row[0]), row[1], row[2] or "", norm_cmd(row[3] or ""), row[4] or ""])
        out["ok"] = True
    except Exception as e:  # noqa: BLE001
        out["erro"] = str(e)
    return out


def _agente_por_tool_id(tid: str) -> str:
    if tid.startswith("toolu_"):
        return "claude"
    if tid.startswith("call_"):
        return "codex"
    return "desconhecido"


_WORD = re.compile(r"[a-z0-9_\-]{2,}")
_STOP = {"users", "jonas", "dev", "null", "head", "tail", "rtk", "cd", "echo", "true"}


def _palavras(s: str) -> list[str]:
    seen, out = set(), []
    for w in _WORD.findall((s or "").lower()):
        if w not in seen and w not in _STOP:
            seen.add(w)
            out.append(w)
    return out


# comandos que o RTK sabe comprimir, e os equivalentes do PowerShell (que o RTK não
# filtra, mas dá para trocar pela versão do Bash)
RTK_FILTRA = {
    "cat", "head", "tail", "grep", "rg", "ls", "find", "tree", "wc", "diff", "git", "gh", "curl",
    "cargo", "npm", "pnpm", "npx", "yarn", "bun", "tsc", "jest", "vitest", "eslint", "prettier", "next",
    "pytest", "ruff", "mypy", "pip", "go", "golangci-lint", "docker", "kubectl", "aws", "terraform",
    "dotnet", "mvn", "gradle", "gradlew", "rspec", "rubocop", "rake", "php", "phpunit", "composer",
}
PS_EQUIVALENTE = {"get-content", "gc", "type", "select-string", "sls", "get-childitem", "gci", "dir", "measure-object"}


def cabeca_cmd(c: str) -> str:
    """Primeira palavra útil de um comando (pula cd, &&, ; e |)."""
    for seg in re.split(r"&&|\|\||;|\|", c or ""):
        w = seg.strip().split()
        if not w or w[0].lower() in ("cd", "set-location", "sl"):
            continue
        cab = w[0].strip("&'\"").lower()
        if cab == "rtk" and len(w) > 1:
            cab = w[1].lower()
        return cab.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].removesuffix(".exe")
    return ""


class CmdIndex:
    """Índice de comandos executados por cada agente, ordenado por tempo.

    O RTK grava o comando já reescrito (aspas trocadas, ~ expandido, só o trecho
    filtrado de um comando composto), então a comparação é por palavras: o
    comando do RTK casa com o do agente quando a maior parte das suas palavras
    aparece no comando do agente, perto no tempo.
    """

    def __init__(self):
        self.items: list[tuple[float, str, set]] = []
        self.atividade: dict[str, list[float]] = defaultdict(list)

    def add(self, ts: float, agente: str, cmd: str, fonte: str = "log"):
        if ts and cmd:
            self.items.append((ts, agente, set(_palavras(cmd)), fonte, cabeca_cmd(cmd)))

    def ativo(self, ts: float, agente: str):
        self.atividade[agente].append(ts)

    def build(self):
        self.items.sort(key=lambda x: x[0])
        self.times = [x[0] for x in self.items]
        for v in self.atividade.values():
            v.sort()

    def find(self, ts: float, cmd: str, antes: float = 1800, depois: float = 15) -> tuple[str, str, int | None]:
        alvo = _palavras(cmd)[:10]
        if alvo:
            lo = bisect.bisect_left(self.times, ts - antes)
            hi = bisect.bisect_right(self.times, ts + depois)
            best, best_score, best_i = None, 0.0, None
            for i in range(lo, hi):
                t, ag, ws, _f, _c = self.items[i]
                hit = sum(1 for w in alvo if w in ws) / len(alvo)
                if hit < 0.6:
                    continue
                # desempata pela proximidade no tempo
                score = hit - abs(ts - t) / (antes * 10)
                if score > best_score:
                    best, best_score, best_i = ag, score, i
            if best:
                return best, "comando", best_i
        # sem comando parecido: se só um agente estava ativo nos 10 minutos anteriores, é dele
        ativos = []
        for ag, tss in self.atividade.items():
            i = bisect.bisect_right(tss, ts + 60)
            if i and tss[i - 1] >= ts - 600:
                ativos.append(ag)
        if len(ativos) == 1:
            return ativos[0], "atividade", None
        return "desconhecido", "nenhum", None


# ----------------------------------------------------------------------------
# Headroom
# ----------------------------------------------------------------------------

def scan_headroom() -> dict:
    out = {"eventos": [], "lifetime": {}, "assinatura": None, "ok": False, "erro": None}
    root = PATHS["headroom"]
    ev = root / "savings_events.jsonl"
    if ev.exists():
        for line in ev.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                d = json.loads(line)
            except Exception:
                continue
            ts = parse_ts(d.get("ts"))
            if ts is None:
                continue
            out["eventos"].append({
                "ts": ts,
                "antes": int(d.get("before") or 0),
                "depois": int(d.get("after") or 0),
                "economia": int(d.get("saved") or 0),  # saved já inclui saved_tool_schema
                "usd": float(d.get("cost_usd") or 0),
                "modelo": d.get("model") or "?",
                "cliente": d.get("client") or "?",
                "provedor": d.get("provider") or "?",
                "cache_read": int((d.get("cache") or {}).get("cr") or 0),
            })
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
                # o histórico agregado complementa eventos antigos que não estão no jsonl
                out.setdefault("historico", []).append({
                    "ts": ts,
                    "economia": int(h.get("total_tokens_saved") or 0),
                    "modelo": h.get("model") or "?",
                    "cliente": h.get("agent") or "?",
                    "provedor": h.get("provider") or "?",
                    "usd": float(h.get("compression_savings_usd") or 0),
                })
            out["ok"] = True
        except Exception as e:  # noqa: BLE001
            out["erro"] = str(e)
    ss = root / "subscription_state.json"
    if ss.exists():
        try:
            j = json.loads(ss.read_text(encoding="utf-8"))
            out["assinatura"] = j.get("latest")
        except Exception:
            pass
    return out


# ----------------------------------------------------------------------------
# montagem do snapshot
# ----------------------------------------------------------------------------

def _cliente_headroom(c: str) -> str:
    c = (c or "").lower()
    if "claude" in c:
        return "claude"
    if "codex" in c:
        return "codex"
    if "opencode" in c:
        return "opencode"
    if "ollama" in c:
        return "ollama"
    return "desconhecido"


def collect(progress=lambda msg: None) -> dict:
    t0 = time.time()
    precos = load_precos()
    precos_mod.atualizar_em_segundo_plano()  # baixa as tabelas se tiverem mais de 7 dias
    with _cache_lock:
        cache = load_cache()
        progress("Lendo Claude Code…")
        scan_claude(cache, progress)
        progress("Lendo Codex…")
        scan_codex(cache, progress)
        save_cache(cache)
    progress("Lendo OpenCode, Ollama, RTK e Headroom…")
    oc = scan_opencode()
    ol = scan_ollama()
    rtk = scan_rtk()
    hr = scan_headroom()

    # --- uso por hora: (hora, agente, modelo) -> métricas
    uso_hora: dict[tuple, dict] = defaultdict(lambda: defaultdict(float))
    uso_proj: dict[tuple, dict] = defaultdict(lambda: defaultdict(float))
    sessoes: dict[tuple, dict] = {}
    ferramentas: dict[str, dict] = {"claude": defaultdict(int), "codex": defaultdict(int), "opencode": defaultdict(int)}
    cmd_index = CmdIndex()
    projetos_vistos: set[str] = set()
    cabecas: dict[str, dict] = {"claude": defaultdict(int), "codex": defaultdict(int), "opencode": defaultdict(int)}
    # por pasta de projeto: ferramentas chamadas e programas rodados no shell (para as
    # ferramentas de economia que não registram quanto economizam: onde e quanto foram usadas)
    ferr_pasta: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    cab_pasta: dict[str, dict] = defaultdict(lambda: defaultdict(int))

    # atividade por hora e agente: chamadas de ferramenta, de espera e comandos de shell
    atividade: dict[tuple, dict] = defaultdict(lambda: defaultdict(float))

    def conta_cmd(ag, c, ts=None, pasta=""):
        if ts:
            atividade[(hour_key(ts), ag)]["shell"] += 1
        for seg in re.split(r"&&|\|\||;|\|", c):
            w = seg.strip().split()
            if not w or w[0].lower() == "cd":
                continue
            cab = w[0].strip("&'\"").lower()[:30]
            cabecas[ag][cab] += 1
            if pasta:
                cab_pasta[pasta][re.sub(r"\.(exe|cmd|bat)$", "", cab.replace("\\", "/").rsplit("/", 1)[-1])] += 1
            break

    def pasta_principal(cwds) -> str:
        """Pasta onde a sessão mais trabalhou (uma sessão quase sempre fica num projeto só)."""
        cont = defaultdict(int)
        for c in cwds:
            if c:
                cont[norm_path(c)] += 1
        return max(cont, key=cont.get) if cont else ""

    def add(ag, ts, model, inp, out_, cr, cw, reasoning, cwd, sess, usd=None, sub=0, cw1h=0):
        h = hour_key(ts)
        cmd_index.ativo(ts, ag)
        u = {"input": inp, "output": out_, "cache_read": cr, "cache_write": cw, "cache_write_1h": cw1h}
        cost = usd if usd is not None else custo_usd(model, u, precos)
        k = (h, ag, model)
        r = uso_hora[k]
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
            r["sem_preco"] += inp + out_ + cr + cw
        proj = projeto_nome(cwd)
        if cwd:
            projetos_vistos.add(norm_path(cwd))
        pk = (h[:10], ag, proj)
        p = uso_proj[pk]
        p["msgs"] += 1
        p["tokens"] += inp + out_ + cr + cw
        p["input"] += inp
        p["output"] += out_
        if cost is not None:
            p["usd"] += cost
        if sess:
            sk = (ag, sess)
            s = sessoes.get(sk)
            if s is None:
                s = sessoes[sk] = {"agente": ag, "id": sess, "projeto": proj, "pasta": norm_path(cwd), "inicio": ts, "fim": ts,
                                   "msgs": 0, "tokens": 0, "input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "usd": 0.0, "modelos": {}}
            s["inicio"] = min(s["inicio"], ts)
            s["fim"] = max(s["fim"], ts)
            s["msgs"] += 1
            s["tokens"] += inp + out_ + cr + cw
            s["input"] += inp
            s["output"] += out_
            s["cache_read"] += cr
            s["cache_write"] += cw
            s["usd"] += cost or 0
            s["modelos"][model] = s["modelos"].get(model, 0) + 1

    # Claude Code
    for key, e in cache["files"].items():
        if not key.startswith("claude:"):
            continue
        for rec in (e.get("msgs") or {}).values():
            ts, model, inp, out_, cr, cw, cw1h, cwd, sess, sub = rec
            add("claude", ts, model, inp, out_, cr, cw, 0, cwd, sess, sub=sub, cw1h=cw1h)
        pasta = pasta_principal(rec[7] for rec in (e.get("msgs") or {}).values())
        for n, c in (e.get("tools") or {}).items():
            ferramentas["claude"][n] += c
            if pasta:
                ferr_pasta[pasta][n] += c
        for h, (tot, esp) in (e.get("tools_h") or {}).items():
            atividade[(h, "claude")]["ferramentas"] += tot
            atividade[(h, "claude")]["espera"] += esp
        for ts, c, *ferr in e.get("cmds") or []:
            cmd_index.add(ts, "claude", c, "log-ps" if ferr and ferr[0] == "ps" else "log")
            conta_cmd("claude", c, ts, pasta)

    # Codex
    limites_codex = []
    for key, e in cache["files"].items():
        if not key.startswith("codex:"):
            continue
        meta = e.get("meta") or {}
        for ts, model, inp, out_, cr, reasoning in e.get("turns") or []:
            add("codex", ts, model, inp, out_, cr, 0, reasoning, meta.get("cwd", ""), meta.get("session", ""))
        limites_codex += e.get("limits") or []
        pasta = norm_path(meta.get("cwd", ""))
        for n, c in (e.get("tools") or {}).items():
            ferramentas["codex"][n] += c
            if pasta:
                ferr_pasta[pasta][n] += c
        for h, (tot, esp) in (e.get("tools_h") or {}).items():
            atividade[(h, "codex")]["ferramentas"] += tot
            atividade[(h, "codex")]["espera"] += esp
        for ts, c, *ferr in e.get("cmds") or []:
            cmd_index.add(ts, "codex", c)
            conta_cmd("codex", c, ts, pasta)

    # OpenCode (e Ollama quando usado pelo OpenCode)
    for ts, model, provider, inp, out_, cr, cw, reasoning, cost, cwd, sess in oc["msgs"]:
        if ts is None:
            continue
        ag = "opencode"
        add(ag, ts, model if provider != "ollama" else f"ollama/{model}", inp, out_, cr, cw, reasoning, cwd, sess,
            usd=cost if cost else None)
    for n, c in oc["tools"].items():
        ferramentas["opencode"][n] += c
    for pasta, tl in oc.get("tools_dir", {}).items():
        if pasta:
            for n, c in tl.items():
                ferr_pasta[norm_path(pasta)][n] += c
    for ts, c, *resto in oc["cmds"]:
        cmd_index.add(ts, "opencode", c)
        conta_cmd("opencode", c, ts, norm_path(resto[0]) if resto else "")

    # Hooks do RTK (Claude Code registra session_id + tool_use_id)
    for ts, _sess, tid, raw, _dec in rtk["hooks"]:
        if ts:
            cmd_index.add(ts, _agente_por_tool_id(tid), raw, "hook")
    cmd_index.build()

    # --- RTK: atribui cada comando a um agente
    rtk_hora: dict[tuple, dict] = defaultdict(lambda: defaultdict(float))
    rtk_cmd: dict[tuple, dict] = defaultdict(lambda: defaultdict(float))
    metodo_atrib = defaultdict(int)

    # Preço de entrada do modelo que cada agente usava em cada hora, para dar valor
    # em dólar aos tokens que o RTK tirou do contexto. É uma estimativa mínima:
    # conta só a primeira vez que a saída entraria; nas chamadas seguintes o mesmo
    # texto ainda seria relido do cache.
    peso_h: dict[tuple, list] = defaultdict(lambda: [0.0, 0.0])
    peso_ag: dict[str, list] = defaultdict(lambda: [0.0, 0.0])
    for (h, ag, model), v in uso_hora.items():
        p = preco_modelo(model, precos)
        if not p or p.get("input") is None:
            continue
        for alvo in (peso_h[(h, ag)], peso_ag[ag], peso_ag["*"]):
            alvo[0] += p["input"] * v["msgs"]
            alvo[1] += v["msgs"]

    def preco_entrada(h: str, ag: str) -> float | None:
        for alvo in (peso_h.get((h, ag)), peso_ag.get(ag), peso_ag.get("*") if ag == "desconhecido" else None):
            if alvo and alvo[1]:
                return alvo[0] / alvo[1]
        return None

    # Estimativa com releituras: a saída de um comando fica no histórico e é relida do
    # cache em cada chamada seguinte da sessão. Para cada comando, acha a sessão do
    # agente que estava ativa e estima quantas chamadas ainda vieram depois.
    sess_por_hora: dict[tuple, list] = defaultdict(list)
    for (ag_s, _sid), sv in sessoes.items():
        if sv["msgs"] < 2 or sv["fim"] <= sv["inicio"]:
            continue
        modelo_s = max(sv["modelos"], key=sv["modelos"].get)
        p_s = preco_modelo(modelo_s) or {}
        cr_s = p_s.get("cache_read")
        if cr_s is None and p_s.get("input") is not None:
            cr_s = p_s["input"] * 0.1
        cw_s = p_s.get("cache_write")
        if cw_s is None and p_s.get("input") is not None:
            cw_s = p_s["input"] * 1.25
        # quanto um token dura no contexto: o contexto cresce em média `novo` tokens por
        # chamada e, em média, tem `ctx` tokens; um token novo fica por volta de ctx/novo
        # chamadas até a compactação ou o fim da conversa tirá-lo de lá
        ctx = (sv["input"] + sv["cache_read"] + sv["cache_write"]) / sv["msgs"]
        novo = max((sv["input"] + sv["cache_write"] + sv["output"]) / sv["msgs"], 1)
        vida = ctx / novo
        item = (sv["inicio"], sv["fim"], sv["msgs"], sv["pasta"].lower(), cr_s, cw_s, vida)
        t_h = int(sv["inicio"] // 3600)
        while t_h <= int(sv["fim"] // 3600):
            sess_por_hora[(t_h, ag_s)].append(item)
            t_h += 1

    def releituras(ts: float, ag: str, pasta: str):
        """(chamadas restantes estimadas, preço de leitura do cache, preço de escrita) ou None."""
        cands = [x for x in sess_por_hora.get((int(ts // 3600), ag), ()) if x[0] <= ts <= x[1]]
        if not cands:
            return None
        pasta = norm_path(pasta).lower()
        mesmo = [x for x in cands if pasta and x[3] and (pasta.startswith(x[3]) or x[3].startswith(pasta))]
        ini, fim, msgs, _p, cr_s, cw_s, vida = max(mesmo or cands, key=lambda x: x[2])
        if cr_s is None:
            return None
        return min(msgs * (fim - ts) / (fim - ini), vida), cr_s, cw_s

    cobertos: set[int] = set()
    for ts, orig, rtk_c, inp, out_, saved, ms, proj in rtk["rows"]:
        ag, metodo, idx = cmd_index.find(ts, orig)
        # cobertura: quantos comandos distintos do agente passaram pelo RTK (um comando
        # composto vira várias linhas no RTK e não pode contar mais de uma vez)
        if idx is not None and idx not in cobertos:
            cobertos.add(idx)
            atividade[(hour_key(cmd_index.items[idx][0]), cmd_index.items[idx][1])]["shell_rtk"] += 1
        if ag == "desconhecido" and "\\temp\\claude\\" in (proj or "").lower():
            ag, metodo = "claude", "pasta"
        metodo_atrib[metodo] += 1
        h = hour_key(ts)
        r = rtk_hora[(h, ag)]
        # mesma regra do `rtk gain`: acima de 7.500 tokens o agente nunca leria a
        # saída inteira (limite de 30 mil caracteres do Bash), então não conta
        if inp > 7500:
            r["grandes"] += 1
            continue
        saved = max(saved, 0)
        r["cmds"] += 1
        r["input"] += inp
        r["output"] += out_
        r["saved"] += saved
        r["ms"] += ms
        pin = preco_entrada(h, ag)
        usd_rtk = saved * pin / 1_000_000 if pin is not None else None
        if usd_rtk is None:
            r["sem_preco"] += saved
        else:
            r["usd"] += usd_rtk
        rel = releituras(ts, ag, proj) if saved else None
        if rel:
            restantes, cr_s, cw_s = rel
            usd_est = saved * ((cw_s or pin or 0) + restantes * cr_s) / 1_000_000
            r["usd_est"] += usd_est
            r["releituras"] += restantes * saved
        else:
            usd_est = usd_rtk or 0
            r["usd_est"] += usd_est
        base = (rtk_c or orig).split()
        nome = " ".join(base[:2]) if base and base[0] == "rtk" else (base[0] if base else "?")
        if nome.startswith("rtk ") and len(base) > 2 and base[1] in ("git", "cargo", "npm", "pnpm", "go", "docker", "gh", "kubectl"):
            nome = " ".join(base[:3])
        c = rtk_cmd[(h[:10], nome)]
        c["cmds"] += 1
        c["input"] += inp
        c["saved"] += saved
        c["usd"] += usd_rtk or 0
        c["usd_est"] += usd_est
        if saved <= 0:
            c["zero"] += 1

    # cobertura do RTK sobre os comandos que ele sabe filtrar
    #  - Claude Code (Bash): o hook registra cada comando e se o reescreveu
    #  - Claude Code (PowerShell), Codex e OpenCode: comandos do log que casaram com o RTK
    cobertura = {"por_comando": defaultdict(lambda: [0, 0])}
    for ts, _sess, tid, raw, dec in rtk["hooks"]:
        cab = cabeca_cmd(raw)
        if ts and cab in RTK_FILTRA:
            a = atividade[(hour_key(ts), _agente_por_tool_id(tid))]
            a["sup"] += 1
            cobertura["por_comando"][cab][0] += 1
            if dec in ("defer", "ask"):
                a["sup_rtk"] += 1
                cobertura["por_comando"][cab][1] += 1
    for i, (ts, ag, _ws, fonte, cab) in enumerate(cmd_index.items):
        if fonte == "hook" or (ag == "claude" and fonte == "log"):
            continue
        if cab in RTK_FILTRA or cab in PS_EQUIVALENTE:
            a = atividade[(hour_key(ts), ag)]
            a["sup"] += 1
            cobertura["por_comando"][cab][0] += 1
            if i in cobertos:
                a["sup_rtk"] += 1
                cobertura["por_comando"][cab][1] += 1
    cobertura["por_comando"] = dict(sorted(((k, v) for k, v in cobertura["por_comando"].items() if v[0] - v[1] > 0),
                                           key=lambda x: -(x[1][0] - x[1][1]))[:12])

    # --- Outras ferramentas de economia: detecta o que existe nesta máquina e lê a economia
    # das que registram. Mesma conta em dólar do RTK (mínimo e estimativa com releituras).
    uso_mcp: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for ag_f, tl in ferramentas.items():
        for nome_f, n in tl.items():
            m = re.match(r"mcp(?:__|:)([^_.][^.]*?)(?:__|\.)", nome_f)
            if m:
                uso_mcp[m.group(1).lower()][ag_f] += n
    try:
        detectadas = economia_mod.detectar(sinais_mod.coletar(), uso_mcp)
    except Exception:  # noqa: BLE001
        detectadas = []
    try:
        mcp_proj = sinais_mod.mcp_por_projeto(projetos_vistos)
    except Exception:  # noqa: BLE001
        mcp_proj = {}
    for f in detectadas:
        try:
            f["projetos"] = economia_mod.por_projeto(f["id"], ferr_pasta, cab_pasta, projetos_vistos, mcp_proj, projeto_nome)
        except Exception:  # noqa: BLE001
            f["projetos"] = []
    eco_hora: dict[tuple, dict] = defaultdict(lambda: defaultdict(float))
    for f in detectadas:
        f["medida"] = f["medicao"] in ("rtk", "headroom")
        if f["medicao"] == "kompact":
            f["ao_vivo"] = economia_mod.ler_kompact()
            f["medida"] = bool(f["ao_vivo"])
            continue
        evs = economia_mod.eventos(f["id"], f["medicao"])
        if not evs:
            continue
        f["medida"] = True
        for e in evs:
            ag_e = e["agente"]
            h_e = hour_key(e["ts"])
            pin_e = preco_entrada(h_e, ag_e)
            usd_min = e["poupados"] * pin_e / 1_000_000 if pin_e is not None else 0.0
            rel_e = releituras(e["ts"], ag_e, e.get("pasta") or "")
            usd_est = e["poupados"] * ((rel_e[2] or pin_e or 0) + rel_e[0] * rel_e[1]) / 1_000_000 if rel_e else usd_min
            if e.get("usd_ferramenta") is not None:  # a própria ferramenta calculou o valor
                usd_min = usd_est = e["usd_ferramenta"]
            r_e = eco_hora[(h_e, ag_e, f["id"])]
            r_e["saved"] += e["poupados"]
            r_e["eventos"] += 1
            r_e["usd"] += usd_min
            r_e["usd_est"] += usd_est

    falhas = defaultdict(int)
    for ts, raw, err, ok in rtk["falhas"]:
        base = (raw or "").split()
        falhas[base[0] if base else "?"] += 1

    decisoes = defaultdict(int)
    for ts, _s, tid, raw, dec in rtk["hooks"]:
        decisoes[dec] += 1

    # --- Headroom
    hr_eventos = hr["eventos"]
    hr_hora = defaultdict(lambda: defaultdict(float))
    vistos_ts = {round(e["ts"]) for e in hr_eventos}
    todos = list(hr_eventos) + [h for h in hr.get("historico", []) if round(h["ts"]) not in vistos_ts]
    for e in todos:
        ag = _cliente_headroom(e["cliente"])
        r = hr_hora[(hour_key(e["ts"]), ag, e["modelo"])]
        r["reqs"] += 1
        r["saved"] += e["economia"]
        if e.get("antes"):
            r["antes"] += e["antes"]
            r["saved_medido"] += e["economia"]
        r["usd"] += e.get("usd", 0)

    # --- Ollama
    ol_hora = defaultdict(lambda: defaultdict(float))
    for ts, endpoint, status, dur in ol["reqs"]:
        r = ol_hora[(hour_key(ts), endpoint)]
        r["reqs"] += 1
        r["segundos"] += dur
        if status >= 400:
            r["erros"] += 1

    # --- Graphify: projetos com grafo e chamadas
    graphify = {"projetos": [], "chamadas": {}}
    for p in sorted(projetos_vistos):
        if p and os.path.exists(os.path.join(p, "graphify-out", "graph.json")):
            try:
                tam = os.path.getsize(os.path.join(p, "graphify-out", "graph.json"))
            except OSError:
                tam = 0
            if any(x["bytes"] == tam and x["nome"] == projeto_nome(p) for x in graphify["projetos"]):
                continue  # mesma pasta vista por outro caminho
            graphify["projetos"].append({"pasta": p, "nome": projeto_nome(p), "bytes": tam,
                                          "atualizado": os.path.getmtime(os.path.join(p, "graphify-out", "graph.json"))})
    for ag, tl in ferramentas.items():
        n = sum(c for name, c in tl.items() if "graphify" in name.lower())
        graphify["chamadas"][ag] = n + cabecas.get(ag, {}).get("graphify", 0)
    graphify["chamadas"]["shell"] = sum(1 for r in rtk["rows"] if r[1].strip().lower().startswith("graphify"))

    # --- Limites do Codex
    limites_codex.sort(key=lambda x: x[0])
    # --- Assinatura Claude (vinda do Headroom, quando ele está rodando)
    assinatura = hr.get("assinatura")
    # --- Limites oficiais do Claude (endpoint de uso da Anthropic) e janelas unificadas
    try:
        claude_api = limites_mod.claude()
    except Exception as e:  # noqa: BLE001
        claude_api = {"ok": False, "erro": type(e).__name__}
    try:
        codex_api = limites_mod.codex()
    except Exception as e:  # noqa: BLE001
        codex_api = {"ok": False, "erro": type(e).__name__}

    def rows(d: dict, cols: list[str]):
        out = []
        for k, v in d.items():
            item = dict(zip(cols, k))
            item.update({kk: (round(vv, 6) if isinstance(vv, float) else vv) for kk, vv in v.items()})
            out.append(item)
        return out

    sess_list = sorted(sessoes.values(), key=lambda s: s["fim"], reverse=True)
    for s in sess_list:
        s["modelo"] = max(s["modelos"], key=s["modelos"].get) if s["modelos"] else "?"
        del s["modelos"]

    snapshot = {
        "gerado_em": time.time(),
        "duracao_coleta_s": round(time.time() - t0, 1),
        "agentes": AGENTES,
        "fontes": {
            "claude": {"ok": PATHS["claude"].exists(), "arquivos": sum(1 for k in cache["files"] if k.startswith("claude:"))},
            "codex": {"ok": PATHS["codex"].exists(), "arquivos": sum(1 for k in cache["files"] if k.startswith("codex:"))},
            "opencode": {"ok": oc["ok"], "erro": oc["erro"], "mensagens": len(oc["msgs"])},
            "ollama": {"ok": ol["ok"], "erro": ol["erro"], "requisicoes": len(ol["reqs"]), "modelos": ol["modelos"]},
            "rtk": {"ok": rtk["ok"], "erro": rtk["erro"], "comandos": len(rtk["rows"])},
            "headroom": {"ok": hr["ok"], "erro": hr["erro"], "eventos": len(todos)},
        },
        "uso": rows(uso_hora, ["hora", "agente", "modelo"]),
        "uso_projetos": rows(uso_proj, ["dia", "agente", "projeto"]),
        "sessoes": sess_list[:400],
        "rtk": {
            "hora": rows(rtk_hora, ["hora", "agente"]),
            "atividade": rows(atividade, ["hora", "agente"]),
            "comandos": rows(rtk_cmd, ["dia", "comando"]),
            "falhas": sorted(([k, v] for k, v in falhas.items()), key=lambda x: -x[1])[:15],
            "falhas_total": len(rtk["falhas"]),
            "decisoes_hook": dict(decisoes),
            "atribuicao": dict(metodo_atrib),
            "cobertura": cobertura,
        },
        "headroom": {
            "hora": rows(hr_hora, ["hora", "agente", "modelo"]),
            "lifetime": hr["lifetime"],
        },
        "ollama": {"hora": rows(ol_hora, ["hora", "endpoint"]), "modelos": ol["modelos"], "carregados": ol.get("carregados", [])},
        "ferramentas": {ag: dict(sorted(tl.items(), key=lambda x: -x[1])[:40]) for ag, tl in ferramentas.items()},
        "limites": {
            "codex": [
                {"ts": l[0], "p5h": l[1], "janela_min": l[2], "reset_5h": l[3], "psemana": l[4], "reset_semana": l[6], "plano": l[7]}
                for l in limites_codex
            ][-3000:],
            "claude": assinatura,
            "claude_api": claude_api,
            "codex_api": codex_api,
        },
        "graphify": graphify,
        "economia": {"ferramentas": detectadas, "hora": rows(eco_hora, ["hora", "agente", "ferramenta"])},
        "comandos_shell": {ag: dict(sorted(v.items(), key=lambda x: -x[1])[:15]) for ag, v in cabecas.items()},
        "precos": {
            "fontes": precos_mod.info(),
            "sem_preco": sorted({m for (_h, _a, m) in uso_hora if m not in ("?", "") and not preco_modelo(m)}),
            "por_modelo": {m: dict(zip(("preco", "fonte"), precos_mod.preco(m))) for m in sorted({m for (_h, _a, m) in uso_hora})},
        },
    }
    snapshot["limites"]["janelas"] = limites_mod.janelas(snapshot["limites"]["codex"], claude_api, codex_api)
    return snapshot


if __name__ == "__main__":
    import sys

    snap = collect(lambda m: print(m, file=sys.stderr))
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in snap.items() if k in ("uso", "uso_projetos", "sessoes")}))
    print("fontes:", json.dumps(snap["fontes"], ensure_ascii=False))
    print("coleta em", snap["duracao_coleta_s"], "s")
