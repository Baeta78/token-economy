"use strict";
/* global t, LANG, LANGUAGES, LOCALES, translatePage */

// ---------------------------------------------------------------------------
// preferences saved before the English translation used Portuguese keys and values
// ---------------------------------------------------------------------------
(function migratePrefs() {
  try {
    const OLD = { periodo: "period", desligados: "hiddenAgents", unidade: "unit", tema: "theme", idioma: "language" };
    const VALUES = { hoje: "today", tudo: "all" };
    for (const [old, key] of Object.entries(OLD)) {
      const v = localStorage.getItem("painel." + old);
      if (v == null) continue;
      if (localStorage.getItem("panel." + key) == null) {
        localStorage.setItem("panel." + key, old === "desligados" ? v.replace(/"desconhecido"/g, '"unknown"') : VALUES[v] ?? v);
      }
      localStorage.removeItem("painel." + old);
    }
  } catch { /* no storage */ }
})();

// ---------------------------------------------------------------------------
// state
// ---------------------------------------------------------------------------
const S = {
  data: null,
  period: readPref("period", "7d"),
  hiddenAgents: new Set(JSON.parse(readPref("hiddenAgents", "[]"))),
  unit: new URLSearchParams(location.search).get("unit") || readPref("unit", "tokens"),
  charts: {},
  ai: null,
};
const inUSD = () => S.unit === "usd";

// requests that change something on the server carry this header (protection against other sites)
function post(url, body) {
  return fetch(url, { method: "POST", headers: { "Content-Type": "application/json", "X-Token-Panel": "1" }, body: JSON.stringify(body || {}) });
}
const AGENT_ORDER = ["claude", "codex", "opencode", "ollama", "unknown"];

function readPref(k, def) { try { return localStorage.getItem("panel." + k) ?? def; } catch { return def; } }
function savePref(k, v) { try { localStorage.setItem("panel." + k, v); } catch { /* no storage */ } }

// ---------------------------------------------------------------------------
// formatting (follows the chosen language)
// ---------------------------------------------------------------------------
let nf, nfc, usdf, rtf, LOC;
function configureFormats() {
  LOC = LOCALES[LANG] || "en-US";
  nf = new Intl.NumberFormat(LOC);
  nfc = new Intl.NumberFormat(LOC, { notation: "compact", maximumFractionDigits: 1 });
  usdf = new Intl.NumberFormat(LOC, { style: "currency", currency: "USD", maximumFractionDigits: 2 });
  rtf = new Intl.RelativeTimeFormat(LOC, { numeric: "auto" });
}
configureFormats();

