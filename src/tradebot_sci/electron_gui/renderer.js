// ═══════════════════════════════════════════════════════════
// TRADEBOT ELECTRON GUI - CORE RENDERER
// ═══════════════════════════════════════════════════════════
// Senior Frontend Architect Stabilization & Security Hardening
// ═══════════════════════════════════════════════════════════

/**
 * ARCHITECTURE OVERVIEW:
 * 1. UNIFIED STATE: All UI data resides in 'dashboardState'.
 * 2. REACTIVE SYNC: 'syncUI()' is the sole writer to the DOM.
 * 3. SECURITY: Zero .innerHTML for dynamic data. textContent/createElement only.
 * 4. IDEMPOTENT CHART: initChart() reuses existing instance.
 * 5. GLOBAL TIME: formatTime() handles 12h/24h toggle across UI.
 */

// --- Global Chart & Series References ---
let chart;
let candleSeries;
let indicatorSeries;
let emaSeries;
let smaSeries;
let stopLossLine;
let takeProfitLine;
let entryPriceLine;
let tradeMarkers = [];
let markerCache = {};
let candleData = [];
let chartResizeObserver = null;

// =======================================================================
// 1. UNIFIED UI STATE (Single Source of Truth)
// =======================================================================
const dashboardState = {
    profile: 'DEVELOPMENT',
    capital: null,
    capitalLabel: 'Overall Capital:',
    cash: null,
    realizedPnL: 0,
    unrealizedPnL: 0,
    pnlTimeframe: localStorage.getItem('pnlTimeframe') || '24h',
    timeFormat: localStorage.getItem('timeFormat') || '24h',
    isSabbath: false,
    isHalted: false,
    activeSymbol: localStorage.getItem('activeSymbol') || 'BTCUSD',
    activeTimeframe: localStorage.getItem('activeTimeframe') || '15m',
    symbols: ['BTCUSD', 'ETHUSD', 'SOLUSD'],
    status: { text: 'disconnected', latency: '--' },
    positions: [],       // Array of { symbol, side, size, unrealized_pnl }
    decisions: [],       // Array of { time, symbol, action, grade, reason, actionClass, scoreClass }
    aiInsight: null,     // { content, timestamp, nextUpdateIn }
    capitalCache: {},    // Internal cache for broker specific math
};

// Expose state for console debugging
window.dashboardState = dashboardState;

// =======================================================================
// 2. TIME & FORMATTING UTILITIES
// =======================================================================

/**
 * Global time formatter that honors the user's 12h/24h setting.
 */
function formatTime(input) {
    const date = input instanceof Date ? input : (input ? new Date(input) : new Date());
    const hours24 = dashboardState.timeFormat === '24h';

    if (!hours24) {
        let h = date.getHours();
        const m = date.getMinutes().toString().padStart(2, '0');
        const s = date.getSeconds().toString().padStart(2, '0');
        const ampm = h >= 12 ? 'PM' : 'AM';
        h = h % 12 || 12;
        return `${h}:${m}:${s} ${ampm}`;
    } else {
        const h = date.getHours().toString().padStart(2, '0');
        const m = date.getMinutes().toString().padStart(2, '0');
        const s = date.getSeconds().toString().padStart(2, '0');
        return `${h}:${m}:${s}`;
    }
}

/**
 * XSS-safe text escaping
 */
function escapeHtml(str) {
    if (typeof str !== 'string') return String(str ?? '');
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
}

// =======================================================================
// 3. REACTIVE SYNC ENGINE (Exclusive Path for DOM Updates)
// =======================================================================

