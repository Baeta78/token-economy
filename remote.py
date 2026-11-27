"""Other machines (a VPS, a second computer) in this panel, with as little traffic as possible.

Two sides, same code:

  Agent (on the other machine):  python server.py --agent [--listen 100.x.y.z] [--port 8766]
      Runs the same collection as the panel and answers only two read-only routes, both behind
      a token (created on the first run, kept in .cache/agent.json):
        GET /api/export?since=REV&boot=ID   the hourly totals that changed since REV
        GET /api/live?after=SEQ&boot=ID&wait=50   the office feed, held open until there is news
      Raw logs, prompts and file contents never leave the machine: only the totals the panel
      already shows (and, for the live office, the same short labels it shows here).

  Client (in the panel): Settings > Machines keeps a name, URL and token per machine.
      Totals: the first sync brings the history once (compressed); after that only the rows
      that changed (in practice the current hour), and a 304 with no body when nothing did.
      Checks every 5 min while the machine is in use, backing off to 30 min when it is idle.
      Live office: only while the office is open on screen and the machine has "live" on; one
      long request at a time that the agent answers when something happens (or after 50 s),
      at most one every 3 s, so a burst of activity goes in one answer.
      Every byte is counted per machine and month; past the budget the machine pauses.

Hours travel in the agent's local time with its UTC offset, and are moved to this machine's
time zone when merged (days stay as the agent counted them).
"""
from __future__ import annotations

import calendar
import gzip
import hmac
import http.client
import json
import os
import re
import secrets
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

import collector
import runtime

# table -> (where it is in the snapshot, columns that identify a row)
TABLES = {
    "usage": (("usage",), ("hour", "agent", "model")),
    "project_usage": (("project_usage",), ("day", "agent", "project")),
    "sessions": (("sessions",), ("agent", "id")),
    "rtk.hourly": (("rtk", "hourly"), ("hour", "agent")),
    "rtk.activity": (("rtk", "activity"), ("hour", "agent")),
    "rtk.commands": (("rtk", "commands"), ("day", "command")),
    "savings.hourly": (("savings", "hourly"), ("hour", "agent", "tool")),
    "headroom.hourly": (("headroom", "hourly"), ("hour", "agent", "model")),
    "ollama.hourly": (("ollama", "hourly"), ("hour", "endpoint")),
}
# small pieces sent whole when they change
BLOBS = {"tools": ("tools",), "shell_commands": ("shell_commands",), "prices": ("prices", "by_model")}

AGENT_PORT = 8766
SYNC_ACTIVE_S = 300       # between checks while the machine is in use
SYNC_IDLE_MAX_S = 1800    # the interval doubles up to this while nothing changes
LIVE_WAIT_S = 50          # how long the agent holds a live request with no news
LIVE_GAP_S = 3            # minimum time between live requests (events in between go together)
WATCH_S = 12              # the office counts as open this long after its last poll here
GONE_KEEP = 5000          # removed rows remembered for deltas; older clients get a full sync
DEFAULT_BUDGET_MB = 1000
GZIP_FROM = 600           # smaller answers go uncompressed (gzip would only add bytes)


def _get(d, path):
    for p in path:
        d = (d or {}).get(p) if isinstance(d, dict) else None
    return d


def _key(row: dict, cols) -> str:
    return "\x1f".join(str(row.get(c, "")) for c in cols)


def _dumps(x) -> str:
    return json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


# ============================================================================
# agent side
# ============================================================================

AGENT_FILE = runtime.CACHE / "agent.json"


def agent_token() -> str:
    try:
        tok = json.loads(AGENT_FILE.read_text(encoding="utf-8")).get("token")
    except Exception:  # noqa: BLE001
        tok = None
    if not tok:
        tok = secrets.token_urlsafe(24)
        AGENT_FILE.parent.mkdir(parents=True, exist_ok=True)
        AGENT_FILE.write_text(json.dumps({"token": tok}), encoding="utf-8")
        try:
            os.chmod(AGENT_FILE, 0o600)
        except OSError:
            pass
    return tok


