/**
 * Tradebot SCI Settings Interface
 */

// Wait for DOM to be ready
document.addEventListener('DOMContentLoaded', () => init());

// ═══════════════════════════════════════════════════════════
// STATE MANAGEMENT
// ═══════════════════════════════════════════════════════════

let envData = {};
let profilesContent = "";
let currentTab = 'system';
let subTabs = { brokers: 'ibkr', strategy: 'assets' };
let localChanges = {};
let changeCount = 0;

// ═══════════════════════════════════════════════════════════
// TOOLTIP LIBRARY - Detailed, layman-friendly explanations
// ═══════════════════════════════════════════════════════════

const TOOLTIPS = {
    // System Settings
    APP_PROFILE: "Trading profiles define which markets you trade (stocks, forex, crypto), how often the bot checks for opportunities, and when it's allowed to trade. Think of it like choosing between 'day trader mode' vs '24/7 crypto mode'.",
    STRATEGY_VARIANT: "The trading strategy determines HOW the bot decides to enter and exit trades. Each strategy has different rules - some are aggressive scalpers, others wait for perfect setups. Choose based on your risk tolerance and market conditions.",
    BOT_MODE: "Controls how the bot runs: 'Continuous' keeps trading forever until you stop it. 'Scheduled' only trades during specific hours (like market open). 'Iterations' runs a fixed number of trade cycles then stops.",
    EXECUTE_TRADES: "The master ON/OFF switch for real trading. When OFF, the bot analyzes markets and shows what it WOULD do, but never places actual orders. Perfect for testing strategies without risking real money.",
    GUI_AUTOSTART_BOT: "When enabled, the trading bot automatically starts running as soon as you open this application. When disabled, you'll need to manually click 'Start' to begin trading.",
    CONTINUOUS_MODE: "Keeps the bot running indefinitely without stopping between trading sessions. Useful for 24/7 crypto markets. Disable this if you want the bot to pause after each session.",
    GUI_WS_URL: "The WebSocket URL for the trading bot. Change this if you are connecting to a bot running on a remote server or a different port (e.g., ws://192.168.1.10:8080/ws).",
    WS_SERVER_PORT: "The port number the trading bot should listen on for local connections. Default is 8080. If you change this, you must also update your WebConnect URL or external tools to match.",
    FRIDAY_FADE_ENABLED: "IMPORTANT (Forex Only): Automatically reduces risk to 0.25% after 12:00 PM EST on Fridays. This accounts for the sharp drop in Forex liquidity as markets approach the weekend close, preventing 'mean reversion' strategies from getting trapped in late-session drifts.",

    // Timeframes
    CANDLE_TIMEFRAME: "The main chart timeframe the bot watches. '15m' means each candle represents 15 minutes of price action. Shorter timeframes (1m, 5m) = more trades but more noise. Longer (1h, 4h) = fewer but higher-quality signals.",
    HTF_TIMEFRAME: "Higher TimeFrame - the 'big picture' view. The bot checks this larger timeframe to understand the overall market direction (trending up, down, or sideways) before taking trades on the smaller timeframe.",
    LTF_TIMEFRAME: "Lower TimeFrame - used for precise entry timing. Once the higher timeframe confirms the trend, the bot watches this smaller timeframe to find the perfect moment to enter a trade.",

    // Trend Detection
    TREND_WINDOW: "How many candles back the bot looks to determine the trend direction. More candles = smoother, more reliable trend detection but slower to react to changes.",
    LTF_TREND_WINDOW: "Same as Trend Window but for the lower timeframe. Fewer candles here means faster reaction to short-term price moves.",
    TREND_SWING_LOOKBACK: "How many candles on each side must be lower/higher to identify a swing point (local high or low). Higher = fewer but more significant swing points identified.",
    TREND_MIN_SWINGS: "Minimum number of swing highs/lows needed to confirm a trend. More swings required = more confidence the trend is real, but slower to identify new trends.",
    TREND_STRENGTH_FLOOR: "Minimum trend strength (0-1) before the bot considers it tradeable. 0.25 means the trend must be at least 25% strong - prevents trading in weak, uncertain markets.",

    // Risk Management
    RISK_PER_TRADE_PCT: "How much of your account you're willing to lose on a single trade. 1% means if you have $10,000, you risk losing $100 max per trade. Higher = bigger profits AND losses. Most professionals use 1-2%.",
    SHORT_RISK_PCT: "Risk percentage specifically for short (betting price goes down) positions. Some traders use lower risk for shorts since losses are theoretically unlimited.",
    MAX_EXPOSURE_PCT: "Maximum total risk across ALL open positions combined. If set to 10% with a $10,000 account, total risk across all trades can't exceed $1,000.",
    MAX_DAILY_LOSS_PCT: "Safety circuit breaker - if you lose this percentage of your account in one day, the bot stops trading to prevent catastrophic losses. Like a daily loss limit at a casino.",
    RISK_PER_TRADE_DOLLARS: "Fixed dollar amount to risk per trade instead of percentage. Useful if you want consistent $50 or $100 risk regardless of account size.",
    MAX_LOSS_PER_TRADE_DOLLARS: "Absolute maximum dollars you can lose on any single trade, even if percentage calculation says otherwise. A hard safety cap.",

    // Position Management
    MULTI_POSITION_ENABLED: "Allow the bot to have multiple trades open at the same time across different symbols. When disabled, it finishes one trade before starting another.",
    MAX_CONCURRENT_POSITIONS: "Maximum number of trades that can be open simultaneously. More positions = more diversification but also more complexity and capital required.",
    SMART_POSITIONS_ENABLED: "Prevents opening new trades unless your current open profits are high enough to 'pay for' the risk of the new position. Ensures you only scale up using profit, not principal.",

    // Pyramiding
    MAX_PYRAMID_ENTRIES: "Maximum times the bot can add to a winning position. 'Pyramiding' means buying more as a trade goes in your favor. 1 = no adding, just the initial entry.",
    PYRAMID_PROFIT_BUFFER_PCT: "Minimum profit percentage required before the bot will add to a position. Prevents adding too early before the trade proves itself.",
    PYRAMID_RISK_LOAD: "Risk percentage for the FIRST add to a winning position. Often set higher since the trade has already proven profitable.",
    PYRAMID_RISK_SCALE: "Risk percentage for subsequent adds after the first. Usually lower than Load since you're adding to an already-large position.",
    BREAKEVEN_TRAIL_AFTER_PYRAMIDS: "After this many pyramid adds, move your stop-loss to breakeven (entry price). Protects profits on scaled-up positions. 0 = disabled.",
    BREAKEVEN_TRAIL_PCT: "How far above breakeven to trail your stop. 0.003 = 0.3%, so if you bought at $100, stop moves to $100.30 instead of exactly $100.",

    // ICC Settings
    ICC_AUTO_ENTRY_ENABLED: "Enable automatic trade entries based on ICC (Indication, Correction, Continuation) signals. The core pattern recognition system.",
    ICC_AGGRESSIVE_MODE: "When enabled, the bot uses larger position sizes on high-confidence setups. More aggressive but higher risk/reward.",
    ICC_AUTO_ENTRY_REQUIRE_SWEEP: "Require a 'liquidity sweep' (price briefly breaks a level then reverses) before entering. These setups have higher win rates but occur less frequently.",
    ICC_AUTO_ENTRY_MIN_HTF_STRENGTH: "Minimum trend strength on higher timeframe before ICC entries are allowed. Filters out trades against weak or uncertain trends.",
    ICC_CONFIRMATION_BARS: "Number of candles to wait after a signal before confirming the entry. More bars = more confirmation but potentially worse entry price.",
    ICC_ENTRY_SCORE_THRESHOLD: "Minimum score (0-100) a setup must achieve before the bot will trade it. Higher = pickier about setups, fewer but better trades.",

    // ICC Scoring
    ICC_SCORE_CONTINUATION_POINTS: "Points awarded when price shows clear continuation in the trend direction after a correction. Key component of the ICC pattern.",
    ICC_SCORE_SWEEP_POINTS: "Points awarded for liquidity sweeps - when price briefly breaks support/resistance to trigger stop-losses before reversing. High-probability signal.",
    ICC_SCORE_HTF_LTF_ALIGN_POINTS: "Points when both higher and lower timeframes agree on direction. Alignment = higher probability trades.",
    ICC_SCORE_STRONG_HTF_POINTS: "Bonus points when the higher timeframe trend is particularly strong, not just present.",
    ICC_SCORE_PHASE_POINTS: "Points for favorable market phase - trending markets score higher than choppy/ranging markets.",
    ICC_SCORE_INDICATION_POINTS: "Points for the initial trend indication signal (break of structure). The first sign a trade setup may be forming.",

    // Exit Settings
    EXIT_ON_HTF_FLIP_ONLY_IF_LOSING: "Exit when higher timeframe trend flips, but ONLY if the trade is currently losing. Lets winners run if trend temporarily weakens.",
    AUTO_FLATTEN_ON_CLOSE: "Automatically close all positions at the end of the trading session. Prevents overnight/weekend risk.",
    TRAILING_STOP_ENABLED: "Enable trailing stops that follow price up (for longs) or down (for shorts), locking in profits as the trade moves in your favor.",
    TRAILING_STOP_MIN_PROFIT_PCT: "Minimum profit percentage before the trailing stop activates. Prevents premature stop-outs on normal price fluctuations.",
    STOP_ATR_MULTIPLIER: "Stop distance as multiple of ATR (Average True Range). ATR measures volatility - higher multiplier = wider stops, more room for price to move.",
    MIN_HOLD_HOURS: "Minimum hours to hold a position before allowing exits. Prevents panic-selling or premature exits. 0 = no minimum.",
    MAX_HOLD_HOURS: "Maximum hours to hold a position - force exit after this time regardless of profit/loss. 0 = hold forever if needed.",
    HTF_NEUTRAL_EXIT_BARS: "Exit if higher timeframe stays neutral (no clear trend) for this many bars. Prevents capital from being tied up in directionless markets.",

    // Broker Settings - IBKR
    IBKR_HOST: "IP address of your Interactive Brokers TWS or Gateway. Usually 127.0.0.1 if running on the same computer.",
    IBKR_PORT: "Connection port for IBKR. Use 7497 for Paper Trading in TWS, 7496 for Live TWS, 4002 for Paper Gateway, 4001 for Live Gateway.",
    IBKR_CLIENT_ID: "Unique identifier for this connection. If running multiple bots, each needs a different Client ID.",
    IBKR_ACCOUNT_ID: "Your IBKR account number. Found in Account Management. Format like DU1234567 (paper) or U1234567 (live).",
    IBKR_PAPER: "Enable paper trading mode - uses IBKR's simulated trading environment. Always test here before going live!",
    IBKR_READ_ONLY: "Read-only mode - bot can view positions and data but cannot place orders. Safe for monitoring.",
    IBKR_DEFAULT_CCY: "Default currency for the account. Usually USD but could be EUR, GBP, etc. for international accounts.",

    // Broker Settings - OANDA
    OANDA_ACCOUNT_ID: "Your OANDA account ID - found in your OANDA account settings or dashboard. Format like 101-001-1234567-001.",
    OANDA_API_KEY: "Your OANDA API access token. Generate one in OANDA's hub under 'Manage API Access'. Keep this secret!",
    OANDA_ENVIRONMENT: "Choose 'practice' for demo trading with fake money, or 'live' for real money trading. Always test in practice first!",
    OANDA_READ_ONLY: "Read-only mode - bot can fetch prices and positions but cannot place orders. Good for monitoring without trading.",

    // Broker Settings - CCXT/Coinbase
    CCXT_EXCHANGE: "The cryptocurrency exchange to connect to. Currently supports Coinbase and other CCXT-compatible exchanges.",
    CCXT_DEFAULT_TYPE: "Market type: 'spot' for regular buying/selling, 'swap' for perpetual futures, 'future' for dated futures contracts.",
    CCXT_API_KEY: "Your exchange API key - created in your exchange's API settings. Enables the bot to trade on your behalf.",
    CCXT_SECRET: "Your API secret key - paired with the API key. Never share this! Required to authenticate trades.",
    CCXT_SANDBOX: "Enable sandbox/testnet mode for the exchange. Trade with fake money to test your setup safely.",
    CCXT_ENABLE_RATE_LIMIT: "Automatically respect exchange rate limits to avoid getting temporarily banned for too many requests.",

    // Broker Settings - Gemini
    GEMINI_API_KEY: "Your Gemini API key - found in Gemini Settings -> API. Enables the bot to trade crypto on Gemini.com.",
    GEMINI_API_SECRET: "Your Gemini API secret - provided when you created the API key. Never share this! Required to sign orders.",
    GEMINI_SANDBOX: "Connect to the Gemini Sandbox (Exchange Testnet) for risk-free testing with simulated funds.",

    // Broker Settings - Kraken
    KRAKEN_API_KEY: "Your Kraken API key. Enables the bot to trade on your behalf. Keep this secret!",
    KRAKEN_API_SECRET: "Your Kraken API secret. Required for authentication. Never share this!",
    KRAKEN_ENVIRONMENT: "Choose 'production' for real trading or 'sandbox' for testing (if supported).",

    // Crypto Order Settings
    CRYPTO_FRACTIONAL_ENABLED: "Allow buying fractional amounts (0.001 BTC instead of whole coins). Required for expensive cryptos with small accounts.",
    CRYPTO_MIN_NOTIONAL_USD: "Minimum trade size in USD. Exchanges have minimums - trades below this will be rejected.",
    CRYPTO_MAX_NOTIONAL_USD: "Maximum trade size in USD. Safety limit to prevent accidentally huge orders.",
    CRYPTO_ORDER_TYPE: "Order execution type: 'LIMIT' places orders at specific prices (may not fill), 'MARKET' fills immediately at current price.",

    // Data Routing
    MARKET_DATA_MODE: "Where price data comes from: 'primary' (IBKR), 'alternative' (CCXT/Coinbase), 'oanda' for forex, or 'hybrid' for multiple sources.",
    BROKER_MODE: "Where orders are sent: 'primary' (IBKR), 'alternative' (crypto exchanges), 'oanda' for forex, or 'hybrid' for smart routing.",
    ALTERNATIVE_MARKET_DATA: "Backup data source if primary fails: 'mock' for testing, 'coinbase'/'ccxt' for crypto, 'oanda' for forex.",
    ALTERNATIVE_BROKER: "Backup broker if primary is unavailable: 'mock' for simulation, 'ccxt' for crypto, 'oanda' for forex.",

    // AI Settings
    TRADE_SCI_PROVIDER: "AI service for market analysis: 'gemini' (Google), 'openai' (GPT-4), 'claude' (Anthropic), 'deepseek', or 'openrouter' for multiple models.",
    TRADE_SCI_MODEL_NAME: "Specific AI model to use. Different models have different capabilities and costs. Default is optimized for trading analysis.",
    CHATGPT_KEY: "API key for your chosen AI provider. Get this from their developer portal. Required for AI-powered commentary.",
    AI_TEMPERATURE: "AI creativity level (0-2). Lower = more consistent/predictable responses. Higher = more creative but potentially erratic. 0.2 recommended.",
    AI_MAX_TOKENS: "Maximum response length from AI. Higher = more detailed analysis but costs more. 2048 is good for trading commentary.",
    COMMENTARY_LLM_POLICY: "When to request AI analysis: 'a_plus_or_4x' for best setups or 4x daily, 'a_plus_only' for only exceptional setups, 'interval' for fixed schedule.",
    COMMENTARY_LLM_DAILY_SLOTS: "Specific times to request AI commentary (HH:MM format). Example: 09:00,12:00,18:00 for market open, midday, and close.",
    COMMENTARY_LLM_MAX_CALLS_PER_DAY: "Maximum AI API calls per day. Prevents runaway costs. Each call provides fresh market analysis.",

    // Sabbath Settings
    SABBATH_ENABLED: "Block new trade entries during the Jewish Sabbath (Friday sunset to Saturday sunset). Existing positions are managed but no new trades opened.",
    SABBATH_ASTRONOMICAL: "Calculate Sabbath times using actual sunset based on your location, rather than fixed clock times. More accurate for religious observance.",
    SABBATH_TIMEZONE: "Your timezone for Sabbath calculations. Use IANA format like 'America/New_York' or 'Europe/London'.",
    SABBATH_LAT: "Your latitude for astronomical sunset calculations. Positive for North, negative for South. Example: 40.7128 for New York City.",
    SABBATH_LON: "Your longitude for astronomical calculations. Negative for West, positive for East. Example: -74.0060 for New York City.",
    SABBATH_START_LOCAL: "Fixed start time if not using astronomical mode. Default 18:00 (6 PM) is typical Friday evening start.",
    SABBATH_END_LOCAL: "Fixed end time if not using astronomical mode. Default 18:00 Saturday is about an hour after sunset in most locations.",

    // Session Settings
    SESSION_GATE_ENABLED: "Only allow trading during active market sessions. Prevents trading during low-liquidity periods.",
    SESSION_OVERLAP_START_HOUR: "Hour when active trading session starts (0-23). 12 = noon. Best to trade when major markets overlap.",
    SESSION_OVERLAP_END_HOUR: "Hour when active trading session ends (0-23). 16 = 4 PM. Position management continues after this.",
    SESSION_OVERLAP_TIMEZONE: "Timezone for session hours. UTC is universal, or use your local timezone.",
    AUTO_SCHEDULE_ENABLED: "Automatically switch between equity hours (9:30-4 ET) and crypto (24/7) based on what you're trading.",
    SUPPLY_DEMAND: "Identifies areas where large institutional orders are likely waiting. The bot looks for a 'Break of Structure' (BOS) indicating a new trend, then waits for price to return to the 'Base' (Supply or Demand zone) before entering. High-accuracy institutional method.",

    // Safety & Shields
    SAFETY_FLOOR_ENABLED: "Staircase Floor Protection. Implements the 'No Body Close' rule (zones invalidated if a candle closes inside) and locks in principal at major account milestones.",
    SAFETY_ATR_SHIELD_ENABLED: "Advanced ATR Armor. Automatically moves stops to breakeven after a 1x ATR move and activates dynamic 5% trailing stops from peak profit to lock in gains.",
    SAFETY_DRAWDOWN_BREAKER_ENABLED: "Drawdown Circuit Breaker. If the account loses >5% from its daily high-water mark, all positions are flattened and the bot is paused for 24 hours to prevent tilt.",
    SAFETY_SESSION_LOCKOUT_ENABLED: "Time-based Safety. Automatically stops new trade entries after a specific hour (default 12:00 PM EST) to avoid low-liquidity and high-volatility session closes.",
    SAFETY_SESSION_LOCKOUT_HOUR: "The hour (0-23) in EST at which the bot will stop taking new trades. Default is 12 (Noon EST).",
};