const fmt = (n) => {
  if (n == null || isNaN(n)) return "–";
  // Spanish has no short form for billions in the browser ("2864,2 M"); use "2,9 mil M"
  if (LANG === "es" && Math.abs(n) >= 1e9) return (n / 1e9).toLocaleString(LOC, { maximumFractionDigits: 1 }) + " mil M";
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

function fmtDur(sec) {
  if (sec == null || !isFinite(sec)) return "–";
  sec = Math.max(0, sec);
  const totalMin = Math.round(sec / 60);  // round before splitting: never "4 h 60 min"
  const h = Math.floor(totalMin / 60), m = totalMin % 60;
  if (h >= 48) return t("days", { n: Math.round(h / 24) });
  if (h > 0) return `${h} h ${String(m).padStart(2, "0")} min`;
  return `${m} min`;
}
function fmtDate(ts, withTime = true) {
  const d = new Date(ts * 1000);
  return d.toLocaleString(LOC, withTime ? { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" } : { day: "2-digit", month: "2-digit" });
}
function timeAgo(ts) {
  const s = Date.now() / 1000 - ts;
  if (s < 60) return t("now");
  if (s < 3600) return rtf.format(-Math.round(s / 60), "minute");
  if (s < 86400) return rtf.format(-Math.round(s / 3600), "hour");
  return rtf.format(-Math.round(s / 86400), "day");
}
const shortDay = (d) => new Date(+d.slice(0, 4), +d.slice(5, 7) - 1, +d.slice(8, 10)).toLocaleDateString(LOC, { day: "2-digit", month: "2-digit" });

const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const agentColor = (a) => css("--a-" + a) || css("--a-unknown");
const agentName = (a) => t("agent." + a);
const projectName = (p) => (p && p.startsWith("~") ? t("proj." + p) : p);
const capitalize = (s) => s.charAt(0).toUpperCase() + s.slice(1);

// "2026-11-09T14" -> epoch (local time)
const hourTs = (h) => new Date(+h.slice(0, 4), +h.slice(5, 7) - 1, +h.slice(8, 10), +(h.slice(11, 13) || 0)).getTime() / 1000;
const dayOf = (h) => h.slice(0, 10);

// ---------------------------------------------------------------------------
// period and filters
// ---------------------------------------------------------------------------
function interval() {
  const now = Date.now() / 1000;
  const today0 = new Date(); today0.setHours(0, 0, 0, 0);
  switch (S.period) {
    case "today": return [today0.getTime() / 1000, now];
    case "24h": return [now - 86400, now];
    case "7d": return [today0.getTime() / 1000 - 6 * 86400, now];
    case "30d": return [today0.getTime() / 1000 - 29 * 86400, now];
    default: return [0, now];
  }
}
const periodName = () => t("period.name." + S.period);

function inPeriodHour(h) {
  const [start, end] = interval();
  const tt = hourTs(h);
  return tt + 3599 >= start && tt <= end;
}
function inPeriodDay(d) {
  const [start] = interval();
  return hourTs(d + "T00") + 86399 >= start;
}
const agentOn = (a) => !S.hiddenAgents.has(a);

function filtered() {
  const d = S.data;
  return {
    usage: d.usage.filter((r) => inPeriodHour(r.hour) && agentOn(r.agent)),
    rtk: d.rtk.hourly.filter((r) => inPeriodHour(r.hour) && agentOn(r.agent)),
    hr: d.headroom.hourly.filter((r) => inPeriodHour(r.hour) && agentOn(r.agent)),
    sav: (d.savings?.hourly || []).filter((r) => inPeriodHour(r.hour) && agentOn(r.agent)),
    proj: d.project_usage.filter((r) => inPeriodDay(r.day) && agentOn(r.agent)),
    rtkCmd: d.rtk.commands.filter((r) => inPeriodDay(r.day)),
    sessions: d.sessions.filter((s) => s.end >= interval()[0] && agentOn(s.agent)),
    ollama: d.ollama.hourly.filter((r) => inPeriodHour(r.hour)),
  };
}

const newTokens = (r) => (r.input || 0) + (r.cache_write || 0) + (r.output || 0);

function sum(list, keyFn, fields) {
  const m = new Map();
  for (const r of list) {
    const k = keyFn(r);
    let o = m.get(k);
    if (!o) { o = {}; m.set(k, o); }
    for (const [name, fn] of Object.entries(fields)) o[name] = (o[name] || 0) + (typeof fn === "function" ? fn(r) : (r[fn] || 0));
  }
  return m;
}

function daysOfPeriod(minData) {
  let [start, end] = interval();
  if (S.period === "all" && minData) start = hourTs(minData + "T00");
  const out = [];
  const d = new Date(start * 1000); d.setHours(0, 0, 0, 0);
  while (d.getTime() / 1000 <= end) {
    out.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`);
    d.setDate(d.getDate() + 1);
  }
  return out;
}

// ---------------------------------------------------------------------------
// charts (Chart.js)
// ---------------------------------------------------------------------------
function baseOptions(extra = {}, axisFmt = fmt) {
  const grid = css("--grid"), text = css("--text-2");
  return {
    responsive: true, maintainAspectRatio: false, animation: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: { position: "bottom", labels: { color: text, boxWidth: 10, boxHeight: 10, usePointStyle: true, pointStyle: "rectRounded", padding: 14 } },
      tooltip: {
        backgroundColor: css("--surface"), titleColor: css("--text"), bodyColor: css("--text-2"),
        borderColor: css("--border"), borderWidth: 1, padding: 10, boxPadding: 4,
        callbacks: { label: (c) => ` ${c.dataset.label}: ${axisFmt(c.parsed.y ?? c.parsed.x)}` },
      },
    },
    scales: {
      x: { grid: { display: false }, ticks: { color: text, maxRotation: 0, autoSkipPadding: 12 }, border: { color: grid } },
      y: { grid: { color: grid }, ticks: { color: text, callback: (v) => axisFmt(v) }, border: { display: false }, beginAtZero: true },
    },
    ...extra,
  };
}
const stacked = (axisFmt = fmt) => {
  const b = baseOptions({}, axisFmt);
  return baseOptions({ scales: { x: { ...b.scales.x, stacked: true }, y: { ...b.scales.y, stacked: true } } }, axisFmt);
};
// value of the record in the chosen unit
const fmtU = () => (inUSD() ? fmtUSD : fmt);
function draw(id, config) {
  const el = document.getElementById(id);
  if (!el) return;
  if (typeof Chart === "undefined") {
    el.parentElement.innerHTML = `<div class="empty">${esc(t("no.charts"))}</div>`;
    return;
  }
  S.charts[id]?.destroy();
  S.charts[id] = new Chart(el, config);
}
const barDS = (label, data, color, stack) => ({
  label, data, backgroundColor: color, borderColor: css("--surface"), borderWidth: { top: 2 }, borderSkipped: "bottom",
  borderRadius: 4, stack, maxBarThickness: 36,
});

// ---------------------------------------------------------------------------
// HTML components
// ---------------------------------------------------------------------------
function kpi(label, value, detail = "", title = "") {
  return `<div class="kpi" title="${esc(title)}"><div class="label">${esc(label)}</div><div class="value">${value}</div><div class="detail">${detail}</div></div>`;
}
const empty = () => `<div class="empty">${esc(t("empty"))}</div>`;
function bars(items, fmtValue = fmt) {
  if (!items.length) return empty();
  const max = Math.max(...items.map((i) => i.value), 1);
  return `<div class="bars">${items.map((i) => `
    <div class="bar-row" title="${esc(i.title || i.name)}">
      <div class="bar-name"><span class="dot" style="background:${i.color}"></span>${esc(i.name)}</div>
      <div class="bar-track"><div class="bar-fill" style="width:${(100 * i.value) / max}%;background:${i.color}"></div></div>
      <div class="bar-value">${fmtValue(i.value)}${i.extra ? ` <span class="muted">${i.extra}</span>` : ""}</div>
    </div>`).join("")}</div>`;
}
// sortable table: cols = [{t:"i18n key", k: fn(row)->value, f: fn(value,row)->html, left:bool, hint:"i18n key"}]
function table(id, cols, rows, order = 1) {
  const el = document.getElementById(id);
  if (!el) return;
  if (!rows.length) { el.innerHTML = `<tr><td class="empty">${esc(t("empty"))}</td></tr>`; return; }
  let col = el.dataset.col != null ? +el.dataset.col : order, dir = el.dataset.dir || "desc";
  if (col >= cols.length) col = order;
  const render = () => {
    const sorted = [...rows].sort((a, b) => {
      const va = cols[col].k(a), vb = cols[col].k(b);
      const r = typeof va === "string" ? va.localeCompare(vb) : (va ?? -Infinity) - (vb ?? -Infinity);
      return dir === "desc" ? -r : r;
    });
    el.innerHTML = `<thead><tr>${cols.map((c, i) => `<th data-i="${i}" class="${c.left ? "left" : ""}" title="${esc(c.hint ? t(c.hint) : t("sort"))}">${esc(t(c.t))}${i === col ? (dir === "desc" ? " ↓" : " ↑") : ""}</th>`).join("")}</tr></thead>
      <tbody>${sorted.map((r) => `<tr>${cols.map((c) => `<td class="${c.left ? "left" : ""} ${c.cls || ""}">${c.f ? c.f(c.k(r), r) : esc(c.k(r))}</td>`).join("")}</tr>`).join("")}</tbody>`;
    el.querySelectorAll("th").forEach((th) => th.onclick = () => {
      const i = +th.dataset.i;
      if (i === col) dir = dir === "desc" ? "asc" : "desc"; else { col = i; dir = "desc"; }
      el.dataset.col = col; el.dataset.dir = dir;
      render();
    });
  };
  render();
}
const agentDot = (a) => `<span class="dot" style="background:${agentColor(a)}"></span>${esc(agentName(a))}`;

// ---------------------------------------------------------------------------
// overview
// ---------------------------------------------------------------------------
function renderOverview(F) {
  const usd = inUSD(), fu = fmtU();
  const tot = F.usage.reduce((o, r) => {
    o.new += newTokens(r); o.cr += r.cache_read || 0; o.msgs += r.msgs || 0; o.usd += r.usd || 0;
    o.input += (r.input || 0) + (r.cache_read || 0) + (r.cache_write || 0); o.unpriced += r.unpriced || 0;
    return o;
  }, { new: 0, cr: 0, msgs: 0, usd: 0, input: 0, unpriced: 0 });
  const cachePct = tot.input ? (100 * tot.cr) / tot.input : null;
  const savL = savingsRows(F);
  const savTot = savL.reduce((o, r) => { o.saved += r.saved; o.est += r.est; o.usd += r.usd; return o; }, { saved: 0, est: 0, usd: 0 });

  document.getElementById("kpis").innerHTML = [
    kpi(t("kpi.new"), fmt(tot.new), esc(t("kpi.new.det", { n: fmt(tot.msgs), period: periodName() })), t("kpi.new.hint")),
    kpi(t("kpi.cache"), fmt(tot.cr), esc(t("kpi.cache.det", { pct: fmtPct(cachePct) })), t("kpi.cache.hint")),
    kpi(t("kpi.api"), fmtUSD(tot.usd), esc(tot.unpriced ? t("kpi.api.unpriced", { n: fmt(tot.unpriced) }) : t("kpi.api.table")), t("kpi.api.hint")),
    ...(savL.length ? [kpi(t("sav.kpi.tokens"), fmt(savTot.saved), esc(t("sav.kpi.byTools", { n: new Set(savL.map((r) => r.tool)).size })), t("kpi.rtk.hint")),
      kpi(t("kpi.savUsd"), fmtUSD(savTot.est), esc(t("sav.kpi.min", { min: fmtUSD(savTot.usd) })), t("kpi.savUsd.hint"))] : []),
  ].join("");

  document.getElementById("title-daily").textContent = t(usd ? "overview.daily.usd" : "overview.daily");
  document.getElementById("exp-daily").textContent = t(usd ? "overview.daily.usd.explain" : "overview.daily.explain");
  document.getElementById("exp-consumes").textContent = t(usd ? "overview.consumes.usd.explain" : "overview.consumes.explain");
  document.getElementById("exp-saves").textContent = t(usd ? "overview.saves.usd.explain" : "overview.saves.explain");

  const value = usd ? (r) => r.usd || 0 : newTokens;
  const ags = AGENT_ORDER.filter((a) => F.usage.some((r) => r.agent === a));
  const useHours = S.period === "today" || S.period === "24h";
  let labels, series;
  if (useHours) {
    const [start, end] = interval();
    const hours = [];
    for (let tt = Math.floor(start / 3600) * 3600; tt <= end; tt += 3600) {
      const d = new Date(tt * 1000);
      hours.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}T${String(d.getHours()).padStart(2, "0")}`);
    }
    const byHourAg = sum(F.usage, (r) => r.hour + "|" + r.agent, { v: value });
    labels = hours.map((h) => h.slice(11, 13) + "h");
    series = ags.map((a) => barDS(agentName(a), hours.map((h) => byHourAg.get(h + "|" + a)?.v || 0), agentColor(a), "s"));
    document.getElementById("sub-daily").textContent = t("overview.byHour");
  } else {
    const days = daysOfPeriod(F.usage.length ? F.usage.reduce((m, r) => (r.hour < m ? r.hour : m), "9999").slice(0, 10) : null);
    const byDayAg = sum(F.usage, (r) => dayOf(r.hour) + "|" + r.agent, { v: value });
    labels = days.map(shortDay);
    series = ags.map((a) => barDS(agentName(a), days.map((d) => byDayAg.get(d + "|" + a)?.v || 0), agentColor(a), "s"));
    document.getElementById("sub-daily").textContent = t("overview.byDay");
  }
  draw("g-daily", { type: "bar", data: { labels, datasets: series }, options: stacked(fu) });

  const byAg = sum(F.usage, (r) => r.agent, { v: value, msgs: "msgs" });
  const totN = [...byAg.values()].reduce((s, o) => s + o.v, 0) || 1;
  document.getElementById("share").innerHTML = bars(
    AGENT_ORDER.filter((a) => byAg.has(a)).map((a) => ({ name: agentName(a), value: byAg.get(a).v, color: agentColor(a), extra: fmtPct((100 * byAg.get(a).v) / totN), title: t("calls", { n: fmt(byAg.get(a).msgs) }) })),
    fu,
  );

  const savAg = sum(savL, (r) => r.agent + "|" + r.tool, { v: usd ? "est" : "saved" });
  const items = [];
  for (const a of AGENT_ORDER) {
    const parts = [...savAg.entries()].filter(([k]) => k.startsWith(a + "|")).map(([k, o]) => [k.split("|")[1], o.v]).filter(([, v]) => v > 0);
    const total = parts.reduce((s2, [, v]) => s2 + v, 0);
    if (total > 0) items.push({ name: agentName(a), value: total, color: agentColor(a), extra: parts.map(([f, v]) => `${toolName(f)} ${fu(v)}`).join(" · ") });
  }
  document.getElementById("savings-by-agent").innerHTML = bars(items, fu);
}

// ---------------------------------------------------------------------------
// limits
// ---------------------------------------------------------------------------
// windows of up to 24 h (the 5 h ones) of every agent, grouped by reset, from the unified history
function allShortWindows() {
  const out = [];
  for (const x of S.data.limits.series || []) {
    if (!x.duration_h || x.duration_h > 24) continue;
    const L = x.points.map((p) => ({ ts: p[0], p5h: p[1], reset_5h: p[2], window_min: x.duration_h * 60 }));
    for (const j of groupWindows(L)) out.push({ ...j, agent: x.agent, id: x.id });
  }
  return out;
}
function codexWindows() {
  const s = (S.data.limits.series || []).find((x) => x.agent === "codex" && x.id === "five_hour");
  return groupWindows(s ? s.points.map((p) => ({ ts: p[0], p5h: p[1], reset_5h: p[2], window_min: s.duration_h * 60 }))
    : S.data.limits.codex || []);
}
function groupWindows(L) {
  const win = new Map();
  for (const l of L) {
    if (l.reset_5h == null || l.p5h == null) continue;
    let j = win.get(l.reset_5h);
    if (!j) { j = { reset: l.reset_5h, start: l.reset_5h - (l.window_min || 300) * 60, first: l, last: l, max: 0, samples: 0 }; win.set(l.reset_5h, j); }
    if (l.ts < j.first.ts) j.first = l;
    if (l.ts > j.last.ts) j.last = l;
    j.max = Math.max(j.max, l.p5h);
    j.samples++;
  }
  // merges windows whose reset differs only by seconds (Codex rounds it)
  const out = [];
  for (const j of [...win.values()].sort((a, b) => a.reset - b.reset)) {
    const prev = out[out.length - 1];
    if (prev && Math.abs(prev.reset - j.reset) < 120) {
      prev.max = Math.max(prev.max, j.max);
      if (j.last.ts > prev.last.ts) prev.last = j.last;
      if (j.first.ts < prev.first.ts) prev.first = j.first;
      prev.samples += j.samples;
    } else out.push({ ...j });
  }
  for (const j of out) {
    const hours = Math.max((j.last.ts - j.start) / 3600, 1 / 60);
    j.rate = j.max / hours;
    j.runsOutIn = j.rate > 0 ? 100 / j.rate : null;
  }
  return out;
}
function avgRate(js) {
  const v = js.filter((j) => j.max > 0 && j.rate).map((j) => j.rate);
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
}


function renderLimits() {
  const jsT = visibleWindows();
  document.getElementById("lim-windows").innerHTML = jsT.length
    ? byAgent(jsT).map((g) => `<div class="agent-group">${agentHead(g)}<div class="grid g3" style="margin:0">${g.windows.map(windowCard).join("")}</div>${g.agent === "claude" ? creditsBlock() : ""}</div>`).join("") + claudeNotice()
    : versionNotice() || claudeNotice() || `<div class="empty">${esc(t("summary.limits.no"))}</div>`;
  const now = Date.now() / 1000;

  // % used of every limit window of every agent over time (one color per agent, one line style per window)
  const [start, end] = interval();
  const SERIES = (S.data.limits.series || []).filter((x) => agentOn(x.agent) && x.duration_h);
  const dash = (x) => (x.duration_h <= 24 ? [] : x.id === "seven_day" ? [6, 3] : [2, 3]);
  const line = (x) => {
    const pts = x.points.filter((p) => p[0] >= start), out = [];
    for (let i = 0; i < pts.length; i++) {
      const p = pts[i], prev = pts[i - 1];
      // a new window (reset changed) or a long gap without readings: break the line
      if (prev && (Math.abs((p[2] || 0) - (prev[2] || 0)) > 120 || p[0] - prev[0] > 3 * 3600)) out.push({ x: (prev[0] + 1) * 1000, y: null });
      out.push({ x: p[0] * 1000, y: p[1] });
    }
    return out;
  };
  const datasets = SERIES.map((x) => ({ label: `${agentName(x.agent)} · ${windowName(x.id)}`, data: line(x) }))
    .map((d, i) => ({ ...d, borderColor: agentColor(SERIES[i].agent), backgroundColor: agentColor(SERIES[i].agent), borderDash: dash(SERIES[i]),
      borderWidth: 2, pointRadius: 0, spanGaps: false, tension: 0, hidden: S.limHidden?.has(d.label) }))
    .filter((d) => d.data.length);
  const firstTs = Math.min(...datasets.flatMap((d) => d.data.filter((p) => p.y != null).map((p) => p.x)));
  const box = document.getElementById("g-codex-limit").parentElement;
  document.getElementById("lim-history-empty").hidden = !!datasets.length;
  box.hidden = !datasets.length;
  if (datasets.length) {
    const b = baseOptions();
    draw("g-codex-limit", {
      type: "line",
      data: { datasets },
      options: baseOptions({
        parsing: false,
        plugins: {
          ...b.plugins,
          legend: { ...b.plugins.legend, onClick: (e, item, legend) => {
            // remembers which lines were turned off: the chart is redrawn on every collection
            S.limHidden ||= new Set();
            S.limHidden.has(item.text) ? S.limHidden.delete(item.text) : S.limHidden.add(item.text);
            Chart.defaults.plugins.legend.onClick.call(legend.chart.legend, e, item, legend);
          } },
          tooltip: { ...b.plugins.tooltip, callbacks: { title: (c) => fmtDate(c[0].parsed.x / 1000), label: (c) => ` ${c.dataset.label}: ${fmtPct(c.parsed.y)}` } },
        },
        scales: {
          x: { type: "linear", min: Math.max(start * 1000, firstTs), max: end * 1000, grid: { display: false },
               ticks: { color: css("--text-2"), callback: (v) => fmtDate(v / 1000, S.period !== "today" && S.period !== "24h"), maxTicksLimit: 8 } },
          y: { min: 0, max: 100, grid: { color: css("--grid") }, ticks: { color: css("--text-2"), callback: (v) => v + "%" }, border: { display: false } },
        },
      }),
    });
  }

  // recent short windows (5 h) of every agent, with the pace at which each one was spent. Windows
  // still at 0% are left out: while the limit is unused the endpoint moves its reset forward on
  // every reading, which would list one empty "window" per reading.
  const shortWins = allShortWindows().filter((j) => agentOn(j.agent) && j.reset >= start && j.max > 0).sort((a, b) => b.reset - a.reset).slice(0, 40);
  table("t-windows", [
    { t: "col.agent", k: (j) => agentName(j.agent), left: true },
    { t: "col.windowStart", k: (j) => j.start, f: (v) => fmtDate(v), left: true },
    { t: "col.used", k: (j) => j.max, f: (v, j) => `${fmtPct(v)}<span class="mini-bar" style="width:${Math.min(v, 100) * 0.6}px;background:${v >= 100 ? css("--critical") : agentColor(j.agent)}"></span>` },
    { t: "col.rate", k: (j) => j.rate, f: (v) => fmtPct(v, 1) },
    { t: "col.wouldRunOut", k: (j) => j.runsOutIn, f: (v) => (v ? fmtDur(v * 3600) : "–"), hint: "col.wouldRunOut.hint" },
    { t: "col.lastReading", k: (j) => j.last.ts, f: (v) => fmtDate(v) },
  ], shortWins, 1);

  // last 5 h, compared with the 5 h peak of the last 30 days
  const lim5 = now - 5 * 3600;
  const rec = S.data.usage.filter((r) => hourTs(r.hour) + 3600 >= lim5 && agentOn(r.agent));
  const p5 = sum(rec, (r) => r.agent, { v: newTokens, msgs: "msgs" });
  const ref = {};
  const byHour = sum(S.data.usage.filter((r) => hourTs(r.hour) >= now - 30 * 86400), (r) => r.agent + "|" + r.hour, { v: newTokens });
  for (const [k, o] of byHour) {
    const [a, h] = k.split("|");
    (ref[a] ||= []).push([hourTs(h), o.v]);
  }
  const peak = {};
  for (const [a, arr] of Object.entries(ref)) {
    arr.sort((x, y) => x[0] - y[0]);
    let best = 0, s = 0, i0 = 0;
    for (let i = 0; i < arr.length; i++) {
      s += arr[i][1];
      while (arr[i][0] - arr[i0][0] >= 5 * 3600) { s -= arr[i0][1]; i0++; }
      best = Math.max(best, s);
    }
    peak[a] = best;
  }
  document.getElementById("last-5h").innerHTML = bars(
    AGENT_ORDER.filter((a) => p5.has(a)).map((a) => ({
      name: agentName(a), value: p5.get(a).v, color: agentColor(a),
      extra: peak[a] ? esc(t("lim.peak", { pct: fmtPct((100 * p5.get(a).v) / peak[a]) })) : "",
      title: t("lim.peak.hint", { n: fmt(p5.get(a).msgs), peak: fmt(peak[a]) }),
    })),
  ) + `<p class="explain" style="margin-top:10px">${esc(t("lim.peak.explain"))}</p>`;
}

// ---------------------------------------------------------------------------
// agents and models
// ---------------------------------------------------------------------------
function renderModels(F) {
  const m = sum(F.usage, (r) => r.agent + "|" + r.model, {
    msgs: "msgs", input: "input", output: "output", cr: "cache_read", cw: "cache_write", reasoning: "reasoning", usd: "usd", unpriced: "unpriced",
  });
  const rows = [...m.entries()].map(([k, o]) => {
    const [agent, model] = k.split("|");
    const input = o.input + o.cr + o.cw;
    return { agent, model, ...o, new: o.input + o.cw + o.output, perMsg: o.msgs ? input / o.msgs : 0, cache: input ? (100 * o.cr) / input : null, outPerMsg: o.msgs ? o.output / o.msgs : 0 };
  });
  table("t-models", [
    { t: "col.agent", k: (r) => agentName(r.agent), f: (_, r) => agentDot(r.agent), left: true },
    { t: "col.model", k: (r) => r.model, left: true },
    { t: "col.calls", k: (r) => r.msgs, f: fmt },
    { t: "col.new", k: (r) => r.new, f: fmt },
    { t: "col.inputPerCall", k: (r) => r.perMsg, f: fmt, hint: "col.inputPerCall.hint" },
    { t: "col.cache", k: (r) => r.cache, f: (v) => fmtPct(v), hint: "col.cache.hint" },
    { t: "col.outputPerCall", k: (r) => r.outPerMsg, f: fmt },
    { t: "col.reasoning", k: (r) => r.reasoning, f: (v) => (v ? fmt(v) : "–"), hint: "col.reasoning.hint" },
    { t: "col.api", k: (r) => (r.unpriced && !r.usd ? -1 : r.usd), f: (v, r) => (r.unpriced && !r.usd ? `<span class="muted">${esc(t("unpriced"))}</span>` : fmtUSD(v)) },
  ], rows, 3);

  const [start, end] = interval();
  const step = S.period === "all" || S.period === "30d" ? 86400 : 3600;
  const ags = AGENT_ORDER.filter((a) => F.usage.some((r) => r.agent === a));
  const map = sum(F.usage, (r) => r.agent + "|" + Math.floor(hourTs(r.hour) / step) * step, { v: newTokens });
  const t0 = S.period === "all" && F.usage.length ? Math.min(...F.usage.map((r) => hourTs(r.hour))) : start;
  const ts = [];
  for (let x = Math.floor(t0 / step) * step; x <= end; x += step) ts.push(x);
  const b = baseOptions();
  draw("g-hour", {
    type: "line",
    data: { datasets: ags.map((a) => ({ label: agentName(a), data: ts.map((x) => ({ x: x * 1000, y: map.get(a + "|" + x)?.v || 0 })), borderColor: agentColor(a), backgroundColor: agentColor(a), borderWidth: 2, pointRadius: 0, tension: 0.2 })) },
    options: baseOptions({
      parsing: false,
      plugins: { ...b.plugins, tooltip: { ...b.plugins.tooltip, callbacks: { title: (c) => fmtDate(c[0].parsed.x / 1000, step === 3600), label: (c) => ` ${c.dataset.label}: ${fmt(c.parsed.y)}` } } },
      scales: { ...b.scales, x: { type: "linear", grid: { display: false }, ticks: { color: css("--text-2"), maxTicksLimit: 8, callback: (v) => fmtDate(v / 1000, step === 3600 && (S.period === "today" || S.period === "24h")) } } },
    }),
  });

  const comp = sum(F.usage, (r) => r.agent, { input: "input", cr: "cache_read", cw: "cache_write", out: "output" });
  const agsC = AGENT_ORDER.filter((a) => comp.has(a));
  const pct = (a, k) => { const o = comp.get(a); const tt = o.input + o.cr + o.cw + o.out; return tt ? (100 * o[k]) / tt : 0; };
  const parts = [["cr", "comp.cr", css("--s1")], ["cw", "comp.cw", css("--s2")], ["input", "comp.input", css("--s3")], ["out", "comp.out", css("--s4")]];
  draw("g-composition", {
    type: "bar",
    data: { labels: agsC.map(agentName), datasets: parts.map(([k, l, c]) => ({ ...barDS(t(l), agsC.map((a) => pct(a, k)), c, "c"), borderWidth: { right: 2 }, borderSkipped: "left" })) },
    options: baseOptions({
      indexAxis: "y",
      plugins: { ...b.plugins, tooltip: { ...b.plugins.tooltip, callbacks: { label: (c) => ` ${c.dataset.label}: ${fmtPct(c.parsed.x, 1)}` } } },
      scales: { x: { stacked: true, max: 100, grid: { color: css("--grid") }, ticks: { color: css("--text-2"), callback: (v) => v + "%" } }, y: { stacked: true, grid: { display: false }, ticks: { color: css("--text-2") } } },
    }),
  });

  const hd = sum(F.usage, (r) => r.agent + "|" + r.hour.slice(11, 13), { v: newTokens });
  const hs = [...Array(24).keys()].map((h) => String(h).padStart(2, "0"));
  draw("g-hour-of-day", {
    type: "bar",
    data: { labels: hs.map((h) => h + "h"), datasets: ags.map((a) => barDS(agentName(a), hs.map((h) => hd.get(a + "|" + h)?.v || 0), agentColor(a), "h")) },
    options: stacked(),
  });
}

// ---------------------------------------------------------------------------
// savings: tools detected on this machine and what each one saved
// ---------------------------------------------------------------------------
// Only the detected tools exist on screen. The ones that record their savings are added up;
// the ones that do not show what can be known (usage by the agents, projects).
const detectedTools = () => S.data.savings?.tools || [];
const hasTool = (id) => detectedTools().some((f) => f.id === id);
const toolName = (id) => detectedTools().find((f) => f.id === id)?.name || id;
const TOOL_COLORS = ["--s1", "--s3", "--s2", "--s4", "--a-opencode", "--a-unknown"];
const toolColor = (id) => css(TOOL_COLORS[Math.max(0, detectedTools().filter((f) => f.measured).findIndex((f) => f.id === id)) % TOOL_COLORS.length]);

// every measured saving in the same format: {hour, agent, tool, saved, usd, est}
function savingsRows(F) {
  const out = [];
  if (hasTool("rtk")) for (const r of F.rtk) out.push({ hour: r.hour, agent: r.agent, tool: "rtk", saved: r.saved || 0, usd: r.usd || 0, est: r.usd_est || 0 });
  if (hasTool("headroom")) for (const r of F.hr) out.push({ hour: r.hour, agent: r.agent, tool: "headroom", saved: r.saved || 0, usd: r.usd || 0, est: r.usd || 0 });
  for (const r of F.sav) out.push({ hour: r.hour, agent: r.agent, tool: r.tool, saved: r.saved || 0, usd: r.usd || 0, est: r.usd_est || 0 });
  return out;
}

function toolCard(f, byTool, F) {
  const v = byTool.get(f.id);
  const head = `<div class="head"><b><a class="link" href="${esc(f.url || "#")}" target="_blank" rel="noopener">${esc(f.name)}</a></b><span class="tag">${esc(t("cat." + (f.category || "other")))}</span></div>`;
  const ags = f.agents?.length ? `<div class="muted">${esc(t("sav.agents", { list: f.agents.map(agentName).join(", ") }))}</div>` : "";
  let body;
  if (f.measured && f.id === "kompact") {
    const k = f.live || {};
    body = `<div class="pct">${fmt(k.saved)}</div><div class="muted">${esc(t("sav.kompact", { n: fmt(k.requests) }))}</div>`;
  } else if (f.measured) {
    body = v && v.saved
      ? `<div class="pct">${fmt(v.saved)}</div><div class="muted">${esc(t("sav.tokensSaved", { period: periodName() }))} · ≈ ${fmtUSD(v.est)}</div>`
      : `<div class="pct">0</div><div class="muted">${esc(t("sav.noEvents", { period: periodName() }))}</div>`;
  } else {
    const ch = Object.values(f.calls || {}).reduce((a, b) => a + b, 0);
    const lines = [t("sav.doesNotMeasure")];
    const pr = f.projects || [];
    const queries = pr.reduce((s, p) => s + p.queries, 0);
    if (ch || queries) lines.push(t("sav.calls", { n: fmt(Math.max(ch, queries)) }));
    if (pr.length) lines.push(t("sav.projects", { p: fmt(pr.filter((p) => p.installed).length), u: fmt(pr.filter((p) => p.queries).length) }));
    body = `<div class="pct muted" style="font-size:15px;font-weight:500">${esc(t("sav.notMeasured"))}</div>${lines.map((l) => `<div class="muted">${esc(l)}</div>`).join("")}`;
  }
  return `<div class="window-card">${head}${body}${ags}${versionHtml(f)}</div>`;
}

// installed version and, when there is a newer one, the update command and a ready-made
// instruction to paste into the user's own agent (the panel never installs anything itself)
function versionHtml(f) {
  const v = f.version;
  if (!v || !v.installed) return "";
  if (!v.newer) return `<div class="muted">${esc(t("upd.current", { v: v.installed }))}</div>`;
  const cmds = (v.update || []).map((c) => `<div class="add-cmd"><code>${esc(c)}</code></div>`).join("");
  return `<div class="tool-update"><b>${esc(t("upd.available", { a: v.installed, b: v.latest }))}</b>${cmds}
    <button class="btn" data-agent-prompt="${esc(f.id)}">${esc(t("upd.copyPrompt"))}</button></div>`;
}

function agentPrompt(f) {
  const v = f.version;
  const steps = (v.update || []).map((c) => "  " + c).join(String.fromCharCode(10));
  return t("upd.prompt", { name: f.name, a: v.installed, b: v.latest, url: f.url || "", check: v.check || "", path: v.path || "?",
    steps: steps || t("upd.prompt.noCmd", { url: f.url || "" }) });
}

function bindAgentPrompts(root) {
  root.querySelectorAll("[data-agent-prompt]").forEach((b) => b.onclick = async () => {
    const f = detectedTools().find((x) => x.id === b.dataset.agentPrompt);
    try { await navigator.clipboard.writeText(agentPrompt(f)); b.textContent = t("donate.copied"); } catch { /* no clipboard */ }
  });
}

// tools not found on this machine: what each does and how to install it, gaps first
const ADD_CATS = ["command_output", "code_index", "proxy", "memory", "response_style"];
const pick = (v) => (v && typeof v === "object" ? v[LANG] || v.en || "" : v || "");
const withCode = (s) => esc(s).replace(/`([^`]+)`/g, "<code>$1</code>");  // `cmd` in notes
const missingCats = () => {
  const have = new Set(detectedTools().map((f) => f.category));
  return ADD_CATS.filter((c) => !have.has(c) && (S.data.savings?.available || []).some((f) => f.category === c));
};

function addCard(f) {
  const steps = f.install || [];
  const cmds = steps.map((c, i) => `<div class="add-cmd"><code>${esc(c)}</code><button class="btn" data-add-copy="${esc(f.id)}:${i}">${esc(t("donate.copy"))}</button></div>`).join("");
  const sup = (f.supports || []).filter((a) => !/^(others|any)\b/i.test(a)).map((a) => a.replace(/\s*\(.*\)$/, ""));
  const meta = [
    sup.length ? t("add.works", { list: sup.slice(0, 6).join(", ") + (sup.length > 6 ? " +" + (sup.length - 6) : "") }) : "",
    f.license ? t("add.license", { l: f.license }) : "",
    f.windows === false ? t("add.noWindows") : "",
    f.needs_external ? t("add.external") : "",
  ].filter(Boolean).join(" · ");
  return `<div class="window-card add-card">
    <div class="head"><b><a class="link" href="${esc(f.url || "#")}" target="_blank" rel="noopener">${esc(f.name)}</a></b><span class="tag">${esc(t(f.measured ? "add.measured" : "add.usage"))}</span></div>
    ${pick(f.about) ? `<p>${esc(pick(f.about))}</p>` : ""}
    ${meta ? `<p class="meta">${esc(meta)}</p>` : ""}
    ${cmds || `<p class="meta">${esc(t("add.seeRepo"))}</p>`}
    ${pick(f.install_note) ? `<p class="meta">${withCode(pick(f.install_note))}</p>` : ""}
    <p class="meta"><a class="link" href="${esc(f.url || "#")}" target="_blank" rel="noopener">${esc(t("add.readme"))}</a></p>
  </div>`;
}

function renderAddTools() {
  const av = S.data.savings?.available || [];
  const block = document.getElementById("block-sav-add");
  block.hidden = !av.length;
  if (!av.length) return;
  const gaps = missingCats();
  const group = (c) => {
    const list = av.filter((f) => f.category === c).sort((a, b) => (b.measured - a.measured) || ((b.stars || 0) - (a.stars || 0)));
    if (!list.length) return "";
    const gap = gaps.includes(c) ? `<span class="tag gap-tag">${esc(t("add.gap"))}</span>` : `<span class="tag">${esc(t("add.have"))}</span>`;
    return `<div class="add-group"><h3>${esc(capitalize(t("cat." + c)))} ${gap}</h3><p>${esc(t("add.cat." + c))}</p>
      <div class="grid g3" style="margin:0">${list.map(addCard).join("")}</div></div>`;
  };
  const cats = [...ADD_CATS, ...new Set(av.map((f) => f.category).filter((c) => !ADD_CATS.includes(c)))];
  const first = cats.filter((c) => gaps.includes(c)).map(group).join("");
  const rest = cats.filter((c) => !gaps.includes(c)).map(group).join("");
  const el = document.getElementById("sav-add");
  el.innerHTML = first + (rest ? (first ? `<details class="add-more"><summary>${esc(t("add.more"))}</summary>${rest}</details>` : rest) : "")
    + `<p class="meta" style="margin-top:14px">${esc(t("add.disclaimer"))}</p>`;
  el.querySelectorAll("[data-add-copy]").forEach((b) => b.onclick = async () => {
    const [id, i] = b.dataset.addCopy.split(":");
    try { await navigator.clipboard.writeText(av.find((f) => f.id === id).install[+i]); b.textContent = t("donate.copied"); } catch { /* no clipboard */ }
  });
}

function renderSavings(F) {
  const usd = inUSD(), fu = fmtU();
  const det = detectedTools();
  const L = savingsRows(F);
  const byTool = sum(L, (r) => r.tool, { saved: "saved", usd: "usd", est: "est" });
  const tot = L.reduce((o, r) => { o.saved += r.saved; o.est += r.est; o.usd += r.usd; return o; }, { saved: 0, est: 0, usd: 0 });
  const newTot = F.usage.reduce((s, r) => s + newTokens(r), 0);
  const measured = det.filter((f) => f.measured);

  document.getElementById("kpis-savings").innerHTML = det.length ? [
    kpi(t("sav.kpi.tools"), fmt(det.length), esc(t("sav.kpi.tools.det", { m: measured.length, s: det.length - measured.length }))),
    kpi(t("sav.kpi.tokens"), fmt(tot.saved), esc(periodName())),
    kpi(t("kpi.savUsd"), fmtUSD(tot.est), esc(t("sav.kpi.min", { min: fmtUSD(tot.usd) })), t("kpi.savUsd.hint")),
    kpi(t("kpi.savTotal"), fmtPct(newTot ? (100 * tot.saved) / (newTot + tot.saved) : null, 1), esc(t("kpi.savTotal.det")), t("kpi.savTotal.hint")),
  ].join("") : "";

  document.getElementById("sav-tools").innerHTML = det.length
    ? det.map((f) => toolCard(f, byTool, F)).join("")
    : `<div class="empty">${esc(t("sav.none"))}</div>`;
  bindAgentPrompts(document.getElementById("sav-tools"));

  renderAddTools();

  // unmeasured tools: which projects they are set up in and how often they were queried
  const projNotMeasured = det.filter((f) => !f.measured).flatMap((f) => (f.projects || []).map((p) => ({ ...p, id: f.id, name: f.name })));
  document.getElementById("block-sav-projects").hidden = !projNotMeasured.length;
  if (projNotMeasured.length) {
    table("t-sav-projects", [
      { t: "col.tool", k: (r) => r.name, left: true },
      { t: "col.project", k: (r) => projectName(r.project), f: (v, r) => `<span title="${esc(r.folder)}">${esc(v)}</span>`, left: true, cls: "truncate" },
      { t: "col.setUp", k: (r) => (r.installed ? 1 : 0), f: (v) => esc(t(v ? "sav.yes" : "sav.no")) },
      { t: "col.queries", k: (r) => r.queries, f: fmt },
    ], projNotMeasured, 3);
  }

  // savings per day, stacked by measured tool
  const dayBlock = document.getElementById("block-sav-day");
  dayBlock.hidden = !L.length;
  if (L.length) {
    const days = daysOfPeriod(L.reduce((m, r) => (r.hour < m ? r.hour : m), "9999").slice(0, 10));
    const map = sum(L, (r) => r.tool + "|" + dayOf(r.hour), { v: usd ? "est" : "saved" });
    const ids = [...new Set(L.map((r) => r.tool))];
    document.getElementById("title-sav-day").textContent = t(usd ? "sav.perDay.usd" : "sav.perDay.tokens");
    draw("g-savings", {
      type: "bar",
      data: { labels: days.map(shortDay), datasets: ids.map((id) => barDS(toolName(id), days.map((d) => map.get(id + "|" + d)?.v || 0), toolColor(id), "e")) },
      options: stacked(fu),
    });
  }

  // RTK detail: only if it is installed
  const withRtk = hasTool("rtk");
  for (const id of ["block-rtk-cmd", "block-rtk-hook", "block-rtk-failures"]) document.getElementById(id).hidden = !withRtk;
  if (withRtk) {
    const pc = sum(F.rtkCmd, (r) => r.command, { cmds: "cmds", input: "input", saved: "saved", zero: "zero", usd: "usd", est: "usd_est" });
    table("t-rtk-cmd", [
      { t: "col.command", k: (r) => r.name, left: true, cls: "truncate" },
      { t: "col.runs", k: (r) => r.cmds, f: fmt },
      { t: "col.saved", k: (r) => r.saved, f: fmt },
      { t: "col.usdEst", k: (r) => r.est, f: fmtUSD, hint: "col.usdEst.hint" },
      { t: "col.reduction", k: (r) => (r.input ? (100 * r.saved) / r.input : null), f: (v) => `${fmtPct(v)}<span class="mini-bar" style="width:${Math.max(0, Math.min(v || 0, 100)) * 0.5}px"></span>` },
      { t: "col.noGain", k: (r) => (r.cmds ? (100 * r.zero) / r.cmds : 0), f: (v, r) => `${fmtPct(v)} <span class="muted">(${fmt(r.zero)})</span>` },
    ], [...pc.entries()].map(([name, o]) => ({ name, ...o })).sort((a, b) => b.saved - a.saved).slice(0, 60), 2);

    const dec = S.data.rtk.hook_decisions || {};
    const decColors = { defer: css("--s1"), ask: css("--s2"), allow: css("--s3"), deny: css("--critical") };
    const at = S.data.rtk.attribution || {};
    const totAt = Object.values(at).reduce((a, b) => a + b, 0) || 1;
    document.getElementById("rtk-hook").innerHTML = bars(Object.entries(dec).sort((a, b) => b[1] - a[1]).map(([k, v]) => ({ name: t("dec." + k), value: v, color: decColors[k] || css("--a-unknown") })))
      + `<p class="explain" style="margin-top:12px">${esc(t("sav.attrib", { a: fmtPct((100 * (at.command || 0)) / totAt), b: fmtPct((100 * (at.activity || 0)) / totAt), c: fmtPct((100 * (at.none || 0)) / totAt) }))}</p>`;
    const fail = S.data.rtk.failures || [];
    document.getElementById("rtk-failures").innerHTML = bars(fail.slice(0, 8).map(([k, v]) => ({ name: k, value: v, color: css("--serious") })))
      + `<p class="explain" style="margin-top:12px">${esc(t("sav.failures.total", { n: fmt(S.data.rtk.failures_total) }))}</p>`;
  }

  // Headroom detail: only if it is installed
  const withHr = hasTool("headroom");
  document.getElementById("block-headroom").hidden = !withHr;
  if (withHr) {
    const hm = sum(F.hr, (r) => r.agent + "|" + r.model, { reqs: "reqs", saved: "saved", before: "before", measured: "saved_measured", usd: "usd" });
    table("t-headroom", [
      { t: "col.client", k: (r) => agentName(r.agent), f: (_, r) => agentDot(r.agent), left: true },
      { t: "col.model", k: (r) => r.model, left: true },
      { t: "col.reqs", k: (r) => r.reqs, f: fmt },
      { t: "col.saved", k: (r) => r.saved, f: fmt },
      { t: "col.reduction", k: (r) => (r.before ? (100 * r.measured) / r.before : null), f: (v) => fmtPct(v, 1), hint: "col.reduction.hint" },
      { t: "col.usdSaved", k: (r) => r.usd, f: fmtUSD },
    ], [...hm.entries()].map(([k, o]) => { const [agent, model] = k.split("|"); return { agent, model, ...o }; }), 3);
  }
}

// ---------------------------------------------------------------------------
// projects and sessions
// ---------------------------------------------------------------------------
function renderProjects(F) {
  const pm = sum(F.proj, (r) => r.project, { tokens: "tokens", msgs: "msgs", usd: "usd" });
  const agsByProj = {};
  for (const r of F.proj) { const o = (agsByProj[r.project] ||= {}); o[r.agent] = (o[r.agent] || 0) + r.tokens; }
  const rows = [...pm.entries()].map(([project, o]) => ({ project, ...o, ags: agsByProj[project] || {} }));
  const totP = rows.reduce((s, r) => s + r.tokens, 0) || 1;
  table("t-projects", [
    { t: "col.project", k: (r) => projectName(r.project), left: true, cls: "truncate" },
    { t: "col.agents", k: (r) => Object.keys(r.ags).length, f: (_, r) => Object.entries(r.ags).sort((a, b) => b[1] - a[1]).map(([a]) => `<span class="dot" title="${esc(agentName(a))}" style="background:${agentColor(a)}"></span>`).join(""), left: true },
    { t: "col.calls", k: (r) => r.msgs, f: fmt },
    { t: "col.tokensCache", k: (r) => r.tokens, f: fmt },
    { t: "col.share", k: (r) => (100 * r.tokens) / totP, f: (v) => `${fmtPct(v, 1)}<span class="mini-bar" style="width:${v * 0.8}px"></span>` },
    { t: "col.api", k: (r) => r.usd, f: fmtUSD },
  ], rows.sort((a, b) => b.tokens - a.tokens).slice(0, 50), 3);

  table("t-sessions", [
    { t: "col.agent", k: (s) => agentName(s.agent), f: (_, s) => agentDot(s.agent), left: true },
    { t: "col.project", k: (s) => projectName(s.project), left: true, cls: "truncate" },
    { t: "col.model", k: (s) => s.model, left: true },
    { t: "col.start", k: (s) => s.start, f: (v) => fmtDate(v) },
    { t: "col.duration", k: (s) => s.end - s.start, f: (v) => fmtDur(v) },
    { t: "col.calls", k: (s) => s.msgs, f: fmt },
    { t: "col.avgCtx", k: (s) => (s.msgs ? (s.input + s.cache_read + s.cache_write) / s.msgs : 0), f: fmt, hint: "col.avgCtx.hint" },
    { t: "col.tokens", k: (s) => s.tokens, f: fmt },
    { t: "col.api", k: (s) => s.usd, f: fmtUSD },
  ], F.sessions.slice().sort((a, b) => b.tokens - a.tokens).slice(0, 40), 7);
}

// ---------------------------------------------------------------------------
// tools, Graphify and Ollama
// ---------------------------------------------------------------------------
function renderTools(F) {
  const tools = S.data.tools || {};
  const sh = S.data.shell_commands || {};
  document.getElementById("tools-grid").innerHTML = ["claude", "codex", "opencode"].filter(agentOn).map((a) => {
    const items = Object.entries(tools[a] || {}).slice(0, 12).map(([n, v]) => ({ name: n.replace(/^mcp__/, "mcp:"), value: v, color: agentColor(a), title: n }));
    const cmds = Object.entries(sh[a] || {}).slice(0, 8).map(([n, v]) => ({ name: n, value: v, color: agentColor(a) }));
    return `<div class="card"><div class="card-head"><h2>${esc(t("tools.title", { agent: agentName(a) }))}</h2></div>
      <p class="explain">${esc(t("tools.explain"))}</p>${bars(items)}
      <h2 style="margin-top:18px">${esc(t("tools.shell"))}</h2><p class="explain">${esc(t("tools.shell.explain"))}</p>${bars(cmds)}</div>`;
  }).join("");

  const ol = S.data.ollama || {};
  const req = F.ollama.reduce((o, r) => { o.reqs += r.reqs; o.sec += r.seconds; o.errors += r.errors || 0; return o; }, { reqs: 0, sec: 0, errors: 0 });
  const viaOC = F.usage.filter((r) => r.model.startsWith("ollama/")).reduce((s, r) => s + newTokens(r), 0);
  const loaded = ol.loaded || [];
  document.getElementById("ollama").innerHTML = `
    <p class="explain" style="margin-top:0">${esc(t("ol.explain"))}</p>
    <div class="kpis">${kpi(t("ol.reqs"), fmt(req.reqs), esc(periodName()))}${kpi(t("ol.time"), fmtDur(req.sec), req.errors ? esc(t("ol.errors", { n: req.errors })) : "")}${kpi(t("ol.viaOC"), fmt(viaOC), "ollama/*")}${kpi(t("ol.installed"), fmt((ol.models || []).length), esc(loaded.length ? t("ol.loaded", { m: loaded.join(", ") }) : t("ol.none")))}</div>
    ${(ol.models || []).length ? `<table><thead><tr><th class="left">${esc(t("col.model"))}</th><th>${esc(t("col.size"))}</th></tr></thead><tbody>${ol.models.map((m) => `<tr><td class="left truncate" title="${esc(m.name)}">${esc(m.name)}</td><td>${esc(m.size)}</td></tr>`).join("")}</tbody></table>` : ""}`;
}

// ---------------------------------------------------------------------------
// what to optimize
// ---------------------------------------------------------------------------
function renderTips(F) {
  const d = S.data, tips = [];
  const add = (level, title, text, action) => tips.push({ level, title, text, action });
  const byAg = sum(F.usage, (r) => r.agent, { new: newTokens, msgs: "msgs", input: "input", cr: "cache_read", cw: "cache_write", out: "output", usd: "usd" });
  const rtkAg = sum(F.rtk, (r) => r.agent, { cmds: "cmds", saved: "saved" });
  const totNew = [...byAg.values()].reduce((s, o) => s + o.new, 0) || 1;
  const P = periodName();

  // Codex and RTK
  const cx = byAg.get("codex");
  if (cx && cx.msgs > 20 && hasTool("rtk")) {
    const sh = d.shell_commands?.codex || {};
    const ps = Object.entries(sh).filter(([k]) => /^(get-|set-|select-|\$)/.test(k)).reduce((s, [, v]) => s + v, 0);
    const totSh = Object.values(sh).reduce((a, b) => a + b, 0) || 1;
    const rc = rtkAg.get("codex")?.cmds || 0;
    if (rc < cx.msgs * 0.2) {
      add("high", t("d.codexRtk.t"), t("d.codexRtk.p", { Period: capitalize(P), n: fmt(cx.msgs), r: fmt(rc), pct: fmtPct((100 * ps) / totSh) }), t("d.codexRtk.a"));
    }
  }

  // Codex rate
  const rec = codexWindows().slice(-10).filter((j) => j.max > 0);
  const avg = avgRate(rec);
  const maxedOut = rec.filter((j) => j.max >= 100).length;
  if (avg && avg > 20) {
    add(avg > 40 ? "high" : "medium", t("d.rate.t", { pct: fmtPct(avg) }),
      t("d.rate.p", {
        dur: fmtDur((100 / avg) * 3600),
        overrun: maxedOut ? t("d.rate.overrun", { n: maxedOut, m: rec.length }) : "",
        plan: d.limits.codex.at(-1)?.plan || "",
        ctx: cx ? t("d.rate.ctx", { n: fmt((cx.input + cx.cr) / Math.max(cx.msgs, 1)) }) : "",
      }), t("d.rate.a"));
  }

  // Codex cache vs Claude
  const cachePct = (o) => (o ? (100 * o.cr) / Math.max(o.input + o.cr + o.cw, 1) : null);
  const cc = cachePct(byAg.get("claude")), cxc = cachePct(cx);
  if (cx && cxc != null && cc != null && cxc < cc - 10) add("medium", t("d.cache.t"), t("d.cache.p", { a: fmtPct(cxc), b: fmtPct(cc) }), t("d.cache.a"));

  // Opus vs Sonnet
  const mod = sum(F.usage.filter((r) => r.agent === "claude"), (r) => r.model, { v: newTokens, usd: "usd" });
  const opus = [...mod.entries()].filter(([k]) => k.includes("opus"));
  const opusV = opus.reduce((s, [, o]) => s + o.v, 0);
  const totCl = [...mod.values()].reduce((s, o) => s + o.v, 0);
  if (totCl && opusV / totCl > 0.85) {
    add("low", t("d.opus.t", { pct: fmtPct((100 * opusV) / totCl) }), t("d.opus.p", { usd: fmtUSD(opus.reduce((s, [, o]) => s + o.usd, 0)), period: P }), t("d.opus.a"));
  }

  // Claude average context
  const cl = byAg.get("claude");
  if (cl && cl.msgs) {
    const ctx = (cl.input + cl.cr + cl.cw) / cl.msgs;
    if (ctx > 120000) add("medium", t("d.ctx.t", { n: fmt(ctx) }), t("d.ctx.p"), t("d.ctx.a"));
  }

  // heavy sessions
  const heavy = F.sessions.filter((s) => s.tokens > 50e6).sort((a, b) => b.tokens - a.tokens);
  if (heavy.length) {
    add("low", heavy.length === 1 ? t("d.sess.t1") : t("d.sess.tn", { n: heavy.length }),
      t("d.sess.p", { proj: projectName(heavy[0].project), agent: agentName(heavy[0].agent), tok: fmt(heavy[0].tokens), n: fmt(heavy[0].msgs) }), t("d.sess.a"));
  }

  // wait tools
  const waits = Object.entries(d.tools?.claude || {}).filter(([k]) => /wait|sleep|poll|status/i.test(k)).sort((a, b) => b[1] - a[1]);
  const totWait = waits.reduce((s, [, v]) => s + v, 0);
  if (totWait > 500) {
    add("medium", t("d.waits.t", { n: fmt(totWait) }), t("d.waits.p", { list: waits.slice(0, 3).map(([k, v]) => `${k.replace(/^mcp__/, "")}: ${fmt(v)}`).join(", ") }), t("d.waits.a"));
  }

  // RTK failures
  const fail = d.rtk.failures || [];
  if (hasTool("rtk") && fail.length && fail[0][1] > 200) add("low", t("d.failure.t", { cmd: fail[0][0], n: fmt(fail[0][1]) }), t("d.failure.p"), t("d.failure.a", { cmd: fail[0][0] }));

  // commands with no gain
  const pc = sum(F.rtkCmd, (r) => r.command, { cmds: "cmds", zero: "zero" });
  const bad = [...pc.entries()].filter(([, o]) => o.cmds >= 50 && o.zero / o.cmds > 0.7).sort((a, b) => b[1].cmds - a[1].cmds);
  if (hasTool("rtk") && bad.length) {
    add("low", t("d.noGain.t"), bad.slice(0, 4).map(([k, o]) => t("d.noGain.item", { cmd: k, pct: fmtPct((100 * o.zero) / o.cmds), n: fmt(o.cmds) })).join(", ") + ".", t("d.noGain.a"));
  }

  // Headroom
  const hr = F.hr.reduce((o, r) => { o.saved += r.saved_measured || 0; o.before += r.before || 0; o.reqs += r.reqs; return o; }, { saved: 0, before: 0, reqs: 0 });
  const hrLast = Math.max(0, ...d.headroom.hourly.map((r) => hourTs(r.hour)));
  if (hasTool("headroom") && (!hr.reqs || (hr.before && hr.saved / hr.before < 0.02))) {
    add("medium", hr.reqs ? t("d.hr.t1", { pct: fmtPct((100 * hr.saved) / hr.before, 1) }) : t("d.hr.t0"),
      hrLast ? t("d.hr.p1", { when: timeAgo(hrLast) }) : t("d.hr.p0"), t("d.hr.a"));
  }

  // Graphify
  const g = d.graphify || {};
  const chG = Object.values(g.calls || {}).reduce((a, b) => a + b, 0);
  if (hasTool("graphify") && (g.projects || []).length <= 3 && chG < 20) add("low", t("d.gf.t"), t("d.gf.p", { n: (g.projects || []).length, c: fmt(chG) }), t("d.gf.a"));

  // installed tools with a newer version
  const outdated = detectedTools().filter((f) => f.version?.newer);
  if (outdated.length) {
    add("low", t("d.upd.t", { n: outdated.length }), outdated.map((f) => `${f.name} ${f.version.installed} → ${f.version.latest}`).join(", ") + ".", t("d.upd.a"));
  }

  // categories with no token-saving tool installed: point to the suggestions in the Savings tab
  for (const c of missingCats().filter((c) => c === "command_output" || c === "code_index")) {
    const names = (d.savings.available || []).filter((f) => f.category === c).sort((a, b) => (b.measured - a.measured) || ((b.stars || 0) - (a.stars || 0))).slice(0, 3).map((f) => f.name).join(", ");
    add("medium", t("d.add." + c + ".t"), t("d.add." + c + ".p", { list: names }), t("d.add.a"));
  }

  // share
  const sorted = [...byAg.entries()].sort((a, b) => b[1].new - a[1].new);
  if (sorted.length) {
    add("ok", t("d.share.t", { agent: agentName(sorted[0][0]), pct: fmtPct((100 * sorted[0][1].new) / totNew) }),
      t("d.share.p", { period: P, list: sorted.map(([a, o]) => `${agentName(a)} ${fmtPct((100 * o.new) / totNew, 1)}`).join(", ") }), "");
  }

  const order = { high: 0, medium: 1, low: 2, ok: 3 };
  S.autoTips = tips.sort((a, b) => order[a.level] - order[b.level]);
  document.getElementById("tip-list").innerHTML = tipsHtml(S.autoTips)
    || `<div class="empty">${esc(t("tips.nothing"))}</div>`;
}

// ---------------------------------------------------------------------------
// sources
// ---------------------------------------------------------------------------
function renderSources() {
  const f = S.data.sources;
  const rows = [
    ["Claude Code", "~/.claude/projects/**/*.jsonl", f.claude.ok, t("sources.claude", { n: fmt(f.claude.files) })],
    ["Codex", "~/.codex/sessions/**/rollout-*.jsonl", f.codex.ok, t("sources.codex", { n: fmt(f.codex.files), m: fmt(S.data.limits.codex.length) })],
    ["OpenCode", "~/.local/share/opencode/opencode.db", f.opencode.ok, f.opencode.error || t("sources.opencode", { n: fmt(f.opencode.messages) })],
    ["Ollama", "%LOCALAPPDATA%/Ollama/server*.log", f.ollama.ok, f.ollama.error || t("sources.ollama", { n: fmt(f.ollama.requests) })],
    ["RTK", "%LOCALAPPDATA%/rtk/history.db", f.rtk.ok, f.rtk.error || t("sources.rtk", { n: fmt(f.rtk.commands) })],
    ["Headroom", "~/.headroom/savings_events.jsonl", f.headroom.ok, f.headroom.error || t("sources.headroom", { n: fmt(f.headroom.events) })],
    ["Graphify", "<project>/graphify-out/graph.json", true, t("sources.graphify", { n: fmt(S.data.graphify.projects.length) })],
  ];
  document.getElementById("t-sources").innerHTML = `<thead><tr><th class="left">${esc(t("col.tool"))}</th><th class="left">${esc(t("col.file"))}</th><th class="left">${esc(t("col.status"))}</th><th class="left">${esc(t("col.read"))}</th></tr></thead><tbody>${rows.map(([n, p, ok, det]) => `<tr><td class="left">${n}</td><td class="left"><code>${esc(p)}</code></td><td class="left">${ok ? `<span class="status s-good">${esc(t("sources.ok"))}</span>` : `<span class="status s-critical">${esc(t("sources.no"))}</span>`}</td><td class="left">${esc(det)}</td></tr>`).join("")}</tbody>`;
  document.getElementById("sources-note").innerHTML = t("sources.note", { s: S.data.collect_duration_s });
}

// ---------------------------------------------------------------------------
// AI analysis
// ---------------------------------------------------------------------------
const LEVEL_ICON = { high: "!", medium: "!", low: "i", ok: "✓" };
function tipsHtml(list) {
  return list.map((x) => `
    <div class="tip"><div class="ic ${x.level}" title="${esc(t("level." + x.level))}" aria-label="${esc(t("level." + x.level))}">${LEVEL_ICON[x.level] || "i"}</div>
      <div><h3>${esc(x.title)}${x.sourceTag ? `<span class="source-tag">${esc(x.sourceTag)}</span>` : ""}</h3><p>${esc(x.text)}</p>${x.action ? `<div class="action">${esc(x.action)}</div>` : ""}</div></div>`).join("");
}

let aiFormBuilt = false;
const elAI = (id) => document.getElementById(id);

async function loadAI() {
  try {
    S.ai = await (await fetch("/api/ai", { cache: "no-store" })).json();
  } catch { return; }
  buildAIForm();
  renderAI();
  if (currentTab() === "summary") renderAll();
  if (S.ai.state.running) setTimeout(loadAI, 2000);
}

function buildAIForm() {
  if (!S.ai) return;
  const d = S.ai.available, cfg = S.ai.config || {};
  const sel = elAI("ai-provider");
  const def = cfg.type === "cli" && d.cli.some((c) => c.id === cfg.cli) ? "cli:" + cfg.cli
    : cfg.type === "api" ? "api" : cfg.type === "custom" ? "custom"
    : d.cli[0] ? "cli:" + d.cli[0].id : "api";
  const current = sel.value || def;
  sel.innerHTML = `<optgroup label="${esc(t("ai.cli"))}">${d.cli.length ? d.cli.map((c) => `<option value="cli:${c.id}">${esc(c.name)}</option>`).join("") : `<option disabled>${esc(t("ai.noCli"))}</option>`}</optgroup>
    <option value="api">${esc(t("ai.api"))}</option><option value="custom">${esc(t("ai.custom"))}</option>`;
  sel.value = current;
  elAI("ai-api").innerHTML = d.apis.map((a) => `<option value="${a.id}">${esc(a.name)}</option>`).join("");
  elAI("ai-days").querySelectorAll("option").forEach((o) => (o.textContent = t("ai.days.n", { n: o.value })));
  if (!aiFormBuilt) {
    elAI("ai-api").value = cfg.api || "openai";
    elAI("ai-url").value = cfg.url || (d.apis.find((a) => a.id === (cfg.api || "openai"))?.url || "");
    elAI("ai-model").value = cfg.model || "";
    elAI("ai-command").value = cfg.command || "";
    elAI("ai-days").value = cfg.days || "7";
    sel.onchange = () => { elAI("ai-model").value = ""; updateAIFields(); };
    elAI("ai-api").onchange = () => {
      const a = d.apis.find((x) => x.id === elAI("ai-api").value);
      if (a && a.url) elAI("ai-url").value = a.url;
      updateAIFields();
    };
    elAI("ai-analyze").onclick = analyzeAI;
    aiFormBuilt = true;
  } else {
    elAI("ai-api").value = elAI("ai-api").dataset.v || cfg.api || "openai";
  }
  updateAIFields();
}

function updateAIFields() {
  const v = elAI("ai-provider").value || "";
  const cli = v.startsWith("cli:") ? S.ai.available.cli.find((c) => "cli:" + c.id === v) : null;
  const api = v === "api", custom = v === "custom";
  elAI("ai-api").dataset.v = elAI("ai-api").value;
  elAI("ai-field-api").hidden = !api;
  elAI("ai-field-url").hidden = !api;
  elAI("ai-field-key").hidden = !api;
  elAI("ai-field-command").hidden = !custom;
  elAI("ai-field-model").hidden = custom;
  elAI("ai-command").placeholder = t("ai.command.ph");
  elAI("ai-key").placeholder = S.ai.config?.has_key ? t("ai.key.saved") : t("ai.key.ph");
  const required = cli?.model_required || api;
  elAI("ai-model").placeholder = required ? t("ai.model.required") : t("ai.model.ph");
  // model suggestions: the installed Ollama models, or the ones already used in the data
  const suggestions = cli?.id === "ollama"
    ? (S.data?.ollama?.models || []).map((m) => m.name)
    : [...new Set((S.data?.usage || []).map((r) => r.model))].filter((m) => m && m !== "?");
  elAI("ai-models").innerHTML = suggestions.map((m) => `<option value="${esc(m)}">`).join("");
  elAI("ai-notice").textContent = custom ? t("ai.command.hint") : cli && !cli.verified ? t("ai.unverified") : "";
}

async function analyzeAI() {
  if (S.config?.demo) return renderAI();  // demo mode runs no AI (the server refuses it too)
  const v = elAI("ai-provider").value || "";
  const body = { language: LANG, days: elAI("ai-days").value, model: elAI("ai-model").value.trim() };
  if (v.startsWith("cli:")) Object.assign(body, { type: "cli", cli: v.slice(4) });
  else if (v === "api") Object.assign(body, { type: "api", api: elAI("ai-api").value, url: elAI("ai-url").value.trim(), key: elAI("ai-key").value });
  else Object.assign(body, { type: "custom", command: elAI("ai-command").value.trim() });
  elAI("ai-analyze").disabled = true;
  try {
    const r = await post("/api/ai/analyze", body);
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      elAI("ai-status").innerHTML = `<div class="ai-status error">${esc(t("ai.error", { msg: j.error || r.status }))}</div>`;
    }
  } finally {
    elAI("ai-key").value = "";
    setTimeout(loadAI, 800);
  }
}

function scoreColor(n) {
  return n >= 80 ? css("--good") : n >= 60 ? css("--warning") : n >= 40 ? css("--serious") : css("--critical");
}

function renderAI() {
  if (!S.ai) return;
  const st = S.ai.state || {};
  elAI("ai-analyze").disabled = !!st.running;
  elAI("ai-status").innerHTML = st.running
    ? `<div class="ai-status">${esc(t("ai.running", { stage: "", s: Math.round(Date.now() / 1000 - (st.started || Date.now() / 1000)) }))}</div>`
    : st.error ? `<div class="ai-status error">${esc(t("ai.error", { msg: st.error }))}</div>`
    : S.config?.demo ? `<div class="ai-status">${esc(t("ai.demo"))}</div>` : "";
  const hist = S.ai.history || [];
  if (!hist.length) {
    elAI("ai-result").innerHTML = `<div class="empty">${esc(t("ai.none"))}</div>`;
    return;
  }
  const a = hist[0];
  const meta = t("ai.done", { date: fmtDate(a.date), by: a.by, model: a.model ? ` (${a.model})` : "", days: a.days, s: a.seconds });
  const score = "";  // the score comes from the panel's own calculation (above), not from the AI
  const prev = hist.slice(1, 8);
  elAI("ai-result").innerHTML = `
    <div class="ai-head" style="grid-template-columns:1fr">${score}<div><p class="ai-summary">${esc(a.summary)}</p><div class="muted">${esc(meta)}</div></div></div>
    ${tipsHtml(a.items || [])}
    ${prev.length ? `<details class="ai-previous"><summary>${esc(t("ai.previous"))} (${prev.length})</summary><ul>${prev.map((x) => `<li>${esc(fmtDate(x.date))} · ${esc(x.by)}${x.score != null ? ` · ${x.score}/100` : ""} · ${esc(x.summary || "")}</li>`).join("")}</ul></details>` : ""}`;
}

// ---------------------------------------------------------------------------
// prices
// ---------------------------------------------------------------------------
function renderPrices() {
  const p = S.data.prices || {};
  const f = p.sources || {};
  elAI("price-sources").innerHTML = `<div class="bars">${["manual", "litellm", "openrouter", "default"].filter((k) => f[k]).map((k) => `
    <div class="bar-row" style="grid-template-columns:minmax(200px,40%) 1fr">
      <div class="bar-name">${esc(t("prices.source." + k))}</div>
      <div class="muted">${esc(t("prices.models", { n: fmt(f[k].models) }))}${f[k].updated ? " · " + esc(t("prices.updated", { when: timeAgo(f[k].updated) })) : ""}</div>
    </div>`).join("")}</div>
    <p class="explain" style="margin-top:10px">${esc(p.unpriced?.length ? t("prices.unpriced", { list: p.unpriced.join(", ") }) : t("prices.all"))}</p>`;
  const rows = Object.entries(p.by_model || {}).map(([m, v]) => ({ model: m, source: v.source, ...(v.price || {}) }));
  table("t-prices", [
    { t: "col.model", k: (r) => r.model, left: true },
    { t: "col.source", k: (r) => (r.source ? t("prices.source." + r.source) : "–"), left: true },
    { t: "col.input", k: (r) => r.input, f: (v) => (v != null ? "$" + v.toLocaleString(LOC, { maximumFractionDigits: 3 }) : "–") },
    { t: "col.output", k: (r) => r.output, f: (v) => (v != null ? "$" + v.toLocaleString(LOC, { maximumFractionDigits: 3 }) : "–") },
    { t: "col.cacheRead", k: (r) => r.cache_read, f: (v) => (v != null ? "$" + v.toLocaleString(LOC, { maximumFractionDigits: 3 }) : "–") },
  ], rows, 0);
}

document.getElementById("btn-prices").onclick = async (ev) => {
  const b = ev.currentTarget;
  b.disabled = true;
  try {
    await post("/api/prices/refresh");
    const before = S.data?.generated_at || 0, t0 = Date.now();
    while (Date.now() - t0 < 90000) {
      await new Promise((r) => setTimeout(r, 1500));
      const j = await (await fetch("/api/data", { cache: "no-store" })).json();
      if (j.generated_at && j.generated_at > before) { S.data = j; renderAll(); break; }
    }
  } finally { b.disabled = false; }
};

// unit (tokens or US$)
document.querySelectorAll("#unit button").forEach((b) => {
  b.classList.toggle("active", b.dataset.u === S.unit);
  b.onclick = () => {
    S.unit = b.dataset.u;
    savePref("unit", S.unit);
    document.querySelectorAll("#unit button").forEach((x) => x.classList.toggle("active", x === b));
    renderAll();
  };
});

// ---------------------------------------------------------------------------
// limit windows (all agents)
// ---------------------------------------------------------------------------
function windowName(id) {
  // weekly per model: "weekly_scoped:Fable" -> "Weekly · Fable"
  if (id.startsWith("weekly_scoped:")) return `${t("win.seven_day")} · ${id.slice(14)}`;
  // extra Codex limits: "extra:Name:five_hour" -> "Name · 5 h window"
  if (id.startsWith("extra:")) { const [, name, win] = id.split(":"); return `${name} · ${windowName(win || "")}`; }
  const k = "win." + id;
  if (TXT[LANG]?.[k] || TXT.en[k]) return t(k);
  return id.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}
const visibleWindows = () => (S.data.limits.windows || []).filter((j) => agentOn(j.agent));
// an old server (before this version) does not send the list of windows
const oldServer = () => !("windows" in (S.data.limits || {}));
const versionNotice = () => (oldServer() ? `<p class="explain" style="color:var(--serious)">${esc(t("win.restart"))}</p>` : "");

function windowForecast(j) {
  if (j.projected_at_reset == null) return "";
  return j.runs_out_before_reset
    ? `<div class="prev bad">${esc(t("win.runsOut", { dur: fmtDur(j.runs_out_in_h * 3600) }))}</div>`
    : `<div class="prev muted">${esc(t("win.reaches", { pct: fmtPct(Math.min(j.projected_at_reset, 999)) }))}</div>`;
}

function windowCard(j) {
  const now = Date.now() / 1000;
  return `<div class="window-card">
    <div class="head"><b>${esc(windowName(j.id))}</b></div>
    <div class="pct">${fmtPct(j.pct)}</div>
    <div class="track" style="height:10px;background:var(--bar-track);border-radius:5px;overflow:hidden" role="meter" aria-valuenow="${j.pct}" aria-valuemin="0" aria-valuemax="100"><div style="height:100%;width:${Math.min(j.pct, 100)}%;background:${pctColor(j.pct)};border-radius:5px"></div></div>
    <div class="muted" style="margin-top:6px">${esc(j.reset ? t("win.resets", { dur: fmtDur(j.reset - now) }) : t("win.free"))}${j.rate_h ? " · " + esc(t("win.rate", { pct: fmtPct(j.rate_h, 1) })) : ""}${j.read_at ? " · " + esc(t("win.read", { when: timeAgo(j.read_at) })) : ""}</div>
    ${windowForecast(j)}
  </div>`;
}

function creditsBlock() {
  if (!agentOn("claude")) return "";
  const n = (v) => (v ?? 0).toLocaleString(LOC, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  let html = "";
  // Claude Code cloud session credits
  const cl = S.data.limits.claude_api?.cloud;
  if (cl && cl.limit_usd) {
    const used = Math.max(0, cl.limit_usd - (cl.remaining_usd ?? cl.limit_usd));
    const det = [t("cloud.left", { left: n(cl.remaining_usd), limit: n(cl.limit_usd) })];
    if (cl.reset) det.push(t("cloud.renews", { dur: fmtDur(cl.reset - Date.now() / 1000) }));
    if (cl.locked) det.push(t("cloud.locked"));
    html += miniMeter(t("cloud.title"), (100 * used) / cl.limit_usd, det.join(" · "));
  }
  const ex = S.data.limits.claude_api?.extra;
  if (!ex) return html;
  return html + extraBlock(ex, n);
}

function extraBlock(ex, n) {
  if (!ex.enabled) return "";
  if (ex.limit_usd) {
    const pct = ex.pct ?? (100 * (ex.used_usd || 0)) / ex.limit_usd;
    return miniMeter(t("cred.title"), pct, `${t("cred.usage", { used: n(ex.used_usd), limit: n(ex.limit_usd) })} · ${t("cred.left", { left: n(Math.max(0, ex.limit_usd - (ex.used_usd || 0))) })}`);
  }
  return `<div class="muted" style="margin-top:6px">${esc(t("cred.title"))}: ${esc(t("cred.noLimit", { used: n(ex.used_usd) }))}</div>`;
}

// groups the windows by agent, with the plan shown once in the header
function byAgent(js) {
  const g = new Map();
  for (const j of js) {
    if (!g.has(j.agent)) g.set(j.agent, { agent: j.agent, plan: j.plan, windows: [] });
    g.get(j.agent).windows.push(j);
  }
  return [...g.values()];
}
const agentHead = (g) => `<div class="agent-head"><span class="dot" style="background:${agentColor(g.agent)}"></span><b>${esc(agentName(g.agent))}</b>${g.plan ? `<span class="tag">${esc(t("win.plan", { p: g.plan }))}</span>` : ""}</div>`;

function claudeNotice() {
  const c = S.data.limits.claude_api;
  if (!c || c.ok || !agentOn("claude")) return "";
  const key = "lim.claude.error." + c.error;
  const msg = TXT[LANG]?.[key] || TXT.en[key] ? t(key) : t("lim.claude.error.other", { error: c.error || "?" });
  return `<p class="explain" style="margin:6px 0 0">${esc(msg)}</p>`;
}

function initLimitsSetting() {
  const cb = document.getElementById("set-claude-limits");
  if (!cb) return;
  cb.checked = S.config?.claude_limits !== false;
  cb.onchange = async () => {
    const r = await post("/api/config", { claude_limits: cb.checked });
    if (r.ok) { S.config = await r.json(); post("/api/refresh"); }
  };
}

// ---------------------------------------------------------------------------
// summary (first tab)
// ---------------------------------------------------------------------------
function daysInPeriod() {
  const [start, end] = interval();
  if (S.period !== "all") return (end - start) / 86400;
  const first = S.data.usage.reduce((m, r) => (r.hour < m ? r.hour : m), "9999");
  return first === "9999" ? 0 : (end - hourTs(first)) / 86400;
}

function pctColor(p) {
  return p >= 90 ? css("--critical") : p >= 70 ? css("--serious") : p >= 50 ? css("--warning") : css("--good");
}

function miniMeter(label, pct, detail) {
  return `<div class="mini-meter">
    <div class="meter-head"><span>${esc(label)}</span><b>${fmtPct(pct)}</b></div>
    <div class="track" role="meter" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100"><div class="fill" style="width:${Math.min(pct, 100)}%;background:${pctColor(pct)}"></div></div>
    ${detail ? `<div class="muted">${esc(detail)}</div>` : ""}
  </div>`;
}

function scoreRing(n) {
  if (n == null) return `<div class="score-ring" style="--score:0;--score-color:var(--bar-track)"><span>–</span></div>`;
  return `<div class="score-ring" style="--score:${n};--score-color:${scoreColor(n)}" role="meter" aria-valuenow="${n}" aria-valuemin="0" aria-valuemax="100" aria-label="${esc(t("summary.score"))}"><span>${n}</span></div>`;
}

function renderSummary(F) {
  const usd = inUSD(), fu = fmtU();

  // what the usage is worth: prorated subscriptions vs API value vs savings
  const apiUsd = F.usage.reduce((s, r) => s + (r.usd || 0), 0);
  const savUsd = savingsRows(F).reduce((s, r) => s + r.est, 0);
  const subs = (S.config?.subscriptions || []).filter((a) => a.monthly > 0 && (!a.agent || agentOn(a.agent)));
  const paid = subs.reduce((s, a) => s + a.monthly, 0) * daysInPeriod() / 30.44;
  const items = [];
  if (subs.length) items.push({ name: t("summary.value.paid"), value: paid, color: css("--a-unknown") });
  items.push({ name: t("summary.value.api"), value: apiUsd, color: css("--s1") });
  items.push({ name: t("summary.value.sav"), value: savUsd, color: css("--s4") });
  document.getElementById("summary-value").innerHTML = bars(items, fmtUSD)
    + `<p class="value-mult">${esc(subs.length && paid > 0 ? t("summary.value.mult", { period: periodName(), x: (apiUsd / paid).toLocaleString(LOC, { maximumFractionDigits: 1 }) }) : t("summary.value.noSubs"))}</p>`;

  // limits now: every window of every agent, with a forecast
  const js = visibleWindows();
  document.getElementById("summary-limits").innerHTML = (js.length
    ? byAgent(js).map((g) => agentHead(g) + g.windows.map((j) => miniMeter(windowName(j.id), j.pct,
        j.reset ? t("win.resets", { dur: fmtDur(j.reset - Date.now() / 1000) }) : t("win.free")) + windowForecast(j)).join("")
        + (g.agent === "claude" ? creditsBlock() : "")).join("")
    : `<div class="empty">${esc(t("summary.limits.no"))}</div>`) + claudeNotice() + versionNotice();

  // pie by agent
  const value = usd ? (r) => r.usd || 0 : newTokens;
  const byAg = sum(F.usage, (r) => r.agent, { v: value });
  const ags = AGENT_ORDER.filter((a) => byAg.has(a) && byAg.get(a).v > 0);
  const totAg = ags.reduce((s, a) => s + byAg.get(a).v, 0) || 1;
  draw("g-pie", {
    type: "doughnut",
    data: { labels: ags.map(agentName), datasets: [{ data: ags.map((a) => byAg.get(a).v), backgroundColor: ags.map(agentColor), borderColor: css("--surface"), borderWidth: 2 }] },
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

  // usage per day (or hour), stacked by agent
  const byHours = S.period === "today" || S.period === "24h";
  const key = byHours ? (r) => r.hour : (r) => dayOf(r.hour);
  const map = sum(F.usage, (r) => key(r) + "|" + r.agent, { v: value });
  const labels = byHours
    ? [...new Set(F.usage.map((r) => r.hour))].sort()
    : daysOfPeriod(F.usage.length ? F.usage.reduce((m, r) => (r.hour < m ? r.hour : m), "9999").slice(0, 10) : null);
  draw("g-summary-days", {
    type: "bar",
    data: {
      labels: labels.map((x) => (byHours ? x.slice(11, 13) + "h" : shortDay(x))),
      datasets: ags.map((a) => barDS(agentName(a), labels.map((x) => map.get(x + "|" + a)?.v || 0), agentColor(a), "r")),
    },
    options: stacked(fu),
  });

  // key points: a recent AI analysis first, then the automatic rules
  const order = { high: 0, medium: 1, low: 2, ok: 3 };
  const ai = (S.ai?.history || [])[0];
  const fromAI = ai && Date.now() / 1000 - ai.date < 8 * 86400 ? (ai.items || []).map((x) => ({ ...x, source: "ai" })) : [];
  const auto = (S.autoTips || []).map((x) => ({ ...x, source: "auto" }));
  const list = [...fromAI.filter((x) => x.level !== "ok"), ...auto.filter((x) => x.level !== "ok")]
    .sort((a, b) => order[a.level] - order[b.level]).slice(0, 5);
  document.getElementById("summary-insights").innerHTML = list.length
    ? tipsHtml(list.map((x) => ({ ...x, title: x.title, sourceTag: t(x.source === "ai" ? "source.ai" : "source.auto") })))
    : `<div class="empty">${esc(t("tips.nothing"))}</div>`;
}

// ---------------------------------------------------------------------------
// score (computed by the server for the chosen period)
// ---------------------------------------------------------------------------
async function loadScore() {
  const [start, end] = interval();
  const realStart = S.period === "all" ? end - 3650 * 86400 : start;
  try {
    const r = await fetch(`/api/score?start=${Math.floor(realStart)}&end=${Math.ceil(end)}`, { cache: "no-store" });
    if (r.status !== 200) return;
    S.score = await r.json();
  } catch { return; }
  renderScore();
}

function criterionValue(c, v) {
  return c.unit === "tokens" ? fmt(v) : fmtPct(v, v < 10 ? 1 : 0);
}

function criterionText(c, suffix) {
  const ex = c.extra || {};
  return t(`score.c.${c.id}.${suffix}`, {
    limit: ex.limit, models: (ex.models || []).join(", "), bypassed: fmt(ex.bypassed || 0),
    maxed_out: ex.maxed_out, windows: ex.windows,
  });
}

function renderScore() {
  const N = S.score;
  if (!N) return;
  const losses = N.components.filter((c) => c.weight - c.points >= 0.5).slice(0, 3);
  document.getElementById("summary-score").innerHTML = `<div class="score-big">${scoreRing(N.score)}
    <div class="gains">${losses.map((c) => `<div>${esc(t("summary.score.gain", { p: fmt(c.weight - c.points), criterion: criterionText(c, "t").toLowerCase() }))}</div>`).join("")}
      <a href="#tips" class="link">${esc(t("summary.score.view"))}</a></div></div>`;
  document.getElementById("score-detail").innerHTML = `<div class="score-big" style="margin-bottom:8px">${scoreRing(N.score)}<div></div></div>`
    + N.components.map((c) => {
      const frac = c.weight ? c.points / c.weight : 0;
      const color = frac >= 0.9 ? css("--good") : frac >= 0.5 ? css("--warning") : css("--critical");
      return `<div class="criterion">
        <div><h3>${esc(criterionText(c, "t"))}</h3><p>${esc(criterionText(c, "o"))}</p></div>
        <div class="numbers">
          <span>${esc(t("score.yours"))}: <b>${esc(criterionValue(c, c.value))}</b></span>
          <span>${esc(t("score.target"))}: <b>${esc(criterionValue(c, c.target))}</b> · ${esc(t("score.bad"))}: ${esc(criterionValue(c, c.bad))}</span>
          <div class="points-bar"><div style="width:${100 * frac}%;background:${color}"></div></div>
          <span><b>${esc(t("score.points", { p: fmt(c.points), max: fmt(c.weight) }))}</b></span>
        </div>
        <div>${frac < 0.99 ? `<div class="action">${esc(criterionText(c, "a"))}</div>` : ""}</div>
      </div>`;
    }).join("")
    + (N.excluded?.length ? `<p class="explain" style="margin-top:10px">${esc(t("score.excluded", { list: N.excluded.map((k) => t(`score.c.${k}.t`)).join(", ") }))}</p>` : "");
}

// ---------------------------------------------------------------------------
// subscriptions
// ---------------------------------------------------------------------------
async function loadConfig() {
  try { S.config = await (await fetch("/api/config", { cache: "no-store" })).json(); } catch { S.config = {}; }
  document.getElementById("demo-badge").hidden = !S.config?.demo;
  renderSubscriptions();
  initLimitsSetting();
  renderDonate();
  renderUpdate();
  renderAll();
}

function renderSubscriptions() {
  const el = document.getElementById("subscriptions");
  if (!el) return;
  const list = S.subsEdit || (S.subsEdit = (S.config?.subscriptions || []).map((a) => ({ ...a })));
  const options = (sel) => [...AGENT_ORDER.filter((a) => a !== "unknown"), ""].map((a) =>
    `<option value="${a}" ${a === sel ? "selected" : ""}>${esc(a ? agentName(a) : t("subs.other"))}</option>`).join("");
  el.innerHTML = list.map((a, i) => `<div class="sub-row" data-i="${i}">
      <label>${esc(t("subs.name"))}<input data-k="name" value="${esc(a.name)}" placeholder="Claude Max"></label>
      <label>${esc(t("subs.agent"))}<select data-k="agent">${options(a.agent)}</select></label>
      <label>${esc(t("subs.monthly"))}<input data-k="monthly" type="number" min="0" step="0.01" value="${a.monthly ?? ""}"></label>
      <button class="btn" data-remove="${i}">${esc(t("subs.remove"))}</button>
    </div>`).join("")
    + `<div class="sub-row"><button class="btn" id="sub-add">${esc(t("subs.add"))}</button><button class="btn primary" id="sub-save">${esc(t("subs.save"))}</button><span class="muted" id="sub-msg"></span></div>`;
  el.querySelectorAll(".sub-row[data-i] [data-k]").forEach((inp) => inp.oninput = inp.onchange = () => {
    const i = +inp.closest(".sub-row").dataset.i;
    list[i][inp.dataset.k] = inp.dataset.k === "monthly" ? parseFloat(inp.value) : inp.value;
  });
  el.querySelectorAll("[data-remove]").forEach((b) => b.onclick = () => { list.splice(+b.dataset.remove, 1); renderSubscriptions(); });
  document.getElementById("sub-add").onclick = () => { list.push({ name: "", agent: "claude", monthly: null }); renderSubscriptions(); };
  document.getElementById("sub-save").onclick = async () => {
    const r = await post("/api/config", { subscriptions: list.filter((a) => a.monthly >= 0 && a.monthly !== null && !isNaN(a.monthly)) });
    if (r.ok) {
      S.config = await r.json();
      S.subsEdit = null;
      renderSubscriptions();
      document.getElementById("sub-msg").textContent = t("subs.saved");
      renderAll();
    }
  };
}

// ---------------------------------------------------------------------------
// updates and donations (Settings)
// ---------------------------------------------------------------------------
const REPO_URL = "https://github.com/Baeta78/token-economy";
// Official donation addresses. Empty ones are hidden. Only the addresses in the official repository are ours.
const DONATE = {
  sponsors: "https://github.com/sponsors/Baeta78",
  lightning: "",
  monero: "",
};

async function loadUpdate(force) {
  const btn = document.getElementById("btn-update-check");
  if (btn) btn.disabled = true;
  try { S.update = await (await fetch("/api/update" + (force ? "?force=1" : ""), { cache: "no-store" })).json(); }
  catch (e) { S.update = { error: String(e) }; }
  if (btn) btn.disabled = false;
  renderUpdate();
}

function renderUpdate(msg) {
  const el = document.getElementById("update-box");
  if (!el) return;
  const u = S.update;
  if (!u) { el.innerHTML = `<p class="muted">${esc(t("header.loading"))}</p>`; return; }
  let html = `<p><strong>${esc(t("update.current", { v: u.current }))}</strong> · `;
  if (u.demo) html += esc(t("update.demo"));
  else if (u.error) html += esc(t("update.error", { e: u.error }));
  else if (!u.latest) html += esc(t("update.none"));
  else if (!u.newer) html += esc(t("update.uptodate"));
  else html += `<strong>${esc(t("update.available", { v: u.latest }))}</strong>`;
  html += "</p>";
  if (u.newer && !u.demo) {
    if (u.notes) html += `<details><summary>${esc(t("update.notes"))}</summary><pre class="update-notes">${esc(u.notes)}</pre></details>`;
    html += `<p class="explain">${esc(t(u.method === "git" ? "update.via.git" : "update.via.zip"))}</p>`
      + `<button class="btn primary" id="btn-update-install">${esc(t("update.install"))}</button> `
      + (u.url ? `<a class="btn" href="${esc(u.url)}" target="_blank" rel="noopener">GitHub</a>` : "");
  }
  if (msg) html += `<p class="update-msg">${esc(msg)}</p>`;
  el.innerHTML = html;
  const b = document.getElementById("btn-update-install");
  if (b) b.onclick = async () => {
    b.disabled = true;
    b.textContent = t("update.installing");
    let r, body;
    try { r = await post("/api/update/apply"); body = await r.json(); } catch (e) { body = { error: String(e) }; }
    if (r?.ok && body.updated) { S.update = { ...S.update, newer: false }; renderUpdate(t("update.done", { v: body.version })); }
    else renderUpdate(body.error === "local_changes" ? t("update.local_changes") : t("update.failed", { e: body.error || "?" }));
  };
}

let qrLib = null;
function loadQR() {
  return qrLib || (qrLib = new Promise((ok, fail) => {
    const s = document.createElement("script");
    s.src = "https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js";
    s.onload = ok; s.onerror = fail;
    document.head.appendChild(s);
  }));
}

function renderDonate() {
  const el = document.getElementById("donate-box");
  if (!el) return;
  const coins = [["lightning", "lightning:"], ["monero", "monero:"]].filter(([k]) => DONATE[k]);
  el.innerHTML = `<div class="donate-links">`
    + (DONATE.sponsors ? `<a class="btn primary" href="${esc(DONATE.sponsors)}" target="_blank" rel="noopener">💛 ${esc(t("donate.sponsors"))}</a> ` : "")
    + `<a class="btn" href="${REPO_URL}" target="_blank" rel="noopener">⭐ ${esc(t("donate.star"))}</a></div>`
    + coins.map(([k]) => `<div class="donate-coin">
        <div class="donate-qr" id="qr-${k}"></div>
        <div><div class="donate-label">${esc(t("donate." + k))}</div>
          <code class="donate-addr">${esc(DONATE[k])}</code>
          <button class="btn" data-copy="${k}">${esc(t("donate.copy"))}</button></div>
      </div>`).join("");
  el.querySelectorAll("[data-copy]").forEach((b) => b.onclick = async () => {
    try { await navigator.clipboard.writeText(DONATE[b.dataset.copy]); b.textContent = t("donate.copied"); } catch { /* no clipboard */ }
  });
  if (coins.length) loadQR().then(() => coins.forEach(([k, scheme]) => {
    const box = document.getElementById("qr-" + k);
    if (box && !box.childElementCount) new QRCode(box, { text: scheme + DONATE[k], width: 132, height: 132, correctLevel: QRCode.CorrectLevel.M });
  })).catch(() => {});
}

// ---------------------------------------------------------------------------
// tabs: one section at a time
// ---------------------------------------------------------------------------
const TABS = ["summary", "overview", "limits", "models", "savings", "projects", "tools", "tips", "sources"];
function currentTab() {
  const h = location.hash.replace("#", "");
  return TABS.includes(h) ? h : "summary";
}
function showTab() {
  if (!S.data) return;
  const a = currentTab();
  document.querySelectorAll(".section").forEach((s) => (s.hidden = s.id !== a));
  document.querySelectorAll("#tabs a").forEach((l) => l.classList.toggle("active", l.getAttribute("href") === "#" + a));
  // charts measure their space when drawn: redraw the tab that just appeared
  renderAll();
  window.scrollTo({ top: 0 });
}
window.addEventListener("hashchange", showTab);

// ---------------------------------------------------------------------------
// cycle
// ---------------------------------------------------------------------------
function renderChips() {
  const present = AGENT_ORDER.filter((a) => S.data.usage.some((r) => r.agent === a) || S.data.rtk.hourly.some((r) => r.agent === a));
  document.getElementById("agent-filter").innerHTML = present.map((a) =>
    `<button class="chip ${S.hiddenAgents.has(a) ? "off" : ""}" data-a="${a}" aria-pressed="${!S.hiddenAgents.has(a)}"><span class="dot" style="background:${agentColor(a)}"></span>${esc(agentName(a))}</button>`).join("");
  document.querySelectorAll("#agent-filter .chip").forEach((b) => b.onclick = () => {
    const a = b.dataset.a;
    S.hiddenAgents.has(a) ? S.hiddenAgents.delete(a) : S.hiddenAgents.add(a);
    savePref("hiddenAgents", JSON.stringify([...S.hiddenAgents]));
    renderAll();
  });
}

function renderAll() {
  if (!S.data) return;
  renderChips();
  const F = filtered();
  // only draws the visible tab (the hidden ones have no size for the charts);
  // the automatic rules always run because they feed the Summary
  const byTab = { summary: [renderSummary], overview: [renderOverview], limits: [renderLimits], models: [renderModels],
    savings: [renderSavings], projects: [renderProjects], tools: [renderTools], tips: [renderAI, renderScore], sources: [renderSources, renderPrices] };
  for (const fn of [renderTips, ...(byTab[currentTab()] || [])]) {
    try { fn(F); } catch (e) { console.error(fn.name, e); }
  }
  loadScore();
  document.getElementById("updated").textContent = t("header.data", { when: timeAgo(S.data.generated_at) });
}

async function load() {
  try {
    const r = await fetch("/api/data", { cache: "no-store" });
    const j = await r.json();
    if (r.status === 202 || j.loading) {
      document.getElementById("loading-status").textContent = j.error ? t("loading.error", { msg: j.error.split("\n")[0] }) : t("loading.title");
      setTimeout(load, 1500);
      return;
    }
    S.data = j;
    document.getElementById("loading").hidden = true;
    showTab();
  } catch {
    document.getElementById("loading-status").textContent = t("loading.offline");
    setTimeout(load, 4000);
  }
}

// language
function initLanguage() {
  const sel = document.getElementById("language");
  sel.innerHTML = Object.entries(LANGUAGES).map(([k, v]) => `<option value="${k}">${v}</option>`).join("");
  sel.value = LANG;
  sel.onchange = () => {
    LANG = sel.value;
    savePref("language", LANG);
    // tells the server so the tray app uses the same language
    post("/api/config", { language: LANG }).catch(() => {});
    configureFormats();
    translatePage();
    buildAIForm();
    renderSubscriptions();
    renderDonate();
    renderUpdate();
    renderAll();
  };
  translatePage();
  document.getElementById("updated").textContent = t("header.loading");
}
initLanguage();

document.querySelectorAll("#period button").forEach((b) => {
  b.classList.toggle("active", b.dataset.p === S.period);
  b.onclick = () => {
    S.period = b.dataset.p;
    savePref("period", S.period);
    document.querySelectorAll("#period button").forEach((x) => x.classList.toggle("active", x === b));
    renderAll();
  };
});

document.getElementById("btn-refresh").onclick = async (ev) => {
  const b = ev.currentTarget;
  b.disabled = true; b.textContent = t("btn.reading");
  try {
    await post("/api/refresh");
    const t0 = Date.now();
    const before = S.data?.generated_at || 0;
    while (Date.now() - t0 < 120000) {
      await new Promise((r) => setTimeout(r, 1200));
      const j = await (await fetch("/api/data", { cache: "no-store" })).json();
      if (j.generated_at && j.generated_at > before) { S.data = j; renderAll(); break; }
    }
  } finally { b.disabled = false; b.textContent = t("btn.refresh"); }
};

// theme
(function () {
  const saved = readPref("theme", "");
  if (saved) document.documentElement.dataset.theme = saved;
  document.getElementById("btn-theme").onclick = () => {
    const darkNow = document.documentElement.dataset.theme ? document.documentElement.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    const next = darkNow ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    savePref("theme", next);
    renderAll();
  };
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => !document.documentElement.dataset.theme && renderAll());
})();


// reloads the data every minute (the server collects in the background)
setInterval(async () => {
  try {
    const j = await (await fetch("/api/data", { cache: "no-store" })).json();
    if (j.generated_at && (!S.data || j.generated_at > S.data.generated_at)) { S.data = j; renderAll(); }
  } catch { /* server offline */ }
}, 60000);

// the settings (subscriptions, options) arrive before the first draw
loadConfig().finally(() => { load(); loadAI(); loadUpdate(); });
document.getElementById("btn-update-check").onclick = () => loadUpdate(true);
