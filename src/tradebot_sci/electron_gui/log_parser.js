/**
 * Log Parser Module for Analytics
 * Reads from data/ledger.json (maintained by the Python LedgerDaemon)
 * Falls back to direct log parsing if ledger is unavailable.
 */

const fs = require('fs');
const path = require('path');
const readline = require('readline');

const LOGS_DIR = path.join(__dirname, '../../../logs');
const LEDGER_PATH = path.join(__dirname, '../../../data/ledger.json');
const PAPER_LEDGER_PATH = path.join(__dirname, '../../../data/paper_ledger.json');
const SABBATH_FLAG = path.join(__dirname, '../../../data/.sabbath_active');

// ─────────────────────────────────────────────────────────────────────────
// LEDGER-BASED DATA (preferred path — fast JSON read)
// ─────────────────────────────────────────────────────────────────────────

/**
 * Read the ledger JSON written by the Python LedgerDaemon.
 * Returns null if the file doesn't exist or can't be parsed.
 */
function readLedger() {
    try {
        // During Sabbath, read from paper_ledger.json instead
        const isSabbath = fs.existsSync(SABBATH_FLAG);
        const targetPath = isSabbath ? PAPER_LEDGER_PATH : LEDGER_PATH;
        if (!fs.existsSync(targetPath)) return null;
        const raw = fs.readFileSync(targetPath, 'utf8');
        const data = JSON.parse(raw);
        if (data && data.version) {
            if (isSabbath) {
                console.log('[LOG_PARSER] Sabbath active — reading paper_ledger.json');
            }
            return data;
        }
        return null;
    } catch (e) {
        console.error('[LOG_PARSER] Failed to read ledger:', e.message);
        return null;
    }
}

/**
 * Build an analytics summary from ledger data for a given timeframe.
 *
 * Timeframe mapping:
 *   'holdings' → unrealized PnL only (active positions)
 *   '24h'      → current_day (sundown-to-sundown)
 *   'week'     → last 7 days + current_day
 *   'month'    → last 30 days + current_day
 *   'year'     → last 365 days + current_day
 *   'all'      → all days + current_day
 */
