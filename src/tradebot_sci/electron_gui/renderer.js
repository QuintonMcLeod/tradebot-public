// --- Chart & DOM State ---
let chart;
let candleSeries;
let indicatorSeries;
let logTerminal;
let statusProfile;
let statusText;
let statusDot;
let statusLatency;

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
            bottom: 0.3, // 30% gap from bottom to make room for indicators
        },
    });

    indicatorSeries = chart.addHistogramSeries({
        color: '#22c55e',
        priceFormat: { type: 'volume' },
        priceScaleId: 'indicators',
    });

    chart.priceScale('indicators').applyOptions({
        scaleMargins: {
            top: 0.85,   // Reserve top 85% (only use bottom 15%)
            bottom: 0,
        },
    });

    new ResizeObserver(entries => {
        if (entries.length === 0 || !entries[0].contentRect) return;
        const width = entries[0].contentRect.width;
        const height = entries[0].contentRect.height;
        chart.applyOptions({ width, height });
    }).observe(chartContainer);

    // [ANTIGRAVITY] Dummy data removed. Waiting for 'history' from backend.
}

function subscribeToAsset(symbol, tf) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        console.log(`Subscribing to ${symbol} (${tf})...`);
        ws.send(JSON.stringify({ type: 'subscribe', symbol, tf }));
    }
}

// [WEBSOCKET] Connect to Python Backend
let ws;
const WS_URL = 'ws://localhost:8080/ws';

function connectWebSocket() {
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
                // Initialize Chart with real historical data
                const currentSym = document.getElementById('chart-symbol-label')?.innerText;
                if (msg.symbol === currentSym) {
                    console.log(`Received history for ${msg.symbol} (${msg.data.length} candles)`);
                    const tzOffsetSeconds = new Date().getTimezoneOffset() * 60;
                    const fixedData = msg.data.map(c => ({
                        ...c,
                        time: c.time - tzOffsetSeconds
                    }));
                    candleSeries.setData(fixedData);
                }
            } else if (msg.type === 'candle') {
                // Update Chart ONLY if it matches current symbol
                const currentSym = document.getElementById('chart-symbol-label')?.innerText;
                if (msg.symbol === currentSym) {
                    // [ANTIGRAVITY FIX] Dynamic Timezone Sync
                    const tzOffsetSeconds = new Date().getTimezoneOffset() * 60;
                    const fixedData = { ...msg.data, time: msg.data.time - tzOffsetSeconds };
                    candleSeries.update(fixedData);
                }
            } else if (msg.type === 'log') {
                parseLogLine(msg.data);
                appendLog(msg.level || "INFO", msg.data);
            } else if (msg.type === 'state') {
                const data = msg.data;
                console.log("Syncing UI state:", data);

                if (data.equity !== undefined) {
                    const equityEl = document.getElementById('account-equity');
                    if (equityEl) {
                        equityEl.innerText = data.equity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                        equityEl.className = `text-sm font-black ${data.equity >= 0 ? 'text-green-400' : 'text-red-500'}`;
                    }
                }
                if (data.capital !== undefined) {
                    const capitalEl = document.getElementById('account-capital');
                    if (capitalEl) {
                        capitalEl.innerText = data.capital.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
                    }
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
                        if (data.is_sabbath) {
                            sabbathEl.classList.remove('hidden');
                        } else {
                            sabbathEl.classList.add('hidden');
                        }
                    }
                }
                saveState();
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
    div.className = "log-line text-white/90 py-0.5";

    const ts = new Date().toLocaleTimeString('en-US', { hour12: false });
    div.innerHTML = `<span class="text-slate-600 font-mono">[${ts}]</span> ${formatLogMessage(rawMessage)}`;

    logTerminal.appendChild(div);
    if (logTerminal.children.length > 300) logTerminal.removeChild(logTerminal.firstChild);
    logTerminal.scrollTop = logTerminal.scrollHeight;
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

