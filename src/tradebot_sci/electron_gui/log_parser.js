/**
 * Log Parser Module for Analytics
 * Extracts trade data, capital history, and metrics from bot log files
 */

const fs = require('fs');
const path = require('path');
const readline = require('readline');

const LOGS_DIR = path.join(__dirname, '../../../logs');

/**
 * Parse a timestamp from log line
 * Format: "2026-01-24 10:00:05"
 */
function parseTimestamp(line) {
    const match = line.match(/^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})/);
    if (match) {
        // Logs are local time
        return new Date(match[1].replace(' ', 'T'));
    }
    return null;
}

/**
 * Parse [EXIT] lines for closed trades
 * Example: [EXIT] Chop Scalp triggered: USDCAD +$1.05 (Str=0.00)
 * Example: [EXIT] HTF flip detected: position=SHORT, HTF=long, exiting immediately
 */
function parseExitLine(line, timestamp) {
    const trade = {
        timestamp,
        type: 'exit',
        symbol: null,
        side: null,
        pnl: 0,
        reason: '',
        strategy: null
    };

    // Extract symbol and PnL from "SYMBOL +$X.XX" or "SYMBOL -$X.XX" pattern
    const pnlMatch = line.match(/([A-Z]{3,}(?:USD|JPY|CAD|EUR|GBP|CHF|AUD|NZD)?)\s*([+-]?\$[\d.,]+)/i);
    if (pnlMatch) {
        trade.symbol = pnlMatch[1].toUpperCase();
        const pnlStr = pnlMatch[2].replace(/[$,]/g, '');
        trade.pnl = parseFloat(pnlStr) || 0;
    }

    // Extract Pct if present
    const pctMatch = line.match(/\(Pct=([+-]?[\d.,]+)%\)/i);
    if (pctMatch) {
        trade.pnlPct = parseFloat(pctMatch[1]) || 0;
    }

    // Extract position side
    const sideMatch = line.match(/position=(\w+)/i);
    if (sideMatch) {
        trade.side = sideMatch[1].toLowerCase();
    }

    // Extract reason
    if (line.includes('Chop Scalp')) {
        trade.reason = 'Chop Scalp';
    } else if (line.includes('HTF flip')) {
        trade.reason = 'HTF Flip';
    } else if (line.includes('Structure invalidation')) {
        trade.reason = 'Structure Invalidation';
    } else if (line.includes('Stop Loss')) {
        trade.reason = 'Stop Loss';
    } else if (line.includes('Take Profit')) {
        trade.reason = 'Take Profit';
    } else if (line.includes('Manual/Signal')) {
        trade.reason = 'Manual/Signal';
    } else {
        const reasonMatch = line.match(/\[EXIT\]\s*(.+?)(?::|$)/);
        if (reasonMatch) trade.reason = reasonMatch[1].trim();
    }

    return trade;
}

/**
 * Parse [HOLDINGS] lines for position snapshots
 * Example: [HOLDINGS] {"count": 4, "positions": [...], "total_unrealized_pnl": -0.64}
 */
function parseHoldingsLine(line, timestamp) {
    const jsonMatch = line.match(/\[HOLDINGS\]\s*(\{.+\})/);
    if (!jsonMatch) return null;

    try {
        const data = JSON.parse(jsonMatch[1]);
        return {
            timestamp,
            type: 'holdings',
            count: data.count || 0,
            positions: data.positions || [],
            unrealizedPnl: data.total_unrealized_pnl || 0
        };
    } catch (e) {
        return null;
    }
}

/**
 * Parse Account Summary lines for capital tracking
 * Example: [OANDA] Account Summary: Balance=26.6995, NAV=26.0552
 */
