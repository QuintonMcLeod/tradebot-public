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
                const currentTfRaw = document.getElementById('chart-tf-label')?.innerText || '15m';

                // [ANTIGRAVITY FIX] Normalize TF for comparison (UI often uses UPPERCASE or different formats)
                // We assume backend sends '5m', '15m'. UI might have '5M', '15m'.
                const normalizeTf = (t) => t.toLowerCase().trim();

                if (msg.symbol === currentSym && normalizeTf(msg.tf) === normalizeTf(currentTfRaw)) {
                    console.log(`Received history for ${msg.symbol} ${msg.tf} (${msg.data.length} candles)`);
                    const tzOffsetSeconds = new Date().getTimezoneOffset() * 60;
                    const fixedData = msg.data.map(c => ({
                        ...c,
                        time: c.time - tzOffsetSeconds
                    }));
                    candleSeries.setData(fixedData);
                } else {
                    console.log(`[UI] Ignoring history for ${msg.symbol} ${msg.tf} (Current: ${currentSym} ${currentTfRaw})`);
                }
            } else if (msg.type === 'candle') {
                // Update Chart ONLY if it matches current symbol AND timeframe
                const currentSym = document.getElementById('chart-symbol-label')?.innerText;
                const currentTfRaw = document.getElementById('chart-tf-label')?.innerText || '15m';

                const normalizeTf = (t) => t.toLowerCase().trim();

                if (msg.symbol === currentSym && normalizeTf(msg.tf) === normalizeTf(currentTfRaw)) {

                    // [ANTIGRAVITY FIX] Filter by provider if present (avoids flickering)
                    // If msg.provider is set, we could filter here.
                    // For now, we rely on the backend only sending routed data.

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
                    console.log("[UI-DEBUG] Parsed profile from state sync:", data.profile);
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
                if (data.symbols && Array.isArray(data.symbols) && data.symbols.length > 0) {
                    console.log("Updating WATCHED_SYMBOLS:", data.symbols);
                    // Update the global WATCHED_SYMBOLS list
                    WATCHED_SYMBOLS.splice(0, WATCHED_SYMBOLS.length, ...data.symbols);

                    // Update current index to point to current label, or reset if missing
                    const currentSym = document.getElementById('chart-symbol-label')?.innerText;
                    const newIdx = WATCHED_SYMBOLS.indexOf(currentSym);
                    if (newIdx !== -1) {
                        currentSymbolIndex = newIdx;
                    } else {
                        // Current symbol is no longer in the set, switch to first available
                        currentSymbolIndex = 0;
                        updateSymbolDisplay();
                    }
                }
                saveState();
            } else if (msg.type === 'ai_commentary') {
                // [ANTIGRAVITY] AI Commentary: Update the insight panel
                console.log("AI Commentary received:", msg.content?.substring(0, 50) + "...");
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

function addDecisionRow(symbol, action, scoreNum, reason, forcedGrade = null) {
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
    const grade = forcedGrade || getScoreGrade(scoreNum);
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
window.api.on('env-updated', (updates) => {
    console.log("[UI] Environment updated:", updates);
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

            const actionMatch = body.match(/action=([^\s|]+)/i) || body.match(/gate=([^\s|]+)/i) || body.match(/Switched to\s+([^\s|]+)/i);
            if (actionMatch) action = actionMatch[1].toUpperCase().replace("STAND_ASIDE", "HOLD").replace("SWEEP", "HOLD");

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

    // [ANTIGRAVITY FIX] Strict Capital Logic
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

    let capVal = null;

    // 1. [TOTAL] Source (Aggregated by RoutedExchangeBroker - Highest Priority)
    if (line.includes('[TOTAL] Liquidity available:')) {
        const totalMatch = line.match(/available: \$([\d\.,\-]+)/);
        if (totalMatch) {
            capVal = parseFloat(totalMatch[1].replace(/,/g, ''));
        }
    }
    // 2. [HEARTBEAT] Source (Aggregated, generally trusted)
    else if (line.includes('[HEARTBEAT] Capital available:')) {
        const hbMatch = line.match(/Capital available: \$([\d\.,\-]+)/);
        if (hbMatch) {
            capVal = parseFloat(hbMatch[1].replace(/,/g, ''));
        }
    }
    // 3. Fallbacks for individual reports (respect profile context to avoid flip-flopping)
    // [ANTIGRAVITY] Actually, we remove OANDA/CCXT individual parsers here because they cause
    // flip-flopping in multi-broker setups. [TOTAL] and [HEARTBEAT] are authoritative.

    if (capVal !== null) {
        const capitalEl = document.getElementById('account-capital');
        if (capitalEl) {
            capitalEl.innerText = capVal.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
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

        // [ANTIGRAVITY] User Request: Wipe Decision/Commentary panels on boot
        // We do strictly NOT restore: decisions, commentary, holdings (HTML tables)
        // if (state.decisions) document.getElementById('decisions-table').innerHTML = state.decisions;
        // if (state.commentary) document.getElementById('commentary-content').innerText = state.commentary;
        // if (state.holdings) document.getElementById('holdings-table-body').innerHTML = state.holdings;
        document.getElementById('decisions-table').innerHTML = '';
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

    const STRATEGY_OPTIONS = [
        { value: 'rubberband_reaper', label: 'Rubberband Reaper' },
        { value: 'robocop', label: 'RoboCop' },
        { value: 'quantum', label: 'Quantum' },
        { value: 'evolution', label: 'Evolution' },
        { value: 'mean_reversion', label: 'Mean Reversion' },
        { value: 'hyper_scalper', label: 'Hyper Scalper' },
        { value: 'volatility_breakout', label: 'Volatility Breakout' },
        { value: 'aggregator', label: 'Aggregator' },
        { value: 'supply_demand', label: 'Supply & Demand' },
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
