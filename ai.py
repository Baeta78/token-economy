"""Analysis of the data by an AI chosen by the user.

Three ways to connect:
  - Installed CLI (Claude Code, Codex, Gemini, Grok, Qwen, Cursor, Copilot, OpenCode,
    Ollama…). The catalog is in ai_providers.json; the panel shows the ones found on PATH.
    Uses the subscription the person already has, with no API key.
  - OpenAI-compatible API (OpenAI, xAI, OpenRouter, Groq, DeepSeek, Gemini, Mistral,
    Ollama, LM Studio…): base URL + key + model.
  - Custom command: any program that reads the prompt and answers with the JSON.

The AI only gets an aggregated summary (numbers per agent, model, command, project), never
the content of the conversations. The prompt is in prompts/analysis.md and can be edited.
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
WORK_DIR = CACHE / "ai"
HISTORY = CACHE / "ai_analyses.json"
PROMPT = BASE / "prompts" / "analysis.md"
CATALOG = BASE / "ai_providers.json"
MAX_TIME = 600

LANGUAGES = {"pt": "Brazilian Portuguese", "en": "English", "es": "Spanish"}

APIS = [
    {"id": "openai", "name": "OpenAI", "url": "https://api.openai.com/v1"},
    {"id": "xai", "name": "xAI (Grok)", "url": "https://api.x.ai/v1"},
    {"id": "openrouter", "name": "OpenRouter", "url": "https://openrouter.ai/api/v1"},
    {"id": "gemini", "name": "Google Gemini", "url": "https://generativelanguage.googleapis.com/v1beta/openai"},
    {"id": "groq", "name": "Groq", "url": "https://api.groq.com/openai/v1"},
    {"id": "deepseek", "name": "DeepSeek", "url": "https://api.deepseek.com/v1"},
    {"id": "mistral", "name": "Mistral", "url": "https://api.mistral.ai/v1"},
    {"id": "ollama", "name": "Ollama (local)", "url": "http://localhost:11434/v1"},
    {"id": "lmstudio", "name": "LM Studio (local)", "url": "http://localhost:1234/v1"},
    {"id": "other", "name": "Other", "url": ""},
]

# severity levels of an item; older answers and history entries used the Portuguese names
LEVELS = ("high", "medium", "low", "ok")
OLD_LEVELS = {"alta": "high", "media": "medium", "baixa": "low"}

state = {"running": False, "stage": "", "started": None, "error": None}
_lock = threading.Lock()


# ----------------------------------------------------------------------------
# catalog
# ----------------------------------------------------------------------------

def catalog() -> list[dict]:
    try:
        return json.loads(CATALOG.read_text(encoding="utf-8-sig")).get("cli") or []
    except Exception:  # noqa: BLE001
        return []


def available() -> dict:
    clis = []
    for c in catalog():
        path = shutil.which(c.get("exe") or "")
        if path:
            clis.append({"id": c["id"], "name": c["name"], "verified": bool(c.get("verified")),
                         "model_required": bool(c.get("model_required")), "path": path})
    return {"cli": clis, "apis": APIS}


# ----------------------------------------------------------------------------
# data summary for the AI
# ----------------------------------------------------------------------------

def _hour_ts(h: str) -> float:
    return time.mktime(time.strptime(h[:13], "%Y-%m-%dT%H"))


def _day_ts(d: str) -> float:
    return time.mktime(time.strptime(d[:10], "%Y-%m-%d"))


def _r(x, n=1):
    return round(x, n) if isinstance(x, float) else x


def _aggregate_period(snap: dict, start: float, end: float) -> dict:
    new = lambda r: (r.get("input") or 0) + (r.get("cache_write") or 0) + (r.get("output") or 0)
    ag = defaultdict(lambda: defaultdict(float))
    mod = defaultdict(lambda: defaultdict(float))
    for r in snap["usage"]:
        t = _hour_ts(r["hour"])
        if not (start <= t < end):
            continue
        for target in (ag[r["agent"]], mod[(r["agent"], r["model"])]):
            target["calls"] += r.get("msgs") or 0
            target["new_tokens"] += new(r)
            target["uncached_input"] += r.get("input") or 0
            target["cache_read"] += r.get("cache_read") or 0
            target["cache_write"] += r.get("cache_write") or 0
            target["output"] += r.get("output") or 0
            target["reasoning"] += r.get("reasoning") or 0
            target["api_usd"] += r.get("usd") or 0

    def close(o):
        inp = o["uncached_input"] + o["cache_read"] + o["cache_write"]
        o = {k: _r(v, 2) if k == "api_usd" else int(v) for k, v in o.items()}
        o["cache_hit_pct"] = _r(100 * o["cache_read"] / inp) if inp else None
        o["avg_input_per_call"] = int(inp / o["calls"]) if o["calls"] else None
        o["avg_output_per_call"] = int(o["output"] / o["calls"]) if o["calls"] else None
        return o

    rtk = defaultdict(lambda: defaultdict(float))
    for r in snap["rtk"]["hourly"]:
        if start <= _hour_ts(r["hour"]) < end:
            for k in ("cmds", "input", "saved", "usd"):
                rtk[r["agent"]][k] += r.get(k) or 0
    hr = defaultdict(lambda: defaultdict(float))
    for r in snap["headroom"]["hourly"]:
        if start <= _hour_ts(r["hour"]) < end:
            for k in ("reqs", "saved", "saved_measured", "before", "usd"):
                hr[r["agent"]][k] += r.get(k) or 0

    return {
        "by_agent": {a: close(o) for a, o in ag.items()},
        "by_model": sorted(
            [{"agent": a, "model": m, **close(o)} for (a, m), o in mod.items()],
            key=lambda x: -x["new_tokens"])[:12],
        "rtk_by_agent": {a: {"commands": int(o["cmds"]), "tokens_saved": int(o["saved"]),
                             "reduction_pct": _r(100 * o["saved"] / o["input"]) if o["input"] else None,
                             "api_usd_saved_min": _r(o["usd"], 2)} for a, o in rtk.items()},
        "headroom_by_client": {a: {"requests": int(o["reqs"]), "tokens_saved": int(o["saved"]),
                                   "reduction_pct": _r(100 * o["saved_measured"] / o["before"]) if o["before"] else None,
                                   "usd_saved": _r(o["usd"], 3)} for a, o in hr.items()},
    }


def data_summary(snap: dict, days: int = 7, previous: dict | None = None) -> dict:
    now = time.time()
    start = now - days * 86400
    prev_start = start - days * 86400

    # Codex 5 h windows
    win = {}
    for l in snap["limits"]["codex"]:
        if l.get("reset_5h") and l.get("p5h") is not None and l["ts"] >= start:
            k = round(l["reset_5h"] / 300)
            j = win.setdefault(k, {"start": l["reset_5h"] - (l.get("window_min") or 300) * 60, "max_pct": 0, "last": l["ts"]})
            j["max_pct"] = max(j["max_pct"], l["p5h"])
            j["last"] = max(j["last"], l["ts"])
    windows = []
    for j in sorted(win.values(), key=lambda x: x["start"]):
        hours = max((j["last"] - j["start"]) / 3600, 0.05)
        windows.append({"start": dt.datetime.fromtimestamp(j["start"]).strftime("%Y-%m-%d %H:%M"),
                        "max_pct": j["max_pct"], "pct_per_hour": _r(j["max_pct"] / hours)})
    last = snap["limits"]["codex"][-1] if snap["limits"]["codex"] else None

    rtk_cmd = defaultdict(lambda: defaultdict(float))
    for r in snap["rtk"]["commands"]:
        if _day_ts(r["day"]) + 86400 >= start:
            for k in ("cmds", "input", "saved", "zero", "usd"):
                rtk_cmd[r["command"]][k] += r.get(k) or 0
    cmds = sorted(rtk_cmd.items(), key=lambda x: -x[1]["cmds"])[:15]

    proj = defaultdict(lambda: defaultdict(float))
    for r in snap["project_usage"]:
        if _day_ts(r["day"]) + 86400 >= start:
            proj[r["project"]]["tokens_incl_cache"] += r.get("tokens") or 0
            proj[r["project"]]["calls"] += r.get("msgs") or 0
            proj[r["project"]]["api_usd"] += r.get("usd") or 0
    sess = [s for s in snap["sessions"] if s["end"] >= start]
    sess.sort(key=lambda s: -s["tokens"])

    data = {
        "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "period_days": days,
        "current_period": _aggregate_period(snap, start, now + 3600),
        "previous_period": _aggregate_period(snap, prev_start, start),
        "codex_limits": {
            "plan": last.get("plan") if last else None,
            "weekly_used_pct_now": last.get("pweek") if last and (last.get("reset_week") or 0) > now else 0,
            "five_hour_windows": windows[-15:],
        } if last else None,
        "claude_limits": "not recorded in Claude Code logs",
        "rtk": {
            "top_commands": [{"command": k, "runs": int(o["cmds"]), "tokens_saved": int(o["saved"]),
                              "reduction_pct": _r(100 * o["saved"] / o["input"]) if o["input"] else None,
                              "no_gain_pct": _r(100 * o["zero"] / o["cmds"]) if o["cmds"] else None} for k, o in cmds],
            "failures_all_time": snap["rtk"]["failures"][:8],
            "hook_decisions_all_time": snap["rtk"]["hook_decisions"],
        },
        "shell_commands_by_agent_all_time": {a: dict(list(v.items())[:10]) for a, v in snap.get("shell_commands", {}).items()},
        "tools_by_agent_all_time": {a: dict(list(v.items())[:15]) for a, v in snap.get("tools", {}).items()},
        "top_projects": [{"project": k, **{kk: _r(vv, 2) if kk == "api_usd" else int(vv) for kk, vv in o.items()}}
                         for k, o in sorted(proj.items(), key=lambda x: -x[1]["tokens_incl_cache"])[:10]],
        "heaviest_sessions": [{"agent": s["agent"], "project": s["project"], "model": s["model"],
                               "hours": _r((s["end"] - s["start"]) / 3600), "calls": s["msgs"],
                               "tokens_incl_cache": s["tokens"],
                               "avg_context": int((s["input"] + s["cache_read"] + s["cache_write"]) / max(s["msgs"], 1)),
                               "api_usd": _r(s["usd"], 2)} for s in sess[:8]],
        "graphify": {"projects_with_graph": len(snap["graphify"]["projects"]), "calls_all_time": snap["graphify"]["calls"]},
        "ollama": {"installed_models": len(snap["ollama"].get("models") or [])},
    }
    import score as score_mod
    data["optimization_score"] = score_mod.compute(snap, start, now)
    # token-saving tools found on the machine and what each one recorded in the period
    saved = defaultdict(float)
    for r in (snap.get("savings") or {}).get("hourly") or []:
        if _hour_ts(r["hour"]) >= start:
            saved[r["tool"]] += r.get("saved") or 0
    for r in snap["rtk"]["hourly"]:
        if _hour_ts(r["hour"]) >= start:
            saved["rtk"] += r.get("saved") or 0
    for r in snap["headroom"]["hourly"]:
        if _hour_ts(r["hour"]) >= start:
            saved["headroom"] += r.get("saved") or 0
    data["token_saving_tools"] = [
        {"tool": f["name"], "category": f.get("category"), "records_savings": bool(f.get("measured")),
         "tokens_saved_in_period": int(saved.get(f["id"], 0)) if f.get("measured") else None,
         "agents": f.get("agents"), "calls_by_agents_all_time": f.get("calls") or None}
        for f in (snap.get("savings") or {}).get("tools") or []]
    data["rtk"]["filterable_commands_that_bypassed_rtk"] = snap["rtk"].get("coverage", {}).get("by_command", {})
    if previous:
        data["previous_analysis"] = {
            "date": previous.get("date"), "score": previous.get("score"),
            "items": [i.get("title") for i in previous.get("items") or []],
        }
    return data


def build_prompt(snap: dict, language: str, days: int, previous: dict | None) -> str:
    template = PROMPT.read_text(encoding="utf-8")
    data = json.dumps(data_summary(snap, days, previous), ensure_ascii=False, separators=(",", ":"))
    return template.replace("{language}", LANGUAGES.get(language, "English")).replace("{data}", data)


# ----------------------------------------------------------------------------
# execution
# ----------------------------------------------------------------------------

def extract_json(text: str) -> dict:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("the answer had no JSON")
    d = json.loads(text[start:end + 1])
    items = []
    # the Portuguese keys (itens, nivel, titulo, texto, acao, resumo, nota) are still accepted
    for i in d.get("items") or d.get("itens") or []:
        level = str(i.get("level") or i.get("nivel") or "low").lower()
        level = OLD_LEVELS.get(level, level)
        items.append({
            "level": level if level in LEVELS else "low",
            "title": str(i.get("title") or i.get("titulo") or "")[:200],
            "text": str(i.get("text") or i.get("texto") or "")[:1200],
            "action": str(i.get("action") or i.get("acao") or "")[:800],
        })
    score = d.get("score", d.get("nota"))
    try:
        score = max(0, min(100, int(score)))
    except (TypeError, ValueError):
        score = None
    return {"summary": str(d.get("summary") or d.get("resumo") or "")[:1000], "score": score, "items": items[:10]}


def _run_cli(cfg: dict, prompt: str) -> str:
    entry = next((c for c in catalog() if c["id"] == cfg.get("cli")), None)
    if not entry:
        raise ValueError("tool is not in the catalog")
    exe = shutil.which(entry["exe"])
    if not exe:
        raise ValueError(f"{entry['exe']} not found on PATH")
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    prompt_file = WORK_DIR / "prompt.md"
    prompt_file.write_text(prompt, encoding="utf-8")
    model = (cfg.get("model") or "").strip()
    if entry.get("model_required") and not model:
        raise ValueError("choose a model")
    args = []
    for a in entry["args"]:
        a = a.replace("{file}", str(prompt_file)).replace("{model}", model)
        if "{prompt}" in a:
            a = a.replace("{prompt}", prompt)
        args.append(a)
    if model and entry.get("model_arg") and "{model}" not in " ".join(entry["args"]):
        args = [args[0], entry["model_arg"], model, *args[1:]] if entry["id"] in ("codex", "opencode", "droid") else [entry["model_arg"], model, *args]
    return _execute([exe, *args], prompt if entry["input"] == "stdin" else None)


def _run_custom(cfg: dict, prompt: str) -> str:
    template = (cfg.get("command") or "").strip()
    if not template:
        raise ValueError("empty command")
    # "{arquivo}" is the placeholder used before the English translation
    template = template.replace("{arquivo}", "{file}")
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    prompt_file = WORK_DIR / "prompt.md"
    prompt_file.write_text(prompt, encoding="utf-8")
    uses_file = "{file}" in template
    parts = shlex.split(template.replace("{file}", str(prompt_file).replace("\\", "/")), posix=True)
    exe = shutil.which(parts[0]) or parts[0]
    return _execute([exe, *parts[1:]], None if uses_file else prompt)


def _execute(cmd: list[str], stdin: str | None) -> str:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    env = dict(os.environ, NO_COLOR="1", TERM="dumb")
    p = subprocess.run(
        cmd, input=stdin, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=MAX_TIME, cwd=str(WORK_DIR), creationflags=flags, env=env,
    )
    out = (p.stdout or "").strip()
    if p.returncode != 0 and "{" not in out:
        raise RuntimeError(f"exited with code {p.returncode}: {(p.stderr or out)[-600:]}")
    return out


def _run_api(cfg: dict, prompt: str) -> str:
    url = (cfg.get("url") or "").rstrip("/")
    model = (cfg.get("model") or "").strip()
    if not url or not model:
        raise ValueError("enter the URL and the model")
    key = (cfg.get("key") or "").strip()
    if key.startswith("$"):
        key = os.environ.get(key[1:], "")
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}]}).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "token-economy"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(url + "/chat/completions", data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=MAX_TIME) as r:
            d = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:400]}") from None
    return d["choices"][0]["message"]["content"]


def history() -> list[dict]:
    try:
        return json.loads(HISTORY.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []


def analyze(snap: dict, cfg: dict, language: str) -> None:
    """Runs in the background. The result goes to .cache/ai_analyses.json."""
    with _lock:
        if state["running"]:
            return
        state.update(running=True, stage="preparing", started=time.time(), error=None)

    def job():
        try:
            days = int(cfg.get("days") or 7)
            hist = history()
            prompt = build_prompt(snap, language, days, hist[0] if hist else None)
            state["stage"] = "waiting for the AI"
            kind = cfg.get("type")
            if kind == "cli":
                raw = _run_cli(cfg, prompt)
                who = next((c["name"] for c in catalog() if c["id"] == cfg.get("cli")), cfg.get("cli"))
            elif kind == "api":
                raw = _run_api(cfg, prompt)
                who = next((a["name"] for a in APIS if a["id"] == cfg.get("api")), "API")
            elif kind == "custom":
                raw = _run_custom(cfg, prompt)
                who = (cfg.get("command") or "").split()[0]
            else:
                raise ValueError("choose an AI")
            state["stage"] = "reading the answer"
            try:
                res = extract_json(raw)
            except Exception as e:  # noqa: BLE001
                raise RuntimeError(f"answer not in the expected format ({e}): {raw[:300]}") from None
            import score as score_mod
            res["score"] = score_mod.compute(snap, time.time() - days * 86400, time.time())["score"]
            res.update(date=time.time(), by=who, model=cfg.get("model") or "", days=days, language=language,
                       seconds=round(time.time() - state["started"]), prompt_size=len(prompt))
            CACHE.mkdir(exist_ok=True)
            HISTORY.write_text(json.dumps([res, *hist][:20], ensure_ascii=False), encoding="utf-8")
            state["error"] = None
        except subprocess.TimeoutExpired:
            state["error"] = f"the AI did not answer within {MAX_TIME // 60} minutes"
        except Exception as e:  # noqa: BLE001
            state["error"] = str(e)
            traceback.print_exc()
        finally:
            state.update(running=False, stage="")

    threading.Thread(target=job, daemon=True).start()
