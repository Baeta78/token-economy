"""Subscription plan limits, read from the official sources.

Claude (Pro / Max / Ultra)
    GET https://api.anthropic.com/api/oauth/usage
    header anthropic-beta: oauth-2025-04-20, authenticated with the login that Claude
    Code itself keeps in ~/.claude/.credentials.json (or CLAUDE_CODE_OAUTH_TOKEN; on
    macOS, in the Keychain item "Claude Code-credentials").
    It is the same endpoint Headroom and ccassist use. The token is read on the spot, only
    goes to Anthropic and is never stored or shown by Token Economy. If the login has
    expired, nothing is done: Claude Code renews it by itself the next time it runs.

    The response has one entry per window (five_hour, seven_day, seven_day_opus, …).
    Each plan has its own: Ultra, for example, has no 5 h window. This module reads
    whatever windows come back, so new kinds show up without code changes.

Codex
    Comes from Codex's own logs (rate_limits on every turn), read by the collector.

To turn off the Claude lookup: in Settings, or "claude_limits": false in .cache/config.json.
"""
from __future__ import annotations

import json
import re
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import runtime

BASE = Path(__file__).resolve().parent
CACHE = runtime.CACHE
CLAUDE_HISTORY = CACHE / "claude_limits.jsonl"
CONFIG = CACHE / "config.json"
CLAUDE_URL = "https://api.anthropic.com/api/oauth/usage"
INTERVAL = 300  # queries at most every 5 min

# known duration of each window (hours); unknown ones are inferred from the name
DURATION = {"five_hour": 5, "seven_day": 168}

_state = {"claude": None, "queried": 0.0}
_lock = threading.Lock()


def _enabled() -> bool:
    try:
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        # "limites_claude" is the key used before the English translation
        return cfg.get("claude_limits", cfg.get("limites_claude", True)) is not False
    except Exception:  # noqa: BLE001
        return True


KEYCHAIN_SERVICE = "Claude Code-credentials"  # where Claude Code keeps its login on macOS


def _keychain_login() -> dict:
    """The login Claude Code keeps in the macOS Keychain (it has no .credentials.json there).

    Read with the system `security` tool; the first time, macOS asks whether to allow it
    ("Always Allow" stops the question). Nothing is written to the Keychain."""
    try:
        res = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
                             capture_output=True, text=True, timeout=15)
        if res.returncode == 0 and res.stdout.strip():
            return json.loads(res.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return {}


def _claude_login() -> tuple[str | None, dict]:
    """(token, plan info without secrets)."""
    tok = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip()
    folder = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    info = {}
    try:
        try:
            raw = json.loads((folder / ".credentials.json").read_text(encoding="utf-8"))
        except OSError:
            # macOS: no file, the login is in the Keychain (skipped when a token is already given)
            if not (runtime.MAC and not tok):
                raise
            raw = _keychain_login()
            if not raw:
                return None, info
        cred = raw.get("claudeAiOauth") or {}
        info = {"type": cred.get("subscriptionType"), "tier": cred.get("rateLimitTier")}
        if not tok:
            expires = cred.get("expiresAt")
            if expires and float(expires) / 1000 < time.time() + 60:
                info["expired"] = True
                return None, info
            tok = (cred.get("accessToken") or "").strip()
    except (OSError, ValueError):
        pass
    return tok or None, info


def plan_name(profile: str | None) -> str | None:
    """Plan name only when Anthropic reports the current name (account profile).

    The login only keeps old codes (subscriptionType "max", rateLimitTier
    "default_claude_max_20x"), which do not follow plan renames or multiplier
    changes. So they are not used as a name: without the real name, the panel
    shows only the agent, with no plan label.
    """
    return (profile or "").strip() or None


_PLAN_FIELD = re.compile(r"plan|subscription|tier|billing|organization_type|account_type", re.I)
_SECRET = re.compile(r"email|uuid|^id$|_id$|token|key|phone|^name$|full_name|first_name|last_name|display_name$(?<!plan_display_name)", re.I)


def _plan_fields(obj, path="") -> dict:
    """Profile fields that talk about the plan (short text), with no personal data."""
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            c = f"{path}.{k}" if path else k
            if isinstance(v, (dict, list)):
                out.update(_plan_fields(v, c))
            elif isinstance(v, (str, bool, int, float)) and _PLAN_FIELD.search(c) and not _SECRET.search(k):
                if not isinstance(v, str) or len(v) <= 60:
                    out[c] = v
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:5]):
            out.update(_plan_fields(v, f"{path}[{i}]"))
    return out


