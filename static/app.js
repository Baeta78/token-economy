"use strict";
/* global t, IDIOMA, IDIOMAS, LOCALES, traduzirPagina */

// ---------------------------------------------------------------------------
// estado
// ---------------------------------------------------------------------------
const E = {
  dados: null,
  periodo: lerPref("periodo", "7d"),
  desligados: new Set(JSON.parse(lerPref("desligados", "[]"))),
  unidade: new URLSearchParams(location.search).get("unidade") || lerPref("unidade", "tokens"),
  graficos: {},
  ia: null,
};
const emUSD = () => E.unidade === "usd";

// pedidos que mudam algo no servidor levam este cabeçalho (proteção contra outros sites)
function postar(url, corpo) {
  return fetch(url, { method: "POST", headers: { "Content-Type": "application/json", "X-Token-Panel": "1" }, body: JSON.stringify(corpo || {}) });
}
const ORDEM_AGENTES = ["claude", "codex", "opencode", "ollama", "desconhecido"];

function lerPref(k, padrao) { try { return localStorage.getItem("painel." + k) ?? padrao; } catch { return padrao; } }
function gravarPref(k, v) { try { localStorage.setItem("painel." + k, v); } catch { /* sem armazenamento */ } }

// ---------------------------------------------------------------------------
// formatação (segue o idioma escolhido)
// ---------------------------------------------------------------------------
let nf, nfc, usdf, rtf, LOC;
function configurarFormatos() {
  LOC = LOCALES[IDIOMA] || "en-US";
  nf = new Intl.NumberFormat(LOC);
  nfc = new Intl.NumberFormat(LOC, { notation: "compact", maximumFractionDigits: 1 });
  usdf = new Intl.NumberFormat(LOC, { style: "currency", currency: "USD", maximumFractionDigits: 2 });
  rtf = new Intl.RelativeTimeFormat(LOC, { numeric: "auto" });
}
configurarFormatos();

const fmt = (n) => {
  if (n == null || isNaN(n)) return "–";
  // o espanhol não tem forma curta para bilhões no navegador ("2864,2 M"); usa "2,9 mil M"
  if (IDIOMA === "es" && Math.abs(n) >= 1e9) return (n / 1e9).toLocaleString(LOC, { maximumFractionDigits: 1 }) + " mil M";
  return Math.abs(n) >= 10000 ? nfc.format(n) : nf.format(Math.round(n));
};
const fmtUSD = (n) => {
  if (n == null || isNaN(n)) return "–";
  if (n >= 1000) return "US$ " + nfc.format(n);
  if (n > 0 && n < 1) return n.toLocaleString(LOC, { style: "currency", currency: "USD", maximumFractionDigits: n < 0.01 ? 4 : 3 });
  return usdf.format(n);
};
const fmtPct = (n, d = 0) => (n == null || !isFinite(n) ? "–" : n.toLocaleString(LOC, { maximumFractionDigits: d }) + "%");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function fmtDur(seg) {
  if (seg == null || !isFinite(seg)) return "–";
  seg = Math.max(0, seg);
  const totalMin = Math.round(seg / 60);  // arredonda antes de separar: nunca "4 h 60 min"
  const h = Math.floor(totalMin / 60), m = totalMin % 60;
  if (h >= 48) return t("dias", { n: Math.round(h / 24) });
  if (h > 0) return `${h} h ${String(m).padStart(2, "0")} min`;
  return `${m} min`;
}
function fmtData(ts, comHora = true) {
  const d = new Date(ts * 1000);
  return d.toLocaleString(LOC, comHora ? { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" } : { day: "2-digit", month: "2-digit" });
}
function haQuanto(ts) {
  const s = Date.now() / 1000 - ts;
  if (s < 60) return t("agora");
  if (s < 3600) return rtf.format(-Math.round(s / 60), "minute");
  if (s < 86400) return rtf.format(-Math.round(s / 3600), "hour");
  return rtf.format(-Math.round(s / 86400), "day");
}
const diaCurto = (d) => new Date(+d.slice(0, 4), +d.slice(5, 7) - 1, +d.slice(8, 10)).toLocaleDateString(LOC, { day: "2-digit", month: "2-digit" });

const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const corAgente = (a) => css("--a-" + a) || css("--a-desconhecido");
const nomeAgente = (a) => t("agente." + a);
const nomeProjeto = (p) => (p && p.startsWith("~") ? t("proj." + p) : p);
const primeiraMaiuscula = (s) => s.charAt(0).toUpperCase() + s.slice(1);

// "2026-11-09T14" -> epoch (hora local)
const horaTs = (h) => new Date(+h.slice(0, 4), +h.slice(5, 7) - 1, +h.slice(8, 10), +(h.slice(11, 13) || 0)).getTime() / 1000;
const diaDe = (h) => h.slice(0, 10);

// ---------------------------------------------------------------------------
// período e filtros
// ---------------------------------------------------------------------------
function intervalo() {
  const agora = Date.now() / 1000;
  const hoje0 = new Date(); hoje0.setHours(0, 0, 0, 0);
  switch (E.periodo) {
    case "hoje": return [hoje0.getTime() / 1000, agora];
    case "24h": return [agora - 86400, agora];
    case "7d": return [hoje0.getTime() / 1000 - 6 * 86400, agora];
    case "30d": return [hoje0.getTime() / 1000 - 29 * 86400, agora];
    default: return [0, agora];
  }
}
const nomePeriodo = () => t("periodo.nome." + E.periodo);

function noPeriodoHora(h) {
  const [ini, fim] = intervalo();
  const tt = horaTs(h);
  return tt + 3599 >= ini && tt <= fim;
}
function noPeriodoDia(d) {
  const [ini] = intervalo();
  return horaTs(d + "T00") + 86399 >= ini;
}
const agenteOk = (a) => !E.desligados.has(a);

function filtrados() {
  const d = E.dados;
  return {
    uso: d.uso.filter((r) => noPeriodoHora(r.hora) && agenteOk(r.agente)),
    rtk: d.rtk.hora.filter((r) => noPeriodoHora(r.hora) && agenteOk(r.agente)),
    hr: d.headroom.hora.filter((r) => noPeriodoHora(r.hora) && agenteOk(r.agente)),
    eco: (d.economia?.hora || []).filter((r) => noPeriodoHora(r.hora) && agenteOk(r.agente)),
    proj: d.uso_projetos.filter((r) => noPeriodoDia(r.dia) && agenteOk(r.agente)),
    rtkCmd: d.rtk.comandos.filter((r) => noPeriodoDia(r.dia)),
    sessoes: d.sessoes.filter((s) => s.fim >= intervalo()[0] && agenteOk(s.agente)),
    ollama: d.ollama.hora.filter((r) => noPeriodoHora(r.hora)),
  };
}

const novos = (r) => (r.input || 0) + (r.cache_write || 0) + (r.output || 0);

function soma(lista, chaveFn, campos) {
  const m = new Map();
  for (const r of lista) {
    const k = chaveFn(r);
    let o = m.get(k);
    if (!o) { o = {}; m.set(k, o); }
    for (const [nome, fn] of Object.entries(campos)) o[nome] = (o[nome] || 0) + (typeof fn === "function" ? fn(r) : (r[fn] || 0));
  }
  return m;
}

function diasDoPeriodo(minDados) {
  let [ini, fim] = intervalo();
  if (E.periodo === "tudo" && minDados) ini = horaTs(minDados + "T00");
  const out = [];
  const d = new Date(ini * 1000); d.setHours(0, 0, 0, 0);
  while (d.getTime() / 1000 <= fim) {
    out.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`);
    d.setDate(d.getDate() + 1);
  }
  return out;
}

// ---------------------------------------------------------------------------
// gráficos (Chart.js)
// ---------------------------------------------------------------------------
function baseOpcoes(extra = {}, fmtEixo = fmt) {
  const grid = css("--grid"), texto = css("--text-2");
  return {
    responsive: true, maintainAspectRatio: false, animation: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: { position: "bottom", labels: { color: texto, boxWidth: 10, boxHeight: 10, usePointStyle: true, pointStyle: "rectRounded", padding: 14 } },
      tooltip: {
        backgroundColor: css("--surface"), titleColor: css("--text"), bodyColor: css("--text-2"),
        borderColor: css("--border"), borderWidth: 1, padding: 10, boxPadding: 4,
        callbacks: { label: (c) => ` ${c.dataset.label}: ${fmtEixo(c.parsed.y ?? c.parsed.x)}` },
      },
    },
    scales: {
      x: { grid: { display: false }, ticks: { color: texto, maxRotation: 0, autoSkipPadding: 12 }, border: { color: grid } },
      y: { grid: { color: grid }, ticks: { color: texto, callback: (v) => fmtEixo(v) }, border: { display: false }, beginAtZero: true },
    },
    ...extra,
  };
}
const empilhado = (fmtEixo = fmt) => {
  const b = baseOpcoes({}, fmtEixo);
  return baseOpcoes({ scales: { x: { ...b.scales.x, stacked: true }, y: { ...b.scales.y, stacked: true } } }, fmtEixo);
};
// valor do registro na unidade escolhida
const fmtU = () => (emUSD() ? fmtUSD : fmt);
function desenhar(id, config) {
  const el = document.getElementById(id);
  if (!el) return;
  if (typeof Chart === "undefined") {
    el.parentElement.innerHTML = `<div class="vazio">${esc(t("sem.graficos"))}</div>`;
    return;
  }
  E.graficos[id]?.destroy();
  E.graficos[id] = new Chart(el, config);
}
const barraDS = (label, data, cor, pilha) => ({
  label, data, backgroundColor: cor, borderColor: css("--surface"), borderWidth: { top: 2 }, borderSkipped: "bottom",
  borderRadius: 4, stack: pilha, maxBarThickness: 36,
});

// ---------------------------------------------------------------------------
// componentes HTML
// ---------------------------------------------------------------------------
function kpi(rotulo, valor, detalhe = "", titulo = "") {
  return `<div class="kpi" title="${esc(titulo)}"><div class="rotulo">${esc(rotulo)}</div><div class="valor">${valor}</div><div class="detalhe">${detalhe}</div></div>`;
}
const vazio = () => `<div class="vazio">${esc(t("vazio"))}</div>`;
function barras(itens, fmtValor = fmt) {
  if (!itens.length) return vazio();
  const max = Math.max(...itens.map((i) => i.valor), 1);
  return `<div class="barras">${itens.map((i) => `
    <div class="barra-linha" title="${esc(i.titulo || i.nome)}">
      <div class="barra-nome"><span class="bolinha" style="background:${i.cor}"></span>${esc(i.nome)}</div>
      <div class="barra-trilho"><div class="barra-cheia" style="width:${(100 * i.valor) / max}%;background:${i.cor}"></div></div>
      <div class="barra-valor">${fmtValor(i.valor)}${i.extra ? ` <span class="mudo">${i.extra}</span>` : ""}</div>
    </div>`).join("")}</div>`;
}
// tabela ordenável: cols = [{t:"chave i18n", k: fn(row)->valor, f: fn(valor,row)->html, esq:bool, dica:"chave i18n"}]
function tabela(id, cols, linhas, ordem = 1) {
  const el = document.getElementById(id);
  if (!el) return;
  if (!linhas.length) { el.innerHTML = `<tr><td class="vazio">${esc(t("vazio"))}</td></tr>`; return; }
  let col = el.dataset.col != null ? +el.dataset.col : ordem, dir = el.dataset.dir || "desc";
  if (col >= cols.length) col = ordem;
  const render = () => {
    const ord = [...linhas].sort((a, b) => {
      const va = cols[col].k(a), vb = cols[col].k(b);
      const r = typeof va === "string" ? va.localeCompare(vb) : (va ?? -Infinity) - (vb ?? -Infinity);
      return dir === "desc" ? -r : r;
    });
    el.innerHTML = `<thead><tr>${cols.map((c, i) => `<th data-i="${i}" class="${c.esq ? "esq" : ""}" title="${esc(c.dica ? t(c.dica) : t("ordenar"))}">${esc(t(c.t))}${i === col ? (dir === "desc" ? " ↓" : " ↑") : ""}</th>`).join("")}</tr></thead>
      <tbody>${ord.map((r) => `<tr>${cols.map((c) => `<td class="${c.esq ? "esq" : ""} ${c.cls || ""}">${c.f ? c.f(c.k(r), r) : esc(c.k(r))}</td>`).join("")}</tr>`).join("")}</tbody>`;
    el.querySelectorAll("th").forEach((th) => th.onclick = () => {
      const i = +th.dataset.i;
      if (i === col) dir = dir === "desc" ? "asc" : "desc"; else { col = i; dir = "desc"; }
      el.dataset.col = col; el.dataset.dir = dir;
      render();
    });
  };
  render();
}
const bolinhaAgente = (a) => `<span class="bolinha" style="background:${corAgente(a)}"></span>${esc(nomeAgente(a))}`;

// ---------------------------------------------------------------------------
// visão geral
// ---------------------------------------------------------------------------
function renderVisao(F) {
  const usd = emUSD(), fu = fmtU();
  const tot = F.uso.reduce((o, r) => {
    o.novos += novos(r); o.cr += r.cache_read || 0; o.msgs += r.msgs || 0; o.usd += r.usd || 0;
    o.entrada += (r.input || 0) + (r.cache_read || 0) + (r.cache_write || 0); o.semPreco += r.sem_preco || 0;
    return o;
  }, { novos: 0, cr: 0, msgs: 0, usd: 0, entrada: 0, semPreco: 0 });
  const cachePct = tot.entrada ? (100 * tot.cr) / tot.entrada : null;
  const ecoL = linhasEconomia(F);
  const ecoTot = ecoL.reduce((o, r) => { o.saved += r.saved; o.est += r.est; o.usd += r.usd; return o; }, { saved: 0, est: 0, usd: 0 });

  document.getElementById("kpis").innerHTML = [
    kpi(t("kpi.novos"), fmt(tot.novos), esc(t("kpi.novos.det", { n: fmt(tot.msgs), periodo: nomePeriodo() })), t("kpi.novos.dica")),
    kpi(t("kpi.cache"), fmt(tot.cr), esc(t("kpi.cache.det", { pct: fmtPct(cachePct) })), t("kpi.cache.dica")),
    kpi(t("kpi.api"), fmtUSD(tot.usd), esc(tot.semPreco ? t("kpi.api.semPreco", { n: fmt(tot.semPreco) }) : t("kpi.api.tabela")), t("kpi.api.dica")),
    ...(ecoL.length ? [kpi(t("eco.kpi.tokens"), fmt(ecoTot.saved), esc(t("eco.kpi.porFerramentas", { n: new Set(ecoL.map((r) => r.ferramenta)).size })), t("kpi.rtk.dica")),
      kpi(t("kpi.ecoUsd"), fmtUSD(ecoTot.est), esc(t("eco.kpi.min", { min: fmtUSD(ecoTot.usd) })), t("kpi.ecoUsd.dica"))] : []),
  ].join("");

  document.getElementById("tit-diario").textContent = t(usd ? "visao.diario.usd" : "visao.diario");
  document.getElementById("exp-diario").textContent = t(usd ? "visao.diario.usd.explica" : "visao.diario.explica");
  document.getElementById("exp-consome").textContent = t(usd ? "visao.consome.usd.explica" : "visao.consome.explica");
  document.getElementById("exp-economiza").textContent = t(usd ? "visao.economiza.usd.explica" : "visao.economiza.explica");

  const valor = usd ? (r) => r.usd || 0 : novos;
  const ags = ORDEM_AGENTES.filter((a) => F.uso.some((r) => r.agente === a));
  const usarHoras = E.periodo === "hoje" || E.periodo === "24h";
  let rotulos, series;
  if (usarHoras) {
    const [ini, fim] = intervalo();
    const horas = [];
    for (let tt = Math.floor(ini / 3600) * 3600; tt <= fim; tt += 3600) {
      const d = new Date(tt * 1000);
      horas.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}T${String(d.getHours()).padStart(2, "0")}`);
    }
    const porHoraAg = soma(F.uso, (r) => r.hora + "|" + r.agente, { v: valor });
    rotulos = horas.map((h) => h.slice(11, 13) + "h");
    series = ags.map((a) => barraDS(nomeAgente(a), horas.map((h) => porHoraAg.get(h + "|" + a)?.v || 0), corAgente(a), "s"));
    document.getElementById("sub-diario").textContent = t("visao.porhora");
  } else {
    const dias = diasDoPeriodo(F.uso.length ? F.uso.reduce((m, r) => (r.hora < m ? r.hora : m), "9999").slice(0, 10) : null);
    const porDiaAg = soma(F.uso, (r) => diaDe(r.hora) + "|" + r.agente, { v: valor });
    rotulos = dias.map(diaCurto);
    series = ags.map((a) => barraDS(nomeAgente(a), dias.map((d) => porDiaAg.get(d + "|" + a)?.v || 0), corAgente(a), "s"));
    document.getElementById("sub-diario").textContent = t("visao.pordia");
  }
  desenhar("g-diario", { type: "bar", data: { labels: rotulos, datasets: series }, options: empilhado(fu) });

  const porAg = soma(F.uso, (r) => r.agente, { v: valor, msgs: "msgs" });
  const totN = [...porAg.values()].reduce((s, o) => s + o.v, 0) || 1;
  document.getElementById("participacao").innerHTML = barras(
    ORDEM_AGENTES.filter((a) => porAg.has(a)).map((a) => ({ nome: nomeAgente(a), valor: porAg.get(a).v, cor: corAgente(a), extra: fmtPct((100 * porAg.get(a).v) / totN), titulo: t("chamadas", { n: fmt(porAg.get(a).msgs) }) })),
    fu,
  );

  const ecoAg = soma(ecoL, (r) => r.agente + "|" + r.ferramenta, { v: usd ? "est" : "saved" });
  const itens = [];
  for (const a of ORDEM_AGENTES) {
    const partes = [...ecoAg.entries()].filter(([k]) => k.startsWith(a + "|")).map(([k, o]) => [k.split("|")[1], o.v]).filter(([, v]) => v > 0);
    const total = partes.reduce((s2, [, v]) => s2 + v, 0);
    if (total > 0) itens.push({ nome: nomeAgente(a), valor: total, cor: corAgente(a), extra: partes.map(([f, v]) => `${nomeFerramenta(f)} ${fu(v)}`).join(" · ") });
  }
  document.getElementById("economia-agente").innerHTML = barras(itens, fu);
}

