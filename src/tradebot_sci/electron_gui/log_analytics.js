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

const LOGS_DIR = path.join(__dirname, '../../../logs');
const DATA_DIR = path.join(__dirname, '../../../data');

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
    if (!fs.existsSync(LOGS_DIR)) return files;

    const entries = fs.readdirSync(LOGS_DIR)
        .filter(f => f.startsWith('tradebot.log'))
        .sort((a, b) => {
            const numA = a === 'tradebot.log' ? 0 : parseInt(a.split('.').pop()) || 999;
            const numB = b === 'tradebot.log' ? 0 : parseInt(b.split('.').pop()) || 999;
            return numA - numB;
        });

    for (const name of entries) {
        const fullPath = path.join(LOGS_DIR, name);
        try {
            const stat = fs.statSync(fullPath);
            files.push({ name, path: fullPath, size: stat.size, modified: stat.mtime });
        } catch (_) { /* skip unreadable */ }
    }
    return files;
}

/**
 * getTradeHistory — parse log files + ledger for trade data.
 * @param {string} filter — '1h', '4h', '24h', 'week', 'month', 'year', 'all'
 * @returns {{ trades: Array, capital: Array, capitalByBroker: Object }}
 */
function getTradeHistory(filter = '24h') {
    const cutoff = _getCutoffTime(filter);
    const trades = [];
    const capital = [];
    const capitalByBroker = {};

    // 1. Read from ledger (live first, paper fallback)
    const liveLedgerPath = path.join(DATA_DIR, 'ledger.json');
    const paperLedgerPath = path.join(DATA_DIR, 'paper_ledger.json');
    const ledgerPath = fs.existsSync(liveLedgerPath) ? liveLedgerPath : paperLedgerPath;
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

    // 3. Parse log files for capital snapshots
    const logFiles = getLogFiles();
    for (const logFile of logFiles) {
        try {
            const content = fs.readFileSync(logFile.path, 'utf8');
            const lines = content.split('\n');
            for (const line of lines) {
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
            }
        } catch (_) { /* unreadable log file */ }
    }

    // Sort trades newest first
    trades.sort((a, b) => {
        const ta = new Date(b.closed_at || b.timestamp || 0);
        const tb = new Date(a.closed_at || a.timestamp || 0);
        return ta - tb;
    });

    // Also include active positions from paper_state.json
    const statePath = path.join(DATA_DIR, 'paper_state.json');
    if (fs.existsSync(statePath)) {
        try {
            const state = JSON.parse(fs.readFileSync(statePath, 'utf8'));
            if (state.positions) {
                for (const [symbol, pos] of Object.entries(state.positions)) {
                    trades.unshift({
                        symbol,
                        side: pos.side || 'long',
                        pnl: pos.unrealized_pnl || 0,
                        pct: pos.pnl_pct || 0,
                        timestamp: pos.opened_at || state.updated_at,
                        strategy: pos.strategy || '--',
                        _active: true
                    });
                }
            }
        } catch (_) { /* ignore */ }
    }

    return { trades, capital, capitalByBroker };
}

/**
 * calculateAnalyticsSummary — aggregate metrics from trade data.
 * @param {{ trades: Array, capital: Array, capitalByBroker: Object }} data
 * @returns {Object} summary with all metrics the analytics panel needs
 */
function calculateAnalyticsSummary(data) {
    const { trades = [], capital = [], capitalByBroker = {} } = data;
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
        symbolStats,
        strategyStats,
        _source: 'ledger+log'
    };
}

module.exports = {
    getLogFiles,
    getTradeHistory,
    calculateAnalyticsSummary,
};