function parseAccountLine(line, timestamp) {
    const balanceMatch = line.match(/Balance[=:]\s*([\d.,]+)/i);
    const navMatch = line.match(/NAV[=:]\s*([\d.,]+)/i);
    const equityMatch = line.match(/Equity[=:]\s*([\d.,]+)/i);

    if (balanceMatch || navMatch || equityMatch) {
        return {
            timestamp,
            type: 'capital',
            balance: balanceMatch ? parseFloat(balanceMatch[1]) : null,
            nav: navMatch ? parseFloat(navMatch[1]) : (equityMatch ? parseFloat(equityMatch[1]) : null)
        };
    }
    return null;
}

/**
 * Parse [DECISION] or [STRUCTURE] lines for trade decisions
 */
function parseDecisionLine(line, timestamp) {
    if (!line.includes('[DECISION]') && !line.includes('[STRUCTURE]')) return null;

    const decision = {
        timestamp,
        type: 'decision',
        symbol: null,
        action: null,
        score: null,
        reason: '',
        strategy: null
    };

    // Extract symbol
    const symbolMatch = line.match(/([A-Z]{3,}(?:USD|JPY|CAD|EUR|GBP|CHF|AUD|NZD)?)/);
    if (symbolMatch) decision.symbol = symbolMatch[1];

    // Extract action
    const actionMatch = line.match(/action=([^\s|]+)/i);
    if (actionMatch) decision.action = actionMatch[1].toLowerCase();

    // Extract score
    const scoreMatch = line.match(/(?:icc_score|selection_score|score)[=:]\s*([\d.]+)/i);
    if (scoreMatch) decision.score = parseFloat(scoreMatch[1]);

    // Extract strategy
    const strategyMatch = line.match(/strategy[=:]\s*["']?(\w+)["']?/i);
    if (strategyMatch) decision.strategy = strategyMatch[1];

    // Extract grade
    const gradeMatch = line.match(/grade=([A-F][+-]?)/i);
    if (gradeMatch) decision.grade = gradeMatch[1];

    // Extract reason
    const reasonMatch = line.match(/reason=([^|]+)/i);
    if (reasonMatch) decision.reason = reasonMatch[1].trim();

    return decision;
}

/**
 * Parse [HEARTBEAT] lines for capital snapshots
 * Example: [HEARTBEAT] Capital available: $26.06
 */
function parseHeartbeatLine(line, timestamp) {
    const capitalMatch = line.match(/Capital available[=:]\s*\$?([\d.,]+)/i);
    if (capitalMatch) {
        return {
            timestamp,
            type: 'capital',
            nav: parseFloat(capitalMatch[1].replace(/,/g, ''))
        };
    }
    return null;
}

/**
 * Get all log files sorted by modification time (newest first)
 */
function getLogFiles() {
    if (!fs.existsSync(LOGS_DIR)) return [];

    const files = fs.readdirSync(LOGS_DIR)
        .filter(f => f.startsWith('tradebot.log'))
        .map(f => ({
            name: f,
            path: path.join(LOGS_DIR, f),
            mtime: fs.statSync(path.join(LOGS_DIR, f)).mtime
        }))
        .sort((a, b) => b.mtime - a.mtime);

    return files;
}

/**
 * Parse a single log file and extract all relevant data
 */
async function parseLogFile(filePath, startTime = null, endTime = null) {
    const results = {
        trades: [],
        holdings: [],
        capital: [],
        decisions: []
    };

    if (!fs.existsSync(filePath)) return results;

    try {
        const fileStream = fs.createReadStream(filePath);
        const rl = readline.createInterface({
            input: fileStream,
            crlfDelay: Infinity
        });

        for await (const line of rl) {
            const timestamp = parseTimestamp(line);
            if (!timestamp) continue;

            // Apply time filters
            if (startTime && timestamp < startTime) continue;
            if (endTime && timestamp > endTime) continue;

            // Convert timestamp to ISO string for IPC serialization
            const timestampISO = timestamp.toISOString();

            // Parse different line types
            if (line.includes('[EXIT]')) {
                const trade = parseExitLine(line, timestamp);
                if (trade && trade.symbol) {
                    trade.timestamp = timestampISO;
                    results.trades.push(trade);
                }
            }

            if (line.includes('[HOLDINGS]')) {
                const holdings = parseHoldingsLine(line, timestamp);
                if (holdings) {
                    holdings.timestamp = timestampISO;
                    results.holdings.push(holdings);
                }
            }

            if (line.includes('Account Summary') || line.includes('Balance=')) {
                const capital = parseAccountLine(line, timestamp);
                if (capital) {
                    capital.timestamp = timestampISO;
                    results.capital.push(capital);
                }
            }

            if (line.includes('[HEARTBEAT]')) {
                const heartbeat = parseHeartbeatLine(line, timestamp);
                if (heartbeat) {
                    heartbeat.timestamp = timestampISO;
                    results.capital.push(heartbeat);
                }
            }

            if (line.includes('[DECISION]') || line.includes('[STRUCTURE]')) {
                const decision = parseDecisionLine(line, timestamp);
                if (decision) {
                    decision.timestamp = timestampISO;
                    results.decisions.push(decision);
                }
            }
        }
    } catch (error) {
        console.error('[LOG_PARSER] Error parsing file:', filePath, error);
    }

    return results;
}

/**
 * Get time filter bounds based on filter type
 */
function getTimeFilterBounds(filter) {
    const now = new Date();
    let startTime = null;

    switch (filter) {
        case '1h':
            startTime = new Date(now.getTime() - 60 * 60 * 1000);
            break;
        case '24h':
            startTime = new Date(now.getTime() - 24 * 60 * 60 * 1000);
            break;
        case 'week':
            startTime = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
            break;
        case 'month':
            startTime = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
            break;
        case 'all':
        default:
            startTime = null;
    }

    return { startTime, endTime: now };
}

/**
 * Main function to get trade history with time filter
 */
async function getTradeHistory(filter = '24h') {
    const { startTime, endTime } = getTimeFilterBounds(filter);
    const logFiles = getLogFiles();

    const allResults = {
        trades: [],
        holdings: [],
        capital: [],
        decisions: []
    };

    // Parse main log file first
    const mainLog = path.join(LOGS_DIR, 'tradebot.log');
    if (fs.existsSync(mainLog)) {
        const results = await parseLogFile(mainLog, startTime, endTime);
        allResults.trades.push(...results.trades);
        allResults.holdings.push(...results.holdings);
        allResults.capital.push(...results.capital);
        allResults.decisions.push(...results.decisions);
    }

    // Parse rotated logs if needed (for longer time filters)
    if (filter === 'week' || filter === 'month' || filter === 'all') {
        for (const logFile of logFiles) {
            if (logFile.name === 'tradebot.log') continue;
            if (logFile.name.startsWith('tradebot.log.')) {
                const results = await parseLogFile(logFile.path, startTime, endTime);
                allResults.trades.push(...results.trades);
                allResults.holdings.push(...results.holdings);
                allResults.capital.push(...results.capital);
                allResults.decisions.push(...results.decisions);
            }
        }
    }

    // Sort by timestamp (descending for history, ascending for capital)
    allResults.trades.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
    allResults.holdings.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
    allResults.capital.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
    allResults.decisions.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));

    return allResults;
}