// ---------------------------------------------------------------------------
// limites
// ---------------------------------------------------------------------------
function janelasCodex() {
  const L = E.dados.limites.codex || [];
  const jan = new Map();
  for (const l of L) {
    if (l.reset_5h == null || l.p5h == null) continue;
    let j = jan.get(l.reset_5h);
    if (!j) { j = { reset: l.reset_5h, ini: l.reset_5h - (l.janela_min || 300) * 60, primeiro: l, ultimo: l, max: 0, amostras: 0 }; jan.set(l.reset_5h, j); }
    if (l.ts < j.primeiro.ts) j.primeiro = l;
    if (l.ts > j.ultimo.ts) j.ultimo = l;
    j.max = Math.max(j.max, l.p5h);
    j.amostras++;
  }
  // junta janelas cujo reset difere só por segundos (o Codex arredonda)
  const out = [];
  for (const j of [...jan.values()].sort((a, b) => a.reset - b.reset)) {
    const ant = out[out.length - 1];
    if (ant && Math.abs(ant.reset - j.reset) < 120) {
      ant.max = Math.max(ant.max, j.max);
      if (j.ultimo.ts > ant.ultimo.ts) ant.ultimo = j.ultimo;
      if (j.primeiro.ts < ant.primeiro.ts) ant.primeiro = j.primeiro;
      ant.amostras += j.amostras;
    } else out.push({ ...j });
  }
  for (const j of out) {
    const horas = Math.max((j.ultimo.ts - j.ini) / 3600, 1 / 60);
    j.ritmo = j.max / horas;
    j.estouraEm = j.ritmo > 0 ? 100 / j.ritmo : null;
  }
  return out;
}
function mediaRitmo(js) {
  const v = js.filter((j) => j.max > 0 && j.ritmo).map((j) => j.ritmo);
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
}


function renderLimites() {
  const jsT = janelasVisiveis();
  document.getElementById("lim-janelas").innerHTML = jsT.length
    ? porAgente(jsT).map((g) => `<div class="grupo-agente">${cabAgente(g)}<div class="grade g3" style="margin:0">${g.janelas.map(cartaoJanela).join("")}</div>${g.agente === "claude" ? blocoCreditos() : ""}</div>`).join("") + avisoClaude()
    : avisoVersao() || avisoClaude() || `<div class="vazio">${esc(t("resumo.limites.sem"))}</div>`;
  const L = E.dados.limites.codex || [];
  const agora = Date.now() / 1000;
  const jans = janelasCodex();

  // % da janela de 5 h ao longo do tempo
  const [ini] = intervalo();
  const pts = L.filter((l) => l.ts >= ini && l.p5h != null);
  const serie = (campo, chaveReset) => {
    const out = [];
    for (let i = 0; i < pts.length; i++) {
      const l = pts[i], ant = pts[i - 1];
      if (ant && (Math.abs((l[chaveReset] || 0) - (ant[chaveReset] || 0)) > 120 || l.ts - ant.ts > 3600)) out.push({ x: (ant.ts + 1) * 1000, y: null });
      out.push({ x: l.ts * 1000, y: l[campo] });
    }
    return out;
  };
  const b = baseOpcoes();
  desenhar("g-codex-limite", {
    type: "line",
    data: {
      datasets: [
        { label: t("lim.serie5h"), data: serie("p5h", "reset_5h"), borderColor: corAgente("codex"), backgroundColor: corAgente("codex"), borderWidth: 2, pointRadius: 0, spanGaps: false, tension: 0 },
        { label: t("lim.serieSem"), data: serie("psemana", "reset_semana"), borderColor: css("--s1"), backgroundColor: css("--s1"), borderWidth: 2, pointRadius: 0, spanGaps: false, borderDash: [4, 3] },
      ],
    },
    options: baseOpcoes({
      parsing: false,
      plugins: { ...b.plugins, tooltip: { ...b.plugins.tooltip, callbacks: { title: (c) => fmtData(c[0].parsed.x / 1000), label: (c) => ` ${c.dataset.label}: ${fmtPct(c.parsed.y)}` } } },
      scales: {
        x: { type: "linear", grid: { display: false }, ticks: { color: css("--text-2"), callback: (v) => fmtData(v / 1000, E.periodo !== "hoje" && E.periodo !== "24h"), maxTicksLimit: 8 } },
        y: { min: 0, max: 100, grid: { color: css("--grid") }, ticks: { color: css("--text-2"), callback: (v) => v + "%" }, border: { display: false } },
      },
    }),
  });

  tabela("t-janelas", [
    { t: "col.inicioJanela", k: (j) => j.ini, f: (v) => fmtData(v), esq: true },
    { t: "col.usado", k: (j) => j.max, f: (v) => `${fmtPct(v)}<span class="mini-barra" style="width:${Math.min(v, 100) * 0.6}px;background:${v >= 100 ? css("--critical") : corAgente("codex")}"></span>` },
    { t: "col.ritmo", k: (j) => j.ritmo, f: (v) => fmtPct(v, 1) },
    { t: "col.esgotaria", k: (j) => j.estouraEm, f: (v) => (v ? fmtDur(v * 3600) : "–"), dica: "col.esgotaria.dica" },
    { t: "col.ultLeitura", k: (j) => j.ultimo.ts, f: (v) => fmtData(v) },
  ], jans.filter((j) => j.reset >= ini).reverse().slice(0, 40), 0);

  // últimas 5 h, comparadas com o pico de 5 h dos últimos 30 dias
  const lim5 = agora - 5 * 3600;
  const rec = E.dados.uso.filter((r) => horaTs(r.hora) + 3600 >= lim5 && agenteOk(r.agente));
  const p5 = soma(rec, (r) => r.agente, { v: novos, msgs: "msgs" });
  const ref = {};
  const porHora = soma(E.dados.uso.filter((r) => horaTs(r.hora) >= agora - 30 * 86400), (r) => r.agente + "|" + r.hora, { v: novos });
  for (const [k, o] of porHora) {
    const [a, h] = k.split("|");
    (ref[a] ||= []).push([horaTs(h), o.v]);
  }
  const pico = {};
  for (const [a, arr] of Object.entries(ref)) {
    arr.sort((x, y) => x[0] - y[0]);
    let best = 0, s = 0, i0 = 0;
    for (let i = 0; i < arr.length; i++) {
      s += arr[i][1];
      while (arr[i][0] - arr[i0][0] >= 5 * 3600) { s -= arr[i0][1]; i0++; }
      best = Math.max(best, s);
    }
    pico[a] = best;
  }
  document.getElementById("ultimas-5h").innerHTML = barras(
    ORDEM_AGENTES.filter((a) => p5.has(a)).map((a) => ({
      nome: nomeAgente(a), valor: p5.get(a).v, cor: corAgente(a),
      extra: pico[a] ? esc(t("lim.pico", { pct: fmtPct((100 * p5.get(a).v) / pico[a]) })) : "",
      titulo: t("lim.pico.dica", { n: fmt(p5.get(a).msgs), pico: fmt(pico[a]) }),
    })),
  ) + `<p class="explica" style="margin-top:10px">${esc(t("lim.pico.explica"))}</p>`;
}