// ═══════════════════════════════════════════════════════════
// STRATEGY DEFINITIONS with detailed descriptions
// ═══════════════════════════════════════════════════════════

const STRATEGIES = {
    rubberband_reaper: {
        name: "Rubberband Reaper",
        shortDesc: "Anti-Martingale Mean Reversion",
        description: "Uses Bollinger Bands and RSI to catch price reversals at extremes. Features intelligent tiered risk management that INCREASES position size after wins and DECREASES after losses. Targets the opposite Bollinger Band for 3:1+ reward-to-risk ratios.",
        style: "Mean Reversion",
        risk: "Adaptive",
        bestFor: "Ranging markets, volatile assets",
        stats: { verified: "+7,036%", winRate: "39%", riskReward: "3.7:1" }
    },
    robocop: {
        name: "RoboCop",
        shortDesc: "Aggressive High-Frequency ICC",
        description: "Lightning-fast execution with minimal confirmation requirements. Reacts to ANY valid micro-signal without waiting for corrections. Uses 1-bar confirmation and targets 3.0 ATR for maximum profit potential. Includes fast 'chop exit' to avoid ranging traps.",
        style: "Aggressive Scalping",
        risk: "High",
        bestFor: "Trending markets, high volatility",
        stats: { speed: "Ultra-fast", confirmation: "1 bar", target: "3.0 ATR" }
    },
    evolution: {
        name: "Robot Evolution",
        shortDesc: "NTZ Range Scalper",
        description: "Optimized for choppy, ranging markets. Identifies the 'No-Trade-Zone' (NTZ) between swing highs and lows, then trades liquidity sweeps at the edges. Targets 2.0R with conservative 1.5 ATR stops for consistent small wins.",
        style: "Range Trading",
        risk: "Low-Medium",
        bestFor: "Sideways markets, consolidation phases",
        stats: { target: "2.0R", stop: "1.5 ATR", focus: "NTZ edges" }
    },
    quantum: {
        name: "Quantum",
        shortDesc: "Trend-Following with SMA Pullback",
        description: "Classic trend-following strategy that waits for price to pull back to the 20-period SMA before entering in the trend direction. Requires HTF/LTF alignment for high-probability entries. Exits automatically when the higher timeframe trend flips.",
        style: "Trend Following",
        risk: "Medium",
        bestFor: "Strong trending forex pairs",
        stats: { target: "1.6R", stop: "2.5 ATR", indicator: "20 SMA" }
    },
    mean_reversion: {
        name: "Mean Reversion",
        shortDesc: "Bollinger + RSI Extremes",
        description: "Enters when price breaks outside Bollinger Bands (15-period, 2.5 std) with RSI confirmation of oversold (<25) or overbought (>75). Supports pyramiding with 6-bar cooldown between adds. Simple but effective for ranging markets.",
        style: "Mean Reversion",
        risk: "Medium",
        bestFor: "Ranging crypto and forex",
        stats: { bands: "15p/2.5σ", rsi: "<25/>75", pyramid: "6-bar cool" }
    },
    hyper_scalper: {
        name: "HyperScalper",
        shortDesc: "EMA Crossover Speed Trading",
        description: "High-frequency 5-minute scalper using 9/21 EMA crossovers filtered by 200 EMA trend and RSI. Designed for aggressive compounding with 1% default risk per trade. Targets 3.0 ATR for 100%+ weekly return potential.",
        style: "Fast Scalping",
        risk: "High",
        bestFor: "Liquid forex pairs, fast markets",
        stats: { ema: "9/21/200", target: "3.0 ATR", risk: "1%" }
    },
    london_breakout: {
        name: "London Breakout",
        shortDesc: "Session Opening Range",
        description: "Trades the breakout of the first hour of London session (08:00-09:00 GMT). Waits for the range to establish, then enters on breakout of the high or low before noon. Classic institutional strategy with 1.5R targets.",
        style: "Breakout",
        risk: "Medium",
        bestFor: "GBP pairs, European session",
        stats: { session: "08:00-12:00", target: "1.5R", window: "London" }
    },
    volatility_breakout: {
        name: "Volatility Breakout",
        shortDesc: "Range Expansion Momentum",
        description: "Catches explosive moves when price breaks out of a 20-period range with RSI confirmation (>60 long, <40 short). Features fast momentum exit when RSI reverses. Great for catching the start of new trends.",
        style: "Breakout",
        risk: "Medium-High",
        bestFor: "Any market showing compression",
        stats: { range: "20 periods", target: "2.0R", rsi: ">60/<40" }
    },
    aggregator: {
        name: "Singularity Aggregator",
        shortDesc: "Multi-Strategy Parallel",
        description: "Runs Mean Reversion + HyperScalper simultaneously for maximum capital utilization. Prioritizes scale-ins on existing winners, then new entries. Keeps the bot 'always loaded' for potential 400%+ returns by never missing opportunities.",
        style: "Multi-Strategy",
        risk: "Variable",
        bestFor: "Maximizing capital efficiency",
        stats: { strategies: "2 parallel", priority: "Scale > New", goal: "Always loaded" }
    },
    icc_core: {
        name: "Indication, Correction, Continuation (ICC)",
        shortDesc: "Strict Trade By Sci Logic",
        description: "The pure, unmodified Trade By Sci Internal Capital Cycle methodology. Requires strict HTF/LTF alignment and follows the standard Indication (Sweep) -> Correction -> Continuation sequence. No Rubberband logic, no RoboCop bypasses. Pure Price Action.",
        style: "Trend Following",
        risk: "Low-Medium",
        bestFor: "Aligned Trends",
        stats: { alignment: "Strict", structure: "Standard", method: "Vanilla" }
    },
    supply_demand: {
        name: "Supply & Demand",
        shortDesc: "Institutional Price Action",
        description: "Uses the pure institutional methodology of Supply and Demand zones. It waits for a clear Break of Structure to identify a trend, then tags the 'Base' candle that caused the move as a high-probability zone. Enters only when price returns to 'tap' that zone on a candle break.",
        style: "Price Action / Institutional",
        risk: "Low-Medium",
        bestFor: "Clean trending markets, high-volume crypto",
        stats: { method: "SND Zones", confirmation: "Zone Tap", trend: "BOS Based" }
    }
};

