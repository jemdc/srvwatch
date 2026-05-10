/**
 * SRVWatch — Main application bootstrap.
 *
 * Responsibilities:
 *   - Fetch server list on load, render sidebar tabs
 *   - Poll selected server's /live endpoint every LIVE_INTERVAL ms
 *   - Fetch history when range button is clicked or server changes
 *   - Wire up all UI interactions
 */

import { api } from "./api.js";
import {
  createGauge, updateGauge,
  createLineChart, updateLineChart,
  createPowerChart,
  createSparkline, updateSparkline,
  destroyAll,
} from "./charts.js";

// ── Constants ─────────────────────────────────────────────────────────────────
const LIVE_INTERVAL    = 5_000;   // ms between /live polls
const SERVER_INTERVAL  = 30_000;  // ms between server list refreshes
const SPARKLINE_MAX    = 20;      // data points kept in sparkline buffer

// ── State ─────────────────────────────────────────────────────────────────────
let state = {
  servers:        [],
  selectedId:     null,
  selectedRange:  "1h",
  selectedGpu:    0,       // index of GPU tab selected
  liveTimer:      null,
  serverTimer:    null,
  sparkBuffers:   {},      // { serverId: { cpu: [], mem: [], gpu: [] } }
};

// ── DOM helpers ───────────────────────────────────────────────────────────────
const $  = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

function el(tag, cls, html = "") {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html) e.innerHTML = html;
  return e;
}

// ── Clock ─────────────────────────────────────────────────────────────────────
function startClock() {
  const el = $("#live-clock");
  if (!el) return;
  const tick = () => {
    el.textContent = new Date().toLocaleTimeString("en-GB", { hour12: false });
  };
  tick();
  setInterval(tick, 1000);
}

// ── Format helpers ────────────────────────────────────────────────────────────
const fmt = {
  pct:  (v) => v == null ? "—" : v.toFixed(1) + "%",
  mb:   (v) => v == null ? "—" : (v >= 1024 ? (v / 1024).toFixed(1) + " GB" : v.toFixed(0) + " MB"),
  w:    (v) => v == null ? "—" : v.toFixed(0) + " W",
  temp: (v) => v == null ? "—" : v.toFixed(0) + "°C",
  freq: (v) => v == null ? "—" : v.toFixed(0) + " MHz",
};

// ── Server list ───────────────────────────────────────────────────────────────
async function loadServers() {
  try {
    state.servers = await api.servers();
    renderServerTabs();
    renderServerCards();

    // Auto-select first server
    if (!state.selectedId && state.servers.length > 0) {
      selectServer(state.servers[0].id);
    }
  } catch (err) {
    console.error("Failed to load servers:", err);
    showBanner("error", "Could not reach central server.");
  }
}

function renderServerTabs() {
  const container = $("#server-tabs");
  if (!container) return;
  container.innerHTML = "";

  state.servers.forEach((srv) => {
    const tab = el("button", "srv-tab" + (srv.id === state.selectedId ? " active" : ""));
    tab.dataset.id = srv.id;

    const dot = el("span", "status-dot" + (srv.online === true ? " online" : srv.online === false ? " offline" : " unknown"));
    tab.appendChild(dot);
    tab.appendChild(document.createTextNode(srv.label || srv.id));
    tab.addEventListener("click", () => selectServer(srv.id));
    container.appendChild(tab);
  });

  const count = el("span", "srv-tab-count");
  const online = state.servers.filter((s) => s.online).length;
  count.textContent = `${online} / ${state.servers.length} online`;
  container.appendChild(count);
}

function renderServerCards() {
  const container = $("#server-cards");
  if (!container) return;
  container.innerHTML = "";

  state.servers.forEach((srv) => {
    const card = el("div", "srv-card" + (srv.id === state.selectedId ? " active" : ""));
    card.dataset.id = srv.id;

    const vendors = (srv.gpu_vendors || []).map((v) =>
      `<span class="gpu-badge gpu-badge--${v}">${v.toUpperCase()}</span>`
    ).join("");

    card.innerHTML = `
      <div class="srv-card__header">
        <span class="status-dot ${srv.online === true ? "online" : srv.online === false ? "offline" : "unknown"}"></span>
        <span class="srv-card__name">${srv.label || srv.id}</span>
        <span class="srv-card__ip">${srv.host}</span>
      </div>
      <div class="srv-card__gpu-row">${vendors}</div>
      <div class="srv-card__sparks">
        <div class="spark-row">
          <span class="spark-label">CPU</span>
          <div id="spark-cpu-${srv.id}" class="spark-chart"></div>
        </div>
        <div class="spark-row">
          <span class="spark-label">MEM</span>
          <div id="spark-mem-${srv.id}" class="spark-chart"></div>
        </div>
        ${srv.gpu_count > 0 ? `
        <div class="spark-row">
          <span class="spark-label">GPU</span>
          <div id="spark-gpu-${srv.id}" class="spark-chart"></div>
        </div>` : ""}
      </div>
    `;
    card.addEventListener("click", () => selectServer(srv.id));
    container.appendChild(card);
  });

  // Init sparklines (after DOM inserted)
  requestAnimationFrame(() => {
    state.servers.forEach((srv) => {
      createSparkline(`spark-cpu-${srv.id}`, "#58a6ff");
      createSparkline(`spark-mem-${srv.id}`, "#3fb950");
      if (srv.gpu_count > 0) createSparkline(`spark-gpu-${srv.id}`, "#d29922");
    });
  });
}