// ---------------------------------------------------------------------------
// agentes e modelos
// ---------------------------------------------------------------------------
function renderModelos(F) {
  const m = soma(F.uso, (r) => r.agente + "|" + r.modelo, {
    msgs: "msgs", input: "input", output: "output", cr: "cache_read", cw: "cache_write", reasoning: "reasoning", usd: "usd", semPreco: "sem_preco",
  });
  const linhas = [...m.entries()].map(([k, o]) => {
    const [agente, modelo] = k.split("|");
    const entrada = o.input + o.cr + o.cw;
    return { agente, modelo, ...o, novos: o.input + o.cw + o.output, porMsg: o.msgs ? entrada / o.msgs : 0, cache: entrada ? (100 * o.cr) / entrada : null, saidaMsg: o.msgs ? o.output / o.msgs : 0 };
  });
  tabela("t-modelos", [
    { t: "col.agente", k: (r) => nomeAgente(r.agente), f: (_, r) => bolinhaAgente(r.agente), esq: true },
    { t: "col.modelo", k: (r) => r.modelo, esq: true },
    { t: "col.chamadas", k: (r) => r.msgs, f: fmt },
    { t: "col.novos", k: (r) => r.novos, f: fmt },
    { t: "col.entradaCham", k: (r) => r.porMsg, f: fmt, dica: "col.entradaCham.dica" },
    { t: "col.cache", k: (r) => r.cache, f: (v) => fmtPct(v), dica: "col.cache.dica" },
    { t: "col.saidaCham", k: (r) => r.saidaMsg, f: fmt },
    { t: "col.raciocinio", k: (r) => r.reasoning, f: (v) => (v ? fmt(v) : "–"), dica: "col.raciocinio.dica" },
    { t: "col.api", k: (r) => (r.semPreco && !r.usd ? -1 : r.usd), f: (v, r) => (r.semPreco && !r.usd ? `<span class="mudo">${esc(t("semPreco"))}</span>` : fmtUSD(v)) },
  ], linhas, 3);

  const [ini, fim] = intervalo();
  const passo = E.periodo === "tudo" || E.periodo === "30d" ? 86400 : 3600;
  const ags = ORDEM_AGENTES.filter((a) => F.uso.some((r) => r.agente === a));
  const mapa = soma(F.uso, (r) => r.agente + "|" + Math.floor(horaTs(r.hora) / passo) * passo, { v: novos });
  const t0 = E.periodo === "tudo" && F.uso.length ? Math.min(...F.uso.map((r) => horaTs(r.hora))) : ini;
  const ts = [];
  for (let x = Math.floor(t0 / passo) * passo; x <= fim; x += passo) ts.push(x);
  const b = baseOpcoes();
  desenhar("g-hora", {
    type: "line",
    data: { datasets: ags.map((a) => ({ label: nomeAgente(a), data: ts.map((x) => ({ x: x * 1000, y: mapa.get(a + "|" + x)?.v || 0 })), borderColor: corAgente(a), backgroundColor: corAgente(a), borderWidth: 2, pointRadius: 0, tension: 0.2 })) },
    options: baseOpcoes({
      parsing: false,
      plugins: { ...b.plugins, tooltip: { ...b.plugins.tooltip, callbacks: { title: (c) => fmtData(c[0].parsed.x / 1000, passo === 3600), label: (c) => ` ${c.dataset.label}: ${fmt(c.parsed.y)}` } } },
      scales: { ...b.scales, x: { type: "linear", grid: { display: false }, ticks: { color: css("--text-2"), maxTicksLimit: 8, callback: (v) => fmtData(v / 1000, passo === 3600 && (E.periodo === "hoje" || E.periodo === "24h")) } } },
    }),
  });

  const comp = soma(F.uso, (r) => r.agente, { input: "input", cr: "cache_read", cw: "cache_write", out: "output" });
  const agsC = ORDEM_AGENTES.filter((a) => comp.has(a));
  const pct = (a, k) => { const o = comp.get(a); const tt = o.input + o.cr + o.cw + o.out; return tt ? (100 * o[k]) / tt : 0; };
  const partes = [["cr", "comp.cr", css("--s1")], ["cw", "comp.cw", css("--s2")], ["input", "comp.input", css("--s3")], ["out", "comp.out", css("--s4")]];
  desenhar("g-composicao", {
    type: "bar",
    data: { labels: agsC.map(nomeAgente), datasets: partes.map(([k, l, c]) => ({ ...barraDS(t(l), agsC.map((a) => pct(a, k)), c, "c"), borderWidth: { right: 2 }, borderSkipped: "left" })) },
    options: baseOpcoes({
      indexAxis: "y",
      plugins: { ...b.plugins, tooltip: { ...b.plugins.tooltip, callbacks: { label: (c) => ` ${c.dataset.label}: ${fmtPct(c.parsed.x, 1)}` } } },
      scales: { x: { stacked: true, max: 100, grid: { color: css("--grid") }, ticks: { color: css("--text-2"), callback: (v) => v + "%" } }, y: { stacked: true, grid: { display: false }, ticks: { color: css("--text-2") } } },
    }),
  });

  const hd = soma(F.uso, (r) => r.agente + "|" + r.hora.slice(11, 13), { v: novos });
  const hs = [...Array(24).keys()].map((h) => String(h).padStart(2, "0"));
  desenhar("g-horadia", {
    type: "bar",
    data: { labels: hs.map((h) => h + "h"), datasets: ags.map((a) => barraDS(nomeAgente(a), hs.map((h) => hd.get(a + "|" + h)?.v || 0), corAgente(a), "h")) },
    options: empilhado(),
  });
}

// ---------------------------------------------------------------------------
// economia: ferramentas detectadas nesta máquina e o que cada uma economizou
// ---------------------------------------------------------------------------
// Só existem na tela as ferramentas detectadas. As que registram a economia são somadas;
// as que não registram aparecem com o que dá para saber (uso pelos agentes, projetos).
const ferramentasDetectadas = () => E.dados.economia?.ferramentas || [];
const temFerramenta = (id) => ferramentasDetectadas().some((f) => f.id === id);
const nomeFerramenta = (id) => ferramentasDetectadas().find((f) => f.id === id)?.nome || id;
const CORES_FERRAMENTA = ["--s1", "--s3", "--s2", "--s4", "--a-opencode", "--a-desconhecido"];
const corFerramenta = (id) => css(CORES_FERRAMENTA[Math.max(0, ferramentasDetectadas().filter((f) => f.medida).findIndex((f) => f.id === id)) % CORES_FERRAMENTA.length]);

// todas as economias medidas no mesmo formato: {hora, agente, ferramenta, saved, usd, est}
function linhasEconomia(F) {
  const out = [];
  if (temFerramenta("rtk")) for (const r of F.rtk) out.push({ hora: r.hora, agente: r.agente, ferramenta: "rtk", saved: r.saved || 0, usd: r.usd || 0, est: r.usd_est || 0 });
  if (temFerramenta("headroom")) for (const r of F.hr) out.push({ hora: r.hora, agente: r.agente, ferramenta: "headroom", saved: r.saved || 0, usd: r.usd || 0, est: r.usd || 0 });
  for (const r of F.eco) out.push({ hora: r.hora, agente: r.agente, ferramenta: r.ferramenta, saved: r.saved || 0, usd: r.usd || 0, est: r.usd_est || 0 });
  return out;
}

function cartaoFerramenta(f, porFer, F) {
  const v = porFer.get(f.id);
  const cab = `<div class="cab"><b><a class="link" href="${esc(f.url || "#")}" target="_blank" rel="noopener">${esc(f.nome)}</a></b><span class="etiqueta">${esc(t("cat." + (f.categoria || "outro")))}</span></div>`;
  const ags = f.agentes?.length ? `<div class="mudo">${esc(t("eco.agentes", { lista: f.agentes.map(nomeAgente).join(", ") }))}</div>` : "";
  let corpo;
  if (f.medida && f.id === "kompact") {
    const k = f.ao_vivo || {};
    corpo = `<div class="pct">${fmt(k.poupados)}</div><div class="mudo">${esc(t("eco.kompact", { n: fmt(k.requisicoes) }))}</div>`;
  } else if (f.medida) {
    corpo = v && v.saved
      ? `<div class="pct">${fmt(v.saved)}</div><div class="mudo">${esc(t("eco.tokensPoupados", { periodo: nomePeriodo() }))} · ≈ ${fmtUSD(v.est)}</div>`
      : `<div class="pct">0</div><div class="mudo">${esc(t("eco.semEventos", { periodo: nomePeriodo() }))}</div>`;
  } else {
    const ch = Object.values(f.chamadas || {}).reduce((a, b) => a + b, 0);
    const linhas = [t("eco.naoMede")];
    const pr = f.projetos || [];
    const consultas = pr.reduce((s, p) => s + p.consultas, 0);
    if (ch || consultas) linhas.push(t("eco.chamadas", { n: fmt(Math.max(ch, consultas)) }));
    if (pr.length) linhas.push(t("eco.projetos", { p: fmt(pr.filter((p) => p.instalado).length), u: fmt(pr.filter((p) => p.consultas).length) }));
    corpo = `<div class="pct mudo" style="font-size:15px;font-weight:500">${esc(t("eco.semMedicao"))}</div>${linhas.map((l) => `<div class="mudo">${esc(l)}</div>`).join("")}`;
  }
  return `<div class="janela">${cab}${corpo}${ags}</div>`;
}