// Asset class definitions for strategy assignment
const ASSET_CLASSES = [
    { id: 'crypto', name: 'Cryptocurrency', icon: 'currency_bitcoin', subtitle: 'BTC, ETH, altcoins', envKey: 'STRATEGY_CRYPTO' },
    { id: 'forex', name: 'Forex', icon: 'currency_exchange', subtitle: 'EUR/USD, GBP/JPY, etc.', envKey: 'STRATEGY_FOREX' },
    { id: 'stocks', name: 'Stocks', icon: 'monitoring', subtitle: 'Individual equities', envKey: 'STRATEGY_STOCKS' },
    { id: 'etf', name: 'ETFs', icon: 'analytics', subtitle: 'SPY, QQQ, sector funds', envKey: 'STRATEGY_ETF' },
    { id: 'metals', name: 'Precious Metals', icon: 'diamond', subtitle: 'Gold, Silver, Platinum', envKey: 'STRATEGY_METALS' },
    { id: 'futures', name: 'Futures', icon: 'schedule', subtitle: 'ES, NQ, commodities', envKey: 'STRATEGY_FUTURES' }
];

// Helper to format camelCase/snake_case to Title Case
function formatStatKey(key) {
    return key
        .replace(/([A-Z])/g, ' $1')  // camelCase to spaces
        .replace(/_/g, ' ')           // snake_case to spaces
        .replace(/^\w/, c => c.toUpperCase())  // Capitalize first letter
        .trim();
}

const TABS = {
    system: { icon: 'dashboard', label: 'System', render: renderSystemTab },
    strategy: { icon: 'precision_manufacturing', label: 'Strategy', render: renderStrategyTab },
    brokers: { icon: 'lan', label: 'Brokers', render: renderBrokersTab },
    ai: { icon: 'auto_awesome', label: 'Intelligence', render: renderAITab },
    schedule: { icon: 'event_repeat', label: 'Schedule', render: renderScheduleTab },
    advanced: { icon: 'terminal', label: 'Advanced', render: renderAdvancedTab }
};

// ═══════════════════════════════════════════════════════════
// INITIALIZATION
// ═══════════════════════════════════════════════════════════

async function init() {
    setupGlobalEvents();

    // Listen for bot status updates
    if (window.electronAPI?.onBotStatus) {
        window.electronAPI.onBotStatus((status) => {
            updateBotStatusUI(status.running);
        });
        // Initial check
        window.electronAPI.getBotStatus();
    }

    // Load data from backend
    try {
        if (window.electronAPI) {
            envData = await window.electronAPI.readEnv() || {};
            profilesContent = await window.electronAPI.readProfiles() || "";
        }
    } catch (e) {
        console.error("Data load failed:", e);
    }

    switchTab('system');
}

function setupGlobalEvents() {
    // Navigation buttons
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });

    // Window controls (with safety checks)
    const btnClose = document.getElementById('btn-close');
    const btnMinimize = document.getElementById('btn-minimize');
    const btnSave = document.getElementById('btn-save');
    const btnRevert = document.getElementById('btn-revert');
    const searchInput = document.getElementById('setting-search');

    if (btnClose) {
        btnClose.addEventListener('click', () => {
            if (window.electronAPI?.closeWindow) {
                window.electronAPI.closeWindow();
            }
        });
    }

    if (btnMinimize) {
        btnMinimize.addEventListener('click', () => {
            if (window.electronAPI?.minimizeWindow) {
                window.electronAPI.minimizeWindow();
            }
        });
    }

    if (btnSave) {
        btnSave.addEventListener('click', saveAll);
    }

    if (btnRevert) {
        btnRevert.addEventListener('click', () => {
            if (confirm("Discard all unsaved changes?")) location.reload();
        });
    }

    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            if (currentTab === 'advanced') renderAdvancedTab(document.getElementById('tab-content'), e.target.value);
        });
    }
}

function getProfileOptions() {
    if (!profilesContent) return [
        { value: 'auto_schedule', label: 'Auto (Equities/Crypto)' },
        { value: 'forex_intraday', label: 'Forex Intraday' },
        { value: 'forex_oanda', label: 'OANDA Forex' },
        { value: 'crypto_247', label: 'Crypto 24/7' },
        { value: 'intraday', label: 'Standard Intraday' },
        { value: 'coinbase_futures', label: 'Coinbase Futures' },
        { value: 'coinbase_futures_nano', label: 'Coinbase Nano Futures' }
    ];

    const options = [];
    const lines = profilesContent.split('\n');
    let inProfiles = false;

    for (let line of lines) {
        if (line.trim().startsWith('profiles:')) {
            inProfiles = true;
            continue;
        }
        if (inProfiles) {
            const match = line.match(/^  ([\w-]+):/);
            if (match) {
                const value = match[1];
                const label = value.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
                    .replace('Forex', 'Forex ').replace('Crypto', 'Crypto ').trim();
                options.push({ value, label });
            }
        }
    }

    return options.length > 0 ? options : [
        { value: 'auto_schedule', label: 'Auto (Equities/Crypto)' },
        { value: 'forex_intraday', label: 'Forex Intraday' },
        { value: 'forex_oanda', label: 'OANDA Forex' },
        { value: 'crypto_247', label: 'Crypto 24/7' },
        { value: 'intraday', label: 'Standard Intraday' },
        { value: 'coinbase_futures', label: 'Coinbase Futures' },
        { value: 'coinbase_futures_nano', label: 'Coinbase Nano Futures' }
    ];
}

/**
 * Get settings from the currently active profile in settings_profiles.yaml.
 * This ensures the Settings UI reflects the actual running configuration.
 */
function getActiveProfileSettings() {
    const activeProfile = envData['APP_PROFILE'] || 'auto_schedule';
    const settings = {
        strategy_variant: 'rubberband_reaper',
        strategies: {}
    };

    if (!profilesContent) return settings;

    const lines = profilesContent.split('\n');
    let inTargetProfile = false;
    let inStrategies = false;

    for (let line of lines) {
        // Match profile start (2 spaces)
        const profileMatch = line.match(/^  ([\w_]+):$/);
        if (profileMatch) {
            inTargetProfile = (profileMatch[1] === activeProfile);
            inStrategies = false;
            continue;
        }

        if (!inTargetProfile) continue;

        // Match property (4 spaces) - strip inline comments
        const propMatch = line.match(/^    ([a-z_]+):\s*(.+)$/);
        if (propMatch) {
            const key = propMatch[1];
            const rawVal = propMatch[2].split('#')[0].trim();

            if (key === 'strategies') {
                inStrategies = true;
                continue;
            }
            inStrategies = false;

            if (key === 'strategy_variant') {
                settings.strategy_variant = rawVal;
            }
        }

        // Match strategy items (6 spaces)
        if (inStrategies) {
            const stratMatch = line.match(/^      ([a-z_]+):\s*(.+)$/);
            if (stratMatch) {
                settings.strategies[stratMatch[1]] = stratMatch[2].split('#')[0].trim();
            }
        }
    }

    return settings;
}

// ═══════════════════════════════════════════════════════════
// NAVIGATION
// ═══════════════════════════════════════════════════════════

function switchTab(tabId) {
    currentTab = tabId;
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tabId);
    });

    const searchContainer = document.getElementById('search-container');
    if (searchContainer) {
        searchContainer.classList.toggle('hidden', tabId !== 'advanced');
    }
    renderTab();
}

function renderTab() {
    const container = document.getElementById('tab-content');
    if (!container) return;
    container.innerHTML = '';

    if (TABS[currentTab]) {
        try {
            TABS[currentTab].render(container);
        } catch (e) {
            console.error("Error rendering tab:", e);
            container.innerHTML = `<div style="color: red; padding: 20px;">Error rendering tab: ${e.message}</div>`;
        }
    } else {
        console.error("[SETTINGS] Tab not found in TABS:", currentTab);
        container.innerHTML = `<div style="color: orange; padding: 20px;">Tab "${currentTab}" not found</div>`;
    }
}

window.setSubTab = (category, tab) => {
    subTabs[category] = tab;
    renderTab();
};

// ═══════════════════════════════════════════════════════════
// UI BUILDERS
// ═══════════════════════════════════════════════════════════

function createSectionHeader(title, icon = null) {
    const header = document.createElement('div');
    header.className = 'settings-label text-glow-teal';
    header.innerHTML = icon
        ? `<span class="material-symbols-outlined">${icon}</span>${title}`
        : title;
    return header;
}

function createCard(title, desc, key, controlType, options = {}) {
    const card = document.createElement('div');
    card.className = 'control-card';
    card.dataset.key = key;

    card.innerHTML = `
        <div class="card-info">
            <span class="card-title">${title}</span>
            <span class="card-desc">${desc}</span>
        </div>
        <div class="card-control no-drag"></div>
    `;

    const controlContainer = card.querySelector('.card-control');
    const value = envData[key] || options.default || '';

    const tooltipContent = options.tooltip || TOOLTIPS[key];
    if (tooltipContent) {
        card.addEventListener('mouseenter', (e) => showTooltip(e, key, tooltipContent));
        card.addEventListener('mouseleave', hideTooltip);
    }

    if (controlType === 'toggle') {
        const toggle = document.createElement('div');
        toggle.className = `toggle ${value === 'true' ? 'toggle-active' : ''}`;
        toggle.addEventListener('click', () => {
            const active = toggle.classList.toggle('toggle-active');
            updateValue(key, active ? 'true' : 'false');
        });
        controlContainer.appendChild(toggle);
    }
    else if (controlType === 'input') {
        const input = document.createElement('input');
        input.type = options.password ? 'password' : (options.number ? 'number' : 'text');
        input.className = 'input-field';
        input.value = value;
        input.placeholder = options.placeholder || '';
        if (options.min !== undefined) input.min = options.min;
        if (options.max !== undefined) input.max = options.max;
        if (options.step !== undefined) input.step = options.step;
        input.addEventListener('change', (e) => updateValue(key, e.target.value));
        controlContainer.appendChild(input);
    }
    else if (controlType === 'dropdown') {
        const select = document.createElement('select');
        select.className = 'input-field appearance-none';
        options.items.forEach(item => {
            const opt = document.createElement('option');
            opt.value = item.value;
            opt.textContent = item.label;
            opt.selected = item.value === value;
            select.appendChild(opt);
        });
        select.addEventListener('change', (e) => updateValue(key, e.target.value));
        controlContainer.appendChild(select);
    }

    return card;
}

