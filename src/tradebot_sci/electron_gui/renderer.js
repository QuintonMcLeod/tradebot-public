// CODING RULE: Do NOT insert watermark tags (e.g. [AGENT_NAME], [AI FIX], etc.)
// into comments or log statements. Write clean, professional comments only.
// See AGENTS.md for full guidelines.

// --- Chart & DOM State ---
let chart;
let candleSeries;
let indicatorSeries;
let emaSeries;
let smaSeries;
let bbUpperSeries, bbMiddleSeries, bbLowerSeries;
let vwapSeries;
let ema200Series;
let rsiSeries;
let stopLossLine; // Horizontal price line for SL
let takeProfitLine; // Horizontal price line for TP
let entryPriceLine; // Horizontal price line for entry
let tradeMarkers = []; // Current active markers for symbols
let markerCache = {}; // Cache of markers per symbol: { 'BTCUSD': [markers], ... }
let previousSymbol = null; // Track symbol shifts to clear markers selectively
let candleData = []; // Store candle data for indicator calculations
let rawCandleData = []; // Raw data with volume, for VWAP computation
let chartMode = 'candle'; // 'candle' | 'heikinashi'
let currentPosition = null; // { symbol, side, entry, sl, tp, size }
let lastHoldings = null; // Cache last holdings data for redrawing on symbol switch
let statusDot;
let statusLatency;
let currentRealizedPnL = 0;
let currentUnrealizedPnL = 0;
// pnlTimeframe is now the single source of truth for display mode too.
// Possible values: 'holdings', '24h', 'week', 'month', 'year', 'all'
// Authoritative source for PnL timeframe, synced with sidebar and settings
let pnlTimeframe = localStorage.getItem('pnlTimeframe') || '24h';
window.pnlTimeframe = pnlTimeframe;
const pnlModes = ['1h', '4h', '24h', '7d', 'all'];

function refreshMainPnlDisplay() {
    const equityEl = document.getElementById('account-equity');
    const pnlLabel = document.getElementById('pnl-mode-label'); // Renamed from labelEl for clarity
    if (!equityEl) return;

    let displayVal = 0;
    let labelText = "Profits & Losses";

    if (pnlTimeframe === 'holdings') {
        displayVal = Number(currentUnrealizedPnL) || 0;
        labelText = "Profits & Losses (Active)";
    } else {
        // Total (Realized for timeframe + Current Unrealized)
        displayVal = (Number(currentRealizedPnL) || 0) + (Number(currentUnrealizedPnL) || 0);
        labelText = `Profits & Losses (${pnlTimeframe.toUpperCase()})`;
    }

    if (pnlLabel) pnlLabel.textContent = labelText + ":";
    equityEl.textContent = displayVal.toFixed(2);

    // Sync with settings dropdown if it exists and is loaded
    // Matches the structure in settings_integrated.js
    const timeframeDropdown = document.querySelector('.control-card[data-key="GUI_PNL_TIMEFRAME"] select');
    if (timeframeDropdown) {
        timeframeDropdown.value = pnlTimeframe;
    }

    if (displayVal >= 0) {
        equityEl.classList.remove('text-red-400', 'text-rose-500');
        equityEl.classList.add('text-emerald-400');
    } else {
        equityEl.classList.remove('text-emerald-400', 'text-green-400');
        equityEl.classList.add('text-red-400');
    }
}

function handlePnlToggle() {
    const modes = ['holdings', '24h', 'week', 'month', 'year', 'all'];
    let idx = modes.indexOf(pnlTimeframe);
    if (idx === -1) idx = 1; // Default to 24h if invalid

    pnlTimeframe = modes[(idx + 1) % modes.length];
    window.pnlTimeframe = pnlTimeframe;
    localStorage.setItem('pnlTimeframe', pnlTimeframe);

    // Sync with settings panel if loaded
    if (typeof window.updateValue === 'function') {
        window.updateValue('GUI_PNL_TIMEFRAME', pnlTimeframe);
    }

    // Trigger data refresh if not holdings (since we need realized stats from backend)
    if (pnlTimeframe !== 'holdings') {
        if (typeof updateRealizedPnL === 'function') updateRealizedPnL(); else if (window.updateRealizedPnL) window.updateRealizedPnL();
    } else {
        refreshMainPnLDisplay();
    }

    console.log(`[PNL-UI] Mode switched to: ${pnlTimeframe}`);
    refreshMainPnLDisplay();
}

// Bridge for settings panel to update sidebar
// Sync from settings panel
window.syncPnLTimeframe = function (newTimeframe) {
    if (pnlTimeframe === newTimeframe) return;
    pnlTimeframe = newTimeframe;
    window.pnlTimeframe = newTimeframe;
    localStorage.setItem('pnlTimeframe', pnlTimeframe);
    if (typeof updateRealizedPnL === 'function') updateRealizedPnL(); else if (window.updateRealizedPnL) window.updateRealizedPnL();
    refreshMainPnLDisplay();
    console.log(`[PNL-SYNC] Timeframe synchronized from settings: ${pnlTimeframe}`);
};

function tfToSeconds(tf) {
    if (!tf) return 900;
    const num = parseInt(tf);
    const unit = tf.toLowerCase().replace(/[0-9]/g, '').trim();
    if (unit === 'm') return num * 60;
    if (unit === 'h') return num * 3600;
    if (unit === 'd') return num * 86400;
    return 900;
}

function parseLogTimestamp(line) {
    const match = line.match(/^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})/);
    if (match) {
        // Log is LOCAL time, convert to Unix Seconds.
        // Then shift to match chart's utcToLocal scale.
        const utcEpoch = Math.floor(new Date(match[1].replace(' ', 'T')).getTime() / 1000);
        return utcToLocal(utcEpoch);
    }
    return utcToLocal(Math.floor(Date.now() / 1000));
}

// Timezone offset helper.
// LightweightCharts treats all timestamps as UTC.
// To display local time, we shift UTC epoch seconds by the browser's TZ offset.
const _tzOffsetSec = -(new Date().getTimezoneOffset() * 60); // positive for EST(-5) = -(-300*60) = +18000? No: getTimezoneOffset returns minutes AHEAD of UTC. EST = +300. So offset = -300*60 = -18000. We ADD this to shift UTC->local.
function utcToLocal(epochSec) {
    return epochSec - (new Date().getTimezoneOffset() * 60);
}

// 12-hour tick formatter for the X-axis labels
function formatTime12h(epochSec) {
    // epochSec has already been shifted to local, so treat as-is
    const d = new Date(epochSec * 1000);
    let h = d.getUTCHours();     // Use UTC since we already shifted
    const m = d.getUTCMinutes();
    const ampm = h >= 12 ? 'PM' : 'AM';
    h = h % 12 || 12;
    return `${h}:${m.toString().padStart(2, '0')} ${ampm}`;
}

function initChart(intervalSeconds = 900) {
    const chartContainer = document.getElementById('chart-area');
    if (!chartContainer) return;

    if (chart) {
        chart.remove();
        chart = null;
    }

    chart = LightweightCharts.createChart(chartContainer, {
        layout: {
            background: { type: 'Color', color: 'transparent' },
            textColor: '#94a3b8',
            fontFamily: "'Inter', sans-serif",
        },
        grid: {
            vertLines: { color: 'rgba(255, 255, 255, 0.08)', style: 2, visible: true },
            horzLines: { color: 'rgba(255, 255, 255, 0.08)', style: 2, visible: true },
        },
        rightPriceScale: {
            borderColor: 'rgba(255, 255, 255, 0.05)',
        },
        timeScale: {
            borderColor: 'rgba(255, 255, 255, 0.05)',
            timeVisible: true,
            tickMarkFormatter: (time, tickMarkType, locale) => {
                // tickMarkType: 0=Year, 1=Month, 2=DayOfMonth, 3=Time, 4=TimeWithSeconds
                const d = new Date(time * 1000);
                const month = d.toLocaleString('en-US', { month: 'short', timeZone: 'UTC' });
                const day = d.getUTCDate();
                if (tickMarkType <= 2) {
                    // Date-level ticks: show "Jan 15" etc.
                    return `${month} ${day}`;
                }
                // Time-level ticks: show 12-hour format
                let h = d.getUTCHours();
                const m = d.getUTCMinutes();
                const ampm = h >= 12 ? 'PM' : 'AM';
                h = h % 12 || 12;
                return `${h}:${m.toString().padStart(2, '0')} ${ampm}`;
            },
        },
        localization: {
            timeFormatter: (time) => {
                // Crosshair tooltip time format (12-hour)
                const d = new Date(time * 1000);
                const month = d.toLocaleString('en-US', { month: 'short', timeZone: 'UTC' });
                const day = d.getUTCDate();
                let h = d.getUTCHours();
                const m = d.getUTCMinutes();
                const ampm = h >= 12 ? 'PM' : 'AM';
                h = h % 12 || 12;
                return `${month} ${day}, ${h}:${m.toString().padStart(2, '0')} ${ampm}`;
            },
        },
    });

    indicatorSeries = chart.addHistogramSeries({
        color: '#22c55e',
        priceFormat: { type: 'volume' },
        priceScaleId: 'indicators',
    });

    chart.priceScale('indicators').applyOptions({
        scaleMargins: {
            top: 0.80,   // Reserve top 80% (stay at bottom)
            bottom: 0,
        },
    });

    // Read candle colors from the active theme
    const activeThemeId = window.ThemeEngine ? window.ThemeEngine.getActiveThemeId() : 'obsidian';
    const activeTheme = window.ThemeEngine ? window.ThemeEngine.THEMES[activeThemeId] || window.ThemeEngine.THEMES.obsidian : null;
    const candleUpColor = activeTheme ? activeTheme.candleUp : '#2dd4bf';
    const candleDownColor = activeTheme ? activeTheme.candleDown : '#f43f5e';

    candleSeries = chart.addCandlestickSeries({
        upColor: candleUpColor,
        downColor: candleDownColor,
        borderVisible: false,
        wickUpColor: candleUpColor,
        wickDownColor: candleDownColor,
    });

    candleSeries.priceScale().applyOptions({
        scaleMargins: {
            top: 0.1,    // 10% gap from top
            bottom: 0.05, // 5% gap from bottom (Eliminate dead zone)
        },
    });

    // EMA Line (21-period, hidden by default)
    emaSeries = chart.addLineSeries({
        color: '#fbbf24', // Amber
        lineWidth: 2,
        visible: false,
        priceLineVisible: false,
        lastValueVisible: false,
    });

    // SMA Line (50-period, hidden by default)
    smaSeries = chart.addLineSeries({
        color: '#a855f7', // Purple
        lineWidth: 2,
        visible: false,
        priceLineVisible: false,
        lastValueVisible: false,
    });

    // EMA 200 (slate gray, solid, hidden by default)
    ema200Series = chart.addLineSeries({
        color: '#94a3b8', // Slate-400
        lineWidth: 2,
        visible: false,
        priceLineVisible: false,
        lastValueVisible: false,
    });

    // Bollinger Bands (hidden by default)
    bbUpperSeries = chart.addLineSeries({
        color: 'rgba(34, 211, 238, 0.6)', // Cyan
        lineWidth: 1,
        visible: false,
        priceLineVisible: false,
        lastValueVisible: false,
    });
    bbMiddleSeries = chart.addLineSeries({
        color: 'rgba(34, 211, 238, 0.3)', // Faint cyan
        lineWidth: 1,
        lineStyle: 2, // Dashed
        visible: false,
        priceLineVisible: false,
        lastValueVisible: false,
    });
    bbLowerSeries = chart.addLineSeries({
        color: 'rgba(34, 211, 238, 0.6)', // Cyan
        lineWidth: 1,
        visible: false,
        priceLineVisible: false,
        lastValueVisible: false,
    });

    // VWAP (orange, hidden by default)
    vwapSeries = chart.addLineSeries({
        color: '#f97316', // Orange-500
        lineWidth: 2,
        visible: false,
        priceLineVisible: false,
        lastValueVisible: false,
    });

    // RSI (14, separate pane, hidden by default)
    rsiSeries = chart.addLineSeries({
        color: '#f43f5e', // Rose-500
        lineWidth: 2,
        visible: false,
        priceLineVisible: false,
        lastValueVisible: false,
        priceScaleId: 'rsi',
    });
    chart.priceScale('rsi').applyOptions({
        scaleMargins: { top: 0.85, bottom: 0 },
        visible: false,
    });

    // OHLC Legend overlay — shows O/H/L/C/V on crosshair hover
    const ohlcLegend = document.createElement('div');
    ohlcLegend.id = 'ohlc-legend';
    ohlcLegend.style.cssText = 'position:absolute;top:4px;left:8px;z-index:30;font-family:Inter,monospace;font-size:11px;color:#94a3b8;pointer-events:none;opacity:0.85;';
    chartContainer.style.position = 'relative';
    chartContainer.appendChild(ohlcLegend);

    chart.subscribeCrosshairMove((param) => {
        if (!param || !param.time || !param.seriesData) {
            ohlcLegend.innerHTML = '';
            return;
        }
        const bar = param.seriesData.get(candleSeries);
        if (!bar) { ohlcLegend.innerHTML = ''; return; }
        const o = bar.open, h = bar.high, l = bar.low, c = bar.close;
        const dp = o > 100 ? 2 : (o > 1 ? 4 : 5); // Auto decimal places
        const chg = c - o;
        const chgPct = o !== 0 ? ((chg / o) * 100).toFixed(2) : '0.00';
        const chgColor = chg >= 0 ? '#22c55e' : '#ef4444';
        ohlcLegend.innerHTML = `<span style="color:#64748b">O</span> ${o.toFixed(dp)}  <span style="color:#64748b">H</span> ${h.toFixed(dp)}  <span style="color:#64748b">L</span> ${l.toFixed(dp)}  <span style="color:#64748b">C</span> <span style="color:${chgColor}">${c.toFixed(dp)}</span>  <span style="color:${chgColor}">${chg >= 0 ? '+' : ''}${chgPct}%</span>`;
    });

    new ResizeObserver(entries => {
        if (entries.length === 0 || !entries[0].contentRect) return;
        const width = entries[0].contentRect.width;
        const height = entries[0].contentRect.height;
        chart.applyOptions({ width, height });
    }).observe(chartContainer);

    // Dummy data removed. Waiting for 'history' from backend.
}

// Listen for theme changes to update candle colors dynamically
window.addEventListener('theme-changed', (e) => {
    const { themeId, theme } = e.detail;
    if (!candleSeries || !theme) return;

    const upColor = theme.candleUp || '#2dd4bf';
    const downColor = theme.candleDown || '#f43f5e';

    candleSeries.applyOptions({
        upColor,
        downColor,
        wickUpColor: upColor,
        wickDownColor: downColor,
    });

    // Re-color existing volume bars
    if (indicatorSeries && candleData.length > 0) {
        const volumeData = candleData.map(c => ({
            time: c.time,
            value: 0, // volume data isn't stored in candleData, so just recolor next refresh
            color: c.close >= c.open ? upColor : downColor,
        }));
        // Volume will naturally re-color on next data refresh
    }

    console.log(`[CHART] Candle colors updated: up=${upColor}, down=${downColor}`);
});

function subscribeToAsset(symbol, tf) {
    console.log(`[SUBSCRIBE] Attempting to subscribe to ${symbol} (${tf}). WS state: ${ws ? ws.readyState : 'null'}`);
    if (ws && ws.readyState === WebSocket.OPEN) {
        console.log(`[SUBSCRIBE] Sending subscription request for ${symbol} (${tf})...`);
        ws.send(JSON.stringify({ type: 'subscribe', symbol, tf }));
    } else {
        console.warn(`[SUBSCRIBE] WebSocket not open. Cannot subscribe to ${symbol}`);
    }
}

// [WEBSOCKET] Connect to Python Backend
let ws;
let WS_URL = 'ws://localhost:8080/ws';