function renderEconomia(F) {
  const usd = emUSD(), fu = fmtU();
  const det = ferramentasDetectadas();
  const L = linhasEconomia(F);
  const porFer = soma(L, (r) => r.ferramenta, { saved: "saved", usd: "usd", est: "est" });
  const tot = L.reduce((o, r) => { o.saved += r.saved; o.est += r.est; o.usd += r.usd; return o; }, { saved: 0, est: 0, usd: 0 });
  const novosTot = F.uso.reduce((s, r) => s + novos(r), 0);
  const medidas = det.filter((f) => f.medida);

  document.getElementById("kpis-economia").innerHTML = det.length ? [
    kpi(t("eco.kpi.ferramentas"), fmt(det.length), esc(t("eco.kpi.ferramentas.det", { m: medidas.length, s: det.length - medidas.length }))),
    kpi(t("eco.kpi.tokens"), fmt(tot.saved), esc(nomePeriodo())),
    kpi(t("kpi.ecoUsd"), fmtUSD(tot.est), esc(t("eco.kpi.min", { min: fmtUSD(tot.usd) })), t("kpi.ecoUsd.dica")),
    kpi(t("kpi.ecoTotal"), fmtPct(novosTot ? (100 * tot.saved) / (novosTot + tot.saved) : null, 1), esc(t("kpi.ecoTotal.det")), t("kpi.ecoTotal.dica")),
  ].join("") : "";

  document.getElementById("eco-ferramentas").innerHTML = det.length
    ? det.map((f) => cartaoFerramenta(f, porFer, F)).join("")
    : `<div class="vazio">${esc(t("eco.nenhuma"))}</div>`;

  // ferramentas sem medição: em que projetos estão configuradas e quanto foram consultadas
  const projSem = det.filter((f) => !f.medida).flatMap((f) => (f.projetos || []).map((p) => ({ ...p, id: f.id, nome: f.nome })));
  document.getElementById("bloco-eco-projetos").hidden = !projSem.length;
  if (projSem.length) {
    tabela("t-eco-projetos", [
      { t: "col.ferramenta", k: (r) => r.nome, esq: true },
      { t: "col.projeto", k: (r) => nomeProjeto(r.projeto), f: (v, r) => `<span title="${esc(r.pasta)}">${esc(v)}</span>`, esq: true, cls: "trunca" },
      { t: "col.configurada", k: (r) => (r.instalado ? 1 : 0), f: (v) => esc(t(v ? "eco.sim" : "eco.nao")) },
      { t: "col.consultas", k: (r) => r.consultas, f: fmt },
    ], projSem, 3);
  }

  // economia por dia, empilhada por ferramenta medida
  const blocoDia = document.getElementById("bloco-eco-dia");
  blocoDia.hidden = !L.length;
  if (L.length) {
    const dias = diasDoPeriodo(L.reduce((m, r) => (r.hora < m ? r.hora : m), "9999").slice(0, 10));
    const mapa = soma(L, (r) => r.ferramenta + "|" + diaDe(r.hora), { v: usd ? "est" : "saved" });
    const ids = [...new Set(L.map((r) => r.ferramenta))];
    document.getElementById("tit-eco-dia").textContent = t(usd ? "eco.porDia.usd" : "eco.porDia.tokens");
    desenhar("g-economia", {
      type: "bar",
      data: { labels: dias.map(diaCurto), datasets: ids.map((id) => barraDS(nomeFerramenta(id), dias.map((d) => mapa.get(id + "|" + d)?.v || 0), corFerramenta(id), "e")) },
      options: empilhado(fu),
    });
  }

  // detalhe do RTK: só se ele estiver instalado
  const comRtk = temFerramenta("rtk");
  for (const id of ["bloco-rtk-cmd", "bloco-rtk-hook", "bloco-rtk-falhas"]) document.getElementById(id).hidden = !comRtk;
  if (comRtk) {
    const pc = soma(F.rtkCmd, (r) => r.comando, { cmds: "cmds", input: "input", saved: "saved", zero: "zero", usd: "usd", est: "usd_est" });
    tabela("t-rtk-cmd", [
      { t: "col.comando", k: (r) => r.nome, esq: true, cls: "trunca" },
      { t: "col.vezes", k: (r) => r.cmds, f: fmt },
      { t: "col.poupados", k: (r) => r.saved, f: fmt },
      { t: "col.usdEst", k: (r) => r.est, f: fmtUSD, dica: "col.usdEst.dica" },
      { t: "col.reducao", k: (r) => (r.input ? (100 * r.saved) / r.input : null), f: (v) => `${fmtPct(v)}<span class="mini-barra" style="width:${Math.max(0, Math.min(v || 0, 100)) * 0.5}px"></span>` },
      { t: "col.semGanho", k: (r) => (r.cmds ? (100 * r.zero) / r.cmds : 0), f: (v, r) => `${fmtPct(v)} <span class="mudo">(${fmt(r.zero)})</span>` },
    ], [...pc.entries()].map(([nome, o]) => ({ nome, ...o })).sort((a, b) => b.saved - a.saved).slice(0, 60), 2);

    const dec = E.dados.rtk.decisoes_hook || {};
    const coresDec = { defer: css("--s1"), ask: css("--s2"), allow: css("--s3"), deny: css("--critical") };
    const at = E.dados.rtk.atribuicao || {};
    const totAt = Object.values(at).reduce((a, b) => a + b, 0) || 1;
    document.getElementById("rtk-hook").innerHTML = barras(Object.entries(dec).sort((a, b) => b[1] - a[1]).map(([k, v]) => ({ nome: t("dec." + k), valor: v, cor: coresDec[k] || css("--a-desconhecido") })))
      + `<p class="explica" style="margin-top:12px">${esc(t("eco.atrib", { a: fmtPct((100 * (at.comando || 0)) / totAt), b: fmtPct((100 * (at.atividade || 0)) / totAt), c: fmtPct((100 * (at.nenhum || 0)) / totAt) }))}</p>`;
    const fal = E.dados.rtk.falhas || [];
    document.getElementById("rtk-falhas").innerHTML = barras(fal.slice(0, 8).map(([k, v]) => ({ nome: k, valor: v, cor: css("--serious") })))
      + `<p class="explica" style="margin-top:12px">${esc(t("eco.falhas.total", { n: fmt(E.dados.rtk.falhas_total) }))}</p>`;
  }

  // detalhe do Headroom: só se ele estiver instalado
  const comHr = temFerramenta("headroom");
  document.getElementById("bloco-headroom").hidden = !comHr;
  if (comHr) {
    const hm = soma(F.hr, (r) => r.agente + "|" + r.modelo, { reqs: "reqs", saved: "saved", antes: "antes", medido: "saved_medido", usd: "usd" });
    tabela("t-headroom", [
      { t: "col.cliente", k: (r) => nomeAgente(r.agente), f: (_, r) => bolinhaAgente(r.agente), esq: true },
      { t: "col.modelo", k: (r) => r.modelo, esq: true },
      { t: "col.reqs", k: (r) => r.reqs, f: fmt },
      { t: "col.poupados", k: (r) => r.saved, f: fmt },
      { t: "col.reducao", k: (r) => (r.antes ? (100 * r.medido) / r.antes : null), f: (v) => fmtPct(v, 1), dica: "col.reducao.dica" },
      { t: "col.usdPoup", k: (r) => r.usd, f: fmtUSD },
    ], [...hm.entries()].map(([k, o]) => { const [agente, modelo] = k.split("|"); return { agente, modelo, ...o }; }), 3);
  }
}

// ---------------------------------------------------------------------------
// projetos e sessões
// ---------------------------------------------------------------------------
function renderProjetos(F) {
  const pm = soma(F.proj, (r) => r.projeto, { tokens: "tokens", msgs: "msgs", usd: "usd" });
  const agsPorProj = {};
  for (const r of F.proj) { const o = (agsPorProj[r.projeto] ||= {}); o[r.agente] = (o[r.agente] || 0) + r.tokens; }
  const linhas = [...pm.entries()].map(([projeto, o]) => ({ projeto, ...o, ags: agsPorProj[projeto] || {} }));
  const totP = linhas.reduce((s, r) => s + r.tokens, 0) || 1;
  tabela("t-projetos", [
    { t: "col.projeto", k: (r) => nomeProjeto(r.projeto), esq: true, cls: "trunca" },
    { t: "col.agentes", k: (r) => Object.keys(r.ags).length, f: (_, r) => Object.entries(r.ags).sort((a, b) => b[1] - a[1]).map(([a]) => `<span class="bolinha" title="${esc(nomeAgente(a))}" style="background:${corAgente(a)}"></span>`).join(""), esq: true },
    { t: "col.chamadas", k: (r) => r.msgs, f: fmt },
    { t: "col.tokensCache", k: (r) => r.tokens, f: fmt },
    { t: "col.parte", k: (r) => (100 * r.tokens) / totP, f: (v) => `${fmtPct(v, 1)}<span class="mini-barra" style="width:${v * 0.8}px"></span>` },
    { t: "col.api", k: (r) => r.usd, f: fmtUSD },
  ], linhas.sort((a, b) => b.tokens - a.tokens).slice(0, 50), 3);

  tabela("t-sessoes", [
    { t: "col.agente", k: (s) => nomeAgente(s.agente), f: (_, s) => bolinhaAgente(s.agente), esq: true },
    { t: "col.projeto", k: (s) => nomeProjeto(s.projeto), esq: true, cls: "trunca" },
    { t: "col.modelo", k: (s) => s.modelo, esq: true },
    { t: "col.inicio", k: (s) => s.inicio, f: (v) => fmtData(v) },
    { t: "col.duracao", k: (s) => s.fim - s.inicio, f: (v) => fmtDur(v) },
    { t: "col.chamadas", k: (s) => s.msgs, f: fmt },
    { t: "col.ctxMedio", k: (s) => (s.msgs ? (s.input + s.cache_read + s.cache_write) / s.msgs : 0), f: fmt, dica: "col.ctxMedio.dica" },
    { t: "col.tokens", k: (s) => s.tokens, f: fmt },
    { t: "col.api", k: (s) => s.usd, f: fmtUSD },
  ], F.sessoes.slice().sort((a, b) => b.tokens - a.tokens).slice(0, 40), 7);
}

// ---------------------------------------------------------------------------
// ferramentas, Graphify e Ollama
// ---------------------------------------------------------------------------
function renderFerramentas(F) {
  const fer = E.dados.ferramentas || {};
  const sh = E.dados.comandos_shell || {};
  document.getElementById("ferramentas-grade").innerHTML = ["claude", "codex", "opencode"].filter(agenteOk).map((a) => {
    const itens = Object.entries(fer[a] || {}).slice(0, 12).map(([n, v]) => ({ nome: n.replace(/^mcp__/, "mcp:"), valor: v, cor: corAgente(a), titulo: n }));
    const cmds = Object.entries(sh[a] || {}).slice(0, 8).map(([n, v]) => ({ nome: n, valor: v, cor: corAgente(a) }));
    return `<div class="cartao"><div class="cartao-topo"><h2>${esc(t("fer.titulo", { agente: nomeAgente(a) }))}</h2></div>
      <p class="explica">${esc(t("fer.explica"))}</p>${barras(itens)}
      <h2 style="margin-top:18px">${esc(t("fer.shell"))}</h2><p class="explica">${esc(t("fer.shell.explica"))}</p>${barras(cmds)}</div>`;
  }).join("");

  const ol = E.dados.ollama || {};
  const req = F.ollama.reduce((o, r) => { o.reqs += r.reqs; o.seg += r.segundos; o.erros += r.erros || 0; return o; }, { reqs: 0, seg: 0, erros: 0 });
  const viaOC = F.uso.filter((r) => r.modelo.startsWith("ollama/")).reduce((s, r) => s + novos(r), 0);
  const carregados = ol.carregados || [];
  document.getElementById("ollama").innerHTML = `
    <p class="explica" style="margin-top:0">${esc(t("ol.explica"))}</p>
    <div class="kpis">${kpi(t("ol.reqs"), fmt(req.reqs), esc(nomePeriodo()))}${kpi(t("ol.tempo"), fmtDur(req.seg), req.erros ? esc(t("ol.erros", { n: req.erros })) : "")}${kpi(t("ol.viaOC"), fmt(viaOC), "ollama/*")}${kpi(t("ol.instalados"), fmt((ol.modelos || []).length), esc(carregados.length ? t("ol.carregado", { m: carregados.join(", ") }) : t("ol.nenhum")))}</div>
    ${(ol.modelos || []).length ? `<table><thead><tr><th class="esq">${esc(t("col.modelo"))}</th><th>${esc(t("col.tamanho"))}</th></tr></thead><tbody>${ol.modelos.map((m) => `<tr><td class="esq trunca" title="${esc(m.nome)}">${esc(m.nome)}</td><td>${esc(m.tamanho)}</td></tr>`).join("")}</tbody></table>` : ""}`;
}

