"""Token Economy in the Windows tray.

- Mouse over: summary of the day and of the limits.
- Click: opens the panel in its own window.
- Right click: refresh, start with Windows, quit.

Run it with pythonw (no terminal window):  pythonw tray.py
"""
from __future__ import annotations

import ctypes
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path

import pystray
from PIL import Image, ImageDraw

BASE = Path(__file__).resolve().parent
PORT = 8765
URL = f"http://127.0.0.1:{PORT}"
NAME = "Token Economy"
LOG = BASE / ".cache" / "tray.log"
CONFIG = BASE / ".cache" / "config.json"
STARTUP_DIR = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
STARTUP = STARTUP_DIR / f"{NAME}.vbs"
STARTUP_OLD = [STARTUP_DIR / "Painel de tokens.vbs", STARTUP_DIR / "Token Panel.vbs"]  # earlier names

TXT = {
    "pt": {
        "open": "Abrir painel", "refresh": "Atualizar agora", "autostart": "Iniciar com o Windows", "quit": "Sair",
        "reading": "Lendo os registros…", "noLimits": "Sem leitura de limites", "week": "sem",
        "codex5h": "Codex 5h {p}% (zera {h}h{m}) · sem {s}%", "codexFree": "Codex 5h livre · semana {s}%",
        "today": "Hoje: {n} tokens novos", "noUsage": "sem uso hoje", "rtk": "RTK poupou {n} hoje",
        "thousand": "mil", "million": "mi", "billion": "bi", "dec": ",",
    },
    "en": {
        "open": "Open panel", "refresh": "Refresh now", "autostart": "Start with Windows", "quit": "Quit",
        "reading": "Reading logs…", "noLimits": "No limit readings", "week": "wk",
        "codex5h": "Codex 5h {p}% (resets {h}h{m}) · wk {s}%", "codexFree": "Codex 5h free · week {s}%",
        "today": "Today: {n} new tokens", "noUsage": "no usage today", "rtk": "RTK saved {n} today",
        "thousand": "K", "million": "M", "billion": "B", "dec": ".",
    },
    "es": {
        "open": "Abrir panel", "refresh": "Actualizar ahora", "autostart": "Iniciar con Windows", "quit": "Salir",
        "reading": "Leyendo registros…", "noLimits": "Sin lectura de límites", "week": "sem",
        "codex5h": "Codex 5h {p}% (reinicia {h}h{m}) · sem {s}%", "codexFree": "Codex 5h libre · semana {s}%",
        "today": "Hoy: {n} tokens nuevos", "noUsage": "sin uso hoy", "rtk": "RTK ahorró {n} hoy",
        "thousand": "mil", "million": "M", "billion": "mil M", "dec": ",",
    },
}


def language() -> str:
    """Language chosen in the panel; the first time, the Windows one."""
    try:
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        lang = cfg.get("language") or cfg.get("idioma")  # "idioma": key used before the English translation
        if lang in TXT:
            return lang
    except Exception:  # noqa: BLE001
        pass
    try:
        prim = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
        return {0x16: "pt", 0x0A: "es"}.get(prim, "en")
    except Exception:  # noqa: BLE001
        return "en"


def tr(key: str, **kw) -> str:
    s = TXT[language()].get(key) or TXT["en"][key]
    return s.format(**kw) if kw else s

COLORS = {
    "gray": (122, 121, 116),
    "green": (12, 163, 12),
    "yellow": (214, 150, 0),
    "orange": (236, 131, 90),
    "red": (208, 59, 59),
}