function summaryFromLedger(ledger, timeframe, logTrades = [], logHoldings = [], logCapital = []) {
    const current = ledger.current_day || {};
    const days = ledger.days || [];

    // Holdings mode: just return unrealized PnL + active positions
    if (timeframe === 'holdings') {
        const uPnl = current.pnl_unrealized || 0;
        // Build position entries from latest HOLDINGS snapshot
        const positionTrades = getHoldingsEntries(logHoldings);
        return {
            totalTrades: 0, totalWins: 0, totalLosses: 0, breakeven: 0,
            winRate: 0, totalPnl: parseFloat(uPnl.toFixed(2)),
            totalNetWorth: parseFloat(uPnl.toFixed(2)),
            grossProfit: 0, grossLoss: 0, avgWin: 0, avgLoss: 0,
            riskReward: 'N/A', bestTrade: 0, worstTrade: 0,
            profitFactor: 'N/A', spreadCosts: 0,
            capitalStart: 0, capitalEnd: 0, capitalChange: 0, capitalChangePct: 0,
            strategyStats: {}, symbolStats: {},
            dayStart: current.day_start || '', unrealizedPnl: uPnl,
            trades: positionTrades, capitalHistory: [], _source: 'ledger'
        };
    }

    let selectedDays = [];
    if (timeframe === '24h' || timeframe === '1h' || timeframe === '4h') {
        selectedDays = [];
    } else if (timeframe === 'week') {
        selectedDays = days.slice(-7);
    } else if (timeframe === 'month') {
        selectedDays = days.slice(-30);
    } else if (timeframe === 'year') {
        selectedDays = days.slice(-365);
    } else {
        selectedDays = [...days];
    }

    // Accumulate from historical days
    let totalPnl = 0;
    let totalTrades = 0;
    let totalWins = 0;
    let totalLosses = 0;
    let bestTrade = 0;
    let worstTrade = 0;
    let totalSpreadCosts = 0;
    const symbolStats = {};
    const strategyStats = {};
    const capitalHistory = [];

    for (const day of selectedDays) {
        totalPnl += day.pnl_realized || 0;
        totalTrades += day.trades || 0;
        totalWins += day.wins || 0;
        totalLosses += day.losses || 0;
        totalSpreadCosts += day.spread_costs || 0;

        if ((day.best_trade || 0) > bestTrade) bestTrade = day.best_trade;
        if ((day.worst_trade || 0) < worstTrade) worstTrade = day.worst_trade;

        const bySymbol = day.by_symbol || {};
        for (const [sym, data] of Object.entries(bySymbol)) {
            if (!symbolStats[sym]) symbolStats[sym] = { pnl: 0, trades: 0, wins: 0, losses: 0 };
            symbolStats[sym].pnl += data.pnl || 0;
            symbolStats[sym].trades += data.trades || 0;
            symbolStats[sym].wins += data.wins || 0;
            symbolStats[sym].losses += data.losses || 0;
        }

        const byStrat = day.by_strategy || {};
        for (const [strat, data] of Object.entries(byStrat)) {
            if (!strategyStats[strat]) strategyStats[strat] = { pnl: 0, wins: 0, losses: 0 };
            strategyStats[strat].pnl += data.pnl || 0;
            strategyStats[strat].wins += data.wins || 0;
            strategyStats[strat].losses += data.losses || 0;
        }

        if (day.capital_at_start) {
            capitalHistory.push({
                timestamp: day.day_start || day.date,
                type: 'capital',
                nav: day.capital_at_start
            });
        }
    }

    // Add current day ledger stats
    totalPnl += current.pnl_realized || 0;
    totalTrades += current.trades || 0;
    totalWins += current.wins || 0;
    totalLosses += current.losses || 0;
    totalSpreadCosts += current.spread_costs || 0;

    if ((current.best_trade || 0) > bestTrade) bestTrade = current.best_trade;
    if ((current.worst_trade || 0) < worstTrade) worstTrade = current.worst_trade;

    const curBySymbol = current.by_symbol || {};
    for (const [sym, data] of Object.entries(curBySymbol)) {
        if (!symbolStats[sym]) symbolStats[sym] = { pnl: 0, trades: 0, wins: 0, losses: 0 };
        symbolStats[sym].pnl += data.pnl || 0;
        symbolStats[sym].trades += data.trades || 0;
        symbolStats[sym].wins += data.wins || 0;
        symbolStats[sym].losses += data.losses || 0;
    }

    const curByStrat = current.by_strategy || {};
    for (const [strat, data] of Object.entries(curByStrat)) {
        if (!strategyStats[strat]) strategyStats[strat] = { pnl: 0, wins: 0, losses: 0 };
        strategyStats[strat].pnl += data.pnl || 0;
        strategyStats[strat].wins += data.wins || 0;
        strategyStats[strat].losses += data.losses || 0;
    }

    // ── Build merged trade list from ledger + log-parsed EXIT trades ──
    const ledgerTradeLog = (current.trade_log || []).map(t => ({
        ...t,
        timestamp: t.timestamp || t.time,
        _src: 'ledger'
    }));

    // Build a lookup from log trades for strategy enrichment
    const logTradesByKey = {};
    for (const lt of logTrades) {
        const key = `${lt.symbol}_${Math.round((lt.pnl || 0) * 100)}`;
        if (lt.strategy && lt.strategy !== 'unknown') {
            logTradesByKey[key] = lt.strategy;
        }
    }

    // Enrich ledger trades with 'unknown' strategy from log-parsed data
    for (const lt of ledgerTradeLog) {
        if (!lt.strategy || lt.strategy === 'unknown') {
            const key = `${lt.symbol}_${Math.round((lt.pnl || 0) * 100)}`;
            if (logTradesByKey[key]) {
                const oldStrat = lt.strategy || 'unknown';
                lt.strategy = logTradesByKey[key];
                // Fix strategy breakdown: move stats from 'unknown' to discovered strategy
                if (strategyStats[oldStrat]) {
                    const correctStrat = lt.strategy;
                    if (!strategyStats[correctStrat]) strategyStats[correctStrat] = { pnl: 0, wins: 0, losses: 0 };
                    strategyStats[correctStrat].pnl += lt.pnl || 0;
                    strategyStats[correctStrat].wins += (lt.pnl > 0 ? 1 : 0);
                    strategyStats[correctStrat].losses += (lt.pnl < 0 ? 1 : 0);
                    strategyStats[oldStrat].pnl -= lt.pnl || 0;
                    strategyStats[oldStrat].wins -= (lt.pnl > 0 ? 1 : 0);
                    strategyStats[oldStrat].losses -= (lt.pnl < 0 ? 1 : 0);
                    // Remove empty strategy entry
                    if (strategyStats[oldStrat].wins <= 0 && strategyStats[oldStrat].losses <= 0) {
                        delete strategyStats[oldStrat];
                    }
                }
            }
        }
    }

    // Merge log-parsed EXIT trades that the ledger missed
    const ledgerKeys = new Set(
        ledgerTradeLog.map(t => `${t.symbol}_${Math.round((t.pnl || 0) * 100)}`)
    );

    for (const lt of logTrades) {
        const key = `${lt.symbol}_${Math.round((lt.pnl || 0) * 100)}`;
        if (!ledgerKeys.has(key)) {
            // This trade is in the logs but NOT in the ledger — add it
            ledgerTradeLog.push({
                time: lt.timestamp,
                timestamp: lt.timestamp,
                symbol: lt.symbol,
                pnl: lt.pnl || 0,
                side: lt.side || 'unknown',
                reason: lt.reason || '',
                strategy: lt.strategy || 'unknown',
                _src: 'log'
            });

            // Also update aggregate counts since ledger missed this trade
            totalTrades++;
            totalPnl += lt.pnl || 0;
            if (lt.pnl > 0) totalWins++;
            else if (lt.pnl < 0) totalLosses++;

            if (lt.pnl > bestTrade) bestTrade = lt.pnl;
            if (lt.pnl < worstTrade) worstTrade = lt.pnl;

            // Update symbol/strategy breakdowns
            const sym = lt.symbol || 'unknown';
            if (!symbolStats[sym]) symbolStats[sym] = { pnl: 0, trades: 0, wins: 0, losses: 0 };
            symbolStats[sym].pnl += lt.pnl || 0;
            symbolStats[sym].trades++;
            if (lt.pnl > 0) symbolStats[sym].wins++;
            else if (lt.pnl < 0) symbolStats[sym].losses++;

            const strat = lt.strategy || 'unknown';
            if (!strategyStats[strat]) strategyStats[strat] = { pnl: 0, wins: 0, losses: 0 };
            strategyStats[strat].pnl += lt.pnl || 0;
            if (lt.pnl > 0) strategyStats[strat].wins++;
            else if (lt.pnl < 0) strategyStats[strat].losses++;
        }
    }

    // Sort merged trade list by time (newest first)
    ledgerTradeLog.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));

    // ── Gross profit/loss from the merged trade list ──
    let grossProfit = 0, grossLoss = 0;
    for (const t of ledgerTradeLog) {
        if (t.pnl > 0) grossProfit += t.pnl;
        else if (t.pnl < 0) grossLoss += Math.abs(t.pnl);
    }
    // Fallback if no trades but totalPnl exists
    if (grossProfit === 0 && grossLoss === 0) {
        grossProfit = totalPnl > 0 ? totalPnl : 0;
        grossLoss = totalPnl < 0 ? Math.abs(totalPnl) : 0;
    }

    // ── Add active holdings as synthetic entries in trade list ──
    const holdingsEntries = getHoldingsEntries(logHoldings);
    const allTrades = [...ledgerTradeLog, ...holdingsEntries];

    // ── Supplement capital history from log-parsed data ──
    if (logCapital.length > 0) {
        const existingTimes = new Set(capitalHistory.map(c => c.timestamp));
        for (const cap of logCapital) {
            if (!existingTimes.has(cap.timestamp)) {
                capitalHistory.push(cap);
            }
        }
        capitalHistory.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
    }

    const winRate = totalTrades > 0 ? (totalWins / totalTrades) * 100 : 0;
    const avgWin = totalWins > 0 ? grossProfit / totalWins : 0;
    const avgLoss = totalLosses > 0 ? grossLoss / totalLosses : 0;
    const riskReward = avgLoss > 0 ? avgWin / avgLoss : (avgWin > 0 ? Infinity : 0);
    const profitFactor = grossLoss > 0 ? grossProfit / grossLoss : (grossProfit > 0 ? Infinity : 0);

    // Capital
    const capitalStart = current.capital_at_start || (days.length > 0 ? (days[days.length - 1].capital_at_start || 0) : 0);
    const capitalEnd = current.capital_now || capitalStart;
    const capitalChange = capitalEnd - capitalStart;
    const capitalChangePct = capitalStart > 0 ? (capitalChange / capitalStart) * 100 : 0;

    if (capitalEnd > 0) {
        capitalHistory.push({
            timestamp: current.day_start || new Date().toISOString(),
            type: 'capital',
            nav: capitalEnd
        });
    }

    return {
        totalTrades,
        totalWins,
        totalLosses,
        breakeven: totalTrades - totalWins - totalLosses,
        winRate: parseFloat(winRate.toFixed(1)),
        totalPnl: parseFloat(totalPnl.toFixed(2)),
        totalNetWorth: parseFloat(totalPnl.toFixed(2)),
        grossProfit: parseFloat(grossProfit.toFixed(2)),
        grossLoss: parseFloat(grossLoss.toFixed(2)),

        avgWin: parseFloat(avgWin.toFixed(2)),
        avgLoss: parseFloat(avgLoss.toFixed(2)),
        riskReward: isFinite(riskReward) ? parseFloat(riskReward.toFixed(2)) : 'N/A',
        bestTrade: parseFloat(bestTrade.toFixed(2)),
        worstTrade: parseFloat(worstTrade.toFixed(2)),
        profitFactor: isFinite(profitFactor) ? parseFloat(profitFactor.toFixed(2)) : 'N/A',
        spreadCosts: parseFloat(totalSpreadCosts.toFixed(4)),

        capitalStart: parseFloat(capitalStart.toFixed(2)),
        capitalEnd: parseFloat(capitalEnd.toFixed(2)),
        capitalChange: parseFloat(capitalChange.toFixed(2)),
        capitalChangePct: parseFloat(capitalChangePct.toFixed(1)),

        strategyStats,
        symbolStats,

        dayStart: current.day_start || '',
        unrealizedPnl: current.pnl_unrealized || 0,

        trades: allTrades,
        capitalHistory,

        _source: 'ledger+logs'
    };
}

