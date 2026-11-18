// Live office: each active agent session is a character in a small animated office.
// Data comes from /api/live (see live.py); with ?demo=1, or when the server runs in demo
// mode, a local simulation feeds the same events. Art comes from sprites/manifest.json
// (built by tools/build_sprites.py); anything without a sprite yet is drawn in code.
(() => {
  "use strict";
  const W = 1600, H = 900;
  const cv = document.getElementById("scene");
  const ctx = cv.getContext("2d");
  const $ = (id) => document.getElementById(id);

  // ---------------------------------------------------------------------------
  // text
  // ---------------------------------------------------------------------------
  const TEXT = {
    pt: { agents: "agentes", tokens: "tokens", saved: "economizados", tools: "ferramentas", activity: "Atividade",
      emptyTitle: "Ninguém trabalhando agora", emptySub: "Os agentes aparecem aqui quando uma sessão do Claude Code ou do Codex está ativa.",
      demo: "simulação", offline: "sem conexão com o painel", newTask: "nova tarefa", done: "terminou", thinking: "pensando…",
      waiting: "esperando", saving: "economizou", subagent: "chamou um ajudante",
      cat: { command_output: "Compactador", code_index: "Mapa de código", proxy: "Filtro", memory: "Memória", response_style: "Texto curto", mcp: "MCP" } },
    en: { agents: "agents", tokens: "tokens", saved: "saved", tools: "tools", activity: "Activity",
      emptyTitle: "Nobody is working right now", emptySub: "Agents show up here while a Claude Code or Codex session is active.",
      demo: "simulation", offline: "can't reach the panel", newTask: "new task", done: "done", thinking: "thinking…",
      waiting: "waiting", saving: "saved", subagent: "called a helper",
      cat: { command_output: "Compactor", code_index: "Code map", proxy: "Filter", memory: "Memory", response_style: "Short replies", mcp: "MCP" } },
    es: { agents: "agentes", tokens: "tokens", saved: "ahorrados", tools: "herramientas", activity: "Actividad",
      emptyTitle: "Nadie está trabajando ahora", emptySub: "Los agentes aparecen aquí mientras una sesión de Claude Code o Codex está activa.",
      demo: "simulación", offline: "sin conexión con el panel", newTask: "nueva tarea", done: "terminó", thinking: "pensando…",
      waiting: "esperando", saving: "ahorró", subagent: "llamó a un ayudante",
      cat: { command_output: "Compactador", code_index: "Mapa de código", proxy: "Filtro", memory: "Memoria", response_style: "Texto corto", mcp: "MCP" } },
  };
  let T = TEXT.pt;
  function applyText() {
    document.querySelectorAll("[data-t]").forEach((el) => (el.textContent = T[el.dataset.t] || ""));
  }

  // ---------------------------------------------------------------------------
  // sprites
  // ---------------------------------------------------------------------------
  const SPR = {};          // group -> pose -> {img, frames, w, h, faces}
  let STAND = 360;
  let SCALE = 0.47;        // sprite px -> scene px (standing character ≈ 170 px; bigger in the painted room)
  const CHAR_NAMES = { nina: "Nina", theo: "Theo", kai: "Kai", lia: "Lia", bruno: "Bruno", maya: "Maya" };

  async function loadSprites() {
    try {
      const m = await (await fetch("sprites/manifest.json", { cache: "no-store" })).json();
      STAND = m.stand || STAND;
      const jobs = [];
      for (const [group, poses] of Object.entries(m.sprites || {})) {
        for (const [pose, e] of Object.entries(poses)) {
          const img = new Image();
          img.src = "sprites/" + e.file + (m.v ? "?v=" + m.v : "");
          (SPR[group] ||= {})[pose] = { ...e, img };
          jobs.push(img.decode().catch(() => {}));
        }
      }
      await Promise.all(jobs);
    } catch { /* no sprites yet: everything is drawn in code */ }
  }
  const characters = () => Object.keys(CHAR_NAMES).filter((k) => SPR[k] && SPR[k].walk_front && SPR[k].type);

  function drawSprite(group, pose, frame, x, y, opt = {}) {
    const s = SPR[group] && SPR[group][pose];
    if (!s || !s.img.complete) return false;
    const k = (opt.scale || SCALE);
    const f = Math.floor(frame) % s.frames;
    const dw = s.w * k, dh = s.h * k;
    const sy = opt.squash || 1;
    ctx.save();
    ctx.globalAlpha = opt.alpha ?? 1;
    ctx.translate(x, y);
    if (opt.shear) ctx.transform(1, opt.shear, 0, 1, 0, 0);  // vertical skew: match a wall's slope
    if (opt.mirror) ctx.scale(-1, 1);
    ctx.scale(1 / sy ** 0.5, sy);
    ctx.drawImage(s.img, f * s.w, 0, s.w, s.h, -dw / 2, -dh + 2 * k, dw, dh);
    ctx.restore();
    return true;
  }

  // ---------------------------------------------------------------------------
  // layout (scene coordinates; y is the floor line = depth)
  // ---------------------------------------------------------------------------
  const FLOOR_Y = 348;
  const DOOR = { x: 105, y: 372 };
  const COFFEE = [{ x: 300, y: 432 }, { x: 375, y: 452 }, { x: 225, y: 458 }];
  const NAP = [{ x: 1430, y: 800 }, { x: 1520, y: 830 }, { x: 1340, y: 840 }];
  const CATS = ["command_output", "code_index", "proxy", "memory", "response_style", "mcp"];
  const CAT_COLOR = { command_output: "#3f9a96", code_index: "#6c5fc0", proxy: "#e07a4f", memory: "#a45cb8", response_style: "#d9a23c", mcp: "#5b6d82" };
  const CAT_SPRITE = { command_output: "compactor", code_index: "map", proxy: "gateway", memory: "memory", response_style: "terse", mcp: "mcp" };
  const MACHINES = CATS.map((cat, i) => ({ cat, x: 865 + i * 124, y: FLOOR_Y + 8, active: 0, last: "", users: 0 }));
  const DESKS = [
    { x: 250, y: 585 }, { x: 640, y: 585 }, { x: 1030, y: 585 },
    { x: 250, y: 800 }, { x: 640, y: 800 }, { x: 1030, y: 800 },
  ].map((d) => ({ ...d, owner: null, screen: 0 }));
  const machineFor = (cat) => MACHINES.find((m) => m.cat === cat) || MACHINES[MACHINES.length - 1];

  // Painted room (loft bg sprite): a 3/4 view whose back corner is CORNER; the brick wall runs
  // down-left from it and the plain wall down-right. Everything is laid out against those walls.
  let ART = false;
  const CORNER = { x: 823, y: 330 };
  const DESK_OFF = { x: 88, y: 42 };   // desk sprite anchor relative to the seat (seat is up-left of it)
  const MAIN = 705;                    // walkway between the two desk rows
  const AISLES_ART = [430, 750, 1050, 1370];
  // walkway along the walls, parallel to them
  const backLane = (x) => 435 + (x > CORNER.x ? 0.277 * (x - CORNER.x) : 0.285 * (CORNER.x - x));
  function useArtLayout() {
    ART = true;
    SCALE = 0.55;
    document.body.classList.add("art");
    MACHINES.forEach((m, i) => { const a = 100 + 118 * i; m.x = CORNER.x + a - 28; m.y = CORNER.y + 0.277 * a + 24; });
    const seats = [[530, 585], [830, 585], [1130, 585], [490, 775], [790, 775], [1090, 775]];
    DESKS.forEach((d, i) => { d.x = seats[i][0]; d.y = seats[i][1]; d.kind = i % 2 ? "desk_b" : "desk"; });
    Object.assign(DOOR, { x: 130, y: 618 });   // in front of the door on the brick wall, left of the window
    COFFEE.splice(0, COFFEE.length, { x: 650, y: 462 }, { x: 735, y: 474 }, { x: 575, y: 478 });
    NAP.splice(0, NAP.length, { x: 300, y: 700 }, { x: 440, y: 698 }, { x: 190, y: 692 });
  }

  // ---------------------------------------------------------------------------
  // background (drawn once per hour into an offscreen canvas)
  // ---------------------------------------------------------------------------
  let bg = null, bgHour = -1, dpr = 1, view = 1;

  function skyColors(h) {
    if (h >= 7 && h < 17) return ["#8ec9ef", "#d8eef8", false];
    if (h >= 17 && h < 19) return ["#f1a06b", "#f7d59a", false];
    if (h >= 5 && h < 7) return ["#9fb4e0", "#f6c9a8", false];
    return ["#1b2347", "#3a3566", true];
  }
  const isNight = () => skyColors(new Date().getHours())[2];

  function roundRect(c, x, y, w, h, r) {
    c.beginPath();
    c.moveTo(x + r, y); c.arcTo(x + w, y, x + w, y + h, r); c.arcTo(x + w, y + h, x, y + h, r);
    c.arcTo(x, y + h, x, y, r); c.arcTo(x, y, x + w, y, r); c.closePath();
  }

  function buildBackground() {
    const hour = new Date().getHours();
    bgHour = hour;
    const c2 = document.createElement("canvas");
    c2.width = Math.round(W * view * dpr); c2.height = Math.round(H * view * dpr);
    const c = c2.getContext("2d");
    c.scale(view * dpr, view * dpr);
    const bgImg = SPR.loft && (SPR.loft[isNight() ? "bg_night" : "bg_day"] || SPR.loft.bg_day);
    if (bgImg) { c.drawImage(bgImg.img, 0, 0, W, H); bg = c2; return; }
    const [skyTop, skyBottom, night] = skyColors(hour);

    // walls
    let g = c.createLinearGradient(0, 0, 0, FLOOR_Y);
    g.addColorStop(0, night ? "#d9cbbb" : "#f1e6d6"); g.addColorStop(1, night ? "#c9b8a5" : "#e5d4bf");
    c.fillStyle = g; c.fillRect(0, 0, W, FLOOR_Y);
    // exposed brick on the left
    c.save(); c.beginPath(); c.rect(0, 0, 560, FLOOR_Y); c.clip();
    c.fillStyle = night ? "#8f5a45" : "#b06a4c"; c.fillRect(0, 0, 560, FLOOR_Y);
    for (let row = 0, y = 0; y < FLOOR_Y; row++, y += 24) {
      for (let x = (row % 2) * -32; x < 560; x += 64) {
        const t = ((x * 7 + row * 13) % 17) / 17;
        c.fillStyle = `hsl(${14 + t * 8}, ${38 + t * 10}%, ${night ? 34 + t * 6 : 43 + t * 8}%)`;
        roundRect(c, x + 2, y + 2, 60, 20, 3); c.fill();
      }
    }
    g = c.createLinearGradient(400, 0, 560, 0);
    g.addColorStop(0, "rgba(0,0,0,0)"); g.addColorStop(1, "rgba(0,0,0,.18)");
    c.fillStyle = g; c.fillRect(400, 0, 160, FLOOR_Y);
    c.restore();

    // window
    const wx = 610, wy = 48, ww = 200, wh = 240;
    for (const ox of [0, 0]) void ox;
    for (let i = 0; i < 1; i++) {
      g = c.createLinearGradient(0, wy, 0, wy + wh);
      g.addColorStop(0, skyTop); g.addColorStop(1, skyBottom);
      c.fillStyle = g; c.fillRect(wx - 180, wy, ww + 180, wh);
      // skyline
      let seed = 7;
      const rnd = () => ((seed = (seed * 9301 + 49297) % 233280) / 233280);
      for (let x = wx - 180; x < wx + ww; x += 22 + rnd() * 18) {
        const bh = 50 + rnd() * 120, bw = 18 + rnd() * 26;
        c.fillStyle = night ? "#11152c" : "#7b93ad";
        c.fillRect(x, wy + wh - bh, bw, bh);
        for (let yy = wy + wh - bh + 8; yy < wy + wh - 6; yy += 12) {
          for (let xx = x + 4; xx < x + bw - 4; xx += 8) {
            if (rnd() < (night ? 0.45 : 0.15)) { c.fillStyle = night ? "#ffd27a" : "#c7d9ea"; c.fillRect(xx, yy, 4, 5); }
          }
        }
      }
    }
    c.lineWidth = 10; c.strokeStyle = "#2f3138";
    c.strokeRect(wx - 180, wy, ww + 180, wh);
    c.lineWidth = 5;
    for (let i = 1; i < 4; i++) { c.beginPath(); c.moveTo(wx - 180 + i * (ww + 180) / 4, wy); c.lineTo(wx - 180 + i * (ww + 180) / 4, wy + wh); c.stroke(); }
    c.beginPath(); c.moveTo(wx - 180, wy + wh * 0.55); c.lineTo(wx + ww, wy + wh * 0.55); c.stroke();
    c.fillStyle = "#3a3c44"; c.fillRect(wx - 192, wy + wh + 2, ww + 204, 10);

    // neon sign above the machines
    c.save();
    c.font = "700 46px 'Segoe UI', system-ui, sans-serif"; c.textAlign = "center"; c.textBaseline = "middle";
    c.shadowColor = night ? "#ff7ad9" : "rgba(224,122,79,.6)"; c.shadowBlur = night ? 26 : 10;
    c.fillStyle = night ? "#ffd1f1" : "#e07a4f";
    c.fillText("TOKEN ECONOMY", 1175, 92);
    c.font = "600 18px 'Segoe UI', system-ui, sans-serif"; c.shadowBlur = night ? 16 : 0;
    c.fillStyle = night ? "#9ff3ff" : "#3f9a96";
    c.fillText("· HQ ·", 1175, 132);
    c.restore();

    // door frame (the door itself is drawn live, it opens)
    c.fillStyle = "#4a3426"; c.fillRect(42, 112, 126, FLOOR_Y - 112);

    // coffee counter
    c.fillStyle = "#7a5238"; roundRect(c, 200, 238, 190, 112, 6); c.fill();
    c.fillStyle = "#9a6a48"; c.fillRect(196, 232, 198, 12);
    c.fillStyle = "#c9ccd2"; roundRect(c, 232, 168, 62, 66, 8); c.fill();
    c.fillStyle = "#3a3d44"; c.fillRect(244, 186, 38, 16);
    c.fillStyle = "#e9e2d6"; for (let i = 0; i < 3; i++) { roundRect(c, 312 + i * 22, 210, 16, 22, 4); c.fill(); }
    c.fillStyle = "#3d7a4a"; c.beginPath(); c.ellipse(372, 196, 16, 26, 0, 0, Math.PI * 2); c.fill();

    // baseboard and floor
    c.fillStyle = "#6b4a33"; c.fillRect(0, FLOOR_Y - 8, W, 10);
    g = c.createLinearGradient(0, FLOOR_Y, 0, H);
    g.addColorStop(0, night ? "#8c6644" : "#c99d70"); g.addColorStop(1, night ? "#6f4f35" : "#b4855a");
    c.fillStyle = g; c.fillRect(0, FLOOR_Y, W, H - FLOOR_Y);
    c.strokeStyle = "rgba(70,40,20,.18)"; c.lineWidth = 2;
    for (let i = 0, y = FLOOR_Y + 14; y < H; i++, y += 16 + i * 2.2) {
      c.beginPath(); c.moveTo(0, y); c.lineTo(W, y); c.stroke();
      for (let x = (i % 3) * 140; x < W; x += 420) { c.beginPath(); c.moveTo(x, y); c.lineTo(x, y + 16 + i * 2.2); c.stroke(); }
    }
    // rug
    c.save();
    c.fillStyle = night ? "#2f6f72" : "#3f9a96"; roundRect(c, 150, 470, 1120, 400, 26); c.fill();
    c.strokeStyle = "#f0e6d2"; c.lineWidth = 6; roundRect(c, 172, 490, 1076, 360, 18); c.stroke();
    c.strokeStyle = "rgba(240,230,210,.35)"; c.lineWidth = 3;
    for (let x = 220; x < 1240; x += 70) { c.beginPath(); c.moveTo(x, 500); c.lineTo(x + 30, 520); c.lineTo(x, 540); c.stroke(); }
    c.restore();
    // lounge rug and sofa
    c.fillStyle = night ? "#6d4a7a" : "#d9a23c"; c.beginPath(); c.ellipse(1450, 800, 150, 70, 0, 0, Math.PI * 2); c.fill();

    // pendant lamps
    for (const lx of [420, 840, 1260]) {
      c.strokeStyle = "#2f3138"; c.lineWidth = 2; c.beginPath(); c.moveTo(lx, 0); c.lineTo(lx, 30); c.stroke();
      c.fillStyle = "#2f3138"; c.beginPath(); c.moveTo(lx - 22, 52); c.lineTo(lx + 22, 52); c.lineTo(lx + 8, 30); c.lineTo(lx - 8, 30); c.fill();
      if (night) {
        const rg = c.createRadialGradient(lx, 60, 4, lx, 60, 260);
        rg.addColorStop(0, "rgba(255,214,140,.55)"); rg.addColorStop(1, "rgba(255,214,140,0)");
        c.fillStyle = rg; c.fillRect(lx - 260, 40, 520, 520);
      }
    }
    if (night) { c.fillStyle = "rgba(30,20,70,.18)"; c.fillRect(0, 0, W, H); }
    bg = c2;
  }

  // ---------------------------------------------------------------------------
  // props drawn in depth order with the people
  // ---------------------------------------------------------------------------
  function drawChair(x, y) {
    if (drawSprite("loft", "chair", 0, x - 6, y + 4, { scale: 0.5 })) return;
    ctx.fillStyle = "#3b3f4a"; roundRect(ctx, x - 34, y - 150, 50, 82, 12); ctx.fill();
    ctx.fillStyle = "#2a9d9a"; roundRect(ctx, x - 30, y - 144, 42, 20, 8); ctx.fill();
    ctx.fillStyle = "#3b3f4a"; roundRect(ctx, x - 40, y - 74, 84, 16, 7); ctx.fill();
    ctx.fillStyle = "#2b2e36"; ctx.fillRect(x - 3, y - 58, 6, 44);
    ctx.fillRect(x - 30, y - 16, 60, 5);
  }

  const DESK_SCALE = 0.6;
  function drawDesk(d, t) {
    if (ART && SPR.loft && SPR.loft[d.kind]) {
      // the person sits up-left of the desk, facing the monitor; the desk hides their legs
      const x = d.x + DESK_OFF.x, y = d.y + DESK_OFF.y;
      ctx.fillStyle = "rgba(40,20,10,.18)"; ctx.beginPath(); ctx.ellipse(x, y - 4, 118, 16, 0, 0, Math.PI * 2); ctx.fill();
      drawSprite("loft", d.kind, 0, x, y, { scale: DESK_SCALE });
      if (d.screen > t) {
        // the screen faces the seat: a soft glow on the person's side
        const gx = x - 20, gy = y - 120;
        const rg = ctx.createRadialGradient(gx, gy, 6, gx, gy, 90);
        rg.addColorStop(0, "rgba(120,220,255,.28)"); rg.addColorStop(1, "rgba(120,220,255,0)");
        ctx.fillStyle = rg; ctx.fillRect(gx - 100, gy - 100, 200, 200);
      }
      return;
    }
    const x = d.x + 40, y = d.y, w = 210, top = y - 82;
    if (drawSprite("loft", "desk", 0, x + w / 2, y + 6, { scale: 0.5 })) return;
    ctx.fillStyle = "rgba(0,0,0,.14)"; ctx.beginPath(); ctx.ellipse(x + w / 2, y + 4, w / 2 + 10, 12, 0, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#5d4330"; ctx.fillRect(x + 10, top + 14, 10, 80); ctx.fillRect(x + w - 20, top + 14, 10, 80);
    ctx.fillStyle = "#8a6142"; roundRect(ctx, x + 6, top + 14, w - 12, 46, 6); ctx.fill();
    ctx.fillStyle = "#b98a5e"; roundRect(ctx, x, top, w, 18, 6); ctx.fill();
    // monitor, screen turned toward the seat
    const mx = x + 70, my = top - 78;
    ctx.fillStyle = "#2b2e36"; ctx.fillRect(mx + 40, top - 14, 10, 14); ctx.fillRect(mx + 22, top - 4, 46, 6);
    ctx.fillStyle = "#2b2e36"; roundRect(ctx, mx, my, 92, 66, 7); ctx.fill();
    const on = d.screen > t;
    ctx.fillStyle = on ? "#1c2b3a" : "#232831"; roundRect(ctx, mx + 6, my + 6, 80, 54, 4); ctx.fill();
    if (on) {
      ctx.save(); ctx.beginPath(); ctx.rect(mx + 6, my + 6, 80, 54); ctx.clip();
      const off = (t * 22) % 12;
      for (let i = 0; i < 6; i++) {
        const ly = my + 12 + i * 10 - off;
        ctx.fillStyle = ["#6fd3c9", "#f0b46a", "#a99cf0", "#8fd16f"][i % 4];
        ctx.fillRect(mx + 12 + (i % 3) * 6, ly, 20 + ((i * 37) % 40), 4);
      }
      ctx.restore();
      const rg = ctx.createRadialGradient(mx + 46, my + 33, 4, mx + 46, my + 33, 90);
      rg.addColorStop(0, "rgba(120,220,255,.18)"); rg.addColorStop(1, "rgba(120,220,255,0)");
      ctx.fillStyle = rg; ctx.fillRect(mx - 50, my - 60, 200, 200);
    }
    ctx.fillStyle = "#e9e2d6"; roundRect(ctx, x + 16, top - 8, 54, 8, 3); ctx.fill();   // keyboard
    ctx.fillStyle = "#e8d6b8"; roundRect(ctx, x + 172, top - 20, 18, 20, 4); ctx.fill(); // mug
  }

  function drawMachine(m, t) {
    const on = m.active > t;
    const key = CAT_SPRITE[m.cat];
    const spr = SPR.machine && SPR.machine[key + (on ? "_on" : "_idle")];
    const color = CAT_COLOR[m.cat];
    if (on) {
      const rg = ctx.createRadialGradient(m.x, m.y - 80, 10, m.x, m.y - 80, 130);
      rg.addColorStop(0, hexA(color, 0.45)); rg.addColorStop(1, hexA(color, 0));
      ctx.fillStyle = rg; ctx.fillRect(m.x - 140, m.y - 220, 280, 280);
    }
    if (spr) {
      drawSprite("machine", key + (on ? "_on" : "_idle"), on ? t * 8 : 0, m.x, m.y, { scale: 0.45 });
    } else {
      const x = m.x - 50, y = m.y - 160;
      ctx.fillStyle = "rgba(0,0,0,.15)"; ctx.beginPath(); ctx.ellipse(m.x, m.y, 56, 10, 0, 0, Math.PI * 2); ctx.fill();
      const g = ctx.createLinearGradient(x, 0, x + 100, 0);
      g.addColorStop(0, "#e9e4dc"); g.addColorStop(1, "#c9c2b6");
      ctx.fillStyle = g; roundRect(ctx, x, y, 100, 160, 14); ctx.fill();
      ctx.fillStyle = color; roundRect(ctx, x + 8, y + 10, 84, 10, 5); ctx.fill();
      ctx.fillStyle = on ? "#14242c" : "#2a2f37"; roundRect(ctx, x + 14, y + 30, 72, 52, 8); ctx.fill();
      if (on) machineScreen(m, x + 14, y + 30, t, color);
      for (let i = 0; i < 4; i++) {
        const lit = on && Math.floor(t * 6 + i) % 4 === 0;
        ctx.fillStyle = lit ? color : "#8e877c";
        ctx.beginPath(); ctx.arc(x + 22 + i * 19, y + 100, 5, 0, Math.PI * 2); ctx.fill();
      }
      ctx.fillStyle = "#b3aa9c"; roundRect(ctx, x + 14, y + 118, 72, 30, 6); ctx.fill();
    }
  }

  function drawMachineLabel(m, t) {
    const on = m.active > t, color = CAT_COLOR[m.cat];
    const label = m.last || T.cat[m.cat];
    ctx.font = "600 13px 'Segoe UI', system-ui, sans-serif";
    const tw = Math.max(60, ctx.measureText(label).width + 16);
    ctx.fillStyle = on ? color : "rgba(43,36,32,.75)";
    roundRect(ctx, m.x - tw / 2, m.y + 8, tw, 22, 11); ctx.fill();
    ctx.fillStyle = "#fff"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(label, m.x, m.y + 19.5);
  }

  function machineScreen(m, x, y, t, color) {
    ctx.save(); ctx.beginPath(); ctx.rect(x, y, 72, 52); ctx.clip();
    if (m.cat === "code_index") {
      const pts = [...Array(7)].map((_, i) => [x + 36 + Math.cos(i * 0.9 + t) * 24, y + 26 + Math.sin(i * 1.7 + t * 0.8) * 16]);
      ctx.strokeStyle = hexA(color, 0.9); ctx.lineWidth = 1.5;
      for (let i = 1; i < pts.length; i++) { ctx.beginPath(); ctx.moveTo(...pts[0]); ctx.lineTo(...pts[i]); ctx.stroke(); }
      ctx.fillStyle = "#c9bfff"; pts.forEach((p) => { ctx.beginPath(); ctx.arc(p[0], p[1], 3, 0, Math.PI * 2); ctx.fill(); });
    } else {
      for (let i = 0; i < 5; i++) {
        const w = (m.cat === "command_output" ? 60 - ((t * 40 + i * 13) % 50) : 20 + ((i * 29 + t * 30) % 40));
        ctx.fillStyle = hexA(color, 0.9);
        ctx.fillRect(x + 6, y + 6 + i * 9, Math.max(6, w), 4);
      }
    }
    ctx.restore();
  }

  // coffee counter against the brick wall (painted room; the drawn room has it in the background)
  function drawCoffeeCounter(x, y) {
    if (drawSprite("loft", "coffee", 0, x, y, { scale: 0.5 })) return;
    ctx.fillStyle = "rgba(40,20,10,.18)"; ctx.beginPath(); ctx.ellipse(x, y, 100, 12, 0, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#5a3d2b"; roundRect(ctx, x - 90, y - 92, 180, 92, 6); ctx.fill();
    ctx.fillStyle = "#8a5e40"; ctx.fillRect(x - 96, y - 100, 192, 12);
    ctx.fillStyle = "#c9ccd2"; roundRect(ctx, x - 64, y - 168, 56, 68, 8); ctx.fill();
    ctx.fillStyle = "#3a3d44"; ctx.fillRect(x - 54, y - 150, 36, 14);
    ctx.fillStyle = "#e9e2d6"; for (let i = 0; i < 3; i++) { roundRect(ctx, x + 6 + i * 22, y - 122, 16, 22, 4); ctx.fill(); }
  }

  function drawDoor(t) {
    const open = doorOpenUntil > t;
    if (ART) {
      // door on the brick wall, left of the window; the rug lies on the floor under the lounge
      drawSprite("loft", "rug", 0, 330, 790, { scale: 0.6 });
      // the door art is drawn steeper than the brick wall (its bottom rises 0.42 px per px, the
      // baseboard 0.25): a vertical skew lines its foot up with the floor along the wall
      if (!(open && drawSprite("loft", "door_open", 0, 79, 563, { scale: 0.83, shear: 0.165 }))) {
        drawSprite("loft", "door_closed", 0, 79, 565, { scale: 0.83, shear: 0.167 });
      }
      return;
    }
    const x = 52, y = 122, w = 106, h = FLOOR_Y - 124;
    ctx.fillStyle = open ? "#fff3d6" : "#2e2018"; ctx.fillRect(x, y, w, h);
    if (open) {
      ctx.fillStyle = "#8a5e40"; ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + 34, y + 14); ctx.lineTo(x + 34, y + h + 6); ctx.lineTo(x, y + h); ctx.fill();
    } else {
      ctx.fillStyle = "#8a5e40"; ctx.fillRect(x + 4, y + 4, w - 8, h - 4);
      ctx.fillStyle = "rgba(220,235,240,.65)"; roundRect(ctx, x + 18, y + 20, w - 36, 90, 6); ctx.fill();
      ctx.fillStyle = "#e0b04a"; ctx.beginPath(); ctx.arc(x + w - 18, y + h / 2 + 20, 5, 0, Math.PI * 2); ctx.fill();
    }
  }

  function drawPlant(x, y, s = 1) {
    if (drawSprite("loft", s > 1 ? "plant_tall" : "plant_small", 0, x, y, { scale: 0.45 })) return;
    ctx.fillStyle = "rgba(0,0,0,.15)"; ctx.beginPath(); ctx.ellipse(x, y, 26 * s, 7 * s, 0, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#d9cfc0"; roundRect(ctx, x - 20 * s, y - 40 * s, 40 * s, 40 * s, 8); ctx.fill();
    for (let i = 0; i < 7; i++) {
      const a = -Math.PI / 2 + (i - 3) * 0.38;
      ctx.fillStyle = i % 2 ? "#3f8a52" : "#55a564";
      ctx.beginPath();
      ctx.ellipse(x + Math.cos(a) * 34 * s, y - 40 * s + Math.sin(a) * 50 * s, 13 * s, 30 * s, a + Math.PI / 2, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  function drawSofa(x, y) {
    if (drawSprite("loft", "sofa", 0, x, y, { scale: 0.5 })) return;
    ctx.fillStyle = "rgba(0,0,0,.16)"; ctx.beginPath(); ctx.ellipse(x, y + 2, 140, 14, 0, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#b5573a"; roundRect(ctx, x - 130, y - 110, 260, 70, 22); ctx.fill();
    ctx.fillStyle = "#c9694a"; roundRect(ctx, x - 140, y - 60, 280, 52, 16); ctx.fill();
    ctx.fillStyle = "#a54d33"; roundRect(ctx, x - 150, y - 86, 34, 80, 14); ctx.fill(); roundRect(ctx, x + 116, y - 86, 34, 80, 14); ctx.fill();
    ctx.fillStyle = "#f0d9a8"; roundRect(ctx, x - 90, y - 100, 50, 40, 12); ctx.fill();
  }

  // ---------------------------------------------------------------------------
  // agents
  // ---------------------------------------------------------------------------
  const agents = new Map();   // session id -> agent
  window.__office = { agents };
  const bots = new Map();     // session id -> helper bot
  const fx = [];              // particles and floating texts
  let doorOpenUntil = 0;
  const now = () => performance.now() / 1000;

  function hash(s) { let h = 0; for (const ch of s) h = (h * 31 + ch.charCodeAt(0)) | 0; return Math.abs(h); }
  function hexA(hex, a) {
    const n = parseInt(hex.slice(1), 16);
    return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`;
  }
  function fmt(n) {
    if (n >= 1e9) return (n / 1e9).toFixed(1) + "B";
    if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
    if (n >= 1e3) return (n / 1e3).toFixed(1) + "k";
    return String(Math.round(n));
  }

  function newAgent(s, entering) {
    const chars = characters();
    const inside = [...agents.values()].filter((a) => !a.leaving);   // one walking out frees its character
    const used = inside.map((a) => a.char);
    let char = chars.find((c) => !used.includes(c));
    if (!char && chars.length) char = chars[hash(s.id) % chars.length];
    const base = CHAR_NAMES[char] || "Agent";
    const twins = inside.filter((a) => a.char === char).length;
    // a free desk, or the one someone is walking out of right now
    const desk = DESKS.find((d) => !d.owner) || DESKS.find((d) => agents.get(d.owner)?.leaving)
      || DESKS[hash(s.id) % DESKS.length];
    desk.owner = s.id;
    const a = {
      id: s.id, agent: s.agent, project: s.project || "", char, name: twins ? `${base} ${["", "II", "III", "IV"][twins] || twins + 1}` : base,
      desk, x: entering ? DOOR.x : desk.x, y: entering ? DOOR.y : desk.y, path: null, place: "desk", pose: "think",
      mirror: false, frame: 0, busyUntil: 0, queue: [], bubble: null, celebrateUntil: 0, last: now(), alpha: entering ? 0 : 1,
      leaving: false, spot: null, seed: Math.random() * 10, sessions: new Map([[s.id, s.project || ""]]),
    };
    agents.set(s.id, a);
    if (entering) { doorOpenUntil = now() + 1.6; goTo(a, "desk"); }
    return a;
  }

  function napsAtDesk(a) { return !!(SPR[a.char] && SPR[a.char].sleep && SPR[a.char].sleep.seated); }

  // standing spots are reserved: each agent keeps its slot until it goes elsewhere, so a newcomer
  // takes the next free one instead of landing on top of whoever is already there
  function freeSlot(a, place, key) {
    const taken = new Set([...agents.values()]
      .filter((o) => o !== a && o.place === place && o.slotKey === key && o.slot != null).map((o) => o.slot));
    let i = 0;
    while (taken.has(i)) i++;
    a.slot = i; a.slotKey = key;
    return i;
  }
  // past the listed spots, line up beside the last one
  const slotAt = (list, i) => (i < list.length ? list[i]
    : { x: list[list.length - 1].x - 70 * (i - list.length + 1), y: list[list.length - 1].y + 8 * (i - list.length + 1) });

  function spotFor(a, place, extra) {
    if (place === "desk") return { x: a.desk.x, y: a.desk.y };
    if (place === "coffee") return slotAt(COFFEE, freeSlot(a, "coffee", "coffee"));
    if (place === "nap") {
      // a nap drawn seated (head on the arms) happens in the desk chair; a standing one by the sofa
      if (napsAtDesk(a)) return { x: a.desk.x, y: a.desk.y };
      return slotAt(NAP, freeSlot(a, "nap", "sofa"));
    }
    if (place === "door") return DOOR;
    if (place === "machine") {
      const m = extra; const n = freeSlot(a, "machine", m.cat);
      return ART ? { x: m.x + 60 + n * 36, y: m.y + 62 + n * 14 } : { x: m.x + 66 + n * 40, y: m.y + 72 + n * 18 };
    }
    return { x: a.x, y: a.y };
  }

  function goTo(a, place, extra) {
    if (a.place === "machine" && a.machine) { a.machine.users = Math.max(0, a.machine.users - 1); a.machine = null; }
    a.slot = null; a.slotKey = null;
    const to = spotFor(a, place, extra);
    a.place = place;
    if (place === "machine") { a.machine = extra; extra.users++; }
    if (Math.hypot(to.x - a.x, to.y - a.y) < 4) { a.path = null; return; }
    a.path = route(a, to);
  }

  // walk along the corridors between the desk rows instead of through the desks
  const AISLES = [545, 935, 1300];
  function lane(p) {
    if (p.y <= 470) return 450;          // the free strip in front of the back wall
    if (p.x > 1265) return null;         // lounge on the right: open floor
    return p.y < 700 ? 450 : 690;        // above row 1, or between the rows
  }
  // painted room: two walkways (along the walls, and between the desk rows) joined by aisles
  function artLane(p) {
    if (p.x < 0) return "main";
    // the back desk row, the coffee corner and the machines are reached from the wall walkway
    return p.y < 610 ? "back" : "main";
  }
  const laneY = (l, x) => (l === "back" ? backLane(x) : MAIN);
  function along(l, x1, x2, pts) {
    // the wall walkway bends at the corner
    if (l === "back" && (x1 - CORNER.x) * (x2 - CORNER.x) < 0) pts.push({ x: CORNER.x, y: backLane(CORNER.x) });
    pts.push({ x: x2, y: laneY(l, x2) });
  }
  function artRoute(a, b) {
    const pts = [];
    const la = artLane(a), lb = artLane(b);
    pts.push({ x: a.x, y: laneY(la, a.x) });
    let x = a.x;
    if (la !== lb) {
      const mid = (a.x + b.x) / 2;
      const ax = AISLES_ART.reduce((p, q) => (Math.abs(q - mid) < Math.abs(p - mid) ? q : p));
      along(la, x, ax, pts);
      pts.push({ x: ax, y: laneY(lb, ax) });
      x = ax;
    }
    along(lb, x, b.x, pts);
    pts.push({ x: b.x, y: b.y });
    return pts.filter((p, i) => i === 0 ? Math.hypot(p.x - a.x, p.y - a.y) > 4 : Math.hypot(p.x - pts[i - 1].x, p.y - pts[i - 1].y) > 4);
  }

  function route(a, b) {
    if (ART) return artRoute(a, b);
    const pts = [];
    const la = lane(a), lb = lane(b);
    const y1 = la ?? lb ?? b.y;
    const y2 = lb ?? y1;
    if (Math.abs(a.y - y1) > 4) pts.push({ x: a.x, y: y1 });
    if (y1 !== y2) {
      const mid = (a.x + b.x) / 2;
      const ax = AISLES.reduce((p, q) => (Math.abs(q - mid) < Math.abs(p - mid) ? q : p));
      pts.push({ x: ax, y: y1 }, { x: ax, y: y2 });
    }
    pts.push({ x: b.x, y: y2 }, { x: b.x, y: b.y });
    return pts;
  }

  function bubble(a, icon, text, secs = 2.2) {
    a.bubble = { icon, text: text || "", until: now() + secs, born: now() };
  }

  const ICON = { terminal: "⌨️", read: "📄", edit: "✏️", search: "🔍", web: "🌐", idea: "💡", plug: "🔌", bot: "🤖",
    wait: "⏳", done: "✅", warn: "⚠️", coins: "🪙", prompt: "💬", think: "💭", sleep: "💤" };
  // position of each icon in sprites/icons.png (the emoji stays as the fallback and in the feed)
  const ICON_CELL = { "⌨️": 0, "📄": 1, "✏️": 2, "🔍": 3, "🌐": 4, "💡": 5, "💭": 5, "🔌": 6, "🤖": 7,
    "⏳": 8, "✅": 9, "⚠️": 10, "🪙": 11 };

  // one event changes what the agent is doing; quick ones only update the bubble
  function handle(a, e) {
    const t = now();
    a.last = t;
    if (a.place === "nap" && e.kind !== "tokens") goTo(a, "desk");
    switch (e.kind) {
      case "prompt":
        goTo(a, "desk"); a.pose = "think";
        bubble(a, ICON.prompt, e.label, 3.2); a.busyUntil = t + 1.6;
        log(a, ICON.prompt + " " + (e.label || T.newTask));
        break;
      case "think":
        if (a.place !== "desk") goTo(a, "desk");
        a.pose = "think"; if (!a.bubble || a.bubble.until < t) bubble(a, ICON.think, T.thinking, 1.2);
        a.busyUntil = t + 0.6;
        break;
      case "say":
        bubble(a, "", e.label, 3.0);
        break;
      case "tool": {
        if (e.sub) return subagent(a, e);
        if (e.saving) {
          const m = machineFor(e.category || "mcp");
          m.last = e.saving_name || m.last;
          bubble(a, ICON[e.icon] || ICON.plug, e.saving_name + (e.label ? " · " + e.label : ""), 3);
          if (a.place === "machine" && a.machine === m && !a.path) {
            m.active = t + 2.6; a.busyUntil = t + 1.2;           // already there: keep working
          } else if (t - (a.lastTrip || -99) < 15 && a.place === "desk") {
            m.active = t + 2.2; beam(a, m); a.pose = "type";     // just went: use it from the desk
            a.desk.screen = t + 3; a.busyUntil = t + 1;
          } else {
            goTo(a, "machine", m); a.pose = "machine"; a.lastTrip = t; a.busyUntil = t + 3.2;
          }
          toolsUsed++;
          log(a, "⚙️ " + e.saving_name + (e.label ? " — " + e.label : ""), true);
        } else if (e.icon === "wait") {
          goTo(a, "coffee"); a.pose = "coffee"; bubble(a, ICON.wait, T.waiting, 2.5); a.busyUntil = t + 1.2;
        } else {
          if (a.place !== "desk") goTo(a, "desk");
          a.pose = "type"; a.desk.screen = t + 3;
          bubble(a, ICON[e.icon] || ICON.terminal, e.label || e.tool, 2.2);
          a.busyUntil = t + 0.9;
          if (e.icon === "bot") spawnBot(a);
          log(a, (ICON[e.icon] || "") + " " + (e.label || e.tool));
        }
        break;
      }
      case "done":
        a.celebrateUntil = t + 1.7; bubble(a, ICON.done, T.done, 2); a.busyUntil = t + 1.8;
        sparkle(a.x, a.y - 150, 0.7);
        a.afterCelebrate = "coffee";
        log(a, ICON.done + " " + T.done);
        break;
    }
  }

  function subagent(a, e) {
    const b = spawnBot(a);
    b.workUntil = now() + 1.6;
    b.label = e.label || e.tool;
  }

  function spawnBot(a) {
    let b = bots.get(a.id);
    if (!b) {
      b = { owner: a.id, x: a.desk.x - 70, y: a.desk.y - 175, born: now(), last: now(), workUntil: 0, alpha: 0 };
      bots.set(a.id, b);
      puff(b.x, b.y + 30);
      log(a, ICON.bot + " " + T.subagent);
    }
    b.last = now();
    return b;
  }

  // ---------------------------------------------------------------------------
  // the room's extras: piggy-bank safe, alarm lamp, office cat
  // ---------------------------------------------------------------------------
  const VAULT = { x: 1475, y: 885 };          // on the floor, in the free front-right corner
  const ALARM = { x: 655, y: 232 };           // on the brick wall, near the corner
  const ALARM_AT = 90;                        // % of the tightest plan limit (red on the tray icon)
  let limitPct = 0, vaultBump = 0;
  const hasVault = () => ART && !!(SPR.vault && SPR.vault.items);

  function drawVault(t) {
    // empty, a few coins, full: grows with what was saved while the page is open
    const f = savedTotal <= 0 ? 0 : savedTotal < 20000 ? 1 : 2;
    const bump = vaultBump > t ? 1 + Math.sin((vaultBump - t) * 14) * 0.06 * (vaultBump - t) : 1;
    ctx.fillStyle = "rgba(0,0,0,.16)";
    ctx.beginPath(); ctx.ellipse(VAULT.x, VAULT.y, 52, 11, 0, 0, Math.PI * 2); ctx.fill();
    drawSprite("vault", "items", f, VAULT.x, VAULT.y + 4, { scale: 0.5, squash: bump });
  }

  function drawAlarm(t) {
    const on = limitPct >= ALARM_AT;
    const blink = on && Math.floor(t * 2) % 2 === 0;
    if (blink) {
      const rg = ctx.createRadialGradient(ALARM.x + 4, ALARM.y - 48, 6, ALARM.x + 4, ALARM.y - 48, 150);
      rg.addColorStop(0, "rgba(255,60,50,.42)"); rg.addColorStop(1, "rgba(255,60,50,0)");
      ctx.fillStyle = rg; ctx.fillRect(ALARM.x - 150, ALARM.y - 200, 300, 300);
    }
    // the lamp itself never changes; when lit, the glow layer goes on top of it
    drawSprite("loft", "alarm_off", 0, ALARM.x, ALARM.y, { scale: 0.5 });
    if (blink) drawSprite("loft", "alarm_on", 0, ALARM.x, ALARM.y, { scale: 0.5 });
  }

  // the cat strolls between a few cozy spots, sits a while, naps in the sun and stretches after
  const CAT_SPOTS = [{ x: 330, y: 560 }, { x: 430, y: 520 }, { x: 980, y: 470 }, { x: 700, y: 690 },
    { x: 1250, y: 690 }, { x: 250, y: 610 }];
  const CAT_SUN = [0, 1, 5];                  // spots in the window's sunlight: where it naps
  const cat = { x: 430, y: 520, pose: "sleep", until: 12, path: null, spot: 1, dir: 1, frame: 0 };
  const hasCat = () => ART && !!(SPR.cat && SPR.cat.walk);

  function updateCat(dt, t) {
    if (!hasCat()) return;
    if (cat.path) {
      const dx = cat.path.x - cat.x, dy = cat.path.y - cat.y, d = Math.hypot(dx, dy), sp = 70 * dt;
      if (Math.abs(dx) > 1) cat.dir = dx > 0 ? 1 : -1;
      cat.frame += dt * 7;
      if (d <= sp) { cat.x = cat.path.x; cat.y = cat.path.y; cat.path = null; cat.pose = "sit"; cat.until = t + 5 + Math.random() * 6; }
      else { cat.x += (dx / d) * sp; cat.y += (dy / d) * sp; }
      return;
    }
    if (t < cat.until) return;
    if (cat.pose === "sleep") { cat.pose = "stretch"; cat.until = t + 1.8; return; }
    if (cat.pose === "sit" && CAT_SUN.includes(cat.spot) && Math.random() < 0.6) {
      cat.pose = "sleep"; cat.until = t + 25 + Math.random() * 35; return;
    }
    let next = cat.spot;
    while (next === cat.spot) next = Math.floor(Math.random() * CAT_SPOTS.length);
    cat.spot = next; cat.path = CAT_SPOTS[next]; cat.pose = "walk";
  }

  function drawCat(t) {
    const pose = cat.path ? "walk" : cat.pose;
    const breathe = pose === "sleep" ? 1 + Math.sin(t * 2) * 0.025 : 1;
    ctx.fillStyle = "rgba(0,0,0,.14)";
    ctx.beginPath(); ctx.ellipse(cat.x, cat.y, 26, 6, 0, 0, Math.PI * 2); ctx.fill();
    // the drawings look down-right: mirror when it heads left
    drawSprite("cat", pose, pose === "walk" ? cat.frame : 0, cat.x, cat.y + 3, { scale: 0.62, mirror: cat.dir < 0, squash: breathe });
  }

  // tokens and savings become coins and floating numbers
  function coins(x, y, n, toX, toY, color) {
    for (let i = 0; i < n; i++) {
      fx.push({ type: "coin", x: x + (Math.random() - 0.5) * 30, y, vx: (Math.random() - 0.5) * 120, vy: -160 - Math.random() * 120,
        born: now() + i * 0.06, life: 1.4, toX, toY, color });
    }
  }
  function beam(a, m) { fx.push({ type: "beam", x: a.desk.x + 145, y: a.desk.y - 150, toX: m.x, toY: m.y - 110, color: CAT_COLOR[m.cat], born: now(), life: 1.1 }); }
  function floatText(x, y, text, color) { fx.push({ type: "text", x, y, text, color, born: now(), life: 1.6 }); }
  function puff(x, y) { fx.push({ type: "puff", x, y, born: now(), life: SPR.fx && SPR.fx.puff ? 0.8 : 0.6 }); }
  function sparkle(x, y, scale, delay = 0) {
    if (SPR.fx && SPR.fx.sparkle) fx.push({ type: "sparkle", x, y, scale, born: now() + delay, life: 0.7 });
  }

  // ---------------------------------------------------------------------------
  // feed + HUD
  // ---------------------------------------------------------------------------
  let tokensTotal = 0, savedTotal = 0, toolsUsed = 0;
  function log(a, text, saving = false) {
    const li = document.createElement("li");
    if (saving) li.className = "saving";
    const who = document.createElement("span");
    who.className = "who"; who.textContent = a.name; who.style.color = a.agent === "codex" ? "var(--codex)" : "var(--claude)";
    const what = document.createElement("span");
    what.className = "what"; what.textContent = text;
    li.append(who, what);
    const ol = $("feed-list");
    ol.prepend(li);
    while (ol.children.length > 9) ol.lastChild.remove();
  }
  function hud() {
    $("h-agents").textContent = [...agents.values()].filter((a) => !a.leaving).length;
    $("h-tokens").textContent = fmt(tokensTotal);
    $("h-saved").textContent = fmt(savedTotal);
    $("h-tools").textContent = toolsUsed;
    $("empty").hidden = agents.size > 0 || !started;
  }

  // ---------------------------------------------------------------------------
  // data in: apply one /api/live answer
  // ---------------------------------------------------------------------------
  let seq = 0, started = false;
  // One person per desk. With more open sessions than desks, a person works on several projects
  // at once (one Nina on "sonora · maestro-work") instead of a second copy of her: the label lists
  // every project, everything any of them does shows on her, and she only naps when all are idle.
  const owner = new Map();   // session id -> id of the person working on it
  const agentFor = (sid) => agents.get(owner.get(sid));

  function apply(r, first) {
    const t = now();
    const ids = new Set(r.sessions.map((s) => s.id));
    for (const [sid, aid] of owner) {
      if (ids.has(sid)) continue;
      owner.delete(sid);
      const a = agents.get(aid);
      if (!a) continue;
      a.sessions.delete(sid);
      if (!a.sessions.size && !a.leaving) { a.leaving = true; a.queue = []; goTo(a, "door"); }
    }
    // newest first, so after a restart the busiest sessions get their own person
    const recent = r.sessions.slice().sort((p, q) => (q.last || 0) - (p.last || 0));
    for (const s of recent) {
      let a = agentFor(s.id);
      const idle = r.now - (s.last || 0) > 240;
      if (!a) {
        const inside = [...agents.values()].filter((o) => !o.leaving);
        if (inside.length < DESKS.length) {
          a = newAgent(s, !first);
          if (first && idle) { a.place = "nap"; const p = spotFor(a, "nap"); a.x = p.x; a.y = p.y; a.pose = "sleep"; }
        } else {
          // the person with the fewest projects takes it on (same agent kind first)
          a = inside.reduce((p, o) => {
            const k = (x) => x.sessions.size * 2 + (x.agent === s.agent ? 0 : 1);
            return k(o) < k(p) ? o : p;
          });
          a.sessions.set(s.id, s.project || "");
          if (first && !idle && a.place === "nap") { a.place = "desk"; a.x = a.desk.x; a.y = a.desk.y; a.pose = "think"; a.slot = null; }
        }
        owner.set(s.id, a.id);
      }
      a.sessions.set(s.id, s.project || a.sessions.get(s.id) || "");
    }
    for (const a of agents.values()) {
      if (!a.leaving) a.project = [...new Set(a.sessions.values())].filter(Boolean).join(" · ");
    }
    tokensTotal = r.sessions.reduce((n, s) => n + (s.tokens || 0), 0);
    limitPct = r.limit || 0;
    if (!first) {
      for (const e of r.events) {
        const a = agentFor(e.session);
        if (!a) continue;
        if (e.kind === "tokens") {
          if (e.sub) continue;
          coins(a.x, a.y - 150, Math.min(6, 1 + Math.floor(Math.log10(Math.max(10, e.total)) - 1)), 330, 30, "#e8b33a");
          if (e.output > 0) floatText(a.x + 70, a.y - 120, "+" + fmt(e.total), "#b07a10");
          continue;
        }
        if (e.kind === "saved") {
          savedTotal += e.saved || 0;
          const m = machineFor(e.category);
          m.active = t + 2.2; m.last = e.saving_name;
          if (hasVault()) {   // the saved tokens drop into the piggy-bank safe
            coins(m.x, m.y - 150, 5, VAULT.x, VAULT.y - 60, "#3fbf7f");
            sparkle(VAULT.x, VAULT.y - 50, 0.55, 1.2);
            vaultBump = t + 1.6;
          } else coins(m.x, m.y - 150, 5, 520, 30, "#3fbf7f");
          floatText(m.x, m.y - 190, "−" + fmt(e.saved || 0), "#1f8a5b");
          log(a, "🪙 " + e.saving_name + " " + T.saving + " " + fmt(e.saved || 0) + " tokens", true);
          continue;
        }
        if (e.kind === "say") { handle(a, e); continue; }
        a.queue.push(e);
        if (a.queue.length > 8) {
          const i = a.queue.findIndex((x) => !x.saving && x.kind !== "prompt" && x.kind !== "done");
          a.queue.splice(i >= 0 ? i : 0, 1);
        }
      }
    }
    seq = r.seq;
    started = true;
  }

  // ---------------------------------------------------------------------------
  // simulation (demo mode and ?demo=1)
  // ---------------------------------------------------------------------------
  function simulator() {
    const sessions = [
      { id: "demo-a", agent: "claude", project: "token-economy", tokens: 1800000, last: 0, start: 0 },
      { id: "demo-b", agent: "codex", project: "loja-online", tokens: 640000, last: 0, start: 0 },
      { id: "demo-c", agent: "claude", project: "app-mobile", tokens: 220000, last: 0, start: 0 },
    ];
    let n = 0, live = 2;
    const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];
    const desk = [
      () => ({ kind: "tool", tool: "Read", icon: "read", label: pick(["server.py", "app.js", "README.md", "collector.py"]) }),
      () => ({ kind: "tool", tool: "Edit", icon: "edit", label: pick(["office.js", "live.py", "style.css"]) }),
      () => ({ kind: "tool", tool: "Bash", icon: "terminal", label: pick(["git status", "npm test", "pytest -q"]) }),
    ];
    const tools = [
      ...desk, ...desk,
      () => ({ kind: "tool", tool: "Read", icon: "read", label: pick(["server.py", "app.js", "README.md", "collector.py"]) }),
      () => ({ kind: "tool", tool: "Edit", icon: "edit", label: pick(["office.js", "live.py", "style.css"]) }),
      () => ({ kind: "tool", tool: "Bash", icon: "terminal", label: pick(["git status", "npm test", "pytest -q", "git diff"]) }),
      () => ({ kind: "tool", tool: "Grep", icon: "search", label: pick(["def collect", "TODO", "session_id"]) }),
      () => ({ kind: "tool", tool: "WebSearch", icon: "web", label: "isometric sprite tips" }),
      () => ({ kind: "tool", tool: "Bash", icon: "terminal", label: "rtk git log", saving: "rtk", saving_name: "RTK", category: "command_output" }),
      () => ({ kind: "tool", tool: "Bash", icon: "terminal", label: "graphify query \"auth\"", saving: "graphify", saving_name: "Graphify", category: "code_index" }),
      () => ({ kind: "tool", tool: "mcp__context-mode__ctx_execute", icon: "plug", label: "ctx_execute", saving: "context-mode", saving_name: "Context Mode", category: "command_output" }),
      () => ({ kind: "tool", tool: "mcp__claude-mem__search", icon: "plug", label: "search", saving: "claude-mem", saving_name: "claude-mem", category: "memory" }),
      () => ({ kind: "think" }),
      () => ({ kind: "say", label: pick(["Achei o problema no parser.", "Rodando os testes agora.", "Pronto, ajustei o layout."]) }),
      () => ({ kind: "tool", tool: "Agent", icon: "bot", label: "explorar o código" }),
      () => ({ kind: "tool", tool: "Bash", icon: "wait", label: "sleep 30" }),
    ];
    function step() {
      const ts = Date.now() / 1000;
      const evs = [];
      const active = sessions.slice(0, live);
      if (Math.random() < 0.02) live = live === 3 ? 2 : 3;
      for (const s of active) {
        if (Math.random() < 0.55) {
          const r = Math.random();
          let e;
          if (r < 0.04) e = { kind: "prompt", label: pick(["Cria a aba do escritório", "Corrige o teste que quebrou", "Revisa o README"]) };
          else if (r < 0.09) e = { kind: "done" };
          else e = pick(tools)();
          evs.push({ ...e, ts, session: s.id, agent: s.agent, sub: e.tool === "Agent" ? false : Math.random() < 0.08, seq: ++n });
          const tot = 2000 + Math.floor(Math.random() * 40000);
          s.tokens += tot;
          evs.push({ kind: "tokens", ts, session: s.id, agent: s.agent, total: tot, output: 300, seq: ++n });
          if (e.saving === "rtk") evs.push({ kind: "saved", ts, session: s.id, agent: s.agent, saving: "rtk", saving_name: "RTK", category: "command_output", saved: 800 + Math.floor(Math.random() * 6000), seq: ++n });
        }
        s.last = ts;
      }
      // a third of the time a plan limit is almost used up, so the alarm lamp shows in the demo
      const limit = Math.floor(ts / 40) % 3 === 0 ? 93 : 45;
      return { seq: n, now: ts, sessions: active.map((s) => ({ ...s })), events: evs, limit };
    }
    return step;
  }

  // ---------------------------------------------------------------------------
  // update + draw
  // ---------------------------------------------------------------------------
  // Body collider: each person standing on the floor is an ellipse at the feet (wide, flat, like
  // the floor in this view). Two that overlap slide apart sideways until they stand side by side.
  // Seated agents stay in their chair and only push the others; walkers pass by and are not pushed.
  const BODY = { rx: 34, ry: 14 };
  function separate(dt) {
    const list = [...agents.values()].filter((a) => a.alpha > 0.3);
    for (let i = 0; i < list.length; i++) {
      for (let j = i + 1; j < list.length; j++) {
        const a = list[i], b = list[j];
        const dx = (b.x - a.x) / (2 * BODY.rx), dy = (b.y - a.y) / (2 * BODY.ry);
        const d = Math.hypot(dx, dy);
        if (d >= 1 || a.path || b.path) continue;
        const fixedA = a.place === "desk" || (a.place === "nap" && napsAtDesk(a));
        const fixedB = b.place === "desk" || (b.place === "nap" && napsAtDesk(b));
        if (fixedA && fixedB) continue;
        // push mostly sideways; exactly on top of each other: split by id so it is stable
        const ux = d > 0.01 ? dx / d : (a.id < b.id ? 1 : -1), uy = d > 0.01 ? dy / d : 0;
        const push = Math.min(1 - d, 0.5) * 2 * BODY.rx * Math.min(1, dt * 6);
        const share = fixedA || fixedB ? 1 : 0.5;
        if (!fixedA) { a.x -= ux * push * share; a.y -= uy * push * share * (BODY.ry / BODY.rx); }
        if (!fixedB) { b.x += ux * push * share; b.y += uy * push * share * (BODY.ry / BODY.rx); }
      }
    }
  }

  function update(dt, t) {
    for (const [id, a] of agents) {
      // next queued event when the current one had its moment
      if (!a.path && t >= a.busyUntil && a.queue.length) handle(a, a.queue.shift());
      // after celebrating: wait for the person at the coffee corner
      if (a.afterCelebrate && t > a.celebrateUntil) { goTo(a, a.afterCelebrate); a.pose = "coffee"; a.afterCelebrate = null; }
      // nothing for a while: back to the desk, then a nap
      if (!a.leaving && !a.path && !a.queue.length && t > a.busyUntil) {
        if (a.place === "machine" && t - a.last > 2.5) { goTo(a, "desk"); a.pose = "type"; }
        if (t - a.last > 240 && a.place !== "nap") { goTo(a, "nap"); a.pose = "sleep"; }
      }
      if (a.path) {
        const p = a.path[0];
        const dx = p.x - a.x, dy = p.y - a.y, d = Math.hypot(dx, dy);
        const sp = 210 * dt;
        if (d <= sp) { a.x = p.x; a.y = p.y; a.path.shift(); if (!a.path.length) a.path = null; }
        else { a.x += (dx / d) * sp; a.y += (dy / d) * sp; a.dir = { dx, dy }; }
        a.frame += dt * 8.5;
        if (!a.path && a.place === "machine" && a.machine) a.machine.active = t + 2.6;
        if (!a.path && a.leaving) { puff(a.x, a.y - 60); doorOpenUntil = t + 1; agents.delete(id); if (a.desk.owner === id) a.desk.owner = null; bots.delete(id); }
      } else {
        a.frame += dt * (a.pose === "type" ? 5 : 1);
      }
      if (!a.path && a.place === "desk" && (a.pose === "type" || a.pose === "think")) a.desk.screen = Math.max(a.desk.screen, t + 0.5);
      a.alpha = Math.min(1, a.alpha + dt * 2.5);
      if (a.bubble && a.bubble.until < t) a.bubble = null;
    }
    separate(dt);
    for (const [id, b] of bots) {
      const a = agents.get(id);
      b.alpha = Math.min(1, b.alpha + dt * 2);
      if (!a || t - b.last > 40) { puff(b.x, b.y + 30); bots.delete(id); continue; }
      b.x += ((a.desk.x - 70) - b.x) * dt * 2;
      b.y += ((a.desk.y - 175) - b.y) * dt * 2;
    }
    updateCat(dt, t);
    for (let i = fx.length - 1; i >= 0; i--) if (t - fx[i].born > fx[i].life) fx.splice(i, 1);
  }

  // Napping in the chair: the legs stay hidden behind the desk like when typing, but the head and
  // arms rest on the desk top, so that part is drawn again over the desk (over its lamp or plant).
  const NAP_CUT = -55;   // the desk top, relative to the seat
  const deskNap = (a) => ART && a.place === "nap" && !a.path && a.pose === "sleep" && napsAtDesk(a);
  function drawNapTop(a, t) {
    ctx.save();
    ctx.beginPath(); ctx.rect(a.x - 220, a.y - 420, 440, 420 + NAP_CUT); ctx.clip();
    drawAgent(a, t, true);
    ctx.restore();
  }

  function drawAgent(a, t, top = false) {
    let pose = a.pose, mirror = false, y = a.y, squash = 1;
    const chars = !!a.char;
    if (a.path) {
      const { dx, dy } = a.dir || { dx: 1, dy: 0 };
      pose = dy < -Math.abs(dx) * 0.35 ? "walk_back" : "walk_front";
      // each drawing says which way it looks (manifest "faces"); mirror when walking the other way
      const s = SPR[a.char] && SPR[a.char][pose];
      const faces = (s && s.faces) || (pose === "walk_back" ? "left" : "right");
      mirror = faces !== (dx > 0 ? "right" : "left");
      y -= Math.abs(Math.sin(a.frame * Math.PI / 2)) * 3;
    } else if (a.celebrateUntil > t) {
      pose = "celebrate";
      y -= Math.abs(Math.sin((t - a.celebrateUntil) * 7)) * 26;
    } else if (pose === "machine") {
      // faces the machine on its left
    } else {
      squash = 1 + Math.sin(t * 2.2 + a.seed) * 0.012;
      if (pose === "think" && a.place !== "desk") pose = "idle";
      if (pose === "type" && a.place !== "desk") pose = "idle";
    }
    if (!(SPR[a.char] && SPR[a.char][pose])) pose = SPR[a.char] && SPR[a.char].idle ? "idle" : pose;
    // shadow
    ctx.fillStyle = "rgba(40,20,10,.22)";
    ctx.beginPath(); ctx.ellipse(a.x, a.y + 1, 38, 9, 0, 0, Math.PI * 2); ctx.fill();
    let frame = a.frame;
    if (pose === "type") frame = Math.sin(t * 9 + a.seed) > 0.2 ? 1 : 0;
    if (pose === "machine") frame = Math.floor(t * 3) % 2;
    const ok = chars && drawSprite(a.char, pose, frame, a.x, y, { mirror, alpha: a.alpha, squash });
    if (top) return;
    if (!ok) drawStickFigure(a, y);
    if (a.place === "nap" && !a.path) {
      ctx.font = "600 22px 'Segoe UI', system-ui"; ctx.fillStyle = "rgba(60,60,110,.8)";
      for (let i = 0; i < 3; i++) {
        const k = ((t * 0.6 + i / 3) % 1);
        ctx.globalAlpha = 1 - k; ctx.fillText("z", a.x + 30 + k * 30, a.y - 170 - k * 50); ctx.globalAlpha = 1;
      }
    }
  }

  function drawStickFigure(a, y) {
    ctx.fillStyle = a.agent === "codex" ? "#2a9d9a" : "#e07a4f";
    roundRect(ctx, a.x - 24, y - 120, 48, 90, 18); ctx.fill();
    ctx.fillStyle = "#8a5a3c"; ctx.beginPath(); ctx.arc(a.x, y - 140, 24, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#3a3d44"; ctx.fillRect(a.x - 18, y - 34, 14, 34); ctx.fillRect(a.x + 4, y - 34, 14, 34);
  }

  function drawLabel(a, t) {
    const top = labelTop(a);
    const team = a.agent === "codex" ? "#2a9d9a" : "#e07a4f";
    ctx.font = "700 14px 'Segoe UI', system-ui, sans-serif";
    const name = a.name;
    const sub = a.project ? a.project : "";
    ctx.font = "700 14px 'Segoe UI', system-ui, sans-serif"; const w1 = ctx.measureText(name).width;
    ctx.font = "500 11px 'Segoe UI', system-ui, sans-serif"; const w2 = ctx.measureText(sub).width;
    const w = Math.max(w1, w2) + 30;
    ctx.globalAlpha = a.alpha;
    ctx.fillStyle = "rgba(255,250,242,.93)"; roundRect(ctx, a.x - w / 2, top - 40, w, sub ? 36 : 24, 10); ctx.fill();
    ctx.fillStyle = team; ctx.beginPath(); ctx.arc(a.x - w / 2 + 12, top - 28, 5, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#2b2420"; ctx.textAlign = "left"; ctx.textBaseline = "middle";
    ctx.font = "700 14px 'Segoe UI', system-ui, sans-serif"; ctx.fillText(name, a.x - w / 2 + 22, top - 28);
    if (sub) { ctx.font = "500 11px 'Segoe UI', system-ui, sans-serif"; ctx.fillStyle = "#7a6c62"; ctx.fillText(sub, a.x - w / 2 + 22, top - 13); }
    ctx.globalAlpha = 1;
  }
  function labelTop(a) {
    const seated = !a.path && (a.pose === "type" || a.pose === "think") && a.place === "desk" && a.celebrateUntil < now();
    return a.y - (seated ? 158 : 184);
  }

  function drawBubble(a, t) {
    const b = a.bubble;
    if (!b) return;
    const life = Math.min(1, (t - b.born) * 6, (b.until - t) * 4);
    const top = labelTop(a) - 48;
    ctx.save();
    ctx.globalAlpha = Math.max(0, life);
    ctx.font = "500 14px 'Segoe UI', system-ui, sans-serif";
    let text = b.text || "";
    if (text.length > 42) text = text.slice(0, 41) + "…";
    const cell = SPR.icons && SPR.icons.items ? ICON_CELL[b.icon] : undefined;
    const pic = cell !== undefined;            // drawn icon instead of the emoji
    const icon = b.icon && !pic ? b.icon + " " : "";
    const pad = pic ? 26 : 0;
    const w = Math.min(380, ctx.measureText(icon + text).width + 26 + pad);
    const x = Math.min(W - w - 10, Math.max(10, a.x - w / 2)), y = top - 30 + (1 - life) * 6;
    ctx.fillStyle = "#fff"; ctx.shadowColor = "rgba(0,0,0,.18)"; ctx.shadowBlur = 8; ctx.shadowOffsetY = 2;
    roundRect(ctx, x, y, w, 32, 14); ctx.fill();
    ctx.beginPath(); ctx.moveTo(a.x - 8, y + 31); ctx.lineTo(a.x, y + 42); ctx.lineTo(a.x + 8, y + 31); ctx.fill();
    ctx.shadowColor = "transparent";
    ctx.fillStyle = "#2b2420"; ctx.textAlign = "left"; ctx.textBaseline = "middle";
    ctx.fillText(icon + text, x + 13 + pad, y + 16.5, w - 22 - pad);
    if (pic) {
      const s = SPR.icons.items, k = 24 / s.h;
      ctx.drawImage(s.img, cell * s.w, 0, s.w, s.h, x + 9, y + 4, s.w * k, 24);
    }
    ctx.restore();
  }

  function drawBot(b, t) {
    const y = b.y + Math.sin(t * 3 + b.born) * 6;
    const working = b.workUntil > t;
    if (drawSprite("bot", working ? "work" : "float", Math.floor(t * 4), b.x, y + 40, { alpha: b.alpha, scale: 0.5 })) return;
    ctx.save(); ctx.globalAlpha = b.alpha;
    ctx.fillStyle = "rgba(0,0,0,.12)"; ctx.beginPath(); ctx.ellipse(b.x, b.y + 150, 16, 5, 0, 0, Math.PI * 2); ctx.fill();
    const g = ctx.createRadialGradient(b.x, y + 34, 2, b.x, y + 34, 18);
    g.addColorStop(0, "rgba(120,230,255,.9)"); g.addColorStop(1, "rgba(120,230,255,0)");
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(b.x, y + 34, 18, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#f4f1ea"; roundRect(ctx, b.x - 22, y - 22, 44, 50, 18); ctx.fill();
    ctx.fillStyle = "#2a9d9a"; roundRect(ctx, b.x - 22, y + 10, 44, 10, 4); ctx.fill();
    ctx.fillStyle = "#1f2530"; roundRect(ctx, b.x - 16, y - 14, 32, 18, 8); ctx.fill();
    ctx.fillStyle = "#7fe7ff";
    if (working) { ctx.fillRect(b.x - 10, y - 6, 7, 2); ctx.fillRect(b.x + 3, y - 6, 7, 2); }
    else { ctx.beginPath(); ctx.arc(b.x - 6, y - 5, 3, 0, Math.PI * 2); ctx.arc(b.x + 6, y - 5, 3, 0, Math.PI * 2); ctx.fill(); }
    if (working) {
      ctx.fillStyle = "#ffd36a";
      for (let i = 0; i < 3; i++) { const k = (t * 2 + i / 3) % 1; ctx.globalAlpha = (1 - k) * b.alpha; ctx.beginPath(); ctx.arc(b.x + 26 + k * 14, y - 10 - k * 20, 2.5, 0, Math.PI * 2); ctx.fill(); }
    }
    ctx.restore();
  }

  function drawFx(t) {
    for (const p of fx) {
      const k = (t - p.born) / p.life;
      if (k < 0) continue;
      if (p.type === "coin") {
        // up with a little arc, then fly to the HUD counter
        let x, y;
        if (k < 0.45) { const s = k / 0.45; x = p.x + p.vx * s * 0.4; y = p.y + p.vy * s * 0.4 + 200 * (s * 0.4) ** 2; }
        else { const s = (k - 0.45) / 0.55, e = s * s; const sx = p.x + p.vx * 0.4, sy = p.y + p.vy * 0.4 + 200 * 0.16; x = sx + (p.toX - sx) * e; y = sy + (p.toY - sy) * e; }
        const r = 8 * (1 - Math.max(0, k - 0.8) * 3);
        if (drawSprite("tokens", "items", 1, x, y + r, { scale: r / 30 })) continue;
        ctx.fillStyle = p.color; ctx.beginPath(); ctx.ellipse(x, y, r * Math.abs(Math.cos(t * 8 + p.vx)), r, 0, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = "rgba(255,255,255,.6)"; ctx.beginPath(); ctx.arc(x - r * 0.25, y - r * 0.3, r * 0.3, 0, Math.PI * 2); ctx.fill();
      } else if (p.type === "text") {
        ctx.globalAlpha = 1 - k; ctx.font = "800 20px 'Segoe UI', system-ui"; ctx.textAlign = "center";
        ctx.fillStyle = "#fff"; ctx.fillText(p.text, p.x + 1, p.y - k * 50 + 1);
        ctx.fillStyle = p.color; ctx.fillText(p.text, p.x, p.y - k * 50); ctx.globalAlpha = 1;
      } else if (p.type === "beam") {
        // a dotted arc of light from the desk monitor to the machine
        for (let i = 0; i < 14; i++) {
          const s = i / 13, ph = (s - k * 1.6);
          if (ph < -0.3 || ph > 0.3) continue;
          const x = p.x + (p.toX - p.x) * s, y = p.y + (p.toY - p.y) * s - Math.sin(s * Math.PI) * 90;
          ctx.globalAlpha = 1 - Math.abs(ph) / 0.3;
          ctx.fillStyle = p.color; ctx.beginPath(); ctx.arc(x, y, 5, 0, Math.PI * 2); ctx.fill();
          ctx.fillStyle = "#fff"; ctx.beginPath(); ctx.arc(x, y, 2, 0, Math.PI * 2); ctx.fill();
        }
        ctx.globalAlpha = 1;
      } else if (p.type === "sparkle") {
        drawSprite("fx", "sparkle", Math.min(3, Math.floor(k * 4)), p.x, p.y + 40, { scale: p.scale || 0.5 });
      } else if (p.type === "puff" && SPR.fx && SPR.fx.puff) {
        drawSprite("fx", "puff", Math.min(3, Math.floor(k * 4)), p.x, p.y + 45, { scale: 0.55, alpha: 1 - Math.max(0, k - 0.75) * 4 });
      } else if (p.type === "puff") {
        ctx.globalAlpha = 1 - k; ctx.fillStyle = "#e9eef0";
        for (let i = 0; i < 6; i++) { const ang = i * 1.05; ctx.beginPath(); ctx.arc(p.x + Math.cos(ang) * k * 40, p.y + Math.sin(ang) * k * 24, 14 * (1 - k * 0.5), 0, Math.PI * 2); ctx.fill(); }
        ctx.globalAlpha = 1;
      }
    }
  }

  function frame(tms) {
    const t = tms / 1000;
    // big gaps happen when the tab is in the background: catch up instead of crawling
    const dt = Math.min(0.5, t - (frame.prev || t));
    frame.prev = t;
    update(dt, t);
    if (new Date().getHours() !== bgHour) buildBackground();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.drawImage(bg, 0, 0);
    ctx.setTransform(view * dpr, 0, 0, view * dpr, 0, 0);
    drawDoor(t);
    // everything that stands on the floor, back to front
    const items = [];
    for (const m of MACHINES) items.push([m.y, () => drawMachine(m, t)]);
    for (const d of DESKS) {
      items.push([d.y - 2, () => drawChair(d.x, d.y)]);
      items.push([d.y + (ART ? DESK_OFF.y : 3), () => drawDesk(d, t)]);
    }
    if (ART) {
      items.push([405, () => drawCoffeeCounter(700, 405)]);
      items.push([640, () => drawSofa(330, 640)]);
      items.push([752, () => drawSprite("loft", "whiteboard", 0, 1430, 752, { scale: 0.6 })]);
      if (SPR.loft && SPR.loft.bookshelf) {
        items.push([440, () => drawSprite("loft", "bookshelf", 0, 560, 440, { scale: 0.5 })]);
        items.push([392, () => drawPlant(805, 392, 1)]);   // the small plant moves to the corner
      } else items.push([430, () => drawPlant(555, 430, 1)]);
      items.push([640, () => drawPlant(1555, 640, 1.3)]);
      items.push([726, () => drawPlant(70, 726, 1.2)]);
      if (SPR.loft && SPR.loft.alarm_off) items.push([ALARM.y, () => drawAlarm(t)]);
      if (hasVault()) items.push([VAULT.y, () => drawVault(t)]);
      if (hasCat()) items.push([cat.y, () => drawCat(t)]);
    } else {
      items.push([760, () => drawSofa(1450, 760)]);
      items.push([660, () => drawPlant(1560, 660, 1.3)]);
      items.push([372, () => drawPlant(800, 372, 1)]);
      items.push([880, () => drawPlant(120, 880, 1.2)]);
    }
    for (const a of agents.values()) {
      items.push([a.y, () => drawAgent(a, t)]);
      if (deskNap(a)) items.push([a.y + DESK_OFF.y + 1, () => drawNapTop(a, t)]);
    }
    for (const b of bots.values()) items.push([b.y + 150, () => drawBot(b, t)]);
    items.sort((p, q) => p[0] - q[0]);
    for (const [, draw] of items) draw();
    for (const m of MACHINES) drawMachineLabel(m, t);
    for (const a of agents.values()) drawLabel(a, t);
    for (const a of agents.values()) drawBubble(a, t);
    drawFx(t);
    hud();
    requestAnimationFrame(frame);
  }

  function resize() {
    // fit 16:9 inside the window, whichever side runs out first
    const st = $("stage").getBoundingClientRect();
    const w = Math.min(st.width - 16, (st.height - 16) * (W / H));
    dpr = window.devicePixelRatio || 1;
    view = w / W;
    cv.style.width = w + "px";
    cv.style.height = w * (H / W) + "px";
    cv.width = Math.round(w * dpr);
    cv.height = Math.round(w * (H / W) * dpr);
    buildBackground();
  }

  // ---------------------------------------------------------------------------
  // start
  // ---------------------------------------------------------------------------
  async function start() {
    try {
      const cfg = await (await fetch("/api/config")).json();
      const lang = (cfg.language || "pt").slice(0, 2);
      T = TEXT[lang] || TEXT.pt;
    } catch { /* keep Portuguese */ }
    applyText();
    await loadSprites();
    if (SPR.loft && SPR.loft.bg_day) useArtLayout();
    resize();
    window.addEventListener("resize", resize);
    requestAnimationFrame(frame);

    let sim = new URLSearchParams(location.search).has("demo") ? simulator() : null;
    let first = true;
    async function tick() {
      try {
        let r;
        if (sim) r = sim();
        else {
          r = await (await fetch("/api/live?after=" + seq, { cache: "no-store" })).json();
          if (r.demo) { sim = simulator(); r = sim(); }
        }
        $("h-mode").textContent = sim ? T.demo : "";
        apply(r, first);
        first = false;
      } catch {
        $("h-mode").textContent = T.offline;
      }
      setTimeout(tick, sim ? 1500 : 2000);
    }
    tick();
  }
  start();
})();
