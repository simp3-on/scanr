/* static/main.js */

const API_BASE      = window.location.origin;
const AUTO_INTERVAL = 10 * 60; // seconds

let currentMode    = "relaxed";
let allResults     = [];
let prevResultsMap = {};

// ── Auto-scan state ───────────────────────────────────────────────────────────
let autoScanEnabled  = false;
let countdownSeconds = AUTO_INTERVAL;
let countdownTimer   = null;

// ── Mode toggle ───────────────────────────────────────────────────────────────

function setMode(m) {
  currentMode = m;
  document.getElementById("btnRelaxed").className =
    "mode-btn" + (m === "relaxed" ? " active-relaxed" : "");
  document.getElementById("btnStrict").className =
    "mode-btn" + (m === "strict" ? " active-strict" : "");
  updateModeInfo();
}

function updateModeInfo() {
  const el = document.getElementById("modeInfo");
  if (currentMode === "strict") {
    el.className   = "mode-info strict show";
    el.textContent = "STRICT MODE — ≥3% price move AND ≥2× volume spike both required. High-conviction only.";
  } else {
    el.className   = "mode-info show";
    el.textContent = "RELAXED MODE — ≥1.5% price move OR ≥1.3× volume spike. Wider net, more noise.";
  }
}

// ── Legend toggle ─────────────────────────────────────────────────────────────

function toggleLegend() {
  const panel = document.getElementById("legendPanel");
  const icon  = document.getElementById("legendIcon");
  const open  = panel.classList.toggle("open");
  icon.classList.toggle("open", open);
}

// ── UTC clock ─────────────────────────────────────────────────────────────────

function updateClock() {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  document.getElementById("clockDisplay").textContent =
    `${pad(now.getUTCHours())}:${pad(now.getUTCMinutes())}:${pad(now.getUTCSeconds())} UTC`;
}
setInterval(updateClock, 1000);
updateClock();

// ── Market hours banner ───────────────────────────────────────────────────────

async function updateMarketHours() {
  try {
    const resp = await fetch(`${API_BASE}/api/market-hours`);
    const data = await resp.json();
    renderMarketHours(data);
  } catch {
    // silently fail — don't break the UI if this endpoint is slow
  }
}

function renderMarketHours(data) {
  const banner = document.getElementById("marketHoursBanner");
  const { us, eu, utc_time, weekday } = data;

  const pill = (market, info) => {
    const cls = {
      open:    "mh-open",
      pre:     "mh-pre",
      post:    "mh-post",
      closed:  "mh-closed",
      weekend: "mh-closed",
    }[info.status] || "mh-closed";

    const dot = {
      open:    "🟢",
      pre:     "🟡",
      post:    "🟡",
      closed:  "🔴",
      weekend: "🔴",
    }[info.status] || "🔴";

    return `<span class="mh-pill ${cls}">${dot} ${market}: ${info.label} <span class="mh-hours">${info.hours}</span></span>`;
  };

  banner.innerHTML = `
    <span class="mh-label">Market Status</span>
    ${pill("US", us)}
    ${pill("EU", eu)}
    <span class="mh-time">${weekday} · ${utc_time}</span>
  `;
  banner.style.display = "flex";

  // Warn if both markets closed and auto-scan is on
  updateClosedWarning(us.status, eu.status);
}

function updateClosedWarning(usStatus, euStatus) {
  const warn   = document.getElementById("closedWarning");
  const market = document.getElementById("marketSelect").value;
  if (!warn) return;

  const bothClosed = usStatus !== "open" && euStatus !== "open";
  const usClosed   = market === "us" && usStatus !== "open";
  const euClosed   = market === "eu" && euStatus !== "open";

  if (usClosed || euClosed || (market === "all" && bothClosed)) {
    warn.style.display = "flex";
    const why = usStatus === "weekend" || euStatus === "weekend" ? "weekend" : "outside trading hours";
    warn.textContent = `⚠ The selected market is currently closed (${why}). Data shown is from the last trading session — not live.`;
  } else {
    warn.style.display = "none";
  }
}

