"""Token Economy: local server. Opens at http://127.0.0.1:8765

Usage:  python server.py [--port 8765] [--interval 60] [--no-browser] [--demo]

--demo shows fictional data (port 8780 by default); see demo.py.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import traceback
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

if __name__ == "__main__" and "--demo" in sys.argv[1:]:
    import socket

    import demo
    _a = sys.argv[1:]
    _port = int(_a[_a.index("--port") + 1]) if "--port" in _a[:-1] else demo.PORT
    with socket.socket() as _s:  # check the port BEFORE rebuilding .cache-demo, which a running demo is using
        _s.settimeout(0.5)
        if _s.connect_ex(("127.0.0.1", _port)) == 0:
            sys.exit(f"Port {_port} is already in use. Choose another one with --port, e.g. --port {_port + 1}")
    demo.setup()  # fictional data; must run before the modules below read their paths

import ai  # noqa: E402
import cache_migration  # noqa: E402
import collector  # noqa: E402
import prices  # noqa: E402
import runtime  # noqa: E402
import score  # noqa: E402
import updater  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
CONFIG = runtime.CACHE / "config.json"


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
    if isinstance(new.get("auto_update"), bool):
        cfg["auto_update"] = new["auto_update"]
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
    if runtime.DEMO:
        cfg["demo"] = True
    return cfg


state = {"snapshot": None, "data": None, "status": "Starting…", "error": None, "collecting": False}
lock = threading.Lock()
request = threading.Event()
listeners = []  # functions called on every new collection (the tray app uses it)


def collect(force: bool = False):
    with lock:
        if state["collecting"]:
            return
        state["collecting"] = True
    try:
        def progress(msg):
            state["status"] = msg

        snap = collector.collect(progress, force)
        if snap is state["data"]:  # nothing new: the same snapshot is still being served
            state["status"] = "ok"
            return
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


def limit_level() -> float:
    """Tightest plan limit right now, in % (the office's alarm lamp; same rule as the tray icon):
    a window that runs out before it resets counts as at least 70%."""
    wins = (((state["data"] or {}).get("limits") or {}).get("windows")) or []
    worst = 0.0
    for j in wins:
        try:
            worst = max(worst, float(j.get("pct") or 0), 70.0 if j.get("runs_out_before_reset") else 0.0)
        except (TypeError, ValueError, AttributeError):
            continue
    return worst


stopping = threading.Event()


def loop(interval: int):
    force = True
    while not stopping.is_set():
        collect(force)
        # woken by a request (refresh button, new price table): rebuilds even with no new data
        force = request.wait(interval)
        request.clear()


def stop(timeout: float = 90) -> None:
    """Ends the collection loop and waits for a collection in progress, so a restart never
    has two processes writing .cache/ at the same time."""
    stopping.set()
    request.set()
    end = time.time() + timeout
    while state["collecting"] and time.time() < end:
        time.sleep(0.2)
    try:
        collector.flush()  # the index is kept in memory and saved every few minutes
    except Exception:  # noqa: BLE001
        traceback.print_exc()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(STATIC), **kw)

    def log_message(self, *_):
        pass

    def end_headers(self):
        # pages and scripts: the browser checks for a newer file on every load (a cheap 304
        # when unchanged), so an update shows up without an old office.js stuck in its cache
        if not self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def _json(self, body: bytes, code: int = 200):
        if runtime.DEMO:
            body = _demo_mask(body)
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
            body = _demo_mask(txt.encode("utf-8")) if runtime.DEMO else txt.encode("utf-8")
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
        if self.path.startswith("/api/update"):
            return self._json(json.dumps(updater.check(force="force=1" in self.path)).encode("utf-8"))
        if self.path.startswith("/api/live"):
            if runtime.DEMO:  # the office page runs its own simulation in demo mode
                return self._json(b'{"demo":true}')
            import live
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            try:
                after = int((q.get("after") or ["0"])[0])
            except ValueError:
                after = 0
            body = live.feed(after)
            body["limit"] = limit_level()
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
            if runtime.DEMO:  # demo mode runs no AI
                return self._json(b'{"error":"demo"}', 403)
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
        if self.path.startswith("/api/update/apply"):
            try:
                res = updater.apply()
                if res.get("updated"):
                    res["restart"] = updater.restart_soon()  # after this answer reaches the panel
                return self._json(json.dumps(res).encode("utf-8"))
            except Exception as e:  # noqa: BLE001
                return self._json(json.dumps({"error": str(e)}).encode("utf-8"), 409)
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


def _demo_mask(body: bytes) -> bytes:
    """Demo mode: shows the fake home folder as a fictional user folder (see demo.mask)."""
    import demo
    return demo.mask(body.decode("utf-8")).encode("utf-8")


class Server(ThreadingHTTPServer):
    """Binds the port exclusively. Python's default (SO_REUSEADDR) lets a second server take a
    port that is already in use on Windows, and requests then reach the wrong program.
    On macOS/Linux SO_REUSEADDR never shares a listening port; it only lets a restart bind
    right away instead of waiting a minute for the old socket to clear, so it stays on there."""
    allow_reuse_address = sys.platform != "win32"

    def server_bind(self):
        import socket
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def start(port: int = 8765, interval: int = 60) -> ThreadingHTTPServer:
    """Starts the server and the collection in background threads. Used by the tray app."""
    srv = Server(("127.0.0.1", port), Handler)
    cache_migration.migrate()  # only once the port is ours: no other instance is using .cache/
    threading.Thread(target=loop, args=(interval,), daemon=True).start()
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=None, help="default 8765 (8780 with --demo)")
    ap.add_argument("--interval", type=int, default=60, help="seconds between collections")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--demo", action="store_true", help="fictional data, for screenshots and trying the panel out")
    args = ap.parse_args()
    port = args.port or (8780 if args.demo else 8765)
    try:
        srv = Server(("127.0.0.1", port), Handler)
    except OSError:
        sys.exit(f"Port {port} is already in use. Choose another one with --port, e.g. --port {port + 1}")
    cache_migration.migrate()  # only once the port is ours: no other instance is using .cache/
    threading.Thread(target=loop, args=(args.interval,), daemon=True).start()
    url = f"http://127.0.0.1:{port}"
    print(f"Token Economy{' (demo data)' if args.demo else ''}: {url}  (Ctrl+C)")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    restart = threading.Event()

    def request_restart():
        restart.set()
        srv.shutdown()  # serve_forever below returns, and main restarts the process

    updater.start_auto(request_restart)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    srv.server_close()
    if not restart.is_set():
        stop(30)  # Ctrl+C: saves the index kept in memory
    if restart.is_set():
        stop()
        print("Token Economy was updated; restarting...", flush=True)
        argv = [sys.executable, str(Path(__file__).resolve()), *[a for a in sys.argv[1:] if a != "--no-browser"], "--no-browser"]
        if sys.platform == "win32":
            # Windows has no real exec: run the new version in this same console and wait for it,
            # so start.bat's "pause" and the window stay with the running server
            import subprocess
            try:
                sys.exit(subprocess.call(argv))
            except KeyboardInterrupt:
                sys.exit(0)
        os.execv(sys.executable, argv)


if __name__ == "__main__":
    main()
