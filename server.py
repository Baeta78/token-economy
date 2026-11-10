"""Token Economy: local server. Opens at http://127.0.0.1:8765

Usage:  python server.py [--port 8765] [--interval 60] [--no-browser]
"""
from __future__ import annotations

import argparse
import json
import threading
import time
import traceback
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import ai
import cache_migration
import collector
import prices
import score

STATIC = Path(__file__).resolve().parent / "static"
CONFIG = Path(__file__).resolve().parent / ".cache" / "config.json"


def read_config() -> dict:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


AI_FIELDS = ("type", "cli", "api", "url", "model", "command", "days")


def write_config(new: dict) -> dict:
    cfg = read_config()
    if new.get("language") in ("pt", "en", "es"):
        cfg["language"] = new["language"]
    if isinstance(new.get("ai"), dict):
        current = cfg.get("ai") or {}
        for k in AI_FIELDS:
            if k in new["ai"]:
                current[k] = str(new["ai"][k])[:2000]
        # the key is only replaced when it comes filled in; it stays only in this local file
        if (new["ai"].get("key") or "").strip():
            current["key"] = new["ai"]["key"].strip()
        cfg["ai"] = current
    if isinstance(new.get("claude_limits"), bool):
        cfg["claude_limits"] = new["claude_limits"]
    if isinstance(new.get("subscriptions"), list):
        items = []
        for a in new["subscriptions"][:12]:
            try:
                monthly = float(a.get("monthly"))
            except (TypeError, ValueError, AttributeError):
                continue
            if monthly < 0:
                continue
            items.append({"name": str(a.get("name") or "")[:60], "agent": str(a.get("agent") or "")[:20], "monthly": round(monthly, 2)})
        cfg["subscriptions"] = items
    CONFIG.parent.mkdir(exist_ok=True)
    CONFIG.write_text(json.dumps(cfg), encoding="utf-8")
    return cfg

def public_config() -> dict:
    """Settings without the API key (it never leaves the file)."""
    cfg = read_config()
    if isinstance(cfg.get("ai"), dict):
        cfg["ai"] = {k: v for k, v in cfg["ai"].items() if k != "key"}
        cfg["ai"]["has_key"] = bool(read_config()["ai"].get("key"))
    return cfg


state = {"snapshot": None, "data": None, "status": "Starting…", "error": None, "collecting": False}
lock = threading.Lock()
request = threading.Event()
listeners = []  # functions called on every new collection (the tray app uses it)


def collect():
    with lock:
        if state["collecting"]:
            return
        state["collecting"] = True
    try:
        def progress(msg):
            state["status"] = msg

        snap = collector.collect(progress)
        state["snapshot"] = json.dumps(snap, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        state["data"] = snap
        state["status"] = "ok"
        state["error"] = None
        for fn in list(listeners):
            try:
                fn(snap)
            except Exception:  # noqa: BLE001
                traceback.print_exc()
    except Exception as e:  # noqa: BLE001
        state["error"] = f"{e}\n{traceback.format_exc()}"
        state["status"] = "error"
    finally:
        state["collecting"] = False


def loop(interval: int):
    while True:
        collect()
        request.wait(interval)
        request.clear()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(STATIC), **kw)

    def log_message(self, *_):
        pass

    def _json(self, body: bytes, code: int = 200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/data"):
            snap = state["snapshot"]
            if snap is None:
                body = json.dumps({"loading": True, "status": state["status"], "error": state["error"]}, ensure_ascii=False)
                return self._json(body.encode("utf-8"), 202)
            return self._json(snap)
        if self.path.startswith("/api/config"):
            return self._json(json.dumps(public_config()).encode("utf-8"))
        if self.path.startswith("/api/score"):
            if state["data"] is None:
                return self._json(b'{"loading":true}', 202)
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            end = float((q.get("end") or [time.time()])[0])
            start = float((q.get("start") or [end - 7 * 86400])[0])
            return self._json(json.dumps(score.compute(state["data"], start, end)).encode("utf-8"))
        if self.path.startswith("/api/ai/prompt"):
            if state["data"] is None:
                return self._json(b'{"error":"loading"}', 202)
            cfg = read_config()
            hist = ai.history()
            txt = ai.build_prompt(state["data"], cfg.get("language", "en"), int((cfg.get("ai") or {}).get("days") or 7), hist[0] if hist else None)
            body = txt.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith("/api/ai"):
            body = {"available": ai.available(), "history": ai.history()[:10], "state": ai.state,
                    "config": public_config().get("ai") or {}}
            return self._json(json.dumps(body, ensure_ascii=False).encode("utf-8"))
        if self.path.startswith("/api/status"):
            body = json.dumps({"status": state["status"], "collecting": state["collecting"], "error": state["error"]}, ensure_ascii=False)
            return self._json(body.encode("utf-8"))
        return super().do_GET()

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(min(n, 65536)) or b"{}")

    def do_POST(self):
        # only the panel's own page sends this header; other sites open in the
        # browser cannot (the browser requires a permission this server does not grant)
        if self.headers.get("X-Token-Panel") != "1":
            self.send_error(403)
            return
        if self.path.startswith("/api/ai/analyze"):
            if state["data"] is None:
                return self._json(b'{"error":"loading"}', 409)
            try:
                body = self._body()
                cfg = write_config({"ai": body, "language": body.get("language")})
                ai.analyze(state["data"], cfg.get("ai") or {}, cfg.get("language", "en"))
                return self._json(b'{"ok":true}', 202)
            except Exception as e:  # noqa: BLE001
                return self._json(json.dumps({"error": str(e)}).encode("utf-8"), 400)
        if self.path.startswith("/api/prices/refresh"):
            def job():
                prices.refresh(force=True)
                request.set()  # recomputes the values with the new table
            threading.Thread(target=job, daemon=True).start()
            return self._json(b'{"ok":true}', 202)
        if self.path.startswith("/api/refresh"):
            request.set()
            return self._json(b'{"ok":true}')
        if self.path.startswith("/api/config"):
            try:
                n = int(self.headers.get("Content-Length") or 0)
                write_config(json.loads(self.rfile.read(min(n, 4096)) or b"{}"))
                return self._json(json.dumps(public_config()).encode("utf-8"))
            except Exception:  # noqa: BLE001
                return self._json(b'{"error":"invalid config"}', 400)
        self.send_error(404)


def start(port: int = 8765, interval: int = 60) -> ThreadingHTTPServer:
    """Starts the server and the collection in background threads. Used by the tray app."""
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    cache_migration.migrate()  # only once the port is ours: no other instance is using .cache/
    threading.Thread(target=loop, args=(interval,), daemon=True).start()
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--interval", type=int, default=60, help="seconds between collections")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    cache_migration.migrate()  # only once the port is ours: no other instance is using .cache/
    threading.Thread(target=loop, args=(args.interval,), daemon=True).start()
    url = f"http://127.0.0.1:{args.port}"
    print(f"Token Economy: {url}  (Ctrl+C)")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