function createSliderCard(title, desc, key, min, max, step, unit = '%') {
    const card = document.createElement('div');
    card.className = 'slider-card';
    const value = envData[key] || min;

    card.innerHTML = `
        <div class="slider-header">
            <div>
                <div class="slider-title">${title}</div>
                <div class="slider-desc">${desc}</div>
            </div>
            <div class="slider-value">${value}<span class="slider-value-small">${unit}</span></div>
        </div>
        <input type="range" class="slider-input" min="${min}" max="${max}" step="${step}" value="${value}">
        <div class="slider-key">${key}</div>
    `;

    const slider = card.querySelector('.slider-input');
    const valueDisplay = card.querySelector('.slider-value');

    if (TOOLTIPS[key]) {
        card.addEventListener('mouseenter', (e) => showTooltip(e, key, TOOLTIPS[key]));
        card.addEventListener('mouseleave', hideTooltip);
    }

    slider.addEventListener('input', (e) => {
        valueDisplay.innerHTML = `${e.target.value}<span class="slider-value-small">${unit}</span>`;
        updateValue(key, e.target.value);
    });

    return card;
}

function createSubNav(items, category) {
    const nav = document.createElement('div');
    nav.className = 'sub-nav';

    items.forEach(item => {
        const btn = document.createElement('button');
        btn.className = `sub-nav-btn ${subTabs[category] === item.id ? 'active' : ''}`;
        btn.textContent = item.label;
        btn.onclick = () => setSubTab(category, item.id);
        nav.appendChild(btn);
    });

    return nav;
}

function createDivider() {
    const div = document.createElement('div');
    div.className = 'section-divider';
    return div;
}

function createWarningBox(text) {
    const box = document.createElement('div');
    box.className = 'warning-box';
    box.innerHTML = `
        <span class="material-symbols-outlined">warning</span>
        <div class="warning-box-content">${text}</div>
    `;
    return box;
}

// ═══════════════════════════════════════════════════════════
// TAB RENDERERS
// ═══════════════════════════════════════════════════════════

function renderSystemTab(container) {
    const section = document.createElement('div');
    section.className = 'settings-section';

    // Sync envData with active profile settings so UI reflects actual config
    // Profile settings are authoritative - always prefer them over .env values
    const profileSettings = getActiveProfileSettings();
    if (profileSettings.strategy_variant) {
        envData['STRATEGY_VARIANT'] = profileSettings.strategy_variant;
    }
    // Also sync per-asset strategies
    const assetKeyMap = { crypto: 'STRATEGY_CRYPTO', forex: 'STRATEGY_FOREX', stocks: 'STRATEGY_STOCKS', etf: 'STRATEGY_ETF', metals: 'STRATEGY_METALS', futures: 'STRATEGY_FUTURES' };
    for (const [asset, envKey] of Object.entries(assetKeyMap)) {
        if (profileSettings.strategies[asset]) {
            envData[envKey] = profileSettings.strategies[asset];
        } else if (profileSettings.strategy_variant) {
            envData[envKey] = profileSettings.strategy_variant; // Fallback to default
        }
    }

    // Core Runtime
    section.appendChild(createSectionHeader('Core Runtime', 'dashboard'));

    section.appendChild(createCard('Active Profile', 'Select symbol universe & trading cadence', 'APP_PROFILE', 'dropdown', {
        items: getProfileOptions()
    }));

    section.appendChild(createCard('Strategy Variant', 'Trading strategy algorithm', 'STRATEGY_VARIANT', 'dropdown', {
        items: [
            { value: 'rubberband_reaper', label: 'Rubberband Reaper (Anti-Martingale)' },
            { value: 'robocop', label: 'RoboCop (Aggressive ICC)' },
            { value: 'evolution', label: 'Robot Evolution (NTZ Scalper)' },
            { value: 'quantum', label: 'Quantum (Trend Following)' },
            { value: 'mean_reversion', label: 'Mean Reversion (Bollinger/RSI)' },
            { value: 'hyper_scalper', label: 'HyperScalper (EMA Crossover)' },
            { value: 'london_breakout', label: 'London Breakout (Session)' },
            { value: 'volatility_breakout', label: 'Volatility Breakout' },
            { value: 'aggregator', label: 'Singularity Aggregator (Multi-Strategy)' },
            { value: 'icc_core', label: 'ICC (Indication, Correction, Continuation)' },
            { value: 'supply_demand', label: 'Supply & Demand (Institutional)' }
        ],
        default: 'rubberband_reaper'
    }));

    section.appendChild(createCard('Execution Mode', 'How the bot cycles through iterations', 'BOT_MODE', 'dropdown', {
        items: [
            { value: 'continuous', label: 'Continuous Loop' },
            { value: 'scheduled', label: 'Session Windows' },
            { value: 'iterations', label: 'Fixed Iterations' }
        ]
    }));

    section.appendChild(createCard('Live Trading', 'Master switch for real order execution', 'EXECUTE_TRADES', 'toggle'));
    section.appendChild(createCard('Auto-Start Bot', 'Launch bot automatically with GUI', 'GUI_AUTOSTART_BOT', 'toggle', { default: 'true' }));
    section.appendChild(createCard('Continuous Mode', 'Keep runtime alive indefinitely', 'CONTINUOUS_MODE', 'toggle'));
    section.appendChild(createCard('Friday Fade Damper', 'Risk cap after 12:00 PM EST Fri (Forex Only)', 'FRIDAY_FADE_ENABLED', 'toggle', { default: 'true' }));
    section.appendChild(createCard('WebConnect URL', 'Remote bot connection address', 'GUI_WS_URL', 'input', { default: 'ws://localhost:8080/ws' }));
    section.appendChild(createCard('Bot Listening Port', 'Port the bot server listens on', 'WS_SERVER_PORT', 'input', { default: '8080' }));

    section.appendChild(createDivider());

    // Runtime Control (Start/Stop/Restart)
    section.appendChild(createSectionHeader('Runtime Control', 'play_circle'));

    const controlGrid = document.createElement('div');
    controlGrid.className = 'card-grid card-grid-3 mb-8';

    const btnStart = createControlButton('Start Bot', 'play_arrow', 'teal', () => {
        window.electronAPI.startBot();
        showNotice('Bot start command sent', 'teal');
    });
    const btnStop = createControlButton('Stop Bot', 'stop', 'red', () => {
        window.electronAPI.stopBot();
        showNotice('Bot stop command sent', 'red');
    });
    const btnRestart = createControlButton('Restart', 'refresh', 'purple', () => {
        window.electronAPI.restartBot();
        showNotice('Bot restart sequence initiated', 'purple');
    });

    controlGrid.appendChild(btnStart);
    controlGrid.appendChild(btnStop);
    controlGrid.appendChild(btnRestart);
    section.appendChild(controlGrid);

    section.appendChild(createDivider());

    // Timeframes
    section.appendChild(createSectionHeader('Timeframes', 'schedule'));

    section.appendChild(createCard('Candle Timeframe', 'Primary data timeframe', 'CANDLE_TIMEFRAME', 'dropdown', {
        items: [
            { value: '1m', label: '1 Minute' },
            { value: '5m', label: '5 Minutes' },
            { value: '15m', label: '15 Minutes' },
            { value: '1h', label: '1 Hour' },
            { value: '4h', label: '4 Hours' }
        ],
        default: '15m'
    }));

    section.appendChild(createCard('HTF Timeframe', 'Higher timeframe for trend analysis', 'HTF_TIMEFRAME', 'dropdown', {
        items: [
            { value: '15m', label: '15 Minutes' },
            { value: '1h', label: '1 Hour' },
            { value: '4h', label: '4 Hours' },
            { value: '1d', label: 'Daily' }
        ],
        default: '1h'
    }));

    section.appendChild(createCard('LTF Timeframe', 'Lower timeframe for entry precision', 'LTF_TIMEFRAME', 'dropdown', {
        items: [
            { value: '1m', label: '1 Minute' },
            { value: '5m', label: '5 Minutes' },
            { value: '15m', label: '15 Minutes' }
        ],
        default: '5m'
    }));

    section.appendChild(createDivider());

    // Trend Detection
    section.appendChild(createSectionHeader('Trend Detection', 'trending_up'));

    section.appendChild(createCard('Trend Window', 'Candles for HTF trend analysis', 'TREND_WINDOW', 'input', { number: true, default: '12', min: 5, max: 50 }));
    section.appendChild(createCard('LTF Trend Window', 'Candles for LTF trend analysis', 'LTF_TREND_WINDOW', 'input', { number: true, default: '8', min: 3, max: 30 }));
    section.appendChild(createCard('Swing Lookback', 'Fractal lookback for swing detection', 'TREND_SWING_LOOKBACK', 'input', { number: true, default: '2', min: 1, max: 5 }));
    section.appendChild(createCard('Min Swings', 'Minimum swings for trend classification', 'TREND_MIN_SWINGS', 'input', { number: true, default: '2', min: 1, max: 5 }));
    section.appendChild(createCard('Strength Floor', 'Minimum strength for non-neutral trend', 'TREND_STRENGTH_FLOOR', 'input', { number: true, default: '0.25', min: 0, max: 1, step: 0.05 }));

    container.appendChild(section);
}