// ---------------------------------------------------------------------------
// o que otimizar
// ---------------------------------------------------------------------------
function renderDicas(F) {
  const d = E.dados, dicas = [];
  const add = (nivel, titulo, texto, acao) => dicas.push({ nivel, titulo, texto, acao });
  const porAg = soma(F.uso, (r) => r.agente, { novos, msgs: "msgs", input: "input", cr: "cache_read", cw: "cache_write", out: "output", usd: "usd" });
  const rtkAg = soma(F.rtk, (r) => r.agente, { cmds: "cmds", saved: "saved" });
  const totNovos = [...porAg.values()].reduce((s, o) => s + o.novos, 0) || 1;
  const P = nomePeriodo();

  // Codex e o RTK
  const cx = porAg.get("codex");
  if (cx && cx.msgs > 20 && temFerramenta("rtk")) {
    const sh = d.comandos_shell?.codex || {};
    const ps = Object.entries(sh).filter(([k]) => /^(get-|set-|select-|\$)/.test(k)).reduce((s, [, v]) => s + v, 0);
    const totSh = Object.values(sh).reduce((a, b) => a + b, 0) || 1;
    const rc = rtkAg.get("codex")?.cmds || 0;
    if (rc < cx.msgs * 0.2) {
      add("alta", t("d.codexRtk.t"), t("d.codexRtk.p", { Periodo: primeiraMaiuscula(P), n: fmt(cx.msgs), r: fmt(rc), pct: fmtPct((100 * ps) / totSh) }), t("d.codexRtk.a"));
    }
  }

  // ritmo do Codex
  const rec = janelasCodex().slice(-10).filter((j) => j.max > 0);
  const media = mediaRitmo(rec);
  const estouradas = rec.filter((j) => j.max >= 100).length;
  if (media && media > 20) {
    add(media > 40 ? "alta" : "media", t("d.ritmo.t", { pct: fmtPct(media) }),
      t("d.ritmo.p", {
        dur: fmtDur((100 / media) * 3600),
        estouro: estouradas ? t("d.ritmo.estouro", { n: estouradas, m: rec.length }) : "",
        plano: d.limites.codex.at(-1)?.plano || "",
        ctx: cx ? t("d.ritmo.ctx", { n: fmt((cx.input + cx.cr) / Math.max(cx.msgs, 1)) }) : "",
      }), t("d.ritmo.a"));
  }

  // cache do Codex x Claude
  const cachePct = (o) => (o ? (100 * o.cr) / Math.max(o.input + o.cr + o.cw, 1) : null);
  const cc = cachePct(porAg.get("claude")), cxc = cachePct(cx);
  if (cx && cxc != null && cc != null && cxc < cc - 10) add("media", t("d.cache.t"), t("d.cache.p", { a: fmtPct(cxc), b: fmtPct(cc) }), t("d.cache.a"));

  // Opus x Sonnet
  const mod = soma(F.uso.filter((r) => r.agente === "claude"), (r) => r.modelo, { v: novos, usd: "usd" });
  const opus = [...mod.entries()].filter(([k]) => k.includes("opus"));
  const opusV = opus.reduce((s, [, o]) => s + o.v, 0);
  const totCl = [...mod.values()].reduce((s, o) => s + o.v, 0);
  if (totCl && opusV / totCl > 0.85) {
    add("baixa", t("d.opus.t", { pct: fmtPct((100 * opusV) / totCl) }), t("d.opus.p", { usd: fmtUSD(opus.reduce((s, [, o]) => s + o.usd, 0)), periodo: P }), t("d.opus.a"));
  }

  // contexto médio do Claude
  const cl = porAg.get("claude");
  if (cl && cl.msgs) {
    const ctx = (cl.input + cl.cr + cl.cw) / cl.msgs;
    if (ctx > 120000) add("media", t("d.ctx.t", { n: fmt(ctx) }), t("d.ctx.p"), t("d.ctx.a"));
  }

  // sessões pesadas
  const pes = F.sessoes.filter((s) => s.tokens > 50e6).sort((a, b) => b.tokens - a.tokens);
  if (pes.length) {
    add("baixa", pes.length === 1 ? t("d.sess.t1") : t("d.sess.tn", { n: pes.length }),
      t("d.sess.p", { proj: nomeProjeto(pes[0].projeto), agente: nomeAgente(pes[0].agente), tok: fmt(pes[0].tokens), n: fmt(pes[0].msgs) }), t("d.sess.a"));
  }

  // ferramentas de espera
  const espera = Object.entries(d.ferramentas?.claude || {}).filter(([k]) => /wait|sleep|poll|status/i.test(k)).sort((a, b) => b[1] - a[1]);
  const totEsp = espera.reduce((s, [, v]) => s + v, 0);
  if (totEsp > 500) {
    add("media", t("d.espera.t", { n: fmt(totEsp) }), t("d.espera.p", { lista: espera.slice(0, 3).map(([k, v]) => `${k.replace(/^mcp__/, "")}: ${fmt(v)}`).join(", ") }), t("d.espera.a"));
  }

  // falhas do RTK
  const fal = d.rtk.falhas || [];
  if (temFerramenta("rtk") && fal.length && fal[0][1] > 200) add("baixa", t("d.falha.t", { cmd: fal[0][0], n: fmt(fal[0][1]) }), t("d.falha.p"), t("d.falha.a", { cmd: fal[0][0] }));

  // comandos sem ganho
  const pc = soma(F.rtkCmd, (r) => r.comando, { cmds: "cmds", zero: "zero" });
  const ruins = [...pc.entries()].filter(([, o]) => o.cmds >= 50 && o.zero / o.cmds > 0.7).sort((a, b) => b[1].cmds - a[1].cmds);
  if (temFerramenta("rtk") && ruins.length) {
    add("baixa", t("d.semGanho.t"), ruins.slice(0, 4).map(([k, o]) => t("d.semGanho.item", { cmd: k, pct: fmtPct((100 * o.zero) / o.cmds), n: fmt(o.cmds) })).join(", ") + ".", t("d.semGanho.a"));
  }

  // Headroom
  const hr = F.hr.reduce((o, r) => { o.saved += r.saved_medido || 0; o.antes += r.antes || 0; o.reqs += r.reqs; return o; }, { saved: 0, antes: 0, reqs: 0 });
  const hrUlt = Math.max(0, ...d.headroom.hora.map((r) => horaTs(r.hora)));
  if (temFerramenta("headroom") && (!hr.reqs || (hr.antes && hr.saved / hr.antes < 0.02))) {
    add("media", hr.reqs ? t("d.hr.t1", { pct: fmtPct((100 * hr.saved) / hr.antes, 1) }) : t("d.hr.t0"),
      hrUlt ? t("d.hr.p1", { quando: haQuanto(hrUlt) }) : t("d.hr.p0"), t("d.hr.a"));
  }

  // Graphify
  const g = d.graphify || {};
  const chG = Object.values(g.chamadas || {}).reduce((a, b) => a + b, 0);
  if (temFerramenta("graphify") && (g.projetos || []).length <= 3 && chG < 20) add("baixa", t("d.gf.t"), t("d.gf.p", { n: (g.projetos || []).length, c: fmt(chG) }), t("d.gf.a"));

  // participação
  const ordenado = [...porAg.entries()].sort((a, b) => b[1].novos - a[1].novos);
  if (ordenado.length) {
    add("ok", t("d.part.t", { agente: nomeAgente(ordenado[0][0]), pct: fmtPct((100 * ordenado[0][1].novos) / totNovos) }),
      t("d.part.p", { periodo: P, lista: ordenado.map(([a, o]) => `${nomeAgente(a)} ${fmtPct((100 * o.novos) / totNovos, 1)}`).join(", ") }), "");
  }

  const ordem = { alta: 0, media: 1, baixa: 2, ok: 3 };
  E.dicasAuto = dicas.sort((a, b) => ordem[a.nivel] - ordem[b.nivel]);
  document.getElementById("lista-dicas").innerHTML = htmlDicas(E.dicasAuto)
    || `<div class="vazio">${esc(t("dicas.nada"))}</div>`;
}

// ---------------------------------------------------------------------------
// fontes
// ---------------------------------------------------------------------------
function renderFontes() {
  const f = E.dados.fontes;
  const linhas = [
    ["Claude Code", "~/.claude/projects/**/*.jsonl", f.claude.ok, t("fontes.claude", { n: fmt(f.claude.arquivos) })],
    ["Codex", "~/.codex/sessions/**/rollout-*.jsonl", f.codex.ok, t("fontes.codex", { n: fmt(f.codex.arquivos), m: fmt(E.dados.limites.codex.length) })],
    ["OpenCode", "~/.local/share/opencode/opencode.db", f.opencode.ok, f.opencode.erro || t("fontes.opencode", { n: fmt(f.opencode.mensagens) })],
    ["Ollama", "%LOCALAPPDATA%/Ollama/server*.log", f.ollama.ok, f.ollama.erro || t("fontes.ollama", { n: fmt(f.ollama.requisicoes) })],
    ["RTK", "%LOCALAPPDATA%/rtk/history.db", f.rtk.ok, f.rtk.erro || t("fontes.rtk", { n: fmt(f.rtk.comandos) })],
    ["Headroom", "~/.headroom/savings_events.jsonl", f.headroom.ok, f.headroom.erro || t("fontes.headroom", { n: fmt(f.headroom.eventos) })],
    ["Graphify", "<project>/graphify-out/graph.json", true, t("fontes.graphify", { n: fmt(E.dados.graphify.projetos.length) })],
  ];
  document.getElementById("t-fontes").innerHTML = `<thead><tr><th class="esq">${esc(t("col.ferramenta"))}</th><th class="esq">${esc(t("col.arquivo"))}</th><th class="esq">${esc(t("col.status"))}</th><th class="esq">${esc(t("col.lido"))}</th></tr></thead><tbody>${linhas.map(([n, p, ok, det]) => `<tr><td class="esq">${n}</td><td class="esq"><code>${esc(p)}</code></td><td class="esq">${ok ? `<span class="status s-good">${esc(t("fontes.ok"))}</span>` : `<span class="status s-critical">${esc(t("fontes.nao"))}</span>`}</td><td class="esq">${esc(det)}</td></tr>`).join("")}</tbody>`;
  document.getElementById("fontes-nota").innerHTML = t("fontes.nota", { s: E.dados.duracao_coleta_s });
}

// ---------------------------------------------------------------------------
// análise por IA
// ---------------------------------------------------------------------------
const ROTULO_NIVEL = { alta: "!", media: "!", baixa: "i", ok: "✓" };
function htmlDicas(lista) {
  return lista.map((x) => `
    <div class="dica"><div class="ic ${x.nivel}" title="${esc(t("nivel." + x.nivel))}" aria-label="${esc(t("nivel." + x.nivel))}">${ROTULO_NIVEL[x.nivel] || "i"}</div>
      <div><h3>${esc(x.titulo)}${x.fonteTag ? `<span class="tag-fonte">${esc(x.fonteTag)}</span>` : ""}</h3><p>${esc(x.texto)}</p>${x.acao ? `<div class="acao">${esc(x.acao)}</div>` : ""}</div></div>`).join("");
}

