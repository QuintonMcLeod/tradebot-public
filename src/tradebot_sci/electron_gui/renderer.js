// ═══════════════════════════════════════════════════════════
// TRADEBOT ELECTRON GUI - CORE RENDERER (DEFINITIVE)
// ═══════════════════════════════════════════════════════════
// - Architectural Refactor: State-Driven (SSOT)
// - Security hardening: 100% textContent / createElement
// - Idempotent Charting & Unified Time
// ═══════════════════════════════════════════════════════════

// --- Global Chart & Series References ---
let chart;
let candleSeries;
let indicatorSeries;
let emaSeries;
let smaSeries;
let stopLossSeries;  // Restore line series for dynamic SL/TP
let takeProfitSeries;
let entryPriceLine;
let markerCache = {};
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
    activeSymbol: localStorage.getItem('tradebot_active_sym') || 'BTCUSD',
    activeTimeframe: localStorage.getItem('tradebot_active_tf') || '15m',
    symbols: ['BTCUSD', 'ETHUSD', 'SOLUSD'],
    status: { text: 'disconnected', latency: '--' },
    positions: [],       // Array of { symbol, side, size, unrealized_pnl }
    decisions: [],       // Array of { time, symbol, action, grade, reason, actionClass, scoreClass }
    aiInsight: null,     // { content, timestamp, nextUpdateIn }
    currentPanel: 'panel-decisions',
};

// Expose state for console debugging
window.dashboardState = dashboardState;

// =======================================================================
// 2. TIME & FORMATTING UTILITIES
// =======================================================================

/**
 * Global time formatter that honors the user's 12h/24h setting.
 * @param {Date|number|string} input - Date object, timestamp, or ISO string
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

// =======================================================================
// 3. REACTIVE SYNC ENGINE (Exclusive Path for DOM Updates)
// =======================================================================

/**
 * Main synchronization loop. Surgical updates to the DOM based on state.
 */
function syncUI() {
    const prev = syncUI._prev || {};
    const s = dashboardState;

    const setText = (id, val) => {
        if (prev[id] === val) return;
        const el = document.getElementById(id);
        if (el) el.textContent = val;
        prev[id] = val;
    };

    // Header & Stats
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

    // Status Indicators
    const sabbathEl = document.getElementById('status-sabbath');
    if (sabbathEl && prev._sabbath !== s.isSabbath) {
        sabbathEl.classList.toggle('hidden', !s.isSabbath);
        prev._sabbath = s.isSabbath;
    }
    syncStatusDisplay(s.status, prev);

    // Chart Labels
    setText('chart-symbol-label', s.activeSymbol);
    setText('chart-tf-label', s.activeTimeframe);

    // Bug 6: Timeframe Highlighting
    syncTimeframeButtons();

    // Panes & Insights
    syncHoldingsTable(s, prev);
    syncDecisionsTable(s.decisions, prev);
    syncAIInsight(s.aiInsight, prev);

    syncUI._prev = Object.assign({}, prev);
}
syncUI._prev = {};

/**
 * Bug 6: Unified Timeframe Highlight Engine
 */
function syncTimeframeButtons() {
    const activeTf = dashboardState.activeTimeframe;
    const highlightClasses = ['bg-teal-500/20', 'text-teal-300', 'border-teal-500/40', 'font-bold'];

    document.querySelectorAll('.timeframe-btn').forEach(btn => {
        const isMatch = btn.textContent.trim().toLowerCase() === activeTf.toLowerCase();
        if (isMatch) {
            btn.classList.add(...highlightClasses);
            btn.classList.remove('text-slate-400', 'hover:text-white', 'cursor-pointer');
        } else {
            btn.classList.remove(...highlightClasses);
            btn.classList.add('text-slate-400', 'hover:text-white', 'cursor-pointer');
        }
    });

    const select = document.getElementById('timeframe-select');
    if (select) {
        const options = Array.from(select.options).map(o => o.value);
        if (options.includes(activeTf)) {
            select.classList.add('bg-teal-500/20', 'text-teal-300', 'font-bold');
            select.value = activeTf;
        } else {
            select.classList.remove('bg-teal-500/20', 'text-teal-300', 'font-bold');
        }
    }
}

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

