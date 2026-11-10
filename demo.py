"""Demo mode: the dashboard with realistic but entirely fictional data.

    python server.py --demo            (opens on port 8766)

Used for the README screenshots and by contributors who have no agent history.

How it works: instead of faking the dashboard's output, it writes fictional SOURCE data
(the same files the agents and token-saving tools write) into a fake home folder, points
every path the app reads at it and lets the real collector read it. So the whole pipeline
runs, and none of the machine owner's data can show up:

  .cache-demo/home     fake user folder: ~/.claude, ~/.codex, opencode.db, Ollama logs,
                       RTK history.db, Headroom, Context Mode, agent configs, projects
  .cache-demo/cache    the app's data folder in demo mode (the real .cache/ is never used)

  - USERPROFILE, HOME, APPDATA, LOCALAPPDATA, CODEX_HOME and CLAUDE_CONFIG_DIR point into the
    fake home; the XDG_* and per-tool variables (CONTEXT_MODE_DATA_DIR, SQUEEZ_DIR…) are removed.
  - PATH holds only the fake home's bin folder, with do-nothing stubs for the programs the
    demo pretends are installed (the real installed tools are not seen).
  - The official Claude and Codex usage endpoints are never called: limits.py asks
    claude_usage() / codex_usage() below for an answer in the same format, computed from the
    fictional activity. Prices are not downloaded (the public tables already in .cache/ are
    copied, or default_prices.json is used). The Analyze button runs no AI; a previous
    analysis comes seeded.
  - Paths shown in the dashboard are rewritten from the fake home to C:\\Users\\dev (mask()).

Everything is generated again at each start, seeded (same shape every time) and relative
to the current time. The folder is in .gitignore.
"""
from __future__ import annotations

import bisect
import datetime as dt
import json
import os
import random
import re
import shutil
import sqlite3
import time
import uuid
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("TOKEN_ECONOMY_DEMO_DIR") or BASE / ".cache-demo")
HOME = ROOT / "home"
CACHE = ROOT / "cache"
BIN = HOME / ".local" / "bin"
MARKER = ROOT / ".token-economy-demo"
STATE = ROOT / "limits_state.json"
PORT = 8766
SHOWN_HOME = "C:\\Users\\dev"  # how the fake home appears on screen
CLAUDE_PLAN = "Max"
SEED = 20261110
DAYS = 30

# variables that would point a reader somewhere outside the fake home
CLEARED_ENV = (
    "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME",
    "CLAUDE_CODE_OAUTH_TOKEN", "TOKEN_SAVER_DB_DIR", "SQUEEZ_DIR", "CONTEXT_MODE_DATA_DIR",
    "CAVEMAN_DB", "CAVEMAN_HOME", "CODE_INDEX_PATH", "LEAN_CTX_STATE_DIR",
    "TOKEN_OPTIMIZER_SNAPSHOT_DIR", "KOMPACT_PORT", "HOMEDRIVE", "HOMEPATH",
)

# fictional projects: (name, stack, has a Graphify graph)
PROJECTS = [
    ("acme-storefront", "ts", True),
    ("billing-api", "go", True),
    ("mobile-app", "rn", False),
    ("data-pipeline", "py", True),
    ("docs-site", "docs", False),
]
PROJECT_WEIGHT = [0.34, 0.24, 0.16, 0.18, 0.08]

COMMANDS = {
    "ts": ["git status", "git diff", "git diff --stat", "git log --oneline -15", "npm test", "npm run build", "npm run lint",
           "npx tsc --noEmit", "npx vitest run src/cart", "ls src/components", "cat package.json", "grep -rn \"useCart\" src",
           "rg \"checkout\" src --type ts", "find src -name \"*.test.ts\"", "npx eslint src --fix", "git add -A", "pnpm install"],
    "go": ["git status", "git diff", "go test ./...", "go test ./internal/invoice -run TestProration", "go build ./...",
           "go vet ./...", "golangci-lint run", "git log --oneline -10", "ls internal", "cat go.mod", "grep -rn \"func (s *Service)\" internal",
           "rg \"stripe\" --type go", "docker compose up -d db", "curl -s localhost:8080/healthz", "git add -A"],
    "rn": ["git status", "git diff", "npm test -- --watch=false", "npx tsc --noEmit", "ls app/screens", "cat app.json",
           "grep -rn \"useNavigation\" app", "npx eslint app", "git log --oneline -10", "npx expo-doctor"],
    "py": ["git status", "git diff", "pytest -q", "pytest tests/test_transform.py -q", "ruff check .", "mypy pipeline",
           "pip list", "ls pipeline", "cat pyproject.toml", "grep -rn \"def run\" pipeline", "python -m pipeline.cli --dry-run",
           "git log --oneline -10", "docker build -t pipeline ."],
    "docs": ["git status", "git diff", "npm run build", "ls src/content/docs", "grep -rn \"TODO\" src/content", "cat astro.config.mjs",
             "npx markdownlint \"**/*.md\"", "git log --oneline -5"],
}
GRAPHIFY_QUESTIONS = ["where is the checkout total computed", "what calls the invoice service", "how does retry work",
                      "where are webhooks handled", "which modules read the config", "how is auth wired"]
PS_COMMANDS = ["Get-Content .env.example", "Get-ChildItem src -Recurse -Filter *.ts", "Select-String -Path src\\*.ts -Pattern TODO",
               "Get-Content package.json"]

CLAUDE_TOOLS = [("Read", 24), ("Bash", 22), ("Edit", 14), ("Grep", 9), ("Glob", 5), ("Write", 4), ("TodoWrite", 4),
                ("mcp__context-mode__ctx_execute", 5), ("mcp__context-mode__ctx_search", 2), ("Agent", 3), ("WebSearch", 1),
                ("WebFetch", 1), ("PowerShell", 3), ("BashOutput", 2), ("Skill:graphify", 1)]