function renderStrategyTab(container) {
    // Sync envData with active profile settings so UI reflects actual config
    // Profile settings are authoritative - always prefer them over .env values
    const profileSettings = getActiveProfileSettings();
    const assetKeyMap = { crypto: 'STRATEGY_CRYPTO', forex: 'STRATEGY_FOREX', stocks: 'STRATEGY_STOCKS', etf: 'STRATEGY_ETF', metals: 'STRATEGY_METALS', futures: 'STRATEGY_FUTURES' };
    for (const [asset, envKey] of Object.entries(assetKeyMap)) {
        if (profileSettings.strategies[asset]) {
            envData[envKey] = profileSettings.strategies[asset];
        } else if (profileSettings.strategy_variant) {
            envData[envKey] = profileSettings.strategy_variant; // Fallback to default
        }
    }

    // Sub-navigation
    container.appendChild(createSubNav([
        { id: 'assets', label: 'Asset Strategies' },
        { id: 'toolbox', label: 'Strategy Toolbox' },
        { id: 'risk', label: 'Global Risk' },
        { id: 'pyramid', label: 'Pyramiding' },
        { id: 'exits', label: 'Exit Logic' },
        { id: 'yaml', label: 'YAML Editor' }
    ], 'strategy'));

    const section = document.createElement('div');
    section.className = 'settings-section';

    if (subTabs.strategy === 'assets') {
        section.appendChild(createSectionHeader('Strategy per Asset Class', 'precision_manufacturing'));

        // Intro text
        const intro = document.createElement('div');
        intro.className = 'strategy-intro';
        intro.innerHTML = `
            <p style="color: var(--text-secondary); font-size: 13px; line-height: 1.7; margin-bottom: 24px;">
                Choose which trading strategy to use for each asset class. Each strategy has different strengths —
                some excel in trending markets, others in ranging conditions. Read the descriptions to find the best fit.
            </p>
        `;
        section.appendChild(intro);

        // Create a card for each asset class
        ASSET_CLASSES.forEach(asset => {
            const card = document.createElement('div');
            card.className = 'asset-strategy-card';

            // Get current strategy for this asset
            const currentStrategy = envData[asset.envKey] || 'rubberband_reaper';
            const strategyInfo = STRATEGIES[currentStrategy] || STRATEGIES.rubberband_reaper;

            card.innerHTML = `
                <div class="asset-header">
                    <div class="asset-icon ${asset.id}">
                        <span class="material-symbols-outlined">${asset.icon}</span>
                    </div>
                    <div>
                        <div class="asset-title">${asset.name}</div>
                        <div class="asset-subtitle">${asset.subtitle}</div>
                    </div>
                </div>
                <div class="strategy-select-wrapper">
                    <select class="input-field" data-env-key="${asset.envKey}">
                        ${Object.entries(STRATEGIES).map(([key, strat]) => `
                            <option value="${key}" ${key === currentStrategy ? 'selected' : ''}>
                                ${strat.name} — ${strat.shortDesc}
                            </option>
                        `).join('')}
                    </select>
                </div>
                <div class="strategy-description" data-desc-for="${asset.envKey}">
                    <strong>${strategyInfo.style} • ${strategyInfo.risk} Risk</strong>
                    ${strategyInfo.description}
                    <div class="strategy-best-for">Best for: <em>${strategyInfo.bestFor}</em></div>
                    <div class="strategy-stats">
                        ${Object.entries(strategyInfo.stats || {}).map(([k, v]) => `
                            <div class="strategy-stat">${formatStatKey(k)}: <span>${v}</span></div>
                        `).join('')}
                    </div>
                </div>
            `;

            // Handle strategy selection change
            const select = card.querySelector('select');
            select.addEventListener('change', (e) => {
                const newStrategy = e.target.value;
                const newInfo = STRATEGIES[newStrategy];

                // Update the description
                const descBox = card.querySelector('.strategy-description');
                descBox.innerHTML = `
                    <strong>${newInfo.style} • ${newInfo.risk} Risk</strong>
                    ${newInfo.description}
                    <div class="strategy-best-for">Best for: <em>${newInfo.bestFor}</em></div>
                    <div class="strategy-stats">
                        ${Object.entries(newInfo.stats || {}).map(([k, v]) => `
                            <div class="strategy-stat">${formatStatKey(k)}: <span>${v}</span></div>
                        `).join('')}
                    </div>
                `;

                // Save the value
                updateValue(asset.envKey, newStrategy);
            });

            section.appendChild(card);
        });

    } else if (subTabs.strategy === 'toolbox') {
        // Delegate to specific toolbox renderer
        renderStrategyToolbox(container);
        return;

    } else if (subTabs.strategy === 'risk') {
        section.appendChild(createSectionHeader('Global Risk Limits', 'account_balance'));

        section.appendChild(createWarningBox('<strong>Note:</strong> These are global defaults and safety limits. Individual strategies in the <strong>Strategy Toolbox</strong> may override specific risk parameters (e.g. higher risk for high-probability setups).'));

        // Slider Grid
        const grid = document.createElement('div');
        grid.className = 'card-grid';
        grid.appendChild(createSliderCard('Default Risk %', 'Fallback equity risk', 'RISK_PER_TRADE_PCT', 0.1, 5.0, 0.1, '%'));
        grid.appendChild(createSliderCard('Short Risk', 'Risk for short positions', 'SHORT_RISK_PCT', 0.1, 5.0, 0.1, '%'));
        grid.appendChild(createSliderCard('Max Exposure', 'Total open risk limit', 'MAX_EXPOSURE_PCT', 5, 100, 5, '%'));
        grid.appendChild(createSliderCard('Max Daily Loss', 'Daily loss circuit breaker', 'MAX_DAILY_LOSS_PCT', 1, 20, 1, '%'));
        section.appendChild(grid);

        section.appendChild(createCard('Fixed Risk ($)', 'Fixed dollar risk (overrides %)', 'RISK_PER_TRADE_DOLLARS', 'input', { number: true, placeholder: '0.00' }));
        section.appendChild(createCard('Max Loss Per Trade ($)', 'Hard cap per trade', 'MAX_LOSS_PER_TRADE_DOLLARS', 'input', { number: true, default: '500' }));

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('Position Management', 'layers'));

        section.appendChild(createCard('Multi-Position', 'Trade multiple symbols simultaneously', 'MULTI_POSITION_ENABLED', 'toggle'));
        section.appendChild(createCard('Max Concurrent Positions', 'Maximum open positions', 'MAX_CONCURRENT_POSITIONS', 'input', { number: true, default: '1', min: 1, max: 10 }));
        section.appendChild(createCard('Smart Positions', 'Fund new risk with open profits', 'SMART_POSITIONS_ENABLED', 'toggle'));

        // Initialize Financed Risk state
        setTimeout(() => {
            const multiEnabled = envData['MULTI_POSITION_ENABLED'] === 'true';
            const smartToggle = section.querySelector('.control-card[data-key="SMART_POSITIONS_ENABLED"]');
            if (smartToggle && !multiEnabled) {
                smartToggle.classList.add('opacity-50', 'pointer-events-none');
            }
        }, 0);

    } else if (subTabs.strategy === 'pyramid') {
        section.appendChild(createSectionHeader('Pyramid Configuration', 'stacked_line_chart'));

        section.appendChild(createCard('Max Pyramid Entries', 'Total entries per position', 'MAX_PYRAMID_ENTRIES', 'input', { number: true, default: '6', min: 1, max: 20 }));
        section.appendChild(createCard('Profit Buffer %', 'Min profit before first add', 'PYRAMID_PROFIT_BUFFER_PCT', 'input', { number: true, default: '0.0015', min: 0, max: 0.05, step: 0.0005 }));

        const pyramidGrid = document.createElement('div');
        pyramidGrid.className = 'card-grid';
        pyramidGrid.appendChild(createSliderCard('Load Risk', 'First add risk %', 'PYRAMID_RISK_LOAD', 5, 100, 5, '%'));
        pyramidGrid.appendChild(createSliderCard('Scale Risk', 'Subsequent adds risk %', 'PYRAMID_RISK_SCALE', 5, 50, 5, '%'));
        section.appendChild(pyramidGrid);

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('Breakeven Trail', 'shield'));

        section.appendChild(createCard('Trail After N Pyramids', '0 = disabled', 'BREAKEVEN_TRAIL_AFTER_PYRAMIDS', 'input', { number: true, default: '1', min: 0, max: 10 }));
        section.appendChild(createCard('Trail Percentage', 'Above breakeven (0.003 = 0.3%)', 'BREAKEVEN_TRAIL_PCT', 'input', { number: true, default: '0.003', min: 0, max: 0.05, step: 0.001 }));

    } else if (subTabs.strategy === 'exits') {
        section.appendChild(createSectionHeader('Exit Configuration', 'exit_to_app'));

        section.appendChild(createCard('HTF Flip Exit (Loss Only)', 'Exit on flip only if losing', 'EXIT_ON_HTF_FLIP_ONLY_IF_LOSING', 'toggle', { default: 'true' }));
        section.appendChild(createCard('Auto-Flatten on Close', 'Flatten positions at session end', 'AUTO_FLATTEN_ON_CLOSE', 'toggle'));

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('Trailing Stop', 'trending_down'));

        section.appendChild(createCard('Trailing Stop Enabled', 'Enable trailing stop logic', 'TRAILING_STOP_ENABLED', 'toggle'));
        section.appendChild(createCard('Min Profit to Trail', 'Activate at this profit %', 'TRAILING_STOP_MIN_PROFIT_PCT', 'input', { number: true, default: '1.0', min: 0, max: 10, step: 0.5 }));
        section.appendChild(createCard('Stop ATR Multiplier', 'Distance from structure', 'STOP_ATR_MULTIPLIER', 'input', { number: true, default: '1.5', min: 0.5, max: 3, step: 0.1 }));

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('Hold Time Rules', 'timer'));

        section.appendChild(createCard('Min Hold Hours', '0 = disabled', 'MIN_HOLD_HOURS', 'input', { number: true, default: '0', min: 0, max: 48 }));
        section.appendChild(createCard('Max Hold Hours', '0 = disabled', 'MAX_HOLD_HOURS', 'input', { number: true, default: '0', min: 0, max: 168 }));
        section.appendChild(createCard('HTF Neutral Exit Bars', 'Exit after N neutral bars', 'HTF_NEUTRAL_EXIT_BARS', 'input', { number: true, default: '48', min: 0, max: 200 }));

    } else if (subTabs.strategy === 'yaml') {
        section.appendChild(createSectionHeader('Profiles YAML Editor', 'code'));
        section.appendChild(createWarningBox('<strong>Warning:</strong> Direct YAML editing. Invalid syntax will break the bot. Use the other tabs for safer configuration.'));

        const editor = document.createElement('textarea');
        editor.id = 'profiles-editor';
        editor.value = profilesContent;
        editor.addEventListener('input', (e) => {
            profilesContent = e.target.value;
            localChanges['_profiles_'] = true;
            updateChangeCounter();
        });
        section.appendChild(editor);
    }

    container.appendChild(section);
}