// Refresh market hours every minute
updateMarketHours();
setInterval(updateMarketHours, 60 * 1000);

// Re-check warning when market selection changes
document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("marketSelect").addEventListener("change", updateMarketHours);
});

// ── Auto-scan ─────────────────────────────────────────────────────────────────

function toggleAutoScan() {
  autoScanEnabled = !autoScanEnabled;
  const btn = document.getElementById("autoScanBtn");

  if (autoScanEnabled) {
    btn.classList.add("active");
    btn.textContent = "⏸ Auto-Scan ON";
    startCountdown();
    runScan();
  } else {
    btn.classList.remove("active");
    btn.textContent = "▶▶ Auto-Scan";
    stopCountdown();
    setCountdownDisplay(null);
  }
}

function startCountdown() {
  stopCountdown();
  countdownSeconds = AUTO_INTERVAL;
  updateCountdownDisplay();

  countdownTimer = setInterval(() => {
    countdownSeconds--;
    updateCountdownDisplay();
    if (countdownSeconds <= 0) {
      countdownSeconds = AUTO_INTERVAL;
      runScan();
    }
  }, 1000);
}

function stopCountdown() {
  if (countdownTimer) clearInterval(countdownTimer);
  countdownTimer = null;
}

function updateCountdownDisplay() {
  const mins = String(Math.floor(countdownSeconds / 60)).padStart(2, "0");
  const secs = String(countdownSeconds % 60).padStart(2, "0");
  setCountdownDisplay(`Next scan in ${mins}:${secs}`);
}

function setCountdownDisplay(text) {
  const el = document.getElementById("countdownDisplay");
  el.textContent   = text || "";
  el.style.display = text ? "inline" : "none";
}

function resetCountdown() {
  if (!autoScanEnabled) return;
  countdownSeconds = AUTO_INTERVAL;
  updateCountdownDisplay();
}

// ── Sort ──────────────────────────────────────────────────────────────────────

function getSortedResults() {
  const sort = document.getElementById("sortSelect").value;
  const r    = [...allResults];
  const fns  = {
    change:  (a, b) => Math.abs(b.price_change_pct) - Math.abs(a.price_change_pct),
    volume:  (a, b) => b.volume_ratio - a.volume_ratio,
    price:   (a, b) => b.price - a.price,
    signals: (a, b) => b.signals.length - a.signals.length,
  };
  return r.sort(fns[sort] || fns.change);
}

document.getElementById("sortSelect").addEventListener("change", () => {
  if (allResults.length > 0) renderTable(getSortedResults());
});

// ── Scan (SSE-powered) ────────────────────────────────────────────────────────

async function runScan() {
  const market    = document.getElementById("marketSelect").value;
  const direction = document.getElementById("directionSelect").value;
  const btn       = document.querySelector(".scan-btn");
  const btnText   = document.getElementById("scanBtnText");

  btn.classList.add("loading");
  btnText.textContent = "⟳ Scanning...";
  setStatus("SCANNING", true);
  document.getElementById("errorBox").style.display = "none";

  const isFirstScan = allResults.length === 0;
  if (isFirstScan) {
    document.getElementById("statsBar").style.display    = "none";
    document.getElementById("tableHeader").style.display = "none";
    showProgressBox(0, 0, 0);
  }

  const url = `${API_BASE}/api/scan?mode=${currentMode}&market=${market}&direction=${direction}`;

  try {
    const evtSource = new EventSource(url);

    evtSource.onmessage = (e) => {
      const msg = JSON.parse(e.data);

      if (msg.type === "universe") {
        showProgressBox(0, msg.total, 0);
      }

      if (msg.type === "progress") {
        showProgressBox(msg.done, msg.total, msg.eta);
      }

      if (msg.type === "result") {
        evtSource.close();

        const newResults     = msg.results || [];
        const changedSymbols = diffResults(allResults, newResults);
        prevResultsMap       = buildSnapshotMap(newResults);
        allResults           = newResults;

        renderStats(msg);
        updateModeInfo();
        renderTable(getSortedResults(), changedSymbols);

        document.getElementById("scanTimestamp").textContent =
          "Last scan: " + (msg.timestamp ? new Date(msg.timestamp).toUTCString() : "—");
        document.getElementById("tableHeader").style.display = "flex";

        btn.classList.remove("loading");
        btnText.textContent = "▶ Run Scan";
        setStatus(autoScanEnabled ? "AUTO" : "IDLE", autoScanEnabled);
        resetCountdown();
      }

      if (msg.type === "error") {
        evtSource.close();
        showError(msg.message);
        btn.classList.remove("loading");
        btnText.textContent = "▶ Run Scan";
        setStatus("IDLE", false);
        resetCountdown();
      }
    };

    evtSource.onerror = () => {
      evtSource.close();
      showError("Connection lost. Make sure app.py is running on port 5000.");
      btn.classList.remove("loading");
      btnText.textContent = "▶ Run Scan";
      setStatus("IDLE", false);
      resetCountdown();
    };

  } catch (err) {
    showError(err.message);
    btn.classList.remove("loading");
    btnText.textContent = "▶ Run Scan";
    setStatus("IDLE", false);
    resetCountdown();
  }
}