CODEX_TOOLS = [("exec_command", 62), ("apply_patch", 22), ("update_plan", 8), ("view_image", 1), ("write_stdin", 3)]

# relative weight of each model's tokens in the plan limits (for the fictional windows only)
LIMIT_WEIGHT = {"claude-opus-5-5": 1.0, "claude-sonnet-5-5": 0.5, "claude-haiku-5-5": 0.15, "gpt-6.1-sol": 1.0, "gpt-6.1-terra": 0.5}


# ----------------------------------------------------------------------------
# entry point
# ----------------------------------------------------------------------------

def setup() -> None:
    """Builds the fake home and points the whole app at it. Must run before the other
    modules are imported (they read the paths when they load)."""
    real_cache = Path(os.environ.get("TOKEN_ECONOMY_CACHE") or BASE / ".cache")
    _reset_folder()
    _set_env()
    generate(time.time(), real_cache)


def _reset_folder() -> None:
    if ROOT.exists():
        if not MARKER.exists():
            raise SystemExit(f"{ROOT} exists and is not a demo folder; not touching it")
        shutil.rmtree(ROOT)
    for p in (HOME, CACHE, BIN):
        p.mkdir(parents=True, exist_ok=True)
    MARKER.write_text("Generated by `python server.py --demo`. Safe to delete.\n", encoding="utf-8")


def _set_env() -> None:
    env = os.environ
    for k in CLEARED_ENV:
        env.pop(k, None)
    env.update({
        "TOKEN_ECONOMY_DEMO": "1",
        "TOKEN_ECONOMY_DEMO_DIR": str(ROOT),
        "TOKEN_ECONOMY_CACHE": str(CACHE),
        "USERPROFILE": str(HOME),
        "HOME": str(HOME),
        "APPDATA": str(HOME / "AppData" / "Roaming"),
        "LOCALAPPDATA": str(HOME / "AppData" / "Local"),
        "CODEX_HOME": str(HOME / ".codex"),
        "CLAUDE_CONFIG_DIR": str(HOME / ".claude"),
        "PATH": str(BIN),
        # Windows: shutil.which must not look in the current folder either
        "NoDefaultCurrentDirectoryInExePath": "1",
    })


# ----------------------------------------------------------------------------
# fictional limits: the answers of the official usage endpoints
# ----------------------------------------------------------------------------

_state: dict | None = None


def _load_state() -> dict:
    global _state
    if _state is None:
        _state = json.loads(STATE.read_text(encoding="utf-8"))
    return _state


def _pct_at(win: dict, ts: float) -> tuple[float, float | None]:
    """(% used, reset) of a simulated window at time ts; (0, None) when none is in progress."""
    i = bisect.bisect_right(win["starts"], ts) - 1
    if i < 0 or ts >= win["periods"][i][1]:
        return 0.0, None
    start, reset = win["periods"][i]

    def cum(t):  # weight of the requests up to t (inclusive)
        j = bisect.bisect_right(win["t"], t)
        return win["cum"][j - 1] if j else 0.0

    used = cum(ts) - cum(start - 1e-6)
    return round(min(100.0, 100 * used / win["budget"]), 1), reset


def _iso(ts: float | None) -> str | None:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat() if ts else None


def claude_usage(now: float) -> dict:
    """Same format as GET api.anthropic.com/api/oauth/usage."""
    st = _load_state()["claude"]
    out = {}
    for key in ("five_hour", "seven_day", "seven_day_sonnet"):
        pct, reset = _pct_at(st[key], now)
        out[key] = {"utilization": pct, "resets_at": _iso(reset)}
    pct, reset = _pct_at(st["opus"], now)
    out["limits"] = [{"kind": "weekly_scoped", "scope": {"model": {"display_name": "Opus"}}, "percent": pct, "resets_at": _iso(reset)}]
    out["extra_usage"] = {"is_enabled": True, "monthly_limit": 5000, "used_credits": 1240, "utilization": 24.8,
                          "currency": "USD", "decimal_places": 2}
    return out


def codex_usage(now: float) -> dict:
    """Same format as GET chatgpt.com/backend-api/wham/usage."""
    st = _load_state()["codex"]
    rl = {}
    for key, sim in (("primary_window", st["five_hour"]), ("secondary_window", st["seven_day"])):
        pct, reset = _pct_at(sim, now)
        rl[key] = {"used_percent": pct, "limit_window_seconds": int(sim["duration_h"] * 3600), "reset_at": reset}
    return {"plan_type": "plus", "rate_limit": rl}


def ollama_models() -> tuple[list[dict], list[str]]:
    """What `ollama list` and `ollama ps` would print, already parsed."""
    return ([{"name": "qwen3-coder:30b", "size": "18 GB"}, {"name": "llama3.2:3b", "size": "2.0 GB"},
             {"name": "nomic-embed-text:latest", "size": "274 MB"}], ["qwen3-coder:30b"])


# ----------------------------------------------------------------------------
# display: the fake home is shown as C:\Users\dev
# ----------------------------------------------------------------------------

_MASK: list[tuple[re.Pattern, str]] | None = None


def _mask_rules() -> list[tuple[re.Pattern, str]]:
    global _MASK
    if _MASK is None:
        rules = []
        for real, shown in ((HOME, SHOWN_HOME), (ROOT, SHOWN_HOME + "\\.token-economy-demo"), (BASE, "token-economy")):
            for r in (str(real), str(real).replace("\\", "/")):
                s = shown if "\\" in r else shown.replace("\\", "/")
                forms = {(r, s), (json.dumps(r, ensure_ascii=False)[1:-1], json.dumps(s)[1:-1]), (json.dumps(r)[1:-1], json.dumps(s)[1:-1])}
                rules += [(re.compile(re.escape(a), re.I), b) for a, b in forms]
        _MASK = rules
    return _MASK