/**
 * Calculate analytics summary from trade data
 * Note: timestamps are ISO strings for IPC serialization
 */
function calculateAnalyticsSummary(data) {
    const trades = data.trades || [];
    const capital = data.capital || [];

    console.log('[LOG_PARSER] Calculating summary - trades:', trades.length, 'capital entries:', capital.length);

    // Separate wins and losses
    const wins = trades.filter(t => t.pnl > 0);
    const losses = trades.filter(t => t.pnl < 0);
    const breakeven = trades.filter(t => t.pnl === 0);

    // Calculate totals
    const totalWins = wins.length;
    const totalLosses = losses.length;
    const totalTrades = trades.length;

    const grossProfit = wins.reduce((sum, t) => sum + t.pnl, 0);
    const grossLoss = Math.abs(losses.reduce((sum, t) => sum + t.pnl, 0));
    const totalPnl = grossProfit - grossLoss;

    // Win rate
    const winRate = totalTrades > 0 ? (totalWins / totalTrades) * 100 : 0;

    // Average win/loss
    const avgWin = totalWins > 0 ? grossProfit / totalWins : 0;
    const avgLoss = totalLosses > 0 ? grossLoss / totalLosses : 0;

    // Risk:Reward ratio
    const riskReward = avgLoss > 0 ? avgWin / avgLoss : avgWin > 0 ? Infinity : 0;

    // Best and worst trades
    const bestTrade = trades.length > 0 ? Math.max(...trades.map(t => t.pnl)) : 0;
    const worstTrade = trades.length > 0 ? Math.min(...trades.map(t => t.pnl)) : 0;

    // Profit factor
    const profitFactor = grossLoss > 0 ? grossProfit / grossLoss : grossProfit > 0 ? Infinity : 0;

    // Capital at start and end
    const capitalStart = capital.length > 0 ? (capital[0].nav || capital[0].balance || 0) : 0;
    const capitalEnd = capital.length > 0 ? (capital[capital.length - 1].nav || capital[capital.length - 1].balance || 0) : 0;
    const capitalChange = capitalEnd - capitalStart;
    const capitalChangePct = capitalStart > 0 ? (capitalChange / capitalStart) * 100 : 0;

    // Strategy breakdown
    const strategyStats = {};
    trades.forEach(t => {
        const strat = t.strategy || 'unknown';
        if (!strategyStats[strat]) {
            strategyStats[strat] = { wins: 0, losses: 0, pnl: 0 };
        }
        if (t.pnl > 0) strategyStats[strat].wins++;
        else if (t.pnl < 0) strategyStats[strat].losses++;
        strategyStats[strat].pnl += t.pnl;
    });

    // Symbol breakdown
    const symbolStats = {};
    trades.forEach(t => {
        const sym = t.symbol || 'unknown';
        if (!symbolStats[sym]) {
            symbolStats[sym] = { wins: 0, losses: 0, pnl: 0 };
        }
        if (t.pnl > 0) symbolStats[sym].wins++;
        else if (t.pnl < 0) symbolStats[sym].losses++;
        symbolStats[sym].pnl += t.pnl;
    });

    return {
        // Core metrics
        totalTrades,
        totalWins,
        totalLosses,
        breakeven: breakeven.length,
        winRate: parseFloat(winRate.toFixed(1)),
        totalPnl: parseFloat(totalPnl.toFixed(2)),
        grossProfit: parseFloat(grossProfit.toFixed(2)),
        grossLoss: parseFloat(grossLoss.toFixed(2)),

        // Additional metrics
        avgWin: parseFloat(avgWin.toFixed(2)),
        avgLoss: parseFloat(avgLoss.toFixed(2)),
        riskReward: isFinite(riskReward) ? parseFloat(riskReward.toFixed(2)) : 'N/A',
        bestTrade: parseFloat(bestTrade.toFixed(2)),
        worstTrade: parseFloat(worstTrade.toFixed(2)),
        profitFactor: isFinite(profitFactor) ? parseFloat(profitFactor.toFixed(2)) : 'N/A',

        // Capital metrics
        capitalStart: parseFloat(capitalStart.toFixed(2)),
        capitalEnd: parseFloat(capitalEnd.toFixed(2)),
        capitalChange: parseFloat(capitalChange.toFixed(2)),
        capitalChangePct: parseFloat(capitalChangePct.toFixed(1)),

        // Breakdowns
        strategyStats,
        symbolStats,

        // Raw data for charts
        trades,
        capitalHistory: capital
    };
}

module.exports = {
    getTradeHistory,
    calculateAnalyticsSummary,
    getLogFiles,
    parseLogFile,
    getTimeFilterBounds
};