async function connectWebSocket() {
    try {
        const env = await window.api.invoke('read-env');
        if (env.GUI_WS_URL) {
            WS_URL = env.GUI_WS_URL;
        }
    } catch (err) {
        console.warn("Failed to read GUI_WS_URL from .env, using default:", WS_URL);
    }

    console.log(`Connecting to Live Data Stream (${WS_URL})...`);
    ws = new WebSocket(WS_URL);

    let pingInterval;

    ws.onopen = () => {
        console.log("Connected to Live Data Stream.");
        updateStatus('connected', '--');

        // Subscribe to current UI selection on open
        const symbol = document.getElementById('chart-symbol-label')?.innerText;
        const tf = document.getElementById('chart-tf-label')?.innerText || '15m';
        if (symbol) subscribeToAsset(symbol, tf);

        // Start Ping-Pong
        if (pingInterval) clearInterval(pingInterval);
        pingInterval = setInterval(() => {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws._lastPing = Date.now();
                ws.send(JSON.stringify({ type: 'ping' }));
            }
        }, 5000);

        // Periodic candle tick to keep chart live
        // Sends a lightweight 'tick' request that fetches only 2 candles
        // and updates the current bar smoothly (instead of full 200-candle history reload)
        if (window._chartRefreshInterval) clearInterval(window._chartRefreshInterval);
        window._chartRefreshInterval = setInterval(() => {
            if (ws && ws.readyState === WebSocket.OPEN) {
                const sym = document.getElementById('chart-symbol-label')?.innerText?.trim();
                const tf = document.getElementById('chart-tf-label')?.innerText?.trim() || '15m';
                if (sym) {
                    ws.send(JSON.stringify({ type: 'tick', symbol: sym, tf }));
                }
            }
        }, 3000); // Tick every 3 seconds for live price movement
    };

    ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);



            if (msg.type === 'pong') {
                if (ws._lastPing) {
                    const latency = Date.now() - ws._lastPing;
                    if (statusLatency) statusLatency.textContent = `${latency}ms`;
                }
            } else if (msg.type === 'history') {
                const currentSym = (document.getElementById('chart-symbol-label')?.innerText || "").trim().toUpperCase();
                const currentTfRaw = (document.getElementById('chart-tf-label')?.innerText || '15m').trim();
                const normalizeTf = (t) => t.toLowerCase().trim();

                if (msg.symbol === currentSym && normalizeTf(msg.tf) === normalizeTf(currentTfRaw)) {
                    console.log(`[CHART] Received history for ${msg.symbol} ${msg.tf} (${msg.data.length} candles).`);

                    const fixedData = msg.data.map(c => ({
                        time: utcToLocal(c.time),
                        open: c.open, high: c.high, low: c.low, close: c.close
                    }));
                    // Store raw data with volume for VWAP
                    rawCandleData = msg.data.map(c => ({
                        time: utcToLocal(c.time),
                        open: c.open, high: c.high, low: c.low, close: c.close,
                        volume: c.volume || 0
                    }));
                    candleData = fixedData;
                    // Apply Heikin-Ashi if active
                    const displayData = chartMode === 'heikinashi' ? calculateHeikinAshi(fixedData) : fixedData;
                    candleSeries.setData(displayData);

                    if (indicatorSeries) {
                        // Use theme candle colors for volume bars
                        const themeNow = window.ThemeEngine ? window.ThemeEngine.THEMES[window.ThemeEngine.getActiveThemeId()] : null;
                        const volUp = (themeNow && themeNow.candleUp) || '#2dd4bf';
                        const volDown = (themeNow && themeNow.candleDown) || '#f43f5e';
                        const volumeData = msg.data.map(c => {
                            const isUp = c.close >= c.open;
                            return {
                                time: utcToLocal(c.time),
                                value: c.volume || 0,
                                color: isUp ? volUp : volDown
                            };
                        });
                        console.log(`[CHART-VOLUME] Setting ${volumeData.length} volume bars. Sample:`, volumeData[volumeData.length - 1]);
                        indicatorSeries.setData(volumeData);
                    }

                    updateIndicators();

                    const msgSym = msg.symbol.toUpperCase();
                    if (previousSymbol !== msgSym) {
                        clearTradeMarkers();
                        previousSymbol = msgSym;
                    }

                    tradeMarkers = markerCache[msgSym] || [];
                    if (candleSeries) {
                        candleSeries.setMarkers(tradeMarkers);
                    }

                    if (lastHoldings && lastHoldings.positions) {
                        const pos = parsePositionFromHoldings(lastHoldings.positions, msg.symbol);
                        if (pos) {
                            updatePositionLines(pos);
                        }
                    }

                    chart.timeScale().fitContent();
                }
            } else if (msg.type === 'candle') {
                const currentSym = (document.getElementById('chart-symbol-label')?.innerText || "").trim().toUpperCase();
                const currentTfRaw = (document.getElementById('chart-tf-label')?.innerText || '15m').trim();
                const normalizeTf = (t) => t.toLowerCase().trim();
                const symMatch = msg.symbol === currentSym;
                const tfMatch = normalizeTf(msg.tf) === normalizeTf(currentTfRaw);

                if (symMatch && tfMatch) {
                    const localTime = utcToLocal(msg.data.time);

                    // Guard: skip candles older than the chart's last known bar
                    const lastTime = candleData.length > 0 ? candleData[candleData.length - 1].time : 0;
                    if (localTime < lastTime) {
                        console.warn(`[CHART] Stale candle skipped: candle=${localTime} < chart=${lastTime} (diff=${lastTime - localTime}s)`);
                        return;
                    }

                    const newBar = {
                        time: localTime,
                        open: msg.data.open, high: msg.data.high, low: msg.data.low, close: msg.data.close
                    };
                    const newRawBar = { ...newBar, volume: msg.data.volume || 0 };

                    // Keep candleData and rawCandleData in sync for indicator calculations
                    if (candleData.length > 0 && candleData[candleData.length - 1].time === localTime) {
                        candleData[candleData.length - 1] = newBar;
                        if (rawCandleData.length > 0) rawCandleData[rawCandleData.length - 1] = newRawBar;
                    } else {
                        candleData.push(newBar);
                        rawCandleData.push(newRawBar);
                    }

                    // Update the chart — apply HA transform if active
                    try {
                        if (chartMode === 'heikinashi') {
                            candleSeries.setData(calculateHeikinAshi(candleData));
                        } else {
                            candleSeries.update(newBar);
                        }
                    } catch (e) {
                        console.warn(`[CANDLE-RX] update() failed, falling back to setData: ${e.message}`);
                        const displayData = chartMode === 'heikinashi' ? calculateHeikinAshi(candleData) : candleData;
                        candleSeries.setData(displayData);
                    }

                    // Update indicators on each new candle
                    updateIndicators();

                    if (indicatorSeries && typeof msg.data.volume !== 'undefined') {
                        const isUp = msg.data.close >= msg.data.open;
                        const themeNow = window.ThemeEngine ? window.ThemeEngine.THEMES[window.ThemeEngine.getActiveThemeId()] : null;
                        const volUp = (themeNow && themeNow.candleUp) || '#2dd4bf';
                        const volDown = (themeNow && themeNow.candleDown) || '#f43f5e';
                        try {
                            indicatorSeries.update({
                                time: localTime,
                                value: msg.data.volume,
                                color: isUp ? volUp : volDown
                            });
                        } catch (e) {
                            console.warn(`[CHART] Volume update failed: ${e.message}`);
                        }
                    }
                }
            } else if (msg.type === 'log') {
                parseLogLine(msg.data);
                appendLog(msg.level || "INFO", msg.data);
            } else if (msg.type === 'state') {
                const data = msg.data;
                if (data.pnl_stats && data.pnl_stats[pnlTimeframe] !== undefined) {
                    currentRealizedPnL = parseFloat(data.pnl_stats[pnlTimeframe]);
                    refreshMainPnlDisplay();
                }
                if (data.capital !== undefined) {
                    const capitalEl = document.getElementById('account-capital');
                    if (capitalEl) capitalEl.innerText = data.capital.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                    // Store live capital for analytics.js to use (prevents stale ledger override)
                    window.__liveCapital = data.capital;
                    // Sync "Capital Now" stat card with live value
                    const capNowEl = document.getElementById('metric-capital-end');
                    if (capNowEl) capNowEl.innerText = '$' + data.capital.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                    // Seed "Capital Start" if still at default $0.00
                    const capStartEl = document.getElementById('metric-capital-start');
                    if (capStartEl && (capStartEl.innerText === '$0.00' || capStartEl.innerText === '$0')) {
                        capStartEl.innerText = '$' + data.capital.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                    }
                    // Update Net Change
                    const capChangeEl = document.getElementById('metric-capital-change');
                    if (capChangeEl && capStartEl) {
                        const startVal = parseFloat(capStartEl.innerText.replace(/[$,]/g, '')) || 0;
                        const change = data.capital - startVal;
                        capChangeEl.innerText = (change >= 0 ? '+' : '') + '$' + change.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                        capChangeEl.style.color = change >= 0 ? '#2dd4bf' : '#f87171';
                    }
                }
                if (data.cash !== undefined) {
                    const cashEl = document.getElementById('account-cash');
                    if (cashEl) cashEl.innerText = data.cash.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                }
                if (data.profile) {
                    const profileEl = document.getElementById('status-profile');
                    if (profileEl) {
                        profileEl.innerText = data.profile.toUpperCase();
                        profileEl.className = "text-xs text-emerald-400 font-bold drop-shadow-sm";
                    }
                }
                if (data.is_sabbath !== undefined) {
                    const sabbathEl = document.getElementById('status-sabbath');
                    if (sabbathEl) {
                        if (data.is_sabbath) sabbathEl.classList.remove('hidden');
                        else sabbathEl.classList.add('hidden');
                    }
                    // Show/hide the Reset Paper button in analytics
                    const resetBtn = document.getElementById('btn-reset-paper');
                    if (resetBtn) {
                        if (data.is_sabbath) {
                            resetBtn.classList.remove('hidden');
                            resetBtn.classList.add('flex');
                        } else {
                            resetBtn.classList.add('hidden');
                            resetBtn.classList.remove('flex');
                        }
                    }
                }
                if (data.symbols && Array.isArray(data.symbols) && data.symbols.length > 0) {
                    WATCHED_SYMBOLS.splice(0, WATCHED_SYMBOLS.length, ...data.symbols);
                    const currentSym = document.getElementById('chart-symbol-label')?.innerText;
                    const newIdx = WATCHED_SYMBOLS.indexOf(currentSym);
                    if (newIdx !== -1) currentSymbolIndex = newIdx;
                    else {
                        currentSymbolIndex = 0;
                        updateSymbolDisplay();
                    }
                }
                saveState();
            } else if (msg.type === 'ai_commentary') {
                updateAIInsightPanel(msg.content, msg.timestamp, msg.next_update_in);
            }
        } catch (e) {
            console.error("WS Parse Error", e);
        }
    };

    ws.onclose = () => {
        console.warn("Live Data Stream Disconnected. Retrying in 5s...");
        updateStatus('disconnected', '--');
        if (pingInterval) clearInterval(pingInterval);
        setTimeout(connectWebSocket, 5000);
    };

    ws.onerror = (err) => {
        console.error("WS Error", err);
        ws.close();
    };
}

// Start WS
// Initialized later in init()

function generateDummyData(interval = 900) {
    let res = [];
    const tzOffsetSeconds = new Date().getTimezoneOffset() * 60;
    // Current local time in seconds
    const now = Math.floor(Date.now() / 1000) - tzOffsetSeconds;

    let time = now - (300 * interval);
    let value = 1.1000;
    for (let i = 0; i < 300; i++) {
        let open = value;
        let change = (Math.random() - 0.5) * 0.0020;
        let close = value + change;
        let high = Math.max(open, close) + Math.random() * 0.0010;
        let low = Math.min(open, close) - Math.random() * 0.0010;
        res.push({
            time: time + i * interval,
            open, high, low, close
        });
        value = close;
    }
    return res;
}

// --- Indicator Calculation Functions ---
function calculateSMA(data, period) {
    const result = [];
    for (let i = period - 1; i < data.length; i++) {
        let sum = 0;
        for (let j = 0; j < period; j++) {
            sum += data[i - j].close;
        }
        result.push({ time: data[i].time, value: sum / period });
    }
    return result;
}

function calculateEMA(data, period) {
    const result = [];
    const multiplier = 2 / (period + 1);

    // Start with SMA for the first EMA value
    if (data.length < period) return result;

    let sum = 0;
    for (let i = 0; i < period; i++) {
        sum += data[i].close;
    }
    let ema = sum / period;
    result.push({ time: data[period - 1].time, value: ema });

    for (let i = period; i < data.length; i++) {
        ema = (data[i].close - ema) * multiplier + ema;
        result.push({ time: data[i].time, value: ema });
    }
    return result;
}

// --- Bollinger Bands ---
function calculateBollingerBands(data, period = 20, stdDevMultiplier = 2) {
    const upper = [], middle = [], lower = [];
    for (let i = period - 1; i < data.length; i++) {
        let sum = 0;
        for (let j = 0; j < period; j++) sum += data[i - j].close;
        const mean = sum / period;
        let sqSum = 0;
        for (let j = 0; j < period; j++) sqSum += Math.pow(data[i - j].close - mean, 2);
        const stdDev = Math.sqrt(sqSum / period);
        const t = data[i].time;
        upper.push({ time: t, value: mean + stdDevMultiplier * stdDev });
        middle.push({ time: t, value: mean });
        lower.push({ time: t, value: mean - stdDevMultiplier * stdDev });
    }
    return { upper, middle, lower };
}

// --- VWAP (Volume-Weighted Average Price) ---
function calculateVWAP(data) {
    // data must have .close and .volume (use rawCandleData)
    const result = [];
    let cumVol = 0, cumTP = 0;
    for (let i = 0; i < data.length; i++) {
        const tp = (data[i].high + data[i].low + data[i].close) / 3;
        const vol = data[i].volume || 0;
        cumVol += vol;
        cumTP += tp * vol;
        if (cumVol > 0) {
            result.push({ time: data[i].time, value: cumTP / cumVol });
        }
    }
    return result;
}

// --- RSI (Relative Strength Index) ---
function calculateRSI(data, period = 14) {
    const result = [];
    if (data.length < period + 1) return result;
    let gains = 0, losses = 0;
    for (let i = 1; i <= period; i++) {
        const change = data[i].close - data[i - 1].close;
        if (change >= 0) gains += change;
        else losses -= change;
    }
    let avgGain = gains / period;
    let avgLoss = losses / period;
    const rsi = avgLoss === 0 ? 100 : 100 - (100 / (1 + avgGain / avgLoss));
    result.push({ time: data[period].time, value: rsi });
    for (let i = period + 1; i < data.length; i++) {
        const change = data[i].close - data[i - 1].close;
        avgGain = (avgGain * (period - 1) + (change >= 0 ? change : 0)) / period;
        avgLoss = (avgLoss * (period - 1) + (change < 0 ? -change : 0)) / period;
        const r = avgLoss === 0 ? 100 : 100 - (100 / (1 + avgGain / avgLoss));
        result.push({ time: data[i].time, value: r });
    }
    return result;
}

// --- Heikin-Ashi Transformation ---
function calculateHeikinAshi(data) {
    if (!data || data.length === 0) return [];
    const result = [];
    for (let i = 0; i < data.length; i++) {
        const c = data[i];
        const haClose = (c.open + c.high + c.low + c.close) / 4;
        const haOpen = i === 0
            ? (c.open + c.close) / 2
            : (result[i - 1].open + result[i - 1].close) / 2;
        const haHigh = Math.max(c.high, haOpen, haClose);
        const haLow = Math.min(c.low, haOpen, haClose);
        result.push({ time: c.time, open: haOpen, high: haHigh, low: haLow, close: haClose });
    }
    return result;
}

function updateIndicators() {
    if (!candleData || candleData.length < 14) return;

    // EMA 21
    if (emaSeries) {
        const emaData = calculateEMA(candleData, 21);
        emaSeries.setData(emaData);
    }
    // SMA 50
    if (smaSeries) {
        const smaData = calculateSMA(candleData, 50);
        smaSeries.setData(smaData);
    }
    // EMA 200
    if (ema200Series) {
        const ema200Data = calculateEMA(candleData, 200);
        ema200Series.setData(ema200Data);
    }
    // Bollinger Bands (20, 2σ)
    if (bbUpperSeries && bbMiddleSeries && bbLowerSeries) {
        const bb = calculateBollingerBands(candleData, 20, 2);
        bbUpperSeries.setData(bb.upper);
        bbMiddleSeries.setData(bb.middle);
        bbLowerSeries.setData(bb.lower);
    }
    // VWAP (needs volume from rawCandleData)
    if (vwapSeries && rawCandleData.length > 0) {
        const vwapData = calculateVWAP(rawCandleData);
        vwapSeries.setData(vwapData);
    }
    // RSI (14)
    if (rsiSeries) {
        const rsiData = calculateRSI(candleData, 14);
        rsiSeries.setData(rsiData);
    }
}

// --- Trade Marker Functions ---
function addTradeMarker(time, isBuy, symbol, price, customText = null) {
    const sym = symbol.toUpperCase();
    if (!markerCache[sym]) markerCache[sym] = [];

    // Enhanced marker styling for better visibility
    const marker = {
        time: time,
        position: isBuy ? 'belowBar' : 'aboveBar',
        color: isBuy ? '#22c55e' : '#ef4444',
        shape: isBuy ? 'arrowUp' : 'arrowDown',
        text: customText || (isBuy ? `▶ BUY ${price?.toFixed(2) || ''}` : `◀ SELL ${price?.toFixed(2) || ''}`),
        size: 2,
    };

    console.log(`[MARKER-CACHE] Adding to ${sym}:`, marker);

    // Deduplicate: Don't add if we already have a marker at this time with this shape
    const exists = markerCache[sym].some(m => m.time === marker.time && m.shape === marker.shape);
    if (!exists) {
        markerCache[sym].push(marker);
        markerCache[sym].sort((a, b) => a.time - b.time);

        const currentSym = (document.getElementById('chart-symbol-label')?.innerText || "").trim().toUpperCase();
        if (sym === currentSym) {
            tradeMarkers = markerCache[sym];
            console.log(`[CHART-RENDER] Setting markers for ${sym} (count: ${tradeMarkers.length})`);
            if (candleSeries) {
                candleSeries.setMarkers(tradeMarkers);
            }
        }
    }
}

// Exit marker function for closed trades
function addExitMarker(time, isWin, symbol, price, pnlPct, customText = null) {
    const sym = symbol.toUpperCase();
    if (!markerCache[sym]) markerCache[sym] = [];

    const pnlStr = pnlPct ? `${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(1)}%` : '';
    const marker = {
        time: time,
        position: 'aboveBar',
        color: isWin ? '#10b981' : '#f43f5e',  // Emerald for win, Rose for loss
        shape: 'square',  // Square shape for exits (different from arrows for entries)
        text: customText || `EXIT ${price?.toFixed(2) || ''} ${pnlStr}`,
        size: 2,
    };

    const exists = markerCache[sym].some(m => m.time === marker.time && m.shape === marker.shape);
    if (!exists) {
        markerCache[sym].push(marker);
        markerCache[sym].sort((a, b) => a.time - b.time);

        const currentSym = (document.getElementById('chart-symbol-label')?.innerText || "").trim().toUpperCase();
        if (sym === currentSym) {
            tradeMarkers = markerCache[sym];
            if (candleSeries) {
                candleSeries.setMarkers(tradeMarkers);
            }
        }
    }
}

function clearTradeMarkers() {
    tradeMarkers = [];
    if (candleSeries) {
        candleSeries.setMarkers([]);
    }
}

// --- Position Line Functions ---
function updatePositionLines(position) {
    // Always clear existing lines first to prevent duplicates
    clearPositionLines();

    if (!candleSeries || !position) {
        return;
    }

    const currentSym = (document.getElementById('chart-symbol-label')?.innerText || "").trim().toUpperCase();
    if (position.symbol?.toUpperCase() !== currentSym) {
        return;
    }

    currentPosition = position;

    // Entry is shown as an ARROW MARKER (positioned on the correct candle)
    // SL and TP are shown as horizontal lines

    // Stop Loss Line (Red)
    if (position.sl) {
        stopLossLine = candleSeries.createPriceLine({
            price: position.sl,
            color: '#ef4444',
            lineWidth: 2,
            lineStyle: 2, // Dashed
            axisLabelVisible: true,
            title: `SL @ ${position.sl.toFixed(4)}`,
        });
    }

    // Take Profit Line (Green)
    if (position.tp) {
        takeProfitLine = candleSeries.createPriceLine({
            price: position.tp,
            color: '#22c55e',
            lineWidth: 2,
            lineStyle: 2, // Dashed
            axisLabelVisible: true,
            title: `TP @ ${position.tp.toFixed(4)}`,
        });
    }

    console.log(`[CHART] Drew position lines for ${position.symbol}: SL=${position.sl}, TP=${position.tp}`);
}

function clearPositionLines() {
    if (candleSeries) {
        // Remove existing price lines if they exist
        if (entryPriceLine) {
            candleSeries.removePriceLine(entryPriceLine);
            entryPriceLine = null;
        }
        if (stopLossLine) {
            candleSeries.removePriceLine(stopLossLine);
            stopLossLine = null;
        }
        if (takeProfitLine) {
            candleSeries.removePriceLine(takeProfitLine);
            takeProfitLine = null;
        }
    }
    currentPosition = null;
}

function parsePositionFromHoldings(holdings, symbol) {
    if (!holdings || !Array.isArray(holdings)) return null;

    const pos = holdings.find(h => h.symbol?.toUpperCase() === symbol.toUpperCase());
    if (!pos) return null;

    return {
        symbol: pos.symbol,
        side: pos.side || pos.direction,
        entry: pos.entry_price || pos.avg_price,
        entryTime: pos.opened_at || pos.entry_time,  // ISO timestamp
        sl: pos.stop_loss || pos.sl,
        tp: pos.take_profit || pos.tp,
        size: Math.abs(pos.size || 0),
    };
}

// --- Log Formatting Logic ---
function formatLogMessage(msg) {
    let formatted = msg;
    // Strip timestamps like [10:00:00] or 2024-01-01 10:00:00
    formatted = formatted.replace(/^\[\d{2}:\d{2}:\d{2}\]\s*/, "");
    formatted = formatted.replace(/^\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}[,\.]\d+\s*/, "");

    const labels = {
        'INFO': 'text-blue-500 font-bold',
        'SUCCESS': 'text-green-500 font-bold',
        'WARNING': 'text-yellow-500 font-bold',
        'ERROR': 'text-red-500 font-bold',
        'CRITICAL': 'text-red-600 font-black italic',
        'SYSTEM': 'text-slate-500',
        'STRUCTURE': 'text-teal-500 font-bold',
        'DECISION': 'text-purple-500 font-bold',
        'HOLDINGS': 'text-orange-500 font-bold',
        'STATE': 'text-slate-400 font-bold',
        'FIX': 'text-cyan-400',
        'BLOCKED': 'text-red-500 underline'
    };

    for (const [tag, color] of Object.entries(labels)) {
        const regex = new RegExp(`\\[${tag}\\]`, 'g');
        formatted = formatted.replace(regex, `<span class="${color}">[${tag}]</span>`);
    }

    formatted = formatted.replace(/\b(BUY|LONG|ENTER_LONG|A\+)\b/gi, '<span class="text-green-400 font-black">$1</span>');
    formatted = formatted.replace(/\b(SELL|SHORT|ENTER_SHORT)\b/gi, '<span class="text-red-500 font-black">$1</span>');
    formatted = formatted.replace(/(\$\s?[\d\.,]+)/g, '<span class="text-teal-400">$1</span>');

    return formatted;
}