function renderBrokersTab(container) {
    // Sub-navigation
    container.appendChild(createSubNav([
        { id: 'ibkr', label: 'Interactive Brokers' },
        { id: 'oanda', label: 'OANDA Forex' },
        { id: 'gemini', label: 'Gemini.com' },
        { id: 'kraken', label: 'Kraken' },
        { id: 'paxos', label: 'Paxos (Crypto)' },
        { id: 'ccxt', label: 'Coinbase / CCXT' },
        { id: 'routing', label: 'Data Routing' }
    ], 'brokers'));

    const section = document.createElement('div');
    section.className = 'settings-section';

    if (subTabs.brokers === 'ibkr') {
        section.appendChild(createSectionHeader('IBKR Connection', 'lan'));

        section.appendChild(createCard('Host', 'TWS/Gateway IP address', 'IBKR_HOST', 'input', { default: '127.0.0.1' }));
        section.appendChild(createCard('Port', '7497 (Paper) / 4001 (Live Gateway)', 'IBKR_PORT', 'input', { number: true, default: '7497' }));
        section.appendChild(createCard('Client ID', 'Unique connection identifier', 'IBKR_CLIENT_ID', 'input', { number: true, default: '1' }));
        section.appendChild(createCard('Account ID', 'Specific sub-account', 'IBKR_ACCOUNT_ID', 'input'));
        section.appendChild(createCard('Paper Trading', 'Use paper trading mode', 'IBKR_PAPER', 'toggle', { default: 'true' }));
        section.appendChild(createCard('Read Only', 'Monitor mode only (no orders)', 'IBKR_READ_ONLY', 'toggle'));
        section.appendChild(createCard('Default Currency', 'Base currency for positions', 'IBKR_DEFAULT_CCY', 'input', { default: 'USD' }));

    } else if (subTabs.brokers === 'oanda') {
        section.appendChild(createSectionHeader('OANDA Forex Connection', 'currency_exchange'));

        section.appendChild(createCard('Account ID', 'Your OANDA account number', 'OANDA_ACCOUNT_ID', 'input', { placeholder: '101-001-1234567-001' }));
        section.appendChild(createCard('API Key', 'OANDA API access token', 'OANDA_API_KEY', 'input', { password: true }));
        section.appendChild(createCard('Environment', 'Trading environment', 'OANDA_ENVIRONMENT', 'dropdown', {
            items: [
                { value: 'practice', label: 'Practice (Demo)' },
                { value: 'live', label: 'Live (Real Money)' }
            ],
            default: 'practice'
        }));
        section.appendChild(createCard('Read Only', 'Monitor only (no trading)', 'OANDA_READ_ONLY', 'toggle', { default: 'true' }));

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('OANDA Info', 'info'));

        const infoBox = document.createElement('div');
        infoBox.className = 'warning-box';
        infoBox.style.borderColor = 'rgba(20, 184, 166, 0.3)';
        infoBox.innerHTML = `
            <span class="material-symbols-outlined" style="color: var(--accent);">lightbulb</span>
            <div class="warning-box-content">
                <strong>Getting Started with OANDA:</strong><br>
                1. Create an OANDA account at oanda.com<br>
                2. Go to "Manage API Access" in your account settings<br>
                3. Generate a new API token and copy it here<br>
                4. Your Account ID is shown in your account dashboard<br>
                5. Always test with Practice mode first!
            </div>
        `;
        section.appendChild(infoBox);

    } else if (subTabs.brokers === 'gemini') {
        section.appendChild(createSectionHeader('Gemini.com Connection', 'security'));

        section.appendChild(createCard('API Key', 'Gemini Master Key', 'GEMINI_API_KEY', 'input', { password: true }));
        section.appendChild(createCard('API Secret', 'Gemini Secret', 'GEMINI_API_SECRET', 'input', { password: true }));
        section.appendChild(createCard('Sandbox Mode', 'Use Gemini Exchange Testnet', 'GEMINI_SANDBOX', 'toggle', { default: 'false' }));

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('Gemini Info', 'info'));

        const geminiInfo = document.createElement('div');
        geminiInfo.className = 'warning-box';
        geminiInfo.style.borderColor = 'rgba(20, 184, 166, 0.3)';
        geminiInfo.innerHTML = `
            <span class="material-symbols-outlined" style="color: var(--accent);">info</span>
            <div class="warning-box-content">
                <strong>Configuring Gemini Trading:</strong><br>
                1. Log in to your account at gemini.com<br>
                2. Navigate to <strong>Settings -> API</strong><br>
                3. Create a new API Key with "Trading" permissions enabled<br>
                4. Paste your Key and Secret here<br>
                5. Important: Set <strong>Data Routing</strong> to use Gemini for Crypto.
            </div>
        `;
        section.appendChild(geminiInfo);

    } else if (subTabs.brokers === 'kraken') {
        section.appendChild(createSectionHeader('Kraken Connection', 'account_balance_wallet'));

        section.appendChild(createCard('API Key', 'Kraken API Key', 'KRAKEN_API_KEY', 'input', { password: true }));
        section.appendChild(createCard('API Secret', 'Kraken API Secret', 'KRAKEN_API_SECRET', 'input', { password: true }));
        section.appendChild(createCard('Environment', 'Trading Environment', 'KRAKEN_ENVIRONMENT', 'dropdown', {
            items: [
                { value: 'production', label: 'Production (Live)' },
                { value: 'sandbox', label: 'Sandbox (Test)' }
            ],
            default: 'production'
        }));

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('Kraken Info', 'info'));
        const krakenInfo = document.createElement('div');
        krakenInfo.className = 'warning-box';
        krakenInfo.style.borderColor = 'rgba(20, 184, 166, 0.3)';
        krakenInfo.innerHTML = `
            <span class="material-symbols-outlined" style="color: var(--accent);">info</span>
            <div class="warning-box-content">
                <strong>Configuring Kraken Trading:</strong><br>
                1. Log in to your Kraken account<br>
                2. Navigate to <strong>Security -> API</strong><br>
                3. Create a new API Key with appropriate permissions<br>
                4. Paste your Key and Private Key (Secret) here<br>
                5. Note: Set <strong>Data Routing</strong> to use Kraken for Crypto.
            </div>
        `;
        section.appendChild(krakenInfo);

    } else if (subTabs.brokers === 'paxos') {
        section.appendChild(createSectionHeader('Paxos / itBit Connection', 'token'));

        section.appendChild(createCard('API Key', 'Paxos API Key', 'PAXOS_API_KEY', 'input', { password: true }));
        section.appendChild(createCard('API Secret', 'Paxos API Secret', 'PAXOS_API_SECRET', 'input', { password: true }));
        section.appendChild(createCard('Environment', 'Sandbox or Production', 'PAXOS_ENVIRONMENT', 'dropdown', {
            items: [
                { value: 'sandbox', label: 'Sandbox (Test)' },
                { value: 'production', label: 'Production (Live)' }
            ],
            default: 'sandbox'
        }));

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('Paxos Info', 'info'));
        section.appendChild(createWarningBox('<strong>Note:</strong> Used for direct Crypto Spot trading. Ensure "Data Routing" is set to use Paxos for Crypto.'));

    } else if (subTabs.brokers === 'ccxt') {
        section.appendChild(createSectionHeader('Coinbase / CCXT Engine', 'currency_bitcoin'));

        section.appendChild(createCard('Exchange ID', 'Provider name', 'CCXT_EXCHANGE', 'input', { default: 'coinbase' }));
        section.appendChild(createCard('Market Type', 'Asset class', 'CCXT_DEFAULT_TYPE', 'dropdown', {
            items: [
                { value: 'spot', label: 'Spot' },
                { value: 'swap', label: 'Swap' },
                { value: 'future', label: 'Future' }
            ]
        }));
        section.appendChild(createCard('API Key', 'Access identifier', 'CCXT_API_KEY', 'input', { password: true }));
        section.appendChild(createCard('API Secret', 'Secure key', 'CCXT_SECRET', 'input', { password: true }));
        section.appendChild(createCard('Sandbox Mode', 'Enable testnet', 'CCXT_SANDBOX', 'toggle'));
        section.appendChild(createCard('Rate Limit', 'Built-in rate limiting', 'CCXT_ENABLE_RATE_LIMIT', 'toggle', { default: 'true' }));

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('Crypto Order Settings', 'paid'));

        section.appendChild(createCard('Fractional Enabled', 'Allow fractional sizing', 'CRYPTO_FRACTIONAL_ENABLED', 'toggle', { default: 'true' }));
        section.appendChild(createCard('Min Notional (USD)', 'Minimum trade size', 'CRYPTO_MIN_NOTIONAL_USD', 'input', { number: true, default: '20' }));
        section.appendChild(createCard('Max Notional (USD)', 'Maximum trade size', 'CRYPTO_MAX_NOTIONAL_USD', 'input', { number: true, default: '1000000' }));
        section.appendChild(createCard('Order Type', 'Limit vs Market', 'CRYPTO_ORDER_TYPE', 'dropdown', {
            items: [
                { value: 'LIMIT', label: 'Limit (Safer)' },
                { value: 'MARKET', label: 'Market (Guaranteed Fill)' }
            ]
        }));

    } else if (subTabs.brokers === 'routing') {
        section.appendChild(createSectionHeader('Data & Execution Routing', 'route'));

        section.appendChild(createSectionHeader('Asset-Based Routing', 'route'));

        const infoBox = document.createElement('div');
        infoBox.className = 'warning-box';
        infoBox.style.borderColor = 'rgba(20, 184, 166, 0.3)';
        infoBox.innerHTML = `
            <div class="warning-box-content">
                <strong>Smart Routing Active:</strong><br>
                The execution engine will automatically route orders to the correct broker based on the asset class (Crypto vs Forex vs Stocks).
            </div>
        `;
        section.appendChild(infoBox);

        section.appendChild(createCard('Crypto Broker', 'btc, eth, sol', 'BROKER_CRYPTO', 'dropdown', {
            items: [
                { value: 'ccxt', label: 'Coinbase / CCXT' },
                { value: 'gemini', label: 'Gemini.com' },
                { value: 'kraken', label: 'Kraken' },
                { value: 'paxos', label: 'Paxos (Native API)' },
                { value: 'oanda', label: 'OANDA (Spot via Paxos)' },
                { value: 'ibkr', label: 'Interactive Brokers' }
            ],
            default: 'ccxt'
        }));

        section.appendChild(createCard('Forex Broker', 'eur/usd, jpy', 'BROKER_FOREX', 'dropdown', {
            items: [
                { value: 'ibkr', label: 'Interactive Brokers (Primary)' },
                { value: 'oanda', label: 'OANDA' }
            ],
            default: 'ibkr'
        }));

        section.appendChild(createCard('Equities Broker', 'spy, aapl', 'BROKER_EQUITIES', 'dropdown', {
            items: [
                { value: 'ibkr', label: 'Interactive Brokers Only' }
            ],
            default: 'ibkr'
        }));

        // Hidden master mode (implicitly Hybrid)
        // We will handle the BROKER_MODE env var on the backend or implicitly set it.
    }

    container.appendChild(section);
}

function renderAITab(container) {
    const section = document.createElement('div');
    section.className = 'settings-section';

    section.appendChild(createSectionHeader('AI Provider', 'smart_toy'));

    section.appendChild(createCard('AI Provider', 'Backend service', 'TRADE_SCI_PROVIDER', 'dropdown', {
        items: [
            { value: 'gemini', label: 'Google Gemini Pro' },
            { value: 'openai', label: 'OpenAI (GPT-4)' },
            { value: 'claude', label: 'Anthropic Claude' },
            { value: 'deepseek', label: 'DeepSeek' },
            { value: 'openrouter', label: 'OpenRouter' }
        ]
    }));

    section.appendChild(createCard('Model Name', 'e.g., gemini-1.5-pro-002', 'TRADE_SCI_MODEL_NAME', 'input'));
    section.appendChild(createCard('API Key', 'Provider authentication', 'CHATGPT_KEY', 'input', { password: true }));
    section.appendChild(createCard('Temperature', 'Response randomness (0-2)', 'AI_TEMPERATURE', 'input', { number: true, default: '0.2', min: 0, max: 2, step: 0.1 }));
    section.appendChild(createCard('Max Tokens', 'Response length limit', 'AI_MAX_TOKENS', 'input', { number: true, default: '2048' }));

    section.appendChild(createDivider());
    section.appendChild(createSectionHeader('AI Commentary', 'comment'));

    section.appendChild(createCard('Commentary Policy', 'When to invoke AI', 'COMMENTARY_LLM_POLICY', 'dropdown', {
        items: [
            { value: 'a_plus_or_4x', label: 'A+ Setup or 4x Daily' },
            { value: 'a_plus_only', label: 'A+ Setup Only' },
            { value: 'interval', label: 'Fixed Interval' }
        ]
    }));
    section.appendChild(createCard('Daily Slots', 'Comma-separated HH:MM', 'COMMENTARY_LLM_DAILY_SLOTS', 'input', { placeholder: '09:00,12:00,18:00,22:00' }));
    section.appendChild(createCard('Max Daily Calls', 'API cost cap', 'COMMENTARY_LLM_MAX_CALLS_PER_DAY', 'input', { number: true, default: '20' }));

    container.appendChild(section);
}

function renderScheduleTab(container) {
    const section = document.createElement('div');
    section.className = 'settings-section';

    section.appendChild(createSectionHeader('Sabbath Configuration', 'synagogue'));

    // City Resolver
    const resolver = document.createElement('div');
    resolver.className = 'city-resolver';
    resolver.innerHTML = `
        <div style="flex: 1;">
            <label style="display: block; font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.15em; color: var(--accent); margin-bottom: 8px;">Location Resolver</label>
            <input type="text" id="city-input" placeholder="Enter City (e.g. New York)" class="input-field" style="width: 100%;">
        </div>
        <button id="btn-resolve">Resolve</button>
    `;
    section.appendChild(resolver);

    section.appendChild(createCard('Enable Sabbath', 'Block trades during Sabbath', 'SABBATH_ENABLED', 'toggle'));
    section.appendChild(createCard('Astronomical Mode', 'Use actual sunset times', 'SABBATH_ASTRONOMICAL', 'toggle'));
    section.appendChild(createCard('Timezone', 'IANA zone name', 'SABBATH_TIMEZONE', 'input', { default: 'America/New_York' }));
    section.appendChild(createCard('Latitude', 'Decimal coordinate', 'SABBATH_LAT', 'input'));
    section.appendChild(createCard('Longitude', 'Decimal coordinate', 'SABBATH_LON', 'input'));
    section.appendChild(createCard('Start Time', 'Friday sunset (HH:MM)', 'SABBATH_START_LOCAL', 'input', { default: '18:00' }));
    section.appendChild(createCard('End Time', 'Saturday sunset (HH:MM)', 'SABBATH_END_LOCAL', 'input', { default: '18:00' }));

    section.appendChild(createDivider());
    section.appendChild(createSectionHeader('Session Gate', 'access_time'));

    section.appendChild(createCard('Session Gate Enabled', 'Enforce session health checks', 'SESSION_GATE_ENABLED', 'toggle', { default: 'true' }));
    section.appendChild(createCard('Overlap Start Hour', 'Active session start (0-23)', 'SESSION_OVERLAP_START_HOUR', 'input', { number: true, default: '12', min: 0, max: 23 }));
    section.appendChild(createCard('Overlap End Hour', 'Active session end (0-23)', 'SESSION_OVERLAP_END_HOUR', 'input', { number: true, default: '16', min: 0, max: 23 }));
    section.appendChild(createCard('Session Timezone', 'For overlap hours', 'SESSION_OVERLAP_TIMEZONE', 'input', { default: 'UTC' }));
    section.appendChild(createCard('Auto Schedule', 'Auto switch equities/crypto', 'AUTO_SCHEDULE_ENABLED', 'toggle'));

    container.appendChild(section);

    // City resolver event
    resolver.querySelector('#btn-resolve').addEventListener('click', async () => {
        const city = resolver.querySelector('#city-input').value;
        if (!city) return;

        const btn = resolver.querySelector('#btn-resolve');
        btn.textContent = 'RESOLVING...';

        const res = await window.electronAPI.resolveCity(city);
        if (res) {
            updateValue('SABBATH_LAT', res.lat.toString());
            updateValue('SABBATH_LON', res.lon.toString());
            updateValue('SABBATH_TIMEZONE', res.tz);
            renderTab();
        } else {
            alert("City not found. Please enter Lat/Lon manually.");
            btn.textContent = 'RESOLVE';
        }
    });
}

