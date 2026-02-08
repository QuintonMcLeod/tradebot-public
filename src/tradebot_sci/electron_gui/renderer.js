// --- Chart & DOM State ---
let chart;
let candleSeries;
let indicatorSeries;
let emaSeries;
let smaSeries;
let stopLossLine; // Horizontal price line for SL
let takeProfitLine; // Horizontal price line for TP
let entryPriceLine; // Horizontal price line for entry
let tradeMarkers = []; // Current active markers for symbols
let markerCache = {}; // Cache of markers per symbol: { 'BTCUSD': [markers], ... }
let previousSymbol = null; // Track symbol shifts to clear markers selectively
let candleData = []; // Store candle data for indicator calculations
let currentPosition = null; // { symbol, side, entry, sl, tp, size }
let lastHoldings = null; // Cache last holdings data for redrawing on symbol switch
let statusDot;
let statusLatency;
let currentRealizedPnL = 0;
let currentUnrealizedPnL = 0;
let chartResizeObserver = null; // [ANTIGRAVITY] Module-scoped to prevent leaks
// [ANTIGRAVITY] pnlTimeframe is now the single source of truth for display mode too.
// Possible values: 'holdings', '24h', 'week', 'month', 'year', 'all'
// Authoritative source for PnL timeframe, synced with sidebar and settings
let pnlTimeframe = localStorage.getItem('pnlTimeframe') || '24h';
window.pnlTimeframe = pnlTimeframe;
let timeFormat = localStorage.getItem('timeFormat') || '24h';
window.timeFormat = timeFormat;
const pnlModes = ['1h', '4h', '24h', '7d', 'all'];
const DEFAULT_LOCALE = 'en-US'; // [ANTIGRAVITY] Force consistent locale for predictable parsing

// =======================================================================
// [ANTIGRAVITY] SINGLE SOURCE OF TRUTH — Central UI State
// =======================================================================
const dashboardState = {
    profile: '',
    capital: null,
    capitalLabel: 'Overall Capital:',
    capitalCache: {},         // replaces window.capitalCache
    cash: null,
    realizedPnL: null,
    unrealizedPnL: null,
    pnlTimeframe: pnlTimeframe,
    timeFormat: timeFormat,
    isSabbath: false,
    isHalted: false,
    symbols: [],
    activeSymbol: '',
    activeTimeframe: '15m',
};
// Expose for DevTools debugging
window.dashboardState = dashboardState;

// [ANTIGRAVITY] XSS-safe text escaping
function escapeHtml(str) {
    if (typeof str !== 'string') return String(str ?? '');
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
}

// [ANTIGRAVITY] Central time formatter — honors global 12h/24h preference
// Used by: appendLog, addDecisionRow, parseLogLine commentary, chart formatters
function formatTime(date) {
    if (!date) date = new Date();
    if (timeFormat === '12h') {
        let h = date.getHours();
        const m = date.getMinutes().toString().padStart(2, '0');
        const s = date.getSeconds().toString().padStart(2, '0');
        const ampm = h >= 12 ? 'PM' : 'AM';
        h = h % 12;
        h = h ? h : 12;
        return `${h}:${m}:${s} ${ampm}`;
    } else {
        const h = date.getHours().toString().padStart(2, '0');
        const m = date.getMinutes().toString().padStart(2, '0');
        const s = date.getSeconds().toString().padStart(2, '0');
        return `${h}:${m}:${s}`;
    }
}

// [ANTIGRAVITY] Memoized DOM writer — ONLY place profile/capital/equity DOM is touched
function syncUI() {
    const prev = syncUI._prev || {};
    const s = dashboardState;

    const setText = (id, val) => {
        if (prev[id] === val) return;
        const el = document.getElementById(id);
        if (el) el.textContent = val;
        prev[id] = val;
    };

    setText('status-profile', s.profile);
    setText('capital-label', s.capitalLabel);
    if (s.capital !== null) {
        setText('account-capital', s.capital.toLocaleString('en-US', {
            minimumFractionDigits: 2, maximumFractionDigits: 2
        }));
    }
    if (s.cash !== null) {
        const cashEl = document.getElementById('account-cash');
        if (cashEl) {
            const formatted = s.cash.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            if (prev['account-cash'] !== formatted) {
                cashEl.textContent = formatted;
                prev['account-cash'] = formatted;
            }
        }
    }

    // Sabbath badge
    const sabbathEl = document.getElementById('status-sabbath');
    if (sabbathEl) {
        const shouldHide = !s.isSabbath;
        if (prev._sabbathHidden !== shouldHide) {
            sabbathEl.classList.toggle('hidden', shouldHide);
            prev._sabbathHidden = shouldHide;
        }
    }

    syncUI._prev = prev;
}
syncUI._prev = {};

// [ANTIGRAVITY] Forex symbols for manual 12h offset
const FOREX_SYMBOLS = [
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "NZDUSD", "USDCAD", "USDCHF",
    "GBPJPY", "EURJPY", "AUDJPY", "XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD", "UNG"
];

function isForex(symbol) {
    if (!symbol) return false;
    const sym = symbol.toUpperCase().replace('/', '');
    return FOREX_SYMBOLS.includes(sym);
}

function logToServer(msg, level = 'INFO') {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'log', level: level, data: `[FRONTEND] ${msg}` }));
    }
}

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

    // [ANTIGRAVITY FIX] Sync with settings dropdown if it exists and is loaded
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

    // [ANTIGRAVITY FIX] Sync with settings panel if loaded
    if (typeof window.updateValue === 'function') {
        window.updateValue('GUI_PNL_TIMEFRAME', pnlTimeframe);
    }

    // Trigger data refresh if not holdings (since we need realized stats from backend)
    if (pnlTimeframe !== 'holdings') {
        updateRealizedPnL();
    } else {
        refreshMainPnLDisplay();
    }

    console.log(`[PNL-UI] Mode switched to: ${pnlTimeframe}`);
    refreshMainPnLDisplay();
}