function appendLog(level, rawMessage) {
    if (!logTerminal) {
        logTerminal = document.getElementById('log-terminal');
        if (!logTerminal) return;
    }
    const div = document.createElement('div');
    const ts = new Date().toLocaleTimeString('en-US', { hour12: false });

    if (level === 'GUI') {
        div.className = "log-line py-1 px-2 my-1 rounded bg-amber-500/10 border-l-2 border-amber-500/50 text-amber-200/90 font-bold";
        div.innerHTML = `<span class="text-amber-500/60 font-mono text-[10px] mr-2">[GUI]</span> ${rawMessage}`;
    } else {
        div.className = "log-line text-white/90 py-0.5";
        div.innerHTML = `<span class="text-slate-600 font-mono">[${ts}]</span> ${formatLogMessage(rawMessage)}`;
    }

    logTerminal.appendChild(div);
    if (logTerminal.children.length > 300) logTerminal.removeChild(logTerminal.firstChild);
    logTerminal.scrollTop = logTerminal.scrollHeight;
}

// --- AI Commentary Panel Logic ---
let aiCommentaryTimer = null;
let aiNextUpdateCountdown = 0;

function updateAIInsightPanel(content, timestamp, nextUpdateIn) {
    const scroller = document.getElementById('insight-scroller');
    if (!scroller || !content) return;

    // Clear placeholder and existing content
    scroller.innerHTML = '';

    // Parse markdown-like formatting from AI response
    const lines = content.split('\n');
    let currentSection = null;
    let sectionContent = [];

    const createBubble = (title, text, icon, colorClass) => {
        const bubble = document.createElement('div');
        bubble.className = `insight-bubble bg-black/40 border border-${colorClass}-500/30 rounded-xl p-4 backdrop-blur-sm`;
        bubble.innerHTML = `
            <div class="flex items-start gap-3">
                <span class="material-symbols-outlined text-${colorClass}-400 text-lg mt-0.5">${icon}</span>
                <div class="flex-1">
                    <div class="text-[10px] font-bold uppercase tracking-wider text-${colorClass}-400 mb-1">${title}</div>
                    <div class="text-xs text-slate-300 leading-relaxed">${text}</div>
                </div>
            </div>
        `;
        return bubble;
    };

    // Parse sections from AI content
    const sections = [];
    let current = { title: 'Market Update', content: [], icon: 'insights', color: 'teal' };

    for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;

        // Detect section headers by emoji markers
        if (trimmed.includes('📊') || trimmed.toLowerCase().includes("what's happening")) {
            if (current.content.length > 0) sections.push({ ...current });
            current = { title: "What's Happening Now", content: [], icon: 'trending_up', color: 'teal' };
        } else if (trimmed.includes('📈') || trimmed.toLowerCase().includes('chart breakdown')) {
            if (current.content.length > 0) sections.push({ ...current });
            current = { title: 'Chart Breakdown', content: [], icon: 'show_chart', color: 'cyan' };
        } else if (trimmed.includes('🎯') || trimmed.toLowerCase().includes('watching')) {
            if (current.content.length > 0) sections.push({ ...current });
            current = { title: "What I'm Watching", content: [], icon: 'visibility', color: 'purple' };
        } else if (trimmed.includes('⚠️') || trimmed.toLowerCase().includes('heads up')) {
            if (current.content.length > 0) sections.push({ ...current });
            current = { title: 'Heads Up', content: [], icon: 'warning', color: 'amber' };
        } else {
            // Clean up markdown formatting
            let cleaned = trimmed.replace(/\*\*/g, '').replace(/^\s*[-•]\s*/, '• ');
            current.content.push(cleaned);
        }
    }
    if (current.content.length > 0) sections.push(current);

    // Render sections as bubbles
    for (const section of sections) {
        const bubble = createBubble(section.title, section.content.join('<br>'), section.icon, section.color);
        scroller.appendChild(bubble);
    }

    // Add update timer footer
    const footer = document.createElement('div');
    footer.className = 'insight-footer flex items-center justify-between text-[10px] text-slate-500 pt-3 border-t border-white/5 mt-4';
    footer.innerHTML = `
        <span class="flex items-center gap-1">
            <span class="material-symbols-outlined text-xs">schedule</span>
            Updated ${timestamp}
        </span>
        <span id="ai-countdown" class="text-teal-500/70">Next update in ${Math.floor(nextUpdateIn / 60)}m</span>
    `;
    scroller.appendChild(footer);

    // Start countdown timer
    if (aiCommentaryTimer) clearInterval(aiCommentaryTimer);
    aiNextUpdateCountdown = nextUpdateIn;
    aiCommentaryTimer = setInterval(() => {
        aiNextUpdateCountdown--;
        const countdownEl = document.getElementById('ai-countdown');
        if (countdownEl && aiNextUpdateCountdown > 0) {
            const mins = Math.floor(aiNextUpdateCountdown / 60);
            const secs = aiNextUpdateCountdown % 60;
            countdownEl.textContent = mins > 0 ? `Next update in ${mins}m ${secs}s` : `Next update in ${secs}s`;
        } else if (countdownEl) {
            countdownEl.textContent = 'Updating soon...';
            clearInterval(aiCommentaryTimer);
        }
    }, 1000);
}

// --- Decisions Logic ---
function getScoreGrade(score) {
    if (score === null || score === undefined) return "N/A";
    if (score >= 97) return "A+";
    if (score >= 93) return "A";
    if (score >= 90) return "A-";
    if (score >= 87) return "B+";
    if (score >= 83) return "B";
    if (score >= 80) return "B-";
    if (score >= 77) return "C+";
    if (score >= 70) return "C";
    if (score >= 60) return "D";
    return "F";
}

function getScoreColor(grade) {
    if (grade === "N/A") return "text-slate-600";
    if (grade.startsWith('A')) return "text-green-400 text-glow";
    if (grade.startsWith('B')) return "text-cyan-400 text-glow-sm";
    if (grade.startsWith('C')) return "text-yellow-400";
    if (grade.startsWith('D')) return "text-orange-400";
    return "text-red-500";
}

function addDecisionRow(symbol, action, scoreNum, reason, forcedGrade = null, strategyName = null) {
    const table = document.getElementById('decisions-table');
    if (!table) return;

    // DE-DUPLICATE: Find existing row for this symbol
    let existingRow = null;
    for (let row of table.rows) {
        if (row.cells[1].innerText === symbol) {
            existingRow = row;
            break;
        }
    }

    const row = existingRow || document.createElement('tr');
    row.className = "hover:bg-cyan-500/5 transition-colors border-b border-slate-700/20";
    row.setAttribute('data-score', scoreNum !== null && scoreNum !== undefined ? scoreNum : -1);

    // Time AM/PM
    const time = new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', second: '2-digit', hour12: true });

    // Grade
    const grade = forcedGrade || getScoreGrade(scoreNum);
    const scoreClass = getScoreColor(grade);

    // Strategy Badge
    let stratBadge = '';
    if (strategyName && strategyName !== 'Unknown' && strategyName !== 'N/A') {
        const sName = strategyName.toUpperCase().replace(/\s+/g, '');
        const badgeColors = {
            'ROBOCOP': 'bg-blue-500/20 text-blue-400 border-blue-500/40',
            'RUBBERBANDREAPER': 'bg-purple-500/20 text-purple-400 border-purple-500/40',
            'ROBOTEVOLUTION': 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40',
            'EVOLUTION': 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40',
            'META-SCI': 'bg-amber-500/20 text-amber-400 border-amber-500/40',
            'META_SCI': 'bg-amber-500/20 text-amber-400 border-amber-500/40',
            'METASCI': 'bg-amber-500/20 text-amber-400 border-amber-500/40',
        };
        const badgeColor = badgeColors[sName] || 'bg-slate-500/20 text-slate-400 border-slate-500/40';
        stratBadge = `<span class="inline-block px-1.5 py-0.5 text-[10px] font-bold rounded border ${badgeColor} mr-1">${strategyName.replace(/([a-z])([A-Z])/g, '$1 $2').toUpperCase()}</span>`;
    }

    // Action Styling
    let actionHtml = `<span class="text-slate-500">${action}</span>`;
    const actUpper = action.toUpperCase();
    if (actUpper === "ENTER_LONG" || actUpper === "BUY" || actUpper === "ENTRY" || actUpper === "FILL") {
        actionHtml = `<span class="text-green-400 font-bold text-glow-sm">${actUpper}</span>`;
    } else if (actUpper === "ENTER_SHORT" || actUpper === "SELL" || actUpper === "EXIT") {
        actionHtml = `<span class="text-red-500 font-bold text-glow-sm">${actUpper}</span>`;
    } else if (actUpper === "HOLD" || actUpper === "WAIT" || actUpper === "CONTINUATION") {
        actionHtml = `<span class="text-slate-400 font-bold text-glow-sm">${actUpper}</span>`;
    } else {
        actionHtml = `<span class="text-cyan-400 font-bold text-glow-sm">${actUpper}</span>`;
    }

    // Clean reason text: strip redundant strategy name prefix when badge already shows it
    let displayReason = reason || '';
    if (stratBadge) {
        // Remove "Meta-SCI Tournament: " or "Meta-SCI: " prefix since badge already identifies the strategy
        displayReason = displayReason.replace(/^Meta-SCI\s*(Tournament)?:\s*/i, '');
    }

    // Much larger font (text-lg / 18px), bunched rows (py-1.5)
    row.innerHTML = `
        <td class="px-4 py-1.5 text-slate-500 text-left font-mono text-sm">${time}</td>
        <td class="px-4 py-1.5 font-bold text-slate-200 text-left text-lg">${symbol}</td>
        <td class="px-4 py-1.5 text-left text-sm uppercase tracking-wider">${actionHtml}</td>
        <td class="px-4 py-1.5 ${scoreClass} text-left font-black text-lg">${grade}</td>
        <td class="px-4 py-1.5 text-center">${stratBadge || '<span class="text-slate-600 text-[10px]">—</span>'}</td>
        <td class="px-4 py-1.5 text-slate-400 text-sm italic text-left">${displayReason}</td>
    `;

    if (!existingRow) {
        table.appendChild(row);
    }

    // Re-sort all rows: highest score at top
    const rows = Array.from(table.rows);
    rows.sort((a, b) => {
        const sa = parseFloat(a.getAttribute('data-score') || -1);
        const sb = parseFloat(b.getAttribute('data-score') || -1);
        return sb - sa;
    });
    rows.forEach(r => table.appendChild(r));
}

// --- IPC / Socket Logic ---
let capitalDisplayMode = 'equity';
window.api.on('env-updated', (updates) => {
    console.log("[UI] Environment updated:", updates);
    if (updates.GUI_CAPITAL_DISPLAY_MODE) {
        capitalDisplayMode = updates.GUI_CAPITAL_DISPLAY_MODE;
        // Optionally trigger a redraw if we have data
    }
    if (updates.GUI_PNL_TIMEFRAME) {
        pnlTimeframe = updates.GUI_PNL_TIMEFRAME;
        if (typeof updateRealizedPnL === 'function') updateRealizedPnL(); else if (window.updateRealizedPnL) window.updateRealizedPnL();
    }
    if (updates.APP_PROFILE) {
        const profileEl = document.getElementById('status-profile');
        if (profileEl) {
            profileEl.innerText = updates.APP_PROFILE.toUpperCase();
            profileEl.className = "text-xs text-emerald-400 font-bold drop-shadow-sm";
            appendLog("SYSTEM", `Active Profile changed to ${updates.APP_PROFILE.toUpperCase()}`);
        }
    }
});

window.api.on('fromMain', (payload) => {
    if (payload.type === 'log-chunk') {
        // DO NOT WIPE CACHE. 
        // Wiping here causes markers to vanish when the log rotates or the bot restarts,
        // unless the log is in the current tiny 2kb buffer.

        const lines = payload.data.split('\n');
        lines.forEach(line => {
            if (line.trim()) parseLogLine(line.trim()); // Parse content but maybe don't append ALL to UI to avoid spam?
            // tailored approach: Append all to log panel, parse specifics
            appendLog("HIST", line.trim(), "FILE");
        });
    } else if (payload.type === 'log-update') {
        // Real-time update: Chunk might contain multiple lines
        const chunk = payload.line;
        if (chunk) {
            const lines = chunk.split('\n');
            lines.forEach(rawLine => {
                const line = rawLine.trim();
                if (line) {
                    parseLogLine(line);
                    appendLog("LIVE", line, "FILE");
                }
            });
        }
    } else if (payload.type === 'gui-notice') {
        const level = payload.color === 'red' ? 'ERROR' : (payload.color === 'teal' ? 'GUI' : 'SYSTEM');
        let msg = payload.message;
        if (payload.detail) msg += `: ${payload.detail}`;
        appendLog(level, msg);
    }
});

// --- Panel Rotation Logic ---
const panels = ['panel-decisions', 'panel-commentary', 'panel-holdings'];
const panelTitles = ['Decisions Panel', 'AI Insight', 'Holdings'];
let currentPanelIndex = 0;

function setupPanelRotation() {
    const titleEl = document.getElementById('panel-title');

    function showPanel(index) {
        panels.forEach((id, i) => {
            const el = document.getElementById(id);
            if (el) el.classList.toggle('hidden', i !== index);
        });
        if (titleEl) {
            titleEl.textContent = panelTitles[index];
            appendLog("SYSTEM", `Switched to ${panelTitles[index]} tab.`);
        }
    }

    document.getElementById('btn-prev-panel')?.addEventListener('click', () => {
        currentPanelIndex = (currentPanelIndex - 1 + panels.length) % panels.length;
        showPanel(currentPanelIndex);
    });

    document.getElementById('btn-next-panel')?.addEventListener('click', () => {
        currentPanelIndex = (currentPanelIndex + 1) % panels.length;
        showPanel(currentPanelIndex);
    });

    setupTableSorting();
}

function setupTableSorting() {
    const table = document.getElementById('decisions-table');
    if (!table) return;

    document.querySelectorAll('.sortable-header').forEach(th => {
        th.addEventListener('click', () => {
            const colIndex = parseInt(th.getAttribute('data-col'));
            const rows = Array.from(table.rows);
            // Simple toggle sort order
            const isAsc = th.classList.contains('asc');

            // clear others
            document.querySelectorAll('.sortable-header').forEach(h => {
                h.classList.remove('asc', 'desc', 'text-teal-300');
            });

            th.classList.toggle('asc', !isAsc);
            th.classList.toggle('desc', isAsc);
            th.classList.add('text-teal-300'); // Highlight active

            rows.sort((a, b) => {
                const aText = a.cells[colIndex].innerText.trim();
                const bText = b.cells[colIndex].innerText.trim();
                return isAsc ? bText.localeCompare(aText) : aText.localeCompare(bText);
            });

            rows.forEach(row => table.appendChild(row));
        });
    });
}


// --- Holdings Logic ---
function updateHoldingsTable(payload) {
    const tbody = document.getElementById('holdings-table-body');
    if (!tbody || !payload.positions) return;

    // Clear existing
    tbody.innerHTML = '';

    payload.positions.forEach(pos => {
        const row = document.createElement('tr');
        row.className = "border-b border-slate-700/30 hover:bg-slate-800/20 transition-colors";

        const pnlClass = (pos.unrealized_pnl >= 0) ? "text-green-400" : "text-red-500";
        const pnlSign = (pos.unrealized_pnl >= 0) ? "+" : "";

        // Determine side color/text
        const sideClass = (pos.side && pos.side.toUpperCase() === 'SHORT') ? "text-red-400" : "text-green-400";

        const rawPnl = parseFloat(pos.unrealized_pnl);
        const displayPnl = isNaN(rawPnl) ? "0.00" : rawPnl.toFixed(2);
        const displaySize = Math.abs(parseFloat(pos.size)).toFixed(4);

        row.innerHTML = `
            <td class="p-2 font-mono font-bold text-slate-200">${pos.symbol}</td>
            <td class="p-2 text-center ${sideClass} font-bold text-xs">${pos.side ? pos.side.toUpperCase() : 'LONG'}</td>
            <td class="p-2 text-right font-mono text-slate-400">${displaySize}</td>
            <td class="p-2 text-right font-mono font-bold ${pnlClass}">${pnlSign}$${displayPnl}</td>
        `;
        tbody.appendChild(row);
    });

    // Handle empty state
    if (payload.positions.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" class="p-4 text-center text-slate-500 italic text-xs">No active positions</td></tr>`;
    }

    // Update sidebar PNL
    if (payload.total_unrealized_pnl !== undefined) {
        currentUnrealizedPnL = parseFloat(payload.total_unrealized_pnl);
        refreshMainPnlDisplay();
    }

    // Cache holdings and draw SL/TP/Entry lines for current symbol
    lastHoldings = payload;
    const currentSym = (document.getElementById('chart-symbol-label')?.innerText || "").trim().toUpperCase();

    if (currentSym && payload.positions) {
        const pos = parsePositionFromHoldings(payload.positions, currentSym);


        // Draw SL/TP lines
        if (pos && (pos.sl || pos.tp)) {

            updatePositionLines(pos);
        }

        // Add entry marker from holdings entry_time
        // Arrow is placed on the candle matching the entry time if visible,
        // or on the candle with the closest price if entry is outside chart range.
        if (pos && pos.entryTime && pos.entry) {
            let entryTimeSec = utcToLocal(Math.floor(new Date(pos.entryTime).getTime() / 1000));
            const tfRaw = (document.getElementById('chart-tf-label')?.innerText || '15m').trim();
            const interval = tfToSeconds(tfRaw);
            entryTimeSec = Math.floor(entryTimeSec / interval) * interval;

            const isBuy = (pos.side === 'long');
            if (candleData && candleData.length > 0) {
                const firstCandleTime = candleData[0].time;
                const lastCandleTime = candleData[candleData.length - 1].time;

                if (entryTimeSec >= firstCandleTime && entryTimeSec <= lastCandleTime) {
                    // Entry is within chart range — find exact time match
                    let bestTime = firstCandleTime;
                    let bestDiff = Math.abs(entryTimeSec - firstCandleTime);
                    for (const c of candleData) {
                        const diff = Math.abs(c.time - entryTimeSec);
                        if (diff < bestDiff) {
                            bestDiff = diff;
                            bestTime = c.time;
                        }
                    }
                    addTradeMarker(bestTime, isBuy, currentSym, pos.entry);
                } else {
                    // Entry is outside chart time range — find the candle
                    // whose price is closest to entry price so the arrow
                    // appears at the correct Y-axis row on the grid.
                    let bestTime = candleData[0].time;
                    let bestPriceDiff = Math.abs((candleData[0].close || 0) - pos.entry);
                    for (const c of candleData) {
                        const diff = Math.abs((c.close || 0) - pos.entry);
                        if (diff < bestPriceDiff) {
                            bestPriceDiff = diff;
                            bestTime = c.time;
                        }
                    }
                    console.log(`[MARKER] Entry outside time range — placing arrow on candle at closest price (diff=${bestPriceDiff.toFixed(2)})`);
                    addTradeMarker(bestTime, isBuy, currentSym, pos.entry);
                }
            }
        }
    }
}