class Exporter:
    """Keeps every exported row with the revision in which it last changed, so a client that
    says "I have up to revision N" gets only what changed after N."""

    def __init__(self):
        self.lock = threading.Lock()
        self.boot = secrets.token_hex(6)   # a restart numbers revisions again: clients resync
        self.rev = 0
        self.rows: dict[str, dict[str, list]] = {t: {} for t in TABLES}   # key -> [json, rev]
        self.gone: dict[str, dict[str, int]] = {t: {} for t in TABLES}    # key -> rev removed
        self.gone_floor = 0
        self.blobs: dict[str, list] = {}

    def update(self, snap: dict) -> None:
        with self.lock:
            rev = self.rev + 1
            changed = False
            for t, (path, cols) in TABLES.items():
                cur, seen = self.rows[t], set()
                for r in _get(snap, path) or []:
                    k = _key(r, cols)
                    seen.add(k)
                    j = _dumps(r)
                    old = cur.get(k)
                    if old is None or old[0] != j:
                        cur[k] = [j, rev]
                        self.gone[t].pop(k, None)
                        changed = True
                for k in [k for k in cur if k not in seen]:
                    del cur[k]
                    self.gone[t][k] = rev
                    changed = True
                if len(self.gone[t]) > GONE_KEEP:
                    old = sorted(self.gone[t].items(), key=lambda kv: kv[1])[: len(self.gone[t]) - GONE_KEEP]
                    for k, r_ in old:
                        del self.gone[t][k]
                        self.gone_floor = max(self.gone_floor, r_)
            for name, path in BLOBS.items():
                j = _dumps(_get(snap, path))
                if (self.blobs.get(name) or [None])[0] != j:
                    self.blobs[name] = [j, rev]
                    changed = True
            if changed:
                self.rev = rev

    def export(self, since: int, boot: str) -> str | None:
        """JSON text with what changed after `since`, or None when nothing did."""
        with self.lock:
            full = boot != self.boot or since > self.rev or since < self.gone_floor or since <= 0
            if not full and since == self.rev:
                return None
            s = 0 if full else since
            tables = []
            for t in TABLES:
                rows = [j for j, r in self.rows[t].values() if r > s]
                if rows:
                    tables.append(f"{json.dumps(t)}:[{','.join(rows)}]")
            gone = {} if full else {t: [k for k, r in g.items() if r > s] for t, g in self.gone.items()}
            gone = {t: v for t, v in gone.items() if v}
            blobs = [f"{json.dumps(n)}:{j}" for n, (j, r) in self.blobs.items() if r > s]
            head = {"boot": self.boot, "rev": self.rev, "full": full, "tz": time.localtime().tm_gmtoff, "gone": gone}
            return _dumps(head)[:-1] + ',"tables":{' + ",".join(tables) + '},"blobs":{' + ",".join(blobs) + "}}"

    def live(self, after: int, boot: str, wait: float) -> dict:
        """The office feed, held until there are new events or `wait` seconds pass. A client
        that is new (after < 0) or saw another run of this agent gets the sessions only."""
        import live
        fresh = after < 0 or boot != self.boot
        if fresh:
            after = 10 ** 12
        end = time.time() + max(0.0, min(wait, 55.0))
        while True:
            r = live.feed(after)
            if fresh:
                break
            if r["events"] or time.time() >= end:
                break
            time.sleep(2)
        keep = ("id", "agent", "project", "model", "start", "last", "tokens", "usd", "saved", "saved_usd")
        return {"boot": self.boot, "seq": r["seq"],
                "sessions": [{k: s.get(k) for k in keep} for s in r["sessions"]],
                "events": [] if fresh else r["events"]}


class AgentHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"   # keep-alive: one connection for every poll, no new handshakes
    exporter: Exporter = None  # type: ignore[assignment]
    token = ""

    def log_message(self, *_):
        pass

    def _send(self, code: int, body: bytes = b"") -> None:
        gz = len(body) >= GZIP_FROM and "gzip" in (self.headers.get("Accept-Encoding") or "")
        if gz:
            body = gzip.compress(body, 6)
        self.send_response(code)
        if body:
            self.send_header("Content-Type", "application/json; charset=utf-8")
        if gz:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def version_string(self):
        return "te"  # the Server header goes out on every answer: keep it short

    def date_time_string(self, timestamp=None):
        return ""

    def send_header(self, keyword, value):
        if keyword == "Date":
            return
        super().send_header(keyword, value)

    def do_GET(self):
        auth = self.headers.get("Authorization") or ""
        if not hmac.compare_digest(auth.encode(), f"Bearer {self.token}".encode()):
            time.sleep(1)  # slows down guessing
            return self._send(401)
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}

        def num(name, default):
            try:
                return int(q.get(name, default))
            except ValueError:
                return default
        if u.path == "/api/export":
            body = self.exporter.export(num("since", 0), q.get("boot", ""))
            return self._send(304) if body is None else self._send(200, body.encode("utf-8"))
        if u.path == "/api/live":
            body = self.exporter.live(num("after", -1), q.get("boot", ""), num("wait", LIVE_WAIT_S))
            return self._send(200, json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        if u.path == "/api/ping":
            return self._send(200, b'{"ok":true}')
        return self._send(404)


def agent_server(host: str, port: int, exporter: Exporter, token: str) -> ThreadingHTTPServer:
    AgentHandler.exporter = exporter
    AgentHandler.token = token
    srv = ThreadingHTTPServer((host, port), AgentHandler)
    srv.daemon_threads = True
    return srv


# ============================================================================
# client side (the panel)
# ============================================================================

STATE_DIR = runtime.CACHE / "remote"


def _month() -> str:
    return time.strftime("%Y-%m")


class Conn:
    """One kept-alive HTTP(S) connection to an agent. Counts the bytes that crossed the wire
    (the body as sent, the headers, plus an estimate for the request)."""

    def __init__(self, url: str, token: str):
        u = urlparse(url.rstrip("/"))
        self.https = u.scheme == "https"
        self.host = u.hostname or ""
        self.port = u.port or (443 if self.https else 80)
        self.base = u.path or ""
        self.token = token
        self.c = None

    def close(self):
        if self.c is not None:
            try:
                self.c.close()
            except Exception:  # noqa: BLE001
                pass
            self.c = None

    def get(self, path: str, timeout: float) -> tuple[int, bytes, int]:
        for attempt in (0, 1):
            try:
                if self.c is None:
                    cls = http.client.HTTPSConnection if self.https else http.client.HTTPConnection
                    self.c = cls(self.host, self.port, timeout=timeout)
                    self.c.connect()
                self.c.sock.settimeout(timeout)
                url = self.base + path
                headers = {"Authorization": f"Bearer {self.token}", "Accept-Encoding": "gzip"}
                self.c.request("GET", url, headers=headers)
                r = self.c.getresponse()
                raw = r.read()
                wire = len(raw) + sum(len(k) + len(v) + 4 for k, v in r.getheaders()) + 17 \
                    + len(url) + sum(len(k) + len(v) + 4 for k, v in headers.items()) + 40 + len(self.host)
                if (r.getheader("Connection") or "").lower() == "close":
                    self.close()
                if r.getheader("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return r.status, raw, wire
            except (http.client.HTTPException, OSError):
                self.close()  # a kept-alive connection the other side already closed: once more
                if attempt:
                    raise
        raise OSError("unreachable")


class Machine:
    def __init__(self, cfg: dict):
        self.id = cfg["id"]
        self.file = STATE_DIR / f"{self.id}.json"
        self.lock = threading.Lock()
        self.cfg = cfg
        self.data = {"boot": "", "rev": 0, "tz": 0, "tables": {}, "blobs": {}, "bytes": {}}
        try:
            self.data.update(json.loads(self.file.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            pass
        self.error = None
        self.last_ok = self.data.get("last_ok")
        self.interval = SYNC_ACTIVE_S
        self.next_at = 0.0
        self.conn: Conn | None = None
        self.live_thread: threading.Thread | None = None
        self.live_state = "off"

    # --- traffic
    def add_bytes(self, n: int) -> None:
        with self.lock:
            b = self.data.setdefault("bytes", {})
            m = _month()
            b[m] = b.get(m, 0) + n
            for k in sorted(b)[:-3]:   # keeps the last 3 months
                del b[k]

    def month_bytes(self) -> int:
        return int((self.data.get("bytes") or {}).get(_month(), 0))

    def budget(self) -> int:
        try:
            mb = float(self.cfg.get("budget_mb") or DEFAULT_BUDGET_MB)
        except (TypeError, ValueError):
            mb = DEFAULT_BUDGET_MB
        return int(mb * 1_000_000)

    def over_budget(self) -> bool:
        return self.month_bytes() >= self.budget()

    def save(self) -> None:
        with self.lock:
            text = json.dumps(self.data, ensure_ascii=False, separators=(",", ":"))
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = self.file.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, self.file)

    def connection(self) -> Conn:
        if self.conn is None or self.conn.token != self.cfg.get("token") or self.conn.host != (urlparse(self.cfg["url"]).hostname or ""):
            if self.conn:
                self.conn.close()
            self.conn = Conn(self.cfg["url"], self.cfg.get("token") or "")
        return self.conn

    # --- totals
    def sync(self) -> bool:
        """One check. True when the totals changed."""
        now = time.time()
        if self.over_budget():
            self.error = "budget"
            self.next_at = now + 3600
            return False
        q = f"/api/export?since={int(self.data.get('rev') or 0)}&boot={quote(self.data.get('boot') or '')}"
        try:
            status, body, wire = self.connection().get(q, timeout=60)
        except Exception as e:  # noqa: BLE001
            self.error = f"offline: {type(e).__name__}"
            self.interval = min(max(self.interval, SYNC_ACTIVE_S) * 2, SYNC_IDLE_MAX_S)
            self.next_at = now + self.interval
            return False
        self.add_bytes(wire)
        if status == 401:
            self.error = "token"
            self.next_at = now + SYNC_IDLE_MAX_S
            self.save()
            return False
        if status not in (200, 304):
            self.error = f"HTTP {status}"
            self.next_at = now + SYNC_ACTIVE_S
            return False
        self.error = None
        self.last_ok = self.data["last_ok"] = now
        if status == 304:
            self.interval = min(self.interval * 2, SYNC_IDLE_MAX_S)
            self.next_at = now + self.interval
            self.save()
            return False
        self.apply(json.loads(body))
        self.interval = SYNC_ACTIVE_S
        self.next_at = now + self.interval
        self.save()
        return True

    def apply(self, d: dict) -> None:
        with self.lock:
            tables = {} if d.get("full") else self.data.setdefault("tables", {})
            for t, keys in (d.get("gone") or {}).items():
                for k in keys:
                    (tables.get(t) or {}).pop(k, None)
            for t, rows in (d.get("tables") or {}).items():
                if t not in TABLES:
                    continue
                cols = TABLES[t][1]
                dest = tables.setdefault(t, {})
                for r in rows:
                    dest[_key(r, cols)] = r
            blobs = {} if d.get("full") else self.data.setdefault("blobs", {})
            blobs.update(d.get("blobs") or {})
            self.data.update(tables=tables, blobs=blobs, boot=d.get("boot", ""), rev=int(d.get("rev") or 0),
                             tz=int(d.get("tz") or 0))

    # --- live office
    def live_loop(self, owner: "Remote") -> None:
        import live
        url, token = self.cfg["url"], self.cfg.get("token") or ""
        conn = Conn(url, token)
        seq, boot, pause = -1, "", 0.0
        try:
            while (not owner.stopping.is_set() and self.cfg.get("live") and owner.machines.get(self.id) is self
                   and self.cfg.get("url") == url and (self.cfg.get("token") or "") == token):
                if time.time() - owner.watched_at > WATCH_S:
                    live.drop_remote(self.id)
                    self.live_state = "idle"
                    seq = -1   # coming back later: only the sessions, not what happened meanwhile
                    conn.close()
                    owner.stopping.wait(1)
                    continue
                if self.over_budget():
                    live.drop_remote(self.id)
                    self.live_state = "budget"
                    owner.stopping.wait(60)
                    continue
                t0 = time.time()
                try:
                    status, body, wire = conn.get(f"/api/live?after={seq}&boot={quote(boot)}&wait={LIVE_WAIT_S}",
                                                  timeout=LIVE_WAIT_S + 20)
                    self.add_bytes(wire)
                    if status != 200:
                        raise OSError(f"HTTP {status}")
                    d = json.loads(body)
                    boot, seq = d.get("boot", ""), int(d.get("seq") or 0)
                    live.inject_remote(self.id, self.cfg.get("name") or self.id, d.get("sessions") or [], d.get("events") or [])
                    self.live_state = "on"
                    pause = 0.0
                except Exception as e:  # noqa: BLE001
                    live.drop_remote(self.id)
                    self.live_state = f"offline: {type(e).__name__}"
                    conn.close()
                    pause = min(max(pause * 2, 5.0), 60.0)
                    owner.stopping.wait(pause)
                    continue
                owner.stopping.wait(max(0.0, LIVE_GAP_S - (time.time() - t0)))
        finally:
            conn.close()
            live.drop_remote(self.id)
            self.live_state = "off"

    def info(self) -> dict:
        return {"id": self.id, "name": self.cfg.get("name") or self.id, "ok": self.error is None and bool(self.last_ok),
                "error": self.error, "last_ok": self.last_ok, "bytes_month": self.month_bytes(),
                "budget": self.budget(), "live": bool(self.cfg.get("live")), "live_state": self.live_state,
                "next_check": self.next_at, "rows": sum(len(v) for v in (self.data.get("tables") or {}).values())}


class Remote:
    def __init__(self):
        self.machines: dict[str, Machine] = {}
        self.stopping = threading.Event()
        self.kick_ev = threading.Event()
        self.watched_at = 0.0
        self.on_change = lambda: None
        self._hours: dict[tuple, str] = {}

    def configure(self, items: list[dict]) -> None:
        want = {m["id"]: m for m in items if m.get("id") and m.get("url")}
        for mid in list(self.machines):
            if mid not in want:
                old = self.machines.pop(mid)
                if old.conn:
                    old.conn.close()
                try:
                    old.file.unlink()
                except OSError:
                    pass
        for mid, cfg in want.items():
            m = self.machines.get(mid)
            if m is None:
                self.machines[mid] = Machine(cfg)
            else:
                if cfg.get("url") != m.cfg.get("url"):
                    m.data.update(boot="", rev=0, tables={}, blobs={})   # another machine: start over
                m.cfg = cfg
                m.next_at = 0
                m.error = None
        self.kick()

    def kick(self) -> None:
        for m in self.machines.values():
            m.next_at = 0
        self.kick_ev.set()

    def watching(self) -> None:
        self.watched_at = time.time()

    def loop(self) -> None:
        while not self.stopping.is_set():
            changed = False
            for m in list(self.machines.values()):
                try:
                    if time.time() >= m.next_at:
                        changed = m.sync() or changed
                    if m.cfg.get("live") and (m.live_thread is None or not m.live_thread.is_alive()):
                        m.live_thread = threading.Thread(target=m.live_loop, args=(self,), daemon=True)
                        m.live_thread.start()
                except Exception:  # noqa: BLE001
                    traceback.print_exc()
            if changed:
                try:
                    self.on_change()
                except Exception:  # noqa: BLE001
                    traceback.print_exc()
            self.kick_ev.wait(5)
            self.kick_ev.clear()

    def start(self, items: list[dict], on_change) -> None:
        self.on_change = on_change
        self.configure(items)
        threading.Thread(target=self.loop, daemon=True).start()

    def save_all(self) -> None:
        for m in self.machines.values():
            try:
                m.save()
            except Exception:  # noqa: BLE001
                pass

    # --- merging into the snapshot
    def _hour(self, h: str, tz: int) -> str:
        """The agent's local hour -> this machine's local hour."""
        k = (h, tz)
        out = self._hours.get(k)
        if out is None:
            try:
                ts = calendar.timegm(time.strptime(h[:13], "%Y-%m-%dT%H")) - tz
                out = collector.hour_key(ts)
            except ValueError:
                out = h
            if len(self._hours) > 100_000:
                self._hours.clear()
            self._hours[k] = out
        return out

    def merge(self, local: dict) -> dict:
        """The local snapshot plus every machine's rows (marked with "machine"). The local
        snapshot is not changed: the collector hands it out again when nothing is new."""
        out = dict(local)
        out["machines"] = [m.info() for m in self.machines.values()]
        withdata = [m for m in self.machines.values() if m.data.get("tables")]
        if not withdata:
            return out
        copied = set()
        for t, (path, _cols) in TABLES.items():
            extra = []
            for m in withdata:
                name, tz = m.cfg.get("name") or m.id, int(m.data.get("tz") or 0)
                for r in (m.data["tables"].get(t) or {}).values():
                    r2 = dict(r, machine=name)
                    if "hour" in r2:
                        r2["hour"] = self._hour(r2["hour"], tz)
                    extra.append(r2)
            if not extra:
                continue
            if len(path) == 2:
                if path[0] not in copied:
                    out[path[0]] = dict(out.get(path[0]) or {})
                    copied.add(path[0])
                out[path[0]][path[1]] = list(out[path[0]].get(path[1]) or []) + extra
            else:
                out[path[0]] = list(out.get(path[0]) or []) + extra
        if any("sessions" in (m.data["tables"] or {}) for m in withdata):
            out["sessions"] = sorted(out["sessions"], key=lambda s: s.get("end") or 0, reverse=True)
        for key in ("tools", "shell_commands"):
            merged = {ag: dict(v) for ag, v in (out.get(key) or {}).items()}
            for m in withdata:
                for ag, counts in ((m.data.get("blobs") or {}).get(key) or {}).items():
                    dest = merged.setdefault(ag, {})
                    for n, c in (counts or {}).items():
                        dest[n] = dest.get(n, 0) + c
            out[key] = {ag: dict(sorted(v.items(), key=lambda x: -x[1])[:40]) for ag, v in merged.items()}
        by_model = dict(_get(out, ("prices", "by_model")) or {})
        for m in withdata:
            for model, p in ((m.data.get("blobs") or {}).get("prices") or {}).items():
                by_model.setdefault(model, p)
        out["prices"] = dict(out.get("prices") or {}, by_model=by_model)
        return out


remote = Remote()


# ============================================================================
# settings
# ============================================================================

def clean_machines(items, current: list[dict]) -> list[dict]:
    """Validates the machines sent by the panel. An empty token keeps the saved one."""
    old = {m.get("id"): m for m in current or []}
    out = []
    for m in (items or [])[:10]:
        if not isinstance(m, dict):
            continue
        url = str(m.get("url") or "").strip()
        if not re.match(r"^https?://[^\s/]+", url):
            continue
        mid = str(m.get("id") or "")
        if not re.fullmatch(r"[a-z0-9]{6,16}", mid):
            mid = secrets.token_hex(4)
        prev = old.get(mid) or {}
        token = str(m.get("token") or "").strip() or prev.get("token") or ""
        try:
            budget = max(1.0, min(float(m.get("budget_mb") or DEFAULT_BUDGET_MB), 100_000.0))
        except (TypeError, ValueError):
            budget = DEFAULT_BUDGET_MB
        out.append({"id": mid, "name": (str(m.get("name") or "").strip() or "VPS")[:40], "url": url[:300],
                    "token": token[:200], "live": bool(m.get("live")), "budget_mb": budget})
    return out


def public(items: list[dict]) -> list[dict]:
    return [dict({k: v for k, v in m.items() if k != "token"}, has_token=bool(m.get("token"))) for m in items or []]