function syncUI() {
    const prev = syncUI._prev || {};
    const s = dashboardState;

    const setText = (id, val) => {
        if (prev[id] === val) return;
        const el = document.getElementById(id);
        if (el) el.textContent = val;
        prev[id] = val;
    };

    // Header Stats
    setText('status-profile', s.profile);
    setText('capital-label', s.capitalLabel);
    if (s.capital !== null) {
        setText('account-capital', s.capital.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
    }
    if (s.cash !== null) {
        setText('account-cash', s.cash.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
    }

    // PnL & Equity Display
    syncPnLDisplay(s, prev);

    // Sabbath/Halt logic
    const sabbathEl = document.getElementById('status-sabbath');
    if (sabbathEl && prev._sabbath !== s.isSabbath) {
        sabbathEl.classList.toggle('hidden', !s.isSabbath);
        prev._sabbath = s.isSabbath;
    }

    // Connection Status
    syncStatusDisplay(s.status, prev);

    // Charts & Labels
    setText('chart-symbol-label', s.activeSymbol);
    setText('chart-tf-label', s.activeTimeframe);

    // Tables & Insights
    syncHoldingsTable(s.positions, prev);
    syncDecisionsTable(s.decisions, prev);
    syncAIInsight(s.aiInsight, prev);

    syncUI._prev = Object.assign({}, prev);
}
syncUI._prev = {};

function syncPnLDisplay(s, prev) {
    const equityEl = document.getElementById('account-equity');
    const pnlLabel = document.getElementById('pnl-mode-label');
    if (!equityEl) return;

    let displayVal = 0;
    let labelText = "Profits & Losses";

    if (s.pnlTimeframe === 'holdings') {
        displayVal = Number(s.unrealizedPnL) || 0;
        labelText = "Profits & Losses (Active)";
    } else {
        displayVal = (Number(s.realizedPnL) || 0) + (Number(s.unrealizedPnL) || 0);
        labelText = `Profits & Losses (${s.pnlTimeframe.toUpperCase()})`;
    }

    const formatted = displayVal.toFixed(2);
    if (prev._pnlVal !== formatted || prev._pnlLabel !== labelText) {
        if (pnlLabel) pnlLabel.textContent = labelText + ":";
        equityEl.textContent = formatted;
        equityEl.className = displayVal >= 0
            ? "text-4xl font-black text-emerald-400 drop-shadow-[0_0_15px_rgba(16,185,129,0.3)] tabular-nums"
            : "text-4xl font-black text-red-500 drop-shadow-[0_0_15px_rgba(239,68,68,0.3)] tabular-nums";
        prev._pnlVal = formatted;
        prev._pnlLabel = labelText;
    }
}

function syncStatusDisplay(status, prev) {
    const dot = document.getElementById('status-dot');
    const text = document.getElementById('status-text');
    const latency = document.getElementById('status-latency');

    if (prev._statusText !== status.text) {
        if (text) text.textContent = `Status: ${status.text.toUpperCase()}`;
        if (dot) {
            dot.className = status.text === 'connected'
                ? "w-2.5 h-2.5 rounded-full bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.5)] animate-pulse"
                : "w-2.5 h-2.5 rounded-full bg-red-500 shadow-[0_0_10px_rgba(239,68,68,0.5)]";
        }
        prev._statusText = status.text;
    }
    if (latency && prev._latency !== status.latency) {
        latency.textContent = status.latency;
        prev._latency = status.latency;
    }
}

function syncHoldingsTable(positions, prev) {
    const tbody = document.getElementById('holdings-table-body');
    if (!tbody) return;
    const stateHash = JSON.stringify(positions);
    if (prev._holdingsHash === stateHash) return;

    while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
    if (positions.length === 0) {
        const tr = document.createElement('tr');
        const td = document.createElement('td');
        td.colSpan = 4;
        td.className = 'p-4 text-center text-slate-500 italic text-xs';
        td.textContent = 'No active positions';
        tr.appendChild(td);
        tbody.appendChild(tr);
    } else {
        positions.forEach(pos => {
            const tr = document.createElement('tr');
            tr.className = "border-b border-slate-700/30 hover:bg-slate-800/20";

            const pnl = parseFloat(pos.unrealized_pnl || 0);
            const side = (pos.side || 'LONG').toUpperCase();

            [[pos.symbol, 'p-2 font-mono font-bold text-slate-200'],
            [side, `p-2 text-center font-bold text-xs ${side === 'SHORT' ? 'text-red-400' : 'text-green-400'}`],
            [Math.abs(parseFloat(pos.size)).toFixed(4), 'p-2 text-right font-mono text-slate-400'],
            [`${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`, `p-2 text-right font-mono font-bold ${pnl >= 0 ? 'text-green-400' : 'text-red-500'}`]
            ].forEach(([text, cls]) => {
                const td = document.createElement('td');
                td.className = cls;
                td.textContent = text;
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });
    }
    prev._holdingsHash = stateHash;
}

function syncDecisionsTable(decisions, prev) {
    const table = document.getElementById('decisions-table');
    if (!table) return;
    const stateHash = JSON.stringify(decisions);
    if (prev._decisionsHash === stateHash) return;

    while (table.firstChild) table.removeChild(table.firstChild);
    decisions.forEach(d => {
        const tr = document.createElement('tr');
        tr.className = "hover:bg-cyan-500/5 border-b border-slate-700/20";
        [[formatTime(d.time), 'px-4 py-1.5 text-slate-500 text-left font-mono text-sm'],
        [d.symbol, 'px-4 py-1.5 font-bold text-slate-200 text-left text-lg'],
        [d.action, `px-4 py-1.5 text-left text-sm uppercase tracking-wider ${d.actionClass}`],
        [d.grade, `px-4 py-1.5 ${d.scoreClass} text-left font-black text-lg`],
        [d.reason, 'px-4 py-1.5 text-slate-400 text-sm italic text-left']
        ].forEach(([text, cls]) => {
            const td = document.createElement('td');
            td.className = cls;
            td.textContent = text;
            tr.appendChild(td);
        });
        table.appendChild(tr);
    });
    prev._decisionsHash = stateHash;
}

function syncAIInsight(insight, prev) {
    const scroller = document.getElementById('insight-scroller');
    if (!scroller || !insight) return;
    const stateHash = JSON.stringify(insight);
    if (prev._aiHash === stateHash) return;

    while (scroller.firstChild) scroller.removeChild(scroller.firstChild);
    const sections = parseAIContent(insight.content);
    sections.forEach(s => scroller.appendChild(createBubbleNode(s.title, s.content.join('\n'), s.icon, s.color)));

    const footer = document.createElement('div');
    footer.className = 'insight-footer flex items-center justify-between text-[10px] text-slate-500 pt-3 border-t border-white/5 mt-4';

    const left = document.createElement('span');
    left.textContent = `Updated ${insight.timestamp}`;

    const right = document.createElement('span');
    right.id = 'ai-countdown';
    right.className = 'text-teal-500/70';
    right.textContent = `Next update in ${Math.floor(insight.nextUpdateIn / 60)}m`;

    footer.appendChild(left);
    footer.appendChild(right);
    scroller.appendChild(footer);
    prev._aiHash = stateHash;
}

// =======================================================================
// 4. CHART CORE (Idempotent Optimization)
// =======================================================================

function initChart(intervalSeconds = 900) {
    const container = document.getElementById('chart-area');
    if (!container) return;

    if (chart) {
        chart.applyOptions({
            timeScale: { tickMarkFormatter: _chartTickMarkFormatter },
            localization: { timeFormatter: _chartTimeFormatter },
        });
        return;
    }

    chart = LightweightCharts.createChart(container, {
        layout: {
            background: { type: 'Color', color: 'transparent' },
            textColor: '#94a3b8',
            fontFamily: "'Inter', sans-serif",
        },
        grid: {
            vertLines: { color: 'rgba(255, 255, 255, 0.08)', style: 2 },
            horzLines: { color: 'rgba(255, 255, 255, 0.08)', style: 2 },
        },
        timeScale: {
            borderColor: 'rgba(255, 255, 255, 0.05)',
            timeVisible: true,
            tickMarkFormatter: _chartTickMarkFormatter,
        },
        localization: {
            timeFormatter: _chartTimeFormatter,
        }
    });

    candleSeries = chart.addCandlestickSeries({
        upColor: '#2dd4bf', downColor: '#f43f5e',
        borderVisible: false, wickUpColor: '#2dd4bf', wickDownColor: '#f43f5e',
    });

    indicatorSeries = chart.addHistogramSeries({
        color: '#22c55e', priceFormat: { type: 'volume' }, priceScaleId: 'indicators',
    });

    chart.priceScale('indicators').applyOptions({
        scaleMargins: { top: 0.8, bottom: 0 },
    });

    emaSeries = chart.addLineSeries({ color: '#fbbf24', lineWidth: 2, visible: false, priceLineVisible: false });
    smaSeries = chart.addLineSeries({ color: '#a855f7', lineWidth: 2, visible: false, priceLineVisible: false });

    if (chartResizeObserver) chartResizeObserver.disconnect();
    chartResizeObserver = new ResizeObserver(entries => {
        if (entries[0]) chart.applyOptions({ width: entries[0].contentRect.width, height: entries[0].contentRect.height });
    });
    chartResizeObserver.observe(container);
}

function _chartTickMarkFormatter(time) {
    const d = new Date(time * 1000);
    const ft = formatTime(d).split(':');
    return `${ft[0]}:${ft[1]}`;
}

function _chartTimeFormatter(time) {
    const ft = formatTime(new Date(time * 1000));
    return ft.includes(' ') ? ft.split(' ')[0] + ' ' + ft.split(' ')[1].slice(0, 2) : ft;
}

// =======================================================================
// 5. WEBSOCKET & DATA FLOW
// =======================================================================

let ws;
const WS_URL = 'ws://localhost:8080/ws';

function connectWebSocket() {
    ws = new WebSocket(WS_URL);
    ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            handleBackendMessage(msg);
        } catch (e) {
            console.error("WS Parse Error", e);
        }
    };
    ws.onopen = () => {
        dashboardState.status.text = 'connected';
        syncUI();
        subscribeToAsset(dashboardState.activeSymbol, dashboardState.activeTimeframe);
    };
    ws.onclose = () => {
        dashboardState.status.text = 'disconnected';
        syncUI();
        setTimeout(connectWebSocket, 5000);
    };
}

function handleBackendMessage(msg) {
    switch (msg.type) {
        case 'state':
            updateGlobalState(msg.data);
            break;
        case 'history':
            handleChartHistory(msg);
            break;
        case 'candle':
            handleChartTick(msg);
            break;
        case 'holdings':
            updateHoldingsState(msg.data);
            break;
        case 'log':
            processLogLine(msg.data, msg.level);
            break;
        case 'ai_commentary':
            dashboardState.aiInsight = { content: msg.content, timestamp: msg.timestamp, nextUpdateIn: msg.next_update_in };
            syncUI();
            break;
        case 'pong':
            if (ws._lastPing) {
                dashboardState.status.latency = `${Date.now() - ws._lastPing}ms`;
                syncUI();
            }
            break;
    }
}

function updateGlobalState(data) {
    if (data.profile) dashboardState.profile = data.profile.toUpperCase();
    if (data.capital !== undefined) dashboardState.capital = data.capital;
    if (data.cash !== undefined) dashboardState.cash = data.cash;
    if (data.is_sabbath !== undefined) dashboardState.isSabbath = data.is_sabbath;
    if (data.symbols) dashboardState.symbols = data.symbols;
    if (data.pnl_stats && data.pnl_stats[dashboardState.pnlTimeframe] !== undefined) {
        dashboardState.realizedPnL = parseFloat(data.pnl_stats[dashboardState.pnlTimeframe]);
    }
    syncUI();
    saveState();
}

function updateHoldingsState(data) {
    if (!data) return;
    dashboardState.positions = data.positions || [];
    dashboardState.unrealizedPnL = parseFloat(data.total_unrealized_pnl || 0);
    syncUI();

    // Clear/Update chart lines
    if (lastHoldingsSym !== dashboardState.activeSymbol) {
        clearPositionLines();
        lastHoldingsSym = dashboardState.activeSymbol;
    }
    const pos = dashboardState.positions.find(p => p.symbol === dashboardState.activeSymbol);
    if (pos) updatePositionLines(pos);
    else clearPositionLines();
}
let lastHoldingsSym = null;

// =======================================================================
// 6. LOG PROCESSING & SECURITY HARDENING
// =======================================================================

function processLogLine(line, level) {
    if (!line) return;
    if (line.includes('[DECISION]') || line.includes('[STRUCTURE]') || line.includes('[SAFETY]')) {
        const d = parseDecisionFromLog(line);
        if (d) {
            dashboardState.decisions.unshift(d);
            if (dashboardState.decisions.length > 50) dashboardState.decisions.pop();
            syncUI();
        }
    }
    if (line.includes('[ENTRY]') || line.includes('[FILL]') || line.includes('[EXIT]')) {
        handleTradeEventLog(line);
    }
    appendLog(level || 'INFO', line);
}

function appendLog(level, rawMessage) {
    const term = document.getElementById('log-terminal');
    if (!term) return;
    const div = document.createElement('div');
    div.className = "log-line py-0.5 text-white/90";
    const ts = document.createElement('span');
    ts.className = 'text-slate-600 font-mono mr-2';
    ts.textContent = `[${formatTime()}]`;
    div.appendChild(ts);
    div.appendChild(formatLogMessageSafe(rawMessage));
    term.appendChild(div);
    if (term.children.length > 300) term.removeChild(term.firstChild);
    term.scrollTop = term.scrollHeight;
}

function formatLogMessageSafe(msg) {
    const frag = document.createDocumentFragment();
    const tagRegex = /\[([A-Z]+)\]/g;
    let last = 0; let m;
    const styles = { 'INFO': 'text-blue-500 font-bold', 'SUCCESS': 'text-green-500 font-bold', 'ERROR': 'text-red-500 font-bold', 'WARNING': 'text-yellow-500 font-bold', 'DECISION': 'text-purple-500 font-bold', 'STRUCTURE': 'text-teal-500 font-bold' };
    while ((m = tagRegex.exec(msg)) !== null) {
        if (m.index > last) frag.appendChild(document.createTextNode(msg.slice(last, m.index)));
        const tag = document.createElement('span');
        tag.className = styles[m[1]] || 'text-slate-400';
        tag.textContent = `[${m[1]}]`;
        frag.appendChild(tag);
        last = m.index + m[0].length;
    }
    if (last < msg.length) frag.appendChild(document.createTextNode(msg.slice(last)));
    return frag;
}

// =======================================================================
// 7. CHART TRADING UI (Lines & Markers)
// =======================================================================

function updatePositionLines(pos) {
    clearPositionLines();
    if (!candleSeries || !pos) return;

    if (pos.stop_loss || pos.sl) {
        const val = pos.stop_loss || pos.sl;
        stopLossLine = candleSeries.createPriceLine({
            price: val, color: '#ef4444', lineWidth: 2, lineStyle: 2,
            axisLabelVisible: true, title: `SL @ ${val.toFixed(4)}`
        });
    }
    if (pos.take_profit || pos.tp) {
        const val = pos.take_profit || pos.tp;
        takeProfitLine = candleSeries.createPriceLine({
            price: val, color: '#22c55e', lineWidth: 2, lineStyle: 2,
            axisLabelVisible: true, title: `TP @ ${val.toFixed(4)}`
        });
    }
}

function clearPositionLines() {
    if (!candleSeries) return;
    if (stopLossLine) { candleSeries.removePriceLine(stopLossLine); stopLossLine = null; }
    if (takeProfitLine) { candleSeries.removePriceLine(takeProfitLine); takeProfitLine = null; }
    if (entryPriceLine) { candleSeries.removePriceLine(entryPriceLine); entryPriceLine = null; }
}

function handleTradeEventLog(line) {
    const isEntry = line.includes('[ENTRY]') || line.includes('[FILL]');
    const isExit = line.includes('[EXIT]');
    const symMatch = line.match(/\[(?:ENTRY|FILL|EXIT)\]\s+([A-Z0-9]+)/i);
    const priceMatch = line.match(/price[=:]?\s*([\d.]+)/i) || line.match(/@\s*([\d.]+)/);

    if (symMatch) {
        const symbol = symMatch[1].toUpperCase();
        const price = priceMatch ? parseFloat(priceMatch[1]) : null;
        const time = Math.floor(Date.now() / 1000); // Should parse from line for accuracy

        if (isEntry) addTradeMarker(time, true, symbol, price);
        else if (isExit) addTradeMarker(time, false, symbol, price, "EXIT");
    }
}

function addTradeMarker(time, isBuy, symbol, price, text) {
    if (!markerCache[symbol]) markerCache[symbol] = [];
    markerCache[symbol].push({
        time: time,
        position: isBuy ? 'belowBar' : 'aboveBar',
        color: isBuy ? '#22c55e' : '#ef4444',
        shape: isBuy ? 'arrowUp' : 'arrowDown',
        text: text || (isBuy ? `BUY @ ${price}` : `SELL @ ${price}`),
    });
    if (symbol === dashboardState.activeSymbol) candleSeries.setMarkers(markerCache[symbol]);
}

// =======================================================================
// 8. PROFILES MODULE (Security Hardened)
// =======================================================================

window.profilesModule = (function () {
    let allProfiles = {};
    let initialized = false;

    async function init() {
        if (initialized) return;
        const res = await window.api.invoke('read-profiles');
        if (res) allProfiles = parseYaml(res);
        renderProfileSidebar();
        setupEvents();
        initialized = true;
    }

    function renderProfileSidebar() {
        const list = document.getElementById('profile-list');
        if (!list) return;
        while (list.firstChild) list.removeChild(list.firstChild);

        Object.keys(allProfiles).forEach(name => {
            const item = document.createElement('div');
            item.className = "p-3 rounded-lg hover:bg-white/5 cursor-pointer text-slate-400";
            item.textContent = name.toUpperCase();
            item.onclick = () => selectProfile(name);
            list.appendChild(item);
        });
    }

    function selectProfile(name) {
        document.getElementById('profile-name-display').textContent = name.toUpperCase();
        renderTab('general', allProfiles[name]);
    }

    function renderTab(type, data) {
        const container = document.getElementById('profile-tab-content');
        if (!container) return;
        while (container.firstChild) container.removeChild(container.firstChild);

        const header = document.createElement('h3');
        header.className = "text-teal-400 font-bold mb-4";
        header.textContent = type.toUpperCase() + " SETTINGS";
        container.appendChild(header);

        // Security Hardened Input Generation
        Object.keys(data).forEach(key => {
            if (typeof data[key] === 'string' || typeof data[key] === 'number') {
                const row = document.createElement('div');
                row.className = "mb-3 flex justify-between items-center";
                const label = document.createElement('span');
                label.className = "text-xs text-slate-400";
                label.textContent = key;
                const input = document.createElement('input');
                input.className = "bg-black/40 border border-white/10 p-1 text-xs text-white rounded";
                input.value = data[key];
                row.append(label, input);
                container.appendChild(row);
            }
        });
    }

    function parseYaml(str) {
        // Simple line parser for our profile structure
        const obj = {}; let curr;
        str.split('\n').forEach(l => {
            const m = l.match(/^\s+([a-z0-9_]+):$/);
            if (m) { curr = m[1]; obj[curr] = {}; }
            else if (curr) {
                const kv = l.match(/^\s+([a-z0-9_]+):\s*(.*)$/);
                if (kv) obj[curr][kv[1]] = kv[2].trim();
            }
        });
        return obj;
    }

    function setupEvents() {
        const btn = document.getElementById('btn-new-profile');
        if (btn) btn.onclick = () => appendLog("INFO", "Create New Profile triggered");
    }

    return { init };
})();

// =======================================================================
// 9. PERSISTENCE & INIT
// =======================================================================

function saveState() {
    localStorage.setItem('tradebot_active_sym', dashboardState.activeSymbol);
    localStorage.setItem('tradebot_active_tf', dashboardState.activeTimeframe);
}

function loadState() {
    dashboardState.activeSymbol = localStorage.getItem('tradebot_active_sym') || 'BTCUSD';
    dashboardState.activeTimeframe = localStorage.getItem('tradebot_active_tf') || '15m';
}

function init() {
    loadState();
    initChart();
    connectWebSocket();
    setupInteractive();

    // Bridge to analytics
    if (window.analyticsModule) window.analyticsModule.init();

    syncUI();
    console.log("Senior Architect Stabilization Complete.");
}

function setupInteractive() {
    // Symbol Arrows
    document.getElementById('btn-next-symbol')?.addEventListener('click', () => {
        const idx = (dashboardState.symbols.indexOf(dashboardState.activeSymbol) + 1) % dashboardState.symbols.length;
        dashboardState.activeSymbol = dashboardState.symbols[idx];
        subscribeToAsset(dashboardState.activeSymbol, dashboardState.activeTimeframe);
        syncUI();
        saveState();
    });

    // Timeframe Click
    document.querySelectorAll('.timeframe-btn').forEach(btn => {
        btn.onclick = (e) => {
            dashboardState.activeTimeframe = e.target.textContent;
            subscribeToAsset(dashboardState.activeSymbol, dashboardState.activeTimeframe);
            syncUI();
            saveState();
        };
    });

    // Nav switch
    document.querySelectorAll('[id^="nav-"]').forEach(btn => {
        btn.onclick = (e) => {
            const view = e.currentTarget.id.replace('nav-', '');
            document.querySelectorAll('[id^="view-"]').forEach(v => v.classList.toggle('hidden', v.id !== `view-${view}`));
            if (view === 'profile') window.profilesModule.init();
        };
    });
}

function subscribeToAsset(symbol, tf) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'subscribe', symbol, tf }));
        if (candleSeries) candleSeries.setData([]);
        clearPositionLines();
    }
}

// Start
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
else init();