function parseLogLine(line) {
    if (!line) return;

    // Check for EXIT logs to trigger PnL refresh and add exit marker
    if (line.includes('[EXIT]')) {
        setTimeout(() => { if (window.updateRealizedPnL) window.updateRealizedPnL(); }, 1000); // Small delay to let filesystem sync if needed

        // Parse EXIT for exit marker with PnL
        // Expected format: [EXIT] Manual/Signal: BTCUSD +$2.50 (Pct=1.25%)
        const symbolMatch = line.match(/\[EXIT\][^:]*:\s*([A-Z0-9]+)/i) || line.match(/\[EXIT\]\s+([A-Z0-9]+)/i);
        const pnlMatch = line.match(/([+-]?\$[\d.]+)/);
        const pctMatch = line.match(/Pct=([+-]?[\d.]+)%?/i);

        if (symbolMatch) {
            let logTime = parseLogTimestamp(line);
            const tfRaw = (document.getElementById('chart-tf-label')?.innerText || '15m').trim();
            const interval = tfToSeconds(tfRaw);

            // Snap to current candle start and shift back by one
            const snappedTime = Math.floor(logTime / interval) * interval;
            logTime = snappedTime - interval;

            const pnlPct = pctMatch ? parseFloat(pctMatch[1]) : null;
            const isWin = pnlMatch ? pnlMatch[1].startsWith('+') : (pnlPct !== null && pnlPct >= 0);
            // Try to extract price from pnl dollar value for display
            const priceFromPnl = pnlMatch ? Math.abs(parseFloat(pnlMatch[1].replace('$', ''))) : null;
            addExitMarker(logTime, isWin, symbolMatch[1], priceFromPnl, pnlPct);

            // Add exits to Decisions Panel
            console.log(`[DECISION-UI] Exit logged for ${symbolMatch[1]}: ${line}`);
            const pnlStr = pnlMatch ? pnlMatch[1] : (pnlPct ? `${pnlPct.toFixed(2)}%` : '');
            addDecisionRow(symbolMatch[1], "EXIT", null, `PnL: ${pnlStr} | Price: ${priceFromPnl || '??'}`);
        }
    }

    // Check for ENTRY logs for buy markers
    if (line.includes('[ENTRY]') || line.includes('[FILL]')) {
        const symbolMatch = line.match(/\[(?:ENTRY|FILL)\]\s+([A-Z0-9]+)/i) || line.match(/symbol[=:]?\s*([A-Z0-9]+)/i);
        const priceMatch = line.match(/price[=:]?\s*([\d.]+)/i) || line.match(/@\s*([\d.]+)/);
        if (symbolMatch) {
            let logTime = parseLogTimestamp(line);
            const tfRaw = (document.getElementById('chart-tf-label')?.innerText || '15m').trim();
            const interval = tfToSeconds(tfRaw);

            // Snap to current candle start and shift back by one
            const snappedTime = Math.floor(logTime / interval) * interval;
            logTime = snappedTime - interval;

            const price = priceMatch ? parseFloat(priceMatch[1]) : null;
            addTradeMarker(logTime, true, symbolMatch[1], price);

            // Add trade entries to Decisions Panel for better visibility
            console.log(`[DECISION-UI] Entry logged for ${symbolMatch[1]}: ${line}`);
            addDecisionRow(symbolMatch[1], line.includes('[FILL]') ? "FILL" : "ENTRY", null, `Price: ${price || '??'}`);
        }
    }

    // 1. Neural Decision Matrix
    if (line.includes('[STRUCTURE]') || line.includes('Decision: Decision:') || line.includes('[DECISION]') || line.includes('[SAFETY]') || line.includes('[PHOENIX]')) {
        try {
            let content = "";
            if (line.includes('[STRUCTURE]')) content = line.split('[STRUCTURE]')[1].trim();
            else if (line.includes('Decision: Decision:')) content = line.split('Decision: Decision:')[1].trim();
            else if (line.includes('[DECISION]')) content = line.split('[DECISION]')[1].trim();
            else if (line.includes('[SAFETY]')) content = line.split('[SAFETY]')[1].trim();
            else if (line.includes('[PHOENIX]')) content = line.split('[PHOENIX]')[1].trim();

            // Handle key-value format "symbol=BTCUSD action=..."
            const parts = content.split('|');
            let head = parts[0].trim();

            let symbol = "UNKNOWN";
            // Try key-value parse first (e.g. "symbol=BTCUSD")
            const kvSymbolMatch = content.match(/symbol=([A-Z0-9]+)/i);
            if (kvSymbolMatch) {
                symbol = kvSymbolMatch[1].toUpperCase();
            } else {
                // Try "for SYMBOL:" or "Blocked SYMBOL:" format (from [SAFETY] logs)
                const forMatch = content.match(/(?:for|Blocked)\s+([A-Z][A-Z0-9]{2,})/);
                if (forMatch) {
                    symbol = forMatch[1].toUpperCase();
                } else {
                    // Fallback to old "BTCUSD | ..." format (require at least 3 uppercase chars)
                    const headMatch = head.match(/^([A-Z0-9]{3,})/);
                    if (headMatch) symbol = headMatch[1];
                }
            }

            // Skip system-level messages where no symbol could be extracted
            // (e.g. "[SAFETY] New Day Detected for crypto..." or "[SAFETY] Leverage Sentry VETO for crypto...")
            if (symbol === "UNKNOWN") {
                return;
            }

            // Search ENTIRE content for action/score/reason
            const body = content;

            let action = "HOLD";
            let score = null;
            let reason = "Evaluation complete";

            const actionMatch = body.match(/action=([^\s|]+)/i) ||
                body.match(/gate=([^\s|]+)/i) ||
                body.match(/Switched to\s+([^\s|]+)/i) ||
                body.match(/Blocked\s+([A-Z0-9]+):\s+([^\s|]+)/i);
            if (actionMatch) {
                if (line.includes('[SAFETY]') && actionMatch[2]) {
                    action = "HOLD"; // Safety blocks are always holds for now
                } else {
                    action = actionMatch[1].toUpperCase().replace("STAND_ASIDE", "HOLD").replace("STAND-ASIDE", "HOLD").replace("SWEEP", "HOLD");
                }
            } else {
                // Fallback: If no explicit key "action=", try to find standalone keywords if needed
                // But Meta-SCI logs use "action=HOLD" consistently
            }

            // Force "HOLD" to display if it comes from a Decision log
            // Previous logic might have been too strict.
            if (!actionMatch && body.includes("Decision:") && body.includes("HOLD")) {
                action = "HOLD";
            }

            const scoreMatch = body.match(/icc_score=([\d\.]+)/i) ||
                body.match(/ICC score\s+([\d\.]+)/i) ||
                body.match(/score=([\d\.]+)/i) ||
                body.match(/selection_score=([\d\.]+)/i) ||
                body.match(/\/(\d+)\s+score/i);

            if (scoreMatch) {
                let raw = parseFloat(scoreMatch[1]);
                // Heuristic: if raw is > 100, it might be raw points (e.g. 6000), scale it? 
                // The log showed 6100.0. Let's assume it's unscaled points.
                if (raw > 100) raw = raw / 100;

                if (raw <= 1.0 && (line.includes('selection_score') || body.includes('selection_score'))) score = raw * 100;
                else if (raw <= 35.0 && line.includes('/35')) score = (raw / 35.0) * 100;
                else score = raw;
            }

            const reasonMatch = body.match(/reason=([^|]+)/i) || body.match(/\(([^)]+)\)$/);
            if (reasonMatch) reason = reasonMatch[1].trim();

            const gradeMatch = body.match(/grade=([A-F][+-]?)/i);
            const forcedGrade = gradeMatch ? gradeMatch[1] : null;

            // Parse strategy-specific fields
            const stratMatch = body.match(/strategy=([^\s|]+)/i);
            const stratGradeMatch = body.match(/strat_grade=([A-F][+-]?)/i);
            const stratName = stratMatch ? stratMatch[1] : null;
            // Prefer strat_grade when available (strategy-specific); fall back to ICC grade
            const displayGrade = stratGradeMatch ? stratGradeMatch[1] : forcedGrade;


            addDecisionRow(symbol, action, score, reason, displayGrade, stratName);

            // Chart Indicator (The "Grey Bars" that should be colorful)
            const headerSym = document.getElementById('chart-symbol-label')?.innerText;
            if (indicatorSeries && symbol === headerSym) {
                const nowSec = utcToLocal(Math.floor(Date.now() / 1000));

                let color = '#475569'; // Muted grey for neutral/hold
                const act = action.toUpperCase();

                if (act.includes("LONG") || act.includes("BUY") || act.includes("BIP")) {
                    color = '#2dd4bf'; // Teal
                } else if (act.includes("SHORT") || act.includes("SELL")) {
                    color = '#f43f5e'; // Rose
                } else if (act === "CLOSE") {
                    color = '#f59e0b'; // Amber
                }

                indicatorSeries.update({ time: nowSec, value: 1, color: color });
            }
            saveState();
        } catch (e) { console.error("Decision Parsing Error:", e); }
    }

    // 2. Profile Parsing (Enhanced)
    if (line.includes('[PROFILE]') || line.includes('profile=') || line.includes('switching to')) {
        const profileMatch = line.match(/profile[:=]\s?([\w\-]+)/i) ||
            line.match(/switching to (?:profile\s+)?([\w\-]+)/i);
        if (profileMatch) {
            const prof = profileMatch[1];
            console.log("[UI-DEBUG] Parsed profile from log:", prof);
            if (!statusProfile) statusProfile = document.getElementById('status-profile');
            if (statusProfile) {
                statusProfile.innerText = prof.toUpperCase();
                statusProfile.className = "text-xs text-emerald-400 font-bold drop-shadow-sm";
            }
            saveState();
        }
    }

    // 3. P&L / Equity / Capital (Consolidated & Robust)

    // Strict Capital Logic
    // We ONLY update Capital, never PnL (which comes from [HOLDINGS])

    let isOandaProfile = false;
    const currentProfile = document.getElementById('status-profile')?.innerText?.toLowerCase() || "";
    if (currentProfile.includes("oanda") || currentProfile.includes("forex")) {
        isOandaProfile = true;
    }

    // Capital / NAV 
    // Matches: [OANDA] Account Summary: Balance=123.45, NAV=100.00
    // Matches: [CCXT] get_liquid_capital... winner=$180.83
    // Matches: [HEARTBEAT] Capital available: $100.00

    // 
    // Maintain a global map of capital by source to prevent flip-flopping
    // and show a unified "big Capital amount" as requested.
    if (!window.capitalCache) window.capitalCache = {};

    // 1. [TOTAL] Source (Aggregated by RoutedExchangeBroker - Authoritative)
    if (line.includes('[TOTAL] Liquidity available:')) {
        const totalMatch = line.match(/available: \$([\d\.,\-]+)/);
        if (totalMatch) {
            const val = parseFloat(totalMatch[1].replace(/,/g, ''));
            window.capitalCache['TOTAL'] = val;
        }
    }
    // 2. [HEARTBEAT] Source
    else if (line.includes('[HEARTBEAT] Capital available:')) {
        const hbMatch = line.match(/Capital available: \$([\d\.,\-]+)/);
        if (hbMatch) {
            const val = parseFloat(hbMatch[1].replace(/,/g, ''));
            window.capitalCache['HEARTBEAT'] = val;
        }
    }
    // 3. Broker Specifics (OANDA/CCXT/IBKR)
    else if (line.includes('[OANDA] Account Summary:')) {
        const oMatch = line.match(/NAV=([\d\.,\-]+)/);
        if (oMatch) window.capitalCache['OANDA'] = parseFloat(oMatch[1].replace(/,/g, ''));
    }
    else if (line.includes('[CCXT] get_liquid_capital')) {
        const cMatch = line.match(/winner=\$([\d\.,\-]+)/);
        if (cMatch) window.capitalCache['CCXT'] = parseFloat(cMatch[1].replace(/,/g, ''));
    }
    else if (line.includes('[IBKR] Account Summary') || line.includes('TotalCashValue=')) {
        const iMatch = line.match(/TotalCashValue=([\d\.,\-]+)/);
        if (iMatch) window.capitalCache['IBKR'] = parseFloat(iMatch[1].replace(/,/g, ''));
    }
    // 4. [CASH] Source (Raw Buying Power / Available Cash)
    else if (line.includes('[CASH] Buying Power:')) {
        const cashMatch = line.match(/Power: \$([\d\.,\-]+)/);
        if (cashMatch) {
            const val = parseFloat(cashMatch[1].replace(/,/g, ''));
            window.capitalCache['CASH'] = val;
        }
    }

    // Determine the most robust value based on user preference
    let capVal = null;
    let labelText = "Overall Capital:";

    // Check global mode (updated from env-updated)
    const displayMode = capitalDisplayMode || 'equity';

    if (displayMode === 'cash') {
        labelText = "Buying Power:";
        // Prefer explicit [CASH] log, fallback to summed broker totals if needed
        capVal = window.capitalCache['CASH'];
        if (capVal === undefined || capVal === null) {
            // Fallback to summing up individual broker cash sources
            const total = (window.capitalCache['OANDA'] || 0) +
                (window.capitalCache['CCXT'] || 0) +
                (window.capitalCache['IBKR'] || 0);
            if (total > 0) capVal = total;
        }
    } else {
        labelText = "Overall Capital:";
        // [HEARTBEAT] and [TOTAL] are now Equity-authoritative
        capVal = window.capitalCache['TOTAL'] || window.capitalCache['HEARTBEAT'];
    }

    if (capVal !== null && capVal !== undefined) {
        const capitalEl = document.getElementById('account-capital');
        const labelEl = document.getElementById('capital-label');
        if (capitalEl) {
            capitalEl.innerText = capVal.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        }
        if (labelEl) {
            labelEl.innerText = labelText;
        }
    }

    // 4. AI Insight (Timestamped Bubbles)
    if (line.includes('[COMMENTARY]') || line.includes('commentary:') || line.includes('Insight:')) {
        const textParts = line.split(/\[COMMENTARY\]|commentary:|Insight:/i);
        if (textParts.length > 1) {
            const text = textParts[1].trim().replace(/^"|"$/g, '');
            const scroller = document.getElementById('insight-scroller');
            if (scroller) {
                // Clear initial placeholder if this is the first real message
                if (scroller.querySelector('.italic.text-slate-500')) {
                    scroller.innerHTML = '';
                }

                const div = document.createElement('div');
                div.className = "insight-bubble bg-teal-500/5 border border-teal-500/20 rounded-xl p-4 mb-4 animate-in fade-in slide-in-from-bottom-2 duration-500";

                const ts = new Date().toLocaleTimeString('en-US', { hour12: false });
                div.innerHTML = `
                    <div class="flex justify-between items-center mb-2">
                        <span class="text-[9px] font-black uppercase tracking-widest text-teal-400 opacity-70">AI Signal Analysis</span>
                        <span class="text-[9px] font-mono text-slate-500">${ts}</span>
                    </div>
                    <div class="text-slate-200 text-sm leading-relaxed">${text}</div>
                `;

                scroller.appendChild(div);
                scroller.scrollTop = scroller.scrollHeight;
            }
        }
    }

    // 5. Holdings
    if (line.includes('[HOLDINGS]') || line.includes('Holdings:')) {
        try {
            const jsonPart = line.split(/\[HOLDINGS\]|Holdings:/i)[1].trim();
            const data = JSON.parse(jsonPart);
            updateHoldingsTable(data);
            saveState();
        } catch (e) {
            // Handle non-JSON lines if any
            const stateMatch = line.match(/\[STATE\]\s+(\w+)\s+open_position:\s+(\w+)/);
            if (stateMatch) {
                upsertHoldingRow(stateMatch[1], stateMatch[2]);
                saveState();
            }
        }
    }
}

function upsertHoldingRow(symbol, side) {
    const tbody = document.getElementById('holdings-table-body');
    if (!tbody) return;

    // Check if exists
    let row = Array.from(tbody.rows).find(r => r.cells[0].innerText === symbol);
    if (!row) {
        row = tbody.insertRow(0);
        row.className = "border-b border-slate-700/30 hover:bg-slate-800/20 transition-colors";
        row.innerHTML = `<td class="p-4 font-mono font-bold text-slate-200">${symbol}</td>
                         <td class="p-4 text-center font-bold text-xs"></td>
                         <td class="p-4 text-right font-mono text-slate-400">---</td>
                         <td class="p-4 text-right font-mono font-bold text-green-400">---</td>`;
    }

    const sideCell = row.cells[1];
    sideCell.innerText = side.toUpperCase();
    sideCell.className = `p-4 text-center font-bold text-xs ${side.toLowerCase() === 'short' ? 'text-red-400' : 'text-green-400'}`;
}


function updateStatus(text, latency) {
    if (statusText) statusText.textContent = `Status: ${text.toUpperCase()}`;
    if (statusLatency) statusLatency.textContent = latency;
    if (statusDot) {
        if (text.toLowerCase() === 'connected') {
            statusDot.className = "w-2.5 h-2.5 rounded-full bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.5)] animate-pulse";
        } else {
            statusDot.className = "w-2.5 h-2.5 rounded-full bg-red-500 shadow-[0_0_10px_rgba(239,68,68,0.5)]";
        }
    }
}

function setupCalendar() {
    const btn = document.getElementById('btn-calendar');
    const input = document.getElementById('date-picker-input');
    if (btn && input) {
        btn.addEventListener('click', () => {
            try { input.showPicker(); } catch (e) { input.click(); }
        });
        input.addEventListener('change', (e) => {
            appendLog("INFO", `[UI] Date selected: ${e.target.value}`, "GUI");
        });
    }
}



let botIsRunning = false;

window.api.on('bot-status', (payload) => {
    botIsRunning = payload.running;
    console.log("Bot Status Update:", botIsRunning);
    updatePanicButtonState();
});

function updatePanicButtonState() {
    const isCurrentlyHalted = document.getElementById('btn-panic')?.classList.contains('bg-emerald-500');
    // If we were in a halted state, we might want to preserve that on resume? 
    // Actually, setPanicState(isHalted) handles it.
    // If not running, force "Start" look.
    if (!botIsRunning) {
        setPanicState(true, true); // Force green, start mode
    } else {
        // If running, we rely on the halted class or the state we loaded
        // setPanicState(isHalted, isStartMode)
        const isHalted = document.getElementById('btn-panic')?.classList.contains('bg-emerald-500');
        setPanicState(isHalted, false);
    }
}

