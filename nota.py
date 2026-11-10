"""Nota de otimização (0 a 100), feita só de coisas que dá para mudar.

Cada critério tem um peso, uma meta (pontuação cheia) e um limite ruim (zero ponto);
entre os dois a pontuação é proporcional. Critérios sem dados (por exemplo, quem não
usa o Codex ou não tem o RTK) ficam de fora e os pesos dos outros são redistribuídos.
Chegar a 100 é possível: basta cada critério bater a meta.
"""
from __future__ import annotations

import time

# id: (peso, meta, limite ruim, unidade)
CRITERIOS = {
    "contexto": (25, 80_000, 300_000, "tokens"),   # entrada média por chamada (menor é melhor)
    "sessoes": (15, 20, 80, "pct"),                 # % das chamadas em sessões com mais de 250 chamadas
    "cache": (10, 90, 50, "pct"),                   # % da entrada lida do cache (maior é melhor)
    "modelo": (10, 60, 100, "pct"),                 # % dos tokens novos em modelos de ponta (US$ 4+/M)
    "rtk": (15, 90, 40, "pct"),                     # % dos comandos que o RTK sabe filtrar que passaram por ele
    "espera": (10, 3, 20, "pct"),                   # % das chamadas de ferramenta que são esperas
    "limites": (15, 0, 50, "pct"),                  # % das janelas de 5 h do Codex que chegaram a 95%
}
SESSAO_LONGA = 250
PRECO_PONTA = 4.0


def _ts_hora(h: str) -> float:
    return time.mktime(time.strptime(h[:13], "%Y-%m-%dT%H"))


def _pontos(valor: float, meta: float, ruim: float) -> float:
    """1.0 na meta (ou melhor), 0.0 no limite ruim (ou pior), proporcional no meio."""
    if meta == ruim:
        return 1.0
    frac = (ruim - valor) / (ruim - meta)
    return max(0.0, min(1.0, frac))


def calcular(snap: dict, ini: float, fim: float) -> dict:
    import precos as precos_mod

    dentro = lambda h: ini <= _ts_hora(h) + 3599 and _ts_hora(h) <= fim
    uso = [r for r in snap["uso"] if dentro(r["hora"])]
    vals: dict[str, float] = {}
    extra: dict[str, dict] = {}

    calls = sum(r.get("msgs") or 0 for r in uso)
    entrada = sum((r.get("input") or 0) + (r.get("cache_read") or 0) + (r.get("cache_write") or 0) for r in uso)
    if calls:
        vals["contexto"] = entrada / calls
        vals["cache"] = 100 * sum(r.get("cache_read") or 0 for r in uso) / entrada if entrada else 0

        novos_tot = novos_ponta = 0.0
        por_modelo: dict[str, float] = {}
        for r in uso:
            n = (r.get("input") or 0) + (r.get("cache_write") or 0) + (r.get("output") or 0)
            novos_tot += n
            p = precos_mod.preco(r["modelo"])[0]
            if p and (p.get("input") or 0) >= PRECO_PONTA:
                novos_ponta += n
                por_modelo[r["modelo"]] = por_modelo.get(r["modelo"], 0) + n
        if novos_tot:
            vals["modelo"] = 100 * novos_ponta / novos_tot
            extra["modelo"] = {"modelos": sorted(por_modelo, key=por_modelo.get, reverse=True)[:3]}

    sess = [s for s in snap["sessoes"] if s["fim"] >= ini and s["inicio"] <= fim]
    tot_sess = sum(s["msgs"] for s in sess)
    if tot_sess:
        longas = [s for s in sess if s["msgs"] > SESSAO_LONGA]
        vals["sessoes"] = 100 * sum(s["msgs"] for s in longas) / tot_sess
        extra["sessoes"] = {"n": len(longas), "limite": SESSAO_LONGA}

    ativ = [r for r in snap["rtk"].get("atividade", []) if dentro(r["hora"])]
    if snap["fontes"]["rtk"]["ok"]:
        sup = sum(r.get("sup") or 0 for r in ativ)
        sup_rtk = sum(r.get("sup_rtk") or 0 for r in ativ)
        if sup >= 20:
            vals["rtk"] = min(100.0, 100 * sup_rtk / sup)
            extra["rtk"] = {"filtraveis": int(sup), "pelo_rtk": int(sup_rtk), "fora": int(sup - sup_rtk)}
    ferr = sum(r.get("ferramentas") or 0 for r in ativ)
    if ferr >= 50:
        vals["espera"] = 100 * sum(r.get("espera") or 0 for r in ativ) / ferr
        extra["espera"] = {"chamadas": int(ferr)}

    jan: dict[int, float] = {}
    for l in snap["limites"]["codex"]:
        if l.get("reset_5h") and l.get("p5h") is not None and ini <= l["ts"] <= fim:
            k = round(l["reset_5h"] / 300)
            jan[k] = max(jan.get(k, 0), l["p5h"])
    usadas = [v for v in jan.values() if v > 0]
    if len(usadas) >= 2:
        vals["limites"] = 100 * sum(1 for v in usadas if v >= 95) / len(usadas)
        extra["limites"] = {"janelas": len(usadas), "estouradas": sum(1 for v in usadas if v >= 95)}

    peso_total = sum(CRITERIOS[k][0] for k in vals) or 1
    comps, nota = [], 0.0
    for k, (peso, meta, ruim, unidade) in CRITERIOS.items():
        if k not in vals:
            continue
        peso_n = 100 * peso / peso_total
        frac = _pontos(vals[k], meta, ruim)
        nota += peso_n * frac
        comps.append({
            "id": k, "valor": round(vals[k], 1), "meta": meta, "ruim": ruim, "unidade": unidade,
            "peso": round(peso_n, 1), "pontos": round(peso_n * frac, 1), "extra": extra.get(k, {}),
        })
    comps.sort(key=lambda c: c["pontos"] - c["peso"])  # o que mais perde ponto primeiro
    return {"nota": round(nota) if comps else None, "componentes": comps,
            "ini": ini, "fim": fim, "fora": [k for k in CRITERIOS if k not in vals]}