// [ANTIGRAVITY FIX] Bridge for settings panel to update sidebar
// [ANTIGRAVITY FIX] Sync from settings panel
window.syncPnLTimeframe = function (newTimeframe) {
    if (pnlTimeframe === newTimeframe) return;
    pnlTimeframe = newTimeframe;
    window.pnlTimeframe = newTimeframe;
    localStorage.setItem('pnlTimeframe', pnlTimeframe);
    updateRealizedPnL();
    refreshMainPnLDisplay();
    console.log(`[PNL-SYNC] Timeframe synchronized from settings: ${pnlTimeframe}`);
};

// [ANTIGRAVITY] Helper to refresh chart formatting without creating a new instance
function refreshChartTimeFormat() {
    if (!chart) return;
    // [ANTIGRAVITY] Delegate to shared formatters — no duplicated logic
    chart.applyOptions({
        timeScale: { tickMarkFormatter: _chartTickMarkFormatter },
        localization: { timeFormatter: _chartTimeFormatter },
    });
}

window.syncTimeFormat = function (newFormat) {
    if (timeFormat === newFormat) return;
    timeFormat = newFormat;
    window.timeFormat = newFormat;
    localStorage.setItem('timeFormat', timeFormat);
    refreshChartTimeFormat();
    console.log(`[TIME-SYNC] Format synchronized from settings: ${timeFormat}`);
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
        // Log is LOCAL time, convert to Unix Seconds based on browser's locale
        return Math.floor(new Date(match[1].replace(' ', 'T')).getTime() / 1000);
    }
    return Math.floor(Date.now() / 1000);
}