function renderAdvancedTab(container, filter = "") {
    const section = document.createElement('div');
    section.className = 'settings-section';

    section.appendChild(createSectionHeader('All Environment Variables', 'terminal'));

    const filteredKeys = Object.keys(envData).filter(key =>
        key.toLowerCase().includes(filter.toLowerCase()) ||
        (envData[key] && envData[key].toLowerCase().includes(filter.toLowerCase()))
    ).sort();

    filteredKeys.forEach(key => {
        const row = document.createElement('div');
        row.className = 'advanced-row';
        row.innerHTML = `
            <div style="width: 280px; flex-shrink: 0; font-size: 10px; font-weight: 700; font-family: 'SF Mono', monospace; color: var(--text-dim); overflow: hidden; text-overflow: ellipsis;">${key}</div>
            <input type="text" class="flex-1" style="background: transparent; border: none; font-size: 13px; color: var(--text-secondary); outline: none; font-family: 'SF Mono', monospace;" value="${envData[key] || ''}">
        `;
        row.querySelector('input').addEventListener('change', (e) => updateValue(key, e.target.value));
        section.appendChild(row);
    });

    if (filteredKeys.length === 0) {
        const empty = document.createElement('div');
        empty.style.cssText = 'padding: 40px; text-align: center; color: var(--text-dim); font-style: italic;';
        empty.textContent = 'No variables match your search.';
        section.appendChild(empty);
    }

    container.appendChild(section);
}

// ═══════════════════════════════════════════════════════════
// DATA ACTIONS
// ═══════════════════════════════════════════════════════════

function updateValue(key, value) {
    envData[key] = value;
    localChanges[key] = value;
    updateChangeCounter();

    if (key === 'MULTI_POSITION_ENABLED') {
        const smartToggle = document.querySelector('.control-card[data-key="SMART_POSITIONS_ENABLED"]');
        if (smartToggle) {
            if (value === 'false') {
                smartToggle.classList.add('opacity-50', 'pointer-events-none');
            } else {
                smartToggle.classList.remove('opacity-50', 'pointer-events-none');
            }
        }
    }
}

function updateChangeCounter() {
    changeCount = Object.keys(localChanges).length;
    const el = document.getElementById('change-counter');
    const saveBtn = document.getElementById('btn-save');

    if (changeCount > 0) {
        el.textContent = `${changeCount} unsaved change${changeCount > 1 ? 's' : ''} detected`;
        el.className = 'text-xs text-rose-400 font-bold';
        saveBtn.classList.add('animate-pulse');
    } else {
        el.textContent = 'All settings synced to disk';
        el.className = 'text-xs text-slate-500 font-bold';
        saveBtn.classList.remove('animate-pulse');
    }
}

async function saveAll() {
    if (changeCount === 0) return;

    const indicator = document.getElementById('save-indicator');
    if (indicator) indicator.style.opacity = '1';

    try {
        if (!window.electronAPI) {
            throw new Error("Not connected to Electron backend");
        }

        const envUpdates = { ...localChanges };
        delete envUpdates['_profiles_'];

        if (Object.keys(envUpdates).length > 0 && window.electronAPI.saveEnv) {
            await window.electronAPI.saveEnv(envUpdates);
        }
        if (localChanges['_profiles_'] && window.electronAPI.saveProfiles) {
            await window.electronAPI.saveProfiles(profilesContent);
        }

        localChanges = {};
        updateChangeCounter();
        setTimeout(() => { if (indicator) indicator.style.opacity = '0'; }, 2000);
    } catch (e) {
        alert("Save Error: " + e.message);
        if (indicator) indicator.style.opacity = '0';
    }
}

// ═══════════════════════════════════════════════════════════
// TOOLTIP
// ═══════════════════════════════════════════════════════════

function showTooltip(e, title, content) {
    const popup = document.getElementById('tooltip-popup');
    document.getElementById('tooltip-title').textContent = title;
    document.getElementById('tooltip-content').textContent = content;

    // Make visible first to get dimensions (but keep offscreen or transparent if possible, though opacity-0 handles visibility)
    popup.classList.add('visible');

    const rect = e.currentTarget.getBoundingClientRect();
    const tooltipWidth = popup.offsetWidth;
    const windowWidth = window.innerWidth;
    const gap = 16;

    // Default: Position to the right
    let leftPos = rect.right + gap;

    // Collision detection: If generic right position + width exceeds window width, flip to left
    if (leftPos + tooltipWidth > windowWidth - 20) { // 20px safety buffer
        leftPos = rect.left - tooltipWidth - gap;
    }

    popup.style.left = `${leftPos}px`;
    popup.style.top = `${rect.top}px`;
}

function hideTooltip() {
    const popup = document.getElementById('tooltip-popup');
    popup.classList.remove('visible');
}

// ═══════════════════════════════════════════════════════════
// NEW STRATEGY TOOLBOX RENDERER
// ═══════════════════════════════════════════════════════════

// Internal state for toolbox sub-tabs
let toolboxTab = 'icc'; // Default

