const logParser = require('./electron_gui/log_analytics.js');
async function run() {
    const data = await logParser.getTradeHistory('24h', false);
    console.log("Trades returned:");
    for (const t of data.trades.filter(t => t._active)) {
        console.log(`Symbol: ${t.symbol}, Strategy: ${t.strategy}, Timestamp: ${t.timestamp}, Active: ${t._active}`);
    }
}
run();