let formIAMontado = false;
const elIA = (id) => document.getElementById(id);

async function carregarIA() {
  try {
    E.ia = await (await fetch("/api/ia", { cache: "no-store" })).json();
  } catch { return; }
  montarFormIA();
  renderIA();
  if (abaAtual() === "resumo") renderTudo();
  if (E.ia.estado.rodando) setTimeout(carregarIA, 2000);
}

function montarFormIA() {
  if (!E.ia) return;
  const d = E.ia.disponiveis, cfg = E.ia.config || {};
  const sel = elIA("ia-provedor");
  const padrao = cfg.tipo === "cli" && d.cli.some((c) => c.id === cfg.cli) ? "cli:" + cfg.cli
    : cfg.tipo === "api" ? "api" : cfg.tipo === "personalizado" ? "custom"
    : d.cli[0] ? "cli:" + d.cli[0].id : "api";
  const atual = sel.value || padrao;
  sel.innerHTML = `<optgroup label="${esc(t("ia.cli"))}">${d.cli.length ? d.cli.map((c) => `<option value="cli:${c.id}">${esc(c.nome)}</option>`).join("") : `<option disabled>${esc(t("ia.semCli"))}</option>`}</optgroup>
    <option value="api">${esc(t("ia.api"))}</option><option value="custom">${esc(t("ia.custom"))}</option>`;
  sel.value = atual;
  elIA("ia-api").innerHTML = d.apis.map((a) => `<option value="${a.id}">${esc(a.nome)}</option>`).join("");
  elIA("ia-dias").querySelectorAll("option").forEach((o) => (o.textContent = t("ia.dias.n", { n: o.value })));
  if (!formIAMontado) {
    elIA("ia-api").value = cfg.api || "openai";
    elIA("ia-url").value = cfg.url || (d.apis.find((a) => a.id === (cfg.api || "openai"))?.url || "");
    elIA("ia-modelo").value = cfg.modelo || "";
    elIA("ia-comando").value = cfg.comando || "";
    elIA("ia-dias").value = cfg.dias || "7";
    sel.onchange = () => { elIA("ia-modelo").value = ""; atualizarCamposIA(); };
    elIA("ia-api").onchange = () => {
      const a = d.apis.find((x) => x.id === elIA("ia-api").value);
      if (a && a.url) elIA("ia-url").value = a.url;
      atualizarCamposIA();
    };
    elIA("ia-analisar").onclick = analisarIA;
    formIAMontado = true;
  } else {
    elIA("ia-api").value = elIA("ia-api").dataset.v || cfg.api || "openai";
  }
  atualizarCamposIA();
}

function atualizarCamposIA() {
  const v = elIA("ia-provedor").value || "";
  const cli = v.startsWith("cli:") ? E.ia.disponiveis.cli.find((c) => "cli:" + c.id === v) : null;
  const api = v === "api", custom = v === "custom";
  elIA("ia-api").dataset.v = elIA("ia-api").value;
  elIA("ia-campo-api").hidden = !api;
  elIA("ia-campo-url").hidden = !api;
  elIA("ia-campo-chave").hidden = !api;
  elIA("ia-campo-comando").hidden = !custom;
  elIA("ia-campo-modelo").hidden = custom;
  elIA("ia-comando").placeholder = t("ia.comando.ph");
  elIA("ia-chave").placeholder = E.ia.config?.tem_chave ? t("ia.chave.salva") : t("ia.chave.ph");
  const obrig = cli?.modelo_obrigatorio || api;
  elIA("ia-modelo").placeholder = obrig ? t("ia.modelo.obrigatorio") : t("ia.modelo.ph");
  // sugestões de modelo: os do Ollama instalados, ou os já usados nos dados
  const sugestoes = cli?.id === "ollama"
    ? (E.dados?.ollama?.modelos || []).map((m) => m.nome)
    : [...new Set((E.dados?.uso || []).map((r) => r.modelo))].filter((m) => m && m !== "?");
  elIA("ia-modelos").innerHTML = sugestoes.map((m) => `<option value="${esc(m)}">`).join("");
  elIA("ia-aviso").textContent = custom ? t("ia.comando.dica") : cli && !cli.verificado ? t("ia.naoVerificado") : "";
}

async function analisarIA() {
  const v = elIA("ia-provedor").value || "";
  const corpo = { idioma: IDIOMA, dias: elIA("ia-dias").value, modelo: elIA("ia-modelo").value.trim() };
  if (v.startsWith("cli:")) Object.assign(corpo, { tipo: "cli", cli: v.slice(4) });
  else if (v === "api") Object.assign(corpo, { tipo: "api", api: elIA("ia-api").value, url: elIA("ia-url").value.trim(), chave: elIA("ia-chave").value });
  else Object.assign(corpo, { tipo: "personalizado", comando: elIA("ia-comando").value.trim() });
  elIA("ia-analisar").disabled = true;
  try {
    const r = await postar("/api/ia/analisar", corpo);
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      elIA("ia-status").innerHTML = `<div class="ia-status erro">${esc(t("ia.erro", { msg: j.erro || r.status }))}</div>`;
    }
  } finally {
    elIA("ia-chave").value = "";
    setTimeout(carregarIA, 800);
  }
}

function corNota(n) {
  return n >= 80 ? css("--good") : n >= 60 ? css("--warning") : n >= 40 ? css("--serious") : css("--critical");
}

function renderIA() {
  if (!E.ia) return;
  const est = E.ia.estado || {};
  elIA("ia-analisar").disabled = !!est.rodando;
  elIA("ia-status").innerHTML = est.rodando
    ? `<div class="ia-status">${esc(t("ia.rodando", { etapa: "", s: Math.round(Date.now() / 1000 - (est.inicio || Date.now() / 1000)) }))}</div>`
    : est.erro ? `<div class="ia-status erro">${esc(t("ia.erro", { msg: est.erro }))}</div>` : "";
  const hist = E.ia.historico || [];
  if (!hist.length) {
    elIA("ia-resultado").innerHTML = `<div class="vazio">${esc(t("ia.nenhuma"))}</div>`;
    return;
  }
  const a = hist[0];
  const meta = t("ia.feita", { data: fmtData(a.data), quem: a.quem, modelo: a.modelo ? ` (${a.modelo})` : "", dias: a.dias, s: a.segundos });
  const nota = "";  // a nota vem do cálculo do painel (acima), não da IA
  const ant = hist.slice(1, 8);
  elIA("ia-resultado").innerHTML = `
    <div class="ia-topo" style="grid-template-columns:1fr">${nota}<div><p class="ia-resumo">${esc(a.resumo)}</p><div class="mudo">${esc(meta)}</div></div></div>
    ${htmlDicas(a.itens || [])}
    ${ant.length ? `<details class="ia-anteriores"><summary>${esc(t("ia.anteriores"))} (${ant.length})</summary><ul>${ant.map((x) => `<li>${esc(fmtData(x.data))} · ${esc(x.quem)}${x.nota != null ? ` · ${x.nota}/100` : ""} · ${esc(x.resumo || "")}</li>`).join("")}</ul></details>` : ""}`;
}

// ---------------------------------------------------------------------------
// preços
// ---------------------------------------------------------------------------
function renderPrecos() {
  const p = E.dados.precos || {};
  const f = p.fontes || {};
  elIA("precos-fontes").innerHTML = `<div class="barras">${["manual", "litellm", "openrouter", "padrao"].filter((k) => f[k]).map((k) => `
    <div class="barra-linha" style="grid-template-columns:minmax(200px,40%) 1fr">
      <div class="barra-nome">${esc(t("precos.fonte." + k))}</div>
      <div class="mudo">${esc(t("precos.modelos", { n: fmt(f[k].modelos) }))}${f[k].atualizado ? " · " + esc(t("precos.atualizado", { quando: haQuanto(f[k].atualizado) })) : ""}</div>
    </div>`).join("")}</div>
    <p class="explica" style="margin-top:10px">${esc(p.sem_preco?.length ? t("precos.semPreco", { lista: p.sem_preco.join(", ") }) : t("precos.todos"))}</p>`;
  const linhas = Object.entries(p.por_modelo || {}).map(([m, v]) => ({ modelo: m, fonte: v.fonte, ...(v.preco || {}) }));
  tabela("t-precos", [
    { t: "col.modelo", k: (r) => r.modelo, esq: true },
    { t: "col.fonte", k: (r) => (r.fonte ? t("precos.fonte." + r.fonte) : "–"), esq: true },
    { t: "col.entrada", k: (r) => r.input, f: (v) => (v != null ? "$" + v.toLocaleString(LOC, { maximumFractionDigits: 3 }) : "–") },
    { t: "col.saida", k: (r) => r.output, f: (v) => (v != null ? "$" + v.toLocaleString(LOC, { maximumFractionDigits: 3 }) : "–") },
    { t: "col.cacheLe", k: (r) => r.cache_read, f: (v) => (v != null ? "$" + v.toLocaleString(LOC, { maximumFractionDigits: 3 }) : "–") },
  ], linhas, 0);
}

document.getElementById("btn-precos").onclick = async (ev) => {
  const b = ev.currentTarget;
  b.disabled = true;
  try {
    await postar("/api/precos/atualizar");
    const antes = E.dados?.gerado_em || 0, t0 = Date.now();
    while (Date.now() - t0 < 90000) {
      await new Promise((r) => setTimeout(r, 1500));
      const j = await (await fetch("/api/dados", { cache: "no-store" })).json();
      if (j.gerado_em && j.gerado_em > antes) { E.dados = j; renderTudo(); break; }
    }
  } finally { b.disabled = false; }
};

// unidade (tokens ou US$)
document.querySelectorAll("#unidade button").forEach((b) => {
  b.classList.toggle("ativo", b.dataset.u === E.unidade);
  b.onclick = () => {
    E.unidade = b.dataset.u;
    gravarPref("unidade", E.unidade);
    document.querySelectorAll("#unidade button").forEach((x) => x.classList.toggle("ativo", x === b));
    renderTudo();
  };
});

// ---------------------------------------------------------------------------
// janelas de limite (todos os agentes)
// ---------------------------------------------------------------------------
function nomeJanela(id) {
  // semanal por modelo: "weekly_scoped:Fable" -> "Semanal · Fable"
  if (id.startsWith("weekly_scoped:")) return `${t("jan.seven_day")} · ${id.slice(14)}`;
  // limites extras do Codex: "extra:Nome:five_hour" -> "Nome · Janela de 5 h"
  if (id.startsWith("extra:")) { const [, nome, jan] = id.split(":"); return `${nome} · ${nomeJanela(jan || "")}`; }
  const k = "jan." + id;
  if (TXT[IDIOMA]?.[k] || TXT.en[k]) return t(k);
  return id.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}
const janelasVisiveis = () => (E.dados.limites.janelas || []).filter((j) => agenteOk(j.agente));
// servidor antigo (antes desta versão) não manda a lista de janelas
const servidorAntigo = () => !("janelas" in (E.dados.limites || {}));
const avisoVersao = () => (servidorAntigo() ? `<p class="explica" style="color:var(--serious)">${esc(t("jan.reiniciar"))}</p>` : "");

function previsaoJanela(j) {
  if (j.previsto_no_reset == null) return "";
  return j.acaba_antes
    ? `<div class="prev ruim">${esc(t("jan.acaba", { dur: fmtDur(j.acaba_em_h * 3600) }))}</div>`
    : `<div class="prev mudo">${esc(t("jan.chega", { pct: fmtPct(Math.min(j.previsto_no_reset, 999)) }))}</div>`;
}

