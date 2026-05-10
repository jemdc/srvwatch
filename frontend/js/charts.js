/**
 * SRVWatch — ApexCharts setup, creation, and update helpers.
 *
 * Chart instances are keyed by their container element ID so we can
 * call updateSeries() on existing charts rather than destroying and
 * recreating them on every data refresh.
 */

const _charts = {};

// ── Shared theme ──────────────────────────────────────────────────────────────

const THEME = {
  blue:   "#58a6ff",
  green:  "#3fb950",
  amber:  "#d29922",
  red:    "#f85149",
  purple: "#bc8cff",
  teal:   "#39d353",
  bg:     "#0e1117",
  panel:  "#161b22",
  border: "#21262d",
  muted:  "#8b949e",
  text:   "#e6edf3",
};

function baseChartOptions(colors = [THEME.blue]) {
  return {
    chart: {
      background: "transparent",
      toolbar: { show: false },
      zoom: { enabled: false },
      animations: { enabled: true, easing: "linear", speed: 400 },
      fontFamily: "'IBM Plex Mono', monospace",
    },
    colors,
    stroke: { curve: "smooth", width: 2 },
    fill: {
      type: "gradient",
      gradient: {
        shadeIntensity: 1,
        opacityFrom: 0.25,
        opacityTo: 0.02,
        stops: [0, 100],
      },
    },
    grid: {
      borderColor: THEME.border,
      strokeDashArray: 3,
      xaxis: { lines: { show: false } },
    },
    xaxis: {
      type: "datetime",
      labels: {
        style: { colors: THEME.muted, fontSize: "10px" },
        datetimeUTC: false,
      },
      axisBorder: { show: false },
      axisTicks: { show: false },
      tooltip: { enabled: false },
    },
    yaxis: {
      labels: {
        style: { colors: THEME.muted, fontSize: "10px" },
        formatter: (v) => (v == null ? "-" : v.toFixed(1)),
      },
      min: 0,
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
    markers: { size: 0 },
    noData: {
      text: "Waiting for data…",
      style: { color: THEME.muted, fontSize: "12px" },
    },
  };
}

// ── Radial gauge ──────────────────────────────────────────────────────────────

export function createGauge(elementId, label, color = THEME.blue) {
  if (_charts[elementId]) return _charts[elementId];

  const options = {
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
        track: {
          background: THEME.border,
          strokeWidth: "100%",
        },
        dataLabels: {
          name: {
            show: true,
            offsetY: 20,
            color: THEME.muted,
            fontSize: "10px",
          },
          value: {
            offsetY: -10,
            color: THEME.text,
            fontSize: "20px",
            fontWeight: 500,
            formatter: (v) => v.toFixed(1) + "%",
          },
        },
      },
    },
    labels: [label],
  };

  const chart = new ApexCharts(document.getElementById(elementId), options);
  chart.render();
  _charts[elementId] = chart;
  return chart;
}

export function updateGauge(elementId, pct) {
  const chart = _charts[elementId];
  if (!chart) return;
  chart.updateSeries([Math.min(100, Math.max(0, pct ?? 0))], false);
}

// ── Area line chart (CPU + MEM, or GPU metrics) ────────────────────────────

export function createLineChart(elementId, seriesConfig, yaxisLabel = "%", yMax = 100) {
  if (_charts[elementId]) return _charts[elementId];

  const colors = seriesConfig.map((s) => s.color);
  const opts = {
    ...baseChartOptions(colors),
    chart: {
      ...baseChartOptions(colors).chart,
      type: "area",
      height: 180,
      id: elementId,
    },
    series: seriesConfig.map((s) => ({ name: s.name, data: [] })),
    yaxis: {
      ...baseChartOptions(colors).yaxis,
      max: yMax || undefined,
      labels: {
        ...baseChartOptions(colors).yaxis.labels,
        formatter: (v) => {
          if (v == null) return "-";
          return yaxisLabel === "W"
            ? v.toFixed(0) + "W"
            : v.toFixed(1) + "%";
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
 * Update a line chart with history API response data.
 * @param {string} elementId
 * @param {Object[]} rows  - array of row objects from /history endpoint
 * @param {string[]} fields - field names to pull from each row
 */
export function updateLineChart(elementId, rows, fields) {
  const chart = _charts[elementId];
  if (!chart) return;

  const series = fields.map((field) => ({
    data: rows
      .filter((r) => r[field] != null)
      .map((r) => [new Date(r.bucket).getTime(), parseFloat(r[field].toFixed(2))]),
  }));

  chart.updateSeries(series, false);
}

// ── GPU power chart (W not %) ─────────────────────────────────────────────

export function createPowerChart(elementId) {
  return createLineChart(
    elementId,
    [{ name: "Power Draw", color: THEME.red }],
    "W",
    null   // no fixed max — auto-scale to TDP
  );
}

// ── Mini sparkline (used in the server list cards) ────────────────────────

export function createSparkline(elementId, color = THEME.blue) {
  if (_charts[elementId]) return _charts[elementId];

  const opts = {
    chart: {
      type: "line",
      height: 30,
      sparkline: { enabled: true },
      background: "transparent",
      animations: { enabled: false },
    },
    series: [{ data: [] }],
    colors: [color],
    stroke: { curve: "smooth", width: 1.5 },
    tooltip: { enabled: false },
  };

  const chart = new ApexCharts(document.getElementById(elementId), opts);
  chart.render();
  _charts[elementId] = chart;
  return chart;
}

export function updateSparkline(elementId, values) {
  const chart = _charts[elementId];
  if (!chart) return;
  chart.updateSeries([{ data: values }], false);
}

// ── Destroy chart (e.g. on server switch) ────────────────────────────────

export function destroyChart(elementId) {
  const chart = _charts[elementId];
  if (chart) {
    chart.destroy();
    delete _charts[elementId];
  }
}

export function destroyAll() {
  Object.keys(_charts).forEach(destroyChart);
}