function setPanicState(isStarted, isStartMode = false) {
    const btn = document.getElementById('btn-panic');
    const text = document.getElementById('panic-text');
    if (!btn || !text) return;

    if (isStartMode) {
        btn.classList.remove('panic-stripes', 'bg-red-500', 'border-red-500/40');
        btn.classList.add('bg-emerald-500', 'border-emerald-500/40');
        text.innerText = "Start Bot";
    } else if (isStarted) {
        btn.classList.remove('panic-stripes', 'bg-red-500', 'border-red-500/40');
        btn.classList.add('bg-emerald-500', 'border-emerald-500/40');
        text.innerText = "Resume Bot";
    } else {
        btn.classList.add('panic-stripes', 'bg-red-500', 'border-red-500/40');
        btn.classList.remove('bg-emerald-500', 'border-emerald-500/40');
        text.innerText = "PANIC BUTTON -\nHALT ALL TRADING";
        text.className = "text-[12px] font-black uppercase tracking-wider relative z-10 whitespace-pre-line leading-tight drop-shadow-[0_2px_2px_rgba(0,0,0,0.8)] text-center";
    }
}

// --- Interactive Elements ---
const WATCHED_SYMBOLS = ['BTCUSD', 'ETHUSD', 'SOLUSD']; // Default to crypto, will be updated from backend
let currentSymbolIndex = 0;

let updateSymbolDisplay; // Forward declaration for use in WS sync

function setupInteractiveElements() {
    const symbolLabel = document.getElementById('chart-symbol-label');
    const tfLabel = document.getElementById('chart-tf-label');

    // Symbol Arrows
    document.getElementById('btn-prev-symbol')?.addEventListener('click', () => {
        currentSymbolIndex = (currentSymbolIndex - 1 + WATCHED_SYMBOLS.length) % WATCHED_SYMBOLS.length;
        updateSymbolDisplay();
    });
    document.getElementById('btn-next-symbol')?.addEventListener('click', () => {
        currentSymbolIndex = (currentSymbolIndex + 1) % WATCHED_SYMBOLS.length;
        updateSymbolDisplay();
    });

    updateSymbolDisplay = () => {
        if (WATCHED_SYMBOLS.length === 0) return;
        const sym = WATCHED_SYMBOLS[currentSymbolIndex];
        if (symbolLabel) {
            symbolLabel.innerHTML = `${sym}`;
        }
        appendLog("INFO", `[UI] Switched chart to ${sym}`);

        // Immediately clear chart so old candles don't linger
        // while waiting for new data (which can take 15-20 seconds)
        if (candleSeries) {
            candleSeries.setData([]);
        }
        if (indicatorSeries) {
            indicatorSeries.setData([]);
        }
        candleData = [];
        clearTradeMarkers();
        clearPositionLines();

        // REFRESH CHART DATA
        console.log(`Refreshing candlestick data for ${sym}...`);
        const tf = document.getElementById('chart-tf-label')?.innerText || '15m';

        // Use subscription instead of full re-init
        subscribeToAsset(sym, tf);
    }

    // Timeframe Buttons
    document.querySelectorAll('.timeframe-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            document.querySelectorAll('.timeframe-btn').forEach(b => {
                b.className = "timeframe-btn text-[10px] px-3 py-1 rounded-lg cursor-pointer text-slate-400 hover:text-white transition-colors";
            });
            e.target.className = "timeframe-btn text-[10px] px-3 py-1 rounded-lg bg-teal-500/20 text-teal-300 border border-teal-500/40 font-bold";

            // Reset dropdown
            const dropdown = document.getElementById('timeframe-select');
            if (dropdown) dropdown.selectedIndex = 0;

            const tf = e.target.innerText;
            if (document.getElementById('chart-tf-label')) document.getElementById('chart-tf-label').innerText = tf;

            console.log(`Switching chart to ${tf}`);
            // Clear chart immediately on TF switch
            if (candleSeries) candleSeries.setData([]);
            if (indicatorSeries) indicatorSeries.setData([]);
            candleData = [];
            const sym = document.getElementById('chart-symbol-label')?.innerText;
            if (sym) subscribeToAsset(sym, tf);
        });
    });

    // Timeframe Dropdown
    document.getElementById('timeframe-select')?.addEventListener('change', (e) => {
        const tf = e.target.value;
        if (!tf) return;

        // De-highlight standard buttons
        document.querySelectorAll('.timeframe-btn').forEach(b => {
            b.className = "timeframe-btn text-[10px] px-3 py-1 rounded-lg cursor-pointer text-slate-400 hover:text-white transition-colors";
        });

        if (document.getElementById('chart-tf-label')) document.getElementById('chart-tf-label').innerText = tf;

        console.log(`Switching chart to ${tf} via dropdown`);
        // Clear chart immediately on TF switch
        if (candleSeries) candleSeries.setData([]);
        if (indicatorSeries) indicatorSeries.setData([]);
        candleData = [];
        const sym = document.getElementById('chart-symbol-label')?.innerText;
        if (sym) subscribeToAsset(sym, tf);
    });

    // Button Handlers
    /*
    document.getElementById('pnl-main-container')?.addEventListener('click', (e) => {
        handlePnlToggle();
    });
    */

    document.getElementById('btn-panic')?.addEventListener('click', (e) => {
        if (!botIsRunning) {
            // "Start Bot" mode
            window.api.send('start-bot');
            appendLog("INFO", "[USER] START BOT SIGNAL SENT TO SYSTEM.");

            // Visual feedback for starting
            const btn = document.getElementById('btn-panic');
            const text = document.getElementById('panic-text');
            if (btn && text) {
                text.innerText = "Starting...";
                // Keep it green but maybe a bit dimmer or pulsing?
                // For now just change text.
            }
            return;
        }

        const isCurrentlyHalted = e.currentTarget.classList.contains('bg-emerald-500');
        const nextHaltedState = !isCurrentlyHalted;
        setPanicState(nextHaltedState);

        const cmd = nextHaltedState ? 'halt' : 'resume';
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'command', cmd: cmd }));
        }

        if (nextHaltedState) {
            appendLog("CRITICAL", "[USER] PANIC BUTTON ACTIVATED. HALT SIGNAL SENT.");
        } else {
            appendLog("SUCCESS", "[USER] RESUME SIGNAL SENT. BOT REINSTATING.");
        }
        saveState();
    });

    // Self-Update Button
    document.getElementById('btn-update')?.addEventListener('click', async () => {
        const btn = document.getElementById('btn-update');
        const btnText = document.getElementById('update-btn-text');
        if (!btn || !btnText) return;

        // Show updating state
        btnText.innerText = 'Updating...';
        btn.classList.add('animate-pulse');
        btn.disabled = true;
        appendLog("INFO", "[UPDATE] Applying update... Bot will restart.");

        try {
            const result = await window.api.applyUpdate();
            if (!result.success) {
                btnText.innerText = 'Update Failed';
                btn.classList.remove('animate-pulse');
                btn.disabled = false;
                appendLog("ERROR", `[UPDATE] Failed: ${result.error}`);
                setTimeout(() => { btnText.innerText = 'Retry Update'; }, 3000);
            }
            // On success, the window will reload automatically
        } catch (err) {
            btnText.innerText = 'Update Error';
            btn.classList.remove('animate-pulse');
            btn.disabled = false;
            appendLog("ERROR", `[UPDATE] Error: ${err.message}`);
        }
    });

    // Periodic update check (every 30 min + on startup)
    async function checkForUpdatesUI() {
        try {
            const result = await window.api.checkForUpdates();
            const btn = document.getElementById('btn-update');
            const btnText = document.getElementById('update-btn-text');
            if (!btn || !btnText) return;

            if (result.available) {
                btn.classList.remove('hidden');
                btn.style.display = 'flex';
                btnText.innerText = 'Update Available';
                appendLog("INFO", "[UPDATE] Update available from remote");
            } else {
                btn.classList.add('hidden');
                btn.style.display = '';
            }
        } catch (err) {
            console.warn('[UPDATE] Check failed:', err);
        }
    }

    // Check on startup after a short delay, then every 30 minutes
    setTimeout(checkForUpdatesUI, 10000);
    setInterval(checkForUpdatesUI, 30 * 60 * 1000);

    ['nav-dashboard', 'nav-profile', 'nav-settings', 'nav-graph', 'nav-help'].forEach(id => {
        document.getElementById(id)?.addEventListener('click', (e) => {
            // Remove active style from all
            ['nav-dashboard', 'nav-profile', 'nav-settings', 'nav-graph', 'nav-help'].forEach(navId => {
                const btn = document.getElementById(navId);
                if (btn) {
                    btn.className = "flex items-center gap-4 px-4 py-3.5 rounded-xl hover:bg-white/5 text-slate-400 hover:text-white transition-all text-sm font-medium";
                }
            });
            // Add to active
            e.currentTarget.className = "flex items-center gap-4 px-4 py-3.5 rounded-xl bg-teal-500/20 text-teal-300 font-bold text-sm border-2 border-teal-500/30 shadow-[0_0_20px_rgba(20,184,166,0.3)] transition-all";

            const name = e.currentTarget.innerText.trim();
            appendLog("INFO", `[UI] Switched to ${name} view.`);

            // Handle view switching
            const dashboardView = document.getElementById('view-dashboard');
            const analyticsView = document.getElementById('view-analytics');
            const profilesView = document.getElementById('view-profiles');
            const settingsView = document.getElementById('view-settings');
            const helpView = document.getElementById('view-help');

            // Hide all views first
            if (dashboardView) dashboardView.classList.add('hidden');
            if (analyticsView) analyticsView.classList.add('hidden');
            if (profilesView) profilesView.classList.add('hidden');
            if (settingsView) settingsView.classList.add('hidden');
            if (helpView) helpView.classList.add('hidden');

            if (id === 'nav-settings') {
                // Show integrated Settings view
                if (settingsView) {
                    settingsView.classList.remove('hidden');
                    // Initialize settings if not loaded
                    if (window.settingsModule && window.settingsModule.init) {
                        window.settingsModule.init();
                    }
                }
            } else if (id === 'nav-graph') {
                // Show Analytics view
                if (analyticsView) {
                    analyticsView.classList.remove('hidden');
                    if (window.analyticsModule && window.analyticsModule.refresh) {
                        window.analyticsModule.refresh();
                    }
                }
            } else if (id === 'nav-profile') {
                // Show Profiles view
                if (profilesView) {
                    profilesView.classList.remove('hidden');
                    // Initialize profiles if not loaded
                    if (window.profilesModule && window.profilesModule.init) {
                        window.profilesModule.init();
                    }
                }
            } else if (id === 'nav-dashboard') {
                // Show Dashboard view
                if (dashboardView) dashboardView.classList.remove('hidden');
            } else if (id === 'nav-help') {
                // Show Help view
                if (helpView) {
                    helpView.classList.remove('hidden');
                    if (window.helpModule && window.helpModule.init) {
                        window.helpModule.init();
                    }
                }
            }
        });
    });

    // Indicator Button & Dropdown - Portal approach for chart isolation
    const indicatorBtn = document.getElementById('btn-indicators');
    const indicatorDropdown = document.getElementById('indicator-dropdown');
    let dropdownOriginalParent = indicatorDropdown?.parentElement;

    indicatorBtn?.addEventListener('click', (e) => {
        e.stopPropagation();
        const isOpening = indicatorDropdown?.classList.contains('hidden');

        if (isOpening && indicatorDropdown) {
            // Portal dropdown to body with fixed positioning
            const btnRect = indicatorBtn.getBoundingClientRect();
            indicatorDropdown.style.position = 'fixed';
            indicatorDropdown.style.top = `${btnRect.bottom + 8}px`;
            indicatorDropdown.style.left = `${btnRect.left}px`;
            indicatorDropdown.style.zIndex = '9999';
            // Match the card glass style from the active theme
            const cs = getComputedStyle(document.documentElement);
            const bgCard = cs.getPropertyValue('--bg-card').trim() || 'rgba(15, 23, 42, 0.4)';
            const bgDark = cs.getPropertyValue('--bg-dark').trim() || '#020617';
            const cardBorder = cs.getPropertyValue('--card-border').trim() || 'rgba(255,255,255,0.06)';
            const cardBorderHover = cs.getPropertyValue('--card-border-hover').trim() || 'rgba(20,184,166,0.4)';
            indicatorDropdown.style.backgroundColor = bgDark;
            indicatorDropdown.style.background = bgCard;
            indicatorDropdown.style.border = `1px solid ${cardBorderHover}`;
            indicatorDropdown.style.borderRadius = '12px';
            indicatorDropdown.style.boxShadow = '0 25px 50px -12px rgba(0,0,0,0.6)';
            indicatorDropdown.style.backdropFilter = 'blur(20px)';
            indicatorDropdown.style.webkitBackdropFilter = 'blur(20px)';
            document.body.appendChild(indicatorDropdown);
            indicatorDropdown.classList.remove('hidden');
            console.log('[UI] Dropdown portaled to body');
        } else if (indicatorDropdown) {
            indicatorDropdown.classList.add('hidden');
        }
    });

    // Close dropdown when clicking outside and restore to original parent
    document.addEventListener('click', (e) => {
        if (indicatorDropdown && !indicatorDropdown.classList.contains('hidden')) {
            // Check if click was inside dropdown
            if (!indicatorDropdown.contains(e.target) && e.target !== indicatorBtn && !indicatorBtn?.contains(e.target)) {
                indicatorDropdown.classList.add('hidden');
                // Restore to original parent
                indicatorDropdown.style.position = '';
                indicatorDropdown.style.top = '';
                indicatorDropdown.style.left = '';
                indicatorDropdown.style.zIndex = '';
                if (dropdownOriginalParent) {
                    dropdownOriginalParent.appendChild(indicatorDropdown);
                }
                console.log('[UI] Dropdown closed and restored');
            }
        }
    });

    // Prevent dropdown from closing when clicking inside it, and stop events from reaching the chart below
    ['click', 'mousedown', 'mousemove', 'mouseup', 'mouseover'].forEach(evt => {
        indicatorDropdown?.addEventListener(evt, (e) => {
            e.stopPropagation();
        });
    });
    // EMA Toggle - Use standard 'change' event for reliable visual state
    const emaCheckbox = document.getElementById('toggle-ema');
    const smaCheckbox = document.getElementById('toggle-sma');

    emaCheckbox?.addEventListener('change', (e) => {
        console.log(`[UI] EMA Toggle changed: ${emaCheckbox.checked}, emaSeries exists: ${!!emaSeries}`);
        if (emaSeries) {
            updateIndicators();
            emaSeries.applyOptions({ visible: emaCheckbox.checked });
            appendLog("INFO", `[UI] EMA (21) ${emaCheckbox.checked ? 'enabled' : 'disabled'}`);
        }
    });

    smaCheckbox?.addEventListener('change', (e) => {
        console.log(`[UI] SMA Toggle changed: ${smaCheckbox.checked}, smaSeries exists: ${!!smaSeries}`);
        if (smaSeries) {
            updateIndicators();
            smaSeries.applyOptions({ visible: smaCheckbox.checked });
            appendLog("INFO", `[UI] SMA (50) ${smaCheckbox.checked ? 'enabled' : 'disabled'}`);
        }
    });

    // Ensure parents don't interfere with standard checkbox behavior but still stop propagation to chart
    emaCheckbox?.parentElement?.addEventListener('click', (e) => e.stopPropagation());
    smaCheckbox?.parentElement?.addEventListener('click', (e) => e.stopPropagation());

    // EMA 200 Toggle
    const ema200Checkbox = document.getElementById('toggle-ema200');
    ema200Checkbox?.addEventListener('change', () => {
        if (ema200Series) {
            updateIndicators();
            ema200Series.applyOptions({ visible: ema200Checkbox.checked });
            appendLog("INFO", `[UI] EMA (200) ${ema200Checkbox.checked ? 'enabled' : 'disabled'}`);
        }
    });
    ema200Checkbox?.parentElement?.addEventListener('click', (e) => e.stopPropagation());

    // Bollinger Bands Toggle
    const bbCheckbox = document.getElementById('toggle-bb');
    bbCheckbox?.addEventListener('change', () => {
        if (bbUpperSeries && bbMiddleSeries && bbLowerSeries) {
            updateIndicators();
            const v = bbCheckbox.checked;
            bbUpperSeries.applyOptions({ visible: v });
            bbMiddleSeries.applyOptions({ visible: v });
            bbLowerSeries.applyOptions({ visible: v });
            appendLog("INFO", `[UI] Bollinger Bands ${v ? 'enabled' : 'disabled'}`);
        }
    });
    bbCheckbox?.parentElement?.addEventListener('click', (e) => e.stopPropagation());

    // VWAP Toggle
    const vwapCheckbox = document.getElementById('toggle-vwap');
    vwapCheckbox?.addEventListener('change', () => {
        if (vwapSeries) {
            updateIndicators();
            vwapSeries.applyOptions({ visible: vwapCheckbox.checked });
            appendLog("INFO", `[UI] VWAP ${vwapCheckbox.checked ? 'enabled' : 'disabled'}`);
        }
    });
    vwapCheckbox?.parentElement?.addEventListener('click', (e) => e.stopPropagation());

    // RSI Toggle
    const rsiCheckbox = document.getElementById('toggle-rsi');
    rsiCheckbox?.addEventListener('change', () => {
        if (rsiSeries && chart) {
            updateIndicators();
            rsiSeries.applyOptions({ visible: rsiCheckbox.checked });
            chart.priceScale('rsi').applyOptions({ visible: rsiCheckbox.checked });
            appendLog("INFO", `[UI] RSI (14) ${rsiCheckbox.checked ? 'enabled' : 'disabled'}`);
        }
    });
    rsiCheckbox?.parentElement?.addEventListener('click', (e) => e.stopPropagation());

    // Heikin-Ashi Toggle
    const haBtn = document.getElementById('btn-heikin-ashi');
    haBtn?.addEventListener('click', () => {
        chartMode = chartMode === 'candle' ? 'heikinashi' : 'candle';
        const isHA = chartMode === 'heikinashi';
        haBtn.classList.toggle('bg-teal-500/20', isHA);
        haBtn.classList.toggle('text-teal-300', isHA);
        haBtn.classList.toggle('border', isHA);
        haBtn.classList.toggle('border-teal-500/40', isHA);
        // Re-render candles
        if (candleSeries && candleData.length > 0) {
            const displayData = isHA ? calculateHeikinAshi(candleData) : candleData;
            candleSeries.setData(displayData);
        }
        appendLog("INFO", `[UI] Chart mode: ${isHA ? 'Heikin-Ashi' : 'Candlestick'}`);
    });

    // Screenshot Button
    const screenshotBtn = document.getElementById('btn-screenshot');
    screenshotBtn?.addEventListener('click', () => {
        if (chart) {
            const canvas = chart.takeScreenshot();
            const link = document.createElement('a');
            const sym = (document.getElementById('chart-symbol-label')?.innerText || 'chart').trim();
            const tf = (document.getElementById('chart-tf-label')?.innerText || '').trim();
            link.download = `${sym}_${tf}_${new Date().toISOString().slice(0, 10)}.png`;
            link.href = canvas.toDataURL('image/png');
            link.click();
            appendLog("INFO", `[UI] Chart screenshot saved: ${link.download}`);
        }
    });

    // Fullscreen Toggle
    const fullscreenBtn = document.getElementById('btn-fullscreen');
    let _fsOriginalStyle = '';
    fullscreenBtn?.addEventListener('click', () => {
        const dashboard = document.getElementById('view-dashboard');
        const chartPanel = dashboard?.querySelector(':scope > div:first-child');
        const sidebar = dashboard?.previousElementSibling;
        const bottomPanel = dashboard?.querySelector(':scope > div:nth-child(2)');
        if (!chartPanel || !dashboard) return;

        const isFullscreen = chartPanel.classList.contains('chart-fullscreen');
        if (isFullscreen) {
            // Exit fullscreen — restore everything
            chartPanel.classList.remove('chart-fullscreen');
            chartPanel.style.cssText = _fsOriginalStyle;
            if (sidebar) sidebar.style.display = '';
            if (bottomPanel) bottomPanel.style.display = '';
            dashboard.style.cssText = '';
            fullscreenBtn.querySelector('span').textContent = 'fullscreen';
        } else {
            // Enter fullscreen — save original style and expand
            _fsOriginalStyle = chartPanel.style.cssText;
            chartPanel.classList.add('chart-fullscreen');
            chartPanel.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;z-index:9999;border-radius:0;border:none;background:#020617;';
            if (sidebar) sidebar.style.display = 'none';
            if (bottomPanel) bottomPanel.style.display = 'none';
            fullscreenBtn.querySelector('span').textContent = 'fullscreen_exit';
        }
        // Trigger chart resize after layout settles
        setTimeout(() => {
            if (chart) {
                const container = document.getElementById('chart-area');
                if (container) chart.applyOptions({ width: container.clientWidth, height: container.clientHeight });
            }
        }, 150);
    });

    // Window Controls
    document.getElementById('btn-minimize')?.addEventListener('click', () => {
        window.api.send('minimize-window');
    });
    document.getElementById('btn-maximize')?.addEventListener('click', () => {
        window.api.send('maximize-window');
    });
    document.getElementById('btn-close')?.addEventListener('click', () => {
        window.api.send('close-window');
    });
}