// ── Server selection ──────────────────────────────────────────────────────────
function selectServer(id) {
  state.selectedId = id;
  state.selectedGpu = 0;

  // Update active state in tabs and cards
  $$(".srv-tab").forEach((t) => t.classList.toggle("active", t.dataset.id === id));
  $$(".srv-card").forEach((c) => c.classList.toggle("active", c.dataset.id === id));

  // Reset and re-init detail panel
  renderDetailPanel();
  startLivePolling();
  loadHistory();
}

// ── Detail panel ──────────────────────────────────────────────────────────────
function renderDetailPanel() {
  const panel = $("#detail-panel");
  if (!panel) return;

  const srv = state.servers.find((s) => s.id === state.selectedId);
  if (!srv) return;

  panel.innerHTML = `
    <div class="detail-header">
      <div class="detail-title">
        <span class="status-dot ${srv.online ? "online" : "offline"}"></span>
        <h2>${srv.label || srv.id}</h2>
        <code class="detail-host">${srv.host}:${srv.port}</code>
      </div>
      <div class="range-bar" id="range-bar"></div>
    </div>

    <div class="gauges-row">
      <div class="gauge-card" style="--accent:#58a6ff">
        <div class="gauge-label">CPU</div>
        <div id="gauge-cpu"></div>
        <div class="gauge-sub" id="sub-cpu">—</div>
      </div>
      <div class="gauge-card" style="--accent:#3fb950">
        <div class="gauge-label">MEMORY</div>
        <div id="gauge-mem"></div>
        <div class="gauge-sub" id="sub-mem">—</div>
      </div>
      <div class="gauge-card gpu-gauge-card" id="gpu-gauges-area">
        <!-- GPU gauges rendered here once live data arrives -->
        <div class="gauge-label">GPU</div>
        <div class="gpu-no-data">Waiting for GPU data…</div>
      </div>
    </div>

    <div class="stats-bar" id="stats-bar">
      <div class="stat-item"><span class="stat-label">CORES</span><span class="stat-val" id="stat-cores">—</span></div>
      <div class="stat-item"><span class="stat-label">FREQ</span><span class="stat-val" id="stat-freq">—</span></div>
      <div class="stat-item"><span class="stat-label">CPU TEMP</span><span class="stat-val" id="stat-cpu-temp">—</span></div>
      <div class="stat-item"><span class="stat-label">SWAP</span><span class="stat-val" id="stat-swap">—</span></div>
      <div class="stat-item"><span class="stat-label">UPTIME</span><span class="stat-val" id="stat-uptime">—</span></div>
      <div class="stat-item"><span class="stat-label">LAST POLL</span><span class="stat-val" id="stat-last">—</span></div>
    </div>

    <div class="charts-grid">
      <div class="chart-panel">
        <div class="chart-panel__title">CPU &amp; MEMORY — <span id="hist-range-label">1H</span></div>
        <div id="chart-cpumem"></div>
      </div>
      <div class="chart-panel" id="gpu-chart-panel">
        <div class="chart-panel__title">GPU vRAM &amp; UTILIZATION — <span class="hist-range-ref">1H</span></div>
        <div id="chart-gpu-vram"></div>
      </div>
      <div class="chart-panel">
        <div class="chart-panel__title">GPU POWER DRAW — <span class="hist-range-ref">1H</span></div>
        <div id="chart-gpu-power"></div>
      </div>
      <div class="chart-panel">
        <div class="chart-panel__title">GPU TEMPERATURE — <span class="hist-range-ref">1H</span></div>
        <div id="chart-gpu-temp"></div>
      </div>
    </div>
  `;

  buildRangeBar();
  initDetailCharts();
}

function buildRangeBar() {
  const bar = $("#range-bar");
  if (!bar) return;
  ["1h","3h","6h","24h","3d","7d"].forEach((r) => {
    const btn = el("button", "range-btn" + (r === state.selectedRange ? " active" : ""));
    btn.textContent = r.toUpperCase();
    btn.addEventListener("click", () => setRange(r));
    bar.appendChild(btn);
  });
}

