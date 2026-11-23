/* ============================================================
   ESP32 RSSI Monitor Dashboard — frontend logic
   - Polls /api/status and /api/history
   - Draws live RSSI chart (Chart.js)
   - Handles connect/disconnect, distance label, export, clear
   ============================================================ */

const API = {
  ports:      "/api/ports",
  connect:    "/api/connect",
  disconnect: "/api/disconnect",
  status:     "/api/status",
  history:    "/api/history",
  setDistance:"/api/set_distance",
  clear:      "/api/clear",
  exportCsv:  "/api/export_csv",
};

let chart = null;
let pollTimer = null;
let lastSampleCount = -1;

/* ---------- Signal quality ---------- */
function qualityOf(rssi) {
  if (rssi === null || rssi === undefined) return { label: "--", cls: "" };
  if (rssi >= -50) return { label: "Excellent", cls: "excellent", badge: "ok" };
  if (rssi >= -60) return { label: "Good",      cls: "good",      badge: "ok" };
  if (rssi >= -70) return { label: "Fair",      cls: "fair",      badge: "warn" };
  if (rssi >= -80) return { label: "Weak",      cls: "weak",      badge: "warn" };
  return { label: "Very weak", cls: "very-weak", badge: "err" };
}

/* ---------- API helper ---------- */
async function api(path, opts) {
  const res = await fetch(path, opts);
  let data = null;
  try { data = await res.json(); } catch (e) { /* may be a file download */ }
  if (!res.ok) {
    const msg = data && data.error ? data.error : `Request failed (${res.status})`;
    throw new Error(msg);
  }
  return data;
}

/* ---------- Ports ---------- */
async function loadPorts() {
  const sel = document.getElementById("port-select");
  sel.innerHTML = "<option value=''>Loading…</option>";
  try {
    const data = await api(API.ports);
    sel.innerHTML = "";
    if (!data.ports.length) {
      sel.innerHTML = "<option value=''>No ports found</option>";
      return;
    }
    for (const p of data.ports) {
      const opt = document.createElement("option");
      opt.value = p.device;
      opt.textContent = `${p.device} — ${p.description}`;
      sel.appendChild(opt);
    }
  } catch (e) {
    sel.innerHTML = "<option value=''>Error loading ports</option>";
  }
}

/* ---------- Connect / Disconnect ---------- */
async function connect() {
  const port = document.getElementById("port-select").value;
  const baud = parseInt(document.getElementById("baud-select").value, 10);
  if (!port) { setConnStatus("Select a COM port first.", true); return; }
  try {
    await api(API.connect, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ port, baud }),
    });
    setConnStatus(`Connected to ${port} @ ${baud}`, false);
    appendLog(`# Connected to ${port} @ ${baud}`, "dbg");
  } catch (e) {
    setConnStatus(e.message, true);
    appendLog(`# ERROR: ${e.message}`, "err");
  }
}

async function disconnect() {
  try {
    await api(API.disconnect, { method: "POST" });
    setConnStatus("Disconnected", false);
    appendLog("# Disconnected", "dbg");
  } catch (e) {
    setConnStatus(e.message, true);
  }
}

/* ---------- Distance ---------- */
async function setDistance() {
  const val = document.getElementById("distance-input").value;
  try {
    const res = await api(API.setDistance, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ distance: parseFloat(val) }),
    });
    appendLog(`# ${res.message}`, "dbg");
  } catch (e) {
    appendLog(`# Error setting distance: ${e.message}`, "err");
  }
}

/* ---------- Clear ---------- */
async function clearData() {
  if (!confirm("Clear all stored samples? This cannot be undone.")) return;
  try {
    await api(API.clear, { method: "POST" });
    lastSampleCount = -1;
    appendLog("# Data cleared", "dbg");
    updateHistory([]);
    if (chart) {
      chart.data.labels = [];
      chart.data.datasets[0].data = [];
      chart.update();
    }
  } catch (e) {
    appendLog(`# Clear failed: ${e.message}`, "err");
  }
}

/* ---------- Export ---------- */
function exportCsv() {
  window.location.href = API.exportCsv;
}

/* ---------- Log ---------- */
function appendLog(text, cls) {
  const log = document.getElementById("telemetry-log");
  const line = document.createElement("div");
  line.className = "line" + (cls ? " " + cls : "");
  line.textContent = text;
  log.appendChild(line);
  log.scrollTop = log.scrollHeight;
  // Trim very old lines to keep DOM light
  while (log.childElementCount > 500) log.removeChild(log.firstChild);
}