function addDecisionRow(symbol, action, scoreNum, reason) {
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

    // Time AM/PM
    const time = new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', second: '2-digit', hour12: true });

    // Grade
    const grade = getScoreGrade(scoreNum);
    const scoreClass = getScoreColor(grade);

    // Action Styling
    let actionHtml = `<span class="text-slate-500">${action}</span>`;
    if (action === "ENTER_LONG" || action === "BUY") {
        actionHtml = `<span class="text-green-400 font-bold text-glow-sm">ENTER_LONG</span>`;
    } else if (action === "ENTER_SHORT" || action === "SELL") {
        actionHtml = `<span class="text-red-500 font-bold text-glow-sm">ENTER_SHORT</span>`;
    } else if (action === "HOLD" || action === "WAIT" || action === "CONTINUATION") {
        actionHtml = `<span class="text-slate-400 font-bold text-glow-sm">${action}</span>`;
    }

    // [ANTIGRAVITY REFINE] Much larger font (text-lg / 18px), bunched rows (py-1.5)
    row.innerHTML = `
        <td class="px-4 py-1.5 text-slate-500 text-left font-mono text-sm">${time}</td>
        <td class="px-4 py-1.5 font-bold text-slate-200 text-left text-lg">${symbol}</td>
        <td class="px-4 py-1.5 text-left text-sm uppercase tracking-wider">${actionHtml}</td>
        <td class="px-4 py-1.5 ${scoreClass} text-left font-black text-lg">${grade}</td>
        <td class="px-4 py-1.5 text-slate-400 text-sm italic text-left">${reason}</td>
    `;

    if (!existingRow) {
        // Prepend to show newest at top if it's a new symbol
        table.prepend(row);
    }
}