function syncHoldingsTable(s, prev) {
    const tbody = document.getElementById('holdings-table-body');
    if (!tbody) return;
    const stateHash = JSON.stringify(s.positions);
    if (prev._holdingsHash === stateHash) return;

    while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
    if (s.positions.length === 0) {
        const tr = document.createElement('tr');
        const td = document.createElement('td');
        td.colSpan = 4;
        td.className = 'p-4 text-center text-slate-500 italic text-xs';
        td.textContent = 'No active positions';
        tr.appendChild(td);
        tbody.appendChild(tr);
    } else {
        s.positions.forEach(pos => {
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

    // Surgical Chart Line Update
    const activePos = s.positions.find(p => p.symbol === s.activeSymbol);
    if (prev._lastActivePos !== JSON.stringify(activePos)) {
        if (activePos) updatePositionLines(activePos);
        else clearPositionLines();
        prev._lastActivePos = JSON.stringify(activePos);
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

function initChart() {
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

    // Restore specialized SL/TP Line Series
    stopLossSeries = chart.addLineSeries({ color: '#ef4444', lineWidth: 2, lineStyle: 2, priceLineVisible: false, lastValueVisible: true });
    takeProfitSeries = chart.addLineSeries({ color: '#22c55e', lineWidth: 2, lineStyle: 2, priceLineVisible: false, lastValueVisible: true });

    if (chartResizeObserver) chartResizeObserver.disconnect();
    chartResizeObserver = new ResizeObserver(entries => {
        if (entries[0]) chart.applyOptions({ width: entries[0].contentRect.width, height: entries[0].contentRect.height });
    });
    chartResizeObserver.observe(container);
}

function _chartTickMarkFormatter(time) {
    const d = new Date(time * 1000);
    const hours24 = dashboardState.timeFormat === '24h';
    if (hours24) {
        const h = d.getHours().toString().padStart(2, '0');
        const m = d.getMinutes().toString().padStart(2, '0');
        return `${h}:${m}`;
    } else {
        let h = d.getHours();
        const ampm = h >= 12 ? 'PM' : 'AM';
        h = h % 12 || 12;
        const m = d.getMinutes().toString().padStart(2, '0');
        return `${h}:${m} ${ampm}`;
    }
}

function _chartTimeFormatter(time) {
    const d = new Date(time * 1000);
    const hours24 = dashboardState.timeFormat === '24h';
    if (hours24) {
        return formatTime(d);
    } else {
        let h = d.getHours();
        const ampm = h >= 12 ? 'PM' : 'AM';
        h = h % 12 || 12;
        const m = d.getMinutes().toString().padStart(2, '0');
        const s = d.getSeconds().toString().padStart(2, '0');
        return `${h}:${m}:${s} ${ampm}`;
    }
}

// =======================================================================
// 5. WEBSOCKET & DATA FLOW (State Updaters)
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

        // Bug 2: Heartbeat Ping (Every 5 seconds)
        if (ws._heartbeat) clearInterval(ws._heartbeat);
        ws._heartbeat = setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) {
                ws._lastPing = Date.now();
                ws.send(JSON.stringify({ type: 'ping' }));
            }
        }, 5000);
    };
    ws.onclose = () => {
        if (ws._heartbeat) clearInterval(ws._heartbeat);
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
        case 'candle':
            if (candleSeries) {
                const tzOffsetSeconds = new Date().getTimezoneOffset() * 60;
                const fixedData = { ...msg.data, time: msg.data.time - tzOffsetSeconds };
                candleSeries.update(fixedData);

                // RESTORE VOLUME LOGIC
                if (indicatorSeries) {
                    indicatorSeries.update({
                        time: fixedData.time,
                        value: msg.data.volume || msg.data.value || 0,
                        color: msg.data.close >= msg.data.open ? '#22c55e' : '#ef4444'
                    });
                }
            }
            break;
        case 'history':
            if (candleSeries) candleSeries.setData(msg.data);
            break;
    }
}

function updateGlobalState(data) {
    if (data.profile) dashboardState.profile = data.profile.toUpperCase();
    if (data.capital !== undefined) dashboardState.capital = data.capital;
    if (data.cash !== undefined) dashboardState.cash = data.cash;
    if (data.is_sabbath !== undefined) dashboardState.isSabbath = data.is_sabbath;
    if (data.symbols) dashboardState.symbols = data.symbols;

    const pnlVal = data.pnl_stats?.[dashboardState.pnlTimeframe];
    if (pnlVal !== undefined) dashboardState.realizedPnL = parseFloat(pnlVal);

    syncUI();
    saveState();
}

function updateHoldingsState(data) {
    if (!data) return;
    // Bug 1: Support direct array or object.positions
    dashboardState.positions = Array.isArray(data) ? data : (data.positions || []);
    dashboardState.unrealizedPnL = parseFloat(data.total_unrealized_pnl || 0);
    syncUI();
}