function initChart(intervalSeconds = 900) {
    const chartContainer = document.getElementById('chart-area');
    if (!chartContainer) return;

    // [ANTIGRAVITY] Idempotent: reuse existing chart, just refresh options
    if (chart) {
        chart.applyOptions({
            timeScale: {
                tickMarkFormatter: _chartTickMarkFormatter,
            },
            localization: {
                timeFormatter: _chartTimeFormatter,
            },
        });
        return;
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
            secondsVisible: false,
            tickMarkFormatter: _chartTickMarkFormatter,
        },
        localization: {
            timeFormatter: _chartTimeFormatter,
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

    candleSeries = chart.addCandlestickSeries({
        upColor: '#2dd4bf',     // Teal
        downColor: '#f43f5e',   // Rose
        borderVisible: false,
        wickUpColor: '#2dd4bf',
        wickDownColor: '#f43f5e',
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

    // [ANTIGRAVITY] Single ResizeObserver — module-scoped to prevent leaks
    if (chartResizeObserver) chartResizeObserver.disconnect();
    chartResizeObserver = new ResizeObserver(entries => {
        if (entries.length === 0 || !entries[0].contentRect) return;
        const width = entries[0].contentRect.width;
        const height = entries[0].contentRect.height;
        chart.applyOptions({ width, height });
    });
    chartResizeObserver.observe(chartContainer);

    // [ANTIGRAVITY] Dummy data removed. Waiting for 'history' from backend.
}

// [ANTIGRAVITY] Shared formatters (referenced by both initChart and refreshChartTimeFormat)
function _chartTickMarkFormatter(time, tickMarkType, locale) {
    const date = new Date(time * 1000);
    if (timeFormat === '12h') {
        let h = date.getHours();
        const m = date.getMinutes().toString().padStart(2, '0');
        const ampm = h >= 12 ? 'PM' : 'AM';
        h = h % 12;
        h = h ? h : 12;
        return `${h}:${m} ${ampm}`;
    } else {
        const h = date.getHours().toString().padStart(2, '0');
        const m = date.getMinutes().toString().padStart(2, '0');
        return `${h}:${m}`;
    }
}

function _chartTimeFormatter(timestamp) {
    const date = new Date(timestamp * 1000);
    if (timeFormat === '12h') {
        let h = date.getHours();
        const m = date.getMinutes().toString().padStart(2, '0');
        const ampm = h >= 12 ? 'PM' : 'AM';
        h = h % 12;
        h = h ? h : 12;
        return `${h}:${m} ${ampm}`;
    } else {
        const h = date.getHours().toString().padStart(2, '0');
        const m = date.getMinutes().toString().padStart(2, '0');
        return `${h}:${m}`;
    }
}

function subscribeToAsset(symbol, tf) {
    console.log(`[SUBSCRIBE] Attempting to subscribe to ${symbol} (${tf}). WS state: ${ws ? ws.readyState : 'null'}`);

    // [ANTIGRAVITY FIX] Clear chart immediately to prevent "stale" data from old symbol showing
    if (candleSeries) {
        candleSeries.setData([]);
        if (indicatorSeries) indicatorSeries.setData([]);
        candleData = [];
    }

    // Reset previous symbol tracking to force marker clearing on next history message
    // Actually, clear markers NOW for better UX
    console.log(`[SUBSCRIBE] Clearing markers for ${symbol} before subscription...`);
    clearTradeMarkers();
    previousSymbol = symbol.toUpperCase();

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

        // [ANTIGRAVITY] Subscribe to current UI selection on open
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

        // [ANTIGRAVITY] Periodic chart refresh to keep data live
        // Fetch updated history every 15 seconds since the bot only broadcasts
        // candles during scan cycles which can be 15-60+ seconds apart
        let chartRefreshInterval;
        if (window._chartRefreshInterval) clearInterval(window._chartRefreshInterval);
        window._chartRefreshInterval = setInterval(() => {
            if (ws && ws.readyState === WebSocket.OPEN) {
                const sym = document.getElementById('chart-symbol-label')?.innerText?.trim();
                const tf = document.getElementById('chart-tf-label')?.innerText?.trim() || '15m';
                if (sym) {
                    console.log(`[CHART-REFRESH] Polling history for ${sym} (${tf})...`);
                    ws.send(JSON.stringify({ type: 'subscribe', symbol: sym, tf }));
                }
            }
        }, 15000); // Refresh every 15 seconds
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

                    // [DEBUG] Log first candle to verify 12h issue
                    if (msg.data.length > 0) {
                        const first = msg.data[0];
                        const date = new Date(first.time * 1000);
                        const debugMsg = `[CHART-DEBUG] ${msg.symbol} Hist[0]: Epoch=${first.time} | Year=${date.getUTCFullYear()} | UTC=${date.toUTCString()} | Format=${timeFormat}`;
                        console.log(debugMsg);
                        logToServer(debugMsg);
                    }

                    const isFx = isForex(msg.symbol);
                    const fxOffset = isFx ? (12 * 3600) : 0;
                    if (isFx) console.log(`[CHART] Applying 12h Forex offset to ${msg.symbol}`);

                    const fixedData = msg.data.map(c => ({
                        time: c.time + fxOffset,
                        open: c.open, high: c.high, low: c.low, close: c.close
                    }));
                    candleSeries.setData(fixedData);
                    candleData = fixedData;

                    if (indicatorSeries) {
                        const volumeData = msg.data.map(c => {
                            const isUp = c.close >= c.open;
                            return {
                                time: c.time + fxOffset,
                                value: c.volume || 0,
                                color: isUp ? '#2dd4bf' : '#f43f5e'
                            };
                        });
                        console.log(`[CHART-VOLUME] Setting ${volumeData.length} volume bars.`);
                        indicatorSeries.setData(volumeData);
                    }

                    updateIndicators();

                    const msgSym = msg.symbol.toUpperCase();
                    previousSymbol = msgSym;

                    // [ANTIGRAVITY FIX] Refresh markers from cache using current snapped TF
                    refreshChartMarkers(msgSym);

                    if (lastHoldings && lastHoldings.positions) {
                        const pos = parsePositionFromHoldings(lastHoldings.positions, msg.symbol);
                        if (pos) {
                            updatePositionLines(pos);
                        }
                    }

                    // [ANTIGRAVITY FIX] Only fit content on FIRST load or symbol change
                    if (!window._lastChartSymbol || window._lastChartSymbol !== msg.symbol) {
                        chart.timeScale().fitContent();
                        window._lastChartSymbol = msg.symbol;
                    }
                }
            } else if (msg.type === 'candle') {
                const currentSym = (document.getElementById('chart-symbol-label')?.innerText || "").trim().toUpperCase();
                const currentTfRaw = (document.getElementById('chart-tf-label')?.innerText || '15m').trim();

                if (msg.symbol === currentSym) {
                    // [DEBUG] Log candle to verify 12h issue
                    const date = new Date(msg.data.time * 1000);
                    const debugMsg = `[CHART-DEBUG] ${msg.symbol} Tick: Epoch=${msg.data.time} | Year=${date.getUTCFullYear()} | UTC=${date.toUTCString()} | Format=${timeFormat}`;
                    console.log(debugMsg);
                    // Only log real-time ticks back to server occasionally to avoid noise
                    if (Math.random() < 0.1) logToServer(debugMsg);

                    // [ANTIGRAVITY FIX] Snap candle timestamp to current chart timeframe
                    const isFx = isForex(msg.symbol);
                    const fxOffset = isFx ? (12 * 3600) : 0;
                    const chartTfSeconds = tfToSeconds(currentTfRaw);
                    const snappedTime = (Math.floor(msg.data.time / chartTfSeconds) * chartTfSeconds) + fxOffset;

                    const fixedData = {
                        time: snappedTime,
                        open: msg.data.open, high: msg.data.high, low: msg.data.low, close: msg.data.close
                    };
                    candleSeries.update(fixedData);

                    if (indicatorSeries && typeof msg.data.volume !== 'undefined') {
                        const isUp = msg.data.close >= msg.data.open;
                        indicatorSeries.update({
                            time: snappedTime,
                            value: msg.data.volume,
                            color: isUp ? '#2dd4bf' : '#f43f5e'
                        });
                    }
                }
            } else if (msg.type === 'log') {
                parseLogLine(msg.data);
                appendLog(msg.level || "INFO", msg.data);
            } else if (msg.type === 'state') {
                const data = msg.data;
                // [ANTIGRAVITY] All state updates go through dashboardState → syncUI()
                if (data.time_format && data.time_format !== timeFormat) {
                    console.log(`[STATE] Updating timeFormat to ${data.time_format} from backend`);
                    timeFormat = data.time_format;
                    window.timeFormat = data.time_format;
                    dashboardState.timeFormat = data.time_format;
                    localStorage.setItem('timeFormat', timeFormat);
                    refreshChartTimeFormat();
                }

                if (data.pnl_stats && data.pnl_stats[pnlTimeframe] !== undefined) {
                    currentRealizedPnL = parseFloat(data.pnl_stats[pnlTimeframe]);
                    refreshMainPnlDisplay();
                }
                if (data.capital !== undefined) {
                    dashboardState.capital = data.capital;
                }
                if (data.cash !== undefined) {
                    dashboardState.cash = data.cash;
                }
                if (data.profile) {
                    dashboardState.profile = data.profile.toUpperCase();
                    const profileEl = document.getElementById('status-profile');
                    if (profileEl) profileEl.className = "text-xs text-emerald-400 font-bold drop-shadow-sm";
                }
                if (data.is_sabbath !== undefined) {
                    dashboardState.isSabbath = data.is_sabbath;
                }
                if (data.symbols && Array.isArray(data.symbols) && data.symbols.length > 0) {
                    WATCHED_SYMBOLS.splice(0, WATCHED_SYMBOLS.length, ...data.symbols);
                    dashboardState.symbols = [...data.symbols];
                    const currentSym = document.getElementById('chart-symbol-label')?.innerText;
                    const newIdx = WATCHED_SYMBOLS.indexOf(currentSym);
                    if (newIdx !== -1) currentSymbolIndex = newIdx;
                    else {
                        currentSymbolIndex = 0;
                        updateSymbolDisplay();
                    }
                }
                syncUI();
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

function updateIndicators() {
    if (!candleData || candleData.length < 21) return;

    if (emaSeries) {
        const emaData = calculateEMA(candleData, 21);
        emaSeries.setData(emaData);
    }
    if (smaSeries) {
        const smaData = calculateSMA(candleData, 50);
        smaSeries.setData(smaData);
    }
}

// --- Trade Marker Functions ---
// [ANTIGRAVITY FIX] Dynamic Marker Refresher
// Translates RAW timestamps into TF-snapped signal candle positions
function refreshChartMarkers(symbol) {
    const sym = (symbol || (document.getElementById('chart-symbol-label')?.innerText || "")).trim().toUpperCase();
    if (!sym || !markerCache[sym]) return;

    const tfRaw = (document.getElementById('chart-tf-label')?.innerText || '15m').trim();
    const interval = tfToSeconds(tfRaw);

    // Map markers to snapped positions
    const isFx = isForex(sym);
    const fxOffset = isFx ? (12 * 3600) : 0;

    const snappedMarkers = markerCache[sym].map(m => {
        // Snap raw log time to previous candle (signal candle)
        const adjustedTime = m.rawTime + fxOffset;
        const snappedTime = Math.floor(adjustedTime / interval) * interval - interval;
        return {
            ...m,
            time: snappedTime
        };
    });

    // Deduplicate by snapped time + shape (avoid stacking markers on one candle)
    const uniqueMarkers = [];
    const seen = new Set();
    for (const m of snappedMarkers) {
        const key = `${m.time}_${m.shape}`;
        if (!seen.has(key)) {
            uniqueMarkers.push(m);
            seen.add(key);
        }
    }

    tradeMarkers = uniqueMarkers;
    console.log(`[CHART-RENDER] Refreshed markers for ${sym} (TF: ${tfRaw}). Total Unique: ${tradeMarkers.length}`);
    if (candleSeries) {
        candleSeries.setMarkers(tradeMarkers);
    }
}

function addTradeMarker(time, isBuy, symbol, price, customText = null) {
    const sym = symbol.toUpperCase();
    if (!markerCache[sym]) markerCache[sym] = [];

    // [ANTIGRAVITY FIX] Use rawTime for persistent caching
    const rawTime = time;

    const marker = {
        rawTime: rawTime,
        position: isBuy ? 'belowBar' : 'aboveBar',
        color: isBuy ? '#22c55e' : '#ef4444',
        shape: isBuy ? 'arrowUp' : 'arrowDown',
        text: customText || (isBuy ? `▶ BUY ${price?.toFixed(2) || ''}` : `◀ SELL ${price?.toFixed(2) || ''}`),
        size: 2,
    };

    // Deduplicate by RAW time (avoid double-parsing same log)
    const exists = markerCache[sym].some(m => Math.abs(m.rawTime - rawTime) < 1 && m.shape === marker.shape);
    if (!exists) {
        markerCache[sym].push(marker);
        markerCache[sym].sort((a, b) => a.rawTime - b.rawTime);
        refreshChartMarkers(sym);
    }
}

// [ANTIGRAVITY] Exit marker function for closed trades
function addExitMarker(time, isWin, symbol, price, pnlPct, customText = null) {
    const sym = symbol.toUpperCase();
    if (!markerCache[sym]) markerCache[sym] = [];

    const rawTime = time;
    const pnlStr = pnlPct ? `${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(1)}%` : '';
    const marker = {
        rawTime: rawTime,
        position: 'aboveBar',
        color: isWin ? '#10b981' : '#f43f5e',  // Emerald for win, Rose for loss
        shape: 'square',  // Square shape for exits (different from arrows for entries)
        text: customText || (price ? `◀ EXIT ${price?.toFixed(2) || ''} (${pnlStr})` : `◀ EXIT (${pnlStr})`),
        size: 1,
    };

    // Deduplicate by RAW time
    const exists = markerCache[sym].some(m => Math.abs(m.rawTime - rawTime) < 1 && m.shape === marker.shape);
    if (!exists) {
        markerCache[sym].push(marker);
        markerCache[sym].sort((a, b) => a.rawTime - b.rawTime);
        refreshChartMarkers(sym);
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

    // Entry is shown as a MARKER (from [ENTRY] logs), not a line
    // SL and TP remain as horizontal lines

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
// [ANTIGRAVITY] Known-safe tag whitelist for log colorization
const LOG_TAG_STYLES = {
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

const ACTION_KEYWORDS_BUY = /\b(BUY|LONG|ENTER_LONG|A\+)\b/gi;
const ACTION_KEYWORDS_SELL = /\b(SELL|SHORT|ENTER_SHORT)\b/gi;
const MONEY_PATTERN = /(\$\s?[\d\.,]+)/g;

// [ANTIGRAVITY] Returns a DocumentFragment with XSS-safe colorized log content
function formatLogMessageSafe(msg) {
    const frag = document.createDocumentFragment();
    // Strip timestamps
    let cleaned = msg.replace(/^\[\d{2}:\d{2}:\d{2}\]\s*/, '')
        .replace(/^\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}[,\.]\d+\s*/, '');

    // Tokenize by known tags [TAG]
    const tagRegex = /\[([A-Z]+)\]/g;
    let lastIndex = 0;
    let match;

    while ((match = tagRegex.exec(cleaned)) !== null) {
        // Text before this tag — safe textContent
        if (match.index > lastIndex) {
            const textBefore = cleaned.slice(lastIndex, match.index);
            frag.appendChild(_colorizeText(textBefore));
        }
        // The tag itself — only colorize if it's in our whitelist
        const tagName = match[1];
        const span = document.createElement('span');
        span.className = LOG_TAG_STYLES[tagName] || 'text-slate-400';
        span.textContent = `[${tagName}]`;
        frag.appendChild(span);
        lastIndex = match.index + match[0].length;
    }
    // Remaining text after last tag
    if (lastIndex < cleaned.length) {
        frag.appendChild(_colorizeText(cleaned.slice(lastIndex)));
    }
    return frag;
}

// [ANTIGRAVITY] Colorize known action keywords and dollar amounts in safe text
function _colorizeText(text) {
    const frag = document.createDocumentFragment();
    // Split by action keywords and money patterns for colorization
    const combined = /\b(BUY|LONG|ENTER_LONG|A\+|SELL|SHORT|ENTER_SHORT)\b|(\$\s?[\d\.,]+)/gi;
    let lastIdx = 0;
    let m;
    while ((m = combined.exec(text)) !== null) {
        if (m.index > lastIdx) {
            frag.appendChild(document.createTextNode(text.slice(lastIdx, m.index)));
        }
        const span = document.createElement('span');
        if (m[1]) {
            // Action keyword
            const kw = m[1].toUpperCase();
            if (['BUY', 'LONG', 'ENTER_LONG', 'A+'].includes(kw)) {
                span.className = 'text-green-400 font-black';
            } else {
                span.className = 'text-red-500 font-black';
            }
        } else {
            // Money
            span.className = 'text-teal-400';
        }
        span.textContent = m[0];
        frag.appendChild(span);
        lastIdx = m.index + m[0].length;
    }
    if (lastIdx < text.length) {
        frag.appendChild(document.createTextNode(text.slice(lastIdx)));
    }
    return frag;
}

function appendLog(level, rawMessage) {
    if (!logTerminal) {
        logTerminal = document.getElementById('log-terminal');
        if (!logTerminal) return;
    }
    const div = document.createElement('div');
    const ts = formatTime();

    if (level === 'GUI') {
        div.className = "log-line py-1 px-2 my-1 rounded bg-amber-500/10 border-l-2 border-amber-500/50 text-amber-200/90 font-bold";
        const guiTag = document.createElement('span');
        guiTag.className = 'text-amber-500/60 font-mono text-[10px] mr-2';
        guiTag.textContent = '[GUI]';
        div.appendChild(guiTag);
        div.appendChild(document.createTextNode(' ' + rawMessage));
    } else {
        div.className = "log-line text-white/90 py-0.5";
        const tsSpan = document.createElement('span');
        tsSpan.className = 'text-slate-600 font-mono';
        tsSpan.textContent = `[${ts}]`;
        div.appendChild(tsSpan);
        div.appendChild(document.createTextNode(' '));
        div.appendChild(formatLogMessageSafe(rawMessage));
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

    // Clear placeholder and existing content [ANTIGRAVITY] safe DOM removal
    while (scroller.firstChild) scroller.removeChild(scroller.firstChild);

    // Parse markdown-like formatting from AI response
    const lines = content.split('\n');
    let currentSection = null;
    let sectionContent = [];

    const createBubble = (title, text, icon, colorClass) => {
        const bubble = document.createElement('div');
        bubble.className = `insight-bubble bg-black/40 border border-${colorClass}-500/30 rounded-xl p-4 backdrop-blur-sm`;

        // [ANTIGRAVITY] XSS-safe: createElement + textContent
        const wrapper = document.createElement('div');
        wrapper.className = 'flex items-start gap-3';

        const iconEl = document.createElement('span');
        iconEl.className = `material-symbols-outlined text-${colorClass}-400 text-lg mt-0.5`;
        iconEl.textContent = icon;

        const contentDiv = document.createElement('div');
        contentDiv.className = 'flex-1';

        const titleDiv = document.createElement('div');
        titleDiv.className = `text-[10px] font-bold uppercase tracking-wider text-${colorClass}-400 mb-1`;
        titleDiv.textContent = title;

        const textDiv = document.createElement('div');
        textDiv.className = 'text-xs text-slate-300 leading-relaxed';
        textDiv.textContent = text;

        contentDiv.appendChild(titleDiv);
        contentDiv.appendChild(textDiv);
        wrapper.appendChild(iconEl);
        wrapper.appendChild(contentDiv);
        bubble.appendChild(wrapper);
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
        const bubble = createBubble(section.title, section.content.join('\n'), section.icon, section.color);
        scroller.appendChild(bubble);
    }

    // Add update timer footer
    const footer = document.createElement('div');
    footer.className = 'insight-footer flex items-center justify-between text-[10px] text-slate-500 pt-3 border-t border-white/5 mt-4';

    // [ANTIGRAVITY] XSS-safe footer
    const footerLeft = document.createElement('span');
    footerLeft.className = 'flex items-center gap-1';
    const schedIcon = document.createElement('span');
    schedIcon.className = 'material-symbols-outlined text-xs';
    schedIcon.textContent = 'schedule';
    footerLeft.appendChild(schedIcon);
    footerLeft.appendChild(document.createTextNode(` Updated ${timestamp}`));

    const footerRight = document.createElement('span');
    footerRight.id = 'ai-countdown';
    footerRight.className = 'text-teal-500/70';
    footerRight.textContent = `Next update in ${Math.floor(nextUpdateIn / 60)}m`;

    footer.appendChild(footerLeft);
    footer.appendChild(footerRight);
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

function addDecisionRow(symbol, action, scoreNum, reason, forcedGrade = null) {
    const table = document.getElementById('decisions-table');
    if (!table) return;

    // DE-DUPLICATE: Find existing row for this symbol
    let existingRow = null;
    for (let row of table.rows) {
        if (row.cells[1]?.textContent === symbol) {
            existingRow = row;
            break;
        }
    }

    const row = existingRow || document.createElement('tr');
    row.className = "hover:bg-cyan-500/5 transition-colors border-b border-slate-700/20";

    // Time AM/PM
    const time = formatTime();

    // Grade
    const grade = forcedGrade || getScoreGrade(scoreNum);
    const scoreClass = getScoreColor(grade);

    // Action color mapping (whitelist-validated, no raw HTML injection)
    const actUpper = (action || '').toUpperCase();
    let actionClass = 'text-cyan-400 font-bold text-glow-sm';
    if (['ENTER_LONG', 'BUY', 'ENTRY', 'FILL'].includes(actUpper)) {
        actionClass = 'text-green-400 font-bold text-glow-sm';
    } else if (['ENTER_SHORT', 'SELL', 'EXIT'].includes(actUpper)) {
        actionClass = 'text-red-500 font-bold text-glow-sm';
    } else if (['HOLD', 'WAIT', 'CONTINUATION'].includes(actUpper)) {
        actionClass = 'text-slate-400 font-bold text-glow-sm';
    }

    // [ANTIGRAVITY] Build row with createElement/textContent (XSS-safe)
    // Clear existing cells
    while (row.firstChild) row.removeChild(row.firstChild);

    const cellDefs = [
        { text: time, cls: 'px-4 py-1.5 text-slate-500 text-left font-mono text-sm' },
        { text: symbol, cls: 'px-4 py-1.5 font-bold text-slate-200 text-left text-lg' },
        { text: actUpper, cls: `px-4 py-1.5 text-left text-sm uppercase tracking-wider ${actionClass}` },
        { text: grade, cls: `px-4 py-1.5 ${scoreClass} text-left font-black text-lg` },
        { text: reason, cls: 'px-4 py-1.5 text-slate-400 text-sm italic text-left' },
    ];

    cellDefs.forEach(def => {
        const td = document.createElement('td');
        td.className = def.cls;
        td.textContent = def.text;
        row.appendChild(td);
    });

    if (!existingRow) {
        table.prepend(row);
    }
}

// --- IPC / Socket Logic ---
let capitalDisplayMode = 'equity';
window.api.on('env-updated', (updates) => {
    console.log("[UI] Environment updated:", updates);
    if (updates.GUI_CAPITAL_DISPLAY_MODE) {
        capitalDisplayMode = updates.GUI_CAPITAL_DISPLAY_MODE;
    }
    if (updates.GUI_PNL_TIMEFRAME) {
        pnlTimeframe = updates.GUI_PNL_TIMEFRAME;
        dashboardState.pnlTimeframe = pnlTimeframe;
        updateRealizedPnL();
    }
    if (updates.APP_PROFILE) {
        dashboardState.profile = updates.APP_PROFILE.toUpperCase();
        const profileEl = document.getElementById('status-profile');
        if (profileEl) profileEl.className = "text-xs text-emerald-400 font-bold drop-shadow-sm";
        syncUI();
        appendLog("SYSTEM", `Active Profile changed to ${dashboardState.profile}`);
    }
});

window.api.on('fromMain', (payload) => {
    if (payload.type === 'log-chunk') {
        // [ANTIGRAVITY FIX] DO NOT WIPE CACHE. 
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

    // [ANTIGRAVITY] Clear existing via DOM (no innerHTML)
    while (tbody.firstChild) tbody.removeChild(tbody.firstChild);

    payload.positions.forEach(pos => {
        const row = document.createElement('tr');
        row.className = "border-b border-slate-700/30 hover:bg-slate-800/20 transition-colors";

        const rawPnl = parseFloat(pos.unrealized_pnl);
        const pnlClass = (rawPnl >= 0) ? "text-green-400" : "text-red-500";
        const pnlSign = (rawPnl >= 0) ? "+" : "";
        const sideClass = (pos.side && pos.side.toUpperCase() === 'SHORT') ? "text-red-400" : "text-green-400";
        const displayPnl = isNaN(rawPnl) ? "0.00" : rawPnl.toFixed(2);
        const displaySize = Math.abs(parseFloat(pos.size)).toFixed(4);

        // [ANTIGRAVITY] XSS-safe: createElement + textContent
        const cellDefs = [
            { text: pos.symbol || '', cls: 'p-2 font-mono font-bold text-slate-200' },
            { text: pos.side ? pos.side.toUpperCase() : 'LONG', cls: `p-2 text-center ${sideClass} font-bold text-xs` },
            { text: displaySize, cls: 'p-2 text-right font-mono text-slate-400' },
            { text: `${pnlSign}$${displayPnl}`, cls: `p-2 text-right font-mono font-bold ${pnlClass}` },
        ];
        cellDefs.forEach(def => {
            const td = document.createElement('td');
            td.className = def.cls;
            td.textContent = def.text;
            row.appendChild(td);
        });
        tbody.appendChild(row);
    });

    // Handle empty state
    if (payload.positions.length === 0) {
        const emptyRow = document.createElement('tr');
        const emptyTd = document.createElement('td');
        emptyTd.colSpan = 4;
        emptyTd.className = 'p-4 text-center text-slate-500 italic text-xs';
        emptyTd.textContent = 'No active positions';
        emptyRow.appendChild(emptyTd);
        tbody.appendChild(emptyRow);
    }

    // [ANTIGRAVITY FIX] Update sidebar PNL
    if (payload.total_unrealized_pnl !== undefined) {
        currentUnrealizedPnL = parseFloat(payload.total_unrealized_pnl);
        refreshMainPnlDisplay();
    }

    // [ANTIGRAVITY] Cache holdings and draw SL/TP/Entry lines for current symbol
    lastHoldings = payload;
    const currentSym = (document.getElementById('chart-symbol-label')?.innerText || "").trim().toUpperCase();
    console.log(`[CHART-DEBUG] Holdings received. Looking for ${currentSym} in positions:`, payload.positions?.map(p => p.symbol));
    if (currentSym && payload.positions) {
        const pos = parsePositionFromHoldings(payload.positions, currentSym);
        console.log(`[CHART-DEBUG] Parsed position for ${currentSym}:`, pos);

        // Draw SL/TP lines
        if (pos && (pos.sl || pos.tp)) {
            console.log(`[CHART-DEBUG] Drawing lines - SL: ${pos.sl}, TP: ${pos.tp}`);
            updatePositionLines(pos);
        }

        // [ANTIGRAVITY] Add entry marker from holdings entry_time
        if (pos && pos.entryTime && pos.entry) {
            let entryTimeSec = Math.floor(new Date(pos.entryTime).getTime() / 1000);
            const tfRaw = (document.getElementById('chart-tf-label')?.innerText || '15m').trim();
            const interval = tfToSeconds(tfRaw);

            // Snap to candle start and shift back by one to hit the signal candle
            const snappedTime = Math.floor(entryTimeSec / interval) * interval;
            entryTimeSec = snappedTime - interval;

            const isBuy = (pos.side === 'long');
            addTradeMarker(entryTimeSec, isBuy, currentSym, pos.entry);
        }
    }
}


function parseLogLine(line) {
    if (!line) return;

    // Check for EXIT logs to trigger PnL refresh and add exit marker
    if (line.includes('[EXIT]')) {
        setTimeout(updateRealizedPnL, 1000); // Small delay to let filesystem sync if needed

        // [ANTIGRAVITY] Parse EXIT for exit marker with PnL
        const symbolMatch = line.match(/\[EXIT\][^:]*:\s*([A-Z0-9]+)/i) || line.match(/\[EXIT\]\s+([A-Z0-9]+)/i);
        const pnlMatch = line.match(/([+-]?\$[\d.]+)/);
        const pctMatch = line.match(/Pct=([+-]?[\d.]+)%?/i);

        if (symbolMatch) {
            let logTime = parseLogTimestamp(line);
            const pnlPct = pctMatch ? parseFloat(pctMatch[1]) : null;
            const isWin = pnlMatch ? pnlMatch[1].startsWith('+') : (pnlPct !== null && pnlPct >= 0);
            const priceFromPnl = pnlMatch ? Math.abs(parseFloat(pnlMatch[1].replace('$', ''))) : null;

            // [ANTIGRAVITY FIX] Pass RAW logTime, addExitMarker handles snapping
            addExitMarker(logTime, isWin, symbolMatch[1], priceFromPnl, pnlPct);

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
            const price = priceMatch ? parseFloat(priceMatch[1]) : null;

            // [ANTIGRAVITY FIX] Pass RAW logTime, addTradeMarker handles snapping
            addTradeMarker(logTime, true, symbolMatch[1], price);

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

            // [ANTIGRAVITY FIX] Handle key-value format "symbol=BTCUSD action=..."
            const parts = content.split('|');
            let head = parts[0].trim();

            let symbol = "UNKNOWN";
            // Try key-value parse first
            const kvSymbolMatch = content.match(/symbol=([A-Z0-9]+)/i);
            if (kvSymbolMatch) {
                symbol = kvSymbolMatch[1].toUpperCase();
            } else {
                // Fallback to old "BTCUSD | ..." format
                const headMatch = head.match(/^([A-Z0-9]+)/);
                if (headMatch) symbol = headMatch[1];
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

            // [ANTIGRAVITY FIX] Force "HOLD" to display if it comes from a Decision log
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

            console.log(`[DECISION-UI] Decision Row for ${symbol}: action=${action}, score=${score}`);
            addDecisionRow(symbol, action, score, reason, forcedGrade);

            // Chart Indicator (The "Grey Bars" that should be colorful)
            const headerSym = document.getElementById('chart-symbol-label')?.innerText;
            if (indicatorSeries && symbol === headerSym) {
                const tzOffsetSeconds = new Date().getTimezoneOffset() * 60;
                const nowSec = Math.floor(Date.now() / 1000) - tzOffsetSeconds;

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

    // 2. Profile Parsing (Enhanced) — [ANTIGRAVITY] Now writes to dashboardState only
    if (line.includes('[PROFILE]') || line.includes('profile=') || line.includes('switching to')) {
        const profileMatch = line.match(/profile[:=]\s?([\w\-]+)/i) ||
            line.match(/switching to (?:profile\s+)?([\w\-]+)/i);
        if (profileMatch) {
            const prof = profileMatch[1];
            console.log("[UI-DEBUG] Parsed profile from log:", prof);
            dashboardState.profile = prof.toUpperCase();
            const profileEl = document.getElementById('status-profile');
            if (profileEl) profileEl.className = "text-xs text-emerald-400 font-bold drop-shadow-sm";
            syncUI();
            saveState();
        }
    }

    // 3. P&L / Equity / Capital (Consolidated & Robust)

    // [ANTIGRAVITY FIX] Strict Capital Logic
    // We ONLY update Capital, never PnL (which comes from [HOLDINGS])

    // 3. P&L / Equity / Capital — [ANTIGRAVITY] Now writes to dashboardState only
    let isOandaProfile = false;
    const currentProfile = (dashboardState.profile || '').toLowerCase();
    if (currentProfile.includes("oanda") || currentProfile.includes("forex")) {
        isOandaProfile = true;
    }

    // Capital / NAV 
    // [ANTIGRAVITY] Use dashboardState.capitalCache instead of window.capitalCache
    const cc = dashboardState.capitalCache;

    // 1. [TOTAL] Source (Aggregated by RoutedExchangeBroker - Authoritative)
    if (line.includes('[TOTAL] Liquidity available:')) {
        const totalMatch = line.match(/available: \$([\d\.,\-]+)/);
        if (totalMatch) cc['TOTAL'] = parseFloat(totalMatch[1].replace(/,/g, ''));
    }
    // 2. [HEARTBEAT] Source
    else if (line.includes('[HEARTBEAT] Capital available:')) {
        const hbMatch = line.match(/Capital available: \$([\d\.,\-]+)/);
        if (hbMatch) cc['HEARTBEAT'] = parseFloat(hbMatch[1].replace(/,/g, ''));
    }
    // 3. Broker Specifics (OANDA/CCXT/IBKR)
    else if (line.includes('[OANDA] Account Summary:')) {
        const oMatch = line.match(/NAV=([\d\.,\-]+)/);
        if (oMatch) cc['OANDA'] = parseFloat(oMatch[1].replace(/,/g, ''));
    }
    else if (line.includes('[CCXT] get_liquid_capital')) {
        const cMatch = line.match(/winner=\$([\d\.,\-]+)/);
        if (cMatch) cc['CCXT'] = parseFloat(cMatch[1].replace(/,/g, ''));
    }
    else if (line.includes('[IBKR] Account Summary') || line.includes('TotalCashValue=')) {
        const iMatch = line.match(/TotalCashValue=([\d\.,\-]+)/);
        if (iMatch) cc['IBKR'] = parseFloat(iMatch[1].replace(/,/g, ''));
    }
    // 4. [CASH] Source (Raw Buying Power / Available Cash)
    else if (line.includes('[CASH] Buying Power:')) {
        const cashMatch = line.match(/Power: \$([\d\.,\-]+)/);
        if (cashMatch) cc['CASH'] = parseFloat(cashMatch[1].replace(/,/g, ''));
    }

    // Determine the most robust value based on user preference
    const displayMode = capitalDisplayMode || 'equity';

    if (displayMode === 'cash') {
        dashboardState.capitalLabel = "Buying Power:";
        let capVal = cc['CASH'];
        if (capVal === undefined || capVal === null) {
            const total = (cc['OANDA'] || 0) + (cc['CCXT'] || 0) + (cc['IBKR'] || 0);
            if (total > 0) capVal = total;
        }
        if (capVal !== null && capVal !== undefined) dashboardState.capital = capVal;
    } else {
        dashboardState.capitalLabel = "Overall Capital:";
        const capVal = cc['TOTAL'] || cc['HEARTBEAT'];
        if (capVal !== null && capVal !== undefined) dashboardState.capital = capVal;
    }

    syncUI();

    // 4. AI Insight (Timestamped Bubbles) — [ANTIGRAVITY] XSS-safe with createElement
    if (line.includes('[COMMENTARY]') || line.includes('commentary:') || line.includes('Insight:')) {
        const textParts = line.split(/\[COMMENTARY\]|commentary:|Insight:/i);
        if (textParts.length > 1) {
            const text = textParts[1].trim().replace(/^"|"$/g, '');
            const scroller = document.getElementById('insight-scroller');
            if (scroller) {
                // Clear initial placeholder if this is the first real message
                const placeholder = scroller.querySelector('.italic.text-slate-500');
                if (placeholder) {
                    while (scroller.firstChild) scroller.removeChild(scroller.firstChild);
                }

                const div = document.createElement('div');
                div.className = "insight-bubble bg-teal-500/5 border border-teal-500/20 rounded-xl p-4 mb-4 animate-in fade-in slide-in-from-bottom-2 duration-500";

                const ts = formatTime();

                // Header row
                const header = document.createElement('div');
                header.className = 'flex justify-between items-center mb-2';
                const titleSpan = document.createElement('span');
                titleSpan.className = 'text-[9px] font-black uppercase tracking-widest text-teal-400 opacity-70';
                titleSpan.textContent = 'AI Signal Analysis';
                const tsSpan = document.createElement('span');
                tsSpan.className = 'text-[9px] font-mono text-slate-500';
                tsSpan.textContent = ts;
                header.appendChild(titleSpan);
                header.appendChild(tsSpan);

                // Body
                const body = document.createElement('div');
                body.className = 'text-slate-200 text-sm leading-relaxed';
                body.textContent = text;

                div.appendChild(header);
                div.appendChild(body);
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
    let row = Array.from(tbody.rows).find(r => r.cells[0]?.textContent === symbol);
    if (!row) {
        row = tbody.insertRow(0);
        row.className = "border-b border-slate-700/30 hover:bg-slate-800/20 transition-colors";
        // [ANTIGRAVITY] XSS-safe: createElement + textContent
        const cellDefs = [
            { text: symbol, cls: 'p-4 font-mono font-bold text-slate-200' },
            { text: '', cls: 'p-4 text-center font-bold text-xs' },
            { text: '---', cls: 'p-4 text-right font-mono text-slate-400' },
            { text: '---', cls: 'p-4 text-right font-mono font-bold text-green-400' },
        ];
        cellDefs.forEach(def => {
            const td = document.createElement('td');
            td.className = def.cls;
            td.textContent = def.text;
            row.appendChild(td);
        });
    }

    const sideCell = row.cells[1];
    sideCell.textContent = side.toUpperCase();
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
            symbolLabel.textContent = sym;
        }
        appendLog("INFO", `[UI] Switched chart to ${sym}`);

        // REFRESH CHART DATA
        console.log(`Refreshing candlestick data for ${sym}...`);
        const tf = document.getElementById('chart-tf-label')?.innerText || '15m';

        // [ANTIGRAVITY] Use subscription instead of full re-init
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
            const sym = (document.getElementById('chart-symbol-label')?.innerText || "").trim();
            if (sym) {
                subscribeToAsset(sym, tf);
                refreshChartMarkers(sym); // [ANTIGRAVITY FIX] Refresh markers on TF change
            }
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
        const sym = (document.getElementById('chart-symbol-label')?.innerText || "").trim();
        if (sym) {
            subscribeToAsset(sym, tf);
            refreshChartMarkers(sym); // [ANTIGRAVITY FIX] Refresh markers on TF change
        }
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

    ['nav-dashboard', 'nav-profile', 'nav-settings', 'nav-graph'].forEach(id => {
        document.getElementById(id)?.addEventListener('click', (e) => {
            // Remove active style from all
            ['nav-dashboard', 'nav-profile', 'nav-settings', 'nav-graph'].forEach(navId => {
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

            // Hide all views first
            if (dashboardView) dashboardView.classList.add('hidden');
            if (analyticsView) analyticsView.classList.add('hidden');
            if (profilesView) profilesView.classList.add('hidden');
            if (settingsView) settingsView.classList.add('hidden');

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
// [ANTIGRAVITY] Phase 4: Config-only persistence (no innerHTML serialization)
function saveState() {
    const state = {
        profile: dashboardState.profile,
        symbol: document.getElementById('chart-symbol-label')?.innerText || dashboardState.activeSymbol,
        timeframe: document.getElementById('chart-tf-label')?.innerText || dashboardState.activeTimeframe,
        isHalted: dashboardState.isHalted || document.getElementById('btn-panic')?.classList.contains('bg-emerald-500'),
        timeFormat: dashboardState.timeFormat,
        pnlTimeframe: dashboardState.pnlTimeframe,
    };
    localStorage.setItem('tradebot_state', JSON.stringify(state));
}

function loadState() {
    const raw = localStorage.getItem('tradebot_state');
    if (!raw) return;
    try {
        const state = JSON.parse(raw);
        if (state.profile) dashboardState.profile = state.profile;
        if (state.symbol) {
            dashboardState.activeSymbol = state.symbol;
            const symEl = document.getElementById('chart-symbol-label');
            if (symEl) symEl.textContent = state.symbol;
        }
        if (state.timeframe) {
            dashboardState.activeTimeframe = state.timeframe;
            const tfEl = document.getElementById('chart-tf-label');
            if (tfEl) tfEl.textContent = state.timeframe;
        }
        if (state.timeFormat) {
            timeFormat = state.timeFormat;
            window.timeFormat = timeFormat;
            dashboardState.timeFormat = timeFormat;
        }
        if (state.pnlTimeframe) {
            pnlTimeframe = state.pnlTimeframe;
            dashboardState.pnlTimeframe = pnlTimeframe;
        }
        if (state.isHalted) setPanicState(true);
        syncUI();
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
                window.syncPnLTimeframe(env.GUI_PNL_TIMEFRAME);
            }
            if (env.GUI_TIME_FORMAT) {
                window.syncTimeFormat(env.GUI_TIME_FORMAT);
            }
            updateRealizedPnL();
        });

        // [ANTIGRAVITY FIX] Chart Refresh Interval (15 Seconds)
        setInterval(() => {
            const sym = document.getElementById('chart-symbol-label')?.innerText || 'EURUSD';
            const tf = document.getElementById('chart-tf-label')?.innerText || '15m';
            console.log(`[SYSTEM] Heartbeat: Refreshing chart for ${sym} @ ${tf}`);
            // We just trigger a visual refresh or data fetch if needed. 
            // Since WebSocket drives updates, this interval ensures the chart stays reactive.
            if (chart) chart.timeScale().scrollToRealTime();
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
        { value: 'supply_demand', label: 'Supply & Demand' }
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