// --- IPC / Socket Logic ---
window.api.on('fromMain', (payload) => {
    if (payload.type === 'log-chunk') {
        // Initial chunk (history)
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

    // [ANTIGRAVITY FIX] Update sidebar PNL
    const equityEl = document.getElementById('account-equity');
    if (equityEl && payload.total_unrealized_pnl !== undefined) {
        const totalPnl = parseFloat(payload.total_unrealized_pnl);
        equityEl.textContent = isNaN(totalPnl) ? "0.00" : totalPnl.toFixed(2);

        // Optional: color coding for sidebar
        if (totalPnl >= 0) {
            equityEl.classList.remove('text-red-400');
            equityEl.classList.add('text-emerald-400');
        } else {
            equityEl.classList.remove('text-emerald-400');
            equityEl.classList.add('text-red-400');
        }
    }
}


function parseLogLine(line) {
    if (!line) return;
    console.log("[DEBUG] Parsing Line:", line);

    // 1. Neural Decision Matrix
    if (line.includes('[STRUCTURE]') || line.includes('Decision: Decision:') || line.includes('[DECISION]')) {
        try {
            let content = "";
            if (line.includes('[STRUCTURE]')) content = line.split('[STRUCTURE]')[1].trim();
            else if (line.includes('Decision: Decision:')) content = line.split('Decision: Decision:')[1].trim();
            else if (line.includes('[DECISION]')) content = line.split('[DECISION]')[1].trim();

            const parts = content.split('|');
            const head = parts[0].trim();
            const symbolMatch = head.match(/^([A-Z0-9]+)/);
            const symbol = symbolMatch ? symbolMatch[1] : "UNKNOWN";

            // Search ENTIRE content for action/score/reason
            const body = content;

            let action = "HOLD";
            let score = null;
            let reason = "Evaluation complete";

            const actionMatch = body.match(/action=([^\s|]+)/i) || body.match(/gate=([^\s|]+)/i) || body.match(/Switched to\s+([^\s|]+)/i);
            if (actionMatch) action = actionMatch[1].toUpperCase().replace("STAND_ASIDE", "HOLD").replace("SWEEP", "HOLD");

            const scoreMatch = body.match(/icc_score=([\d\.]+)/i) ||
                body.match(/ICC score\s+([\d\.]+)/i) ||
                body.match(/selection_score=([\d\.]+)/i) ||
                body.match(/\/(\d+)\s+score/i);
            if (scoreMatch) {
                let raw = parseFloat(scoreMatch[1]);
                if (raw <= 1.0 && (line.includes('selection_score') || body.includes('selection_score'))) score = raw * 100;
                else if (raw <= 35.0 && line.includes('/35')) score = (raw / 35.0) * 100;
                else score = raw;
            }

            const reasonMatch = body.match(/reason=([^|]+)/i) || body.match(/\(([^)]+)\)$/);
            if (reasonMatch) reason = reasonMatch[1].trim();

            addDecisionRow(symbol, action, score, reason);

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

    // 2. Profile Parsing (Enhanced)
    if (line.includes('[PROFILE]') || line.includes('profile=') || line.includes('switching to')) {
        const profileMatch = line.match(/profile[:=]\s?([\w\-]+)/i) ||
            line.match(/switching to (?:profile\s+)?([\w\-]+)/i);
        if (profileMatch) {
            const prof = profileMatch[1];
            if (!statusProfile) statusProfile = document.getElementById('status-profile');
            if (statusProfile) {
                statusProfile.innerText = prof.toUpperCase();
                statusProfile.className = "text-xs text-emerald-400 font-bold drop-shadow-sm";
            }
            saveState();
        }
    }

    // 3. P&L / Equity / Capital (Consolidated & Robust)
    // Matches: [OANDA] Account Summary: Balance=123.45, NAV=100.00
    // Matches: [IBKR] Account Summary: Balance=123.45, Equity=100.00
    // Matches: [HEARTBEAT] Capital available: $100.00

    // Balance / Profit (matches first numeric value after 'Balance=' or 'Profit:')
    const balanceMatch = line.match(/(?:balance|Profit|Equity)[:=]\s?\$?\s?([\d\.,\-]+)/i);
    if (balanceMatch) {
        const val = parseFloat(balanceMatch[1].replace(/,/g, ''));
        const equityEl = document.getElementById('account-equity');
        if (equityEl) {
            equityEl.innerText = val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            equityEl.className = `text-sm font-black ${val >= 0 ? 'text-green-400' : 'text-red-500'}`;
        }
    }

    // Capital / NAV (matches first numeric value after 'NAV=' or 'Capital available:')
    const capitalMatch = line.match(/(?:NAV|Capital available)[:=]\s?\$?\s?([\d\.,\-]+)/i);
    if (capitalMatch) {
        const val = parseFloat(capitalMatch[1].replace(/,/g, ''));
        const capitalEl = document.getElementById('account-capital');
        if (capitalEl) {
            capitalEl.innerText = val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
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
const WATCHED_SYMBOLS = ['EURUSD', 'GBPUSD', 'AUDUSD', 'USDJPY', 'GBPJPY', 'EURJPY', 'USDCAD', 'BTCUSD', 'ETHUSD', 'XAUUSD'];
let currentSymbolIndex = 0;

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

    function updateSymbolDisplay() {
        const sym = WATCHED_SYMBOLS[currentSymbolIndex];
        if (symbolLabel) {
            symbolLabel.innerHTML = `${sym}`;
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
        const sym = document.getElementById('chart-symbol-label')?.innerText;
        if (sym) subscribeToAsset(sym, tf);
    });

    // Button Handlers
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

            if (id === 'nav-settings') {
                window.api.send('open-settings');
            }
        });
    });

    // Indicator Button
    document.getElementById('btn-indicators')?.addEventListener('click', () => {
        appendLog("INFO", "[UI] Indicators menu toggled.");
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
        if (state.decisions) document.getElementById('decisions-table').innerHTML = state.decisions;
        if (state.commentary) document.getElementById('commentary-content').innerText = state.commentary;
        if (state.holdings) document.getElementById('holdings-table-body').innerHTML = state.holdings;
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
