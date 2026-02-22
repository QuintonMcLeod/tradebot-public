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
    const cutoff = _getCutoffTime(filter);
    const trades = [];
    const capital = [];
    const capitalByBroker = {};

    // 1. Read from ledger — paper mode uses paper_ledger exclusively
    const liveLedgerPath = path.join(DATA_DIR, 'ledger.json');
    const paperLedgerPath = path.join(DATA_DIR, 'paper_ledger.json');
    const ledgerPath = paperMode ? paperLedgerPath : (fs.existsSync(liveLedgerPath) ? liveLedgerPath : paperLedgerPath);
    let ledger = null;
    if (fs.existsSync(ledgerPath)) {
        try {
            ledger = JSON.parse(fs.readFileSync(ledgerPath, 'utf8'));
        } catch (_) { /* corrupted ledger */ }
    }

    if (ledger) {
        // Current day trades
        if (ledger.current_day?.trade_log) {
            for (const t of ledger.current_day.trade_log) {
                const ts = t.closed_at || t.timestamp || t.time;
                if (ts && new Date(ts) >= cutoff) {
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
                        if (ts && new Date(ts) >= cutoff) {
                            trades.push(t);
                        }
                    }
                }
                if (day.day_start) {
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
        if (ledger.current_day?.capital_now) {
            capital.push({
                timestamp: ledger.current_day.day_start || new Date().toISOString(),
                nav: ledger.current_day.capital_now,
                balance: ledger.current_day.capital_now,
                broker: 'all'
            });
        }
    }

    // 2. Read from paper_trade_results.json (backup source)
    const resultsPath = path.join(DATA_DIR, 'paper_trade_results.json');
    if (fs.existsSync(resultsPath)) {
        try {
            const results = JSON.parse(fs.readFileSync(resultsPath, 'utf8'));
            if (Array.isArray(results)) {
                for (const t of results) {
                    const ts = t.closed_at || t.timestamp;
                    if (ts && new Date(ts) >= cutoff) {
                        const isDupe = trades.some(existing =>
                            existing.symbol === t.symbol &&
                            (existing.closed_at || existing.timestamp) === (t.closed_at || t.timestamp)
                        );
                        if (!isDupe) trades.push(t);
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
    const logFiles = getLogFiles();
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
                    if (ts && ts >= cutoff) {
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
                    if (ts && ts >= cutoff) {
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
                    if (ts && ts >= cutoff) {
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
                    if (ts && ts >= cutoff) {
                        const m = RE_EXIT.exec(line);
                        if (m) {
                            const pnlVal = parseFloat(m[4]) * (m[3] === '-' ? -1 : 1);
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
                                Math.abs(new Date(existing.closed_at || existing.timestamp || existing.time || 0) - ts) < 5000
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

    // Fallback: Parse last [HOLDINGS] heartbeat from bot_stdout.log for live CCXT positions
    // This captures positions (like DOGE) that aren't in any static JSON file
    if (!paperMode) {
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
                    if (holdingsData.positions) {
                        for (const pos of holdingsData.positions) {
                            if (!pos.symbol) continue;
                            if (trades.some(t => t._active && t.symbol === pos.symbol)) continue;
                            trades.unshift({
                                symbol: pos.symbol,
                                side: pos.side || pos.direction || 'long',
                                pnl: pos.unrealized_pnl || 0,
                                pct: pos.pnl_pct || 0,
                                timestamp: pos.opened_at || pos.entry_time || '',
                                strategy: pos.strategy || '--',
                                stop_loss: pos.stop_loss,
                                take_profit: pos.take_profit,
                                entry_price: pos.entry_price || pos.avg_price || 0,
                                size: pos.size,
                                _active: true
                            });
                        }
                    }
                }
            } catch (_) { /* ignore heartbeat parse errors */ }
        }
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
            if (dayStart && dayStart < cutoff) continue;
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
function calculateAnalyticsSummary(data) {
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

    return {
        totalPnl: totalPnl.toFixed(2),
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