function cartaoJanela(j) {
  const agora = Date.now() / 1000;
  return `<div class="janela">
    <div class="cab"><b>${esc(nomeJanela(j.id))}</b></div>
    <div class="pct">${fmtPct(j.pct)}</div>
    <div class="trilho" style="height:10px;background:var(--bar-track);border-radius:5px;overflow:hidden" role="meter" aria-valuenow="${j.pct}" aria-valuemin="0" aria-valuemax="100"><div style="height:100%;width:${Math.min(j.pct, 100)}%;background:${corPct(j.pct)};border-radius:5px"></div></div>
    <div class="mudo" style="margin-top:6px">${esc(j.reset ? t("jan.zera", { dur: fmtDur(j.reset - agora) }) : t("jan.livre"))}${j.ritmo_h ? " · " + esc(t("jan.ritmo", { pct: fmtPct(j.ritmo_h, 1) })) : ""}${j.lido_em ? " · " + esc(t("jan.lido", { quando: haQuanto(j.lido_em) })) : ""}</div>
    ${previsaoJanela(j)}
  </div>`;
}

function blocoCreditos() {
  if (!agenteOk("claude")) return "";
  const n = (v) => (v ?? 0).toLocaleString(LOC, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  let html = "";
  // créditos de sessão na nuvem do Claude Code
  const nv = E.dados.limites.claude_api?.nuvem;
  if (nv && nv.limite_usd) {
    const usado = Math.max(0, nv.limite_usd - (nv.restante_usd ?? nv.limite_usd));
    const det = [t("nuvem.sobra", { sobra: n(nv.restante_usd), limite: n(nv.limite_usd) })];
    if (nv.reset) det.push(t("nuvem.renova", { dur: fmtDur(nv.reset - Date.now() / 1000) }));
    if (nv.bloqueado) det.push(t("nuvem.bloqueado"));
    html += miniMedidor(t("nuvem.titulo"), (100 * usado) / nv.limite_usd, det.join(" · "));
  }
  const ex = E.dados.limites.claude_api?.extra;
  if (!ex) return html;
  return html + blocoExtra(ex, n);
}

function blocoExtra(ex, n) {
  if (!ex.ativo) return "";
  if (ex.limite_usd) {
    const pct = ex.pct ?? (100 * (ex.usado_usd || 0)) / ex.limite_usd;
    return miniMedidor(t("cred.titulo"), pct, `${t("cred.uso", { usado: n(ex.usado_usd), limite: n(ex.limite_usd) })} · ${t("cred.sobra", { sobra: n(Math.max(0, ex.limite_usd - (ex.usado_usd || 0))) })}`);
  }
  return `<div class="mudo" style="margin-top:6px">${esc(t("cred.titulo"))}: ${esc(t("cred.semLimite", { usado: n(ex.usado_usd) }))}</div>`;
}

// agrupa as janelas por agente, com o plano uma vez só no cabeçalho
function porAgente(js) {
  const g = new Map();
  for (const j of js) {
    if (!g.has(j.agente)) g.set(j.agente, { agente: j.agente, plano: j.plano, janelas: [] });
    g.get(j.agente).janelas.push(j);
  }
  return [...g.values()];
}
const cabAgente = (g) => `<div class="cab-agente"><span class="bolinha" style="background:${corAgente(g.agente)}"></span><b>${esc(nomeAgente(g.agente))}</b>${g.plano ? `<span class="etiqueta">${esc(t("jan.plano", { p: g.plano }))}</span>` : ""}</div>`;

function avisoClaude() {
  const c = E.dados.limites.claude_api;
  if (!c || c.ok || !agenteOk("claude")) return "";
  const chave = "lim.claude.erro." + c.erro;
  const msg = TXT[IDIOMA]?.[chave] || TXT.en[chave] ? t(chave) : t("lim.claude.erro.outro", { erro: c.erro || "?" });
  return `<p class="explica" style="margin:6px 0 0">${esc(msg)}</p>`;
}

function iniciarAjusteLimites() {
  const cb = document.getElementById("aj-limites-claude");
  if (!cb) return;
  cb.checked = E.config?.limites_claude !== false;
  cb.onchange = async () => {
    const r = await postar("/api/config", { limites_claude: cb.checked });
    if (r.ok) { E.config = await r.json(); postar("/api/atualizar"); }
  };
}

// ---------------------------------------------------------------------------
// resumo (primeira aba)
// ---------------------------------------------------------------------------
function diasNoPeriodo() {
  const [ini, fim] = intervalo();
  if (E.periodo !== "tudo") return (fim - ini) / 86400;
  const primeira = E.dados.uso.reduce((m, r) => (r.hora < m ? r.hora : m), "9999");
  return primeira === "9999" ? 0 : (fim - horaTs(primeira)) / 86400;
}

function corPct(p) {
  return p >= 90 ? css("--critical") : p >= 70 ? css("--serious") : p >= 50 ? css("--warning") : css("--good");
}

function miniMedidor(rotulo, pct, detalhe) {
  return `<div class="mini-medidor">
    <div class="topo-m"><span>${esc(rotulo)}</span><b>${fmtPct(pct)}</b></div>
    <div class="trilho" role="meter" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100"><div class="cheio" style="width:${Math.min(pct, 100)}%;background:${corPct(pct)}"></div></div>
    ${detalhe ? `<div class="mudo">${esc(detalhe)}</div>` : ""}
  </div>`;
}

function circuloNota(n) {
  if (n == null) return `<div class="ia-nota" style="--nota:0;--cor-nota:var(--bar-track)"><span>–</span></div>`;
  return `<div class="ia-nota" style="--nota:${n};--cor-nota:${corNota(n)}" role="meter" aria-valuenow="${n}" aria-valuemin="0" aria-valuemax="100" aria-label="${esc(t("resumo.nota"))}"><span>${n}</span></div>`;
}

function renderResumo(F) {
  const usd = emUSD(), fu = fmtU();

  // quanto vale o uso: assinaturas proporcionais x valor em API x economia
  const apiUsd = F.uso.reduce((s, r) => s + (r.usd || 0), 0);
  const ecoUsd = linhasEconomia(F).reduce((s, r) => s + r.est, 0);
  const ass = (E.config?.assinaturas || []).filter((a) => a.mensal > 0 && (!a.agente || agenteOk(a.agente)));
  const pago = ass.reduce((s, a) => s + a.mensal, 0) * diasNoPeriodo() / 30.44;
  const itens = [];
  if (ass.length) itens.push({ nome: t("resumo.valor.pago"), valor: pago, cor: css("--a-desconhecido") });
  itens.push({ nome: t("resumo.valor.api"), valor: apiUsd, cor: css("--s1") });
  itens.push({ nome: t("resumo.valor.eco"), valor: ecoUsd, cor: css("--s4") });
  document.getElementById("resumo-valor").innerHTML = barras(itens, fmtUSD)
    + `<p class="valor-mult">${esc(ass.length && pago > 0 ? t("resumo.valor.mult", { periodo: nomePeriodo(), x: (apiUsd / pago).toLocaleString(LOC, { maximumFractionDigits: 1 }) }) : t("resumo.valor.semAss"))}</p>`;

  // limites agora: todas as janelas de todos os agentes, com previsão
  const js = janelasVisiveis();
  document.getElementById("resumo-limites").innerHTML = (js.length
    ? porAgente(js).map((g) => cabAgente(g) + g.janelas.map((j) => miniMedidor(nomeJanela(j.id), j.pct,
        j.reset ? t("jan.zera", { dur: fmtDur(j.reset - Date.now() / 1000) }) : t("jan.livre")) + previsaoJanela(j)).join("")
        + (g.agente === "claude" ? blocoCreditos() : "")).join("")
    : `<div class="vazio">${esc(t("resumo.limites.sem"))}</div>`) + avisoClaude() + avisoVersao();

  // pizza por agente
  const valor = usd ? (r) => r.usd || 0 : novos;
  const porAg = soma(F.uso, (r) => r.agente, { v: valor });
  const ags = ORDEM_AGENTES.filter((a) => porAg.has(a) && porAg.get(a).v > 0);
  const totAg = ags.reduce((s, a) => s + porAg.get(a).v, 0) || 1;
  desenhar("g-pizza", {
    type: "doughnut",
    data: { labels: ags.map(nomeAgente), datasets: [{ data: ags.map((a) => porAg.get(a).v), backgroundColor: ags.map(corAgente), borderColor: css("--surface"), borderWidth: 2 }] },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false, cutout: "62%",
      plugins: {
        legend: { position: "right", labels: { color: css("--text-2"), boxWidth: 10, boxHeight: 10, usePointStyle: true, pointStyle: "rectRounded", padding: 14,
          generateLabels: (ch) => ch.data.labels.map((l, i) => ({ text: `${l}  ${fmtPct((100 * ch.data.datasets[0].data[i]) / totAg)}`, fillStyle: ch.data.datasets[0].backgroundColor[i], strokeStyle: "transparent", fontColor: css("--text-2"), index: i })) } },
        tooltip: { backgroundColor: css("--surface"), titleColor: css("--text"), bodyColor: css("--text-2"), borderColor: css("--border"), borderWidth: 1, padding: 10,
          callbacks: { label: (c) => ` ${c.label}: ${fu(c.parsed)} (${fmtPct((100 * c.parsed) / totAg)})` } },
      },
    },
  });

  // uso por dia (ou hora), empilhado por agente
  const porHoras = E.periodo === "hoje" || E.periodo === "24h";
  const chave = porHoras ? (r) => r.hora : (r) => diaDe(r.hora);
  const mapa = soma(F.uso, (r) => chave(r) + "|" + r.agente, { v: valor });
  const rotulos = porHoras
    ? [...new Set(F.uso.map((r) => r.hora))].sort()
    : diasDoPeriodo(F.uso.length ? F.uso.reduce((m, r) => (r.hora < m ? r.hora : m), "9999").slice(0, 10) : null);
  desenhar("g-resumo-dias", {
    type: "bar",
    data: {
      labels: rotulos.map((x) => (porHoras ? x.slice(11, 13) + "h" : diaCurto(x))),
      datasets: ags.map((a) => barraDS(nomeAgente(a), rotulos.map((x) => mapa.get(x + "|" + a)?.v || 0), corAgente(a), "r")),
    },
    options: empilhado(fu),
  });

  // principais pontos: análise por IA recente primeiro, depois as regras automáticas
  const ordem = { alta: 0, media: 1, baixa: 2, ok: 3 };
  const ia = (E.ia?.historico || [])[0];
  const daIA = ia && Date.now() / 1000 - ia.data < 8 * 86400 ? (ia.itens || []).map((x) => ({ ...x, fonte: "ia" })) : [];
  const auto = (E.dicasAuto || []).map((x) => ({ ...x, fonte: "auto" }));
  const lista = [...daIA.filter((x) => x.nivel !== "ok"), ...auto.filter((x) => x.nivel !== "ok")]
    .sort((a, b) => ordem[a.nivel] - ordem[b.nivel]).slice(0, 5);
  document.getElementById("resumo-insights").innerHTML = lista.length
    ? htmlDicas(lista.map((x) => ({ ...x, titulo: x.titulo, fonteTag: t(x.fonte === "ia" ? "fonte.ia" : "fonte.auto") })))
    : `<div class="vazio">${esc(t("dicas.nada"))}</div>`;
}