def _name_in_profile(fields: dict) -> str | None:
    """A plan display name, if the profile has one (e.g. '...plan.display_name')."""
    for k, v in fields.items():
        if isinstance(v, str) and re.search(r"(plan|subscription).*(display|label|name)|display_?name.*(plan|subscription)", k, re.I):
            return v.strip() or None
    return None


def _claude_profile(tok: str) -> dict:
    """Queries the account profile (same endpoint Claude Code uses) once every 6 h."""
    now = time.time()
    if now - _state.get("profile_at", 0) < 6 * 3600 and "profile" in _state:
        return _state["profile"]
    fields = {}
    try:
        req = urllib.request.Request("https://api.anthropic.com/api/oauth/profile", headers={
            "Authorization": f"Bearer {tok}", "anthropic-beta": "oauth-2025-04-20", "User-Agent": "token-economy"})
        with urllib.request.urlopen(req, timeout=15) as r:
            fields = _plan_fields(json.loads(r.read().decode("utf-8")))
    except Exception:  # noqa: BLE001
        pass
    _state.update(profile={"fields": fields, "name": _name_in_profile(fields)}, profile_at=now)
    try:  # records only the plan fields, for diagnostics
        (CACHE / "claude_profile_fields.json").write_text(json.dumps(fields, indent=1, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return _state["profile"]


def _duration(name: str) -> float | None:
    if name in DURATION:
        return DURATION[name]
    if name.startswith("seven_day"):
        return 168
    if name.startswith("five_hour"):
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


def _query_claude() -> dict:
    if runtime.DEMO:
        # demo mode: never reads a login nor calls Anthropic; the answer comes from demo.py
        import demo
        res = {"ok": False, "read_at": time.time(), "plan": demo.CLAUDE_PLAN}
        return _read_claude_usage(res, demo.claude_usage(res["read_at"]))
    tok, info = _claude_login()
    res = {"ok": False, "read_at": time.time(), **info}
    if not tok:
        res["error"] = "login_expired" if info.get("expired") else "no_login"
        return res
    res["plan"] = plan_name(_claude_profile(tok).get("name"))
    req = urllib.request.Request(CLAUDE_URL, headers={
        "Authorization": f"Bearer {tok}", "anthropic-beta": "oauth-2025-04-20", "User-Agent": "token-economy",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        res["error"] = f"http_{e.code}"
        return res
    except Exception as e:  # noqa: BLE001
        res["error"] = type(e).__name__
        return res
    return _read_claude_usage(res, d)


def _read_claude_usage(res: dict, d: dict) -> dict:
    """Reads the usage endpoint answer into res (windows, extra credits, cloud credits)."""
    # fixed windows: five_hour, seven_day, seven_day_sonnet… A null window does not exist
    # in the plan (the verified Ultra, for example, has no 5 h window) and is not shown.
    windows = []
    for name, v in d.items():
        if (name.startswith("five_hour") or name.startswith("seven_day")) and isinstance(v, dict) and "utilization" in v:
            windows.append({"id": name, "pct": float(v.get("utilization") or 0),
                            "reset": _ts(v.get("resets_at")), "duration_h": _duration(name)})
    # weekly per-model windows (e.g. Fable) come in the "limits" list as weekly_scoped
    for lim in d.get("limits") or []:
        if not isinstance(lim, dict) or lim.get("kind") != "weekly_scoped":
            continue
        model = ((lim.get("scope") or {}).get("model") or {}).get("display_name")
        if not model or lim.get("percent") is None:
            continue
        windows.append({"id": "weekly_scoped:" + str(model)[:40], "pct": float(lim["percent"]),
                        "reset": _ts(lim.get("resets_at")), "duration_h": 168})
    # the plan's extra usage credits (values in dollar cents in the response)
    extra = None
    eu = d.get("extra_usage")
    if isinstance(eu, dict):
        def usd(v):
            try:
                return round(float(v) / 100, 2)
            except (TypeError, ValueError):
                return None
        places = eu.get("decimal_places") if isinstance(eu.get("decimal_places"), int) and 0 <= eu.get("decimal_places") <= 4 else 2
        def usd(v):  # noqa: F811 - values in the currency's minor units
            try:
                return round(float(v) / (10 ** places), 2)
            except (TypeError, ValueError):
                return None
        extra = {"enabled": bool(eu.get("is_enabled")), "currency": eu.get("currency") or "USD", "limit_usd": usd(eu.get("monthly_limit")),
                 "used_usd": usd(eu.get("used_credits")),
                 "pct": float(eu["utilization"]) if isinstance(eu.get("utilization"), (int, float)) else None}
    # Claude Code cloud session credits ("iguana_necktie" block), in dollars
    cloud = None
    block = d.get("iguana_necktie")
    if isinstance(block, dict):
        def num(v):
            try:
                return round(float(v), 2)
            except (TypeError, ValueError):
                return None
        cloud = {"limit_usd": num(block.get("limit_dollars")), "remaining_usd": num(block.get("remaining_dollars")),
                 "reset": _ts(block.get("resets_at")), "locked": bool(block.get("locked_reason"))}
        if cloud["limit_usd"] is None and cloud["remaining_usd"] is None:
            cloud = None
    res.update(ok=True, windows=windows, extra=extra, cloud=cloud)
    _write_history(CLAUDE_HISTORY, res["read_at"], windows)
    return res


def _trim(p: Path, max_lines: int) -> None:
    lines = p.read_text(encoding="utf-8").splitlines()
    if len(lines) > max_lines * 1.2:
        p.write_text("\n".join(lines[-max_lines:]) + "\n", encoding="utf-8")


def claude(force: bool = False) -> dict | None:
    """Latest reading of the Claude limits (queries again once the interval has passed)."""
    if not _enabled():
        return {"ok": False, "error": "disabled"}
    with _lock:
        if force or time.time() - _state["queried"] >= INTERVAL:
            _state["queried"] = time.time()
            _state["claude"] = _query_claude()
        return _state["claude"]


# ----------------------------------------------------------------------------
# Codex: official usage endpoint (the same one the Codex CLI queries)
# ----------------------------------------------------------------------------

CODEX_URL = "https://chatgpt.com/backend-api/wham/usage"
CODEX_HISTORY = CACHE / "codex_limits.jsonl"


def _codex_login() -> tuple[str | None, str | None]:
    """(access_token, account_id) from the login Codex stores in ~/.codex/auth.json."""
    folder = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    try:
        tokens = json.loads((folder / "auth.json").read_text(encoding="utf-8")).get("tokens") or {}
        return (tokens.get("access_token") or "").strip() or None, tokens.get("account_id")
    except (OSError, ValueError):
        return None, None


def _id_from_duration(sec) -> tuple[str, float | None]:
    """Codex identifies windows by their duration, not by their position in the response."""
    try:
        h = float(sec) / 3600
    except (TypeError, ValueError):
        return "window", None
    if abs(h - 5) < 0.6:
        return "five_hour", 5.0
    if abs(h - 168) < 12:
        return "seven_day", 168.0
    return f"window_{round(h)}h", h


def _query_codex() -> dict:
    if runtime.DEMO:
        # demo mode: never reads a login nor calls OpenAI; the answer comes from demo.py
        import demo
        res = {"ok": False, "read_at": time.time()}
        return _read_codex_usage(res, demo.codex_usage(res["read_at"]))
    tok, account = _codex_login()
    res = {"ok": False, "read_at": time.time()}
    if not tok:
        res["error"] = "no_login"
        return res
    headers = {"Authorization": f"Bearer {tok}", "User-Agent": "codex-cli"}
    if account:
        headers["ChatGPT-Account-Id"] = account
    try:
        with urllib.request.urlopen(urllib.request.Request(CODEX_URL, headers=headers), timeout=15) as r:
            d = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        res["error"] = f"http_{e.code}"
        return res
    except Exception as e:  # noqa: BLE001
        res["error"] = type(e).__name__
        return res
    return _read_codex_usage(res, d)


def _read_codex_usage(res: dict, d: dict) -> dict:
    """Reads the usage endpoint answer into res (windows and plan)."""

    def read_windows(rl, prefix=""):
        out = []
        for key in ("primary_window", "secondary_window"):
            w = (rl or {}).get(key)
            if not isinstance(w, dict) or w.get("used_percent") is None:
                continue
            ident, dur = _id_from_duration(w.get("limit_window_seconds"))
            reset = w.get("reset_at")
            if not reset and w.get("reset_after_seconds") is not None:
                reset = time.time() + float(w["reset_after_seconds"])
            out.append({"id": prefix + ident, "pct": float(w["used_percent"]),
                        "reset": float(reset) if reset else None, "duration_h": dur})
        return out

    wins = read_windows(d.get("rate_limit"))
    for extra in d.get("additional_rate_limits") or []:
        name = (extra or {}).get("limit_name") or (extra or {}).get("metered_feature")
        if name:
            wins += read_windows(extra.get("rate_limit"), f"extra:{str(name)[:40]}:")
    plan = (d.get("plan_type") or "").strip()
    res.update(ok=True, windows=wins, plan=plan.capitalize() or None)
    _write_history(CODEX_HISTORY, res["read_at"], wins)
    return res


def codex(force: bool = False) -> dict | None:
    if not _enabled():
        return {"ok": False, "error": "disabled"}
    with _lock:
        if force or time.time() - _state.get("codex_at", 0) >= INTERVAL:
            _state["codex_at"] = time.time()
            _state["codex"] = _query_codex()
        return _state.get("codex")


def _write_history(path: Path, ts: float, wins: list[dict]) -> None:
    try:
        CACHE.mkdir(exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": ts, "windows": wins}) + "\n")
        _trim(path, 4000)
    except OSError:
        pass


def history(since: float, path: Path = CLAUDE_HISTORY) -> list[dict]:
    out = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("ts", 0) >= since:
                out.append(d)
    except OSError:
        pass
    return out


def _history_windows(h: dict) -> list[dict]:
    # lines written before the English translation use the "janelas" key
    return h.get("windows") or h.get("janelas") or []


# ----------------------------------------------------------------------------
# unified windows, with rate and forecast
# ----------------------------------------------------------------------------

def _rate(samples: list[tuple[float, float]], reset: float | None, duration_h: float | None, pct: float, now: float):
    """% per hour in the current window. Uses this window's readings; with no history,
    divides the usage by the time since the window started."""
    # recent readings only count if they cover a good part of the window: 40 minutes of
    # readings in a weekly window exaggerate any spike (minimum: 10% of the window, up to 6 h)
    minimum = min(6 * 3600, (duration_h or 5) * 3600 * 0.1)
    if len(samples) >= 2 and samples[-1][0] - samples[0][0] >= minimum:
        (t0, p0), (t1, p1) = samples[0], samples[-1]
        if p1 >= p0:
            return (p1 - p0) / ((t1 - t0) / 3600)
    if reset and duration_h:
        start = reset - duration_h * 3600
        hours = (now - start) / 3600
        if hours > 0.1:
            return pct / hours
    return None


def windows(snap_codex: list[dict], claude_res: dict | None, codex_res: dict | None = None) -> list[dict]:
    """Single list of limit windows for all agents, with a forecast."""
    now = time.time()
    out = []

    # Codex from the official endpoint; without it, from the latest reading in the Codex logs
    if codex_res and codex_res.get("ok"):
        out += _api_windows("codex", codex_res, history(now - 8 * 86400, CODEX_HISTORY), now)
    elif snap_codex:
        last = snap_codex[-1]
        plan = (last.get("plan") or "").capitalize() or None
        for pct_field, reset_field, ident, dur in (("p5h", "reset_5h", "five_hour", (last.get("window_min") or 300) / 60),
                                                   ("pweek", "reset_week", "seven_day", 168)):
            reset = last.get(reset_field)
            if last.get(pct_field) is None or not reset:
                continue
            active = reset > now
            pct = last[pct_field] if active else 0.0
            samples = [(l["ts"], l[pct_field]) for l in snap_codex if l.get(reset_field) and abs(l[reset_field] - reset) < 120 and l.get(pct_field) is not None]
            out.append(_complete({"agent": "codex", "id": ident, "pct": pct, "reset": reset if active else None,
                                  "duration_h": dur, "plan": plan, "read_at": last["ts"]},
                                 samples if active else [], now))

    if claude_res and claude_res.get("ok"):
        out += _api_windows("claude", claude_res, history(now - 8 * 86400), now)
    return out


def _api_windows(agent: str, res: dict, hist: list[dict], now: float) -> list[dict]:
    out = []
    for j in res.get("windows") or []:
        samples = []
        for h in hist:
            for hj in _history_windows(h):
                if hj.get("id") == j["id"] and hj.get("reset") and j.get("reset") and abs(hj["reset"] - j["reset"]) < 120:
                    samples.append((h["ts"], hj["pct"]))
        out.append(_complete({"agent": agent, "id": j["id"], "pct": j["pct"], "reset": j.get("reset"),
                              "duration_h": j.get("duration_h"), "plan": res.get("plan"),
                              "read_at": res.get("read_at")}, samples, now))
    return out


def _complete(j: dict, samples: list, now: float) -> dict:
    rate = _rate(sorted(samples), j.get("reset"), j.get("duration_h"), j["pct"], now)
    j["rate_h"] = round(rate, 3) if rate is not None else None
    if rate and rate > 0 and j.get("reset"):
        remaining_h = max(0.0, (j["reset"] - now) / 3600)
        j["projected_at_reset"] = round(j["pct"] + rate * remaining_h, 1)
        j["runs_out_in_h"] = round((100 - j["pct"]) / rate, 2) if j["pct"] < 100 else 0.0
        j["runs_out_before_reset"] = j["runs_out_in_h"] < remaining_h
    return j


# ----------------------------------------------------------------------------
# history of every limit window, for the chart (all agents together)
# ----------------------------------------------------------------------------

def series(snap_codex: list[dict], days: int = 90) -> list[dict]:
    """[{agent, id, duration_h, points: [[ts, pct, reset], ...]}] for each limit window of each agent.

    Sources: the readings Codex writes into its own logs, plus the readings this panel saved
    from the official usage endpoints (Claude and Codex). Any agent added to `windows()` later
    only needs its history file here to show up in the chart."""
    since = time.time() - days * 86400
    acc: dict[tuple, dict] = {}

    def add(agent, ident, dur, ts, pct, reset):
        if pct is None or ts < since:
            return
        s = acc.setdefault((agent, ident), {"agent": agent, "id": ident, "duration_h": dur, "points": []})
        s["points"].append([round(ts), round(float(pct), 1), round(reset) if reset else None])

    for l in snap_codex or []:
        add("codex", "five_hour", (l.get("window_min") or 300) / 60, l["ts"], l.get("p5h"), l.get("reset_5h"))
        add("codex", "seven_day", 168, l["ts"], l.get("pweek"), l.get("reset_week"))
    for agent, path in (("codex", CODEX_HISTORY), ("claude", CLAUDE_HISTORY)):
        for h in history(since, path):
            for j in _history_windows(h):
                if j.get("id"):
                    add(agent, j["id"], j.get("duration_h"), h["ts"], j.get("pct"), j.get("reset"))
    out = []
    for s in acc.values():
        pts = sorted(s["points"])
        # the same moment from two sources (log and endpoint): keep one
        s["points"] = [p for i, p in enumerate(pts) if i == 0 or p[0] - pts[i - 1][0] >= 30]
        out.append(s)
    return sorted(out, key=lambda s: (s["agent"], s["duration_h"] or 0, s["id"]))