function setRange(range) {
  state.selectedRange = range;
  $$(".range-btn").forEach((b) => b.classList.toggle("active", b.textContent.toLowerCase() === range));
  $$(".hist-range-ref, #hist-range-label").forEach((s) => (s.textContent = range.toUpperCase()));
  loadHistory();
}

function initDetailCharts() {
  createGauge("gauge-cpu", "CPU", "#58a6ff");
  createGauge("gauge-mem", "MEM", "#3fb950");

  createLineChart("chart-cpumem",
    [
      { name: "CPU %",  color: "#58a6ff" },
      { name: "MEM %",  color: "#3fb950" },
    ],
    "%", 100
  );

  createLineChart("chart-gpu-vram",
    [
      { name: "vRAM %",   color: "#d29922" },
      { name: "GPU Util %", color: "#bc8cff" },
    ],
    "%", 100
  );

  createPowerChart("chart-gpu-power");

  createLineChart("chart-gpu-temp",
    [{ name: "GPU Temp", color: "#f85149" }],
    "°C", null
  );
}

// ── Live polling ──────────────────────────────────────────────────────────────
function startLivePolling() {
  if (state.liveTimer) clearInterval(state.liveTimer);
  pollLive();   // immediate first poll
  state.liveTimer = setInterval(pollLive, LIVE_INTERVAL);
}

async function pollLive() {
  if (!state.selectedId) return;
  try {
    const data = await api.live(state.selectedId);
    applyLiveData(data);
  } catch (err) {
    console.warn("Live poll failed:", err);
    setOnlineState(false);
  }
}

function applyLiveData(data) {
  setOnlineState(data.online !== false);

  // ── CPU gauges ──
  updateGauge("gauge-cpu", data.cpu.utilization_pct);
  updateGauge("gauge-mem", data.memory.used_pct);

  // ── Sub-labels ──
  const subCpu = document.getElementById("sub-cpu");
  const subMem = document.getElementById("sub-mem");
  if (subCpu) subCpu.textContent =
    `${data.cpu.core_count_logical}-core  ${fmt.temp(data.cpu.temperature_c)}`;
  if (subMem) subMem.textContent =
    `${fmt.mb(data.memory.used_mb)} / ${fmt.mb(data.memory.total_mb)}`;

  // ── Stats bar ──
  setText("stat-cores",    `${data.cpu.core_count_physical}P / ${data.cpu.core_count_logical}L`);
  setText("stat-freq",     fmt.freq(data.cpu.frequency_mhz));
  setText("stat-cpu-temp", fmt.temp(data.cpu.temperature_c));
  setText("stat-swap",     `${fmt.mb(data.memory.swap_used_mb)} / ${fmt.mb(data.memory.swap_total_mb)}`);
  setText("stat-uptime",   fmtUptime(data.uptime_seconds));
  setText("stat-last",     new Date().toLocaleTimeString("en-GB", { hour12: false }));

  // ── GPU gauges ──
  renderGpuGauges(data.gpus || []);

  // ── Sparkline buffers ──
  const sid = state.selectedId;
  if (!state.sparkBuffers[sid]) state.sparkBuffers[sid] = { cpu: [], mem: [], gpu: [] };
  const buf = state.sparkBuffers[sid];
  buf.cpu = [...buf.cpu.slice(-(SPARKLINE_MAX - 1)), data.cpu.utilization_pct];
  buf.mem = [...buf.mem.slice(-(SPARKLINE_MAX - 1)), data.memory.used_pct];
  if (data.gpus?.length) buf.gpu = [...buf.gpu.slice(-(SPARKLINE_MAX - 1)), data.gpus[0].vram_pct];

  updateSparkline(`spark-cpu-${sid}`, buf.cpu);
  updateSparkline(`spark-mem-${sid}`, buf.mem);
  if (data.gpus?.length) updateSparkline(`spark-gpu-${sid}`, buf.gpu);
}

