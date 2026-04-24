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
let marketClosedTimer = null; // Timer to show 'Market Closed' overlay
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

// ── Market Closed Overlay ──────────────────────────────────
function startMarketClosedTimer() {
    clearTimeout(marketClosedTimer);
    marketClosedTimer = setTimeout(() => {
        if (!candleData || candleData.length === 0) {
            const overlay = document.getElementById('market-closed-overlay');
            if (overlay) {
                overlay.classList.remove('hidden');
                overlay.style.display = 'flex';
                overlay.style.opacity = '0';
                requestAnimationFrame(() => {
                    overlay.style.transition = 'opacity 0.6s ease';
                    overlay.style.opacity = '1';
                });
            }
        }
    }, 60000); // 60 seconds — generous to avoid false positives on slow connections
}

function hideMarketClosedOverlay() {
    clearTimeout(marketClosedTimer);
    const overlay = document.getElementById('market-closed-overlay');
    if (overlay && !overlay.classList.contains('hidden')) {
        overlay.style.opacity = '0';
        setTimeout(() => {
            overlay.classList.add('hidden');
            overlay.style.display = 'none';
        }, 400);
    }
}

function initChart(intervalSeconds = 900) {
    const chartContainer = document.getElementById('chart-area');
    if (!chartContainer) return;

    if (chart) {
        chart.remove();
        chart = null;
    }

    // Start market closed detection on chart init
    startMarketClosedTimer();

    chart = LightweightCharts.createChart(chartContainer, {
        autoSize: true,
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

// WebSocket handler — extracted to ws_handler.js

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
// Delegated to indicators.js (loaded before renderer.js)
const calculateSMA = (...a) => window.Indicators.calculateSMA(...a);
const calculateEMA = (...a) => window.Indicators.calculateEMA(...a);
const calculateBollingerBands = (...a) => window.Indicators.calculateBollingerBands(...a);
const calculateVWAP = (...a) => window.Indicators.calculateVWAP(...a);
const calculateRSI = (...a) => window.Indicators.calculateRSI(...a);
const calculateHeikinAshi = (...a) => window.Indicators.calculateHeikinAshi(...a);

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

// chart markers — extracted to chart_markers.js

// --- Log Formatting & Parsing ---
// Delegated to log_parser.js (loaded before renderer.js)
const formatLogMessage = (...a) => window.LogParser.formatLogMessage(...a);
const appendLog = (...a) => window.LogParser.appendLog(...a);

// --- AI Commentary Panel Logic ---
let aiCommentaryTimer = null;
let aiNextUpdateCountdown = 0;

// --- AI Insight Persistence (24h) ---
const AI_INSIGHT_STORAGE_KEY = 'tradebot_ai_insights';
const AI_INSIGHT_MAX_AGE_MS = 24 * 60 * 60 * 1000; // 24 hours
const AI_INSIGHT_MAX_ENTRIES = 20;

function _saveInsightToStorage(content, timestamp) {
    try {
        const raw = localStorage.getItem(AI_INSIGHT_STORAGE_KEY);
        const entries = raw ? JSON.parse(raw) : [];
        entries.unshift({ content, timestamp, epoch: Date.now() });
        // Cap at max entries
        while (entries.length > AI_INSIGHT_MAX_ENTRIES) entries.pop();
        localStorage.setItem(AI_INSIGHT_STORAGE_KEY, JSON.stringify(entries));
    } catch (e) {
        console.warn('[AI-INSIGHT] Failed to save insight to localStorage:', e);
    }
}

function _loadInsightsFromStorage() {
    try {
        const raw = localStorage.getItem(AI_INSIGHT_STORAGE_KEY);
        if (!raw) return [];
        const entries = JSON.parse(raw);
        const cutoff = Date.now() - AI_INSIGHT_MAX_AGE_MS;
        // Filter out expired entries and save back
        const valid = entries.filter(e => e.epoch >= cutoff);
        if (valid.length !== entries.length) {
            localStorage.setItem(AI_INSIGHT_STORAGE_KEY, JSON.stringify(valid));
        }
        return valid;
    } catch (e) {
        console.warn('[AI-INSIGHT] Failed to load insights from localStorage:', e);
        return [];
    }
}

function restoreAIInsights() {
    const entries = _loadInsightsFromStorage();
    if (entries.length === 0) return;

    const scroller = document.getElementById('insight-scroller');
    if (!scroller) return;

    // Remove the placeholder
    const placeholder = scroller.querySelector('.insight-entry');
    if (placeholder) placeholder.remove();

    // Render entries oldest-first so newest ends up at top via prepend
    for (let i = entries.length - 1; i >= 0; i--) {
        const entry = entries[i];
        // Re-render using the same panel function but skip re-saving
        _renderInsightBubbles(scroller, entry.content, entry.timestamp, false);
    }

    // Add a restored footer
    const footer = document.createElement('div');
    footer.className = 'insight-footer flex items-center justify-between text-[10px] text-slate-500 pt-3 border-t border-white/5 mt-2';
    const ago = entries.length > 0 ? _timeAgo(entries[0].epoch) : '';
    footer.innerHTML = `
        <span class="flex items-center gap-1">
            <span class="material-symbols-outlined text-xs">history</span>
            ${entries.length} insight${entries.length !== 1 ? 's' : ''} restored (latest ${ago})
        </span>
        <span id="ai-countdown" class="text-teal-500/70">Waiting for next update...</span>
    `;
    scroller.appendChild(footer);
    scroller.scrollTop = 0;
    console.log(`[AI-INSIGHT] Restored ${entries.length} insight(s) from localStorage`);
}

function _timeAgo(epochMs) {
    const diff = Date.now() - epochMs;
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ${mins % 60}m ago`;
    return 'over 24h ago';
}

function updateAIInsightPanel(content, timestamp, nextUpdateIn) {
    const scroller = document.getElementById('insight-scroller');
    if (!scroller || !content) return;

    // Persist to localStorage
    _saveInsightToStorage(content, timestamp);

    // Remove the placeholder if it still exists
    const placeholder = scroller.querySelector('.insight-placeholder') || scroller.querySelector('.insight-entry');
    if (placeholder) placeholder.remove();

    _renderInsightBubbles(scroller, content, timestamp, true);

    // ── Cap message history at 20 groups to prevent memory bloat ──
    const groups = scroller.querySelectorAll('.insight-message-group');
    if (groups.length > AI_INSIGHT_MAX_ENTRIES) {
        for (let i = AI_INSIGHT_MAX_ENTRIES; i < groups.length; i++) {
            groups[i].remove();
        }
    }

    // ── Add/update countdown footer at the bottom ──
    const oldFooter = scroller.querySelector('.insight-footer');
    if (oldFooter) oldFooter.remove();

    const footer = document.createElement('div');
    footer.className = 'insight-footer flex items-center justify-between text-[10px] text-slate-500 pt-3 border-t border-white/5 mt-2';
    footer.innerHTML = `
        <span class="flex items-center gap-1">
            <span class="material-symbols-outlined text-xs">schedule</span>
            Last updated ${timestamp}
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

    // Scroll to top so the newest message is visible
    scroller.scrollTop = 0;
}

/**
 * Shared renderer: parses AI content into section bubbles and prepends to scroller.
 * Used by both live updates and localStorage restore.
 */
function _renderInsightBubbles(scroller, content, timestamp, animate) {
    const messageGroup = document.createElement('div');
    messageGroup.className = `insight-message-group mb-3${animate ? ' animate-fade-in' : ''}`;

    // Timestamp header
    const header = document.createElement('div');
    header.className = 'flex items-center gap-2 mb-2';
    header.innerHTML = `
        <span class="material-symbols-outlined text-teal-400 text-sm">smart_toy</span>
        <span class="text-[10px] font-bold text-teal-400/80 uppercase tracking-wider">${timestamp}</span>
        <div class="flex-1 h-px bg-gradient-to-r from-teal-500/30 to-transparent"></div>
    `;
    messageGroup.appendChild(header);

    // Parse sections from AI content into bubbles
    const lines = content.split('\n');
    const sections = [];
    let current = { title: 'Market Update', content: [], icon: 'insights', color: 'teal' };

    const escapeHTML = (str) => {
        return str.replace(/[&<>'"]/g, 
            tag => ({
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                "'": '&#39;',
                '"': '&quot;'
            }[tag] || tag)
        );
    };

    for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;

        if (trimmed.includes('📊') || trimmed.toLowerCase().includes("what's happening")) {
            if (current.content.length > 0) sections.push({ ...current });
            current = { title: "What's Happening Now", content: [], icon: 'trending_up', color: 'teal' };
            const rest = trimmed.replace(/.*?(what's happening now|📊):?/i, '').trim();
            if (rest.length > 2) current.content.push(escapeHTML(rest));
        } else if (trimmed.includes('📈') || trimmed.toLowerCase().includes('chart breakdown')) {
            if (current.content.length > 0) sections.push({ ...current });
            current = { title: 'Chart Breakdown', content: [], icon: 'show_chart', color: 'cyan' };
            const rest = trimmed.replace(/.*?(chart breakdown|📈):?/i, '').trim();
            if (rest.length > 2) current.content.push(escapeHTML(rest));
        } else if (trimmed.includes('🎯') || trimmed.toLowerCase().includes('watching')) {
            if (current.content.length > 0) sections.push({ ...current });
            current = { title: "What I'm Watching", content: [], icon: 'visibility', color: 'purple' };
            const rest = trimmed.replace(/.*?(what i'm watching|watching|🎯):?/i, '').trim();
            if (rest.length > 2) current.content.push(escapeHTML(rest));
        } else if (trimmed.includes('⚠️') || trimmed.toLowerCase().includes('heads up')) {
            if (current.content.length > 0) sections.push({ ...current });
            current = { title: 'Heads Up', content: [], icon: 'warning', color: 'amber' };
            const rest = trimmed.replace(/.*?(heads up|⚠️):?/i, '').trim();
            if (rest.length > 2) current.content.push(escapeHTML(rest));
        } else if (trimmed.includes('🤖') || trimmed.toLowerCase().includes('autopilot activated')) {
            if (current.content.length > 0) sections.push({ ...current });
            current = { title: 'Autopilot Activated', content: [], icon: 'psychology', color: 'emerald' };
            const rest = trimmed.replace(/.*?(autopilot activated|🤖):?/i, '').trim();
            if (rest.length > 2) current.content.push(escapeHTML(rest));
        } else {
            let cleaned = trimmed.replace(/\*\*/g, '').replace(/^\s*[-•]\s*/, '• ');
            current.content.push(escapeHTML(cleaned));
        }
    }
    if (current.content.length > 0) sections.push(current);

    // Fallback
    if (sections.length === 0 && content.trim().length > 0) {
        sections.push({
            title: 'AI Insight',
            content: [escapeHTML(content.trim())],
            icon: 'smart_toy',
            color: 'teal'
        });
    }

    // Render each section as a bubble
    for (const section of sections) {
        const bubble = document.createElement('div');
        bubble.className = `insight-bubble bg-black/40 border border-${section.color}-500/30 rounded-xl p-4 backdrop-blur-sm mb-2`;
        bubble.innerHTML = `
            <div class="flex items-start gap-3">
                <span class="material-symbols-outlined text-${section.color}-400 text-lg mt-0.5">${section.icon}</span>
                <div class="flex-1">
                    <div class="text-[10px] font-bold uppercase tracking-wider text-${section.color}-400 mb-1">${section.title}</div>
                    <div class="text-xs text-slate-300 leading-relaxed">${section.content.join('<br>')}</div>
                </div>
            </div>
        `;
        messageGroup.appendChild(bubble);
    }

    // Prepend at top
    scroller.insertBefore(messageGroup, scroller.firstChild);
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

// Grade tooltip text — explains what each grade means and that high grades ≠ guaranteed entry.
// Score is 0–100 weighted composite of HTF trend strength, LTF alignment, sweep, continuation, etc.
// A high grade means conditions are FAVORABLE but the bot only enters when the ICC sequence
// (Sweep → Continuation) also fires in real time. B+ during chop = no trade.
function _gradeTooltip(grade) {
    const base = {
        'A+': 'A+ (97–100) — Exceptional confluence. HTF+LTF aligned, sweep confirmed, continuation live. Very likely to trade.',
        'A': 'A  (93–96) — Strong setup. High HTF strength, good LTF alignment. Entry probable if price triggers.',
        'A-': 'A- (90–92) — Favorable setup. Good structure but may lack sweep/continuation. ⚠️ Watch, not yet a trade.',
        'B+': 'B+ (87–89) — Above-average signal. Conditions trending toward entry. Still waiting on ICC confirmation.',
        'B': 'B  (83–86) — Moderate conditions. Trend visible but not fully aligned. May trade, may not.',
        'B-': 'B- (80–82) — Marginal setup. Something is off — weak HTF or misaligned LTF. Likely no entry.',
        'C+': 'C+ (77–79) — Below-average. Choppy or ranging market. Bot will usually stand aside.',
        'C': 'C  (70–76) — Poor conditions. Mixed signals, no clear trend. No trade expected.',
        'D': 'D  (60–69) — Bad setup. Counter-trend or high chop. Bot will not trade.',
        'F': 'F  (<60)  — Worst conditions. No structural basis. Bot stands aside entirely.',
    }[grade];
    return base || `Grade ${grade} — Setup quality score. High grade = favorable, but entry requires ICC sweep + continuation to fire.`;
}

function addDecisionRow(symbol, action, scoreNum, reason, forcedGrade = null, strategyName = null, gatesData = null) {

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

    let detailsButton = "";
    if (gatesData) {
        // Inject the strategyName into gates data so the drawer knows what logic branch to use
        gatesData.strategyName = strategyName;
        // Inject reason so Meta-SCI tournaments can be parsed
        gatesData.decisionReason = reason;
        // Store gatesData stringified in a dataset attribute so the onclick handler can read it
        const encodedGates = encodeURIComponent(JSON.stringify(gatesData));
        detailsButton = ` <span class="ml-2 px-1.5 py-0.5 text-[10px] uppercase font-bold text-cyan-300 bg-cyan-500/10 border border-cyan-500/30 rounded cursor-pointer hover:bg-cyan-500/20 transition-colors" onclick="showDecisionDetails(this, '${symbol}', '${encodedGates}')">Details</span>`;
    }

    // Much larger font (text-lg / 18px), bunched rows (py-1.5)
    row.innerHTML = `
        <td class="px-4 py-1.5 text-slate-500 text-left font-mono text-sm">${time}</td>
        <td class="px-4 py-1.5 font-bold text-slate-200 text-left text-lg">${symbol}</td>
        <td class="px-4 py-1.5 ${scoreClass} text-left font-black text-lg cursor-help" title="${_gradeTooltip(grade)}">${grade}</td>
        <td class="px-4 py-1.5 text-center">${stratBadge || '<span class="text-slate-600 text-[10px]">—</span>'}</td>
        <td class="px-4 py-1.5 text-left text-sm uppercase tracking-wider">${actionHtml}</td>
        <td class="px-4 py-1.5 text-slate-400 text-sm italic text-left">${displayReason}${detailsButton}</td>
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

// Concept 1: The Sliding Screen Drawer (Glassmorphism + Theme-Aware)
window.showDecisionDetails = function(button, symbol, encodedGates) {
    let gatesData = {};
    try {
        gatesData = JSON.parse(decodeURIComponent(encodedGates));
    } catch(e) {}

    // Clean up any existing drawer
    const existing = document.getElementById('decision-drawer');
    if (existing) existing.remove();
    const existingOverlay = document.getElementById('decision-drawer-overlay');
    if (existingOverlay) existingOverlay.remove();
    const existingTooltip = document.getElementById('decision-drawer-tooltip');
    if (existingTooltip) existingTooltip.remove();

    // ─── Read current theme CSS variables ─────────────────────────
    const cs = getComputedStyle(document.documentElement);
    const tv = (name, fallback) => cs.getPropertyValue(name).trim() || fallback;
    const accent     = tv('--accent', '#14b8a6');
    const accentDim  = tv('--accent-dim', 'rgba(20,184,166,0.15)');
    const accentGlow = tv('--accent-glow', 'rgba(20,184,166,0.25)');
    const bgCard     = tv('--bg-card', 'rgba(15,23,42,0.4)');
    const cardBorder = tv('--card-border', 'rgba(255,255,255,0.06)');
    const textMain   = tv('--text-main', '#f1f5f9');
    const textSec    = tv('--text-secondary', '#94a3b8');
    const textMuted  = tv('--text-muted', '#64748b');
    const textDim    = tv('--text-dim', '#475569');
    const success    = tv('--success', '#10b981');
    const warning    = tv('--warning', '#f59e0b');
    const error      = tv('--error', '#ef4444');

    // Drawer Tooltip implementation to bypass any Electron tooltip issues
    const customTT = document.createElement('div');
    customTT.id = 'decision-drawer-tooltip';
    customTT.style.cssText = `position:fixed; z-index:10000; opacity:0; pointer-events:none; background:rgba(2,6,23,0.95); border:1px solid ${accentGlow}; border-radius:8px; padding:10px 14px; font-size:11.5px; line-height:1.5; color:${textSec}; font-family:Inter, sans-serif; box-shadow:0 10px 30px rgba(0,0,0,0.5); max-width:280px; transition:opacity 0.2s ease; backdrop-filter:blur(10px); -webkit-backdrop-filter:blur(10px); transform:translate(-50%, -100%); margin-top:-10px;`;
    document.body.appendChild(customTT);

    const bindTooltip = (html) => {
        return html.replace(/title="([^"]+)"/g, (match, text) => {
            return `data-drawer-tt="${text.replace(/"/g, '&quot;')}"`;
        });
    };

    // 1. Dark scrim overlay (only cover the left side so the drawer blurs the main UI)
    const overlay = document.createElement('div');
    overlay.id = 'decision-drawer-overlay';
    Object.assign(overlay.style, {
        position: 'fixed', left: '0', top: '0', bottom: '0',
        width: 'calc(100% - 460px)', // Exclude drawer width
        zIndex: '9998',
        background: 'rgba(0, 0, 0, 0.4)',
        opacity: '0',
        transition: 'opacity 0.3s ease',
    });
    document.body.appendChild(overlay);

    // 2. Glassmorphism Drawer — semi-transparent padding right side
    const drawer = document.createElement('div');
    drawer.id = 'decision-drawer';
    Object.assign(drawer.style, {
        position: 'fixed', top: '0', right: '0',
        width: '460px', height: '100vh',
        zIndex: '9999',
        background: `linear-gradient(180deg, ${bgCard} 0%, rgba(0,0,0,0.2) 100%)`, 
        backdropFilter: 'blur(40px) saturate(1.4)',
        WebkitBackdropFilter: 'blur(40px) saturate(1.4)',
        borderLeft: `1px solid ${cardBorder}`,
        boxShadow: `0 0 80px rgba(0,0,0,0.5), -20px 0 60px rgba(0,0,0,0.25), inset 0 0 0 1px rgba(255,255,255,0.03)`,
        display: 'flex', flexDirection: 'column',
        transform: 'translateX(100%)',
        transition: 'transform 0.35s cubic-bezier(0.16, 1, 0.3, 1)',
        fontFamily: 'inherit',
        overflow: 'hidden',
    });
    
    const htfStr = (gatesData.htf_strength !== undefined) ? Math.round(gatesData.htf_strength * 100) : 0;
    const phaseLabel = gatesData.phase ? gatesData.phase.toUpperCase() : 'UNKNOWN';
    const regimeLabel = gatesData.market_regime ? gatesData.market_regime.toUpperCase() : 'TRANSITIONAL';
    const scoreVal = gatesData.score !== undefined ? (gatesData.score > 1 ? gatesData.score.toFixed(1) : (gatesData.score * 100).toFixed(1)) : '?';
    const gradeVal = gatesData.grade || '?';
    const gradeColor = gradeVal.startsWith('A') ? success : gradeVal.startsWith('B') ? accent : gradeVal.startsWith('C') ? warning : error;

    const phaseDescriptions = {
        'TREND':        'The market is moving steadily in one direction — like a river flowing downstream. The bot is waiting for the right moment to hop in and ride the current.',
        'INDICATION':   'Early signs of a possible move are showing up, but it\'s not confirmed yet — like seeing dark clouds before rain. The bot is watching closely for a stronger signal.',
        'CORRECTION':   'The market temporarily pulled back against the main trend — like a rubber band stretching before snapping back. The bot is waiting to see if the original trend resumes.',
        'CONTINUATION': 'The market paused briefly and is now continuing its original move. The bot considers this a strong entry opportunity.',
        'CHOP':         'The market is bouncing up and down with no clear direction. The bot is staying on the sidelines until things settle down.',
        'UNKNOWN':      'The bot is still gathering data to determine what the market is doing.',
    };

    const regimeDescriptions = {
        'TRENDING':     'Prices are moving with conviction in a single direction.',
        'TRANSITIONAL': 'The market is shifting between states — direction unclear.',
        'CHOPPY':       'Prices are erratic with no reliable pattern to follow.',
        'RANGING':      'Prices are oscillating between predictable support and resistance.',
    };

    // ─── Core Strategy Diagnostics Dictionary ─────────────────────────
    const STRATEGY_PROFILES = {
        'REAPER': {
            checks: [
                { id: 'bollinger_squeeze', label: 'Bollinger Squeeze', desc: 'Checks if the market price is compressing like a spring ready to pop out of its bounds.' },
                { id: 'rsi_extreme', label: 'RSI Over-Extension', desc: 'Is the price stretched too far like a rubber band? We wait for extremes before assuming a reversal.' },
                { id: 'momentum', label: 'Momentum Confirmed', desc: 'Is there enough fuel behind the move to sustain a reversion back to the mean?' },
                { id: 'trend_independence', label: 'Trend Independence', desc: 'Reaper does not rely heavily on the big-picture trend. Is the market choppy and range-bound enough to bounce?' }
            ],
            indicators: ['B-BAND WIDTH', 'RSI', 'MACD'],
            explanationMode: 'reaper'
        },
        'MEAN_REVERSION': {
            checks: [
                { id: 'rsi_extreme', label: 'RSI Extremes', desc: 'Market is at an extreme point of overbought or oversold.' },
                { id: 'htf_trend', label: 'Trend Check', desc: 'Ensure we aren\'t stepping in front of a massive freight train.' }
            ],
            indicators: ['RSI', 'ADX', 'MACD'],
            explanationMode: 'reaper' // shares similar logic for now
        },
        'DEFAULT_TREND': {
            checks: [
                { id: 'htf_trend', label: 'Long-Term (HTF) Trend Base', desc: 'Is the "big picture" pointing clearly up or down? Think of it like checking if the tide is coming in or going out.' },
                { id: 'ltf_align', label: 'Short-Term (LTF) Alignment', desc: 'Is the short-term movement agreeing with the big-picture trend?' },
                { id: 'volatility', label: 'Volatility Threshold', desc: 'Is the market moving enough to be worth trading? If prices are barely budging, we stay out.' },
                { id: 'sweep', label: 'Liquidity Sweep', desc: 'Did prices briefly dip below a key level to "sweep" out weak traders before reversing?' },
                { id: 'continuation', label: 'Structural Continuation', desc: 'After a pause in the trend, is the market showing signs of continuing in the same direction?' }
            ],
            indicators: ['ADX', 'RSI', 'HTF STR'],
            explanationMode: 'trend'
        }
    };

    function evaluateStrategyCheck(id, gates) {
        switch(id) {
            case 'bollinger_squeeze': return { pass: gates.bollinger?.squeeze, val: gates.bollinger?.squeeze ? "Yes" : "No" };
            case 'rsi_extreme': return { pass: (gates.rsi && (gates.rsi > 60 || gates.rsi < 40)), val: gates.rsi ? gates.rsi.toFixed(1) : "—" };
            case 'momentum': return { pass: gates.indicator_strength && gates.indicator_strength > 0.4, val: gates.indicator_strength ? (gates.indicator_strength*100).toFixed(0)+"%" : "—" };
            case 'trend_independence': return { pass: gates.market_regime !== 'trending', val: gates.market_regime || "—" };
            case 'htf_trend': return { pass: gates.htf_dir && gates.htf_dir !== 'neutral', val: gates.htf_dir || '—' };
            case 'ltf_align': return { pass: gates.ltf_dir === gates.htf_dir && gates.ltf_dir && gates.ltf_dir !== 'neutral', val: gates.ltf_dir || '—' };
            case 'volatility': 
                const htf = Math.round((gates.htf_strength||0)*100); 
                const ltf = Math.round((gates.ltf_strength||0)*100);
                return { pass: htf > 15 || ltf > 15, val: htf + "%" };
            case 'sweep': return { pass: !!gates.sweep, val: gates.sweep ? "Yes" : "No" };
            case 'continuation': return { pass: !!gates.continuation, val: gates.continuation ? "Live" : "No" };
            default: return { pass: false, val: "—" };
        }
    }

    // Determine strategy profile
    const strategyName = gatesData.strategyName || 'Unknown';
    const decisionReason = gatesData.decisionReason || '';
    const fullContext = (strategyName + " " + decisionReason).toLowerCase();
    
    let activeProfileKey = 'DEFAULT_TREND';
    if (fullContext.includes('reaper')) activeProfileKey = 'REAPER';
    else if (fullContext.includes('range') || fullContext.includes('mean')) activeProfileKey = 'MEAN_REVERSION';
    // Fall back to DEFAULT_TREND for TrendRider, ForexConductor, RoboCop etc.

    const profile = STRATEGY_PROFILES[activeProfileKey];
    
    let structureChecks = profile.checks.map(chk => {
        const result = evaluateStrategyCheck(chk.id, gatesData);
        return { label: chk.label, pass: result.pass, val: result.val, desc: chk.desc };
    });

    let passedCount = structureChecks.filter(c => c.pass).length;
    let checksHtml = '';
    structureChecks.forEach(c => {
        const iconStr = c.pass
            ? `<span class="material-symbols-outlined" style="font-size:16px; color:${success};">check_circle</span>`
            : `<span class="material-symbols-outlined" style="font-size:16px; color:${textDim};">radio_button_unchecked</span>`;
        const labelColor = c.pass ? textMain : textDim;
        const labelDecoration = c.pass ? 'none' : 'line-through';
        const valColor = c.pass ? accent : textDim;
        checksHtml += `
            <div data-drawer-tt="${c.desc}" style="display:flex; align-items:center; justify-content:space-between; padding:10px 0; border-bottom:1px solid ${cardBorder}; cursor:help;">
                <div style="display:flex; align-items:center; gap:10px;">
                    ${iconStr}
                    <span style="font-size:13px; font-weight:500; color:${labelColor}; text-decoration:${labelDecoration}; text-decoration-color:${textDim};">${c.label}</span>
                </div>
                <span style="font-family:monospace; font-size:11px; text-transform:uppercase; padding:2px 8px; border-radius:4px; background:rgba(0,0,0,0.25); border:1px solid ${cardBorder}; color:${valColor};">${c.val}</span>
            </div>
        `;
    });

    const gradeTooltip = 'The bot\'s overall confidence grade for entering a trade right now.';
    const scoreTooltip = 'This is the bot\'s overall confidence number (0–100). Think of it like a test score — the higher the number, the more confident the bot is.';
    
    // Indicators Map
    const adxVal = gatesData.htf_adx || gatesData.adx || null;
    const rsiVal = gatesData.rsi || null;
    let indicatorsHtml = '';
    let indicatorExplanation = '';

    if (profile.explanationMode === 'reaper') {
        const bw = gatesData.bollinger ? (gatesData.bollinger.bandwidth * 100).toFixed(1) : '--';
        indicatorsHtml = `
            ${_buildMiniStat('B-BAND WIDTH', bw + '%', gatesData.bollinger?.squeeze ? warning : textSec, 'Bollinger Bands relative width. Indicates volatility compression.', bgCard, cardBorder, textDim)}
            ${_buildMiniStat('RSI', rsiVal ? rsiVal.toFixed(1) : '--', (rsiVal > 70 || rsiVal < 30) ? warning : textSec, 'Relative Strength Index. Tells us if prices are overbought or oversold.', bgCard, cardBorder, textDim)}
            ${_buildMiniStat('MACD', gatesData.macd ? gatesData.macd.histogram.toFixed(4) : '--', gatesData.macd?.histogram > 0 ? success : error, 'MACD Histogram. Shows short term momentum acceleration.', bgCard, cardBorder, textDim)}
        `;
        const rsiZone = rsiVal > 65 ? "an overbought zone" : rsiVal < 35 ? "an oversold zone" : "a neutral zone";
        indicatorExplanation = `The market is currently in ${rsiZone} with an RSI of ${rsiVal?.toFixed(1)}. Bollinger Bandwidth is at ${bw}%${gatesData.bollinger?.squeeze ? " (Squeeze Active)" : ""}. The bot is actively looking for a structural mean-reversion opportunity.`;
    } else {
        indicatorsHtml = `
            ${_buildMiniStat('ADX', adxVal ? adxVal.toFixed(1) : '--', adxVal > 25 ? success : warning, 'Average Directional Index — measures how strong the current trend is. Think of it like a speedometer for the trend.', bgCard, cardBorder, textDim)}
            ${_buildMiniStat('RSI', rsiVal ? rsiVal.toFixed(1) : '--', (rsiVal > 70 || rsiVal < 30) ? warning : textSec, 'Relative Strength Index — tells us if prices have moved too far, too fast.', bgCard, cardBorder, textDim)}
            ${_buildMiniStat('HTF STR', htfStr + '%', htfStr > 50 ? success : textDim, 'Higher Timeframe Strength — how decisively the big-picture trend is moving.', bgCard, cardBorder, textDim)}
        `;
        let adxExplain = adxVal !== null ? (adxVal > 25 ? `ADX is ${adxVal.toFixed(1)} (strong trend).` : `ADX is ${adxVal.toFixed(1)} (weak trend).`) : '';
        let strExplain = htfStr > 50 ? "Long-term strength is pushing hard." : "Long-term strength is flat.";
        indicatorExplanation = `${adxExplain} ${strExplain} The bot prefers to ride strong momentum waves and avoids flat chop.`;
    }

    const phaseTooltip = phaseDescriptions[phaseLabel] || phaseDescriptions['UNKNOWN'];
    const regimeTooltip = regimeDescriptions[regimeLabel] || 'Current volatility classification of the market.';

    let rawHtml = `
        <!-- Header -->
        <div style="padding:24px 28px; border-bottom:1px solid ${cardBorder}; display:flex; align-items:center; justify-content:space-between; background:linear-gradient(90deg, transparent 0%, ${accentDim} 100%); flex-shrink:0;">
            <div style="display:flex; align-items:center; gap:14px;">
                <div style="width:42px; height:42px; border-radius:12px; background:${accentDim}; border:1px solid ${accentGlow}; display:flex; align-items:center; justify-content:center;">
                    <span class="material-symbols-outlined" style="font-size:22px; color:${accent};">analytics</span>
                </div>
                <div>
                    <h2 style="margin:0; font-size:20px; font-weight:900; color:${textMain}; letter-spacing:-0.01em;">${symbol} Analysis</h2>
                    <span style="font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:0.15em; color:${textMuted};">Decision Diagnostic</span>
                </div>
            </div>
            <button id="close-drawer-btn" data-drawer-tt="Close this panel" style="width:36px; height:36px; border-radius:50%; background:rgba(255,255,255,0.05); border:1px solid ${cardBorder}; color:${textMuted}; cursor:pointer; display:flex; align-items:center; justify-content:center; transition:all 0.2s;">
                <span class="material-symbols-outlined" style="font-size:18px;">close</span>
            </button>
        </div>

        <!-- Scrollable Content -->
        <div style="flex:1; overflow-y:auto; padding:28px; display:flex; flex-direction:column; gap:28px;" class="scrollbar-thin">
            
            <!-- Market Phase Section -->
            <div>
                <div style="font-size:10px; font-weight:800; text-transform:uppercase; letter-spacing:0.2em; color:${textMuted}; margin-bottom:12px; display:flex; align-items:center; gap:8px;">
                    <span class="material-symbols-outlined" style="font-size:14px; color:${accent};">timeline</span>
                    Market Phase
                </div>
                <div style="background:${bgCard}; border:1px solid ${cardBorder}; border-radius:12px; padding:20px; backdrop-filter:blur(12px);" data-drawer-tt="${phaseTooltip}">
                    <div style="display:flex; align-items:baseline; gap:12px; margin-bottom:10px; cursor:help;">
                        <span style="font-size:24px; font-weight:900; color:${accent}; text-transform:capitalize;">${phaseLabel}</span>
                        <span data-drawer-tt="${regimeTooltip}" style="font-size:12px; font-weight:700; font-family:monospace; color:${regimeLabel === 'TRENDING' ? success : regimeLabel === 'CHOPPY' ? error : warning}; padding:2px 8px; border-radius:6px; background:rgba(0,0,0,0.3); border:1px solid ${cardBorder}; cursor:help;">${regimeLabel}</span>
                    </div>
                    <p style="font-size:12px; color:${textSec}; line-height:1.7; margin:0;">
                        ${phaseTooltip}
                    </p>
                </div>
            </div>

            <!-- Structure Conditions -->
            <div>
                <div style="font-size:10px; font-weight:800; text-transform:uppercase; letter-spacing:0.2em; color:${textMuted}; margin-bottom:12px; display:flex; align-items:center; justify-content:space-between;">
                    <span style="display:flex; align-items:center; gap:8px;" data-drawer-tt="These are the conditions the bot checks before entering a trade. Think of them as a safety checklist.">
                        <span class="material-symbols-outlined" style="font-size:14px; color:${accent};">checklist</span>
                        Entry Requirements
                    </span>
                    <span data-drawer-tt="Count of requirements met vs needed." style="font-size:11px; font-weight:800; color:${passedCount >= 4 ? success : passedCount >= 2 ? warning : error}; cursor:help;">${passedCount}/${structureChecks.length} MET</span>
                </div>
                <div style="background:${bgCard}; border-radius:12px; padding:4px 16px; border:1px solid ${cardBorder}; backdrop-filter:blur(8px);">
                    ${checksHtml}
                </div>
            </div>

            <!-- Score/Grade Cards -->
            <div>
                <div style="font-size:10px; font-weight:800; text-transform:uppercase; letter-spacing:0.2em; color:${textMuted}; margin-bottom:12px; display:flex; align-items:center; gap:8px;">
                    <span class="material-symbols-outlined" style="font-size:14px; color:${accent};">speed</span>
                    Real-Time Grading
                </div>
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px;">
                    <div data-drawer-tt="${scoreTooltip}" style="background:${bgCard}; border-radius:12px; padding:16px 20px; border:1px solid ${cardBorder}; cursor:help; backdrop-filter:blur(8px);">
                        <div style="font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:0.15em; color:${textMuted}; margin-bottom:6px;">Composite Score</div>
                        <div style="font-size:28px; font-weight:900; font-family:monospace; color:${accent};">${scoreVal}<span style="font-size:14px; color:${textDim};">/100</span></div>
                    </div>
                    <div data-drawer-tt="${gradeTooltip}" style="background:${bgCard}; border-radius:12px; padding:16px 20px; border:1px solid ${cardBorder}; cursor:help; backdrop-filter:blur(8px);">
                        <div style="font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:0.15em; color:${textMuted}; margin-bottom:6px;">Final Grade</div>
                        <div style="font-size:28px; font-weight:900; color:${gradeColor};">${gradeVal}</div>
                    </div>
                </div>
            </div>

            <!-- Indicator Snapshot -->
            <div>
                <div style="font-size:10px; font-weight:800; text-transform:uppercase; letter-spacing:0.2em; color:${textMuted}; margin-bottom:12px; display:flex; align-items:center; gap:8px;">
                    <span class="material-symbols-outlined" style="font-size:14px; color:${accent};">monitoring</span>
                    Indicator Snapshot
                </div>
                <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:8px;">
                    ${indicatorsHtml}
                </div>
                <div style="margin-top:14px; padding:14px 16px; background:${bgCard}; border:1px solid ${cardBorder}; border-radius:10px; backdrop-filter:blur(8px);">
                    <div style="display:flex; align-items:start; gap:10px;">
                        <span class="material-symbols-outlined" style="font-size:16px; color:${accent}; margin-top:1px; flex-shrink:0;">auto_awesome</span>
                        <p style="font-size:12px; color:${textSec}; line-height:1.7; margin:0;">${indicatorExplanation}</p>
                    </div>
                </div>
            </div>

        </div>

        <!-- Footer -->
        <div style="padding:16px 28px; border-top:1px solid ${cardBorder}; display:flex; justify-content:space-between; align-items:center; flex-shrink:0; background:rgba(0,0,0,0.15); backdrop-filter:blur(8px);">
            <span style="font-size:10px; color:${textDim}; font-weight:600; text-transform:uppercase; letter-spacing:0.1em;">Live Engine Diagnostic</span>
            <span style="font-size:10px; color:${textDim}; font-family:monospace;">Updated ${new Date().toLocaleTimeString('en-US', {hour:'numeric', minute:'2-digit', hour12:true})}</span>
        </div>
    `;

    drawer.innerHTML = bindTooltip(rawHtml);
    document.body.appendChild(drawer);

    // Tooltip event bindings
    const triggerElements = drawer.querySelectorAll('[data-drawer-tt]');
    triggerElements.forEach(el => {
        el.addEventListener('mouseenter', (ev) => {
            const tipText = el.getAttribute('data-drawer-tt');
            if(!tipText) return;
            customTT.innerHTML = tipText;
            customTT.style.opacity = '1';
            const br = el.getBoundingClientRect();
            // Position above the element
            customTT.style.left = (br.left + br.width / 2) + 'px';
            customTT.style.top = (br.top - 5) + 'px';
        });
        el.addEventListener('mouseleave', () => { customTT.style.opacity = '0'; });
    });

    // Hover effect on close button
    const closeBtn = document.getElementById('close-drawer-btn');
    closeBtn.addEventListener('mouseenter', () => { closeBtn.style.background = 'rgba(239,68,68,0.15)'; closeBtn.style.borderColor = 'rgba(239,68,68,0.3)'; closeBtn.style.color = '#f87171'; });
    closeBtn.addEventListener('mouseleave', () => { closeBtn.style.background = 'rgba(255,255,255,0.05)'; closeBtn.style.borderColor = cardBorder; closeBtn.style.color = textMuted; });

    // Trigger open animations
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            overlay.style.opacity = '1';
            drawer.style.transform = 'translateX(0)';
        });
    });

    const closeDrawer = () => {
        overlay.style.opacity = '0';
        drawer.style.transform = 'translateX(100%)';
        customTT.style.opacity = '0';
        setTimeout(() => {
            if (drawer.parentElement) drawer.remove();
            if (overlay.parentElement) overlay.remove();
            if (customTT.parentElement) customTT.remove();
        }, 350);
    };

    closeBtn.addEventListener('click', closeDrawer);
    overlay.addEventListener('click', closeDrawer);

    const escHandler = (e) => { if (e.key === 'Escape') { closeDrawer(); document.removeEventListener('keydown', escHandler); } };
    document.addEventListener('keydown', escHandler);
}