// --- Main Initialization ---
// --- Persistence Logic ---
function saveState() {
    const state = {
        profile: document.getElementById('status-profile')?.innerText,
        equity: document.getElementById('account-equity')?.innerText,
        decisions: document.getElementById('decisions-table')?.innerHTML,
        commentary: document.getElementById('commentary-content')?.innerText,
        holdings: document.getElementById('holdings-table-body')?.innerHTML,
        symbol: document.getElementById('chart-symbol-label')?.innerText,
        timeframe: document.getElementById('chart-tf-label')?.innerText,
        isHalted: document.getElementById('btn-panic')?.classList.contains('bg-emerald-500')
    };
    localStorage.setItem('tradebot_state', JSON.stringify(state));
}

function loadState() {
    const raw = localStorage.getItem('tradebot_state');
    if (!raw) return;
    try {
        const state = JSON.parse(raw);
        if (state.profile) document.getElementById('status-profile').innerText = state.profile;
        if (state.equity) document.getElementById('account-equity').innerText = state.equity;

        // Clear decisions table on load so fresh strategy grades populate
        const decTable = document.getElementById('decisions-table');
        if (decTable) {
            decTable.innerHTML = '';
        }

        if (document.getElementById('commentary-content')) document.getElementById('commentary-content').innerHTML = '';
        document.getElementById('holdings-table-body').innerHTML = '';

        if (state.symbol) document.getElementById('chart-symbol-label').innerText = state.symbol;
        if (state.timeframe) document.getElementById('chart-tf-label').innerText = state.timeframe;

        if (state.isHalted) {
            setPanicState(true);
        }
    } catch (e) { console.error("Load State Error:", e); }
}

function init() {
    console.log("Initializing Dashboard...");

    // Initialize DOM references
    logTerminal = document.getElementById('log-terminal');
    statusProfile = document.getElementById('status-profile');
    statusText = document.getElementById('status-text');
    statusDot = document.getElementById('status-dot');
    statusLatency = document.getElementById('status-latency');

    console.log("DOM references initialized.");

    // Load Cached State
    loadState();

    try {
        initChart();
        console.log("initChart Success");
    } catch (e) {
        console.error("initChart Failed:", e);
    }

    try {
        connectWebSocket();
        setupInteractiveElements();
        setupPanelRotation();
        setupCalendar();

        // Request initial bot status
        window.api.send('get-bot-status');

        // Initialize PnL Timeframe from env (overrides stale localStorage)
        window.api.invoke('read-env').then(env => {
            if (env.GUI_PNL_TIMEFRAME) {
                pnlTimeframe = env.GUI_PNL_TIMEFRAME;
                localStorage.setItem('pnlTimeframe', pnlTimeframe);
            }
            if (window.updateRealizedPnL) window.updateRealizedPnL();
        });

        // Chart Refresh Interval (15 Seconds)
        setInterval(() => {
            const sym = document.getElementById('chart-symbol-label')?.innerText || 'EURUSD';
            const tf = document.getElementById('chart-tf-label')?.innerText || '15m';
            // scrollToRealTime removed — it was causing a gap after the last candle
        }, 15000);

        console.log("Other UI modules initialized.");
    } catch (e) {
        console.error("UI setup failed:", e);
    }
}

// Start the app when ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}

// ═══════════════════════════════════════════════════════════
// PROFILES MODULE - Integrated Profile Editor
// ═══════════════════════════════════════════════════════════
window.profilesModule = (function () {
    let allProfiles = {};
    let selectedProfileName = null;
    let originalProfileData = null;
    let changeCount = 0;
    let initialized = false;

    /**
     * Fetch and update Realized PnL metrics based on timeframe
     */
    async function updateRealizedPnL() {
        try {
            const result = await window.api.invoke('get-analytics-summary', pnlTimeframe);
            if (result && result.success) {
                const summary = result.data;
                if (summary) {
                    const pnlVal = summary.totalNetWorth || summary.totalPnl || 0;

                    // Update global state for sidebar sync
                    currentRealizedPnL = pnlVal;
                    refreshMainPnlDisplay();

                    // Update chips if they exist (backward compatibility or future proofing)
                    const pnlEl = document.getElementById('realized-pnl-chip');
                    const tradeEl = document.getElementById('trade-count-chip');
                    const labelEl = document.getElementById('pnl-timeframe-label');

                    if (pnlEl) {
                        pnlEl.textContent = `${pnlVal >= 0 ? '+' : ''}$${pnlVal.toFixed(2)}`;
                        pnlEl.className = `text-[10px] font-black ${pnlVal >= 0 ? 'text-emerald-400' : 'text-rose-500'} drop-shadow-sm`;
                    }
                    if (tradeEl) tradeEl.textContent = summary.totalTrades || 0;
                    if (labelEl) labelEl.textContent = `Profits & Losses (${pnlTimeframe.toUpperCase()})`;
                }
            }
        } catch (err) {
            console.error('[PNL] Failed to update realized PnL:', err);
        }
    }
    // Expose to global scope so callers outside this IIFE can access it
    window.updateRealizedPnL = updateRealizedPnL;

    // ──────────────────────────────────────────────────────────────
    // STRATEGY_OPTIONS — master list for Profile Editor dropdowns.
    // HOW TO ADD A NEW STRATEGY:
    //   1. Add { value: 'your_key', label: 'Display Name' } below
    //   2. Also add to: settings_integrated.js (System Tab + Strategy Toolbox + STRATEGIES object)
    //   3. Also add to: settings.js (System Tab dropdown)
    //   4. Register in: src/tradebot_sci/strategy/engine.py STRATEGY_MAP
    //   5. Add to Meta-SCI regime groups if applicable: strategy/variants/meta_sci.py
    // ──────────────────────────────────────────────────────────────
    const STRATEGY_OPTIONS = [
        { value: 'rubberband_reaper', label: 'Rubberband Reaper' },
        { value: 'robocop', label: 'RoboCop' },
        { value: 'evolution', label: 'Robot Evolution' },
        { value: 'quantum', label: 'Quantum' },
        { value: 'mean_reversion', label: 'Mean Reversion' },
        { value: 'hyper_scalper', label: 'HyperScalper' },
        { value: 'london_breakout', label: 'London Breakout' },
        { value: 'orb_breakout', label: 'ORB' },
        { value: 'volatility_breakout', label: 'Volatility Breakout' },
        { value: 'aggregator', label: 'Singularity Aggregator' },
        { value: 'meta_sci', label: 'Meta-SCI (AI Ensemble)' },
        { value: 'icc_core', label: 'ICC (Standard)' },
        { value: 'supply_demand', label: 'Supply & Demand' },
        { value: 'trend_rider', label: 'Trend Rider (EMA Pullback)' },
        { value: 'session_momentum', label: 'Session Momentum (VWAP)' },
        { value: 'bearish_engulfing', label: 'Engulfing Reversal' },
        // 🪙 Crypto-Specific Strategies
        { value: 'crypto_rsi_macd', label: '🪙 RSI + MACD (Crypto)' },
        { value: 'crypto_vwap_reversion', label: '🪙 VWAP Reversion (Crypto)' },
        { value: 'crypto_double_macd', label: '🪙 Double MACD Scalper (Crypto)' },
        { value: 'crypto_grid', label: '🪙 Virtual Grid (Crypto)' }
    ];

    const TIMEFRAME_OPTIONS = ['1m', '5m', '15m', '30m', '1h', '4h', '1d'];

    async function init() {
        if (initialized) return;
        await loadProfiles();
        setupEventListeners();
        renderProfileList();
        initialized = true;
    }

    async function loadProfiles() {
        try {
            const result = await window.api.invoke('read-profiles');
            if (result) {
                // Parse YAML using simple regex (no external lib needed for reading)
                allProfiles = parseYaml(result);
            }
        } catch (err) {
            console.error('[PROFILES] Load failed:', err);
            allProfiles = {};
        }
    }

    function parseYaml(yamlStr) {
        // Simple YAML parser for profiles structure
        const profiles = {};
        const lines = yamlStr.split('\n');
        let currentProfile = null;
        let currentKey = null;
        let inSymbols = false;
        let inStrategies = false;

        for (let line of lines) {
            // Skip comments and empty
            if (!line.trim() || line.trim().startsWith('#')) continue;

            // Profile name (2 spaces indent)
            const profileMatch = line.match(/^  ([a-z_0-9]+):$/);
            if (profileMatch) {
                currentProfile = profileMatch[1];
                profiles[currentProfile] = { symbols: [], strategies: {} };
                inSymbols = false;
                inStrategies = false;
                continue;
            }

            if (!currentProfile) continue;

            // Property (4 spaces indent)
            const propMatch = line.match(/^    ([a-z_]+):\s*(.*)$/);
            if (propMatch) {
                const key = propMatch[1];
                // Strip inline comments (e.g., "value  # comment")
                let val = propMatch[2].split('#')[0].trim();
                inSymbols = key === 'symbols' && !val;
                inStrategies = key === 'strategies' && !val;
                if (!inSymbols && !inStrategies && val) {
                    // Parse value
                    if (val === 'true') profiles[currentProfile][key] = true;
                    else if (val === 'false') profiles[currentProfile][key] = false;
                    else if (!isNaN(parseFloat(val)) && /^[\d.\-]+$/.test(val)) profiles[currentProfile][key] = parseFloat(val);
                    else profiles[currentProfile][key] = val.replace(/^['"]|['"]$/g, '');
                }
                continue;
            }

            // Symbol list item (4 spaces + -)
            if (inSymbols) {
                const symMatch = line.match(/^    - (.+)$/);
                if (symMatch) {
                    profiles[currentProfile].symbols.push(symMatch[1].trim().replace(/^['"]|['"]$/g, ''));
                }
            }

            // Strategy item (6 spaces)
            if (inStrategies) {
                const stratMatch = line.match(/^      ([a-z_]+):\s*(.+)$/);
                if (stratMatch) {
                    // Strip inline comments
                    profiles[currentProfile].strategies[stratMatch[1]] = stratMatch[2].split('#')[0].trim();
                }
            }
        }
        return profiles;
    }

    function setupEventListeners() {
        // Tab navigation
        document.getElementById('profile-tabs')?.querySelectorAll('.profile-tab-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.profile-tab-btn').forEach(b => {
                    b.classList.remove('active', 'bg-teal-500/20', 'text-teal-300', 'border', 'border-teal-500/40');
                    b.classList.add('text-slate-400');
                });
                btn.classList.add('active', 'bg-teal-500/20', 'text-teal-300', 'border', 'border-teal-500/40');
                btn.classList.remove('text-slate-400');
                renderTabContent(btn.dataset.tab);
            });
        });

        // Save / Revert
        document.getElementById('btn-save-profile')?.addEventListener('click', saveProfile);
        document.getElementById('btn-revert-profile')?.addEventListener('click', revertChanges);
        document.getElementById('btn-delete-profile')?.addEventListener('click', deleteProfile);
        document.getElementById('btn-new-profile')?.addEventListener('click', createNewProfile);
    }

    function renderProfileList() {
        const list = document.getElementById('profile-list');
        if (!list) return;
        list.innerHTML = '';

        Object.keys(allProfiles).forEach(name => {
            const profile = allProfiles[name];
            const item = document.createElement('div');
            item.className = 'flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer hover:bg-white/5 text-slate-400 hover:text-white transition-all';
            item.dataset.profile = name;

            const symbolCount = profile.symbols?.length || 0;
            item.innerHTML = `
                <span class="material-symbols-outlined text-base opacity-60">tune</span>
                <div class="flex-1 min-w-0">
                    <div class="text-xs font-bold truncate">${formatName(name)}</div>
                    <div class="text-[9px] text-slate-500">${symbolCount} symbols</div>
                </div>
            `;

            item.addEventListener('click', () => selectProfile(name));
            list.appendChild(item);
        });
    }

    function formatName(name) {
        return name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    }

    function selectProfile(name) {
        selectedProfileName = name;
        originalProfileData = JSON.parse(JSON.stringify(allProfiles[name]));

        // Update sidebar active state
        document.querySelectorAll('#profile-list > div').forEach(item => {
            const isActive = item.dataset.profile === name;
            item.className = isActive
                ? 'flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer bg-teal-500/20 text-teal-300 border border-teal-500/30'
                : 'flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer hover:bg-white/5 text-slate-400 hover:text-white transition-all';
        });

        // Update header
        document.getElementById('profile-name-display').textContent = formatName(name);
        document.getElementById('profile-desc-display').textContent = `${allProfiles[name].symbols?.length || 0} symbols`;
        document.getElementById('profile-status')?.classList.remove('hidden');
        document.getElementById('btn-delete-profile')?.classList.remove('hidden');

        // Hide empty state, render first tab
        document.getElementById('profile-empty-state')?.classList.add('hidden');
        const firstTab = document.querySelector('.profile-tab-btn');
        if (firstTab) firstTab.click();

        resetChangeCounter();
    }

    function renderTabContent(tabName) {
        if (!selectedProfileName) return;
        const profile = allProfiles[selectedProfileName];
        const container = document.getElementById('profile-tab-content');
        if (!container) return;

        let html = '<div class="max-w-2xl mx-auto">';

        switch (tabName) {
            case 'general':
                html += renderGeneralTab(profile);
                break;
            case 'symbols':
                html += renderSymbolsTab(profile);
                break;
            case 'risk':
                html += renderRiskTab(profile);
                break;
            case 'icc':
                html += renderIccTab(profile);
                break;
            case 'schedule':
                html += renderScheduleTab(profile);
                break;
        }

        html += '</div>';
        container.innerHTML = html;
        attachTabEventListeners(tabName);
    }

    function renderGeneralTab(profile) {
        return `
            <div class="text-[10px] font-black uppercase tracking-[0.2em] text-teal-500 mb-4 pb-2 border-b border-teal-500/20">Core Settings</div>
            ${renderSelect('strategy_variant', 'Default Strategy', profile.strategy_variant, STRATEGY_OPTIONS)}
            <div class="grid grid-cols-2 gap-3 mt-3">
                ${renderSelect('htf_timeframe', 'HTF Timeframe', profile.htf_timeframe, TIMEFRAME_OPTIONS.map(t => ({ value: t, label: t })))}
                ${renderSelect('ltf_timeframe', 'LTF Timeframe', profile.ltf_timeframe, TIMEFRAME_OPTIONS.map(t => ({ value: t, label: t })))}
            </div>
            <div class="text-[10px] font-black uppercase tracking-[0.2em] text-teal-500 mb-4 pb-2 border-b border-teal-500/20 mt-6">Asset Strategies</div>
            <div class="grid grid-cols-2 gap-3">
                ${['crypto', 'forex', 'stocks', 'etf', 'metals', 'futures'].map(asset =>
            renderSelect(`strategies.${asset}`, asset.charAt(0).toUpperCase() + asset.slice(1), profile.strategies?.[asset] || profile.strategy_variant, STRATEGY_OPTIONS)
        ).join('')}
            </div>
        `;
    }

    function renderSymbolsTab(profile) {
        const symbols = profile.symbols || [];
        return `
            <div class="text-[10px] font-black uppercase tracking-[0.2em] text-teal-500 mb-4 pb-2 border-b border-teal-500/20">Trading Symbols</div>
            <p class="text-[10px] text-slate-500 mb-3">Type a symbol and press Enter to add.</p>
            <div class="bg-black/40 border border-white/5 rounded-xl p-4 min-h-[200px] flex flex-wrap gap-2 content-start">
                ${symbols.map(s => `
                    <span class="symbol-chip inline-flex items-center gap-1 px-3 py-1.5 bg-teal-500/15 border border-teal-500/30 rounded-full text-[11px] font-bold text-teal-400" data-symbol="${s}">
                        ${s}
                        <span class="remove-symbol material-symbols-outlined text-xs cursor-pointer opacity-60 hover:opacity-100 hover:text-red-400">close</span>
                    </span>
                `).join('')}
                <input type="text" id="symbol-input" placeholder="Add symbol..." class="flex-1 min-w-[100px] bg-transparent border-none outline-none text-xs text-white placeholder:text-slate-600">
            </div>
        `;
    }

    function renderRiskTab(profile) {
        return `
            <div class="text-[10px] font-black uppercase tracking-[0.2em] text-teal-500 mb-4 pb-2 border-b border-teal-500/20">Risk Management</div>
            <div class="space-y-3">
                ${renderSlider('risk_per_trade_pct', 'Risk Per Trade', profile.risk_per_trade_pct || 0.02, 0.01, 0.30, 0.01, '%', 100)}
                ${renderSlider('max_concurrent_positions', 'Max Positions', profile.max_concurrent_positions || 1, 1, 10, 1, '')}
                ${renderSlider('max_pyramid_entries', 'Pyramid Entries', profile.max_pyramid_entries || 3, 1, 10, 1, '')}
                ${renderToggle('multi_position_enabled', 'Multi-Position Mode', profile.multi_position_enabled)}
            </div>
        `;
    }

    function renderIccTab(profile) {
        return `
            <div class="text-[10px] font-black uppercase tracking-[0.2em] text-teal-500 mb-4 pb-2 border-b border-teal-500/20">ICC Scoring</div>
            <div class="space-y-3">
                ${renderSlider('icc_entry_score_threshold', 'Entry Threshold', profile.icc_entry_score_threshold || 60, 0, 100, 5, '')}
                ${renderSlider('icc_score_continuation_points', 'Continuation Pts', profile.icc_score_continuation_points || 60, 0, 100, 5, '')}
                ${renderSlider('icc_score_sweep_points', 'Sweep Points', profile.icc_score_sweep_points || 25, 0, 50, 5, '')}
                ${renderToggle('icc_auto_entry_enabled', 'Auto Entry', profile.icc_auto_entry_enabled)}
                ${renderToggle('icc_aggressive_mode', 'Aggressive Mode', profile.icc_aggressive_mode)}
            </div>
        `;
    }

    function renderScheduleTab(profile) {
        return `
            <div class="text-[10px] font-black uppercase tracking-[0.2em] text-teal-500 mb-4 pb-2 border-b border-teal-500/20">Trading Schedule</div>
            <div class="space-y-3">
                ${renderToggle('session_gate_enabled', 'Session Gate', profile.session_gate_enabled)}
                ${renderToggle('sabbath_enabled', 'Sabbath Mode', profile.sabbath_enabled)}
                ${renderToggle('continuous_mode', 'Continuous (24/7)', profile.continuous_mode)}
                ${renderToggle('crypto_only', 'Crypto Only', profile.crypto_only)}
            </div>
        `;
    }

    function renderSelect(key, label, value, options) {
        return `
            <div class="bg-black/30 border border-white/5 rounded-xl p-3 flex items-center justify-between">
                <span class="text-xs font-bold text-slate-300">${label}</span>
                <select class="input-field bg-black/60 border border-white/10 rounded-lg px-3 py-1.5 text-xs text-white min-w-[140px]" data-key="${key}">
                    ${options.map(o => `<option value="${o.value || o}" ${(value === (o.value || o)) ? 'selected' : ''}>${o.label || o}</option>`).join('')}
                </select>
            </div>
        `;
    }

    function renderSlider(key, label, value, min, max, step, suffix, mult = 1) {
        const display = (value * mult).toFixed(mult > 1 ? 1 : 2);
        return `
            <div class="bg-black/30 border border-white/5 rounded-xl p-4">
                <div class="flex justify-between items-center mb-2">
                    <span class="text-xs font-bold text-slate-300">${label}</span>
                    <span class="text-lg font-black text-teal-400" id="val-${key}">${display}${suffix}</span>
                </div>
                <input type="range" class="w-full h-1.5 bg-white/10 rounded-full appearance-none cursor-pointer slider-range" data-key="${key}" data-mult="${mult}" data-suffix="${suffix}" min="${min}" max="${max}" step="${step}" value="${value}">
            </div>
        `;
    }

    function renderToggle(key, label, value) {
        return `
            <div class="bg-black/30 border border-white/5 rounded-xl p-3 flex items-center justify-between">
                <span class="text-xs font-bold text-slate-300">${label}</span>
                <div class="toggle-switch ${value ? 'active' : ''}" data-key="${key}">
                    <div class="toggle-knob"></div>
                </div>
            </div>
        `;
    }

    function attachTabEventListeners(tabName) {
        // Selects
        document.querySelectorAll('#profile-tab-content select').forEach(el => {
            el.addEventListener('change', handleFieldChange);
        });

        // Sliders
        document.querySelectorAll('#profile-tab-content .slider-range').forEach(el => {
            el.addEventListener('input', handleSliderChange);
        });

        // Toggles
        document.querySelectorAll('#profile-tab-content .toggle-switch').forEach(el => {
            el.addEventListener('click', handleToggleClick);
        });

        // Symbols
        if (tabName === 'symbols') {
            document.getElementById('symbol-input')?.addEventListener('keydown', e => {
                if (e.key === 'Enter' && e.target.value.trim()) {
                    const sym = e.target.value.trim().toUpperCase();
                    if (!allProfiles[selectedProfileName].symbols) allProfiles[selectedProfileName].symbols = [];
                    if (!allProfiles[selectedProfileName].symbols.includes(sym)) {
                        allProfiles[selectedProfileName].symbols.push(sym);
                        renderTabContent('symbols');
                        incrementChangeCounter();
                    }
                    e.target.value = '';
                }
            });
            document.querySelectorAll('.remove-symbol').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const sym = e.target.closest('.symbol-chip').dataset.symbol;
                    allProfiles[selectedProfileName].symbols = (allProfiles[selectedProfileName].symbols || []).filter(s => s !== sym);
                    renderTabContent('symbols');
                    incrementChangeCounter();
                });
            });
        }
    }

    function handleFieldChange(e) {
        const key = e.target.dataset.key;
        setNestedValue(allProfiles[selectedProfileName], key, e.target.value);
        incrementChangeCounter();
    }

    function handleSliderChange(e) {
        const key = e.target.dataset.key;
        const mult = parseFloat(e.target.dataset.mult) || 1;
        const suffix = e.target.dataset.suffix || '';
        const val = parseFloat(e.target.value);
        document.getElementById(`val-${key}`).textContent = `${(val * mult).toFixed(mult > 1 ? 1 : 2)}${suffix}`;
        setNestedValue(allProfiles[selectedProfileName], key, val);
        incrementChangeCounter();
    }

    function handleToggleClick(e) {
        const toggle = e.currentTarget;
        const key = toggle.dataset.key;
        const isActive = toggle.classList.contains('active');
        toggle.classList.toggle('active', !isActive);
        setNestedValue(allProfiles[selectedProfileName], key, !isActive);
        incrementChangeCounter();
    }

    function setNestedValue(obj, path, value) {
        const keys = path.split('.');
        let current = obj;
        for (let i = 0; i < keys.length - 1; i++) {
            if (!current[keys[i]]) current[keys[i]] = {};
            current = current[keys[i]];
        }
        current[keys[keys.length - 1]] = value;
    }

    function incrementChangeCounter() {
        changeCount++;
        document.getElementById('profile-change-counter').textContent = `${changeCount} unsaved change${changeCount !== 1 ? 's' : ''}`;
    }

    function resetChangeCounter() {
        changeCount = 0;
        document.getElementById('profile-change-counter').textContent = '0 unsaved changes';
    }

    async function saveProfile() {
        try {
            // Build YAML string
            let yaml = 'profiles:\n';
            for (const [name, profile] of Object.entries(allProfiles)) {
                yaml += `  ${name}:\n`;
                for (const [key, val] of Object.entries(profile)) {
                    if (key === 'symbols' && Array.isArray(val)) {
                        yaml += `    symbols:\n`;
                        val.forEach(s => yaml += `    - ${s}\n`);
                    } else if (key === 'strategies' && typeof val === 'object') {
                        yaml += `    strategies:\n`;
                        for (const [asset, strat] of Object.entries(val)) {
                            yaml += `      ${asset}: ${strat}\n`;
                        }
                    } else if (typeof val === 'boolean') {
                        yaml += `    ${key}: ${val}\n`;
                    } else if (typeof val === 'number') {
                        yaml += `    ${key}: ${val}\n`;
                    } else if (val !== null && val !== undefined) {
                        yaml += `    ${key}: ${val}\n`;
                    }
                }
            }
            await window.api.invoke('save-profiles', yaml);
            originalProfileData = JSON.parse(JSON.stringify(allProfiles[selectedProfileName]));
            resetChangeCounter();
            appendLog("SUCCESS", `[PROFILES] Profile "${selectedProfileName}" saved.`);
        } catch (err) {
            console.error('[PROFILES] Save failed:', err);
            appendLog("ERROR", `[PROFILES] Save failed: ${err.message}`);
        }
    }

    function revertChanges() {
        if (!selectedProfileName || !originalProfileData) return;
        allProfiles[selectedProfileName] = JSON.parse(JSON.stringify(originalProfileData));
        const activeTab = document.querySelector('.profile-tab-btn.active');
        if (activeTab) renderTabContent(activeTab.dataset.tab);
        resetChangeCounter();
        appendLog("INFO", `[PROFILES] Changes reverted for "${selectedProfileName}".`);
    }

    async function deleteProfile() {
        if (!selectedProfileName) return;
        if (!confirm(`Delete profile "${formatName(selectedProfileName)}"?`)) return;
        delete allProfiles[selectedProfileName];
        selectedProfileName = null;
        originalProfileData = null;
        renderProfileList();
        document.getElementById('profile-tab-content').innerHTML = `
            <div id="profile-empty-state" class="flex flex-col items-center justify-center h-full text-center">
                <span class="material-symbols-outlined text-5xl text-slate-600 mb-3">folder_open</span>
                <p class="text-slate-500 text-sm">Select a profile from the sidebar</p>
            </div>
        `;
        document.getElementById('btn-delete-profile')?.classList.add('hidden');
        document.getElementById('profile-name-display').textContent = 'Select a Profile';
        document.getElementById('profile-desc-display').textContent = 'Choose a profile from the sidebar';
        document.getElementById('profile-status')?.classList.add('hidden');
        await saveProfile();
    }

    function createNewProfile() {
        const name = prompt('Enter new profile name (lowercase, underscores):');
        if (!name) return;
        const safeName = name.toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '');
        if (allProfiles[safeName]) {
            alert('Profile already exists!');
            return;
        }
        allProfiles[safeName] = {
            strategy_variant: 'rubberband_reaper',
            htf_timeframe: '15m',
            ltf_timeframe: '5m',
            symbols: [],
            risk_per_trade_pct: 0.02,
            max_concurrent_positions: 1,
            icc_auto_entry_enabled: true,
            strategies: {}
        };
        renderProfileList();
        selectProfile(safeName);
        incrementChangeCounter();
    }

    return { init };
})();