// ── Progress box ──────────────────────────────────────────────────────────────

function showProgressBox(done, total, eta) {
  const pct     = total > 0 ? Math.round((done / total) * 100) : 0;
  const etaText = eta > 0
    ? `~${eta}s remaining`
    : done === 0 ? "Starting..." : "Finishing up...";

  document.getElementById("tableContainer").innerHTML = `
    <div class="state-box">
      <div class="progress-label">
        <span class="progress-count">Fetching <strong>${done}</strong> / <strong>${total}</strong> stocks</span>
        <span class="progress-eta">${etaText}</span>
      </div>
      <div class="progress-track">
        <div class="progress-real" style="width:${pct}%"></div>
      </div>
      <span class="progress-pct">${pct}%</span>
    </div>`;
}

// ── Change detection ──────────────────────────────────────────────────────────

function buildSnapshotMap(results) {
  const map = {};
  results.forEach((s) => {
    map[s.symbol] = {
      price:            s.price,
      price_change_pct: s.price_change_pct,
      signals:          (s.signals || []).join(","),
    };
  });
  return map;
}

function diffResults(prev, next) {
  const changed = new Set();
  const prevMap = buildSnapshotMap(prev);
  next.forEach((s) => {
    const old = prevMap[s.symbol];
    if (!old) { changed.add(s.symbol); return; }
    if (
      old.price            !== s.price ||
      old.price_change_pct !== s.price_change_pct ||
      old.signals          !== (s.signals || []).join(",")
    ) changed.add(s.symbol);
  });
  return changed;
}

// ── UI helpers ────────────────────────────────────────────────────────────────

function setStatus(text, live) {
  document.getElementById("statusText").textContent = text;
  document.getElementById("statusDot").className    = "status-dot" + (live ? " live" : "");
}

function showError(msg) {
  if (allResults.length === 0) {
    document.getElementById("tableContainer").innerHTML = `
      <div class="state-box">
        <div class="icon">⚠</div>
        <p>Scan failed — is the Flask server running?</p>
      </div>`;
  }
  const eb         = document.getElementById("errorBox");
  eb.style.display = "block";
  eb.textContent   = `ERROR: ${msg}`;
}

function renderStats(data) {
  const { results = [], scanned = 0 } = data;
  const up  = results.filter((r) => r.direction === "UP").length;
  const dn  = results.filter((r) => r.direction === "DOWN").length;
  const avg = results.length
    ? (results.reduce((s, r) => s + Math.abs(r.price_change_pct), 0) / results.length).toFixed(2)
    : "0.00";

  document.getElementById("statSignals").textContent = results.length;
  document.getElementById("statScanned").textContent = scanned;
  document.getElementById("statUp").textContent      = up;
  document.getElementById("statDown").textContent    = dn;
  document.getElementById("statAvgMove").textContent = avg + "%";
  document.getElementById("statsBar").style.display  = "flex";
}

