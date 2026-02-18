/**
 * log_parser.js — Log formatting, display, and parsing logic.
 *
 * Exposes window.LogParser = { formatLogMessage, appendLog, parseLogLine }
 * Loaded before renderer.js so delegates can be wired.
 */
(function () {
    'use strict';

    /**
     * formatLogMessage — colourises log tags and trade keywords.
     */
    function formatLogMessage(msg) {
        let formatted = msg;
        // Strip timestamps like [10:00:00] or 2024-01-01 10:00:00
        formatted = formatted.replace(/^\[\d{2}:\d{2}:\d{2}\]\s*/, "");
        formatted = formatted.replace(/^\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}[,.]\d+\s*/, "");

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
        formatted = formatted.replace(/(\$\s?[\d.,]+)/g, '<span class="text-teal-400">$1</span>');

        return formatted;
    }

    /**
     * appendLog — appends a formatted log line to the terminal element.
     */
    let _logTerminal = null;
    function appendLog(level, rawMessage) {
        if (!_logTerminal) {
            _logTerminal = document.getElementById('log-terminal');
            if (!_logTerminal) return;
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

        _logTerminal.appendChild(div);
        if (_logTerminal.children.length > 300) _logTerminal.removeChild(_logTerminal.firstChild);
        _logTerminal.scrollTop = _logTerminal.scrollHeight;
    }

    /**
     * parseLogLine — parses a single log line and updates GUI state.
     *
     * Relies on renderer.js globals at call-time:
     *   parseLogTimestamp, tfToSeconds, utcToLocal, addExitMarker, addTradeMarker,
     *   addDecisionRow, updateHoldingsTable, upsertHoldingRow, saveState,
     *   indicatorSeries, capitalDisplayMode, statusProfile, chartMode, pnlTimeframe, etc.
     */
    function parseLogLine(line) {
        if (!line) return;

        // If the log line is structured JSON, extract the message field cleanly
        if (line.trimStart().startsWith('{')) {
            try {
                const parsed = JSON.parse(line);
                if (parsed.message) line = parsed.message;
            } catch (_) { /* Not valid JSON, fall through with raw line */ }
        }

        // Check for EXIT logs to trigger PnL refresh and add exit marker
        if (line.includes('[EXIT]')) {
            setTimeout(() => { if (window.updateRealizedPnL) window.updateRealizedPnL(); }, 1000);

            const symbolMatch = line.match(/\[EXIT\][^:]*:\s*([A-Z0-9_]+)/i) || line.match(/\[EXIT\]\s+([A-Z0-9_]+)/i);
            const pnlMatch = line.match(/([+-]?\$[\d.]+)/);
            const pctMatch = line.match(/Pct=([+-]?[\d.]+)%?/i);

            if (symbolMatch) {
                symbolMatch[1] = symbolMatch[1].replace(/_/g, '');
                let logTime = parseLogTimestamp(line);
                const tfRaw = (document.getElementById('chart-tf-label')?.innerText || '15m').trim();
                const interval = tfToSeconds(tfRaw);

                const snappedTime = Math.floor(logTime / interval) * interval;
                logTime = snappedTime - interval;

                const pnlPct = pctMatch ? parseFloat(pctMatch[1]) : null;
                const isWin = pnlMatch ? pnlMatch[1].startsWith('+') : (pnlPct !== null && pnlPct >= 0);
                const priceFromPnl = pnlMatch ? Math.abs(parseFloat(pnlMatch[1].replace('$', ''))) : null;
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
                const tfRaw = (document.getElementById('chart-tf-label')?.innerText || '15m').trim();
                const interval = tfToSeconds(tfRaw);

                const snappedTime = Math.floor(logTime / interval) * interval;
                logTime = snappedTime - interval;

                const price = priceMatch ? parseFloat(priceMatch[1]) : null;
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

                const parts = content.split('|');
                let head = parts[0].trim();

                let symbol = "UNKNOWN";
                const kvSymbolMatch = content.match(/symbol=([A-Z0-9]+)/i);
                if (kvSymbolMatch) {
                    symbol = kvSymbolMatch[1].toUpperCase();
                } else {
                    const forMatch = content.match(/(?:for|Blocked)\s+([A-Z][A-Z0-9]{2,})/);
                    if (forMatch) {
                        symbol = forMatch[1].toUpperCase();
                    } else {
                        const headMatch = head.match(/^([A-Z0-9]{3,})/);
                        if (headMatch) symbol = headMatch[1];
                    }
                }

                if (symbol === "UNKNOWN") {
                    return;
                }

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
                        action = "HOLD";
                    } else {
                        action = actionMatch[1].toUpperCase().replace("STAND_ASIDE", "HOLD").replace("STAND-ASIDE", "HOLD").replace("SWEEP", "HOLD");
                    }
                }

                if (!actionMatch && body.includes("Decision:") && body.includes("HOLD")) {
                    action = "HOLD";
                }

                const scoreMatch = body.match(/icc_score=([\d.]+)/i) ||
                    body.match(/ICC score\s+([\d.]+)/i) ||
                    body.match(/score=([\d.]+)/i) ||
                    body.match(/selection_score=([\d.]+)/i) ||
                    body.match(/\/(\d+)\s+score/i);

                if (scoreMatch) {
                    let raw = parseFloat(scoreMatch[1]);
                    if (raw > 100) raw = raw / 100;

                    if (raw <= 1.0 && (line.includes('selection_score') || body.includes('selection_score'))) score = raw * 100;
                    else if (raw <= 35.0 && line.includes('/35')) score = (raw / 35.0) * 100;
                    else score = raw;
                }

                const reasonMatch = body.match(/reason=([^|]+)/i) || body.match(/\(([^)]+)\)$/);
                if (reasonMatch) reason = reasonMatch[1].trim();

                const gradeMatch = body.match(/grade=([A-F][+-]?)/i);
                const forcedGrade = gradeMatch ? gradeMatch[1] : null;

                const stratMatch = body.match(/strategy=([^\s|]+)/i);
                const stratGradeMatch = body.match(/strat_grade=([A-F][+-]?)/i);
                const stratName = stratMatch ? stratMatch[1] : null;
                const displayGrade = stratGradeMatch ? stratGradeMatch[1] : forcedGrade;

                addDecisionRow(symbol, action, score, reason, displayGrade, stratName);

                // Chart Indicator
                const headerSym = document.getElementById('chart-symbol-label')?.innerText;
                if (indicatorSeries && symbol === headerSym) {
                    const nowSec = utcToLocal(Math.floor(Date.now() / 1000));

                    let color = '#475569';
                    const act = action.toUpperCase();

                    if (act.includes("LONG") || act.includes("BUY") || act.includes("BIP")) {
                        color = '#2dd4bf';
                    } else if (act.includes("SHORT") || act.includes("SELL")) {
                        color = '#f43f5e';
                    } else if (act === "CLOSE") {
                        color = '#f59e0b';
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
        let isOandaProfile = false;
        const currentProfile = document.getElementById('status-profile')?.innerText?.toLowerCase() || "";
        if (currentProfile.includes("oanda") || currentProfile.includes("forex")) {
            isOandaProfile = true;
        }

        if (!window.capitalCache) window.capitalCache = {};

        // 1. [TOTAL] Source
        if (line.includes('[TOTAL] Liquidity available:')) {
            const totalMatch = line.match(/available: \$([\d.,\-]+)/);
            if (totalMatch) {
                const val = parseFloat(totalMatch[1].replace(/,/g, ''));
                window.capitalCache['TOTAL'] = val;
            }
        }
        // 2. [HEARTBEAT] Source
        else if (line.includes('[HEARTBEAT] Capital available:')) {
            const hbMatch = line.match(/Capital available: \$([\d.,\-]+)/);
            if (hbMatch) {
                const val = parseFloat(hbMatch[1].replace(/,/g, ''));
                window.capitalCache['HEARTBEAT'] = val;
            }
        }
        // 3. Broker Specifics (OANDA/CCXT/IBKR)
        else if (line.includes('[OANDA] Account Summary:')) {
            const oMatch = line.match(/NAV=([\d.,\-]+)/);
            if (oMatch) window.capitalCache['OANDA'] = parseFloat(oMatch[1].replace(/,/g, ''));
        }
        else if (line.includes('[CCXT] get_liquid_capital')) {
            const cMatch = line.match(/winner=\$([\d.,\-]+)/);
            if (cMatch) window.capitalCache['CCXT'] = parseFloat(cMatch[1].replace(/,/g, ''));
        }
        else if (line.includes('[IBKR] Account Summary') || line.includes('TotalCashValue=')) {
            const iMatch = line.match(/TotalCashValue=([\d.,\-]+)/);
            if (iMatch) window.capitalCache['IBKR'] = parseFloat(iMatch[1].replace(/,/g, ''));
        }
        // 4. [CASH] Source
        else if (line.includes('[CASH] Buying Power:')) {
            const cashMatch = line.match(/Power: \$([\d.,\-]+)/);
            if (cashMatch) {
                const val = parseFloat(cashMatch[1].replace(/,/g, ''));
                window.capitalCache['CASH'] = val;
            }
        }

        // Determine the most robust value based on user preference
        let capVal = null;
        let labelText = "Overall Capital:";

        const displayMode = capitalDisplayMode || 'equity';

        if (displayMode === 'cash') {
            labelText = "Buying Power:";
            capVal = window.capitalCache['CASH'];
            if (capVal === undefined || capVal === null) {
                const total = (window.capitalCache['OANDA'] || 0) +
                    (window.capitalCache['CCXT'] || 0) +
                    (window.capitalCache['IBKR'] || 0);
                if (total > 0) capVal = total;
            }
        } else {
            labelText = "Overall Capital:";
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
                const stateMatch = line.match(/\[STATE\]\s+(\w+)\s+open_position:\s+(\w+)/);
                if (stateMatch) {
                    upsertHoldingRow(stateMatch[1], stateMatch[2]);
                    saveState();
                }
            }
        }
    }

    // Expose on window (renderer context) or module.exports (Node/main context)
    if (typeof window !== 'undefined') {
        window.LogParser = {
            formatLogMessage,
            appendLog,
            parseLogLine,
        };
    }
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = {
            formatLogMessage,
            appendLog,
            parseLogLine,
        };
    }
})();