function renderStrategyToolbox(container) {
    // Internal Navigation for Toolbox (Horizontal or vertical variant)
    const nav = document.createElement('div');
    nav.className = 'sub-nav';
    // Using a different style or just expanding sub-nav

    const strategies = [
        { id: 'icc', label: 'ICC (Indication, Correction, Continuation)' },
        { id: 'rubberband_reaper', label: 'Rubberband Reaper' },
        { id: 'robocop', label: 'RoboCop' },
        { id: 'evolution', label: 'Robot Evolution' },
        { id: 'quantum', label: 'Quantum' },
        { id: 'mean_reversion', label: 'Mean Reversion' },
        { id: 'hyper_scalper', label: 'HyperScalper' },
        { id: 'london_breakout', label: 'London Breakout' },
        { id: 'volatility_breakout', label: 'Volatility Breakout' },
        { id: 'aggregator', label: 'Aggregator' },
        { id: 'supply_demand', label: 'Supply & Demand' }
    ];

    strategies.forEach(s => {
        const btn = document.createElement('button');
        btn.className = `sub-nav-btn ${toolboxTab === s.id ? 'active' : ''}`;
        btn.textContent = s.label;
        btn.onclick = () => {
            toolboxTab = s.id;
            renderTab(); // Re-render the whole tab to update this section
        };
        nav.appendChild(btn);
    });

    container.appendChild(nav);

    const section = document.createElement('div');
    section.className = 'settings-section';

    if (toolboxTab === 'icc') {
        section.appendChild(createSectionHeader('ICC Core Logic', 'auto_mode'));

        section.appendChild(createCard('ICC Auto-Entry', 'Auto-enter on valid signals', 'ICC_AUTO_ENTRY_ENABLED', 'toggle', { default: 'true' }));
        section.appendChild(createCard('Aggressive Mode', 'Enable aggressive sizing', 'ICC_AGGRESSIVE_MODE', 'toggle', { default: 'true' }));
        section.appendChild(createCard('Require Sweep', 'Must have liquidity sweep', 'ICC_AUTO_ENTRY_REQUIRE_SWEEP', 'toggle'));
        section.appendChild(createCard('Min HTF Strength', 'Minimum trend strength', 'ICC_AUTO_ENTRY_MIN_HTF_STRENGTH', 'input', { number: true, default: '0.25', min: 0, max: 1, step: 0.05 }));
        section.appendChild(createCard('Confirmation Bars', 'Bars to confirm signal', 'ICC_CONFIRMATION_BARS', 'input', { number: true, default: '2', min: 1, max: 5 }));

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('ICC Scoring Weights', 'leaderboard'));

        section.appendChild(createCard('Entry Score Threshold', 'Minimum score for entry', 'ICC_ENTRY_SCORE_THRESHOLD', 'input', { number: true, default: '35', min: 0, max: 100 }));

        const scoreGrid = document.createElement('div');
        scoreGrid.className = 'card-grid';
        scoreGrid.appendChild(createSliderCard('Continuation', 'Points for continuation', 'ICC_SCORE_CONTINUATION_POINTS', 0, 100, 5, 'pts'));
        scoreGrid.appendChild(createSliderCard('Sweep', 'Points for liquidity sweep', 'ICC_SCORE_SWEEP_POINTS', 0, 50, 5, 'pts'));
        scoreGrid.appendChild(createSliderCard('HTF/LTF Align', 'Points for alignment', 'ICC_SCORE_HTF_LTF_ALIGN_POINTS', 0, 50, 5, 'pts'));
        scoreGrid.appendChild(createSliderCard('Strong HTF', 'Points for strong trend', 'ICC_SCORE_STRONG_HTF_POINTS', 0, 30, 5, 'pts'));
        scoreGrid.appendChild(createSliderCard('Phase', 'Points for good phase', 'ICC_SCORE_PHASE_POINTS', 0, 20, 5, 'pts'));
        scoreGrid.appendChild(createSliderCard('Indication', 'Points for indication', 'ICC_SCORE_INDICATION_POINTS', 0, 20, 5, 'pts'));
        section.appendChild(scoreGrid);
    } else if (toolboxTab === 'rubberband_reaper') {
        const stratInfo = STRATEGIES.rubberband_reaper;
        section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'tune'));

        section.appendChild(createWarningBox(`
            <strong>Strategy Override:</strong><br>
            Use this panel to configure the Mean Reversion parameters. These settings override global defaults when this strategy is active.
        `));

        section.appendChild(createCard('Base Risk %', 'Initial entry risk', 'RUBBERBAND_REAPER_RISK_PCT', 'input', {
            number: true,
            default: '0.20',
            tooltip: 'The default risk percentage for the initial entry. Rubberband Reaper uses a "Tiered Risk" model by default (20% for small accounts), but this setting defines the baseline if dynamic logic permits.'
        }));

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('Bollinger Bands', 'donut_large'));

        section.appendChild(createCard('Period', 'Lookback bars', 'BB_PERIOD', 'input', {
            number: true,
            default: '15',
            tooltip: 'The number of candles used to calculate the Bollinger Bands. A smaller number makes the bands more reactive to price changes, while a larger number smooths them out.'
        }));
        section.appendChild(createCard('Std Dev', 'Width multiplier', 'BB_STD', 'input', {
            number: true,
            default: '2.5',
            tooltip: 'Standard Deviation multiplier. Higher values (e.g. 3.0) mean price hits the bands less often (more extreme). Lower values (e.g. 2.0) generate more signals but potentially more false alarms.'
        }));

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('RSI Config', 'ssid_chart'));

        section.appendChild(createCard('Period', 'RSI Lookback', 'RSI_PERIOD', 'input', {
            number: true,
            default: '14',
            tooltip: 'The lookback period for the Relative Strength Index. 14 is the industry standard.'
        }));
        section.appendChild(createCard('Overbought', 'Short threshold', 'RSI_OVERBOUGHT', 'input', {
            number: true,
            default: '75',
            tooltip: 'RSI level considered "Overbought". Price above this level suggests an exhaustion of buying momentum, signaling a potential Short entry.'
        }));
        section.appendChild(createCard('Oversold', 'Long threshold', 'RSI_OVERSOLD', 'input', {
            number: true,
            default: '25',
            tooltip: 'RSI level considered "Oversold". Price below this level suggests an exhaustion of selling momentum, signaling a potential Long entry.'
        }));

    } else if (toolboxTab === 'supply_demand') {
        const stratInfo = STRATEGIES.supply_demand;
        section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'account_balance_wallet'));

        section.appendChild(createWarningBox(`
            <strong>Institutional Logic:</strong><br>
            Supply & Demand focuses on "Unfilled Orders". It ignores minor noise and only enters when price returns to a high-probability zone after a solid Break of Structure (BOS).
        `));

        section.appendChild(createCard('RR Target', 'Reward-to-Risk Goal', 'SND_RR_TARGET', 'input', {
            number: true,
            default: '2.0',
            tooltip: 'The desired Reward-to-Risk ratio. 2.0 means targeting twice the amount risked. This is the optimal setting for SND institutional setups.'
        }));

        section.appendChild(createCard('Zone Window', 'Candle Lookback for Zones', 'SND_ZONE_WINDOW', 'input', {
            number: true,
            default: '100',
            tooltip: 'How many historical candles the bot scans to find valid Supply or Demand zones. A larger window finds older, potentially stronger zones.'
        }));

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('Advanced SND Filters', 'military_tech'));

        section.appendChild(createCard('Max Daily Trades', 'Daily Trade Cap', 'MAX_DAILY_TRADES', 'input', {
            number: true,
            default: '20',
            tooltip: 'Safety cap on how many trades this strategy can take per symbol per day. Prevents over-trading in choppy markets.'
        }));

    } else if (toolboxTab === 'icc') {
        const stratInfo = STRATEGIES.icc_core || { description: "Standard ICC Logic" };
        section.appendChild(createDescriptionBox(stratInfo.description, stratInfo.stats));

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('Indication, Correction, Continuation (ICC)', 'auto_mode'));

        section.appendChild(createCard('ICC Auto-Entry', 'Auto-enter on valid signals', 'ICC_AUTO_ENTRY_ENABLED', 'toggle', { default: 'true' }));
        section.appendChild(createCard('Aggressive Mode', 'Enable aggressive sizing', 'ICC_AGGRESSIVE_MODE', 'toggle', { default: 'true' }));
        section.appendChild(createCard('Require Sweep', 'Must have liquidity sweep', 'ICC_AUTO_ENTRY_REQUIRE_SWEEP', 'toggle'));
        section.appendChild(createCard('Min HTF Strength', 'Minimum trend strength', 'ICC_AUTO_ENTRY_MIN_HTF_STRENGTH', 'input', { number: true, default: '0.25', min: 0, max: 1, step: 0.05 }));
        section.appendChild(createCard('Confirmation Bars', 'Bars to confirm signal', 'ICC_CONFIRMATION_BARS', 'input', { number: true, default: '2', min: 1, max: 5 }));

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('ICC Scoring Weights', 'leaderboard'));

        section.appendChild(createCard('Entry Score Threshold', 'Minimum score for entry', 'ICC_ENTRY_SCORE_THRESHOLD', 'input', { number: true, default: '35', min: 0, max: 100 }));

        const scoreGrid = document.createElement('div');
        scoreGrid.className = 'card-grid';
        scoreGrid.appendChild(createSliderCard('Continuation', 'Points for continuation', 'ICC_SCORE_CONTINUATION_POINTS', 0, 100, 5, 'pts'));
        scoreGrid.appendChild(createSliderCard('Sweep', 'Points for liquidity sweep', 'ICC_SCORE_SWEEP_POINTS', 0, 50, 5, 'pts'));
        scoreGrid.appendChild(createSliderCard('HTF/LTF Align', 'Points for alignment', 'ICC_SCORE_HTF_LTF_ALIGN_POINTS', 0, 50, 5, 'pts'));
        scoreGrid.appendChild(createSliderCard('Strong HTF', 'Points for strong trend', 'ICC_SCORE_STRONG_HTF_POINTS', 0, 30, 5, 'pts'));
        scoreGrid.appendChild(createSliderCard('Phase', 'Points for good phase', 'ICC_SCORE_PHASE_POINTS', 0, 20, 5, 'pts'));
        scoreGrid.appendChild(createSliderCard('Indication', 'Points for indication', 'ICC_SCORE_INDICATION_POINTS', 0, 20, 5, 'pts'));
        section.appendChild(scoreGrid);
    } else if (toolboxTab === 'robocop') {
        const stratInfo = STRATEGIES.robocop;
        section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'local_police'));

        section.appendChild(createWarningBox(`
            <strong>High Frequency Trading:</strong><br>
            RoboCop is designed for speed. Use "Combat Mode" to bypass safety checks (like HTF alignment) for maximum aggression.
        `));

        section.appendChild(createCard('Combat Mode', 'Bypass all safety gates', 'COMBAT_MODE_ENABLED', 'toggle', {
            tooltip: 'If enabled, RoboCop ignores "HTF Strength" and "Score Threshold" gates. It will take every valid liquidity sweep or continuation signal regardless of broader context. High risk, high volume.'
        }));

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('Aggressive Targets', 'gps_fixed'));

        section.appendChild(createCard('Confirmation Bars', 'Bars to wait', 'ROBOCOP_CONFIRMATION_BARS', 'input', {
            number: true,
            default: '1',
            min: 1, limit: 3,
            tooltip: 'How many candles to wait after a signal before entering. RoboCop defaults to 1 for speed. Increasing this adds safety but may miss fast moves.'
        }));
        section.appendChild(createCard('Target Multiplier', 'R-multiple', 'ROBOCOP_TARGET_ATR_MULT', 'input', {
            number: true,
            default: '3.0',
            tooltip: 'Multiplies the ATR (volatility) to set the Take Profit level. 3.0 means targeting a move 3x the average volatility size.'
        }));
        section.appendChild(createCard('Stop Multiplier', 'Protection width', 'ROBOCOP_STOP_ATR_MULT', 'input', {
            number: true,
            default: '1.5',
            tooltip: 'Multiplies the ATR to set the Stop Loss. 1.5 offers a tight but breathable stop for scalping.'
        }));

    } else if (toolboxTab === 'evolution') {
        const stratInfo = STRATEGIES.evolution;
        section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'smart_toy'));

        section.appendChild(createCard('Target Risk:Reward', 'R-Multiple', 'EVOLUTION_TARGET_R', 'input', {
            number: true,
            default: '2.0',
            tooltip: 'The fixed Reward-to-Risk ratio. A value of 2.0 means the bot calculates position size such that the Profit Target is 2x the distance of the Stop Loss.'
        }));
        section.appendChild(createCard('Stop ATR Mult', 'Volatility based stop', 'EVOLUTION_STOP_ATR_MULT', 'input', {
            number: true,
            default: '1.5',
            tooltip: 'Sets the stop loss distance based on market volatility (ATR). 1.5 is standard for this strategy to survive random noise while chopping.'
        }));

    } else if (toolboxTab === 'quantum') {
        const stratInfo = STRATEGIES.quantum;
        section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'science'));

        section.appendChild(createCard('SMA Period', 'Trend baseline', 'QUANTUM_SMA_PERIOD', 'input', {
            number: true,
            default: '20',
            tooltip: 'The Simple Moving Average (SMA) period used to define the "mean". Quantum looks for pullbacks to this line.'
        }));
        section.appendChild(createCard('Stop ATR Mult', 'Protection width', 'QUANTUM_STOP_ATR_MULT', 'input', {
            number: true,
            default: '2.5',
            tooltip: 'Quantum uses a wider stop (2.5 ATR) to allow for deeper pullbacks within a massive trend.'
        }));
        section.appendChild(createCard('Target R', 'Profit target', 'QUANTUM_TARGET_R', 'input', {
            number: true,
            default: '1.6',
            tooltip: 'The Reward-to-Risk target. 1.6 ensures a high win rate while maintaining positive expectancy.'
        }));

    } else {
        // Generic fallback for others (London, MeanRev, HyperScalper, etc)
        const stratInfo = STRATEGIES[toolboxTab];
        if (stratInfo) {
            section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'tune'));

            section.appendChild(createWarningBox(`
                <strong>Strategy Override Enabled:</strong><br>
                Settings configured here for <em>${stratInfo.name}</em> will take precedence over global Global Risk limits.
            `));

            section.appendChild(createCard('Base Risk %', `Specific risk for ${stratInfo.name}`, `${toolboxTab.toUpperCase()}_RISK_PCT`, 'input', {
                number: true,
                placeholder: 'Default',
                tooltip: `Define the specific risk percentage for ${stratInfo.name}. This overrides the global "Default Risk %" setting.`
            }));

            // Add strategy description again for context
            const descCard = document.createElement('div');
            descCard.className = 'control-card';
            descCard.style.display = 'block';
            descCard.style.padding = '16px';
            descCard.innerHTML = `
                <div style="color: var(--text-secondary); font-size: 13px; line-height: 1.6;">
                    ${stratInfo.description}
                </div>
            `;
            section.appendChild(descCard);
        }
    }

    container.appendChild(section);
}

// ═══════════════════════════════════════════════════════════
// START (init is called from DOMContentLoaded handler at top)
// ═══════════════════════════════════════════════════════════

function createControlButton(label, icon, color, onClick) {
    const btn = document.createElement('button');
    btn.className = `control-btn control-btn-${color}`;
    btn.innerHTML = `
        <span class="material-symbols-outlined">${icon}</span>
        <span class="text-xs font-bold uppercase tracking-widest">${label}</span>
    `;
    btn.onclick = (e) => {
        e.preventDefault();
        onClick();
    };
    return btn;
}

function updateBotStatusUI(isRunning) {
    const banner = document.getElementById('runtime-status-banner');
    const dot = document.getElementById('status-dot');
    const text = document.getElementById('status-text');

    if (!banner || !dot || !text) return;

    banner.classList.remove('hidden');
    if (isRunning) {
        dot.className = 'w-2 h-2 rounded-full bg-teal-500 shadow-[0_0_10px_rgba(20,184,166,0.8)]';
        text.textContent = 'Bot Online';
        text.className = 'text-[10px] font-black uppercase tracking-widest text-teal-400';
    } else {
        dot.className = 'w-2 h-2 rounded-full bg-slate-500 animate-pulse';
        text.textContent = 'Bot Offline';
        text.className = 'text-[10px] font-black uppercase tracking-widest text-slate-400';
    }
}

function showNotice(message, color = 'teal') {
    // Create toast element
    const toast = document.createElement('div');
    toast.className = `fixed top-12 left-1/2 -translate-x-1/2 z-[100] px-8 py-4 rounded-2xl bg-black/80 backdrop-blur-2xl border-2 border-${color}-500/30 shadow-2xl animate-in fade-in zoom-in slide-in-from-top-4 duration-500`;

    // Convert generic colors to valid tailwind/custom classes if needed
    const colorClass = color === 'teal' ? 'teal' : (color === 'red' ? 'red' : 'purple');

    toast.innerHTML = `
        <div class="flex items-center gap-4">
            <div class="w-3 h-3 rounded-full bg-${colorClass}-500 shadow-[0_0_15px_rgba(20,184,166,0.8)] animate-pulse"></div>
            <span class="text-xs font-black uppercase tracking-[0.2em] text-${colorClass}-400">${message}</span>
        </div>
    `;

    document.body.appendChild(toast);

    // Smooth exit
    setTimeout(() => {
        toast.classList.add('animate-out', 'fade-out', 'zoom-out', 'slide-out-to-top-4');
        setTimeout(() => toast.remove(), 500);
    }, 4000);
}