def mask(text: str) -> str:
    for rx, shown in _mask_rules():
        text = rx.sub(lambda _m, s=shown: s, text)
    return text


# ----------------------------------------------------------------------------
# generation
# ----------------------------------------------------------------------------

class Gen:
    def __init__(self, now: float):
        self.now = now
        self.rng = random.Random(SEED)
        self.claude_events: list[tuple[float, str, float]] = []  # (ts, model, limit weight)
        self.codex_events: list[tuple[float, str, float]] = []
        self.rtk_rows: list[tuple] = []
        self.hooks: list[tuple] = []
        self.cm_events: list[tuple] = []  # context mode
        self.headroom: list[dict] = []
        self.ollama_reqs: list[tuple[float, str, float]] = []
        self.oc_sessions: list[tuple] = []

    # ---- helpers
    def hexid(self, n: int) -> str:
        return "".join(self.rng.choice("0123456789abcdef") for _ in range(n))

    def b62(self, n: int) -> str:
        return "".join(self.rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789") for _ in range(n))

    def uid(self) -> str:
        return str(uuid.UUID(int=self.rng.getrandbits(128), version=4))

    def pick(self, items):
        return self.rng.choices([x for x, _ in items], [w for _, w in items])[0]

    def project(self):
        return self.rng.choices(PROJECTS, PROJECT_WEIGHT)[0]

    def calls_in_session(self) -> int:
        r = self.rng.random()
        if r < 0.40:
            return self.rng.randint(12, 60)
        if r < 0.76:
            return self.rng.randint(60, 150)
        if r < 0.88:
            return self.rng.randint(150, 250)
        return self.rng.randint(270, 560)

    def times(self, start: float, n: int, stop: float) -> list[float]:
        out, t = [], start
        for _ in range(n):
            t += self.rng.uniform(6, 70) + (self.rng.uniform(120, 900) if self.rng.random() < 0.06 else 0)
            if t >= stop:
                break
            out.append(t)
        return out

    def command(self, stack: str, graph: bool) -> str:
        if graph and self.rng.random() < 0.07:
            return f'graphify query "{self.rng.choice(GRAPHIFY_QUESTIONS)}"'
        return self.rng.choice(COMMANDS[stack])

    # ---- RTK: what it records when a command goes through it
    def rtk(self, ts: float, cmd: str, folder: str, agent: str):
        head = cmd.split()[0]
        if head == "graphify":
            return
        big = {"npm": 2600, "pnpm": 3000, "go": 1800, "pytest": 2200, "cargo": 3000, "npx": 1500, "docker": 1400,
               "golangci-lint": 1600, "ruff": 900, "mypy": 800, "git": 900, "grep": 1300, "rg": 1300, "find": 700,
               "cat": 900, "ls": 260, "curl": 500, "pip": 1100}.get(head, 600)
        inp = int(big * self.rng.lognormvariate(0, 0.7))
        if self.rng.random() < 0.015:
            inp = self.rng.randint(8000, 30000)  # huge output: RTK does not count it
        ratio = 0.0 if head in ("ls", "curl") and self.rng.random() < 0.5 else self.rng.uniform(0.55, 0.93)
        saved = int(inp * ratio)
        sub = cmd.split()
        rtk_cmd = "rtk " + " ".join(sub)
        self.rtk_rows.append((ts + self.rng.uniform(0.5, 6), cmd, rtk_cmd, inp, inp - saved, saved,
                              round(100 * saved / inp, 1) if inp else 0.0, self.rng.randint(40, 2500), folder, agent))

    # ---- Claude Code
    def claude_session(self, start: float, stop: float, n: int | None = None, proj=None, sub_of: tuple | None = None):
        name, stack, graph = proj or self.project()
        folder = str(HOME / "code" / name)
        sid = self.uid()
        n = n or self.calls_in_session()
        ts_list = self.times(start, n, stop)
        if not ts_list:
            return
        model = "claude-haiku-5-5" if sub_of else ("claude-opus-5-5" if self.rng.random() < 0.72 else "claude-sonnet-5-5")
        slug = re.sub(r"[^A-Za-z0-9]", "-", folder)
        if sub_of:
            path = HOME / ".claude" / "projects" / slug / sub_of[0] / "subagents" / f"agent-{self.hexid(16)}.jsonl"
            sid = sub_of[0]
        else:
            path = HOME / ".claude" / "projects" / slug / f"{sid}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        ctx = self.rng.randint(18000, 30000)
        lines = []
        parent = None
        for ts in ts_list:
            new = int(self.rng.lognormvariate(8.0, 0.8))  # tokens added to the context in this call
            out = int(self.rng.lognormvariate(6.4, 0.8))
            if ctx > 150000 and self.rng.random() < 0.5:
                ctx = self.rng.randint(30000, 45000)  # compaction
            usage = {"input_tokens": self.rng.randint(1, 8), "cache_creation_input_tokens": new, "cache_read_input_tokens": ctx,
                     "cache_creation": {"ephemeral_5m_input_tokens": new if sub_of else 0, "ephemeral_1h_input_tokens": 0 if sub_of else new},
                     "output_tokens": out, "service_tier": "standard"}
            ctx += new + out
            content = [{"type": "text", "text": "…"}]
            if self.rng.random() < 0.78:
                tool = self.pick(CLAUDE_TOOLS)
                if tool == "Skill:graphify" and not graph:
                    tool = "Read"
                tid = "toolu_" + self.b62(24)
                block = {"type": "tool_use", "id": tid, "name": tool, "input": {}}
                if tool == "Skill:graphify":
                    block.update(name="Skill", input={"skill": "graphify"})
                elif tool == "Bash":
                    cmd = self.command(stack, graph)
                    block["input"] = {"command": cmd, "description": "run " + cmd.split()[0]}
                    self.claude_bash(ts, cmd, folder, sid, tid)
                elif tool == "PowerShell":
                    block["input"] = {"command": self.rng.choice(PS_COMMANDS)}
                elif tool.startswith("mcp__context-mode"):
                    sb = int(self.rng.lognormvariate(10.6, 0.8))
                    self.cm_events.append((ts, "claude-code", folder, tool.split("__")[-1], sb, int(sb * self.rng.uniform(0.02, 0.09))))
                elif tool == "Read":
                    block["input"] = {"file_path": folder + "\\src\\index.ts"}
                content.append(block)
            mid = "msg_" + self.b62(24)
            line = {"parentUuid": parent, "isSidechain": bool(sub_of), "userType": "external", "cwd": folder, "sessionId": sid,
                    "version": "2.9.4", "gitBranch": "main", "type": "assistant", "uuid": self.uid(),
                    "timestamp": dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                    "requestId": "req_" + self.b62(24),
                    "message": {"id": mid, "type": "message", "role": "assistant", "model": model, "content": content,
                                "stop_reason": "tool_use" if len(content) > 1 else "end_turn", "usage": usage}}
            parent = line["uuid"]
            lines.append(json.dumps(line))
            weight = (new * 1.25 + ctx * 0.1 + out * 5) * LIMIT_WEIGHT[model]
            self.claude_events.append((ts, model, weight))
            # Headroom proxies part of the requests (installed 20 days ago)
            if ts > self.now - 20 * 86400 and self.rng.random() < 0.35:
                before = ctx + new
                saved = int(before * self.rng.uniform(0.02, 0.09))
                self.headroom.append({"ts": ts + 0.5, "before": before, "after": before - saved, "saved": saved, "model": model,
                                      "client": "claude-code", "provider": "anthropic", "cr": ctx})
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        # some sessions start helper agents
        if not sub_of and len(ts_list) > 40 and self.rng.random() < 0.45:
            t0 = self.rng.choice(ts_list[: len(ts_list) // 2])
            self.claude_session(t0, stop, self.rng.randint(8, 30), (name, stack, graph), (sid,))

    def claude_bash(self, ts, cmd, folder, sid, tid):
        head = cmd.split()[0]
        filterable = head in ("git", "npm", "npx", "pnpm", "go", "golangci-lint", "pytest", "ruff", "mypy", "pip", "ls", "cat",
                              "grep", "rg", "find", "docker", "curl")
        if not filterable:
            self.hooks.append((ts, sid, tid, folder, cmd, "allow", None))
            return
        r = self.rng.random()
        decision = "defer" if r < 0.74 else "ask" if r < 0.86 else "allow"
        self.hooks.append((ts, sid, tid, folder, cmd, decision, "rtk " + cmd if decision != "allow" else None))
        if decision != "allow":
            self.rtk(ts, cmd, folder, "claude")

    # ---- Codex
    def codex_session(self, start: float, stop: float, n: int | None = None):
        name, stack, graph = self.project()
        folder = str(HOME / "code" / name)
        sid = self.uid()
        model = "gpt-6.1-sol" if self.rng.random() < 0.8 else "gpt-6.1-terra"
        ts_list = self.times(start, n or max(8, self.calls_in_session() // 3), stop)
        if not ts_list:
            return
        local = dt.datetime.fromtimestamp(start)
        path = HOME / ".codex" / "sessions" / local.strftime("%Y/%m/%d") / f"rollout-{local.strftime('%Y-%m-%dT%H-%M-%S')}-{sid}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)

        def stamp(ts):
            return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

        lines = [{"timestamp": stamp(ts_list[0] - 2), "type": "session_meta",
                  "payload": {"id": sid, "timestamp": stamp(ts_list[0] - 2), "cwd": folder, "originator": "codex_cli_rs",
                              "cli_version": "0.98.0", "source": "cli", "model_provider": "openai"}},
                 {"timestamp": stamp(ts_list[0] - 1), "type": "turn_context",
                  "payload": {"cwd": folder, "model": model, "effort": self.rng.choice(["medium", "medium", "high"]),
                              "approval_policy": "on-request", "sandbox_policy": {"mode": "workspace-write"}}}]
        tot = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0, "reasoning_output_tokens": 0, "total_tokens": 0}
        ctx = self.rng.randint(14000, 22000)
        for ts in ts_list:
            tool = self.pick(CODEX_TOOLS)
            args = {}
            if tool == "exec_command":
                cmd = self.command(stack, graph)
                via_rtk = cmd.split()[0] != "graphify" and self.rng.random() < 0.72
                args = {"cmd": ("rtk " + cmd) if via_rtk else cmd, "workdir": folder}
                if via_rtk:
                    self.rtk(ts, cmd, folder, "codex")
            elif tool == "apply_patch":
                args = {"input": "*** Begin Patch\n*** Update File: src/main\n*** End Patch"}
            elif tool == "write_stdin":
                args = {"session_id": 1, "chars": ""}
            lines.append({"timestamp": stamp(ts - 0.4), "type": "response_item",
                          "payload": {"type": "function_call", "name": tool, "arguments": json.dumps(args), "call_id": "call_" + self.b62(24)}})
            new = int(self.rng.lognormvariate(7.9, 0.7))
            if ctx > 180000 and self.rng.random() < 0.5:
                ctx = self.rng.randint(20000, 30000)
            inp = ctx + new
            out = int(self.rng.lognormvariate(6.2, 0.7))
            reasoning = int(out * self.rng.uniform(0.3, 1.6))
            tot["input_tokens"] += inp
            tot["cached_input_tokens"] += ctx
            tot["output_tokens"] += out
            tot["reasoning_output_tokens"] += reasoning
            tot["total_tokens"] += inp + out
            ctx += new + out
            self.codex_events.append((ts, model, (new + ctx * 0.1 + out * 5) * LIMIT_WEIGHT[model]))
            if self.rng.random() < 0.05:
                sb = int(self.rng.lognormvariate(10.2, 0.8))
                self.cm_events.append((ts, "codex", folder, "ctx_execute", sb, int(sb * self.rng.uniform(0.03, 0.1))))
            lines.append({"timestamp": stamp(ts), "type": "event_msg",
                          "payload": {"type": "token_count", "info": {"total_token_usage": dict(tot)}, "rate_limits": None}})
        path.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
        return path

    # ---- OpenCode (local model through Ollama, or Claude through the API)
    def opencode_session(self, start: float, stop: float):
        name, stack, graph = self.project()
        folder = str(HOME / "code" / name)
        local = self.rng.random() < 0.7
        ts_list = self.times(start, self.rng.randint(6, 40), stop)
        if ts_list:
            self.oc_sessions.append(("ses_" + self.b62(26), folder, local, ts_list, stack, graph))


def generate(now: float, real_cache: Path) -> None:
    g = Gen(now)
    rng = g.rng
    today = dt.datetime.fromtimestamp(now).replace(hour=0, minute=0, second=0, microsecond=0)
    codex_files = []
    for k in range(DAYS - 1, -1, -1):
        day = today - dt.timedelta(days=k)
        weekend = day.weekday() >= 5
        ramp = 0.75 + 0.25 * (DAYS - k) / DAYS  # usage grows a bit over the month
        n_claude = max(0, round(rng.gauss(1.6 if weekend else 4.2, 1.0) * ramp))
        n_codex = max(0, round(rng.gauss(0.5 if weekend else 1.7, 0.8)))
        n_oc = 1 if rng.random() < (0.15 if weekend else 0.45) else 0
        for kind, n in (("claude", n_claude), ("codex", n_codex), ("opencode", n_oc)):
            for _ in range(n):
                hour = rng.choice([9, 9, 10, 10, 11, 11, 13, 14, 14, 15, 15, 16, 17, 19, 21, 22])
                start = (day + dt.timedelta(hours=hour, minutes=rng.randint(0, 59))).timestamp()
                if k == 0 and start > now - 4 * 3600:
                    continue  # today: the sessions running now are added below
                if kind == "claude":
                    g.claude_session(start, now - 300)
                elif kind == "codex":
                    p = g.codex_session(start, now - 300)
                    if p:
                        codex_files.append(p)
                else:
                    g.opencode_session(start, now - 300)
    # a few marathon sessions in the last week (they weigh on the score)
    for k, proj in ((2, PROJECTS[0]), (5, PROJECTS[1])):
        start = (today - dt.timedelta(days=k) + dt.timedelta(hours=9, minutes=40)).timestamp()
        g.claude_session(start, now - 300, 380, proj)
    # sessions in progress: the 5 h windows have something now
    g.claude_session(now - 2.7 * 3600, now - 240, 90, PROJECTS[0])
    g.claude_session(now - 1.2 * 3600, now - 600, 60, PROJECTS[1])
    p = g.codex_session(now - 3.4 * 3600, now - 420, 30)
    if p:
        codex_files.append(p)

    state = _simulate_limits(g, now)
    STATE.write_text(json.dumps(state), encoding="utf-8")
    _write_codex_limits(codex_files, state["codex"])
    _write_opencode_and_ollama(g)  # before RTK: OpenCode commands also go through RTK
    _write_rtk(g)
    _write_headroom(g)
    _write_context_mode(g)
    _write_configs()
    _write_projects()
    _write_cache(g, now, state, real_cache)


# ----------------------------------------------------------------------------
# limit windows simulated from the fictional activity
# ----------------------------------------------------------------------------

def _rolling(events, dur_h: float) -> list[list[float]]:
    """5 h windows: one starts at the first request after the previous one ended."""
    periods = []
    for t, _w in events:
        if not periods or t >= periods[-1][1]:
            start = max(t - t % 3600, periods[-1][1] if periods else 0)
            periods.append([start, start + dur_h * 3600])
    return periods


def _fixed(now: float, reset: float, dur_h: float, back_days: int = 40) -> list[list[float]]:
    out, r = [], reset
    while r > now - back_days * 86400:
        out.append([r - dur_h * 3600, r])
        r -= dur_h * 3600
    return sorted(out)


def _budget(events, periods, now: float, target_now: float, quantile: float | None = None, cap: float = 0.85) -> float:
    sums = [sum(w for t, w in events if a <= t < b) for a, b in periods]
    cur = next((s for (a, b), s in zip(periods, sums) if a <= now < b), 0) or max(sums or [1])
    budget = cur / target_now
    past = sorted(s for (a, b), s in zip(periods, sums) if b <= now and s > 0)
    if quantile is not None and past:
        # the busiest past windows hit the cap; the current one stays below it
        budget = max(past[int(len(past) * quantile)], cur / cap)
    return budget or 1.0


def _sim(events, periods, budget, dur_h) -> dict:
    cum, acc = [], 0.0
    for _t, w in events:
        acc += w
        cum.append(round(acc, 1))
    return {"t": [round(t, 1) for t, _w in events], "cum": cum, "periods": periods,
            "starts": [a for a, _b in periods], "budget": budget, "duration_h": dur_h}


def _simulate_limits(g: Gen, now: float) -> dict:
    ce = sorted((t, w) for t, _m, w in g.claude_events if t <= now)
    opus = [(t, w) for t, m, w in sorted(g.claude_events) if "opus" in m and t <= now]
    sonnet = [(t, w) for t, m, w in sorted(g.claude_events) if "sonnet" in m and t <= now]
    xe = sorted((t, w) for t, _m, w in g.codex_events if t <= now)
    week_c = _fixed(now, now + 2.6 * 86400 - now % 3600, 168)
    week_x = _fixed(now, now + 3.2 * 86400 - now % 3600, 168)
    five_c, five_x = _rolling(ce, 5), _rolling(xe, 5)
    return {
        "claude": {
            "five_hour": _sim(ce, five_c, _budget(ce, five_c, now, 0.3, 0.8, cap=0.3), 5),
            "seven_day": _sim(ce, week_c, _budget(ce, week_c, now, 0.71), 168),
            "seven_day_sonnet": _sim(sonnet, week_c, _budget(sonnet, week_c, now, 0.18), 168),
            "opus": _sim(opus, week_c, _budget(opus, week_c, now, 0.58), 168),
        },
        "codex": {
            "five_hour": _sim(xe, five_x, _budget(xe, five_x, now, 0.24, 0.72), 5),
            "seven_day": _sim(xe, week_x, _budget(xe, week_x, now, 0.44), 168),
        },
    }


def _write_codex_limits(files, st: dict) -> None:
    """Puts the rate limits into the token_count events, as Codex does on every turn."""
    for path in files:
        lines = path.read_text(encoding="utf-8").splitlines()
        out = []
        for raw in lines:
            d = json.loads(raw)
            p = d.get("payload") or {}
            if d.get("type") == "event_msg" and p.get("type") == "token_count":
                ts = dt.datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00")).timestamp()
                p5, r5 = _pct_at(st["five_hour"], ts)
                pw, rw = _pct_at(st["seven_day"], ts)
                p["rate_limits"] = {"primary": {"used_percent": p5, "window_minutes": 300, "resets_at": int(r5) if r5 else None},
                                    "secondary": {"used_percent": pw, "window_minutes": 10080, "resets_at": int(rw) if rw else None},
                                    "plan_type": "plus"}
            out.append(json.dumps(d))
        path.write_text("\n".join(out) + "\n", encoding="utf-8")


# ----------------------------------------------------------------------------
# token-saving tools
# ----------------------------------------------------------------------------

def _rfc3339(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "100+00:00"


def _write_rtk(g: Gen) -> None:
    db = HOME / "AppData" / "Local" / "rtk" / "history.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(db)
    c.executescript("""
        CREATE TABLE commands (id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, original_cmd TEXT NOT NULL, rtk_cmd TEXT NOT NULL,
            input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL, saved_tokens INTEGER NOT NULL, savings_pct REAL NOT NULL,
            exec_time_ms INTEGER DEFAULT 0, project_path TEXT);
        CREATE INDEX idx_timestamp ON commands(timestamp);
        CREATE TABLE parse_failures (id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, raw_command TEXT NOT NULL,
            error_message TEXT NOT NULL, fallback_succeeded INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE hook_decisions (id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, session_id TEXT NOT NULL, tool_use_id TEXT NOT NULL,
            project_path TEXT DEFAULT '', raw_cmd TEXT NOT NULL, decision TEXT NOT NULL, rewritten_cmd TEXT, rtk_version TEXT NOT NULL);
    """)
    rows = sorted(g.rtk_rows)
    c.executemany("insert into commands (timestamp, original_cmd, rtk_cmd, input_tokens, output_tokens, saved_tokens, savings_pct, exec_time_ms, project_path) values (?,?,?,?,?,?,?,?,?)",
                  [(_rfc3339(r[0]), *r[1:9]) for r in rows])
    c.executemany("insert into hook_decisions (timestamp, session_id, tool_use_id, project_path, raw_cmd, decision, rewritten_cmd, rtk_version) values (?,?,?,?,?,?,?,?)",
                  [(_rfc3339(h[0]), h[1], h[2], h[3], h[4], h[5], h[6], "0.42.1") for h in sorted(g.hooks)])
    fails = []
    for r in rows:
        if r[1].split()[0] in ("pytest", "go", "npx", "docker") and g.rng.random() < 0.03:
            fails.append((_rfc3339(r[0] + 1), r[1], g.rng.choice(["unexpected output format", "could not parse test summary", "unknown flag"]),
                          1 if g.rng.random() < 0.8 else 0))
    c.executemany("insert into parse_failures (timestamp, raw_command, error_message, fallback_succeeded) values (?,?,?,?)", fails)
    c.commit()
    c.close()


def _write_headroom(g: Gen) -> None:
    root = HOME / ".headroom"
    root.mkdir(parents=True, exist_ok=True)
    price = {"claude-opus-5-5": 4.0, "claude-sonnet-5-5": 2.0, "claude-haiku-5-5": 0.1}
    lines = []
    tot_saved = tot_usd = 0.0
    for e in sorted(g.headroom, key=lambda x: x["ts"]):
        usd = e["saved"] * price[e["model"]] / 1e6
        tot_saved += e["saved"]
        tot_usd += usd
        lines.append(json.dumps({"v": 2, "ts": dt.datetime.fromtimestamp(e["ts"], dt.timezone.utc).isoformat(), "before": e["before"],
                                 "after": e["after"], "saved": e["saved"], "cost_usd": round(usd, 6), "model": e["model"],
                                 "client": e["client"], "source": "proxy", "provider": e["provider"], "cache": {"cr": e["cr"]},
                                 "basis": "list"}))
    (root / "savings_events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (root / "proxy_savings.json").write_text(json.dumps({
        "schema_version": 3,
        "lifetime": {"requests": len(lines), "tokens_saved": int(tot_saved), "compression_savings_usd": round(tot_usd, 2)},
        "history": [],
    }), encoding="utf-8")


def _write_context_mode(g: Gen) -> None:
    by_folder: dict[str, list] = {}
    for e in g.cm_events:
        by_folder.setdefault(e[2], []).append(e)
    for folder, evs in by_folder.items():
        db = HOME / ".context-mode" / "projects" / g.hexid(12) / "context.db"
        db.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(db)
        c.execute("create table events (id integer primary key, created_at integer not null, agent text, worktree text, tool text, "
                  "kind text, sandbox_bytes integer, returned_bytes integer)")
        c.executemany("insert into events (created_at, agent, worktree, tool, kind, sandbox_bytes, returned_bytes) values (?,?,?,?,?,?,?)",
                      [(int(ts * 1000), ag, wt, tool, "tool", sb, rb) for ts, ag, wt, tool, sb, rb in sorted(evs)])
        c.commit()
        c.close()


def _write_opencode_and_ollama(g: Gen) -> None:
    db = HOME / ".local" / "share" / "opencode" / "opencode.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(db)
    c.executescript("""
        CREATE TABLE session_v2 (id text PRIMARY KEY, project_id text NOT NULL, slug text NOT NULL, directory text NOT NULL,
            title text, version text NOT NULL, time_created integer);
        CREATE TABLE session_message (id text PRIMARY KEY, session_id text NOT NULL, type text NOT NULL, seq integer NOT NULL,
            time_created integer NOT NULL, time_updated integer NOT NULL, data text NOT NULL);
    """)
    rng = g.rng
    for sid, folder, local, ts_list, stack, graph in g.oc_sessions:
        c.execute("insert into session_v2 values (?,?,?,?,?,?,?)", (sid, "prj_" + g.b62(10), "demo", folder, "session", "1.4.0", int(ts_list[0] * 1000)))
        ctx = rng.randint(8000, 14000)
        for i, ts in enumerate(ts_list):
            out = int(rng.lognormvariate(5.9, 0.7))
            new = int(rng.lognormvariate(7.2, 0.7))
            parts = [{"type": "text", "text": "…"}]
            if rng.random() < 0.7:
                cmd = g.command(stack, False)
                parts.append({"type": "tool", "name": "bash", "state": {"status": "completed", "input": {"command": cmd}}})
                if rng.random() < 0.5:
                    g.rtk(ts, cmd, folder, "opencode")
            if local:
                model, provider, cost = "qwen3-coder:30b", "ollama", 0
                tokens = {"input": ctx + new, "output": out, "reasoning": 0, "cache": {"read": 0, "write": 0}}
                dur = (ctx + new) / 2500 + out / 45
                g.ollama_reqs.append((ts - dur, "/v1/chat/completions", dur))
            else:
                model, provider = "claude-sonnet-5-5", "anthropic"
                tokens = {"input": rng.randint(2, 9), "output": out, "reasoning": 0, "cache": {"read": ctx, "write": new}}
                cost = (ctx * 0.1 + new * 2.5 + out * 10) / 1e6
            ctx += new + out
            data = {"role": "assistant", "time": {"created": int(ts * 1000), "completed": int(ts * 1000) + 900},
                    "model": {"id": model, "providerID": provider}, "tokens": tokens, "cost": cost, "content": parts}
            c.execute("insert into session_message values (?,?,?,?,?,?,?)",
                      ("msg_" + g.b62(26), sid, "assistant", i, int(ts * 1000), int(ts * 1000) + 900, json.dumps(data)))
    c.commit()
    c.close()
    # Ollama server log: model requests (OpenCode) plus a few embeddings and direct calls
    for ts, _ep, _d in list(g.ollama_reqs):
        if rng.random() < 0.3:
            g.ollama_reqs.append((ts + 30, "/api/embed", rng.uniform(0.05, 0.4)))
    for _ in range(25):
        g.ollama_reqs.append((g.now - rng.uniform(0, 25 * 86400), "/api/generate", rng.uniform(2, 40)))
    logdir = HOME / "AppData" / "Local" / "Ollama"
    logdir.mkdir(parents=True, exist_ok=True)
    out = ["time=startup level=INFO source=routes.go msg=\"Listening on 127.0.0.1:11434 (version 0.13.2)\""]
    for ts, ep, dur in sorted(g.ollama_reqs):
        d = dt.datetime.fromtimestamp(ts + dur)
        status = 500 if rng.random() < 0.01 else 200
        el = f"{dur:.6f}s" if dur < 60 else f"{int(dur // 60)}m{dur % 60:.6f}s"
        out.append(f"[GIN] {d:%Y/%m/%d - %H:%M:%S} | {status} | {el:>14} |       127.0.0.1 | POST     \"{ep}\"")
    (logdir / "server.log").write_text("\n".join(out) + "\n", encoding="utf-8")


# ----------------------------------------------------------------------------
# agent configuration, installed programs and projects
# ----------------------------------------------------------------------------

def _write_configs() -> None:
    claude = HOME / ".claude"
    (claude / "skills" / "graphify").mkdir(parents=True, exist_ok=True)
    (claude / "skills" / "graphify" / "SKILL.md").write_text("---\nname: graphify\n---\nQuery the project graph.\n", encoding="utf-8")
    (claude / "settings.json").write_text(json.dumps({
        "model": "opus",
        "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "rtk hook claude"}]}]},
        "enabledPlugins": {},
    }, indent=2), encoding="utf-8")
    (HOME / ".claude.json").write_text(json.dumps({
        "mcpServers": {"context-mode": {"type": "stdio", "command": "npx", "args": ["-y", "context-mode"]}},
        "projects": {},
    }, indent=2), encoding="utf-8")
    codex = HOME / ".codex"
    codex.mkdir(parents=True, exist_ok=True)
    (codex / "config.toml").write_text('model = "gpt-6.1-sol"\n\n[mcp_servers.context-mode]\ncommand = "npx"\nargs = ["-y", "context-mode"]\n',
                                       encoding="utf-8")
    oc = HOME / ".config" / "opencode"
    oc.mkdir(parents=True, exist_ok=True)
    (oc / "opencode.json").write_text(json.dumps({
        "$schema": "https://opencode.ai/config.json",
        "provider": {"ollama": {"npm": "@ai-sdk/openai-compatible", "options": {"baseURL": "http://localhost:11434/v1"},
                                "models": {"qwen3-coder:30b": {}}}},
    }, indent=2), encoding="utf-8")
    # programs "installed" on the fake PATH: do-nothing stubs, only so they are detected
    for name in ("rtk", "headroom", "graphify", "claude", "codex", "opencode", "ollama"):
        (BIN / f"{name}.cmd").write_text("@echo off\r\nrem Token Economy demo stub: does nothing\r\n", encoding="utf-8")
        stub = BIN / name
        stub.write_text("#!/bin/sh\n# Token Economy demo stub: does nothing\n", encoding="utf-8")
        stub.chmod(0o755)


def _write_projects() -> None:
    for name, stack, graph in PROJECTS:
        p = HOME / "code" / name
        (p / ".git").mkdir(parents=True, exist_ok=True)  # project root for the project name
        (p / "README.md").write_text(f"# {name}\n\nFictional project used by the Token Economy demo.\n", encoding="utf-8")
        if graph:
            (p / "graphify-out").mkdir(exist_ok=True)
            nodes = [{"id": f"n{i}", "label": f"symbol_{i}"} for i in range(240 + 90 * len(name))]
            (p / "graphify-out" / "graph.json").write_text(json.dumps({"nodes": nodes, "links": []}), encoding="utf-8")


# ----------------------------------------------------------------------------
# the app's own data folder in demo mode
# ----------------------------------------------------------------------------

def _write_cache(g: Gen, now: float, state: dict, real_cache: Path) -> None:
    (CACHE / "config.json").write_text(json.dumps({
        "subscriptions": [{"name": "Claude Max", "agent": "claude", "monthly": 100.0},
                          {"name": "ChatGPT Plus", "agent": "codex", "monthly": 20.0}],
        "ai": {"type": "cli", "cli": "claude", "days": "7"},
    }), encoding="utf-8")
    # public price tables already downloaded by the real install (read-only copy); without
    # them, default_prices.json is used
    for name in ("litellm", "openrouter"):
        for src in (real_cache / f"prices_{name}.json", real_cache / f"precos_{name}.json"):
            if src.is_file():
                shutil.copy2(src, CACHE / f"prices_{name}.json")
                break
    # limit readings of the last 8 days, as the app records them every 5 minutes
    for agent, path, fn in (("claude", CACHE / "claude_limits.jsonl", _claude_windows),
                            ("codex", CACHE / "codex_limits.jsonl", _codex_windows)):
        lines = []
        t = now - 8 * 86400
        while t < now - 60:
            lines.append(json.dumps({"ts": round(t, 1), "windows": fn(t)}))
            t += 600
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (CACHE / "ai_analyses.json").write_text(json.dumps([_analysis(now - 19 * 3600)], ensure_ascii=False), encoding="utf-8")


def _claude_windows(ts: float) -> list[dict]:
    d = claude_usage(ts)
    out = [{"id": k, "pct": d[k]["utilization"], "reset": _ts(d[k]["resets_at"]), "duration_h": 5 if k == "five_hour" else 168}
           for k in ("five_hour", "seven_day", "seven_day_sonnet")]
    lim = d["limits"][0]
    out.append({"id": "weekly_scoped:Opus", "pct": lim["percent"], "reset": _ts(lim["resets_at"]), "duration_h": 168})
    return out


def _codex_windows(ts: float) -> list[dict]:
    d = codex_usage(ts)["rate_limit"]
    return [{"id": i, "pct": d[k]["used_percent"], "reset": d[k]["reset_at"], "duration_h": h}
            for k, i, h in (("primary_window", "five_hour", 5.0), ("secondary_window", "seven_day", 168.0))]


def _ts(iso: str | None) -> float | None:
    return dt.datetime.fromisoformat(iso).timestamp() if iso else None


def _analysis(date: float) -> dict:
    return {
        "summary": "Usage is healthy overall: 95% of the input comes from the cache and RTK filters most shell output. "
                   "The weekly Claude limit is the bottleneck: at this pace it runs out about a day before it resets, mostly "
                   "because of long Opus sessions in acme-storefront.",
        "score": 86,
        "items": [
            {"level": "high", "title": "Weekly Claude limit runs out before the reset",
             "text": "71% of the weekly window is used with 2.6 days left. Long Opus sessions in acme-storefront (300+ calls) "
                     "account for most of it; their average context is above 120k tokens per call.",
             "action": "Start a fresh session (or /compact) when a task changes, and use Sonnet for routine edits and test runs."},
            {"level": "medium", "title": "PowerShell commands bypass RTK",
             "text": "Get-Content and Select-String calls from Claude Code are not filtered by RTK, so their full output enters the context.",
             "action": "Ask the agent to prefer Bash (cat, grep) for reading files and searching, which RTK compresses."},
            {"level": "medium", "title": "Graphify is set up but rarely queried in billing-api",
             "text": "The project has a code graph, but the agents mostly grep and read files there instead of querying it.",
             "action": "Add a line to the project's CLAUDE.md / AGENTS.md telling the agent to run graphify query before grepping."},
            {"level": "low", "title": "Codex 5-hour windows hit 100% on busy days",
             "text": "Several 5-hour windows reached the cap this week, mostly in the afternoon.",
             "action": "Move long refactors to the morning or split them across windows."},
            {"level": "ok", "title": "Cache hit rate is excellent",
             "text": "Cache reads are about 95% of all input across agents.", "action": ""},
        ],
        "date": date, "by": "Claude Code", "model": "claude-opus-5-5", "days": 7, "language": "en", "seconds": 96,
        "prompt_size": 18342,
    }