def log(msg: str) -> None:
    try:
        LOG.parent.mkdir(exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
    except OSError:
        pass


# ----------------------------------------------------------------------------
# single instance
# ----------------------------------------------------------------------------

def already_running() -> bool:
    ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\TokenEconomyTray")
    return ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


# ----------------------------------------------------------------------------
# opening the panel
# ----------------------------------------------------------------------------

def app_browser() -> str | None:
    candidates = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return shutil.which("msedge") or shutil.which("chrome")


def open_panel(*_):
    exe = app_browser()
    try:
        if exe:
            # app mode: its own window, with no tabs or address bar
            subprocess.Popen([exe, f"--app={URL}", "--window-size=1440,920"], creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
            return
    except OSError as e:
        log(f"failed to open in app mode: {e}")
    webbrowser.open(URL)


# ----------------------------------------------------------------------------
# summary
# ----------------------------------------------------------------------------

def compact(n: float) -> str:
    n = float(n or 0)
    sep = " " if language() != "en" else ""
    for div, key, places in ((1e9, "billion", 1), (1e6, "million", 1), (1e3, "thousand", 0)):
        if n >= div:
            return f"{n / div:.{places}f}".replace(".", tr("dec")) + sep + tr(key)
    return f"{n:.0f}"


def new_tokens(r: dict) -> float:
    return (r.get("input") or 0) + (r.get("cache_write") or 0) + (r.get("output") or 0)


def summary(d: dict) -> tuple[str, str, list[str]]:
    """Returns (tooltip text up to 127 characters, icon color, lines for the menu)."""
    now = time.time()
    today = dt.datetime.now().strftime("%Y-%m-%d")
    names = d.get("agents") or {}

    # limits: one line per agent with all of its windows (Claude, Codex, …)
    wins = (d.get("limits") or {}).get("windows") or []
    short_win = {"five_hour": "5h", "seven_day": tr("week"), "seven_day_opus": "Opus", "seven_day_sonnet": "Sonnet", "seven_day_fable": "Fable"}
    by_agent: dict[str, list[str]] = {}
    worst = 0.0
    for j in wins:
        pct = float(j.get("pct") or 0)
        label = short_win.get(j["id"], j["id"].replace("seven_day_", "").replace("_", " "))
        txt = f"{label} {pct:.0f}%"
        if j.get("reset") and j["id"] == "five_hour":
            left = max(0, j["reset"] - now)
            txt += f" ({int(left // 3600)}h{int(left % 3600 // 60):02d})"
        by_agent.setdefault(j["agent"], []).append(txt)
        # a window that will run out before it resets counts as at least 70%
        worst = max(worst, pct, 70.0 if j.get("runs_out_before_reset") else 0.0)
    agent_names = {"claude": "Claude", "codex": "Codex"}
    limit_lines = [f"{agent_names.get(a, a)}: " + " · ".join(v) for a, v in by_agent.items()] or [tr("noLimits")]

    # today's usage
    per_agent: dict[str, float] = {}
    for r in d.get("usage") or []:
        if r["hour"].startswith(today):
            per_agent[r["agent"]] = per_agent.get(r["agent"], 0) + new_tokens(r)
    total = sum(per_agent.values())
    rtk_today = sum(r.get("saved") or 0 for r in (d.get("rtk") or {}).get("hourly") or [] if r["hour"].startswith(today))

    # icon color: the tightest window of any agent
    if not wins:
        color = "gray"
    elif worst >= 90:
        color = "red"
    elif worst >= 70:
        color = "orange"
    elif worst >= 50:
        color = "yellow"
    else:
        color = "green"

    short = {"claude": "Claude", "codex": "Codex", "opencode": "OpenCode", "ollama": "Ollama", "unknown": "?"}
    order = sorted(per_agent.items(), key=lambda x: -x[1])
    parts = " · ".join(f"{short.get(a, a)} {100 * v / total:.0f}%" for a, v in order[:3] if total) or tr("noUsage")
    lines = [*limit_lines, tr("today", n=compact(total)), parts, tr("rtk", n=compact(rtk_today))]
    # Windows cuts the icon text at 127 characters: drop the title and then the
    # last lines until it fits (the limits, which come first, stay)
    tip_lines = [NAME, *lines]
    while len("\n".join(tip_lines)) > 127 and len(tip_lines) > 1:
        tip_lines.pop(0 if tip_lines[0] == NAME else -1)
    return "\n".join(tip_lines)[:127], color, lines


# ----------------------------------------------------------------------------
# icon
# ----------------------------------------------------------------------------

def draw_icon(color: str) -> Image.Image:
    """Same drawing as the logo (coin with descending bars), in the color of the limits status."""
    s = 256  # draws large and scales down, so the edges are smooth
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    dr.ellipse((8, 8, s - 8, s - 8), fill=COLORS[color] + (255,))
    dr.ellipse((34, 34, s - 34, s - 34), outline=(255, 255, 255, 110), width=8)
    width, gap, base = 34, 16, 186
    x0 = (s - (3 * width + 2 * gap)) // 2
    for i, h in enumerate((112, 84, 56)):
        x = x0 + i * (width + gap)
        dr.rounded_rectangle((x, base - h, x + width, base), radius=width // 2, fill=(255, 255, 255, 255))
    return img.resize((64, 64), Image.LANCZOS)


# ----------------------------------------------------------------------------
# start with Windows
# ----------------------------------------------------------------------------

def pythonw() -> str:
    exe = Path(sys.executable)
    w = exe.with_name("pythonw.exe")
    return str(w if w.exists() else exe)


def autostart_enabled(*_) -> bool:
    return STARTUP.exists()


def toggle_autostart(icon, _item):
    try:
        for old in STARTUP_OLD:
            if old.exists():
                old.unlink()
        if STARTUP.exists():
            STARTUP.unlink()
        else:
            STARTUP.parent.mkdir(parents=True, exist_ok=True)
            cmd = f'"{pythonw()}" "{BASE / "tray.py"}"'
            STARTUP.write_text(
                'Set sh = CreateObject("WScript.Shell")\r\n'
                f'sh.CurrentDirectory = "{BASE}"\r\n'
                f'sh.Run "{cmd.replace(chr(34), chr(34) * 2)}", 0, False\r\n',
                encoding="utf-16",
            )
    except OSError as e:
        log(f"autostart: {e}")
    icon.update_menu()


# ----------------------------------------------------------------------------
# app
# ----------------------------------------------------------------------------

class App:
    def __init__(self):
        self.lines = [tr("reading")]
        self.color = "gray"
        self.data = None
        self.lang = language()
        self.icon = pystray.Icon(
            "token-economy",
            icon=draw_icon("gray"),
            title=f"{NAME}\n{tr('reading')}",
            menu=self.menu(),
        )

    def menu(self):
        def line(i):
            return pystray.MenuItem(lambda _: self.lines[i] if i < len(self.lines) else "", None, enabled=False,
                                    visible=lambda _: i < len(self.lines))

        # texts as functions: the menu follows a language change without restarting
        return pystray.Menu(
            pystray.MenuItem(lambda _: tr("open"), open_panel, default=True),
            pystray.Menu.SEPARATOR,
            *[line(i) for i in range(6)],
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda _: tr("refresh"), self.refresh_now),
            pystray.MenuItem(lambda _: tr("autostart"), toggle_autostart, checked=autostart_enabled),
            pystray.MenuItem(lambda _: tr("quit"), self.quit),
        )

    def apply(self, d: dict):
        try:
            tip, color, lines = summary(d)
            self.lines = lines
            self.icon.title = tip
            if color != self.color:
                self.color = color
                self.icon.icon = draw_icon(color)
            self.icon.update_menu()
        except Exception:  # noqa: BLE001
            log(traceback.format_exc())

    def fetch(self) -> dict | None:
        try:
            with urllib.request.urlopen(URL + "/api/data", timeout=20) as r:
                if r.status == 200:
                    return json.loads(r.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            return None
        return None

    def loop(self):
        last, next_fetch = 0, 0.0
        while True:
            now = time.time()
            if now >= next_fetch:
                d = self.fetch()
                if d and d.get("generated_at", 0) > last:
                    last = d["generated_at"]
                    self.data = d
                    self.apply(d)
                next_fetch = now + (30 if d else 5)
            # the language was changed in the panel: redo the text right away
            lang = language()
            if lang != self.lang:
                self.lang = lang
                if self.data:
                    self.apply(self.data)
                else:
                    self.icon.title = f"{NAME}\n{tr('reading')}"
                    self.lines = [tr("reading")]
                    self.icon.update_menu()
            time.sleep(3)

    def refresh_now(self, *_):
        try:
            urllib.request.urlopen(urllib.request.Request(URL + "/api/refresh", method="POST", headers={"X-Token-Panel": "1"}), timeout=5).close()
        except Exception:  # noqa: BLE001
            pass

    def quit(self, *_):
        self.icon.stop()

    def run(self):
        threading.Thread(target=self.loop, daemon=True).start()
        self.icon.run()


def main():
    os.chdir(BASE)
    if already_running():
        open_panel()
        return
    try:
        import server

        server.start(PORT, 60)
    except OSError:
        # port in use: server.py is probably already running on its own; use it
        log("port in use, using the server that is already running")
    App().run()


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        log(traceback.format_exc())
        raise