// ---------------------------------------------------------------------------
// nota (calculada pelo servidor para o período escolhido)
// ---------------------------------------------------------------------------
async function carregarNota() {
  const [ini, fim] = intervalo();
  const iniReal = E.periodo === "tudo" ? fim - 3650 * 86400 : ini;
  try {
    const r = await fetch(`/api/nota?ini=${Math.floor(iniReal)}&fim=${Math.ceil(fim)}`, { cache: "no-store" });
    if (r.status !== 200) return;
    E.nota = await r.json();
  } catch { return; }
  renderNota();
}

function valorCriterio(c, v) {
  return c.unidade === "tokens" ? fmt(v) : fmtPct(v, v < 10 ? 1 : 0);
}

function textoCriterio(c, sufixo) {
  const ex = c.extra || {};
  return t(`nota.c.${c.id}.${sufixo}`, {
    limite: ex.limite, modelos: (ex.modelos || []).join(", "), fora: fmt(ex.fora || 0),
    estouradas: ex.estouradas, janelas: ex.janelas,
  });
}

function renderNota() {
  const N = E.nota;
  if (!N) return;
  const perdas = N.componentes.filter((c) => c.peso - c.pontos >= 0.5).slice(0, 3);
  document.getElementById("resumo-nota").innerHTML = `<div class="nota-grande">${circuloNota(N.nota)}
    <div class="ganhos">${perdas.map((c) => `<div>${esc(t("resumo.nota.ganho", { p: fmt(c.peso - c.pontos), criterio: textoCriterio(c, "t").toLowerCase() }))}</div>`).join("")}
      <a href="#dicas" class="link">${esc(t("resumo.nota.ver"))}</a></div></div>`;
  document.getElementById("nota-detalhe").innerHTML = `<div class="nota-grande" style="margin-bottom:8px">${circuloNota(N.nota)}<div></div></div>`
    + N.componentes.map((c) => {
      const frac = c.peso ? c.pontos / c.peso : 0;
      const cor = frac >= 0.9 ? css("--good") : frac >= 0.5 ? css("--warning") : css("--critical");
      return `<div class="criterio">
        <div><h3>${esc(textoCriterio(c, "t"))}</h3><p>${esc(textoCriterio(c, "o"))}</p></div>
        <div class="numeros">
          <span>${esc(t("nota.seu"))}: <b>${esc(valorCriterio(c, c.valor))}</b></span>
          <span>${esc(t("nota.meta"))}: <b>${esc(valorCriterio(c, c.meta))}</b> · ${esc(t("nota.ruim"))}: ${esc(valorCriterio(c, c.ruim))}</span>
          <div class="barra-pts"><div style="width:${100 * frac}%;background:${cor}"></div></div>
          <span><b>${esc(t("nota.pontos", { p: fmt(c.pontos), max: fmt(c.peso) }))}</b></span>
        </div>
        <div>${frac < 0.99 ? `<div class="acao">${esc(textoCriterio(c, "a"))}</div>` : ""}</div>
      </div>`;
    }).join("")
    + (N.fora?.length ? `<p class="explica" style="margin-top:10px">${esc(t("nota.fora", { lista: N.fora.map((k) => t(`nota.c.${k}.t`)).join(", ") }))}</p>` : "");
}

// ---------------------------------------------------------------------------
// assinaturas
// ---------------------------------------------------------------------------
async function carregarConfig() {
  try { E.config = await (await fetch("/api/config", { cache: "no-store" })).json(); } catch { E.config = {}; }
  renderAssinaturas();
  iniciarAjusteLimites();
  renderTudo();
}

function renderAssinaturas() {
  const el = document.getElementById("assinaturas");
  if (!el) return;
  const lista = E.assEdit || (E.assEdit = (E.config?.assinaturas || []).map((a) => ({ ...a })));
  const opcoes = (sel) => [...ORDEM_AGENTES.filter((a) => a !== "desconhecido"), ""].map((a) =>
    `<option value="${a}" ${a === sel ? "selected" : ""}>${esc(a ? nomeAgente(a) : t("ass.outro"))}</option>`).join("");
  el.innerHTML = lista.map((a, i) => `<div class="ass-linha" data-i="${i}">
      <label>${esc(t("ass.nome"))}<input data-k="nome" value="${esc(a.nome)}" placeholder="Claude Max"></label>
      <label>${esc(t("ass.agente"))}<select data-k="agente">${opcoes(a.agente)}</select></label>
      <label>${esc(t("ass.mensal"))}<input data-k="mensal" type="number" min="0" step="0.01" value="${a.mensal ?? ""}"></label>
      <button class="botao" data-remover="${i}">${esc(t("ass.remover"))}</button>
    </div>`).join("")
    + `<div class="ass-linha"><button class="botao" id="ass-add">${esc(t("ass.add"))}</button><button class="botao primario" id="ass-salvar">${esc(t("ass.salvar"))}</button><span class="mudo" id="ass-msg"></span></div>`;
  el.querySelectorAll(".ass-linha[data-i] [data-k]").forEach((inp) => inp.oninput = inp.onchange = () => {
    const i = +inp.closest(".ass-linha").dataset.i;
    lista[i][inp.dataset.k] = inp.dataset.k === "mensal" ? parseFloat(inp.value) : inp.value;
  });
  el.querySelectorAll("[data-remover]").forEach((b) => b.onclick = () => { lista.splice(+b.dataset.remover, 1); renderAssinaturas(); });
  document.getElementById("ass-add").onclick = () => { lista.push({ nome: "", agente: "claude", mensal: null }); renderAssinaturas(); };
  document.getElementById("ass-salvar").onclick = async () => {
    const r = await postar("/api/config", { assinaturas: lista.filter((a) => a.mensal >= 0 && a.mensal !== null && !isNaN(a.mensal)) });
    if (r.ok) {
      E.config = await r.json();
      E.assEdit = null;
      renderAssinaturas();
      document.getElementById("ass-msg").textContent = t("ass.salvo");
      renderTudo();
    }
  };
}

// ---------------------------------------------------------------------------
// abas: uma seção por vez
// ---------------------------------------------------------------------------
const ABAS = ["resumo", "visao", "limites", "modelos", "economia", "projetos", "ferramentas", "dicas", "fontes"];
function abaAtual() {
  const h = location.hash.replace("#", "");
  return ABAS.includes(h) ? h : "resumo";
}
function mostrarAba() {
  if (!E.dados) return;
  const a = abaAtual();
  document.querySelectorAll(".secao").forEach((s) => (s.hidden = s.id !== a));
  document.querySelectorAll("#abas a").forEach((l) => l.classList.toggle("ativo", l.getAttribute("href") === "#" + a));
  // os gráficos medem o espaço ao serem desenhados: redesenha a aba que apareceu
  renderTudo();
  window.scrollTo({ top: 0 });
}
window.addEventListener("hashchange", mostrarAba);

// ---------------------------------------------------------------------------
// ciclo
// ---------------------------------------------------------------------------
function renderChips() {
  const presentes = ORDEM_AGENTES.filter((a) => E.dados.uso.some((r) => r.agente === a) || E.dados.rtk.hora.some((r) => r.agente === a));
  document.getElementById("filtro-agentes").innerHTML = presentes.map((a) =>
    `<button class="chip ${E.desligados.has(a) ? "desligado" : ""}" data-a="${a}" aria-pressed="${!E.desligados.has(a)}"><span class="bolinha" style="background:${corAgente(a)}"></span>${esc(nomeAgente(a))}</button>`).join("");
  document.querySelectorAll("#filtro-agentes .chip").forEach((b) => b.onclick = () => {
    const a = b.dataset.a;
    E.desligados.has(a) ? E.desligados.delete(a) : E.desligados.add(a);
    gravarPref("desligados", JSON.stringify([...E.desligados]));
    renderTudo();
  });
}

function renderTudo() {
  if (!E.dados) return;
  renderChips();
  const F = filtrados();
  // só desenha a aba visível (as escondidas não têm tamanho para os gráficos);
  // as regras automáticas rodam sempre porque alimentam o Resumo
  const porAba = { resumo: [renderResumo], visao: [renderVisao], limites: [renderLimites], modelos: [renderModelos],
    economia: [renderEconomia], projetos: [renderProjetos], ferramentas: [renderFerramentas], dicas: [renderIA, renderNota], fontes: [renderFontes, renderPrecos] };
  for (const fn of [renderDicas, ...(porAba[abaAtual()] || [])]) {
    try { fn(F); } catch (e) { console.error(fn.name, e); }
  }
  carregarNota();
  document.getElementById("atualizado").textContent = t("topo.dados", { quando: haQuanto(E.dados.gerado_em) });
}

async function carregar() {
  try {
    const r = await fetch("/api/dados", { cache: "no-store" });
    const j = await r.json();
    if (r.status === 202 || j.carregando) {
      document.getElementById("carregando-status").textContent = j.erro ? t("carregando.erro", { msg: j.erro.split("\n")[0] }) : t("carregando.titulo");
      setTimeout(carregar, 1500);
      return;
    }
    E.dados = j;
    document.getElementById("carregando").hidden = true;
    mostrarAba();
  } catch {
    document.getElementById("carregando-status").textContent = t("carregando.fora");
    setTimeout(carregar, 4000);
  }
}

// idioma
function iniciarIdioma() {
  const sel = document.getElementById("idioma");
  sel.innerHTML = Object.entries(IDIOMAS).map(([k, v]) => `<option value="${k}">${v}</option>`).join("");
  sel.value = IDIOMA;
  sel.onchange = () => {
    IDIOMA = sel.value;
    gravarPref("idioma", IDIOMA);
    // avisa o servidor para o app da bandeja usar a mesma língua
    postar("/api/config", { idioma: IDIOMA }).catch(() => {});
    configurarFormatos();
    traduzirPagina();
    montarFormIA();
    renderAssinaturas();
    renderTudo();
  };
  traduzirPagina();
  document.getElementById("atualizado").textContent = t("topo.carregando");
}
iniciarIdioma();

document.querySelectorAll("#periodo button").forEach((b) => {
  b.classList.toggle("ativo", b.dataset.p === E.periodo);
  b.onclick = () => {
    E.periodo = b.dataset.p;
    gravarPref("periodo", E.periodo);
    document.querySelectorAll("#periodo button").forEach((x) => x.classList.toggle("ativo", x === b));
    renderTudo();
  };
});

document.getElementById("btn-atualizar").onclick = async (ev) => {
  const b = ev.currentTarget;
  b.disabled = true; b.textContent = t("btn.lendo");
  try {
    await postar("/api/atualizar");
    const t0 = Date.now();
    const antes = E.dados?.gerado_em || 0;
    while (Date.now() - t0 < 120000) {
      await new Promise((r) => setTimeout(r, 1200));
      const j = await (await fetch("/api/dados", { cache: "no-store" })).json();
      if (j.gerado_em && j.gerado_em > antes) { E.dados = j; renderTudo(); break; }
    }
  } finally { b.disabled = false; b.textContent = t("btn.atualizar"); }
};

// tema
(function () {
  const salvo = lerPref("tema", "");
  if (salvo) document.documentElement.dataset.theme = salvo;
  document.getElementById("btn-tema").onclick = () => {
    const escuroAgora = document.documentElement.dataset.theme ? document.documentElement.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    const novo = escuroAgora ? "light" : "dark";
    document.documentElement.dataset.theme = novo;
    gravarPref("tema", novo);
    renderTudo();
  };
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => !document.documentElement.dataset.theme && renderTudo());
})();


// recarrega os dados a cada minuto (o servidor coleta em segundo plano)
setInterval(async () => {
  try {
    const j = await (await fetch("/api/dados", { cache: "no-store" })).json();
    if (j.gerado_em && (!E.dados || j.gerado_em > E.dados.gerado_em)) { E.dados = j; renderTudo(); }
  } catch { /* servidor fora */ }
}, 60000);

// a configuração (assinaturas, ajustes) chega antes do primeiro desenho
carregarConfig().finally(() => { carregar(); carregarIA(); });