// ═══════════════════════════════════════════════════════════════
// HELP MODULE — Documentation viewer with markdown rendering
// ═══════════════════════════════════════════════════════════════
window.helpModule = (() => {
    let initialized = false;
    let docCatalog = [];
    let activeDoc = null;

    // ── Markdown → HTML Renderer ─────────────────────────────
    function renderMarkdown(md) {
        // Phase 1: Extract code blocks to protect them from inline processing
        const codeBlocks = [];
        let processed = md.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
            const idx = codeBlocks.length;
            const escaped = escapeHtml(code.trimEnd());
            const langLabel = lang ? `<div class="help-code-lang">${lang}</div>` : '';
            codeBlocks.push(`<div class="help-code-block">${langLabel}<pre><code>${escaped}</code></pre></div>`);
            return `%%CODEBLOCK_${idx}%%`;
        });

        // Phase 2: Process line by line
        const lines = processed.split('\n');
        let html = '';
        let inTable = false;
        let tableRows = [];
        let inList = false;
        let listType = '';
        let listItems = [];
        let inBlockquote = false;
        let blockquoteLines = [];
        let alertType = null;

        function flushTable() {
            if (!inTable) return;
            inTable = false;
            if (tableRows.length < 2) { tableRows = []; return; }
            let t = '<div class="help-table-wrap"><table class="help-table"><thead><tr>';
            const headers = tableRows[0].split('|').map(c => c.trim()).filter(Boolean);
            headers.forEach(h => { t += `<th>${inlineFormat(h)}</th>`; });
            t += '</tr></thead><tbody>';
            for (let i = 2; i < tableRows.length; i++) {
                const cells = tableRows[i].split('|').map(c => c.trim()).filter(Boolean);
                t += '<tr>';
                cells.forEach(c => { t += `<td>${inlineFormat(c)}</td>`; });
                t += '</tr>';
            }
            t += '</tbody></table></div>';
            html += t;
            tableRows = [];
        }

        function flushList() {
            if (!inList) return;
            inList = false;
            const tag = listType === 'ol' ? 'ol' : 'ul';
            html += `<${tag} class="help-list">`;
            listItems.forEach(item => {
                html += `<li>${inlineFormat(item)}</li>`;
            });
            html += `</${tag}>`;
            listItems = [];
        }

        function flushBlockquote() {
            if (!inBlockquote) return;
            inBlockquote = false;

            const content = blockquoteLines.join('\n');
            blockquoteLines = [];

            // Check for GitHub-style alerts
            const alertMatch = content.match(/^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*\n?([\s\S]*)/);
            if (alertMatch) {
                const type = alertMatch[1].toLowerCase();
                const body = alertMatch[2].trim();
                const icons = {
                    note: 'info', tip: 'lightbulb', important: 'priority_high',
                    warning: 'warning', caution: 'dangerous'
                };
                const colors = {
                    note: 'var(--accent, #14b8a6)',
                    tip: '#22c55e',
                    important: '#a78bfa',
                    warning: '#f59e0b',
                    caution: '#ef4444'
                };
                html += `<div class="help-alert help-alert-${type}" style="border-left-color: ${colors[type]};">
                    <div class="help-alert-header" style="color: ${colors[type]};">
                        <span class="material-symbols-outlined" style="font-size: 16px;">${icons[type]}</span>
                        <span>${type.toUpperCase()}</span>
                    </div>
                    <div class="help-alert-body">${inlineFormat(body)}</div>
                </div>`;
            } else {
                html += `<blockquote class="help-blockquote">${inlineFormat(content)}</blockquote>`;
            }
        }

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];
            const trimmed = line.trim();

            // Code block placeholder
            if (trimmed.match(/^%%CODEBLOCK_\d+%%$/)) {
                flushTable(); flushList(); flushBlockquote();
                const idx = parseInt(trimmed.match(/\d+/)[0]);
                html += codeBlocks[idx];
                continue;
            }

            // Horizontal rule
            if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
                flushTable(); flushList(); flushBlockquote();
                html += '<hr class="help-hr">';
                continue;
            }

            // Table row
            if (trimmed.includes('|') && !trimmed.startsWith('>')) {
                flushList(); flushBlockquote();
                if (!inTable) inTable = true;
                tableRows.push(trimmed);
                continue;
            } else {
                flushTable();
            }

            // Blockquote
            if (trimmed.startsWith('>')) {
                flushTable(); flushList();
                if (!inBlockquote) inBlockquote = true;
                blockquoteLines.push(trimmed.replace(/^>\s?/, ''));
                continue;
            } else {
                flushBlockquote();
            }

            // List items (unordered: - or *, ordered: 1.)
            const ulMatch = trimmed.match(/^[-*]\s+(.*)/);
            const olMatch = trimmed.match(/^\d+\.\s+(.*)/);
            if (ulMatch || olMatch) {
                flushTable(); flushBlockquote();
                const newType = ulMatch ? 'ul' : 'ol';
                if (inList && listType !== newType) flushList();
                inList = true;
                listType = newType;
                listItems.push(ulMatch ? ulMatch[1] : olMatch[1]);
                continue;
            } else if (inList && trimmed === '') {
                flushList();
                continue;
            } else if (inList && /^\s{2,}/.test(line)) {
                // Continuation / nested
                listItems[listItems.length - 1] += ' ' + trimmed;
                continue;
            } else {
                flushList();
            }

            // Headers
            const headerMatch = trimmed.match(/^(#{1,6})\s+(.*)/);
            if (headerMatch) {
                flushTable(); flushList(); flushBlockquote();
                const level = headerMatch[1].length;
                const text = headerMatch[2];
                const id = text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/-+$/, '');
                html += `<h${level} class="help-h${level}" id="h-${id}">${inlineFormat(text)}</h${level}>`;
                continue;
            }

            // Empty line → paragraph break
            if (trimmed === '') {
                continue;
            }

            // Regular paragraph
            html += `<p class="help-p">${inlineFormat(trimmed)}</p>`;
        }

        // Flush remaining
        flushTable(); flushList(); flushBlockquote();
        return html;
    }

    function escapeHtml(str) {
        return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function inlineFormat(text) {
        if (!text) return '';
        // Process inline elements (order matters)
        return text
            // Images
            .replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img src="$2" alt="$1" class="help-img">')
            // Links
            .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" class="help-link" target="_blank" rel="noopener">$1</a>')
            // Bold + italic
            .replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')
            // Bold
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            // Italic
            .replace(/\*(.+?)\*/g, '<em>$1</em>')
            // Inline code
            .replace(/`([^`]+)`/g, '<code class="help-inline-code">$1</code>')
            // Emoji shortcuts (common ones in the docs)
            .replace(/⭐/g, '<span style="color: #f59e0b;">⭐</span>');
    }

    // ── CSS for the markdown content, using theme variables ──
    function injectStyles() {
        if (document.getElementById('help-module-styles')) return;
        const style = document.createElement('style');
        style.id = 'help-module-styles';
        style.textContent = `
            /* ── Doc Picker Items ── */
            .help-doc-item {
                display: flex;
                align-items: center;
                gap: 0.75rem;
                padding: 0.625rem 0.875rem;
                border-radius: 0.625rem;
                cursor: pointer;
                transition: all 0.2s ease;
                border: 1px solid transparent;
                color: var(--text-secondary, #94a3b8);
                font-size: 0.8125rem;
                font-weight: 500;
            }
            .help-doc-item:hover {
                background: rgba(255,255,255,0.04);
                color: var(--text-primary, #e2e8f0);
            }
            .help-doc-item.active {
                background: var(--accent-dim, rgba(20,184,166,0.15));
                color: var(--accent, #14b8a6);
                border-color: var(--accent-glow, rgba(20,184,166,0.3));
                font-weight: 700;
            }
            .help-doc-item .doc-icon {
                font-size: 1.125rem;
                flex-shrink: 0;
                color: inherit;
                opacity: 0.7;
            }
            .help-doc-item.active .doc-icon {
                opacity: 1;
            }
            .help-doc-item .doc-title {
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .help-category-label {
                font-size: 0.5625rem;
                font-weight: 900;
                text-transform: uppercase;
                letter-spacing: 0.15em;
                color: var(--text-muted, #64748b);
                padding: 1rem 0.875rem 0.375rem;
            }

            /* ── Markdown Content Styles ── */
            .help-h1 {
                font-size: 2.125rem;
                font-weight: 800;
                color: var(--text-primary, #e2e8f0);
                margin: 0 0 1rem 0;
                padding-bottom: 0.75rem;
                border-bottom: 2px solid var(--accent-dim, rgba(20,184,166,0.15));
                line-height: 1.3;
            }
            .help-h2 {
                font-size: 1.625rem;
                font-weight: 700;
                color: var(--text-primary, #e2e8f0);
                margin: 2rem 0 0.75rem 0;
                padding-bottom: 0.5rem;
                border-bottom: 1px solid rgba(255,255,255,0.06);
                line-height: 1.3;
            }
            .help-h3 {
                font-size: 1.325rem;
                font-weight: 700;
                color: var(--accent, #14b8a6);
                margin: 1.5rem 0 0.5rem 0;
                line-height: 1.3;
            }
            .help-h4, .help-h5, .help-h6 {
                font-size: 1.125rem;
                font-weight: 700;
                color: var(--text-primary, #e2e8f0);
                margin: 1.25rem 0 0.375rem 0;
                line-height: 1.3;
            }
            .help-p {
                font-size: 1.0625rem;
                line-height: 1.75;
                color: var(--text-secondary, #94a3b8);
                margin: 0.5rem 0;
            }
            .help-p strong {
                color: var(--text-primary, #e2e8f0);
                font-weight: 700;
            }
            .help-p em {
                color: var(--text-primary, #e2e8f0);
                font-style: italic;
            }
            .help-link {
                color: var(--accent, #14b8a6);
                text-decoration: none;
                font-weight: 600;
                border-bottom: 1px solid var(--accent-dim, rgba(20,184,166,0.3));
                transition: all 0.15s ease;
            }
            .help-link:hover {
                border-bottom-color: var(--accent, #14b8a6);
            }
            .help-inline-code {
                background: rgba(0,0,0,0.35);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 4px;
                padding: 0.125rem 0.375rem;
                font-family: 'JetBrains Mono', 'Fira Code', monospace;
                font-size: 0.8em;
                color: var(--accent, #14b8a6);
            }
            .help-code-block {
                position: relative;
                margin: 1rem 0;
                border-radius: 0.75rem;
                overflow: hidden;
                border: 1px solid rgba(255,255,255,0.06);
                background: rgba(0,0,0,0.4);
            }
            .help-code-lang {
                position: absolute;
                top: 0;
                right: 0;
                padding: 0.25rem 0.75rem;
                font-size: 0.625rem;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.1em;
                color: var(--text-muted, #64748b);
                background: rgba(0,0,0,0.3);
                border-bottom-left-radius: 0.5rem;
            }
            .help-code-block pre {
                margin: 0;
                padding: 1rem 1.25rem;
                overflow-x: auto;
            }
            .help-code-block code {
                font-family: 'JetBrains Mono', 'Fira Code', monospace;
                font-size: 0.9375rem;
                line-height: 1.6;
                color: var(--text-primary, #e2e8f0);
            }

            /* ── Tables ── */
            .help-table-wrap {
                overflow-x: auto;
                margin: 1rem 0;
                border-radius: 0.75rem;
                border: 1px solid rgba(255,255,255,0.06);
            }
            .help-table {
                width: 100%;
                border-collapse: collapse;
                font-size: 1.0rem;
            }
            .help-table th {
                text-align: left;
                padding: 0.625rem 1rem;
                font-weight: 700;
                font-size: 0.8125rem;
                text-transform: uppercase;
                letter-spacing: 0.06em;
                color: var(--accent, #14b8a6);
                background: rgba(0,0,0,0.3);
                border-bottom: 1px solid rgba(255,255,255,0.06);
            }
            .help-table td {
                padding: 0.5rem 1rem;
                color: var(--text-secondary, #94a3b8);
                border-bottom: 1px solid rgba(255,255,255,0.03);
                line-height: 1.5;
            }
            .help-table td strong {
                color: var(--text-primary, #e2e8f0);
            }
            .help-table tr:hover td {
                background: rgba(255,255,255,0.02);
            }
            .help-table tr:last-child td {
                border-bottom: none;
            }

            /* ── Blockquotes ── */
            .help-blockquote {
                border-left: 3px solid var(--accent-dim, rgba(20,184,166,0.3));
                padding: 0.5rem 1rem;
                margin: 1rem 0;
                color: var(--text-secondary, #94a3b8);
                font-size: 1.0625rem;
                font-style: italic;
                background: rgba(0,0,0,0.15);
                border-radius: 0 0.5rem 0.5rem 0;
            }
            .help-blockquote strong {
                color: var(--text-primary, #e2e8f0);
            }

            /* ── GitHub-style alerts ── */
            .help-alert {
                border-left: 3px solid;
                padding: 0.75rem 1rem;
                margin: 1rem 0;
                border-radius: 0 0.5rem 0.5rem 0;
                background: rgba(0,0,0,0.2);
            }
            .help-alert-header {
                display: flex;
                align-items: center;
                gap: 0.375rem;
                font-size: 0.875rem;
                font-weight: 800;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                margin-bottom: 0.375rem;
            }
            .help-alert-body {
                font-size: 1.0rem;
                line-height: 1.6;
                color: var(--text-secondary, #94a3b8);
            }
            .help-alert-body strong {
                color: var(--text-primary, #e2e8f0);
            }

            /* ── Lists ── */
            .help-list {
                margin: 0.625rem 0;
                padding-left: 1.5rem;
                font-size: 1.0625rem;
                line-height: 1.75;
                color: var(--text-secondary, #94a3b8);
            }
            .help-list li {
                margin: 0.25rem 0;
            }
            .help-list li strong {
                color: var(--text-primary, #e2e8f0);
            }
            .help-list li code {
                background: rgba(0,0,0,0.35);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 4px;
                padding: 0.125rem 0.375rem;
                font-family: 'JetBrains Mono', 'Fira Code', monospace;
                font-size: 0.8em;
                color: var(--accent, #14b8a6);
            }
            ul.help-list {
                list-style-type: disc;
            }
            ul.help-list li::marker {
                color: var(--accent, #14b8a6);
            }
            ol.help-list {
                list-style-type: decimal;
            }
            ol.help-list li::marker {
                color: var(--accent, #14b8a6);
                font-weight: 700;
            }

            /* ── Horizontal Rule ── */
            .help-hr {
                border: none;
                border-top: 1px solid rgba(255,255,255,0.06);
                margin: 2rem 0;
            }

            /* ── Images ── */
            .help-img {
                max-width: 100%;
                border-radius: 0.5rem;
                margin: 0.5rem 0;
            }

            /* ── Search highlight ── */
            .help-search-highlight {
                background: var(--accent-dim, rgba(20,184,166,0.3));
                color: var(--accent, #14b8a6);
                padding: 0.05rem 0.2rem;
                border-radius: 2px;
                font-weight: 700;
            }

            /* ── Smooth scroll for content ── */
            #help-content {
                scroll-behavior: smooth;
            }

            /* ══════════════════════════════════════ */
            /* ── Magazine Landing Page ──            */
            /* ══════════════════════════════════════ */
            .help-magazine {
                padding: 1.5rem 2rem;
                max-width: 1400px;
                margin: 0 auto;
            }
            .help-mag-header {
                margin-bottom: 1.25rem;
                display: flex;
                align-items: baseline;
                gap: 1rem;
            }
            .help-mag-header h1 {
                font-size: 1.35rem;
                font-weight: 800;
                color: var(--text-primary, #e2e8f0);
                margin: 0;
                letter-spacing: -0.02em;
            }
            .help-mag-header p {
                font-size: 0.75rem;
                color: var(--text-muted, #64748b);
                margin: 0;
            }

            /* ── Masonry grid ── */
            .help-mag-grid {
                display: grid;
                grid-template-columns: repeat(4, 1fr);
                gap: 16px;
            }

            /* Size variants */
            .help-mag-card.mag-lg {
                grid-column: span 2;
                min-height: 220px;
            }
            .help-mag-card.mag-md {
                grid-column: span 1;
                min-height: 180px;
            }
            .help-mag-card.mag-sm {
                grid-column: span 1;
                min-height: 140px;
            }

            /* Base card */
            .help-mag-card {
                position: relative;
                border-radius: 14px;
                border: 1px solid rgba(255,255,255,0.06);
                background: rgba(255,255,255,0.025);
                backdrop-filter: blur(12px);
                -webkit-backdrop-filter: blur(12px);
                cursor: pointer;
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                overflow: hidden;
                display: flex;
                flex-direction: column;
            }
            .help-mag-card:hover {
                border-color: var(--accent-glow, rgba(20,184,166,0.3));
                background: rgba(255,255,255,0.05);
                transform: translateY(-4px);
                box-shadow: 0 16px 48px rgba(0,0,0,0.35);
            }

            /* Card inner layout */
            .help-mag-card-inner {
                position: relative;
                z-index: 1;
                display: flex;
                flex-direction: column;
                flex: 1;
                padding: 1.25rem 1.375rem;
            }

            /* Top row: icon + badge */
            .help-mag-card-top {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: 0.75rem;
            }
            .help-mag-card-top .material-symbols-outlined {
                font-size: 1.75rem;
                color: var(--accent, #14b8a6);
                opacity: 0.85;
            }
            .mag-lg .help-mag-card-top .material-symbols-outlined {
                font-size: 2.25rem;
            }
            .mag-badge {
                display: inline-flex;
                align-items: center;
                gap: 0.2rem;
                padding: 0.15rem 0.5rem;
                border-radius: 999px;
                font-size: 0.5rem;
                font-weight: 800;
                text-transform: uppercase;
                letter-spacing: 0.12em;
                border: 1px solid rgba(255,255,255,0.1);
                color: var(--text-muted, #64748b);
            }
            .mag-badge.featured {
                background: var(--accent, #14b8a6);
                border-color: transparent;
                color: #000;
            }

            /* Title + description */
            .help-mag-card h3 {
                font-size: 0.875rem;
                font-weight: 700;
                color: var(--text-primary, #e2e8f0);
                margin: 0 0 0.375rem 0;
                line-height: 1.35;
            }
            .mag-lg h3 {
                font-size: 1.0625rem;
            }
            .help-mag-card .mag-desc {
                font-size: 0.6875rem;
                color: var(--text-muted, #64748b);
                margin: 0;
                line-height: 1.65;
                flex: 1;
            }
            .mag-lg .mag-desc {
                font-size: 0.75rem;
            }

            /* Read more label — reveal on hover */
            .mag-read {
                display: inline-flex;
                align-items: center;
                gap: 0.3rem;
                font-size: 0.625rem;
                font-weight: 700;
                color: var(--accent, #14b8a6);
                margin-top: auto;
                padding-top: 0.75rem;
                opacity: 0;
                transform: translateY(4px);
                transition: all 0.25s ease;
            }
            .help-mag-card:hover .mag-read {
                opacity: 1;
                transform: translateY(0);
            }

            /* Section divider */
            .help-mag-section {
                grid-column: 1 / -1;
                font-size: 0.5625rem;
                font-weight: 900;
                text-transform: uppercase;
                letter-spacing: 0.2em;
                color: var(--text-muted, #64748b);
                display: flex;
                align-items: center;
                gap: 0.75rem;
                padding: 0.5rem 0 0;
            }
            .help-mag-section::after {
                content: '';
                flex: 1;
                height: 1px;
                background: rgba(255,255,255,0.06);
            }

            /* Back button */
            .help-back-btn {
                display: inline-flex;
                align-items: center;
                gap: 0.25rem;
                padding: 0.375rem 0.5rem;
                font-size: 0.6875rem;
                font-weight: 600;
                color: var(--text-muted, #64748b);
                background: transparent;
                border: none;
                cursor: pointer;
                transition: color 0.15s ease;
            }
            .help-back-btn:hover {
                color: var(--text-primary, #e2e8f0);
            }
        `;
        document.head.appendChild(style);
    }

    // ── Magazine Landing Page ────────────────────────────────
    function renderMagazine() {
        const welcomeEl = document.getElementById('help-welcome');
        const markdownEl = document.getElementById('help-markdown');
        const titleEl = document.getElementById('help-doc-title');

        if (markdownEl) markdownEl.classList.add('hidden');
        if (titleEl) titleEl.textContent = 'Knowledge Base';

        if (!welcomeEl) return;
        welcomeEl.classList.remove('hidden');

        console.log('[HELP] renderMagazine: catalog has', docCatalog.length, 'docs');

        let html = `<div class="help-magazine">`;

        // Header
        html += `<div class="help-mag-header">
            <h1>Knowledge Base</h1>
            <p>Everything you need to master TradeBot SCI Enterprise</p>
        </div>`;

        // Build masonry grid — all cards in one grid
        html += `<div class="help-mag-grid">`;

        docCatalog.forEach((doc, i) => {
            // Assign size: featured = large, certain important ones = medium, rest = small
            let sizeClass = 'mag-sm';
            if (doc.featured) {
                sizeClass = 'mag-lg';
            } else if (doc.size === 'md' || ['RTFM/06_PANIC_BUTTON.md', 'RTFM/05_COOKBOOK.md', 'RTFM/08_API_SETUP.md'].includes(doc.filename)) {
                sizeClass = 'mag-md';
            }

            const icon = doc.icon || 'article';
            const badgeLabel = doc.featured ? '⭐ Featured' : (doc.category === 'guide' ? 'Quick Start' : 'RTFM');
            const badgeClass = doc.featured ? 'mag-badge featured' : 'mag-badge';

            html += `
                <div class="help-mag-card ${sizeClass}" data-filename="${doc.filename}">
                    <div class="help-mag-card-inner">
                        <div class="help-mag-card-top">
                            <span class="material-symbols-outlined">${icon}</span>
                            <span class="${badgeClass}">${badgeLabel}</span>
                        </div>
                        <h3>${doc.title}</h3>
                        <p class="mag-desc">${doc.description || ''}</p>
                        <div class="mag-read">Read article <span class="material-symbols-outlined" style="font-size: 13px;">arrow_forward</span></div>
                    </div>
                </div>`;
        });

        html += `</div></div>`;
        welcomeEl.innerHTML = html;

        // Attach click handlers
        welcomeEl.querySelectorAll('[data-filename]').forEach(card => {
            card.addEventListener('click', (e) => {
                console.log('[HELP] Card clicked:', card.dataset.filename);
                loadDoc(card.dataset.filename);
            });
        });
        console.log('[HELP] Attached click handlers to', welcomeEl.querySelectorAll('[data-filename]').length, 'cards');
    }

    // Show magazine (reset from article view)
    function showMagazine() {
        activeDoc = null;
        renderMagazine();

        const contentArea = document.getElementById('help-content');
        if (contentArea) contentArea.scrollTop = 0;

        const backBtn = document.getElementById('help-back-btn');
        if (backBtn) backBtn.classList.add('hidden');

        // Show search box on magazine landing
        const searchWrap = document.getElementById('help-search-wrap');
        if (searchWrap) searchWrap.style.display = '';
        // Clear search on return
        const searchInput = document.getElementById('help-search-input');
        if (searchInput) searchInput.value = '';
    }

    // ── Load a document ──────────────────────────────────────
    async function loadDoc(filename) {
        console.log('[HELP] loadDoc called with:', filename, 'API available:', !!window.api?.readHelpDoc);
        if (!window.api?.readHelpDoc) {
            console.warn('[HELP] readHelpDoc API not available!');
            return;
        }

        activeDoc = filename;

        const titleEl = document.getElementById('help-doc-title');
        const welcomeEl = document.getElementById('help-welcome');
        const markdownEl = document.getElementById('help-markdown');
        if (titleEl) titleEl.textContent = 'Loading...';

        // Show back button
        const backBtn = document.getElementById('help-back-btn');
        if (backBtn) backBtn.classList.remove('hidden');

        // Hide search box when viewing an article
        const searchWrap = document.getElementById('help-search-wrap');
        if (searchWrap) searchWrap.style.display = 'none';

        try {
            const result = await window.api.readHelpDoc(filename);
            if (!result.success) {
                if (titleEl) titleEl.textContent = 'Error';
                if (markdownEl) markdownEl.innerHTML = `<div class="help-p" style="color: #ef4444;">Failed to load: ${result.error}</div>`;
                return;
            }

            const { title, content } = result.data;
            if (titleEl) titleEl.textContent = title;
            if (welcomeEl) welcomeEl.classList.add('hidden');
            if (markdownEl) {
                markdownEl.classList.remove('hidden');
                markdownEl.innerHTML = renderMarkdown(content);
            }

            const contentArea = document.getElementById('help-content');
            if (contentArea) contentArea.scrollTop = 0;

        } catch (err) {
            console.error('[HELP] Error loading doc:', err);
            if (titleEl) titleEl.textContent = 'Error';
        }
    }

    // ── Scroll to top button ────────────────────────────────
    function setupScrollTop() {
        const btn = document.getElementById('help-scroll-top');
        const contentArea = document.getElementById('help-content');
        if (btn && contentArea) {
            btn.addEventListener('click', () => {
                contentArea.scrollTop = 0;
            });
        }
    }

    // ── Search filter ────────────────────────────────────────
    function setupHelpSearch() {
        const input = document.getElementById('help-search-input');
        if (!input) return;

        input.addEventListener('input', () => {
            const query = input.value.trim().toLowerCase();
            const cards = document.querySelectorAll('.help-mag-card');

            cards.forEach(card => {
                if (!query) {
                    // No query — show all cards
                    card.style.display = '';
                    card.style.opacity = '1';
                    return;
                }

                const filename = (card.dataset.filename || '').toLowerCase();
                // Find the matching catalog entry for richer matching
                const catEntry = docCatalog.find(d => d.filename === card.dataset.filename);
                const title = catEntry ? catEntry.title.toLowerCase() : '';
                const desc = catEntry ? (catEntry.description || '').toLowerCase() : '';

                const matches = title.includes(query) || desc.includes(query) || filename.includes(query);
                card.style.display = matches ? '' : 'none';
                card.style.opacity = matches ? '1' : '0';
            });
        });
    }

    // ── Init ─────────────────────────────────────────────────
    async function init() {
        if (initialized) return;
        initialized = true;

        injectStyles();

        // Load doc catalog
        if (window.api?.listHelpDocs) {
            try {
                const result = await window.api.listHelpDocs();
                if (result.success) {
                    docCatalog = result.data;
                }
            } catch (err) {
                console.error('[HELP] Failed to load catalog:', err);
            }
        }

        // Fallback catalog if IPC isn't available (for debugging)
        if (docCatalog.length === 0) {
            docCatalog = [
                { filename: 'HOW_TO_USE.md', title: 'First Time? Everything You Need to Launch Your First Trade', category: 'guide', icon: 'rocket_launch', description: 'The practical, no-fluff guide to getting the bot running and making trades.', featured: true },
                { filename: 'RTFM/01_PHILOSOPHY.md', title: 'Born From Late-Stage Capitalism: Why This Bot Exists', category: 'rtfm', icon: 'psychology', description: '"The economy is in shambles. The rent is too damn high."' },
                { filename: 'RTFM/02_SKELETON_ARCH.md', title: 'Inside the Machine: The Complete Skeletal Architecture', category: 'rtfm', icon: 'account_tree', description: '"It\'s alive! ...mostly." The anatomy of the application.' },
                { filename: 'RTFM/03_FUNCTIONS_DATA.md', title: 'Under the Hood: Every Function, Every Data Packet', category: 'rtfm', icon: 'data_object', description: '"The devil is in the details. And the bugs."' },
                { filename: 'RTFM/04_MAP_TOC.md', title: 'Lost in the Codebase? The Complete Navigation Map', category: 'rtfm', icon: 'map', description: '"Where is main.py again?"' },
                { filename: 'RTFM/05_COOKBOOK.md', title: 'Recipes for Traders: A Cookbook of Common Tasks', category: 'rtfm', icon: 'menu_book', description: '"Give a man a fish, he trades for a day."' },
                { filename: 'RTFM/06_PANIC_BUTTON.md', title: 'Something Is Wrong — The Emergency Panic Protocol', category: 'rtfm', icon: 'emergency', description: '"Something is wrong. Make it stop."' },
                { filename: 'RTFM/07_COCKPIT_CONTROLS.md', title: 'What Does This Button Do? The Complete Cockpit Guide', category: 'rtfm', icon: 'tune', description: '"What does this button do?" — Last words of a former trader.' },
                { filename: 'RTFM/08_API_SETUP.md', title: 'Connecting to the World: Every Broker, Every API Key', category: 'rtfm', icon: 'key', description: '"The bot is only as smart as its connection."' },
                { filename: 'RTFM/09_FEET_WET_STRATEGY.md', title: '20 Weapons of War: The Complete Strategy Arsenal', category: 'rtfm', icon: 'strategy', description: '"One strategy doesn\'t fit all markets."', featured: true },
                { filename: 'RTFM/14_READING_THE_SCOREBOARD.md', title: 'Am I Winning? How to Read Your Performance Metrics', category: 'rtfm', icon: 'monitoring', description: '"If you can\'t measure it, you can\'t improve it."' },
                { filename: 'RTFM/11_GHOST_IN_MACHINE.md', title: 'I Think, Therefore I Trade: The AI Decision Engine', category: 'rtfm', icon: 'smart_toy', description: '"I think, therefore I trade."' },
                { filename: 'RTFM/12_TIME_MACHINE.md', title: 'I Have to Go Back: The Trinity of Backtesting', category: 'rtfm', icon: 'history', description: '"I have to go back."' },
                { filename: 'RTFM/13_ENV_VARS.md', title: 'Every Toggle, Every Flag: The Environment Variable Bible', category: 'rtfm', icon: 'settings_applications', description: 'The complete env var reference.' },
            ];
        }

        renderMagazine();
        setupScrollTop();
        setupHelpSearch();

        // Back button
        const backBtn = document.getElementById('help-back-btn');
        if (backBtn) {
            backBtn.addEventListener('click', () => showMagazine());
        }
    }

    return { init };
})();