// Helper for indicator mini-stat cards inside the drawer
function _buildMiniStat(label, value, color, tooltip, bgCard, cardBorder, textDim) {
    const displayVal = (value !== null && value !== undefined) ? (typeof value === 'number' ? value.toFixed(1) : value) : '—';
    const bg = bgCard || 'rgba(0,0,0,0.3)';
    const border = cardBorder || 'rgba(255,255,255,0.04)';
    const dimColor = textDim || '#475569';
    const tt = tooltip ? ` title="${tooltip}"` : '';
    return `<div${tt} style="background:${bg}; border-radius:8px; padding:12px; border:1px solid ${border}; text-align:center; cursor:help; backdrop-filter:blur(8px);">
        <div style="font-size:9px; font-weight:700; text-transform:uppercase; letter-spacing:0.15em; color:${dimColor}; margin-bottom:4px;">${label}</div>
        <div style="font-size:16px; font-weight:800; font-family:monospace; color:${color};">${displayVal}</div>
    </div>`;
}

// --- IPC / Socket Logic ---
let capitalDisplayMode = 'equity';
window.api?.on('env-updated', (updates) => {
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

window.api?.on('fromMain', (payload) => {
    if (payload.type === 'log-clear') {
        // Clear the sys-log panel on GUI boot — start fresh
        const term = document.getElementById('log-terminal') || document.querySelector('.log-terminal');
        if (term) term.innerHTML = '';
    } else if (payload.type === 'log-chunk') {
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
        if (payload.detail) {
            // Fallback guard: if the backend sent raw JSON (due to no hard restart), parse it here
            const parsedDetails = payload.detail.split('\n').map(line => {
                let l = line.trim();
                if (l.startsWith('{')) {
                    try {
                        const obj = JSON.parse(l);
                        if (obj.message) return obj.level ? `[${obj.level}] ${obj.message}` : obj.message;
                    } catch(e) {}
                }
                return l;
            }).join('<br>');
            msg += `:<br><span class="text-slate-400 mt-1 block">${parsedDetails}</span>`;
        } else {
            // If it's just a message like "Bot Started Successfully", no detail to append
        }
        appendLog(level, msg);
    } else if (payload.type === 'navigate') {
        // Programmatic navigation from main process (e.g. "Open Broker Settings" popup)
        if (payload.target === 'settings') {
            const navSettings = document.getElementById('nav-settings');
            if (navSettings) navSettings.click();
            // Switch to specific settings tab if requested
            if (payload.tab && window.settingsModule && window.settingsModule.switchTab) {
                setTimeout(() => window.settingsModule.switchTab(payload.tab), 300);
            }
        }
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

    // Helper: format seconds into human-readable age
    function formatAge(secs) {
        if (secs == null || isNaN(secs) || secs < 0) return '—';
        const s = Math.round(secs);
        if (s < 60) return s + 's';
        const m = Math.floor(s / 60);
        if (m < 60) return m + 'm';
        const h = Math.floor(m / 60);
        const rm = m % 60;
        return rm > 0 ? h + 'h ' + rm + 'm' : h + 'h';
    }

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
        const displayStrategy = pos.strategy ? pos.strategy.toUpperCase().replace(/_/g, ' ') : '—';
        const displayAge = formatAge(pos.age_seconds);

        // Color age: green < 15m, yellow < 1h, red > 1h
        let ageClass = 'text-green-400';
        if (pos.age_seconds > 3600) ageClass = 'text-red-400';
        else if (pos.age_seconds > 900) ageClass = 'text-yellow-400';

        // Unique button ID for this symbol
        const btnId = `cashout-${pos.symbol.replace(/[^a-zA-Z0-9]/g, '')}`;

        row.innerHTML = `
            <td class="p-2 font-mono font-bold text-slate-200">${pos.symbol}</td>
            <td class="p-2 text-center ${sideClass} font-bold text-xs">${pos.side ? pos.side.toUpperCase() : 'LONG'}</td>
            <td class="p-2 text-center text-[10px] font-semibold"><span class="px-2 py-0.5 rounded bg-teal-900/40 text-teal-300 tracking-wider">${displayStrategy}</span></td>
            <td class="p-2 text-center font-mono text-xs font-bold ${ageClass}">${displayAge}</td>
            <td class="p-2 text-right font-mono text-slate-400">${displaySize}</td>
            <td class="p-2 text-right font-mono font-bold ${pnlClass}">${pnlSign}$${displayPnl}</td>
            <td class="p-2 text-center">
                <button id="${btnId}" data-symbol="${pos.symbol}"
                    class="cashout-btn px-3 py-1.5 rounded-lg text-[9px] font-black uppercase tracking-wider cursor-pointer transition-all duration-200 border select-none"
                    style="background: linear-gradient(135deg, rgba(249,115,22,0.12), rgba(239,68,68,0.12));
                           border-color: rgba(249,115,22,0.3);
                           color: #fb923c;
                           backdrop-filter: blur(8px);
                           box-shadow: 0 0 10px rgba(249,115,22,0.08);"
                    onmouseenter="this.style.background='linear-gradient(135deg, rgba(249,115,22,0.25), rgba(239,68,68,0.25))'; this.style.boxShadow='0 0 18px rgba(249,115,22,0.2)'; this.style.borderColor='rgba(249,115,22,0.5)'"
                    onmouseleave="if(!this._confirmed){this.style.background='linear-gradient(135deg, rgba(249,115,22,0.12), rgba(239,68,68,0.12))'; this.style.boxShadow='0 0 10px rgba(249,115,22,0.08)'; this.style.borderColor='rgba(249,115,22,0.3)'}"
                    title="Manually close this position">
                    <span class="flex items-center gap-1 justify-center">
                        <span class="material-symbols-outlined" style="font-size:12px;">payments</span>
                        Cash Out
                    </span>
                </button>
            </td>
        `;
        tbody.appendChild(row);

        // Two-step confirm flow
        const btn = row.querySelector(`#${btnId}`);
        if (btn) {
            // If a flatten is already pending for this symbol, show "Closing..." immediately
            if (window._pendingFlattens && window._pendingFlattens.has(pos.symbol)) {
                btn._sending = true;
                btn._confirmed = true;
                btn.innerHTML = '<span class="flex items-center gap-1 justify-center"><span class="material-symbols-outlined" style="font-size:12px;">sync</span>Closing...</span>';
                btn.style.background = 'linear-gradient(135deg, rgba(20,184,166,0.2), rgba(16,185,129,0.2))';
                btn.style.borderColor = 'rgba(20,184,166,0.4)';
                btn.style.color = '#2dd4bf';
                btn.style.boxShadow = '0 0 20px rgba(20,184,166,0.2)';
                btn.style.animation = '';
                btn.style.pointerEvents = 'none';
            }
            let confirmTimer = null;
            btn.addEventListener('click', () => {
                if (btn._sending) return;

                if (!btn._confirmed) {
                    // Step 1: Confirm
                    btn._confirmed = true;
                    btn.innerHTML = '<span class="flex items-center gap-1 justify-center"><span class="material-symbols-outlined" style="font-size:12px;">warning</span>Confirm?</span>';
                    btn.style.background = 'linear-gradient(135deg, rgba(245,158,11,0.3), rgba(249,115,22,0.3))';
                    btn.style.borderColor = 'rgba(245,158,11,0.6)';
                    btn.style.color = '#fbbf24';
                    btn.style.boxShadow = '0 0 20px rgba(245,158,11,0.25)';
                    btn.style.animation = 'pulse 1.5s ease-in-out infinite';

                    confirmTimer = setTimeout(() => {
                        btn._confirmed = false;
                        btn.innerHTML = '<span class="flex items-center gap-1 justify-center"><span class="material-symbols-outlined" style="font-size:12px;">payments</span>Cash Out</span>';
                        btn.style.background = 'linear-gradient(135deg, rgba(249,115,22,0.12), rgba(239,68,68,0.12))';
                        btn.style.borderColor = 'rgba(249,115,22,0.3)';
                        btn.style.color = '#fb923c';
                        btn.style.boxShadow = '0 0 10px rgba(249,115,22,0.08)';
                        btn.style.animation = '';
                    }, 3000);
                    return;
                }

                // Step 2: Execute
                clearTimeout(confirmTimer);
                const sym = btn.dataset.symbol;
                const sent = (typeof sendFlattenSymbol === 'function') ? sendFlattenSymbol(sym)
                           : (window.sendFlattenSymbol ? window.sendFlattenSymbol(sym) : false);
                if (sent) {
                    if (typeof appendLog === 'function') {
                        appendLog('INFO', `[USER] ⚡ Manual Cash-Out triggered for ${sym}`);
                    }
                    // sendFlattenSymbol already handled _pendingFlattens + cross-panel sync
                } else {
                    // Truly no WS — show user-friendly message
                    btn._sending = true;
                    btn.innerHTML = '<span class="flex items-center gap-1 justify-center"><span class="material-symbols-outlined" style="font-size:12px;">wifi_off</span>Disconnected</span>';
                    btn.style.background = 'linear-gradient(135deg, rgba(239,68,68,0.2), rgba(248,113,113,0.2))';
                    btn.style.borderColor = 'rgba(239,68,68,0.5)';
                    btn.style.color = '#f87171';
                    btn.style.boxShadow = '0 0 20px rgba(239,68,68,0.2)';
                    btn.style.animation = '';
                    // Auto-reset after 4s
                    setTimeout(() => {
                        btn._confirmed = false;
                        btn._sending = false;
                        btn.style.pointerEvents = '';
                    }, 4000);
                }
            });
        }
    });

    // Handle empty state
    if (payload.positions.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="p-4 text-center text-slate-500 italic text-xs">No active positions</td></tr>`;
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


// parseLogLine — delegated to log_parser.js
const parseLogLine = (...a) => window.LogParser.parseLogLine(...a);

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
        // Set max date to today so users can't pick future dates
        const today = new Date().toISOString().split('T')[0];
        input.setAttribute('max', today);

        btn.addEventListener('click', () => {
            try { input.showPicker(); } catch (e) { input.click(); }
        });
        input.addEventListener('change', (e) => {
            const dateStr = e.target.value; // YYYY-MM-DD
            if (!dateStr) return;

            // Convert to epoch seconds (start of the selected day in UTC)
            const sinceEpoch = Math.floor(new Date(dateStr + 'T00:00:00Z').getTime() / 1000);
            appendLog("INFO", `[UI] Calendar: navigating chart to ${dateStr}`, "GUI");

            // Clear current chart and request historical data from selected date
            if (candleSeries) candleSeries.setData([]);
            if (indicatorSeries) indicatorSeries.setData([]);
            candleData = [];
            clearTradeMarkers();
            clearPositionLines();

            const sym = (document.getElementById('chart-symbol-label')?.innerText || '').trim();
            const tf = (document.getElementById('chart-tf-label')?.innerText || '15m').trim();
            if (sym) subscribeToAsset(sym, tf, sinceEpoch);
        });
    }
}



let botIsRunning = false;

window.api?.on('bot-status', (payload) => {
    botIsRunning = payload.running;
    console.log("Bot Status Update:", botIsRunning);
    updatePanicButtonState();
});

function updatePanicButtonState() {
    // Two states only: bot running → Panic, bot not running → Start
    if (botIsRunning) {
        setPanicState(false); // Show panic button
    } else {
        setPanicState(true);  // Show start button
    }
}

function setPanicState(isStopped) {
    const btn = document.getElementById('btn-panic');
    const text = document.getElementById('panic-text');
    if (!btn || !text) return;

    if (isStopped) {
        // Bot is NOT running → green "Start Bot"
        btn.classList.remove('panic-stripes', 'bg-red-500', 'border-red-500/40');
        btn.classList.add('bg-emerald-500', 'border-emerald-500/40');
        text.innerText = "Start Bot";
    } else {
        // Bot IS running → red panic button
        btn.classList.add('panic-stripes', 'bg-red-500', 'border-red-500/40');
        btn.classList.remove('bg-emerald-500', 'border-emerald-500/40');
        text.innerText = "PANIC BUTTON -\nHALT ALL TRADING";
        text.className = "text-[12px] font-black uppercase tracking-wider relative z-10 whitespace-pre-line leading-tight drop-shadow-[0_2px_2px_rgba(0,0,0,0.8)] text-center";
    }
}

// --- Interactive Elements ---
const WATCHED_SYMBOLS = ['BTCUSD', 'ETHUSD', 'SOLUSD']; // Default to crypto, will be updated from backend
let currentSymbolIndex = 0;

let updateSymbolDisplay = () => { }; // Forward declaration for use in WS sync

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
        startMarketClosedTimer();
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

    document.getElementById('btn-panic')?.addEventListener('click', async (e) => {
        if (!botIsRunning) {
            executeStartBot();
            return;
        }

        // PANIC: Kill the bot PID directly — no WebSocket signals that get ignored
        window.api.send('stop-bot');
        appendLog("CRITICAL", "[USER] PANIC BUTTON ACTIVATED. KILLING BOT PROCESS.");
        setPanicState(true);  // Show "Start Bot" (bot is now stopped)
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

    ['nav-dashboard', 'nav-profile', 'nav-settings', 'nav-graph', 'nav-backtest', 'nav-help'].forEach(id => {
        document.getElementById(id)?.addEventListener('click', (e) => {
            // Remove active style from all
            ['nav-dashboard', 'nav-profile', 'nav-settings', 'nav-graph', 'nav-backtest', 'nav-help'].forEach(navId => {
                const btn = document.getElementById(navId);
                if (btn) {
                    btn.className = "flex items-center gap-4 px-4 py-3.5 rounded-xl hover:bg-white/5 text-slate-400 hover:text-white transition-all text-sm font-medium";
                }
            });
            // Add to active
            e.currentTarget.className = "flex items-center gap-4 px-4 py-3.5 rounded-xl bg-teal-500/20 text-teal-300 font-bold text-sm border-2 border-teal-500/30 shadow-[0_0_20px_rgba(20,184,166,0.3)] transition-all";

            const name = e.currentTarget.innerText.trim();
            try { appendLog("INFO", `[UI] Switched to ${name} view.`); } catch (_) { }

            // Handle view switching
            const dashboardView = document.getElementById('view-dashboard');
            const analyticsView = document.getElementById('view-analytics');
            const profilesView = document.getElementById('view-profiles');
            const settingsView = document.getElementById('view-settings');
            const helpView = document.getElementById('view-help');
            const backtestView = document.getElementById('view-backtest');

            // Hide all views first
            if (dashboardView) dashboardView.classList.add('hidden');
            if (analyticsView) analyticsView.classList.add('hidden');
            if (profilesView) profilesView.classList.add('hidden');
            if (settingsView) settingsView.classList.add('hidden');
            if (helpView) helpView.classList.add('hidden');
            if (backtestView) backtestView.classList.add('hidden');

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
            } else if (id === 'nav-backtest') {
                // Show Backtest view
                if (backtestView) {
                    backtestView.classList.remove('hidden');
                    if (window.backtestModule && window.backtestModule.init) {
                        window.backtestModule.init();
                    }
                }
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
            hideMarketClosedOverlay();
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
let _saveStateTimeout = null;
function saveState() {
    if (_saveStateTimeout) clearTimeout(_saveStateTimeout);
    _saveStateTimeout = setTimeout(() => {
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
    }, 500);
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
            setPanicState(true);  // Bot was halted → show "Start Bot"
        }
    } catch (e) { console.error("Load State Error:", e); }
}

async function executeStartBot() {
    // Force save any pending profile/setting changes before starting the daemon!
    if (typeof saveAll === 'function' && typeof localChanges !== 'undefined' && Object.keys(localChanges).length > 0) {
        if (typeof autoSaveTimeout !== 'undefined') clearTimeout(autoSaveTimeout);
        console.log("[DASHBOARD] Flushing pending settings to disk before starting bot...");
        await saveAll();
    }

    window.api.startBot();
    appendLog("INFO", "[USER] START BOT SIGNAL SENT TO SYSTEM.");

    const btn = document.getElementById('btn-panic');
    const text = document.getElementById('panic-text');
    if (btn && text) {
        text.innerText = "Starting...";
    }
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

    // Restore AI Insights from localStorage (24h persistence)
    restoreAIInsights();

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

        // Request initial bot status (Electron-only)
        try { window.api?.send('get-bot-status'); } catch (_) { }

        // Initialize PnL Timeframe from env (Electron-only)
        try {
            window.api?.invoke('read-env')?.then(env => {
                if (env?.GUI_PNL_TIMEFRAME) {
                    pnlTimeframe = env.GUI_PNL_TIMEFRAME;
                    localStorage.setItem('pnlTimeframe', pnlTimeframe);
                }
                if (window.updateRealizedPnL) window.updateRealizedPnL();
            });
        } catch (_) { }

        // Fetch and display app version from VERSION file (Electron-only)
        try {
            window.api?.invoke('get-app-version')?.then(ver => {
                const badge = document.getElementById('version-badge');
                if (badge && ver) badge.textContent = `β ${ver}`;
            }).catch(() => { });
        } catch (_) { }

        // Chart Refresh Interval (15 Seconds)
        setInterval(() => {
            const sym = document.getElementById('chart-symbol-label')?.innerText || 'EURUSD';
            const tf = document.getElementById('chart-tf-label')?.innerText || '15m';
            // scrollToRealTime removed — it was causing a gap after the last candle
        }, 15000);

        console.log("Other UI modules initialized.");
    } catch (e) {
        console.error("UI setup failed:", e);
        // Ensure nav still works even if other setup fails
        try { setupInteractiveElements(); } catch (_) { }
    }
}

// Start the app when ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}

// profilesModule — extracted to profiles_module.js

// helpModule — extracted to help_module.js


// ═══════════════════════════════════════════════════════════════════════════
// PANEL RESIZE (Independent — each panel resizes without affecting others)
// ═══════════════════════════════════════════════════════════════════════════
(function initPanelResize() {
    const STORAGE_KEY = 'tradebot_panel_heights';
    const ALL_PANELS = ['chart-panel', 'decisions-panel', 'log-panel'];
    const MIN_HEIGHTS = {
        'chart-panel': 200,
        'decisions-panel': 120,
        'log-panel': 80,
    };

    // Lock ALL panels to explicit pixel heights so flex can't redistribute
    function lockAllPanels() {
        ALL_PANELS.forEach(id => {
            const el = document.getElementById(id);
            if (el && el.style.flex !== 'none') {
                const h = el.getBoundingClientRect().height;
                el.style.flex = 'none';
                el.style.height = Math.round(h) + 'px';
            }
        });
    }

    function setup() {
        const handles = document.querySelectorAll('.panel-resize-handle');
        if (!handles.length) return;

        // Restore saved heights
        restoreHeights();

        let activeHandle = null;
        let abovePanel = null;
        let belowPanel = null;
        let startY = 0;
        let aboveStartH = 0;
        let belowStartH = 0;

        handles.forEach(handle => {
            handle.addEventListener('mousedown', (e) => {
                e.preventDefault();
                const aboveId = handle.dataset.above;
                const belowId = handle.dataset.below;
                abovePanel = document.getElementById(aboveId);
                belowPanel = document.getElementById(belowId);
                if (!abovePanel) return;

                // Lock all panels to current pixel heights first
                lockAllPanels();

                activeHandle = handle;
                startY = e.clientY;
                aboveStartH = abovePanel.getBoundingClientRect().height;
                belowStartH = belowPanel ? belowPanel.getBoundingClientRect().height : 0;

                document.body.style.cursor = 'row-resize';
                document.body.style.userSelect = 'none';

                // Glow active handle
                const grip = handle.querySelector('div');
                if (grip) {
                    grip.style.background = 'rgba(20,184,166,0.7)';
                    grip.style.boxShadow = '0 0 12px rgba(20,184,166,0.4)';
                }
            });
        });

        document.addEventListener('mousemove', (e) => {
            if (!activeHandle) return;
            const delta = e.clientY - startY;

            // Resize above panel (grows/shrinks with drag)
            const aboveMin = MIN_HEIGHTS[abovePanel.id] || 100;
            let newAboveH = Math.max(aboveStartH + delta, aboveMin);

            // If there's a below panel, resize inversely
            if (belowPanel) {
                const belowMin = MIN_HEIGHTS[belowPanel.id] || 80;
                let newBelowH = belowStartH - delta;
                if (newBelowH < belowMin) {
                    newBelowH = belowMin;
                    newAboveH = aboveStartH + belowStartH - belowMin;
                }
                belowPanel.style.height = Math.round(newBelowH) + 'px';
            }

            abovePanel.style.height = Math.round(newAboveH) + 'px';

            // Trigger chart resize if chart panel was involved
            if (abovePanel.id === 'chart-panel' || (belowPanel && belowPanel.id === 'chart-panel')) {
                if (chart) {
                    const container = document.getElementById('chart-area');
                    if (container) {
                        chart.applyOptions({ width: container.clientWidth, height: container.clientHeight });
                    }
                }
            }
        });

        document.addEventListener('mouseup', () => {
            if (!activeHandle) return;

            // Reset handle glow
            const grip = activeHandle.querySelector('div');
            if (grip) {
                grip.style.background = 'rgba(20,184,166,0.3)';
                grip.style.boxShadow = 'none';
            }

            document.body.style.cursor = '';
            document.body.style.userSelect = '';

            // Save all panel heights
            saveHeights();

            // Final chart resize
            setTimeout(() => {
                if (chart) {
                    const container = document.getElementById('chart-area');
                    if (container) chart.applyOptions({ width: container.clientWidth, height: container.clientHeight });
                }
            }, 50);

            activeHandle = null;
            abovePanel = null;
            belowPanel = null;
        });
    }

    function saveHeights() {
        const heights = {};
        ALL_PANELS.forEach(id => {
            const el = document.getElementById(id);
            if (el) heights[id] = Math.round(el.getBoundingClientRect().height);
        });
        localStorage.setItem(STORAGE_KEY, JSON.stringify(heights));
    }

    function restoreHeights() {
        try {
            const saved = localStorage.getItem(STORAGE_KEY);
            if (!saved) return;
            const heights = JSON.parse(saved);
            Object.entries(heights).forEach(([id, h]) => {
                const el = document.getElementById(id);
                if (el && h > 0) {
                    el.style.flex = 'none';
                    el.style.height = h + 'px';
                }
            });
        } catch (_) { /* ignore */ }
    }

    // Global reset function — clears saved heights so original CSS flex classes take over
    window.resetPanelLayout = function () {
        localStorage.removeItem(STORAGE_KEY);
        ALL_PANELS.forEach(id => {
            const el = document.getElementById(id);
            if (!el) return;
            // Clear inline overrides — original Tailwind classes (flex-[3], flex-[1.5], flex-1) take over
            el.style.flex = '';
            el.style.height = '';
        });
        // Resize chart after layout settles
        setTimeout(() => {
            if (chart) {
                const container = document.getElementById('chart-area');
                if (container) chart.applyOptions({ width: container.clientWidth, height: container.clientHeight });
            }
        }, 100);
        console.log('[UI] Panel layout reset to defaults');
    };

    // Initialize after DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', setup);
    } else {
        setup();
    }
})();
