/**
 * log_analytics.js — Node.js-only analytics functions for the main process.
 *
 * Parses log files and the paper ledger from disk to produce trade history,
 * capital snapshots, and aggregate metrics for the analytics panel.
 *
 * Consumed by main.js IPC handlers:
 *   - get-trade-history  → getTradeHistory(filter)
 *   - get-analytics-summary → getTradeHistory(filter) + calculateAnalyticsSummary(data)
 *   - get-log-files → getLogFiles()
 */
'use strict';

const fs = require('fs');
const path = require('path');
const os = require('os');

// ── Resolve user data directory (mirrors Python paths.py + tradebot.sh) ──
const _APP_ROOT = path.join(__dirname, '..', '..', '..');
function _resolveUserDataDir() {
    if (process.env.TRADEBOT_DATA_DIR) return process.env.TRADEBOT_DATA_DIR;
    if (process.platform === 'darwin') return path.join(os.homedir(), 'Library', 'Application Support', 'tradebot-sci');
    return path.join(process.env.XDG_CONFIG_HOME || path.join(os.homedir(), '.config'), 'tradebot-sci');
}
const USER_DATA_DIR = _resolveUserDataDir();

// Primary: user data dir (where the daemon writes); Fallback: project root (legacy/dev)
const LOGS_DIR = fs.existsSync(path.join(USER_DATA_DIR, 'logs')) ? path.join(USER_DATA_DIR, 'logs') : path.join(_APP_ROOT, 'logs');
const DATA_DIR = fs.existsSync(path.join(USER_DATA_DIR, 'data')) ? path.join(USER_DATA_DIR, 'data') : path.join(_APP_ROOT, 'data');

// ── Helpers ──────────────────────────────────────────────

function _getCutoffTime(filter) {
    const now = new Date();
    switch (filter) {
        case '1h': return new Date(now - 60 * 60 * 1000);
        case '4h': return new Date(now - 4 * 60 * 60 * 1000);
        case '24h': return new Date(now - 24 * 60 * 60 * 1000);
        case 'week': return new Date(now - 7 * 24 * 60 * 60 * 1000);
        case 'month': return new Date(now - 30 * 24 * 60 * 60 * 1000);
        case 'year': return new Date(now - 365 * 24 * 60 * 60 * 1000);
        case 'all': return new Date(0);
        default: return new Date(now - 24 * 60 * 60 * 1000);
    }
}

function _extractTimestamp(line) {
    const m = line.match(/(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})/);
    return m ? new Date(m[1]) : null;
}

function _latestByBroker(capitalByBroker) {
    const result = {};
    for (const [broker, entries] of Object.entries(capitalByBroker)) {
        if (entries.length > 0) {
            const sorted = entries.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
            result[broker] = sorted[0].nav;
        }
    }
    return result;
}

// ── Public API ──────────────────────────────────────────

/**
 * getLogFiles — returns a list of available log files, newest first.
 */
function getLogFiles() {
    const files = [];
    const seenInodes = new Set();

    // Scan both user-data logs and project-root logs
    const logDirs = [LOGS_DIR, path.join(_APP_ROOT, 'logs')].filter(d => fs.existsSync(d));
    for (const dir of logDirs) {
        // Include tradebot.log* AND bot_stdout.log (launcher redirects stdout there)
        const entries = fs.readdirSync(dir)
            .filter(f => f.startsWith('tradebot.log') || f === 'bot_stdout.log')
            .sort((a, b) => {
                // bot_stdout.log gets priority 0 (newest), tradebot.log = 1, rotated = 2+
                const numA = a === 'bot_stdout.log' ? 0 : a === 'tradebot.log' ? 1 : (parseInt(a.split('.').pop()) || 999) + 1;
                const numB = b === 'bot_stdout.log' ? 0 : b === 'tradebot.log' ? 1 : (parseInt(b.split('.').pop()) || 999) + 1;
                return numA - numB;
            });

        for (const name of entries) {
            const fullPath = path.join(dir, name);
            try {
                const stat = fs.statSync(fullPath);
                if (seenInodes.has(stat.ino)) continue;  // skip hardlinks/same file
                seenInodes.add(stat.ino);
                files.push({ name, path: fullPath, size: stat.size, modified: stat.mtime });
            } catch (_) { /* skip unreadable */ }
        }
    }
    return files;
}