function renderGpuGauges(gpus) {
  const area = document.getElementById("gpu-gauges-area");
  if (!area) return;

  if (!gpus.length) {
    area.innerHTML = `<div class="gauge-label">GPU</div><div class="gpu-no-data">No GPU detected</div>`;
    return;
  }

  // Build gauge HTML once
  if (!area.dataset.rendered || area.dataset.gpuCount !== String(gpus.length)) {
    area.dataset.rendered = "1";
    area.dataset.gpuCount  = String(gpus.length);
    area.innerHTML = `<div class="gauge-label">GPU — ${gpus.length} device${gpus.length > 1 ? "s" : ""}</div>`;

    gpus.forEach((gpu, i) => {
      const wrap = el("div", "gpu-gauge-wrap");
      wrap.innerHTML = `
        <div class="gpu-gauge-name">
          <span class="gpu-badge gpu-badge--${gpu.vendor}">${gpu.vendor.toUpperCase()}</span>
          ${gpu.name}
        </div>
        <div class="gpu-gauge-meters">
          <div>
            <div id="gauge-vram-${i}"></div>
            <div class="gauge-sub" id="sub-vram-${i}">vRAM</div>
          </div>
          <div>
            <div id="gauge-gpupwr-${i}"></div>
            <div class="gauge-sub" id="sub-gpupwr-${i}">Power</div>
          </div>
        </div>
      `;
      area.appendChild(wrap);

      // Render gauges into new elements
      requestAnimationFrame(() => {
        createGauge(`gauge-vram-${i}`, "vRAM", "#d29922");
        // Power gauge shows W/TDP %
        const tdp = gpu.power_limit_w || 450;
        const pwrPct = gpu.power_draw_w != null ? (gpu.power_draw_w / tdp * 100) : 0;
        createGauge(`gauge-gpupwr-${i}`, "POWER", "#f85149");
        updateGauge(`gauge-vram-${i}`, gpu.vram_pct);
        updateGauge(`gauge-gpupwr-${i}`, pwrPct);
        setText(`sub-vram-${i}`,   `${fmt.mb(gpu.vram_used_mb)} / ${fmt.mb(gpu.vram_total_mb)}`);
        setText(`sub-gpupwr-${i}`, `${fmt.w(gpu.power_draw_w)}  ${fmt.temp(gpu.temperature_c)}`);
      });
    });

    return;
  }

  // Just update values
  gpus.forEach((gpu, i) => {
    const tdp    = gpu.power_limit_w || 450;
    const pwrPct = gpu.power_draw_w != null ? (gpu.power_draw_w / tdp * 100) : 0;
    updateGauge(`gauge-vram-${i}`, gpu.vram_pct);
    updateGauge(`gauge-gpupwr-${i}`, pwrPct);
    setText(`sub-vram-${i}`,   `${fmt.mb(gpu.vram_used_mb)} / ${fmt.mb(gpu.vram_total_mb)}`);
    setText(`sub-gpupwr-${i}`, `${fmt.w(gpu.power_draw_w)}  ${fmt.temp(gpu.temperature_c)}`);
  });
}

// ── History loading ───────────────────────────────────────────────────────────
async function loadHistory() {
  if (!state.selectedId) return;
  const id    = state.selectedId;
  const range = state.selectedRange;

  try {
    // System (CPU + MEM)
    const sys = await api.history(id, range, -1);
    updateLineChart("chart-cpumem", sys.data, ["cpu_pct", "mem_pct"]);

    // GPU 0 (vRAM + util)
    const gpuVram = await api.history(id, range, 0);
    if (gpuVram.data.length) {
      updateLineChart("chart-gpu-vram",  gpuVram.data, ["vram_pct", "gpu_util_pct"]);
      updateLineChart("chart-gpu-power", gpuVram.data, ["gpu_power_w"]);
      updateLineChart("chart-gpu-temp",  gpuVram.data, ["gpu_temp_c"]);
      $("#gpu-chart-panel") && ($("#gpu-chart-panel").style.opacity = "1");
    }
  } catch (err) {
    console.warn("History load failed:", err);
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function setOnlineState(online) {
  const srv = state.servers.find((s) => s.id === state.selectedId);
  if (srv) srv.online = online;
  $$(".status-dot").forEach((d) => {
    // only update dots in detail panel header
  });
  const hdr = document.querySelector(".detail-header .status-dot");
  if (hdr) {
    hdr.className = `status-dot ${online ? "online" : "offline"}`;
  }
}

function fmtUptime(secs) {
  if (secs == null) return "—";
  const d = Math.floor(secs / 86400);
  const h = Math.floor((secs % 86400) / 3600);
  const m = Math.floor((secs % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function showBanner(type, msg) {
  const b = document.getElementById("banner");
  if (!b) return;
  b.textContent = msg;
  b.className = `banner banner--${type}`;
  b.style.display = "block";
  setTimeout(() => (b.style.display = "none"), 5000);
}

// ── Boot ──────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
  startClock();
  await loadServers();

  // Periodic server-list refresh (picks up new/removed servers, status changes)
  state.serverTimer = setInterval(async () => {
    const prev = state.selectedId;
    await loadServers();
    if (state.selectedId !== prev) selectServer(prev || state.servers[0]?.id);
  }, SERVER_INTERVAL);
});
