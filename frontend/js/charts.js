/**
 * SRVWatch — ApexCharts setup, creation, and update helpers.
 *
 * Chart instances are keyed by their container element ID so we can
 * call updateSeries() on existing charts rather than destroying and
 * recreating them on every data refresh.
 *
 * Fixes vs v1:
 *  - updateLineChart: keep all rows per series (don't filter per-field —
 *    that caused series length mismatch). Use null for missing values so
 *    ApexCharts renders gaps correctly.
 *  - updateLineChart: guard against non-numeric values before toFixed()
 *  - createLineChart: don't spread baseChartOptions twice (caused chart
 *    key collision in ApexCharts internal registry)
 *  - GPU temp chart uses °C y-axis formatter
 */

const _charts = {};

// ── Shared theme ──────────────────────────────────────────────────────────────

const THEME = {
  blue:   "#58a6ff",
  green:  "#3fb950",
  amber:  "#d29922",
  red:    "#f85149",
  purple: "#bc8cff",
  bg:     "#0d1117",
  panel:  "#161b22",
  border: "#21262d",
  muted:  "#8b949e",
  text:   "#e6edf3",
};

function baseOptions(colors = [THEME.blue]) {
  return {
    chart: {
      background: "transparent",
      toolbar:    { show: false },
      zoom:       { enabled: false },
      animations: { enabled: true, easing: "linear", speed: 400 },
      fontFamily: "'IBM Plex Mono', monospace",
    },
    colors,
    stroke: { curve: "smooth", width: 2 },
    fill: {
      type: "gradient",
      gradient: { shadeIntensity: 1, opacityFrom: 0.22, opacityTo: 0.02, stops: [0, 100] },
    },
    grid: {
      borderColor: THEME.border,
      strokeDashArray: 3,
      xaxis: { lines: { show: false } },
    },
    xaxis: {
      type: "datetime",
      labels: { style: { colors: THEME.muted, fontSize: "10px" }, datetimeUTC: false },
      axisBorder: { show: false },
      axisTicks:  { show: false },
      tooltip:    { enabled: false },
    },
    yaxis: {
      min: 0,
      labels: {
        style: { colors: THEME.muted, fontSize: "10px" },
        formatter: (v) => (v == null ? "-" : v.toFixed(1) + "%"),
      },
    },
    tooltip: {
      theme: "dark",
      x: { format: "HH:mm:ss" },
      style: { fontFamily: "'IBM Plex Mono', monospace", fontSize: "11px" },
    },
    legend: {
      show: true,
      labels: { colors: THEME.muted },
      fontSize: "11px",
      fontFamily: "'IBM Plex Mono', monospace",
      markers: { width: 8, height: 8, radius: 2 },
    },
    dataLabels: { enabled: false },
    markers:    { size: 0 },
    noData: {
      text:  "Waiting for data…",
      style: { color: THEME.muted, fontSize: "12px" },
    },
  };
}

// ── Radial gauge ──────────────────────────────────────────────────────────────

export function createGauge(elementId, label, color = THEME.blue) {
  if (_charts[elementId]) return _charts[elementId];

  const chart = new ApexCharts(document.getElementById(elementId), {
    chart: {
      type: "radialBar",
      height: 140,
      background: "transparent",
      sparkline: { enabled: true },
      fontFamily: "'IBM Plex Mono', monospace",
      animations: { enabled: true, speed: 400 },
    },
    series: [0],
    colors: [color],
    plotOptions: {
      radialBar: {
        startAngle: -135,
        endAngle: 135,
        hollow: { size: "58%" },
        track: { background: THEME.border, strokeWidth: "100%" },
        dataLabels: {
          name:  { show: true, offsetY: 20, color: THEME.muted, fontSize: "10px" },
          value: {
            offsetY: -10, color: THEME.text, fontSize: "20px", fontWeight: 500,
            formatter: (v) => parseFloat(v).toFixed(1) + "%",
          },
        },
      },
    },
    labels: [label],
  });

  chart.render();
  _charts[elementId] = chart;
  return chart;
}