/**
 * getTradeHistory — parse log files + ledger for trade data.
 * @param {string} filter — '1h', '4h', '24h', 'week', 'month', 'year', 'all'
 * @returns {{ trades: Array, capital: Array, capitalByBroker: Object }}
 */
function getTradeHistory(filter = '24h', paperMode = false) {
    // In paper mode, replay trades use candle timestamps (e.g., 2026-02-18)
    // which don't match wall-clock time. Use 'all' to include them.
    const effectiveFilter = paperMode ? 'all' : filter;
    const cutoff = _getCutoffTime(effectiveFilter);
    let trades = [];
    const capital = [];
    const capitalByBroker = {};

    // 1. Read from ledger — paper mode uses paper_ledger exclusively
    const liveLedgerPath = path.join(DATA_DIR, 'ledger.json');
    const paperLedgerPath = path.join(DATA_DIR, 'paper_ledger.json');
    const ledgerPath = paperMode ? paperLedgerPath : (fs.existsSync(liveLedgerPath) ? liveLedgerPath : paperLedgerPath);
    let ledger = null;
    let fallbackGlobalCutoff = cutoff; // We enhance the cutoff timestamp if there has been a paper reset
    if (fs.existsSync(ledgerPath)) {
        try {
            ledger = JSON.parse(fs.readFileSync(ledgerPath, 'utf8'));
            if (paperMode && ledger.last_reset_at) {
                const resetTime = new Date(ledger.last_reset_at);
                if (resetTime > fallbackGlobalCutoff) {
                    fallbackGlobalCutoff = resetTime;
                }
            }
        } catch (_) { /* corrupted ledger */ }
    }
    
    // Also check paper_state.json as an additional safety
    if (paperMode) {
        const paperStatePath = path.join(DATA_DIR, 'paper_state.json');
        if (fs.existsSync(paperStatePath)) {
            try {
                const state = JSON.parse(fs.readFileSync(paperStatePath, 'utf8'));
                if (state.last_reset_at) {
                    const resetTime = new Date(state.last_reset_at);
                    if (resetTime > fallbackGlobalCutoff) {
                        fallbackGlobalCutoff = resetTime;
                    }
                }
            } catch (_) { }
        }
    }

    if (ledger) {
        // Current day trades
        if (ledger.current_day?.trade_log) {
            for (const t of ledger.current_day.trade_log) {
                const ts = t.closed_at || t.timestamp || t.time;
                if (ts && new Date(ts) >= fallbackGlobalCutoff) {
                    trades.push(t);
                }
            }
        }

        // Historical days
        if (ledger.days) {
            for (const day of ledger.days) {
                if (day.trade_log) {
                    for (const t of day.trade_log) {
                        const ts = t.closed_at || t.timestamp || t.time;
                        if (ts && new Date(ts) >= fallbackGlobalCutoff) {
                            trades.push(t);
                        }
                    }
                }
                if (day.day_start && new Date(day.day_start) >= fallbackGlobalCutoff) {
                    capital.push({
                        timestamp: day.day_start,
                        nav: day.capital_at_start || day.capital_now,
                        balance: day.capital_at_start || day.capital_now,
                        broker: 'all'
                    });
                }
            }
        }

        // Current day capital
        if (ledger.current_day) {
            const currentDayTimestamp = ledger.current_day.day_start || new Date().toISOString();
            
            // 1) Push the starting capital at the beginning of the day to baseline trades
            if (ledger.current_day.capital_at_start) {
                capital.push({
                    timestamp: currentDayTimestamp,
                    nav: ledger.current_day.capital_at_start,
                    balance: ledger.current_day.capital_at_start,
                    broker: 'all'
                });
            }
            
            // 2) Push the live floating capital at its true chronological time so it doesn't cause
            //    artificial cashout anomalies when compared against recent trade PnLs
            if (ledger.current_day.capital_now) {
                const ts = ledger.last_updated || new Date().toISOString();
                capital.push({
                    timestamp: ts,
                    nav: ledger.current_day.capital_now,
                    balance: ledger.current_day.capital_now,
                    broker: 'all'
                });
            }
        }
    }

    // 2. Read from trade_results.json (live) or paper_trade_results.json (paper)
    const resultsFile = paperMode ? 'paper_trade_results.json' : 'trade_results.json';
    const resultsPath = path.join(DATA_DIR, resultsFile);
    if (fs.existsSync(resultsPath)) {
        try {
            const results = JSON.parse(fs.readFileSync(resultsPath, 'utf8'));
            if (Array.isArray(results)) {
                for (const t of results) {
                    const ts = t.closed_at || t.timestamp;
                    if (ts && new Date(ts) >= fallbackGlobalCutoff) {
                        const tsTime = new Date(ts).getTime();
                        const isDupe = trades.some(existing => {
                            if (existing.symbol !== t.symbol) return false;
                            const existingTs = existing.closed_at || existing.timestamp || existing.time || 0;
                            return Math.abs(new Date(existingTs).getTime() - tsTime) < 5000;
                        });
                        if (!isDupe) {
                            // Normalize field names: trade_results.json uses
                            // pnl_usd/pnl_pct/exit_reason, analytics expects pnl/pct/reason
                            const pnlVal = t.pnl ?? t.pnl_usd ?? 0;
                            const exitReason = t.exit_reason || t.reason || '';

                            // Extract strategy from exit_reason when strategy is 'unknown'
                            // e.g. "[Conductor:trend_rider] ..." → "trend_rider"
                            let strategy = t.strategy || 'unknown';
                            if (strategy === 'unknown' && exitReason) {
                                const stratMatch = exitReason.match(/\[Conductor:(\w+)\]/);
                                if (stratMatch) {
                                    strategy = stratMatch[1];
                                } else if (exitReason.includes('sl_tp_hit')) {
                                    strategy = 'forex_conductor';
                                } else if (exitReason.includes('Regime Flip')) {
                                    strategy = 'regime_flip';
                                }
                            }

                            // Compute pnl_pct from capital if missing/zero
                            let pctVal = t.pct ?? t.pnl_pct ?? 0;
                            if (pctVal === 0 && pnlVal !== 0 && t.capital_at_close) {
                                const capitalBefore = t.capital_at_close - pnlVal;
                                if (capitalBefore > 0) {
                                    pctVal = (pnlVal / capitalBefore) * 100;
                                }
                            }

                            trades.push({
                                ...t,
                                pnl: pnlVal,
                                pct: pctVal,
                                reason: exitReason,
                                strategy,
                                spread: t.spread ?? t.spread_cost ?? 0,
                                timestamp: ts,
                                _source: 'trade_results',
                            });
                        }
                    }
                }
            }
        } catch (_) { /* empty or corrupted */ }
    }

    // 3. Parse log files for capital snapshots + EXIT trades (fallback)
    const RE_EXIT = /\[EXIT\]\s+([^:]+):\s+([A-Z_]{3,10})\s+([+-])\$?([\d.]+)(?:\s+\(Pct=([+-]?[\d.]+)%\))?(?:.*?position=(\w+))?(?:.*?Duration=([\w\s]+?)(?:\s*\||$))?(?:.*?Est\.\s*Spread\s*Cost:\s*\$([\d.]+))?/;
    const RE_STRATEGY = /Tournament Won by\s+(\w+)/;
    let lastStrategy = '';
    const seenExitLines = new Set();  // Cross-file dedup: track normalized EXIT line content
    const logFiles = !paperMode ? getLogFiles() : []; 
    for (const logFile of logFiles) {
        try {
            const content = fs.readFileSync(logFile.path, 'utf8');
            const lines = content.split('\n');
            for (let line of lines) {
                // Normalize JSON-formatted log lines (project root uses {"timestamp":..., "message":...})
                if (line.startsWith('{') && line.includes('"message"')) {
                    try {
                        const j = JSON.parse(line);
                        line = (j.timestamp || '') + ' ' + (j.message || '');
                    } catch (_) { /* not valid JSON, use as-is */ }
                }

                // Track strategy from META-SCI tournament lines
                const stratMatch = line.match(RE_STRATEGY);
                if (stratMatch) lastStrategy = stratMatch[1];

                if (line.includes('[HEARTBEAT] Capital available:') ||
                    line.includes('[TOTAL] Liquidity available:')) {
                    const ts = _extractTimestamp(line);
                    if (ts && ts >= fallbackGlobalCutoff) {
                        const valMatch = line.match(/(?:available|Liquidity available): \$([\d.,]+)/);
                        if (valMatch) {
                            capital.push({
                                timestamp: ts.toISOString(),
                                nav: parseFloat(valMatch[1].replace(/,/g, '')),
                                broker: 'all'
                            });
                        }
                    }
                }

                if (line.includes('[OANDA] Account Summary:')) {
                    const ts = _extractTimestamp(line);
                    if (ts && ts >= fallbackGlobalCutoff) {
                        const m = line.match(/NAV=([\d.,]+)/);
                        if (m) {
                            const entry = { timestamp: ts.toISOString(), nav: parseFloat(m[1].replace(/,/g, '')), broker: 'oanda' };
                            capital.push(entry);
                            if (!capitalByBroker.oanda) capitalByBroker.oanda = [];
                            capitalByBroker.oanda.push(entry);
                        }
                    }
                }

                if (line.includes('[CCXT] get_liquid_capital')) {
                    const ts = _extractTimestamp(line);
                    if (ts && ts >= fallbackGlobalCutoff) {
                        const m = line.match(/winner=\$([\d.,]+)/);
                        if (m) {
                            const entry = { timestamp: ts.toISOString(), nav: parseFloat(m[1].replace(/,/g, '')), broker: 'ccxt' };
                            capital.push(entry);
                            if (!capitalByBroker.ccxt) capitalByBroker.ccxt = [];
                            capitalByBroker.ccxt.push(entry);
                        }
                    }
                }

                // Parse [EXIT] lines for trade records (fallback when ledger trade_log is empty)
                if (line.includes('[EXIT]')) {
                    const ts = _extractTimestamp(line);
                    if (ts && ts >= fallbackGlobalCutoff) {
                        const m = RE_EXIT.exec(line);
                        if (m) {
                            // m[3] is the sign block (+/-), m[4] is the actual sign character, m[5] is the PnL amount string (e.g. 1,947.00)
                            const pnlStr = (m[5] || '0').replace(/,/g, '');
                            const pnlVal = parseFloat(pnlStr) * (m[4] === '-' ? -1 : 1);
                            const symbol = m[2];
                            const closedAt = ts.toISOString();

                            // Cross-file dedup: use the EXIT portion of the line as a fingerprint.
                            // Same EXIT text across files = duplicate (same line in bot_stdout.log
                            // and tradebot.log). Different EXIT text in same file = distinct fills.
                            const exitFingerprint = line.substring(line.indexOf('[EXIT]'));
                            if (seenExitLines.has(exitFingerprint)) continue;
                            seenExitLines.add(exitFingerprint);

                            // Also deduplicate against ledger-sourced trades
                            const isDupe = trades.some(existing =>
                                existing._source !== 'log' &&
                                existing.symbol === symbol &&
                                // Dupe if within 5 mins (300000ms) or exact same PnL and direction
                                (Math.abs(new Date(existing.closed_at || existing.timestamp || existing.time || 0) - ts) < 300000)
                            );
                            if (!isDupe) {
                                trades.push({
                                    symbol,
                                    pnl: pnlVal,
                                    pct: m[5] ? parseFloat(m[5]) : 0,
                                    side: (m[6] || 'unknown').toLowerCase(),
                                    reason: (m[1] || '').trim(),
                                    strategy: lastStrategy || 'unknown',
                                    spread: m[8] ? parseFloat(m[8]) : 0,
                                    duration: m[7] ? m[7].trim() : null,
                                    closed_at: closedAt,
                                    timestamp: closedAt,
                                    _source: 'log',
                                });
                            }
                        }
                    }
                }
            }
        } catch (_) { /* unreadable log file */ }
    }

    // Sort trades newest first
    trades.sort((a, b) => {
        const ta = new Date(b.closed_at || b.timestamp || 0);
        const tb = new Date(a.closed_at || a.timestamp || 0);
        return ta - tb;
    });

    // Also include active positions — paper mode only shows paper positions
    const positionSources = paperMode
        ? [{ file: 'paper_state.json', key: 'positions' }]
        : [
            { file: 'paper_state.json', key: 'positions' },
            { file: 'oanda_tracked_positions.json', key: null },  // top-level object of symbol->position
            { file: 'position_holds.json', key: null, isArray: true },  // CCXT position hold store
        ];
    for (const src of positionSources) {
        const posPath = path.join(DATA_DIR, src.file);
        if (fs.existsSync(posPath)) {
            try {
                const raw = JSON.parse(fs.readFileSync(posPath, 'utf8'));
                let entries = []; // Normalize to array of [symbol, posData]

                if (src.isArray && Array.isArray(raw)) {
                    // position_holds.json: array of {symbol, ...}
                    for (const pos of raw) {
                        if (pos.symbol && pos.size && Math.abs(parseFloat(pos.size)) > 0) entries.push([pos.symbol, pos]);
                    }
                } else {
                    const positions = src.key ? (raw[src.key] || {}) : raw;
                    if (positions && typeof positions === 'object' && !Array.isArray(positions)) {
                        entries = Object.entries(positions);
                    }
                }

                for (const [symbol, pos] of entries) {
                    // Skip if already present as active
                    if (trades.some(t => t._active && t.symbol === symbol)) continue;
                    // Compute PnL % from available data if not stored
                    const _upnl = pos.unrealized_pnl || 0;
                    const _entry = pos.entry_price || pos.avg_price || 0;
                    const _size = Math.abs(pos.size || 0);
                    const _pctCalc = (_entry && _size) ? (_upnl / (_entry * _size)) * 100 : 0;
                    trades.unshift({
                        symbol,
                        side: pos.side || pos.direction || 'long',
                        pnl: _upnl,
                        pct: pos.pnl_pct || _pctCalc,
                        timestamp: pos.opened_at || pos.entry_time || (raw.updated_at || ''),
                        strategy: pos.strategy || '--',
                        stop_loss: pos.stop_loss,
                        take_profit: pos.take_profit,
                        entry_price: _entry,
                        size: pos.size,
                        _active: true
                    });
                }
            } catch (_) { /* ignore */ }
        }
    }

    // Fallback: Parse last [HOLDINGS] heartbeat from bot_stdout.log for live CCXT and OANDA positions
    // This captures positions (like DOGE) that aren't in any static JSON file
    // AND it acts as the authoritative source to prune ghost static states.
    if (true) { // Always run this, even in paperMode, because paperMode relies on [HOLDINGS] too
        const stdoutPath = path.join(LOGS_DIR, 'bot_stdout.log');
        if (fs.existsSync(stdoutPath)) {
            try {
                // Read last 50KB to find the most recent [HOLDINGS] line
                const stat = fs.statSync(stdoutPath);
                const readSize = Math.min(stat.size, 50000);
                const fd = fs.openSync(stdoutPath, 'r');
                const buf = Buffer.alloc(readSize);
                fs.readSync(fd, buf, 0, readSize, stat.size - readSize);
                fs.closeSync(fd);
                const tail = buf.toString('utf8');
                const holdingsLines = tail.split('\n').filter(l => l.includes('[HOLDINGS]'));
                if (holdingsLines.length > 0) {
                    const lastLine = holdingsLines[holdingsLines.length - 1];
                    const jsonPart = lastLine.split(/\[HOLDINGS\]/i)[1].trim();
                    const holdingsData = JSON.parse(jsonPart);
                    
                    // Create a set of authoritative live symbols (empty if no positions)
                    const liveList = Array.isArray(holdingsData.positions) ? holdingsData.positions : [];
                    const liveSymbols = new Set(liveList.map(p => p.symbol));

                    // Prune any trades previously marked as active from static files 
                    // that do not appear in the live authoritative payload
                    trades = trades.filter(t => !t._active || liveSymbols.has(t.symbol));

                    for (const pos of liveList) {
                        if (!pos.symbol) continue;

                        const _upnl = pos.unrealized_pnl || 0;
                        const _entry = pos.entry_price || pos.avg_price || 0;
                        const _size = Math.abs(pos.size || 0);
                        const _pctCalc = (_entry && _size) ? (_upnl / (_entry * _size)) * 100 : 0;

                        const freshPos = {
                            symbol: pos.symbol,
                            side: pos.side || pos.direction || 'long',
                            pnl: _upnl,
                            pct: pos.pnl_pct || _pctCalc,
                            timestamp: pos.opened_at || pos.entry_time || '',
                            strategy: pos.strategy || '--',
                            stop_loss: pos.stop_loss,
                            take_profit: pos.take_profit,
                            entry_price: _entry,
                            size: pos.size,
                            duration_seconds: pos.age_seconds,
                            _active: true
                        };

                        const existingIdx = trades.findIndex(t => t._active && t.symbol === pos.symbol);
                        if (existingIdx !== -1) {
                            // Overlay fresh data on top of static data (updates real-time PnL and pyramided sizes)
                            trades[existingIdx] = { ...trades[existingIdx], ...freshPos };
                        } else {
                            trades.unshift(freshPos);
                        }
                    }
                }
            } catch (_) { /* ignore heartbeat parse errors */ }
        }

        // --- HARD PRUNE GHOST POSITIONS ---
        // Second pass: Re-read the last [HOLDINGS] line and forcibly delete any `_active` static trade 
        // (like AUDUSD from paper_state.json) that the live bot is no longer tracking.
        try {
            if (fs.existsSync(stdoutPath)) {
                const stat = fs.statSync(stdoutPath);
                const readSize = Math.min(stat.size, 50000);
                const fd = fs.openSync(stdoutPath, 'r');
                const buf = Buffer.alloc(readSize);
                fs.readSync(fd, buf, 0, readSize, stat.size - readSize);
                fs.closeSync(fd);
                const holdingsLines = buf.toString('utf8').split('\n').filter(l => l.includes('[HOLDINGS]'));
                if (holdingsLines.length > 0) {
                    const lastLine = holdingsLines[holdingsLines.length - 1];
                    const jsonPart = lastLine.split(/\[HOLDINGS\]/i)[1].trim();
                    const holdingsData = JSON.parse(jsonPart);
                    const liveList = Array.isArray(holdingsData.positions) ? holdingsData.positions : [];
                    const liveSymbols = new Set(liveList.map(p => p.symbol));
                    trades = trades.filter(t => !t._active || liveSymbols.has(t.symbol));
                }
            }
        } catch (e) { console.error("HARD PRUNE ERROR", e); }
    }

    // Collect ledger by_symbol and by_strategy aggregate data as fallback
    let ledgerBySymbol = {};
    let ledgerByStrategy = {};
    if (ledger) {
        // Merge from all days + current_day
        const allDays = [...(ledger.days || []), ledger.current_day].filter(Boolean);
        for (const day of allDays) {
            const dayStart = day.day_start ? new Date(day.day_start) : null;
            // Only include days within the filter cutoff
            if (dayStart && dayStart < fallbackGlobalCutoff) continue;
            for (const [sym, stats] of Object.entries(day.by_symbol || {})) {
                if (!ledgerBySymbol[sym]) ledgerBySymbol[sym] = { trades: 0, wins: 0, losses: 0, pnl: 0 };
                ledgerBySymbol[sym].trades += stats.trades || 0;
                ledgerBySymbol[sym].wins += stats.wins || 0;
                ledgerBySymbol[sym].losses += stats.losses || 0;
                ledgerBySymbol[sym].pnl += stats.pnl || 0;
            }
            for (const [strat, stats] of Object.entries(day.by_strategy || {})) {
                if (!ledgerByStrategy[strat]) ledgerByStrategy[strat] = { wins: 0, losses: 0, pnl: 0 };
                ledgerByStrategy[strat].wins += stats.wins || 0;
                ledgerByStrategy[strat].losses += stats.losses || 0;
                ledgerByStrategy[strat].pnl += stats.pnl || 0;
            }
        }
    }

    return { trades, capital, capitalByBroker, ledgerBySymbol, ledgerByStrategy };
}