/* ---------- Status text ---------- */
function setConnStatus(msg, isError) {
  const el = document.getElementById("conn-status");
  el.textContent = msg;
  el.style.color = isError ? "var(--danger)" : "var(--text-muted)";
}

/* ---------- Chart ---------- */
function initChart() {
  const ctx = document.getElementById("rssi-chart").getContext("2d");
  chart = new Chart(ctx, {
    type: "line",
    data: {
      labels: [],
      datasets: [{
        label: "RSSI (dBm)",
        data: [],
        borderColor: "#00d9ff",
        backgroundColor: "rgba(0,217,255,0.12)",
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.25,
        fill: true,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: {
        legend: { labels: { color: "#e8eaee" } },
        tooltip: { mode: "index", intersect: false },
      },
      scales: {
        x: { ticks: { color: "#94a3b8", maxTicksLimit: 8 }, grid: { color: "#2d3040" } },
        y: {
          ticks: { color: "#94a3b8" }, grid: { color: "#2d3040" },
          title: { display: true, text: "RSSI (dBm)", color: "#94a3b8" },
        },
      },
    },
  });
}

/* ---------- History table ---------- */
function updateHistory(samples) {
  const body = document.getElementById("history-body");
  body.innerHTML = "";
  // Show newest first, cap at 200 rows for DOM sanity
  const recent = samples.slice(-200).reverse();
  for (const s of recent) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${s.Time_ms}</td><td>${s.Distance_m}</td><td>${s.RSSI_dBm}</td>`;
    body.appendChild(tr);
  }
}

/* ---------- Poll ---------- */
async function poll() {
  try {
    const status = await api(API.status);

    // Latest reading
    if (status.latest) {
      const rssi = status.latest.RSSI_dBm;
      document.getElementById("rssi-value").textContent = `${rssi} dBm`;
      document.getElementById("latest-time").textContent = `${status.latest.Time_ms} ms`;
      document.getElementById("latest-distance").textContent = `${status.latest.Distance_m} m`;

      const q = qualityOf(rssi);
      const ql = document.getElementById("quality-label");
      ql.textContent = q.label;
      ql.className = q.cls;
      const badge = document.getElementById("quality-badge");
      badge.textContent = q.label;
      badge.className = "badge " + (q.badge || "");
    } else {
      document.getElementById("rssi-value").textContent = "-- dBm";
    }

    document.getElementById("sample-count").textContent = status.sample_count;

    // New samples? Refresh history + chart
    if (status.sample_count !== lastSampleCount) {
      lastSampleCount = status.sample_count;
      const hist = await api(API.history);
      const samples = hist.samples || [];
      updateHistory(samples);
      if (chart) {
        chart.data.labels = samples.map((s) => (s.Time_ms / 1000).toFixed(1));
        chart.data.datasets[0].data = samples.map((s) => s.RSSI_dBm);
        chart.update("none");
      }
      // Log the latest sample to telemetry
      if (samples.length) {
        const last = samples[samples.length - 1];
        appendLog(`${last.Time_ms},${last.RSSI_dBm}  (dist=${last.Distance_m} m)`);
      }
    }

    // Connection badge
    const badge = document.getElementById("quality-badge");
    if (!status.connected) {
      // Only override if we have no reading quality badge set
      // (keep quality label if there is a last reading)
    }
  } catch (e) {
    // Silent — server may be momentarily busy
  }
}

/* ---------- Wire up ---------- */
document.addEventListener("DOMContentLoaded", () => {
  initChart();
  loadPorts();

  document.getElementById("refresh-ports").addEventListener("click", loadPorts);
  document.getElementById("connect-btn").addEventListener("click", connect);
  document.getElementById("disconnect-btn").addEventListener("click", disconnect);
  document.getElementById("set-distance-btn").addEventListener("click", setDistance);
  document.getElementById("clear-btn").addEventListener("click", clearData);
  document.getElementById("export-btn").addEventListener("click", exportCsv);

  // Render MATLAB source injected inline by Flask (single source of truth)
  const matlabEl = document.getElementById("matlab-code");
  if (matlabEl && window.__MATLAB_CODE__) {
    matlabEl.textContent = window.__MATLAB_CODE__;
  }

  pollTimer = setInterval(poll, 1000);
  poll();
});