// =======================================================================
// 6. LOG PROCESSING & UI STREAMS
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
    if (line.includes('[ENTRY]') || line.includes('[EXIT]')) {
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
    const styles = {
        'INFO': 'text-blue-500 font-bold',
        'SUCCESS': 'text-green-500 font-bold',
        'ERROR': 'text-red-500 font-bold',
        'WARNING': 'text-yellow-500 font-bold',
        'DECISION': 'text-purple-500 font-bold',
        'STRUCTURE': 'text-teal-500 font-bold'
    };
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

    const sl = pos.stop_loss || pos.sl;
    if (sl && stopLossSeries) {
        // user requested addLineSeries style update
        const data = candleSeries.data();
        if (data.length > 0) {
            const lineData = data.map(d => ({ time: d.time, value: sl }));
            stopLossSeries.setData(lineData);
        }
    }
    const tp = pos.take_profit || pos.tp;
    if (tp && takeProfitSeries) {
        const data = candleSeries.data();
        if (data.length > 0) {
            const lineData = data.map(d => ({ time: d.time, value: tp }));
            takeProfitSeries.setData(lineData);
        }
    }
}

function clearPositionLines() {
    if (stopLossSeries) stopLossSeries.setData([]);
    if (takeProfitSeries) takeProfitSeries.setData([]);
    if (entryPriceLine && candleSeries) { candleSeries.removePriceLine(entryPriceLine); entryPriceLine = null; }
}

function handleTradeEventLog(line) {
    const symMatch = line.match(/\[(?:ENTRY|EXIT)\]\s+([A-Z0-9]+)/i);
    const priceMatch = line.match(/price[=:]?\s*([\d.]+)/i) || line.match(/@\s*([\d.]+)/);
    if (!symMatch) return;

    const symbol = symMatch[1].toUpperCase();
    const price = priceMatch ? parseFloat(priceMatch[1]) : null;
    const isEntry = line.includes('[ENTRY]');

    updateChartMarkers({
        symbol,
        price,
        type: isEntry ? 'buy' : 'sell',
        time: Math.floor(Date.now() / 1000)
    });
}

/**
 * RESTORED: Centralized marker management
 */
function updateChartMarkers(tradeData) {
    const { symbol, price, type, time } = tradeData;
    if (!markerCache[symbol]) markerCache[symbol] = symbol;

    markerCache[symbol].push({
        time: time,
        position: type === 'buy' ? 'belowBar' : 'aboveBar',
        color: type === 'buy' ? '#22c55e' : '#f43f5e',
        shape: type === 'buy' ? 'arrowUp' : 'arrowDown',
        text: `${type.toUpperCase()} @ ${price ? price.toFixed(2) : 'MKT'}`,
    });

    if (symbol === dashboardState.activeSymbol && candleSeries) {
        candleSeries.setMarkers(markerCache[symbol]);
    }
}

// =======================================================================
// 8. HELPER MODULES
// =======================================================================

function parseDecisionFromLog(line) {
    try {
        const content = line.split(']').slice(1).join(']').trim();

        // Bug 10: Hardened Symbol Detection
        let symbol = null;
        const symbolMatch = content.match(/symbol=([A-Z0-9]+)/i);

        if (symbolMatch) {
            symbol = symbolMatch[1].toUpperCase();
        } else {
            // Bug 3: Hardened Symbol Detection (Extended Ignore List)
            const regex = /\b[A-Z]{3,7}\b/g;
            const matches = content.match(regex) || [];
            const ignoreList = ['ENTRY', 'EXIT', 'PHASE', 'TRUE', 'FALSE', 'VETO', 'SAFETY', 'INFO', 'WARN', 'ERROR', 'STATUS'];
            symbol = matches.find(m => !ignoreList.includes(m.toUpperCase()));
        }

        if (!symbol || symbol.length < 3) return null;

        const actionMatch = content.match(/action=([^\s|]+)/i) || content.match(/gate=([^\s|]+)/i) || content.match(/Decision:\s+([A-Z_]+)/i);
        const scoreMatch = content.match(/score=([\d.]+)/i) || content.match(/icc_score=([\d.]+)/i);
        const reasonMatch = content.match(/reason=([^|]+)/i) || content.match(/\(([^)]+)\)$/);

        const action = (actionMatch ? actionMatch[1] : 'HOLD').toUpperCase();
        let grade = 'N/A';
        let scoreClass = 'text-slate-600';
        if (scoreMatch) {
            const s = parseFloat(scoreMatch[1]);
            if (s >= 90) { grade = 'A'; scoreClass = 'text-green-400 text-glow'; }
            else if (s >= 80) { grade = 'B'; scoreClass = 'text-cyan-400'; }
            else if (s >= 70) { grade = 'C'; scoreClass = 'text-yellow-400'; }
            else { grade = s >= 60 ? 'D' : 'F'; scoreClass = 'text-red-500'; }
        }

        let actionClass = 'text-slate-400';
        if (['BUY', 'LONG', 'ENTRY', 'SCALE_IN'].some(k => action.includes(k))) actionClass = 'text-green-400';
        if (['SELL', 'SHORT', 'EXIT', 'CLOSE'].some(k => action.includes(k))) actionClass = 'text-red-500';

        return {
            time: new Date(), symbol,
            action, grade, reason: reasonMatch ? reasonMatch[1].trim() : 'System Check',
            actionClass, scoreClass
        };
    } catch (e) { return null; }
}

