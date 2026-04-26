const logParser = require('./log_analytics.js');
async function run() {
    const data = await logParser.getTradeHistory('24h', true);
    const summary = logParser.calculateAnalyticsSummary(data, true);
    console.log(summary);
}
run();