/**
 * Build trade-like entries from the latest HOLDINGS snapshot.
 * These appear in the trade history as active positions (not closed trades).
 */
function buildHoldingsEntries(logHoldings) {
    if (!logHoldings || logHoldings.length === 0) return [];

    // Use the most recent HOLDINGS snapshot
    const latest = logHoldings[0];
    if (!latest || !latest.positions || latest.positions.length === 0) return [];

    return latest.positions.map(pos => ({
        timestamp: pos.entry_time || latest.timestamp,
        symbol: pos.symbol || '??',
        pnl: pos.unrealized_pnl || 0,
        side: pos.side || pos.direction || 'long',
        reason: '🟢 Active Position',
        strategy: 'active',
        size: pos.size || 0,
        entry_price: pos.entry_price || pos.avg_price || 0,
        stop_loss: pos.stop_loss || 0,
        take_profit: pos.take_profit || 0,
        _active: true
    }));
}

/**
 * Build holdings entries from paper_state.json
 * during Sabbath, so live OANDA positions don't leak into the paper view.
 */
const PAPER_STATE_FILE = path.join(__dirname, '../../../data/paper_state.json');

function buildPaperHoldingsEntries() {
    try {
        if (!fs.existsSync(PAPER_STATE_FILE)) return [];
        const raw = fs.readFileSync(PAPER_STATE_FILE, 'utf8');
        const state = JSON.parse(raw);
        const positions = state.positions || {};
        return Object.entries(positions).map(([symbol, pos]) => ({
            timestamp: pos.opened_at || state.updated_at || new Date().toISOString(),
            symbol: symbol,
            pnl: pos.unrealized_pnl || 0,
            side: pos.side || 'long',
            reason: '🟢 Active Position (Paper)',
            strategy: pos.strategy || 'active',
            size: pos.size || pos.qty || 0,
            entry_price: pos.entry_price || pos.avg_price || 0,
            stop_loss: pos.stop_loss || 0,
            take_profit: pos.take_profit || 0,
            _active: true
        }));
    } catch (e) {
        console.error('[LOG_PARSER] Failed to read paper_state.json for holdings:', e.message);
        return [];
    }
}