function parseAIContent(content) {
    const lines = content.split('\n');
    const sections = [];
    let current = { title: 'Market Insight', content: [], icon: 'insights', color: 'teal' };
    lines.forEach(line => {
        const t = line.trim();
        if (!t) return;
        if (t.includes('📊')) {
            if (current.content.length) sections.push(Object.assign({}, current));
            current = { title: "What's Happening", content: [], icon: 'trending_up', color: 'teal' };
        } else if (t.includes('🎯')) {
            if (current.content.length) sections.push(Object.assign({}, current));
            current = { title: "Strategic Watch", content: [], icon: 'visibility', color: 'purple' };
        } else {
            current.content.push(t.replace(/^\s*[-•]\s*/, '• '));
        }
    });
    if (current.content.length) sections.push(current);
    return sections;
}

function createBubbleNode(title, text, icon, color) {
    const bubble = document.createElement('div');
    bubble.className = `insight-bubble bg-black/40 border border-${color}-500/30 rounded-xl p-4 backdrop-blur-sm mb-4`;

    const wrapper = document.createElement('div');
    wrapper.className = 'flex items-start gap-3';

    const iconSpan = document.createElement('span');
    iconSpan.className = `material-symbols-outlined text-${color}-400 text-lg mt-0.5`;
    iconSpan.textContent = icon;

    const content = document.createElement('div');
    content.className = 'flex-1';

    const titleDiv = document.createElement('div');
    titleDiv.className = `text-[10px] font-bold uppercase tracking-wider text-${color}-400 mb-1`;
    titleDiv.textContent = title;

    const textDiv = document.createElement('div');
    textDiv.className = 'text-xs text-slate-300 leading-relaxed';
    textDiv.textContent = text;

    content.appendChild(titleDiv);
    content.appendChild(textDiv);
    wrapper.appendChild(iconSpan);
    wrapper.appendChild(content);
    bubble.appendChild(wrapper);
    return bubble;
}

// =======================================================================
// 9. PERSISTENCE & INITIALIZATION
// =======================================================================

function saveState() {
    localStorage.setItem('tradebot_active_sym', dashboardState.activeSymbol);
    localStorage.setItem('tradebot_active_tf', dashboardState.activeTimeframe);
}

function init() {
    initChart();
    connectWebSocket();
    setupInteractive();

    // Auto-scroll chart heartbeat
    setInterval(() => { if (chart) chart.timeScale().scrollToRealTime(); }, 30000);

    // INSTANT SETTINGS BRIDGE
    window.api.on('env-updated', (data) => {
        if (!data) return;
        // Sync specific keys that affect UI behavior
        if (data.timeFormat || data.TIME_FORMAT) {
            dashboardState.timeFormat = data.timeFormat || data.TIME_FORMAT;
            localStorage.setItem('timeFormat', dashboardState.timeFormat);
            // FIX TIME VISIBILITY: Update chart immediately without reload
            if (chart) {
                chart.applyOptions({
                    timeScale: { tickMarkFormatter: _chartTickMarkFormatter },
                    localization: { timeFormatter: _chartTimeFormatter },
                });
            }
        }
        // General state sync for any other relevant keys
        Object.assign(dashboardState, data);
        syncUI();
    });

    syncUI();
}