/**
 * calculateAnalyticsSummary — aggregate metrics from trade data.
 * @param {{ trades: Array, capital: Array, capitalByBroker: Object }} data
 * @returns {Object} summary with all metrics the analytics panel needs
 */
function calculateAnalyticsSummary(data, paperMode = false) {
    const { trades = [], capital = [], capitalByBroker = {}, ledgerBySymbol = {}, ledgerByStrategy = {} } = data;
    const closed = trades.filter(t => !t._active);

    let totalPnl = 0, grossProfit = 0, grossLoss = 0;
    let wins = 0, losses = 0, breakeven = 0;
    let bestTrade = 0, worstTrade = 0;
    let totalSpread = 0;
    const symbolStats = {};
    const strategyStats = {};
    const winPnls = [];
    const lossPnls = [];

    for (const t of closed) {
        const pnl = parseFloat(t.pnl) || 0;
        totalPnl += pnl;
        totalSpread += parseFloat(t.spread || t.spread_cost || 0);

        if (pnl > 0.001) {
            wins++;
            grossProfit += pnl;
            winPnls.push(pnl);
            if (pnl > bestTrade) bestTrade = pnl;
        } else if (pnl < -0.001) {
            losses++;
            grossLoss += Math.abs(pnl);
            lossPnls.push(pnl);
            if (pnl < worstTrade) worstTrade = pnl;
        } else {
            breakeven++;
        }

        const sym = t.symbol || 'UNKNOWN';
        if (!symbolStats[sym]) symbolStats[sym] = { trades: 0, wins: 0, losses: 0, pnl: 0 };
        symbolStats[sym].trades++;
        symbolStats[sym].pnl += pnl;
        if (pnl > 0) symbolStats[sym].wins++;
        else if (pnl < 0) symbolStats[sym].losses++;

        const strat = t.strategy || 'unknown';
        if (!strategyStats[strat]) strategyStats[strat] = { wins: 0, losses: 0, pnl: 0 };
        strategyStats[strat].pnl += pnl;
        if (pnl > 0) strategyStats[strat].wins++;
        else if (pnl < 0) strategyStats[strat].losses++;
    }

    const totalTrades = closed.length;
    const winRate = totalTrades > 0 ? ((wins / totalTrades) * 100).toFixed(1) : 0;
    const avgWin = winPnls.length > 0 ? winPnls.reduce((a, b) => a + b, 0) / winPnls.length : 0;
    const avgLoss = lossPnls.length > 0 ? lossPnls.reduce((a, b) => a + b, 0) / lossPnls.length : 0;
    const profitFactor = grossLoss > 0 ? (grossProfit / grossLoss).toFixed(2) : grossProfit > 0 ? 'Inf' : 'N/A';
    const riskReward = avgLoss !== 0 ? Math.abs(avgWin / avgLoss).toFixed(2) : 'N/A';

    const sortedCapital = capital
        .filter(c => c.nav || c.balance)
        .sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
    const capitalStart = sortedCapital.length > 0 ? (sortedCapital[0].nav || sortedCapital[0].balance) : 0;
    const capitalEnd = sortedCapital.length > 0 ? (sortedCapital[sortedCapital.length - 1].nav || sortedCapital[sortedCapital.length - 1].balance) : 0;
    const capitalChange = capitalEnd - capitalStart;
    const capitalChangePct = capitalStart > 0 ? ((capitalChange / capitalStart) * 100).toFixed(1) : 0;

    // ── Cashout & Active PnL Detection ──
    // In paper mode, there are no real cashouts/deposits — capital drops are
    // entirely from trade losses.  The cashout heuristic (diff > $100) was
    // incorrectly rebasing activePnl to $0, which is why the "TOTAL PNL"
    // hero card showed $0.00 despite thousands in losses.
    let activeCapitalStart = capitalStart; 
    let activePnl = totalPnl;  // Default: just use the raw sum
    let totalWithdrawn = 0;

    if (!paperMode) {
        // Live mode: Merge trades and capital snapshots to detect real cash-outs
        const events = [];
        for (const t of closed) {
            if (t.closed_at || t.timestamp) {
                events.push({ time: new Date(t.closed_at || t.timestamp).getTime(), type: 'trade', pnl: parseFloat(t.pnl) || 0 });
            }
        }
        for (const c of sortedCapital) {
            if (c.timestamp && (c.nav || c.balance)) {
                events.push({ time: new Date(c.timestamp).getTime(), type: 'cap', nav: (c.nav || c.balance) });
            }
        }
        events.sort((a, b) => a.time - b.time);

        activePnl = 0;
        let lastKnownNav = capitalStart;

        for (const ev of events) {
            if (ev.type === 'trade') {
                activePnl += ev.pnl;
                lastKnownNav += ev.pnl;
            } else if (ev.type === 'cap') {
                const actualNav = ev.nav;
                const diff = lastKnownNav - actualNav;
                
                if (diff > 100) { 
                    totalWithdrawn += diff;
                    activeCapitalStart = actualNav;
                    activePnl = Math.max(0, activePnl - diff);
                    lastKnownNav = actualNav;
                } else if (diff < -100) {
                    activeCapitalStart += (-diff);
                    lastKnownNav = actualNav;
                } else {
                    lastKnownNav = actualNav;
                }
            }
        }
    }

    return {
        totalPnl: totalPnl.toFixed(2),
        activePnl: activePnl.toFixed(2),
        totalWithdrawn: totalWithdrawn.toFixed(2),
        activeCapitalStart: activeCapitalStart.toFixed(2),
        totalTrades,
        totalWins: wins,
        totalLosses: losses,
        breakeven,
        winRate,
        avgWin: avgWin.toFixed(2),
        avgLoss: avgLoss.toFixed(2),
        bestTrade: bestTrade.toFixed(2),
        worstTrade: worstTrade.toFixed(2),
        profitFactor,
        riskReward,
        grossProfit: grossProfit.toFixed(2),
        grossLoss: grossLoss.toFixed(2),
        spreadCosts: totalSpread.toFixed(2),
        capitalStart: capitalStart.toFixed(2),
        capitalEnd: capitalEnd.toFixed(2),
        capitalChange: capitalChange.toFixed(2),
        capitalChangePct,
        capitalHistory: sortedCapital,
        capitalHistoryByBroker: capitalByBroker,
        capitalByBroker: _latestByBroker(capitalByBroker),
        trades,
        // Merge ledger aggregate data as fallback when trade-derived stats are empty
        symbolStats: Object.keys(symbolStats).length > 0 ? symbolStats : ledgerBySymbol,
        strategyStats: Object.keys(strategyStats).length > 0 ? strategyStats : ledgerByStrategy,
        _source: 'ledger+log'
    };
}

module.exports = {
    getLogFiles,
    getTradeHistory,
    calculateAnalyticsSummary,
};
