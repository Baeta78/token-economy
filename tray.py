"""Token Economy na bandeja do Windows.

- Mouse em cima: resumo do dia e dos limites.
- Clique: abre o painel numa janela própria.
- Botão direito: atualizar, iniciar com o Windows, sair.

Rode com pythonw (sem janela de terminal):  pythonw tray.py
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
PORTA = 8765
URL = f"http://127.0.0.1:{PORTA}"
NOME = "Token Economy"
LOG = BASE / ".cache" / "tray.log"
CONFIG = BASE / ".cache" / "config.json"
STARTUP_DIR = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
STARTUP = STARTUP_DIR / f"{NOME}.vbs"
STARTUP_ANTIGOS = [STARTUP_DIR / "Painel de tokens.vbs", STARTUP_DIR / "Token Panel.vbs"]  # nomes anteriores

TXT = {
    "pt": {
        "abrir": "Abrir painel", "atualizar": "Atualizar agora", "autostart": "Iniciar com o Windows", "sair": "Sair",
        "lendo": "Lendo os registros…", "semLimite": "Sem leitura de limites", "sem": "sem",
        "codex5h": "Codex 5h {p}% (zera {h}h{m}) · sem {s}%", "codexLivre": "Codex 5h livre · semana {s}%",
        "hoje": "Hoje: {n} tokens novos", "semUso": "sem uso hoje", "rtk": "RTK poupou {n} hoje",
        "mil": "mil", "mi": "mi", "bi": "bi", "dec": ",",
    },
    "en": {
        "abrir": "Open panel", "atualizar": "Refresh now", "autostart": "Start with Windows", "sair": "Quit",
        "lendo": "Reading logs…", "semLimite": "No limit readings", "sem": "wk",
        "codex5h": "Codex 5h {p}% (resets {h}h{m}) · wk {s}%", "codexLivre": "Codex 5h free · week {s}%",
        "hoje": "Today: {n} new tokens", "semUso": "no usage today", "rtk": "RTK saved {n} today",
        "mil": "K", "mi": "M", "bi": "B", "dec": ".",
    },
    "es": {
        "abrir": "Abrir panel", "atualizar": "Actualizar ahora", "autostart": "Iniciar con Windows", "sair": "Salir",
        "lendo": "Leyendo registros…", "semLimite": "Sin lectura de límites", "sem": "sem",
        "codex5h": "Codex 5h {p}% (reinicia {h}h{m}) · sem {s}%", "codexLivre": "Codex 5h libre · semana {s}%",
        "hoje": "Hoy: {n} tokens nuevos", "semUso": "sin uso hoy", "rtk": "RTK ahorró {n} hoy",
        "mil": "mil", "mi": "M", "bi": "mil M", "dec": ",",
    },
}


def idioma() -> str:
    """Língua escolhida no painel; na primeira vez, a do Windows."""
    try:
        lang = json.loads(CONFIG.read_text(encoding="utf-8")).get("idioma")
        if lang in TXT:
            return lang
    except Exception:  # noqa: BLE001
        pass
    try:
        prim = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
        return {0x16: "pt", 0x0A: "es"}.get(prim, "en")
    except Exception:  # noqa: BLE001
        return "en"


def tr(chave: str, **kw) -> str:
    s = TXT[idioma()].get(chave) or TXT["en"][chave]
    return s.format(**kw) if kw else s

CORES = {
    "cinza": (122, 121, 116),
    "verde": (12, 163, 12),
    "amarelo": (214, 150, 0),
    "laranja": (236, 131, 90),
    "vermelho": (208, 59, 59),
}


def log(msg: str) -> None:
    try:
        LOG.parent.mkdir(exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
    except OSError:
        pass


# ----------------------------------------------------------------------------
# instância única
# ----------------------------------------------------------------------------

def ja_rodando() -> bool:
    ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\TokenEconomyTray")
    return ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


# ----------------------------------------------------------------------------
# abrir o painel
# ----------------------------------------------------------------------------

def navegador_app() -> str | None:
    candidatos = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    for c in candidatos:
        if os.path.exists(c):
            return c
    return shutil.which("msedge") or shutil.which("chrome")


def abrir_painel(*_):
    exe = navegador_app()
    try:
        if exe:
            # modo app: janela própria, sem abas nem barra de endereço
            subprocess.Popen([exe, f"--app={URL}", "--window-size=1440,920"], creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
            return
    except OSError as e:
        log(f"falha ao abrir em modo app: {e}")
    webbrowser.open(URL)


# ----------------------------------------------------------------------------
# resumo
# ----------------------------------------------------------------------------

def compacto(n: float) -> str:
    n = float(n or 0)
    sep = " " if idioma() != "en" else ""
    for div, chave, casas in ((1e9, "bi", 1), (1e6, "mi", 1), (1e3, "mil", 0)):
        if n >= div:
            return f"{n / div:.{casas}f}".replace(".", tr("dec")) + sep + tr(chave)
    return f"{n:.0f}"


def novos(r: dict) -> float:
    return (r.get("input") or 0) + (r.get("cache_write") or 0) + (r.get("output") or 0)


def resumo(d: dict) -> tuple[str, str, list[str]]:
    """Devolve (texto do balão até 127 caracteres, cor do ícone, linhas para o menu)."""
    agora = time.time()
    hoje = dt.datetime.now().strftime("%Y-%m-%d")
    nomes = d.get("agentes") or {}

    # limites: uma linha por agente com todas as janelas dele (Claude, Codex, …)
    jans = (d.get("limites") or {}).get("janelas") or []
    curtos_jan = {"five_hour": "5h", "seven_day": tr("sem"), "seven_day_opus": "Opus", "seven_day_sonnet": "Sonnet", "seven_day_fable": "Fable"}
    por_agente: dict[str, list[str]] = {}
    pior = 0.0
    for j in jans:
        pct = float(j.get("pct") or 0)
        rotulo = curtos_jan.get(j["id"], j["id"].replace("seven_day_", "").replace("_", " "))
        txt = f"{rotulo} {pct:.0f}%"
        if j.get("reset") and j["id"] == "five_hour":
            falta = max(0, j["reset"] - agora)
            txt += f" ({int(falta // 3600)}h{int(falta % 3600 // 60):02d})"
        por_agente.setdefault(j["agente"], []).append(txt)
        # uma janela que vai acabar antes de zerar conta como pelo menos 70%
        pior = max(pior, pct, 70.0 if j.get("acaba_antes") else 0.0)
    nomes_ag = {"claude": "Claude", "codex": "Codex"}
    l_lim = [f"{nomes_ag.get(a, a)}: " + " · ".join(v) for a, v in por_agente.items()] or [tr("semLimite")]

    # uso de hoje
    por_ag: dict[str, float] = {}
    for r in d.get("uso") or []:
        if r["hora"].startswith(hoje):
            por_ag[r["agente"]] = por_ag.get(r["agente"], 0) + novos(r)
    total = sum(por_ag.values())
    rtk_hoje = sum(r.get("saved") or 0 for r in (d.get("rtk") or {}).get("hora") or [] if r["hora"].startswith(hoje))

    # cor do ícone: a janela mais apertada de qualquer agente
    if not jans:
        cor = "cinza"
    elif pior >= 90:
        cor = "vermelho"
    elif pior >= 70:
        cor = "laranja"
    elif pior >= 50:
        cor = "amarelo"
    else:
        cor = "verde"

    curtos = {"claude": "Claude", "codex": "Codex", "opencode": "OpenCode", "ollama": "Ollama", "desconhecido": "?"}
    ordem = sorted(por_ag.items(), key=lambda x: -x[1])
    partes = " · ".join(f"{curtos.get(a, a)} {100 * v / total:.0f}%" for a, v in ordem[:3] if total) or tr("semUso")
    linhas = [*l_lim, tr("hoje", n=compacto(total)), partes, tr("rtk", n=compacto(rtk_hoje))]
    # o Windows corta o texto do ícone em 127 caracteres: tira o título e depois as
    # últimas linhas até caber (os limites, que vêm primeiro, ficam)
    balao_linhas = [NOME, *linhas]
    while len("\n".join(balao_linhas)) > 127 and len(balao_linhas) > 1:
        balao_linhas.pop(0 if balao_linhas[0] == NOME else -1)
    return "\n".join(balao_linhas)[:127], cor, linhas


# ----------------------------------------------------------------------------
# ícone
# ----------------------------------------------------------------------------

def desenhar_icone(cor: str) -> Image.Image:
    """Mesmo desenho do logo (moeda com barras descendo), na cor do status dos limites."""
    s = 256  # desenha grande e reduz, para as bordas ficarem suaves
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    dr.ellipse((8, 8, s - 8, s - 8), fill=CORES[cor] + (255,))
    dr.ellipse((34, 34, s - 34, s - 34), outline=(255, 255, 255, 110), width=8)
    larg, gap, base = 34, 16, 186
    x0 = (s - (3 * larg + 2 * gap)) // 2
    for i, h in enumerate((112, 84, 56)):
        x = x0 + i * (larg + gap)
        dr.rounded_rectangle((x, base - h, x + larg, base), radius=larg // 2, fill=(255, 255, 255, 255))
    return img.resize((64, 64), Image.LANCZOS)


# ----------------------------------------------------------------------------
# iniciar com o Windows
# ----------------------------------------------------------------------------

def pythonw() -> str:
    exe = Path(sys.executable)
    w = exe.with_name("pythonw.exe")
    return str(w if w.exists() else exe)


def autostart_ativo(*_) -> bool:
    return STARTUP.exists()


def alternar_autostart(icon, _item):
    try:
        for antigo in STARTUP_ANTIGOS:
            if antigo.exists():
                antigo.unlink()
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
        self.linhas = [tr("lendo")]
        self.cor = "cinza"
        self.dados = None
        self.lang = idioma()
        self.icon = pystray.Icon(
            "token-economy",
            icon=desenhar_icone("cinza"),
            title=f"{NOME}\n{tr('lendo')}",
            menu=self.menu(),
        )

    def menu(self):
        def linha(i):
            return pystray.MenuItem(lambda _: self.linhas[i] if i < len(self.linhas) else "", None, enabled=False,
                                    visible=lambda _: i < len(self.linhas))

        # textos como funções: o menu acompanha a troca de idioma sem reiniciar
        return pystray.Menu(
            pystray.MenuItem(lambda _: tr("abrir"), abrir_painel, default=True),
            pystray.Menu.SEPARATOR,
            *[linha(i) for i in range(6)],
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda _: tr("atualizar"), self.atualizar_agora),
            pystray.MenuItem(lambda _: tr("autostart"), alternar_autostart, checked=autostart_ativo),
            pystray.MenuItem(lambda _: tr("sair"), self.sair),
        )

    def aplicar(self, d: dict):
        try:
            balao, cor, linhas = resumo(d)
            self.linhas = linhas
            self.icon.title = balao
            if cor != self.cor:
                self.cor = cor
                self.icon.icon = desenhar_icone(cor)
            self.icon.update_menu()
        except Exception:  # noqa: BLE001
            log(traceback.format_exc())

    def buscar(self) -> dict | None:
        try:
            with urllib.request.urlopen(URL + "/api/dados", timeout=20) as r:
                if r.status == 200:
                    return json.loads(r.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            return None
        return None

    def laco(self):
        ultimo, proxima_busca = 0, 0.0
        while True:
            agora = time.time()
            if agora >= proxima_busca:
                d = self.buscar()
                if d and d.get("gerado_em", 0) > ultimo:
                    ultimo = d["gerado_em"]
                    self.dados = d
                    self.aplicar(d)
                proxima_busca = agora + (30 if d else 5)
            # trocou o idioma no painel: refaz o texto na hora
            lang = idioma()
            if lang != self.lang:
                self.lang = lang
                if self.dados:
                    self.aplicar(self.dados)
                else:
                    self.icon.title = f"{NOME}\n{tr('lendo')}"
                    self.linhas = [tr("lendo")]
                    self.icon.update_menu()
            time.sleep(3)

    def atualizar_agora(self, *_):
        try:
            urllib.request.urlopen(urllib.request.Request(URL + "/api/atualizar", method="POST", headers={"X-Token-Panel": "1"}), timeout=5).close()
        except Exception:  # noqa: BLE001
            pass

    def sair(self, *_):
        self.icon.stop()

    def rodar(self):
        threading.Thread(target=self.laco, daemon=True).start()
        self.icon.run()


def main():
    os.chdir(BASE)
    if ja_rodando():
        abrir_painel()
        return
    try:
        import server

        server.iniciar(PORTA, 60)
    except OSError:
        # porta ocupada: provavelmente o server.py já está rodando sozinho; usa ele
        log("porta ocupada, usando o servidor que já está no ar")
    App().rodar()


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001
        log(traceback.format_exc())
        raise