// ── Tooltip helper ────────────────────────────────────────────────────────────

function tip(label, text) {
  return `<span class="th-wrap">${label}<i class="info-icon">?</i><span class="tooltip">${text}</span></span>`;
}

// ── Table render ──────────────────────────────────────────────────────────────

function renderTable(results, changedSymbols = new Set()) {
  if (results.length === 0) {
    document.getElementById("tableContainer").innerHTML = `
      <div class="state-box">
        <div class="icon">◯</div>
        <p>No signals matched — try relaxed mode</p>
      </div>`;
    return;
  }

  const rows = results.map((s, i) => buildRow(s, i, changedSymbols)).join("");

  document.getElementById("tableContainer").innerHTML = `
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>${tip("Symbol", "The stock's ticker — a short unique code used to identify it on the exchange. e.g. AAPL = Apple.")}</th>
          <th>${tip("Company", "The full company name behind the ticker symbol.")}</th>
          <th style="text-align:right">${tip("Price", "The stock's latest closing price. US stocks are in USD. EU stocks are in their local currency (€, £, etc).")}</th>
          <th>${tip("1D Change", "How much the price moved today vs yesterday's close. Green ▲ = went up. Red ▼ = went down. The % shows how big the move was.")}</th>
          <th style="text-align:right">${tip("5D Move", "Price change over the last 5 trading days (~1 week). Helps you see if today's move is part of a bigger trend or just a one-day event.")}</th>
          <th>${tip("Volume", "How many times more people than usual are trading this stock today vs its 10-day average. 1.0× = normal. 3.0× = 3× the usual. Color = intensity: Blue → Orange → Red (extreme).")}</th>
          <th>${tip("Signals", "What triggered this stock. PRICE MOVE = big daily swing. VOL SPIKE = unusual activity. MOMENTUM = trending for 5+ days. More signals = stronger case.")}</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function buildRow(s, i, changedSymbols = new Set()) {
  const isUp       = s.direction === "UP";
  const changeSign = isUp ? "+" : "";
  const fiveSign   = s.five_day_change >= 0 ? "+" : "";
  const fiveColor  = s.five_day_change >= 0 ? "var(--up)" : "var(--down)";
  const volPct     = Math.min(100, ((s.volume_ratio - 1) / 4) * 100);
  const barClass   = s.volume_ratio >= 4 ? "extreme" : s.volume_ratio >= 2.5 ? "high" : "";
  const sigTags    = (s.signals || [])
    .map((sig) => `<span class="signal-tag ${sig}">${sig.replace("_", " ")}</span>`)
    .join("");
  const price      = s.price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const isChanged  = changedSymbols.has(s.symbol);
  const rowClass   = isChanged ? " class=\"row-changed\"" : "";
  const newBadge   = isChanged && !prevResultsMap[s.symbol]
    ? `<span class="new-badge">NEW</span> ` : "";

  return `
    <tr${rowClass} style="animation-delay:${i * 30}ms">
      <td class="col-rank">${i + 1}</td>
      <td class="col-symbol">${newBadge}${s.symbol}</td>
      <td class="col-name">${s.name}</td>
      <td class="col-price">$${price}</td>
      <td><span class="change-badge ${isUp ? "up" : "down"}">${isUp ? "▲" : "▼"} ${changeSign}${s.price_change_pct}%</span></td>
      <td class="col-5d" style="color:${fiveColor}">${fiveSign}${s.five_day_change}%</td>
      <td>
        <div class="vol-bar-wrap">
          <div class="vol-bar-bg"><div class="vol-bar-fill ${barClass}" style="width:${volPct}%"></div></div>
          <span class="vol-ratio">${s.volume_ratio}×</span>
        </div>
      </td>
      <td class="signals-cell">${sigTags}</td>
    </tr>`;
}