/**
 * Get holdings entries, Sabbath-aware: returns paper positions during Sabbath,
 * live OANDA positions otherwise.
 */
function getHoldingsEntries(logHoldings) {
    const isSabbath = fs.existsSync(SABBATH_FLAG);
    if (isSabbath) {
        return buildPaperHoldingsEntries();
    }
    return buildHoldingsEntries(logHoldings);
}

// ─────────────────────────────────────────────────────────────────────────
// LEGACY LOG PARSING (fallback path)
// ─────────────────────────────────────────────────────────────────────────

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
        .filter(f => f.startsWith('tradebot.log') || f === 'bot_stdout.log')
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

    // Track last strategy seen from [PHOENIX] or [META-DEBUG] lines
    // so we can attribute it to the next [EXIT] trade
    let lastExitStrategy = {}; // per-symbol last strategy

    try {
        const fileStream = fs.createReadStream(filePath);
        const rl = readline.createInterface({
            input: fileStream,
            crlfDelay: Infinity
        });

        for await (const line of rl) {
            const timestamp = parseTimestamp(line);
            if (!timestamp) continue;

            // Skip paper/Sabbath lines — they have their own ledger
            if (line.includes('[PAPER]')) continue;

            // Apply time filters
            if (startTime && timestamp < startTime) continue;
            if (endTime && timestamp > endTime) continue;

            // Convert timestamp to ISO string for IPC serialization
            const timestampISO = timestamp.toISOString();

            // Track strategy from [PHOENIX] lines:
            // [PHOENIX] USDCHF Strategy EXIT triggered: Decision: ...
            if (line.includes('[PHOENIX]') && line.includes('Strategy EXIT triggered')) {
                const phoenixMatch = line.match(/\[PHOENIX\]\s+([A-Z]{3,10})\s+Strategy EXIT triggered/);
                if (phoenixMatch) {
                    lastExitStrategy[phoenixMatch[1]] = 'PHOENIX_EXIT';
                }
            }

            // Track strategy from [META-DEBUG] lines:
            // [META-DEBUG] USDCHF SUPPLY_DEMAND (EXIT): WIN -> close_position
            if (line.includes('[META-DEBUG]') && line.includes('(EXIT)')) {
                const metaMatch = line.match(/\[META-DEBUG\]\s+([A-Z]{3,10})\s+(\w+)\s+\(EXIT\):\s+WIN/);
                if (metaMatch) {
                    lastExitStrategy[metaMatch[1]] = metaMatch[2]; // e.g. 'SUPPLY_DEMAND'
                }
            }

            // Track strategy from Tournament Winner:
            // Tournament Winner: SUPPLY_DEMAND
            if (line.includes('Tournament Winner:')) {
                const tourMatch = line.match(/Tournament Winner:\s*(\w+)/);
                if (tourMatch) {
                    // Global fallback strategy
                    lastExitStrategy['_global'] = tourMatch[1];
                }
            }

            // Parse different line types
            if (line.includes('[EXIT]')) {
                const trade = parseExitLine(line, timestamp);
                if (trade && trade.symbol) {
                    trade.timestamp = timestampISO;

                    // Attribute strategy from tracked context
                    if (!trade.strategy || trade.strategy === 'unknown') {
                        trade.strategy = lastExitStrategy[trade.symbol]
                            || lastExitStrategy['_global']
                            || 'unknown';
                    }

                    results.trades.push(trade);
                    // Clear per-symbol strategy after use
                    delete lastExitStrategy[trade.symbol];
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
 * Parse all log files within a time range, returning combined results.
 */
async function parseAllLogs(filter) {
    const { startTime, endTime } = getTimeFilterBounds(filter);
    const logFiles = getLogFiles();

    const allResults = {
        trades: [],
        holdings: [],
        capital: [],
        decisions: []
    };

    // Parse main log file
    const mainLog = path.join(LOGS_DIR, 'tradebot.log');
    if (fs.existsSync(mainLog)) {
        const results = await parseLogFile(mainLog, startTime, endTime);
        allResults.trades.push(...results.trades);
        allResults.holdings.push(...results.holdings);
        allResults.capital.push(...results.capital);
        allResults.decisions.push(...results.decisions);
    }

    // Always parse rotated logs AND bot_stdout.log — trades span across files
    for (const logFile of logFiles) {
        if (logFile.name === 'tradebot.log') continue;
        if (logFile.name.startsWith('tradebot.log.') || logFile.name === 'bot_stdout.log') {
            const results = await parseLogFile(logFile.path, startTime, endTime);
            allResults.trades.push(...results.trades);
            allResults.holdings.push(...results.holdings);
            allResults.capital.push(...results.capital);
            allResults.decisions.push(...results.decisions);
        }
    }

    // Deduplicate trades by timestamp+symbol
    const seen = new Set();
    allResults.trades = allResults.trades.filter(t => {
        const key = `${t.timestamp}_${t.symbol}_${t.pnl}`;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
    });

    // Sort
    allResults.trades.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
    allResults.holdings.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
    allResults.capital.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
    allResults.decisions.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));

    return allResults;
}

/**
 * Main function to get trade history with time filter.
 * Uses ledger + log parsing combined for complete data.
 */
async function getTradeHistory(filter = '24h') {
    const ledger = readLedger();

    // Always parse logs to catch trades the ledger may have missed
    const logData = await parseAllLogs(filter);
    console.log('[LOG_PARSER] Parsed logs: trades=' + logData.trades.length +
        ', holdings=' + logData.holdings.length +
        ', capital=' + logData.capital.length);

    if (ledger) {
        console.log('[LOG_PARSER] Ledger available — will merge with log data');
        return {
            _fromLedger: true,
            _ledger: ledger,
            _filter: filter,
            _logTrades: logData.trades,
            _logHoldings: logData.holdings,
            _logCapital: logData.capital
        };
    }

    // Pure fallback
    console.log('[LOG_PARSER] No ledger, using log parse only');
    return logData;
}

/**
 * Calculate analytics summary from trade data.
 * Routes to ledger-based summary if data came from ledger.
 * Note: timestamps are ISO strings for IPC serialization
 */
function calculateAnalyticsSummary(data) {
    // If data came from ledger, use ledger-based summary + supplement from logs
    if (data._fromLedger && data._ledger) {
        const summary = summaryFromLedger(
            data._ledger,
            data._filter || '24h',
            data._logTrades || [],
            data._logHoldings || [],
            data._logCapital || []
        );
        console.log('[LOG_PARSER] Ledger summary - trades:', summary.totalTrades,
            'pnl:', summary.totalPnl, 'trade_log:', summary.trades?.length);
        return summary;
    }

    // Legacy path: calculate from parsed log data
    const trades = data.trades || [];
    const capital = data.capital || [];

    console.log('[LOG_PARSER] Calculating summary (legacy) - trades:', trades.length, 'capital entries:', capital.length);

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
        totalNetWorth: parseFloat(totalPnl.toFixed(2)),
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
        capitalHistory: capital,

        // Source marker
        _source: 'legacy_log_parse'
    };
}

module.exports = {
    getTradeHistory,
    calculateAnalyticsSummary,
    getLogFiles,
    parseLogFile,
    getTimeFilterBounds,
    readLedger,
    summaryFromLedger
};