export function updateGauge(elementId, pct) {
  const chart = _charts[elementId];
  if (!chart) return;
  const val = Math.min(100, Math.max(0, parseFloat(pct) || 0));
  chart.updateSeries([val], false);
}

// ── Area / line chart ─────────────────────────────────────────────────────────

/**
 * @param {string}   elementId
 * @param {Array}    seriesConfig  [{name, color}, ...]
 * @param {string}   yUnit         "%" | "W" | "°C"
 * @param {number|null} yMax       fixed y-axis max, or null for auto
 */
export function createLineChart(elementId, seriesConfig, yUnit = "%", yMax = 100) {
  if (_charts[elementId]) return _charts[elementId];

  const colors = seriesConfig.map((s) => s.color);
  const base   = baseOptions(colors);

  const opts = {
    ...base,
    chart: {
      ...base.chart,
      type: "area",
      height: 180,
    },
    series: seriesConfig.map((s) => ({ name: s.name, data: [] })),
    yaxis: {
      ...base.yaxis,
      max: yMax ?? undefined,
      labels: {
        ...base.yaxis.labels,
        formatter: (v) => {
          if (v == null) return "-";
          if (yUnit === "W")  return v.toFixed(0) + " W";
          if (yUnit === "°C") return v.toFixed(0) + "°C";
          return v.toFixed(1) + "%";
        },
      },
    },
  };

  const chart = new ApexCharts(document.getElementById(elementId), opts);
  chart.render();
  _charts[elementId] = chart;
  return chart;
}

/**
 * Feed history rows into a line chart.
 *
 * @param {string}   elementId
 * @param {Object[]} rows    - rows from /history API, each has a `bucket` ISO string
 * @param {string[]} fields  - field names to extract, one per series
 *
 * All rows are kept for every series (null used for missing values so
 * ApexCharts can draw gaps). This keeps x-axis alignment consistent.
 */
export function updateLineChart(elementId, rows, fields) {
  const chart = _charts[elementId];
  if (!chart || !rows?.length) return;

  const series = fields.map((field) => ({
    data: rows.map((r) => {
      const ts  = new Date(r.bucket).getTime();
      const val = r[field] != null ? parseFloat(Number(r[field]).toFixed(2)) : null;
      return [ts, val];
    }),
  }));

  chart.updateSeries(series, false);
}

// ── Convenience constructors ──────────────────────────────────────────────────

export function createPowerChart(elementId) {
  return createLineChart(
    elementId,
    [{ name: "Power Draw", color: THEME.red }],
    "W",
    null
  );
}

export function createTempChart(elementId) {
  return createLineChart(
    elementId,
    [{ name: "Temperature", color: THEME.red }],
    "°C",
    null
  );
}

// ── Sparklines ────────────────────────────────────────────────────────────────

export function createSparkline(elementId, color = THEME.blue) {
  if (_charts[elementId]) return _charts[elementId];

  const chart = new ApexCharts(document.getElementById(elementId), {
    chart: {
      type: "line",
      height: 28,
      sparkline: { enabled: true },
      background: "transparent",
      animations: { enabled: false },
    },
    series: [{ data: [] }],
    colors: [color],
    stroke: { curve: "smooth", width: 1.5 },
    tooltip: { enabled: false },
  });

  chart.render();
  _charts[elementId] = chart;
  return chart;
}

export function updateSparkline(elementId, values) {
  const chart = _charts[elementId];
  if (!chart) return;
  chart.updateSeries([{ data: values }], false);
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────

export function destroyChart(elementId) {
  const chart = _charts[elementId];
  if (chart) { chart.destroy(); delete _charts[elementId]; }
}

export function destroyAll() {
  Object.keys(_charts).forEach(destroyChart);
}