function setupInteractive() {
    // Window Controls (IDs Fixed - Bug 2: Switch to window.api.send)
    document.getElementById('btn-minimize')?.addEventListener('click', () => window.api.send('minimize-window'));
    document.getElementById('btn-maximize')?.addEventListener('click', () => window.api.send('maximize-window'));
    document.getElementById('btn-close')?.addEventListener('click', () => window.api.send('close-window'));

    // Bug 4 & 5: Chart Helpers
    document.getElementById('btn-calendar')?.addEventListener('click', () => {
        document.getElementById('date-picker-input')?.showPicker();
    });
    document.getElementById('btn-indicators')?.addEventListener('click', () => {
        document.getElementById('indicator-dropdown')?.classList.toggle('hidden');
    });

    // Indicator Toggles (Bug 4)
    document.getElementById('toggle-ema')?.addEventListener('change', (e) => {
        if (emaSeries) emaSeries.applyOptions({ visible: e.target.checked });
    });
    document.getElementById('toggle-sma')?.addEventListener('change', (e) => {
        if (smaSeries) smaSeries.applyOptions({ visible: e.target.checked });
    });

    // Symbol Switcher
    document.getElementById('btn-next-symbol')?.addEventListener('click', () => {
        const idx = (dashboardState.symbols.indexOf(dashboardState.activeSymbol) + 1) % dashboardState.symbols.length;
        dashboardState.activeSymbol = dashboardState.symbols[idx];
        subscribeToAsset(dashboardState.activeSymbol, dashboardState.activeTimeframe);
        syncUI();
        saveState();
    });

    // Timeframe Buttons
    document.querySelectorAll('.timeframe-btn').forEach(btn => {
        btn.onclick = (e) => {
            dashboardState.activeTimeframe = e.target.textContent.trim();
            subscribeToAsset(dashboardState.activeSymbol, dashboardState.activeTimeframe);
            syncUI();
            saveState();
        };
    });

    // Bug 7: Timeframe Dropdown Select
    const tfSelect = document.getElementById('timeframe-select');
    if (tfSelect) {
        tfSelect.onchange = (e) => {
            if (e.target.value) {
                dashboardState.activeTimeframe = e.target.value;
                subscribeToAsset(dashboardState.activeSymbol, dashboardState.activeTimeframe);
                syncUI();
                saveState();
            }
        };
    }

    // Sidebar Navigation
    document.querySelectorAll('[id^="nav-"]').forEach(btn => {
        btn.onclick = (e) => {
            const view = e.currentTarget.id.replace('nav-', '');

            // Fix Sidebar Highlights
            document.querySelectorAll('[id^="nav-"]').forEach(n => n.classList.remove('active', 'bg-teal-500/20', 'text-teal-300', 'border-2', 'border-teal-500/30', 'shadow-[0_0_20px_rgba(20,184,166,0.3)]', 'font-bold'));
            document.querySelectorAll('[id^="nav-"]').forEach(n => n.classList.add('hover:bg-white/5', 'text-slate-400', 'font-medium'));

            e.currentTarget.classList.add('active', 'bg-teal-500/20', 'text-teal-300', 'border-2', 'border-teal-500/30', 'shadow-[0_0_20px_rgba(20,184,166,0.3)]', 'font-bold');
            e.currentTarget.classList.remove('hover:bg-white/5', 'text-slate-400', 'font-medium');

            // View Toggling - Precise and Robust
            const views = {
                'dashboard': 'view-dashboard',
                'graph': 'view-analytics',
                'settings': 'view-settings',
                'profile': 'view-profiles'
            };

            Object.keys(views).forEach(vKey => {
                const el = document.getElementById(views[vKey]);
                if (el) el.classList.toggle('hidden', vKey !== view);
            });

            // Module Initializers with Try/Catch
            try {
                if (view === 'graph' && window.analyticsModule) window.analyticsModule.init();
                if (view === 'profile' && window.profilesModule) window.profilesModule.init();
                if (view === 'settings' && window.settingsModule) window.settingsModule.init();
            } catch (err) {
                console.error(`[GUI] Error initializing module for view ${view}:`, err);
            }
        };
    });

    // RESTORE: Panel Rotation
    document.getElementById('btn-next-panel')?.addEventListener('click', () => {
        const panels = ['panel-decisions', 'panel-commentary', 'panel-holdings'];
        const titles = ['Decisions Panel', 'AI Insight', 'Holdings'];
        let idx = panels.indexOf(dashboardState.currentPanel);
        idx = (idx + 1) % panels.length;
        dashboardState.currentPanel = panels[idx];

        panels.forEach((p, i) => {
            const el = document.getElementById(p);
            if (el) el.classList.toggle('hidden', p !== dashboardState.currentPanel);
        });

        const titleEl = document.getElementById('panel-title');
        if (titleEl) titleEl.textContent = titles[idx];
    });
}

function subscribeToAsset(symbol, tf) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'subscribe', symbol, tf }));
        if (candleSeries) candleSeries.setData([]);
        clearPositionLines();
    }
}

// Global Start
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
