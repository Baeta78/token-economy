"""Token Economy: servidor local. Abre em http://127.0.0.1:8765

Uso:  python server.py [--porta 8765] [--intervalo 60] [--sem-navegador]
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

import collector
import ia
import nota
import precos

STATIC = Path(__file__).resolve().parent / "static"
CONFIG = Path(__file__).resolve().parent / ".cache" / "config.json"


def ler_config() -> dict:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


CAMPOS_IA = ("tipo", "cli", "api", "url", "modelo", "comando", "dias")


def gravar_config(novo: dict) -> dict:
    cfg = ler_config()
    if novo.get("idioma") in ("pt", "en", "es"):
        cfg["idioma"] = novo["idioma"]
    if isinstance(novo.get("ia"), dict):
        atual = cfg.get("ia") or {}
        for k in CAMPOS_IA:
            if k in novo["ia"]:
                atual[k] = str(novo["ia"][k])[:2000]
        # a chave só é trocada quando vem preenchida; fica só neste arquivo local
        if (novo["ia"].get("chave") or "").strip():
            atual["chave"] = novo["ia"]["chave"].strip()
        cfg["ia"] = atual
    if isinstance(novo.get("limites_claude"), bool):
        cfg["limites_claude"] = novo["limites_claude"]
    if isinstance(novo.get("assinaturas"), list):
        lista = []
        for a in novo["assinaturas"][:12]:
            try:
                mensal = float(a.get("mensal"))
            except (TypeError, ValueError, AttributeError):
                continue
            if mensal < 0:
                continue
            lista.append({"nome": str(a.get("nome") or "")[:60], "agente": str(a.get("agente") or "")[:20], "mensal": round(mensal, 2)})
        cfg["assinaturas"] = lista
    CONFIG.parent.mkdir(exist_ok=True)
    CONFIG.write_text(json.dumps(cfg), encoding="utf-8")
    return cfg

def config_publica() -> dict:
    """Configuração sem a chave de API (nunca sai do arquivo)."""
    cfg = ler_config()
    if isinstance(cfg.get("ia"), dict):
        cfg["ia"] = {k: v for k, v in cfg["ia"].items() if k != "chave"}
        cfg["ia"]["tem_chave"] = bool(ler_config()["ia"].get("chave"))
    return cfg


estado = {"snapshot": None, "dados": None, "status": "Iniciando…", "erro": None, "coletando": False}
lock = threading.Lock()
pedido = threading.Event()
ouvintes = []  # funções chamadas a cada coleta nova (o app da bandeja usa)


def coletar():
    with lock:
        if estado["coletando"]:
            return
        estado["coletando"] = True
    try:
        def progresso(msg):
            estado["status"] = msg

        snap = collector.collect(progresso)
        estado["snapshot"] = json.dumps(snap, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        estado["dados"] = snap
        estado["status"] = "ok"
        estado["erro"] = None
        for fn in list(ouvintes):
            try:
                fn(snap)
            except Exception:  # noqa: BLE001
                traceback.print_exc()
    except Exception as e:  # noqa: BLE001
        estado["erro"] = f"{e}\n{traceback.format_exc()}"
        estado["status"] = "erro"
    finally:
        estado["coletando"] = False


def laco(intervalo: int):
    while True:
        coletar()
        pedido.wait(intervalo)
        pedido.clear()


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
        if self.path.startswith("/api/dados"):
            snap = estado["snapshot"]
            if snap is None:
                body = json.dumps({"carregando": True, "status": estado["status"], "erro": estado["erro"]}, ensure_ascii=False)
                return self._json(body.encode("utf-8"), 202)
            return self._json(snap)
        if self.path.startswith("/api/config"):
            return self._json(json.dumps(config_publica()).encode("utf-8"))
        if self.path.startswith("/api/nota"):
            if estado["dados"] is None:
                return self._json(b'{"carregando":true}', 202)
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            fim = float((q.get("fim") or [time.time()])[0])
            ini = float((q.get("ini") or [fim - 7 * 86400])[0])
            return self._json(json.dumps(nota.calcular(estado["dados"], ini, fim)).encode("utf-8"))
        if self.path.startswith("/api/ia/prompt"):
            if estado["dados"] is None:
                return self._json(b'{"erro":"carregando"}', 202)
            cfg = ler_config()
            hist = ia.historico()
            txt = ia.montar_prompt(estado["dados"], cfg.get("idioma", "en"), int((cfg.get("ia") or {}).get("dias") or 7), hist[0] if hist else None)
            body = txt.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith("/api/ia"):
            body = {"disponiveis": ia.disponiveis(), "historico": ia.historico()[:10], "estado": ia.estado,
                    "config": config_publica().get("ia") or {}}
            return self._json(json.dumps(body, ensure_ascii=False).encode("utf-8"))
        if self.path.startswith("/api/status"):
            body = json.dumps({"status": estado["status"], "coletando": estado["coletando"], "erro": estado["erro"]}, ensure_ascii=False)
            return self._json(body.encode("utf-8"))
        return super().do_GET()

    def _corpo(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(min(n, 65536)) or b"{}")

    def do_POST(self):
        # só a página do próprio painel manda este cabeçalho; outros sites abertos no
        # navegador não conseguem (o navegador exige permissão que este servidor não dá)
        if self.headers.get("X-Token-Panel") != "1":
            self.send_error(403)
            return
        if self.path.startswith("/api/ia/analisar"):
            if estado["dados"] is None:
                return self._json(b'{"erro":"carregando"}', 409)
            try:
                corpo = self._corpo()
                cfg = gravar_config({"ia": corpo, "idioma": corpo.get("idioma")})
                ia.analisar(estado["dados"], cfg.get("ia") or {}, cfg.get("idioma", "en"))
                return self._json(b'{"ok":true}', 202)
            except Exception as e:  # noqa: BLE001
                return self._json(json.dumps({"erro": str(e)}).encode("utf-8"), 400)
        if self.path.startswith("/api/precos/atualizar"):
            def trabalho():
                precos.atualizar(forcar=True)
                pedido.set()  # recalcula os valores com a tabela nova
            threading.Thread(target=trabalho, daemon=True).start()
            return self._json(b'{"ok":true}', 202)
        if self.path.startswith("/api/atualizar"):
            pedido.set()
            return self._json(b'{"ok":true}')
        if self.path.startswith("/api/config"):
            try:
                n = int(self.headers.get("Content-Length") or 0)
                gravar_config(json.loads(self.rfile.read(min(n, 4096)) or b"{}"))
                return self._json(json.dumps(config_publica()).encode("utf-8"))
            except Exception:  # noqa: BLE001
                return self._json(b'{"erro":"config invalida"}', 400)
        self.send_error(404)


def iniciar(porta: int = 8765, intervalo: int = 60) -> ThreadingHTTPServer:
    """Sobe o servidor e a coleta em threads de fundo. Usado pelo app da bandeja."""
    srv = ThreadingHTTPServer(("127.0.0.1", porta), Handler)
    threading.Thread(target=laco, args=(intervalo,), daemon=True).start()
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--porta", type=int, default=8765)
    ap.add_argument("--intervalo", type=int, default=60, help="segundos entre coletas")
    ap.add_argument("--sem-navegador", action="store_true")
    args = ap.parse_args()

    threading.Thread(target=laco, args=(args.intervalo,), daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", args.porta), Handler)
    url = f"http://127.0.0.1:{args.porta}"
    print(f"Token Economy: {url}  (Ctrl+C)")
    if not args.sem_navegador:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
