/**
 * Tradebot SCI Settings Interface (Integrated)
 * This module is loaded by the main app and initialized when the Settings view is opened.
 */

// Track if already initialized
let settingsInitialized = false;

// ═══════════════════════════════════════════════════════════
// STATE MANAGEMENT
// ═══════════════════════════════════════════════════════════

let configData = {};
let secretsData = {};
let envData = {};
let localChanges = {};
let changeCount = 0;
let autoSaveTimeout;
let profilesContent = "";
let currentTab = 'system';
let subTabs = { brokers: 'ibkr', strategy: 'assets' };

// Property Mapping (Legacy Key -> JSON Path)
const CONFIG_MAP = {
    'APP_PROFILE': ['active_profile'],
    'BOT_MODE': ['global', 'bot_mode'],
    'BOT_ITERATIONS': ['global', 'bot_iterations'],
    'EXECUTE_TRADES': ['global', 'execute_trades'],
    'SABBATH_ENABLED': ['safety', 'sabbath_enabled'],
    'SABBATH_CITY': ['safety', 'sabbath_city'],
    'OANDA_ACCOUNT_ID': ['brokers', 'oanda', 'account_id'],
    'OANDA_ENVIRONMENT': ['brokers', 'oanda', 'environment'],
    'OANDA_READ_ONLY': ['brokers', 'oanda', 'read_only'],
    'IBKR_HOST': ['brokers', 'ibkr', 'host'],
    'IBKR_PORT': ['brokers', 'ibkr', 'port'],
    'IBKR_CLIENT_ID': ['brokers', 'ibkr', 'client_id'],
    'IBKR_ACCOUNT_ID': ['brokers', 'ibkr', 'account_id'],
    'IBKR_PAPER': ['brokers', 'ibkr', 'paper'],
    'IBKR_READ_ONLY': ['brokers', 'ibkr', 'read_only'],
    'GEMINI_SANDBOX': ['brokers', 'gemini', 'sandbox'],
    'CCXT_EXCHANGE': ['brokers', 'ccxt', 'exchange'],
    'CCXT_DEFAULT_TYPE': ['brokers', 'ccxt', 'default_type'],
    'CCXT_SANDBOX': ['brokers', 'ccxt', 'sandbox'],
    'CCXT_ENABLE_RATE_LIMIT': ['brokers', 'ccxt', 'enable_rate_limit'],
    'BROKER_CRYPTO': ['market', 'broker_crypto'],
    'BROKER_FOREX': ['market', 'broker_forex'],
    'BROKER_EQUITIES': ['market', 'broker_equities'],
    'MARKET_DATA_MODE': ['market', 'market_data_mode'],
    'LOG_LEVEL': ['logging', 'level'],
    'TRADEBOT_LOG': ['logging', 'file'],
    'WS_SERVER_PORT': ['runtime', 'ws_server_port'],
    'GUI_WS_URL': ['runtime', 'gui_ws_url'],
    'GUI_PNL_TIMEFRAME': ['runtime', 'pnl_timeframe'],
    'GLOBAL_RISK_PCT': ['runtime', 'global_default_risk_pct'],
    'FRIDAY_FADE_ENABLED': ['schedule', 'friday_fade_enabled'],
    // Safety & Shields
    'SAFETY_ATR_SHIELD_ENABLED': ['safety', 'safety_atr_shield_enabled'],
    'SAFETY_SENTIMENT_SHIELD_ENABLED': ['safety', 'safety_sentiment_shield_enabled'],
    'SAFETY_VOLATILITY_VETO_ENABLED': ['safety', 'safety_volatility_veto_enabled'],
    'WEALTH_EXIT_GAMMA_ENABLED': ['safety', 'wealth_exit_gamma_enabled'],
    'WEALTH_EXIT_MOONSHOT_ENABLED': ['safety', 'wealth_exit_moonshot_enabled'],
    'WEALTH_EXIT_BLOWOFF_ENABLED': ['safety', 'wealth_exit_blowoff_enabled'],
    'RISK_REWARD_RATIO': ['safety', 'risk_reward_ratio'],
    'BREAKEVEN_TRAIL_PCT': ['safety', 'breakeven_trail_pct'],
    'SAFETY_STALE_SNIPER_ENABLED': ['safety', 'safety_stale_sniper_enabled'],
    'SAFETY_STALE_SNIPER_BARS': ['safety', 'safety_stale_sniper_bars'],
    'SAFETY_FLASH_TRAP_ENABLED': ['safety', 'safety_flash_trap_enabled'],
    'SAFETY_REGIME_FLIP_ENABLED': ['safety', 'safety_regime_flip_enabled'],
    'BLOCK_COUNTER_TREND_ENTRIES': ['safety', 'block_counter_trend_entries'],
    // Performance
    'PERFORMANCE_MODE': ['performance', 'performance_mode'],
    'TRAILING_STOP_ENABLED': ['performance', 'trailing_stop_enabled'],
    'PYRAMID_CAP_OVERRIDE': ['performance', 'pyramid_cap_override'],
    'COMPOUNDING_CAP_OVERRIDE': ['performance', 'compounding_cap_override'],
    // ── Risk & ICC (Global — not per-profile) ──────────────────
    'RISK_PER_TRADE_PCT': ['risk', 'risk_per_trade_pct'],
    'RISK_PER_TRADE_DOLLARS': ['risk', 'risk_per_trade_dollars'],
    'MAX_EXPOSURE_PCT': ['risk', 'max_exposure_pct'],
    'LIMIT_LOSS_DAILY_PCT': ['risk', 'limit_loss_daily_pct'],
    'AGGRESSIVE_RISK_PER_TRADE_PCT': ['risk', 'aggressive_risk_per_trade_pct'],
    'ICC_AUTO_ENTRY_ENABLED': ['risk', 'icc_auto_entry_enabled'],
    'ICC_AGGRESSIVE_MODE': ['risk', 'icc_aggressive_mode'],
    'ICC_ENTRY_SCORE_THRESHOLD': ['risk', 'icc_entry_score_threshold'],
    'ICC_AUTO_ENTRY_REQUIRE_SWEEP': ['risk', 'icc_auto_entry_require_sweep'],
    'ICC_AUTO_ENTRY_MIN_HTF_STRENGTH': ['risk', 'icc_auto_entry_min_htf_strength'],
    'ICC_CONFIRMATION_BARS': ['risk', 'icc_confirmation_bars'],
    'ICC_MAX_BARS_AFTER_SWEEP': ['risk', 'icc_max_bars_after_sweep'],
    'ICC_REQUIRE_LIQUIDITY_GRAB': ['risk', 'icc_require_liquidity_grab'],
    'ICC_STRICT_MODE': ['risk', 'icc_strict_mode'],
    'ICC_HIGH_SCORE_OVERRIDE_THRESHOLD': ['risk', 'icc_high_score_override_threshold'],
    'ICC_TWO_SIGNAL_OVERRIDE_ENABLED': ['risk', 'icc_two_signal_override_enabled'],
    'ICC_AUTO_ENTRY_COOLDOWN_MINUTES': ['risk', 'icc_auto_entry_cooldown_minutes'],
    'ICC_AUTO_ENTRY_MIN_SCORE': ['risk', 'icc_auto_entry_min_score'],
    'ICC_SCORE_CONTINUATION_POINTS': ['risk', 'icc_score_continuation_points'],
    'ICC_SCORE_SWEEP_POINTS': ['risk', 'icc_score_sweep_points'],
    'ICC_SCORE_HTF_LTF_ALIGN_POINTS': ['risk', 'icc_score_htf_ltf_align_points'],
    'ICC_SCORE_STRONG_HTF_POINTS': ['risk', 'icc_score_strong_htf_points'],
    'ICC_SCORE_PHASE_POINTS': ['risk', 'icc_score_phase_points'],
    'ICC_SCORE_INDICATION_POINTS': ['risk', 'icc_score_indication_points'],
    'ICC_SCORE_HTF_STRENGTH_THRESHOLD': ['risk', 'icc_score_htf_strength_threshold'],
    // Safety Suite 2.0 Shields
    'SAFETY_DRAWDOWN_BREAKER_ENABLED': ['safety', 'safety_drawdown_breaker_enabled'],
    'SAFETY_GREED_GUARD_ENABLED': ['safety', 'safety_greed_guard_enabled'],
    'SAFETY_GREED_GUARD_TARGET': ['safety', 'safety_greed_guard_target'],
    'SAFETY_STREAK_BREAKER_ENABLED': ['safety', 'safety_streak_breaker_enabled'],
    'SAFETY_CHURN_BURNER_ENABLED': ['safety', 'safety_churn_burner_enabled'],
    'SAFETY_CHURN_BURNER_MAX': ['safety', 'safety_churn_burner_max'],
    'SAFETY_OPENING_SENTRY_ENABLED': ['safety', 'safety_opening_sentry_enabled'],
};

const SECRETS_MAP = {
    'OANDA_API_KEY': 'OANDA_API_KEY',
    'GEMINI_API_KEY': 'GEMINI_API_KEY',
    'GEMINI_API_SECRET': 'GEMINI_API_SECRET',
    'CCXT_API_KEY': 'CCXT_API_KEY',
    'CCXT_SECRET': 'CCXT_SECRET',
    'PAXOS_API_KEY': 'PAXOS_API_KEY',
    'PAXOS_API_SECRET': 'PAXOS_API_SECRET',
    'KRAKEN_API_KEY': 'KRAKEN_API_KEY',
    'KRAKEN_API_SECRET': 'KRAKEN_API_SECRET',
};

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
    GLOBAL_RISK_PCT: "The global default risk percentage used when no other risk is specified. For example, 0.04 is 4%. This acts as the manual 'floor' for all trades.",
    WS_SERVER_PORT: "The port number the trading bot should listen on for local connections. Default is 8080. If you change this, you must also update your WebConnect URL or external tools to match.",
    FRIDAY_FADE_ENABLED: "IMPORTANT (Forex Only): Automatically reduces risk to 0.25% after 12:00 PM EST on Fridays. This accounts for the sharp drop in Forex liquidity as markets approach the weekend close, preventing 'mean reversion' strategies from getting trapped in late-session drifts.",
    PDT_GUARD_ENABLED: "Enable the Pattern Day Trader guard. Prevents opening new positions if you have fewer than $25,000 Equity and have already made 3 day trades in a rolling 5-day window. (Only applies to US Equities via IBKR).",

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
    MAX_EXPOSURE_PCT: "Maximum total risk across ALL open positions combined. If set to 10% with a $10,000 account, total risk across all trades can't exceed $1,000.",
    MAX_DAILY_LOSS_PCT: "Safety circuit breaker - if you lose this percentage of your account in one day, the bot stops trading to prevent catastrophic losses. Like a daily loss limit at a casino.",
    RISK_PER_TRADE_DOLLARS: "Fixed dollar amount to risk per trade instead of percentage. Useful if you want consistent $50 or $100 risk regardless of account size.",
    MAX_LOSS_PER_TRADE_DOLLARS: "Absolute maximum dollars you can lose on any single trade, even if percentage calculation says otherwise. A hard safety cap.",
    LIMIT_LOSS_DAILY_PCT: "Maximum loss allowed for the daily interval (e.g. 0.06 = 6%). The bot will stop trading for the day if reached. Only activates when account capital is above $250 — on smaller accounts, this is like a fire alarm that goes off when you make toast. 🍞",
    LIMIT_LOSS_WEEKLY_PCT: "Maximum loss allowed for the weekly interval (e.g. 0.15 = 15%). The bot will stop trading for the week if reached.",
    LIMIT_LOSS_MONTHLY_PCT: "Maximum loss allowed for the monthly interval (e.g. 0.25 = 25%). The bot will stop trading for the month if reached.",
    TARGET_PROFIT_DAILY_PCT: "Profit target for the daily interval (e.g. 0.02 = 2%). Once hit, the bot stops for the day to lock in profits and prevent 'giving it back'. 0 disables.",
    TARGET_PROFIT_WEEKLY_PCT: "Profit target for the weekly interval (e.g. 0.05 = 5%). Once hit, the bot stops for the week to protect gains. 0 disables.",
    TARGET_PROFIT_MONTHLY_PCT: "Profit target for the monthly interval (e.g. 0.10 = 10%). Once hit, the bot stops for the month for wealth retention. 0 disables.",

    // Safety & Shields
    MULTI_POSITION_ENABLED: "Allow the bot to have multiple trades open at the same time across different symbols. When disabled, it finishes one trade before starting another.",
    MAX_CONCURRENT_POSITIONS: "Maximum number of trades that can be open simultaneously. More positions = more diversification but also more complexity and capital required.",
    SMART_POSITIONS_ENABLED: "The core safety filter: only opens a new trade if your current open profits are high enough to 'pay for' the risk of the next trade. This ensures you only scale up using profit, protecting your principal capital.",

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
    STOP_ATR_MULTIPLIER: "<strong>The 'Safe Distance' Calculator.</strong> Average True Range (ATR) measures how much a market normally 'breathes' or wiggles. A 1.5 multiplier means your stop-loss will be placed 1.5x that normal wiggle distance away from your entry. Tighter (1.0-1.2) = smaller losses but higher chance of getting 'shaken out'. Wider (2.0-3.0) = more breathing room but larger losses when it fails.",
    SAFETY_STABILITY_MODE_ENABLED: "<strong>Master Survival Protocol.</strong> When your account is 'bleeding' or market conditions are uncertain, this is your primary shield. It enforces three strict rules: (1) It caps your risk at 1% per trade, (2) It ignores all low-quality signals, only taking setups that score 75/100 or higher, and (3) It resets aggressive performance modes back to Standard. Use this to protect your capital during rough patches.",
    MIN_HOLD_HOURS: "Minimum hours to hold a position before allowing exits. Prevents panic-selling or premature exits. 0 = no minimum.",
    MAX_HOLD_HOURS: "Maximum hours to hold a position - force exit after this time regardless of profit/loss. 0 = hold forever if needed.",
    HTF_NEUTRAL_EXIT_BARS: "Exit if higher timeframe stays neutral (no clear trend) for this many bars. Prevents capital from being tied up in directionless markets.",

    // Broker Settings - IBKR
    IBKR_HOST: "IP address of your Interactive Brokers TWS or Gateway. Usually 127.0.0.1 if running on the same computer.",
    IBKR_PORT: "Connection port for IBKR. Use 7497 for Paper Trading in TWS, 7496 for Live TWS, 4002 for Paper Gateway, 4001 for Live Gateway.",
    IBKR_CLIENT_ID: "Unique identifier for this connection. If running multiple bots, each needs a different Client ID.",
    IBKR_ACCOUNT_ID: "Your IBKR account number. Found in Account Management. Format like DU1234567 (paper) or U1234567 (live).",
    GUI_PNL_TIMEFRAME: "Select the timeframe for calculating Profit and Loss (PnL) on the dashboard and in analytics. '24h' is standard, but you can view performance over a week, month, or year for a broader perspective.",
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
    KRAKEN_API_SECRET: "Your Kraken Private Key. Required for authentication. Never share this!",
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
    COMMENTARY_ENABLED: "Master toggle for AI commentary. When disabled, no AI insights will be generated.",
    COMMENTARY_LLM_POLICY: "When to generate AI insights: 'disabled' to turn off, 'interval' for fixed timing, 'schedule' for specific times, 'on_signal' on every trade decision.",
    COMMENTARY_INTERVAL_MINUTES: "Time between AI updates when using 'Fixed Interval' policy. Range: 1-60 minutes.",
    COMMENTARY_LLM_DAILY_SLOTS: "Specific times to request AI commentary when using 'Scheduled Times' policy. Format: HH:MM, comma-separated.",
    COMMENTARY_LLM_MAX_CALLS_PER_DAY: "Hard limit on AI API calls per day. Prevents runaway costs regardless of policy.",
    GUI_CAPITAL_DISPLAY_MODE: "Choose what to show in the main 'Overall Capital' dashboard display. 'Overall Liquidity' shows your total net worth (Cash + Assets). 'Buying Power' shows only your available cash for trading.",

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
    SAFETY_ATR_SHIELD_ENABLED: "Advanced ATR-based protection. Moves stops to breakeven after 1x ATR move and uses dynamic trailing stops.",
    SAFETY_DRAWDOWN_BREAKER_ENABLED: "Account Circuit Breaker. If the account loses >5% from daily peak, all trades close and the bot pauses for 24h.",
    SAFETY_SESSION_LOCKOUT_ENABLED: "Prevents over-trading in choppy late-session markets. Automatically stops taking signals after 12:00 PM EST.",

    // Safety Suite 2.0 (New Additions)
    SAFETY_GREED_GUARD_ENABLED: "Profit Lock. Stops trading for the day once a specified daily profit target is hit (Quit while ahead).",
    SAFETY_CHURN_BURNER_ENABLED: "Anti-Churn. Limits the maximum number of trades per hour to prevent over-trading in chop.",
    SAFETY_VOLATILITY_VETO_ENABLED: "Volatility Filter. Blocks entries if the market is too dead (low ATR) or too explosive (high ATR).",
    SAFETY_STREAK_BREAKER_ENABLED: "Tilt Prevention. Pauses a specific symbol for 4 hours after 3 consecutive losses.",
    SAFETY_OPENING_SENTRY_ENABLED: "Morning Guard. Blocks all entries during the first 15 minutes of the market open (9:30-9:45 AM ET) to avoid volatility.",
    SAFETY_SENTIMENT_SHIELD_ENABLED: "AI Veto Shield. Uses your configured AI Model to inspect every potential entry. If the AI detects 'DANGEROUS' market structure, the trade is blocked regardless of the strategy signal. Smart Defense.",

    // Performance & Profits (Wealth Creation) - Detailed Layman Tooltips
    PERFORMANCE_MODE_NONE: "<strong>Safe Mode (Standard):</strong> No account acceleration. The bot operates with its core risk management and standard position sizing. Recommended for initial testing.",
    PERFORMANCE_MODE_HOUSE_MONEY: "<strong>House Money Accelerator:</strong> Uses 'The Casino's Money' to grow faster. Once a trade is nicely in profit (2R), the bot considers that risk 'covered' and unlocks capital to take a new setup.",
    PERFORMANCE_MODE_SNIPER: "<strong>The Sniper (A+ Grading):</strong> Only shoots when the target is perfect. Automatically triples risk (up to 5%) only when a setup scores >90/100.",
    PERFORMANCE_MODE_RUNNER: "<strong>The Runner (Moonshot):</strong> Locks in wins while chasing big trends. Sells half at target to secure profit, then trails the remainder for maximum gains.",
    PERFORMANCE_MODE_REGIME_SYNC: "<strong>Regime Sync (Adaptive):</strong> Automatically senses the 'Market Vibe'. Increases risk by 1.5x in strong trends and dials back to 0.5x in choppy markets.",
    PERFORMANCE_MODE_FLYWHEEL: "<strong>Compound Flywheel:</strong> Momentum Tool. Every time you make $200 in profit, the bot automatically bumps its future risk by 0.1%.",
    PERFORMANCE_MODE_STACKER: "<strong>Signal Stacker (Synergy):</strong> Combined Strength. Doubles risk when multiple internal strategies (e.g. SND + ICC) agree on the same entry.",

    // New Performance Weapons
    PERFORMANCE_MODE_KELLY: "<strong>Kelly Criterion Edge:</strong> Mathematical Precision. Calculates the exact optimal bet size based on your real-time win rate. It bets more when you are winning and scales down pennies when you are losing.",
    PERFORMANCE_MODE_HYDRA: "<strong>Correlation Hydra:</strong> Basket Scaling. Trades correlated assets (e.g., EURUSD and GBPUSD) as a single unit to capture global moves without exceeding total account risk.",
    PERFORMANCE_MODE_COIL: "<strong>Volatility Compression:</strong> The Spring. Triple risk on breakouts that happen after the market has been 'dead quiet' for several hours.",
    PERFORMANCE_MODE_VACUUM: "<strong>Liquidity Vacuum:</strong> Trap Hunter. Bets big on 'Fake Outs.' It waits for price to trap other traders on a false break, then enters heavy when price snaps back.",
    PERFORMANCE_MODE_ALPHA: "<strong>Time-of-Day Alpha:</strong> The Power Hour. Automatically doubles risk during high-volume sessions (Market Overlaps) and goes conservative during 'lunch hours'.",
    PERFORMANCE_MODE_GAMMA: "<strong>Gamma Squeeze:</strong> Price Velocity. Detects when price is moving too fast for regular hedging to keep up, then hitches a ride with heavy leverage until momentum fades.",
    PERFORMANCE_MODE_SMOOTH: "<strong>Equity Smoothing:</strong> Account Protector. Rewards new all-time highs with 0.5% risk boosts, and slashes risk in half during drawdowns until the bot 'earns' its right to trade large again.",

    // Meta-SCI (Auto Strategy)
    META_SCI_ENABLED: "<strong>Meta-SCI Master Toggle:</strong> Enables the 'Auto Strategy' ensemble logic. When ON, the bot runs ALL registered strategies in parallel and selects the winning setup based on consensus and entry score.",
    META_SCI_MIN_CONSENSUS: "<strong>Min Consensus:</strong> The minimum number of strategies that must agree on the same trade direction (Long or Short) before an entry is allowed. 1 = Winner takes all. 2+ = Safer, high-accuracy ensemble.",
    META_SCI_EXCLUDE_LIST: "<strong>Strategy Blacklist:</strong> Comma-separated list of strategy IDs to exclude from the Auto Strategy ensemble (e.g. 'evolution, quantum').",
    PERFORMANCE_MODE_SENTIMENT: "<strong>AI Sentiment Fusion:</strong> Hype Train. Only allows high-risk trades when your configured AI confirms that global news sentiment for the asset is 'Highly Bullish'.",
    PERFORMANCE_MODE_GHOST: "<strong>Harmonic Ghost:</strong> Order Flow. Only takes trades that align with 'Hidden Institutional Liquidity' levels filtered through specialized flow analysis.",
    PERFORMANCE_MODE_PHOENIX: "<strong>The Phoenix:</strong> Reversion Scaling. After the 'Streak Breaker' pause ends, the bot takes the next signal at Double Risk, assuming a win is mathematically overdue.",

    // Advanced Exit Shields
    SAFETY_STALE_SNIPER_ENABLED: "Kills positions that haven't hit a target within a set number of bars. Prevents 'Zombie' trades from tying up capital.",
    SAFETY_STALE_SNIPER_BARS: "Max candle bars to hold a sideways trade before the Sniper terminates it at market price.",
    SAFETY_FLASH_TRAP_ENABLED: "Volatility Protection. Instantly closes trades if ATR spikes by 2.5x average, protecting you from flash-crashes.",
    SAFETY_REGIME_FLIP_ENABLED: "HTF Trend Alignment. If the 4h trend turns against your 15m trade, the bot exits immediately to avoid a mismatch.",
    BLOCK_COUNTER_TREND_ENTRIES: "Counter-Trend Entry Guard. Prevents opening long positions when the higher timeframe is bearish, and short positions when it's bullish. Stops the bot from catching falling knives.",

    // Wealth Weapons Exits
    WEALTH_EXIT_GAMMA_ENABLED: "Velocity Trail. Tightens trailing stops exponentially during vertical moves to capture 90% of the squeeze.",
    WEALTH_EXIT_MOONSHOT_ENABLED: "Target Elevator. If a trade hits 1R target in under 3 bars, the TP is doubled automatically for a massive swing.",
    WEALTH_EXIT_BLOWOFF_ENABLED: "V-Top Seller. Sells 100% at market if volatility hits a 100-bar high while price is vertically extended.",
};

function getValue(key) {
    // Authority: Use the current session's timeframe from renderer.js
    if (key === 'GUI_PNL_TIMEFRAME' && typeof window.pnlTimeframe !== 'undefined') {
        return window.pnlTimeframe;
    }
    if (envData[key] !== undefined) return envData[key];
    // Fallback search in configData if not in flattened envData
    const mapping = CONFIG_MAP[key];
    if (mapping) {
        let val = configData;
        for (const p of mapping) {
            if (val[p] === undefined) { val = undefined; break; }
            val = val[p];
        }
        if (val !== undefined) return String(val);
    }
    return undefined;
}

function syncEnvData() {
    envData = {};
    // 1. Load from Global Config
    for (const [key, path] of Object.entries(CONFIG_MAP)) {
        let val = configData;
        for (const p of path) {
            if (val && val[p] !== undefined) val = val[p];
            else { val = undefined; break; }
        }
        if (val !== undefined) envData[key] = String(val);
    }

    // 2. Load from Secrets
    for (const [envKey, secretKey] of Object.entries(SECRETS_MAP)) {
        if (secretsData[secretKey]) envData[envKey] = secretsData[secretKey];
    }

    // 3. Load from Active Profile (Overrides)
    const active = configData.active_profile;
    if (active && configData.profiles && configData.profiles[active]) {
        const profile = configData.profiles[active];
        for (const [key, val] of Object.entries(profile)) {
            envData[key.toUpperCase()] = String(val);
        }
    }
}

// ═══════════════════════════════════════════════════════════
// CONFLICT RESOLUTION & CONSTRAINT ENGINE
// ═══════════════════════════════════════════════════════════

const CONFLICT_MAP = {
    // Mode -> { targetKeys: [], message: "", type: 'modal'|'ghost' }
    'performance:hydra': {
        targets: ['SMART_POSITIONS_ENABLED', 'MULTI_POSITION_ENABLED'],
        message: "<strong>The Hydra</strong> requires centralized basket risk control. This will override your manual 'Smart Positions' and 'Multi-Position' settings to allow for coordinated scaling across correlated assets.",
        type: 'modal'
    },
    'performance:alpha': {
        targets: ['SESSION_GATE_ENABLED', 'FRIDAY_FADE_ENABLED'],
        message: "<strong>Time-of-Day Alpha</strong> manages its own session high-volume gates and Friday liquidity filters. Enabling this will take control of your 'Session Gate' and 'Friday Fade' settings.",
        type: 'modal'
    },
    'performance:smooth': {
        targets: [],
        message: "<strong>Equity Smoothing</strong> uses its own principal protection model.",
        type: 'modal'
    },
    'performance:gamma': {
        targets: ['TRAILING_STOP_ENABLED'],
        message: "<strong>Gamma Squeeze</strong> uses hyper-tight trailing stops to lock in velocity. This will override your standard 'Trailing Stop' settings.",
        type: 'ghost'
    },
    'performance:sniper': {
        targets: ['RISK_PER_TRADE_PCT', 'RISK_PER_TRADE_DOLLARS'],
        message: "<strong>The Sniper</strong> uses specialized 5% risk logic for A+ setups. This ghosts your standard risk percentage/dollar settings.",
        type: 'ghost'
    },
    'performance:kelly': {
        targets: ['RISK_PER_TRADE_PCT', 'RISK_PER_TRADE_DOLLARS'],
        message: "<strong>Kelly Criterion</strong> uses math-based optimal sizing. This ghosts your standard risk percentage/dollar settings.",
        type: 'ghost'
    },
    'SAFETY_STABILITY_MODE_ENABLED:true': {
        targets: ['PERFORMANCE_MODE'],
        message: "<strong>Stability Mode</strong> is a survival-first protocol. Enabling it will reset your Performance Mode to 'Standard' and enforce a strict 1% risk ceiling.",
        type: 'modal'
    },
    'MULTI_POSITION_ENABLED:false': {
        targets: ['MAX_CONCURRENT_POSITIONS'],
        message: '',
        type: 'ghost'
    },
    'SABBATH_ASTRONOMICAL:true': {
        targets: [],
        message: "<strong>Astronomical Sabbath</strong> uses your geographic coordinates to calculate exact sunset times. Please verify your Latitude and Longitude are set correctly.",
        type: 'modal'
    }
};

/**
 * Checks for conflicts and handles UI enforcement (modals or ghosting).
 */
function checkConflicts(sourceKey, value) {
    const conflictId = `${sourceKey}:${value}`;
    const config = CONFLICT_MAP[conflictId];

    if (config) {
        if (config.type === 'modal') {
            showConflictModal(
                "Optimization Conflict",
                config.message,
                () => {
                    // On Confirm: Disable targets and set source
                    config.targets.forEach(t => updateValue(t, 'false'));
                    updateValue(sourceKey, value);
                    renderTab();
                }
            );
            return true; // Conflict intercepted
        } else if (config.type === 'ghost') {
            // Auto-handle ghosting targets
            config.targets.forEach(t => updateValue(t, 'false'));
        }
    }
    return false;
}

function showConflictModal(title, message, onConfirm) {
    // Check if modal container exists
    let modal = document.getElementById('conflict-modal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'conflict-modal';
        modal.className = 'fixed inset-0 z-[1000] flex items-center justify-center p-4 bg-black/80 backdrop-blur-md opacity-0 pointer-events-none transition-opacity duration-300';
        modal.innerHTML = `
            <div class="bg-slate-900 border border-amber-500/30 rounded-2xl p-6 max-w-md w-full shadow-2xl shadow-amber-500/10">
                <div class="flex items-center gap-3 mb-4">
                    <span class="material-symbols-outlined text-amber-500">warning</span>
                    <h3 class="text-lg font-bold text-white" id="modal-title"></h3>
                </div>
                <div class="text-sm text-slate-300 mb-6 leading-relaxed" id="modal-message"></div>
                <div class="flex gap-3 justify-end">
                    <button id="modal-cancel" class="px-4 py-2 rounded-lg bg-white/5 text-slate-400 hover:bg-white/10 hover:text-white transition-all text-sm font-medium">Cancel</button>
                    <button id="modal-confirm" class="px-4 py-2 rounded-lg bg-amber-500 text-black hover:bg-amber-400 transition-all text-sm font-bold">Proceed & Disable Conflict</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
    }

    modal.querySelector('#modal-title').innerHTML = title;
    modal.querySelector('#modal-message').innerHTML = message;

    const confirmBtn = modal.querySelector('#modal-confirm');
    const cancelBtn = modal.querySelector('#modal-cancel');

    const closeModal = () => {
        modal.classList.add('opacity-0', 'pointer-events-none');
    };

    confirmBtn.onclick = () => {
        onConfirm();
        closeModal();
    };
    cancelBtn.onclick = closeModal;

    modal.classList.remove('opacity-0', 'pointer-events-none');
}

/**
 * Determines if a setting key is currently overridden by an active mode.
 */
function isOverridden(key) {
    // [STABILITY] Global override for aggressive performance modes and risk settings
    if (getValue('SAFETY_STABILITY_MODE_ENABLED') === 'true') {
        const stabilityGhosted = [
            'PERFORMANCE_MODE',
            'RISK_PER_TRADE_PCT',
            'RISK_PER_TRADE_DOLLARS',
            'ICC_ENTRY_SCORE_THRESHOLD'
        ];
        if (stabilityGhosted.includes(key) || (typeof key === 'string' && key.startsWith('PERF_') && key !== 'PERF_STABILITY')) {
            return true;
        }
    }

    const performanceMode = getValue('PERFORMANCE_MODE');
    const activePerformance = `performance:${performanceMode}`;
    const config = CONFLICT_MAP[activePerformance];
    return config && config.targets.includes(key);
}

// ═══════════════════════════════════════════════════════════
// STRATEGY DEFINITIONS with detailed descriptions
// ═══════════════════════════════════════════════════════════

const STRATEGIES = {
    orb_breakout: {
        name: "ORB (Opening Range Breakout)",
        shortDesc: "NY Opening Range Breakout",
        description: "The Opening Range Breakout (ORB) strategy. It watches the first 15 minutes of the New York Stock Market open (9:30 AM ET) to see where the big money is moving. It waits for the price to break out of that range, come back to test the level for safety, and form a 'flag' pattern before entering. Very safe, very precise.",
        style: "Breakout",
        risk: "Low-Medium",
        bestFor: "NY Open (9:30-11:00 ET)",
        stats: { verified: "Simulated", winRate: "High", riskReward: "2:1" }
    },
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
    },
    meta_sci: {
        name: 'Meta-SCI',
        icon: 'auto_awesome',
        shortDesc: 'AI-Enhanced Ensemble Strategy',
        description: "The ultimate AI Brain. It runs multiple trading strategies at the same time and uses an AI ensemble (Meta-SCI) to decide which one has the best chance of winning right now. It's like having a team of expert traders in a room, and the AI acts as the manager who only listens to the most successful ones for each specific trade.",
        style: "AI Ensemble",
        risk: "Dynamic",
        bestFor: "Complex markets, regime changes",
        stats: { method: "Ensemble", ai: "Gemini Pro", strategies: "10+" }
    },
    trend_rider: {
        name: 'Trend Rider',
        shortDesc: 'EMA Pullback in Strong Trend',
        description: "Proven institutional method. Waits for price to pull back to the 21 EMA during a confirmed strong trend, then enters on the bounce. Requires HTF trend strength ≥ 0.5 and RSI between 40-60 to confirm a pullback, not a reversal. Targets 2:1 R:R with trailing to EMA after 1R profit.",
        style: "Trend Following",
        risk: "Medium",
        bestFor: "Strong trending markets, forex & crypto",
        stats: { indicator: "21 EMA", target: "2.0R", filter: "HTF ≥ 0.5" }
    },
    session_momentum: {
        name: 'Session Momentum',
        shortDesc: 'VWAP + Volume Surge at Open',
        description: "Captures the initial directional move during the highest-volume period of the trading day. Active only in the first 30 minutes of London (08:00-08:30 UTC) or New York (09:30-10:00 ET) session. Requires a VWAP break with 2× average volume surge for entry.",
        style: "Momentum / Session",
        risk: "Medium-High",
        bestFor: "London & NY session opens",
        stats: { indicator: "VWAP", volume: "2× avg", target: "2.0R" }
    },
    bearish_engulfing: {
        name: 'Engulfing Reversal',
        shortDesc: 'Candle Pattern at Key Structure',
        description: "Classic price action reversal pattern. Enters when a bullish or bearish engulfing candle forms at a key structural level (swing high/low) with HTF alignment. Optional RSI divergence detection for higher probability setups. Stop placed beyond the engulfing candle's wick.",
        style: "Price Action / Reversal",
        risk: "Medium",
        bestFor: "Reversal zones, supply/demand levels",
        stats: { pattern: "Engulfing", target: "2.0R", bonus: "RSI Divergence" }
    },
    // ──────────────────────────────────────────────────────────────
    // 🪙 CRYPTO-SPECIFIC STRATEGIES
    // HOW TO ADD A NEW STRATEGY:
    //   1. Add entry here with name, shortDesc, description, style, risk, bestFor, stats
    //   2. Add to System Tab dropdown (renderSystemTab → STRATEGY_VARIANT items)
    //   3. Add to Strategy Toolbox grid (renderStrategyToolbox → strategies array)
    //   4. Add to renderer.js Profile Editor (STRATEGY_OPTIONS array)
    //   5. Add to settings.js System Tab dropdown (STRATEGY_VARIANT items)
    //   6. Register in: src/tradebot_sci/strategy/engine.py STRATEGY_MAP
    //   7. Add to Meta-SCI regime groups if applicable: strategy/variants/meta_sci.py
    // ──────────────────────────────────────────────────────────────
    crypto_rsi_macd: {
        name: 'RSI + MACD (Crypto)',
        shortDesc: 'Classic Momentum Combo for Crypto',
        description: "Combines RSI oversold/overbought readings with MACD crossover confirmations. Designed for 24/7 crypto markets — no session gating. Waits for RSI to exit extreme zones while MACD histogram flips direction. ATR-based stops.",
        style: "Momentum / Crypto",
        risk: "Medium",
        bestFor: "Trending crypto markets, BTC/ETH swing trades",
        stats: { rsi: "30/70", macd: "12/26/9", target: "2.0R" }
    },
    crypto_vwap_reversion: {
        name: 'VWAP Reversion (Crypto)',
        shortDesc: 'Mean Reversion to VWAP',
        description: "Enters when price deviates significantly from the volume-weighted average price and shows signs of reverting. Uses Bollinger-style bands around VWAP with volume confirmation. Optimized for high-volume crypto pairs.",
        style: "Mean Reversion / Crypto",
        risk: "Medium",
        bestFor: "Ranging crypto markets, high-volume pairs",
        stats: { indicator: "VWAP", bands: "2σ", target: "1.5R" }
    },
    crypto_double_macd: {
        name: 'Double MACD Scalper (Crypto)',
        shortDesc: 'Dual-Timeframe MACD Momentum',
        description: "Uses two MACD indicators on different timeframes for confluence. Fast MACD (5/13/4) for entry timing, slow MACD (12/26/9) for trend filter. Designed for tight crypto scalps with quick exits on momentum fade.",
        style: "Scalping / Crypto",
        risk: "High",
        bestFor: "Active crypto pairs, scalping BTC/SOL",
        stats: { fast: "5/13/4", slow: "12/26/9", target: "1.5R" }
    },
    crypto_grid: {
        name: 'Virtual Grid (Crypto)',
        shortDesc: 'Grid Trading with Dynamic Levels',
        description: "Places a virtual grid of buy/sell zones around the current market price. Profits from price oscillation within a range. Automatically adjusts grid spacing based on ATR volatility. No physical grid orders — all managed internally.",
        style: "Grid / Crypto",
        risk: "Medium-High",
        bestFor: "Sideways/ranging crypto markets",
        stats: { levels: "Dynamic", spacing: "ATR-based", target: "0.5-1.0R" }
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
    safety: { icon: 'shield', label: 'Safety', render: renderSafetyTab },
    performance: { icon: 'trending_up', label: 'Performance', render: renderPerformanceTab },
    brokers: { icon: 'lan', label: 'Brokers', render: renderBrokersTab },
    ai: { icon: 'auto_awesome', label: 'Intelligence', render: renderAITab },
    schedule: { icon: 'event_repeat', label: 'Schedule', render: renderScheduleTab },
    appearance: { icon: 'palette', label: 'Appearance', render: renderAppearanceTab },
    advanced: { icon: 'terminal', label: 'Advanced', render: renderAdvancedTab }
};

// ═══════════════════════════════════════════════════════════
// INITIALIZATION
// ═══════════════════════════════════════════════════════════

async function init() {
    // Standardize API (support both window.api and window.electronAPI)
    if (!window.api && window.electronAPI) {
        window.api = window.electronAPI;
    }

    // Prevent re-initialization
    if (settingsInitialized) {
        renderTab();
        return;
    }
    settingsInitialized = true;

    setupGlobalEvents();

    // Listen for bot status updates
    if (window.api?.onBotStatus) {
        window.api.onBotStatus((status) => {
            updateBotStatusUI(status.running);
        });
        window.api.getBotStatus();
    }

    // Load data from backend (Simplified JSON loading)
    await loadSettings();
    switchTab('system');
}

async function loadSettings() {
    if (window.api) {
        try {
            configData = await window.api.readConfig() || {};
            secretsData = await window.api.readSecrets() || {};
            syncEnvData();
            profilesContent = JSON.stringify(configData, null, 2);
            console.log("[SETTINGS] Config loaded and synced.");

            // Listen for external config changes
            if (window.api.onConfigUpdated) {
                window.api.onConfigUpdated((newConfig) => {
                    console.log("[SETTINGS] Syncing with external config change...");
                    configData = newConfig;
                    syncEnvData();
                    profilesContent = JSON.stringify(configData, null, 2);
                    renderTab();
                    showNotice("Config Synced", "purple");
                });
            }
        } catch (e) {
            console.error("[SETTINGS] Load Error:", e);
            showNotice("Failed to load settings", "red");
        }
    } else {
        console.warn("[SETTINGS] API not found. Using mock data.");
        configData = { global: { bot_mode: 'continuous' }, profiles: {} };
        syncEnvData();
    }
}


/**
 * Checks all settings for structural conflicts (e.g. Stability Mode vs Kelly)
 * Returns true if any changes were made.
 */
function checkAllConflicts() {
    let changed = false;
    const active = configData.active_profile;
    const profile = configData.profiles?.[active];
    if (!profile) return false;

    // 1. Stability Mode Conflict Logic
    const stabilityEnabled = getValue('SAFETY_STABILITY_MODE_ENABLED') === 'true';

    if (stabilityEnabled) {
        // Enforce Performance Mode = Standard
        let currentPerf = getValue('PERFORMANCE_MODE') || 'none';
        if (currentPerf.includes('kelly') || currentPerf.includes('flywheel')) {
            console.warn("[CONFLICT] Stability Mode active; resetting aggressive performance modes.");
            updateValue('PERFORMANCE_MODE', 'stability');
            changed = true;
        }

        // Enforce Risk Ceiling (1%)
        const riskPct = parseFloat(getValue('RISK_PER_TRADE_PCT') || 0);
        if (riskPct > 0.01) {
            console.warn("[CONFLICT] Stability Mode active; clamping risk to 1%.");
            updateValue('RISK_PER_TRADE_PCT', '0.01');
            changed = true;
        }

        // Enforce Score Threshold (75)
        const scoreThreshold = parseFloat(getValue('ICC_ENTRY_SCORE_THRESHOLD') || 0);
        if (scoreThreshold < 75) {
            console.warn("[CONFLICT] Stability Mode active; raising score threshold to 75.");
            updateValue('ICC_ENTRY_SCORE_THRESHOLD', '75');
            changed = true;
        }
    }

    return changed;
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
            if (window.api?.closeWindow) {
                window.api.closeWindow();
            }
        });
    }

    if (btnMinimize) {
        btnMinimize.addEventListener('click', () => {
            if (window.api?.minimizeWindow) {
                window.api.minimizeWindow();
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
    if (!configData.profiles) {
        return [
            { value: 'auto_schedule', label: 'Auto - Equities & Crypto' },
            { value: 'forex_intraday', label: 'Forex Intraday' },
            { value: 'forex_oanda', label: 'OANDA Forex' },
            { value: 'crypto_247', label: 'Crypto 24/7' },
            { value: 'intraday', label: 'Standard Intraday' },
            { value: 'coinbase_futures', label: 'Coinbase Futures' },
            { value: 'coinbase_futures_nano', label: 'Coinbase Nano Futures' }
        ];
    }

    return Object.keys(configData.profiles).map(value => {
        const label = value.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
            .replace('Forex', 'Forex ').replace('Crypto', 'Crypto ').trim();
        return { value, label };
    });
}

/**
 * Get settings from the currently active profile in settings_profiles.yaml.
 * This ensures the Settings UI reflects the actual running configuration.
 */
function getActiveProfileSettings() {
    const activeProfile = configData.active_profile || 'auto_schedule';
    const settings = {
        strategy_variant: 'rubberband_reaper',
        strategies: {}
    };

    if (configData.profiles && configData.profiles[activeProfile]) {
        const profile = configData.profiles[activeProfile];
        if (profile.strategy_variant) settings.strategy_variant = profile.strategy_variant;
        if (profile.strategies) settings.strategies = { ...profile.strategies };
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
    const locked = options.locked || isOverridden(key);

    card.className = `control-card ${locked ? 'opacity-50 pointer-events-none grayscale-[0.2]' : ''}`;
    card.dataset.key = key;

    let finalDesc = desc;
    if (locked) {
        if (isOverridden(key)) {
            const activePerformance = envData['PERFORMANCE_MODE'];
            finalDesc = `<span class="text-amber-400 font-bold">[OVERRIDDEN]</span> Managed by active Performance Mode (${activePerformance})`;
        } else if (options.lockMessage) {
            finalDesc = `<span class="text-sky-400 font-bold">[LOCKED]</span> ${options.lockMessage}`;
        } else {
            finalDesc = `<span class="text-slate-400 font-bold">[LOCKED]</span> This setting is unavailable in your current configuration.`;
        }
    }

    card.innerHTML = `
        <div class="card-info">
            <span class="card-title">${title}</span>
            <span class="card-desc">${finalDesc}</span>
        </div>
        <div class="card-control no-drag"></div>
    `;

    const controlContainer = card.querySelector('.card-control');
    const value = getValue(key) || options.default || '';

    const tooltipContent = options.tooltip || TOOLTIPS[key];
    if (tooltipContent && !locked) {
        card.addEventListener('mouseenter', (e) => showTooltip(e, key, tooltipContent));
        card.addEventListener('mouseleave', hideTooltip);
    }

    if (controlType === 'toggle') {
        const toggle = document.createElement('div');
        toggle.className = `toggle ${value === 'true' ? 'toggle-active' : ''}`;
        toggle.addEventListener('click', (e) => {
            e.stopPropagation();
            const isNowActive = !toggle.classList.contains('toggle-active');
            const strVal = isNowActive ? 'true' : 'false';

            // Check for conflicts (Modals/Auto-Ghosting)
            if (checkConflicts(key, strVal)) return;

            toggle.classList.toggle('toggle-active', isNowActive);
            updateValue(key, strVal);
            renderTab(); // Refresh to apply UI overrides (ghosting)
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
        select.addEventListener('change', (e) => {
            updateValue(key, e.target.value);
            if (options.onChange) options.onChange(e.target.value);
        });
        controlContainer.appendChild(select);
    }
    else if (controlType === 'time') {
        const timeInput = document.createElement('input');
        timeInput.type = 'time';
        timeInput.className = 'input-field time-picker';
        // Backend stores integer hour (e.g. 16), convert to HH:00
        const hour = parseInt(value) || parseInt(options.default) || 12;
        timeInput.value = String(hour).padStart(2, '0') + ':00';
        timeInput.addEventListener('change', (e) => {
            // Extract hour from HH:MM and save as integer string
            const selectedHour = parseInt(e.target.value.split(':')[0]);
            updateValue(key, String(selectedHour));
        });
        controlContainer.appendChild(timeInput);
    }

    return card;
}

function createSliderCard(title, desc, key, min, max, step, unit = '%') {
    const card = document.createElement('div');
    card.className = 'slider-card';
    let rawValue = getValue(key) || min;

    // The model stores fractions (0.045 = 4.5%).
    // The slider displays human-friendly percentages (4.5%).
    // Convert stored fraction → display % on load, and display % → fraction on save.
    const isPct = (unit === '%');
    const displayValue = isPct && rawValue < 1 ? (rawValue * 100).toFixed(1) : rawValue;

    card.innerHTML = `
        <div class="slider-header">
            <div>
                <div class="slider-title">${title}</div>
                <div class="slider-desc">${desc}</div>
            </div>
            <div class="slider-value">${displayValue}<span class="slider-value-small">${unit}</span></div>
        </div>
        <input type="range" class="slider-input" min="${min}" max="${max}" step="${step}" value="${displayValue}">
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
        // Save as fraction if unit is '%' (e.g. slider 4.5 → save 0.045)
        const saveValue = isPct ? (parseFloat(e.target.value) / 100).toString() : e.target.value;
        updateValue(key, saveValue);
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

    // Core Runtime
    section.appendChild(createSectionHeader('Core Runtime', 'dashboard'));

    section.appendChild(createCard('Active Profile', 'Select symbol universe & trading cadence', 'APP_PROFILE', 'dropdown', {
        items: Object.keys(configData.profiles || {}).map(p => ({ value: p, label: p }))
    }));

    section.appendChild(createCard('Strategy Variant', 'Trading strategy algorithm', 'STRATEGY_VARIANT', 'dropdown', {
        items: [
            { value: 'rubberband_reaper', label: 'Rubberband Reaper - Anti-Martingale' },
            { value: 'robocop', label: 'RoboCop - Aggressive ICC' },
            { value: 'evolution', label: 'Robot Evolution - NTZ Scalper' },
            { value: 'quantum', label: 'Quantum - Trend Following' },
            { value: 'mean_reversion', label: 'Mean Reversion - Bollinger & RSI' },
            { value: 'hyper_scalper', label: 'HyperScalper - EMA Crossover' },
            { value: 'london_breakout', label: 'London Breakout' },
            { value: 'orb_breakout', label: 'ORB - NY Session Break & Retest' },
            { value: 'volatility_breakout', label: 'Volatility Breakout' },
            { value: 'aggregator', label: 'Singularity Aggregator - Multi-Strategy' },
            { value: 'meta_sci', label: 'Meta-SCI - AI-Enhanced Ensemble' },
            { value: 'icc_core', label: 'ICC - Indication, Correction, Continuation' },
            { value: 'supply_demand', label: 'Supply & Demand - Institutional' },
            { value: 'trend_rider', label: 'Trend Rider - EMA Pullback' },
            { value: 'session_momentum', label: 'Session Momentum - VWAP at Open' },
            { value: 'bearish_engulfing', label: 'Engulfing Reversal - Key Structure' },
            // 🪙 Crypto-Specific Strategies
            { value: 'crypto_rsi_macd', label: '🪙 RSI + MACD (Crypto)' },
            { value: 'crypto_vwap_reversion', label: '🪙 VWAP Reversion (Crypto)' },
            { value: 'crypto_double_macd', label: '🪙 Double MACD Scalper (Crypto)' },
            { value: 'crypto_grid', label: '🪙 Virtual Grid (Crypto)' }
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

    section.appendChild(createCard('PnL Timeframe', 'Select performance measurement period for the dashboard', 'GUI_PNL_TIMEFRAME', 'dropdown', {
        items: [
            { value: 'holdings', label: 'Active Holdings Only' },
            { value: '24h', label: 'Last 24 Hours (Realized + Unrealized)' },
            { value: 'week', label: 'Last 7 Days (Realized + Unrealized)' },
            { value: 'month', label: 'Last 30 Days (Realized + Unrealized)' },
            { value: 'year', label: 'Last Year (Realized + Unrealized)' },
            { value: 'all', label: 'All Time (Realized + Unrealized)' }
        ],
        default: '24h'
    }));



    // Runtime Control (Start/Stop/Restart)
    section.appendChild(createSectionHeader('Runtime Control', 'play_circle'));

    const controlGrid = document.createElement('div');
    controlGrid.className = 'card-grid card-grid-3 mb-8';

    const btnStart = createControlButton('Start Bot', 'play_arrow', 'teal', () => {
        window.api.startBot();
        showNotice('Bot start command sent', 'teal');
    });
    const btnStop = createControlButton('Stop Bot', 'stop', 'red', () => {
        window.api.stopBot();
        showNotice('Bot stop command sent', 'red');
    });
    const btnRestart = createControlButton('Restart', 'refresh', 'purple', () => {
        window.api.restartBot();
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

    section.appendChild(createDivider());
    section.appendChild(createSectionHeader('Market Guards', 'security'));
    section.appendChild(createCard('PDT Safety Guard', 'Prevent US Equity 25k rule violations', 'PDT_GUARD_ENABLED', 'toggle'));

    container.appendChild(section);
}


function renderStrategyTab(container) {
    // Sync envData with active profile settings so UI reflects actual config
    // Profile settings are authoritative - but skip keys with pending local changes
    const profileSettings = getActiveProfileSettings();
    const assetKeyMap = { crypto: 'STRATEGY_CRYPTO', forex: 'STRATEGY_FOREX', stocks: 'STRATEGY_STOCKS', etf: 'STRATEGY_ETF', metals: 'STRATEGY_METALS', futures: 'STRATEGY_FUTURES' };
    for (const [asset, envKey] of Object.entries(assetKeyMap)) {
        if (localChanges[envKey]) continue; // Preserve unsaved user selection
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
        { id: 'yaml', label: 'JSON Editor' }
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
            const currentStrategy = getValue(asset.envKey) || 'rubberband_reaper';
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
        grid.appendChild(createSliderCard('Default Risk %', 'Fallback equity risk', 'RISK_PER_TRADE_PCT', 0.1, 20.0, 0.1, '%'));
        grid.appendChild(createSliderCard('Max Exposure', 'Total open risk limit', 'MAX_EXPOSURE_PCT', 5, 100, 5, '%'));
        grid.appendChild(createSliderCard('Daily Loss Limit', 'Circuit breaker — stops trading for the day 🍞', 'LIMIT_LOSS_DAILY_PCT', 1, 20, 1, '%'));
        section.appendChild(grid);

        section.appendChild(createCard('Fixed Risk USD', 'Fixed dollar risk - overrides %', 'RISK_PER_TRADE_DOLLARS', 'input', { number: true, placeholder: '0.00' }));
        section.appendChild(createCard('Max Loss Per Trade USD', 'Hard cap per trade', 'MAX_LOSS_PER_TRADE_DOLLARS', 'input', { number: true, default: '500' }));

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('Position Management', 'layers'));

        const grid2 = document.createElement('div');
        grid2.className = 'card-grid';
        // (Moved Multi-Position and Smart Positions to Safety Tab)
        section.appendChild(grid2);
        section.appendChild(createCard('Opening Range Sentry', 'Avoid first 15 mins (9:30-9:45 ET)', 'SAFETY_OPENING_SENTRY_ENABLED', 'toggle', { default: 'true' }));
        section.appendChild(createCard('AI Sentiment Shield', 'Smart Veto. AI blocks "Dangerous" setups.', 'SAFETY_SENTIMENT_SHIELD_ENABLED', 'toggle'));

        // Initialize Financed Risk state
        setTimeout(() => {
            const multiEnabled = getValue('MULTI_POSITION_ENABLED') === 'true';
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

        section.appendChild(createCard('The "Greedy Exit"', 'Enable trailing stop logic', 'TRAILING_STOP_ENABLED', 'toggle'));
        section.appendChild(createCard('The "Sniper Target"', 'Target Reward Ratio - e.g. 2.0 = 2x Risk', 'RISK_REWARD_RATIO', 'input', {
            number: true,
            placeholder: '2.0',
            default: '2.0'
        }));
        section.appendChild(createCard('Trailing Stop Min Profit %', 'Min profit to activate trail', 'TRAILING_STOP_MIN_PROFIT_PCT', 'input', { number: true, default: '1.0', min: 0, max: 10, step: 0.5 }));
        section.appendChild(createCard('Stop ATR Multiplier', 'Distance from structure', 'STOP_ATR_MULTIPLIER', 'input', { number: true, default: '1.5', min: 0.5, max: 3, step: 0.1 }));

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('Hold Time Rules', 'timer'));

        section.appendChild(createCard('Min Hold Hours', '0 = disabled', 'MIN_HOLD_HOURS', 'input', { number: true, default: '0', min: 0, max: 48 }));
        section.appendChild(createCard('Max Hold Hours', '0 = disabled', 'MAX_HOLD_HOURS', 'input', { number: true, default: '0', min: 0, max: 168 }));
        section.appendChild(createCard('HTF Neutral Exit Bars', 'Exit after N neutral bars', 'HTF_NEUTRAL_EXIT_BARS', 'input', { number: true, default: '48', min: 0, max: 200 }));

    } else if (subTabs.strategy === 'yaml') {
        section.appendChild(createSectionHeader('Config JSON Editor', 'code'));
        section.appendChild(createWarningBox('<strong>Warning:</strong> Direct JSON editing. Invalid syntax will break the bot.'));

        const editor = document.createElement('textarea');
        editor.id = 'profiles-editor';
        editor.value = profilesContent;
        editor.style.height = '500px';
        editor.style.fontFamily = 'monospace';
        editor.addEventListener('input', (e) => {
            profilesContent = e.target.value;
            localChanges['_config_'] = true;
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
                { value: 'practice', label: 'Practice - Demo' },
                { value: 'live', label: 'Live - Real Money' }
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
        section.appendChild(createCard('Private Key', 'Kraken Private Key', 'KRAKEN_API_SECRET', 'input', { password: true }));
        section.appendChild(createCard('Environment', 'Trading Environment', 'KRAKEN_ENVIRONMENT', 'dropdown', {
            items: [
                { value: 'production', label: 'Production - Live' },
                { value: 'sandbox', label: 'Sandbox - Test' }
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
                4. Paste your API Key and Private Key here<br>
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
                { value: 'sandbox', label: 'Sandbox - Test' },
                { value: 'production', label: 'Production - Live' }
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
                { value: 'LIMIT', label: 'Limit - Safer' },
                { value: 'MARKET', label: 'Market - Guaranteed Fill' }
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
                { value: 'paxos', label: 'Paxos - Native API' },
                { value: 'oanda', label: 'OANDA - Spot via Paxos' },
                { value: 'ibkr', label: 'Interactive Brokers' }
            ],
            default: 'ccxt'
        }));

        section.appendChild(createCard('Forex Broker', 'eur/usd, jpy', 'BROKER_FOREX', 'dropdown', {
            items: [
                { value: 'ibkr', label: 'Interactive Brokers - Primary' },
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
            { value: 'openai', label: 'OpenAI - GPT-4' },
            { value: 'claude', label: 'Anthropic Claude' },
            { value: 'deepseek', label: 'DeepSeek' },
            { value: 'openrouter', label: 'OpenRouter' },
            { value: 'local', label: 'Local AI - Ollama / LM Studio' }
        ],
        onChange: () => renderTab() // Force re-render to update dependent locks
    }));

    section.appendChild(createCard('Local Endpoint URL', 'e.g. http://localhost:11434/v1', 'TRADE_SCI_API_BASE_URL', 'input', {
        locked: envData['TRADE_SCI_PROVIDER'] !== 'local',
        lockMessage: 'Only available when "Local AI" provider is selected.',
        placeholder: 'http://localhost:11434/v1'
    }));

    section.appendChild(createCard('Model Name', 'e.g., gemini-1.5-pro-002', 'TRADE_SCI_MODEL_NAME', 'input'));
    section.appendChild(createCard('API Key', 'Provider authentication', 'CHATGPT_KEY', 'input', { password: true }));
    section.appendChild(createCard('Temperature', 'Response randomness - 0-2', 'AI_TEMPERATURE', 'input', { number: true, default: '0.2', min: 0, max: 2, step: 0.1 }));
    section.appendChild(createCard('Max Tokens', 'Response length limit', 'AI_MAX_TOKENS', 'input', { number: true, default: '2048' }));

    section.appendChild(createDivider());
    section.appendChild(createSectionHeader('AI Commentary', 'comment'));

    // Master toggle
    section.appendChild(createCard('Enable Commentary', 'Show AI insights in dashboard', 'COMMENTARY_ENABLED', 'toggle', { default: 'true' }));

    // Policy dropdown with cleaner options
    section.appendChild(createCard('Commentary Policy', 'When to generate insights', 'COMMENTARY_LLM_POLICY', 'dropdown', {
        items: [
            { value: 'disabled', label: 'Disabled' },
            { value: 'interval', label: 'Fixed Interval' },
            { value: 'schedule', label: 'Scheduled Times' },
            { value: 'on_signal', label: 'On Trade Signals' }
        ]
    }));

    // Interval slider (shown when policy is 'interval')
    section.appendChild(createCard('Interval - Minutes', 'Time between AI updates', 'COMMENTARY_INTERVAL_MINUTES', 'input', {
        number: true,
        default: '5',
        min: 1,
        max: 60,
        step: 1
    }));

    // Daily slots (shown when policy is 'schedule')
    section.appendChild(createCard('Scheduled Times', 'Comma-separated HH:MM', 'COMMENTARY_LLM_DAILY_SLOTS', 'input', { placeholder: '09:00,12:00,18:00' }));

    // Daily limit
    section.appendChild(createCard('Daily API Limit', 'Max AI calls per day', 'COMMENTARY_LLM_MAX_CALLS_PER_DAY', 'input', { number: true, default: '50' }));

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
    section.appendChild(createCard('Start Time', 'Friday sunset - HH:MM', 'SABBATH_START_LOCAL', 'input', { default: '18:00' }));
    section.appendChild(createCard('End Time', 'Saturday sunset - HH:MM', 'SABBATH_END_LOCAL', 'input', { default: '18:00' }));

    section.appendChild(createDivider());
    section.appendChild(createSectionHeader('Session Gate', 'access_time'));

    section.appendChild(createCard('Session Gate Enabled', 'Enforce session health checks', 'SESSION_GATE_ENABLED', 'toggle', { default: 'true' }));
    section.appendChild(createCard('Overlap Start Hour', 'Active session start - 0-23', 'SESSION_OVERLAP_START_HOUR', 'input', { number: true, default: '12', min: 0, max: 23 }));
    section.appendChild(createCard('Overlap End Hour', 'Active session end - 0-23', 'SESSION_OVERLAP_END_HOUR', 'input', { number: true, default: '16', min: 0, max: 23 }));
    section.appendChild(createCard('Session Timezone', 'For overlap hours', 'SESSION_OVERLAP_TIMEZONE', 'input', { default: 'UTC' }));
    section.appendChild(createCard('Auto Schedule', 'Auto switch equities/crypto', 'AUTO_SCHEDULE_ENABLED', 'toggle'));

    container.appendChild(section);

    // City resolver event
    resolver.querySelector('#btn-resolve').addEventListener('click', async () => {
        const city = resolver.querySelector('#city-input').value;
        if (!city) return;

        const btn = resolver.querySelector('#btn-resolve');
        btn.textContent = 'RESOLVING...';

        const res = await window.api.resolveCity(city);
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

// ═══════════════════════════════════════════════════════════
// APPEARANCE TAB (Theme Selection)
// ═══════════════════════════════════════════════════════════

function renderAppearanceTab(container) {
    const section = document.createElement('div');
    section.className = 'settings-section';

    const themes = window.ThemeEngine ? window.ThemeEngine.getThemes() : {};
    const activeThemeId = window.ThemeEngine ? window.ThemeEngine.getActiveThemeId() : 'obsidian';
    const isRandom = activeThemeId === 'random';

    // Header
    section.appendChild(createSectionHeader('Theme', 'palette'));

    // Description
    const desc = document.createElement('div');
    desc.className = 'card-desc';
    desc.style.cssText = 'margin-bottom: 24px; font-size: 13px; line-height: 1.6;';
    desc.textContent = 'Choose a visual theme for your trading dashboard. Changes apply instantly.';
    section.appendChild(desc);

    // ── 🎲 Random Theme Card ──
    const randomCard = document.createElement('div');
    randomCard.className = `theme-card ${isRandom ? 'active' : ''}`;
    randomCard.style.cssText = 'margin-bottom: 24px; width: 100%; max-width: 100%;';
    randomCard.innerHTML = `
        <div class="theme-swatches" style="background: linear-gradient(135deg, #6366f1, #ec4899, #f59e0b, #10b981); min-height: 48px; border-radius: 8px 8px 0 0; display: flex; align-items: center; justify-content: center;">
            <span class="material-symbols-outlined" style="font-size: 28px; color: white; text-shadow: 0 2px 8px rgba(0,0,0,0.4);">casino</span>
        </div>
        <div class="theme-info">
            <div class="theme-name">🎲 Random</div>
            <div class="theme-desc">Surprise me — pick a different theme every time the app loads</div>
        </div>
        ${isRandom ? '<div class="theme-active-badge"><span class="material-symbols-outlined" style="font-size: 14px;">check_circle</span> Active</div>' : ''}
    `;
    randomCard.addEventListener('click', () => {
        if (window.ThemeEngine) {
            window.ThemeEngine.applyTheme('random');
            renderTab();
        }
    });
    section.appendChild(randomCard);

    // Group themes by category
    const colorThemes = Object.entries(themes).filter(([, t]) => t.category === 'color');
    const imageThemes = Object.entries(themes).filter(([, t]) => t.category === 'image');

    // ── Color Themes ──
    const colorLabel = document.createElement('div');
    colorLabel.style.cssText = 'font-size: 10px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.15em; color: var(--text-muted); margin-bottom: 16px; margin-top: 8px;';
    colorLabel.textContent = '🎨 Color Themes';
    section.appendChild(colorLabel);

    const colorGrid = document.createElement('div');
    colorGrid.className = 'theme-grid';
    colorThemes.forEach(([id, theme]) => {
        colorGrid.appendChild(createThemeCard(id, theme, activeThemeId));
    });
    section.appendChild(colorGrid);

    // ── Image Themes ──
    const imageLabel = document.createElement('div');
    imageLabel.style.cssText = 'font-size: 10px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.15em; color: var(--text-muted); margin-bottom: 16px; margin-top: 32px;';
    imageLabel.textContent = '🖼️ Image Themes';
    section.appendChild(imageLabel);

    const imageGrid = document.createElement('div');
    imageGrid.className = 'theme-grid';
    imageThemes.forEach(([id, theme]) => {
        imageGrid.appendChild(createThemeCard(id, theme, activeThemeId));
    });
    section.appendChild(imageGrid);

    container.appendChild(section);
}

function createThemeCard(id, theme, activeId) {
    const isActive = id === activeId;
    const card = document.createElement('div');
    card.className = `theme-card ${isActive ? 'active' : ''}`;
    card.dataset.themeId = id;

    // Preview: either image thumbnail or color swatches
    let previewHTML = '';
    if (theme.backgroundImage) {
        previewHTML = `
            <div class="theme-preview-image" style="background-image: url('${theme.backgroundImage}');"></div>
        `;
    } else {
        const swatches = theme.preview.map(c => `<div class="theme-swatch" style="background: ${c};"></div>`).join('');
        previewHTML = `<div class="theme-swatches">${swatches}</div>`;
    }

    card.innerHTML = `
        ${previewHTML}
        <div class="theme-info">
            <div class="theme-name">${theme.name}</div>
            <div class="theme-desc">${theme.description}</div>
        </div>
        ${isActive ? '<div class="theme-active-badge"><span class="material-symbols-outlined" style="font-size: 14px;">check_circle</span> Active</div>' : ''}
    `;

    card.addEventListener('click', () => {
        if (window.ThemeEngine) {
            window.ThemeEngine.applyTheme(id);
            // Re-render to update active state
            renderTab();
        }
    });

    return card;
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

function renderSafetyTab(container) {
    const section = document.createElement('div');
    section.className = 'settings-section';

    section.appendChild(createSectionHeader('Position Protection', 'layers'));
    section.appendChild(createCard('Multi-Position', 'Trade multiple symbols simultaneously', 'MULTI_POSITION_ENABLED', 'toggle'));
    section.appendChild(createCard('Max Concurrent Positions', 'Maximum open positions', 'MAX_CONCURRENT_POSITIONS', 'input', { number: true, default: '1', min: 1, max: 10 }));
    section.appendChild(createCard('Smart Positions', 'Fund new risk with open profits', 'SMART_POSITIONS_ENABLED', 'toggle'));

    section.appendChild(createDivider());
    section.appendChild(createSectionHeader('Account Safety & Shields', 'shield'));

    section.appendChild(createCard('Stability Mode', 'Ultra-safe risk management & quality filters (1% Cap)', 'SAFETY_STABILITY_MODE_ENABLED', 'toggle', {
        tooltip: "<strong>Survival First.</strong> This is your emergency brake. It forces 1% max risk and a 75+ quality score floor. Perfect for preventing account 'bleeding' during choppy or unpredictable market regimes."
    }));
    section.appendChild(createCard('ATR Armor', 'Profit Protection via Break-even & Trailing stops', 'SAFETY_ATR_SHIELD_ENABLED', 'toggle', { default: 'true' }));
    section.appendChild(createCard('Stop ATR Multiplier', 'Standard stop distance as a multiple of ATR', 'STOP_ATR_MULTIPLIER', 'input', {
        number: true,
        placeholder: '1.5',
        default: '1.5',
        step: 0.1,
        min: 0.5,
        max: 5.0
    }));
    section.appendChild(createCard('The "Lock-In"', 'Lock Risk-Free at this profit level - e.g. 0.003 = 0.3%', 'BREAKEVEN_TRAIL_PCT', 'input', {
        number: true,
        placeholder: '0.003',
        default: '0.003',
        step: 0.001
    }));
    section.appendChild(createCard('Drawdown Breaker', 'Account Circuit Breaker - 5% Daily Cap', 'SAFETY_DRAWDOWN_BREAKER_ENABLED', 'toggle', { default: 'true' }));
    section.appendChild(createCard('Session Lockout', 'Stops new entries after cutoff time', 'SAFETY_SESSION_LOCKOUT_ENABLED', 'toggle', { default: 'true' }));
    section.appendChild(createCard('Lockout Time (EST)', 'No new entries after this time', 'SAFETY_SESSION_LOCKOUT_HOUR', 'time', { default: '16' }));
    section.appendChild(createCard('Greed Guard', 'Daily Profit Target Lock - Quit while ahead', 'SAFETY_GREED_GUARD_ENABLED', 'toggle', { default: 'true' }));

    // Greed Guard Target Input (Conditional visibility logic handled via CSS/JS later, or just always show for now)
    section.appendChild(createCard('Greed Guard Target USD', 'Daily profit amount to trigger lockout', 'SAFETY_GREED_GUARD_TARGET', 'input', {
        number: true,
        placeholder: '100.00',
        default: '100.00'
    }));

    section.appendChild(createCard('Churn Burner', 'Rate Limit (Max trades/hour)', 'SAFETY_CHURN_BURNER_ENABLED', 'toggle', { default: 'true' }));
    section.appendChild(createCard('Churn Burner Max', 'Maximum trades allowed per hour', 'SAFETY_CHURN_BURNER_MAX', 'input', {
        number: true,
        placeholder: '5',
        default: '5'
    }));

    section.appendChild(createCard('Volatility Veto', 'Block entries if ATR is too Low/High', 'SAFETY_VOLATILITY_VETO_ENABLED', 'toggle'));
    section.appendChild(createCard('Veto Min ATR %', 'Block if volatility falls below this %', 'SAFETY_VOLATILITY_MIN_PCT', 'input', {
        number: true,
        placeholder: '0.05',
        default: '0.05',
        step: 0.01
    }));
    section.appendChild(createCard('Veto Max ATR %', 'Block if volatility exceeds this %', 'SAFETY_VOLATILITY_MAX_PCT', 'input', {
        number: true,
        placeholder: '5.0',
        default: '5.0',
        step: 0.1
    }));
    section.appendChild(createCard('Streak Breaker', 'Pause Symbol 4h after 3 Consecutive Losses', 'SAFETY_STREAK_BREAKER_ENABLED', 'toggle', { default: 'true' }));
    section.appendChild(createCard('Opening Range Sentry', 'Avoid first 15 mins (9:30-9:45 ET)', 'SAFETY_OPENING_SENTRY_ENABLED', 'toggle', { default: 'true' }));
    section.appendChild(createCard('AI Sentiment Shield', 'Smart Veto. AI blocks "Dangerous" setups.', 'SAFETY_SENTIMENT_SHIELD_ENABLED', 'toggle'));

    section.appendChild(createDivider());
    section.appendChild(createSectionHeader('Advanced Exit Shields', 'cancel_schedule'));

    section.appendChild(createCard('Stale Sniper', 'Terminate trades after N bars of no progress', 'SAFETY_STALE_SNIPER_ENABLED', 'toggle'));
    section.appendChild(createCard('Sniper Bars', 'Maximum bars to hold a trade', 'SAFETY_STALE_SNIPER_BARS', 'input', {
        number: true,
        placeholder: '20',
        default: '20'
    }));
    section.appendChild(createCard('Flash-Trap Shield', 'Exit instantly on extreme ATR spikes', 'SAFETY_FLASH_TRAP_ENABLED', 'toggle'));
    section.appendChild(createCard('Regime-Flip Veto', 'Exit if HTF trend turns against position', 'SAFETY_REGIME_FLIP_ENABLED', 'toggle'));
    section.appendChild(createCard('Counter-Trend Block', 'Block entries against HTF trend direction', 'BLOCK_COUNTER_TREND_ENTRIES', 'toggle', { default: 'true' }));

    section.appendChild(createDivider());
    section.appendChild(createSectionHeader('☢️ NUCLEAR OVERRIDES', 'emergency_home'));

    const nuclearWarning = document.createElement('div');
    nuclearWarning.className = 'warning-box';
    nuclearWarning.style.borderColor = '#ef4444'; // Bright Red
    nuclearWarning.style.background = 'rgba(239, 68, 68, 0.05)';
    nuclearWarning.innerHTML = `
        <div class="warning-box-content" style="color: #ef4444;">
            <strong style="color: #ef4444;">⚠️ FATAL RISK WARNING:</strong><br>
            Bypassing safety walls allows the bot to risk up to 100% of your account on a single trade. 
            This mode is intended for <strong>BACKTESTING ONLY</strong> or for high-stakes professional scaling. 
            <strong>NUCLEAR MODE CAN AND WILL LIQUIDATE YOUR ACCOUNT IF IMPROPERLY CONFIGURED.</strong>
        </div>
    `;
    section.appendChild(nuclearWarning);

    section.appendChild(createCard('Nuclear Mode Active', 'Bypass all hard-coded safety ceilings', 'NUCLEAR_OVERRIDES_ENABLED', 'toggle', { default: 'false' }));
    section.appendChild(createCard('Risk Cap Override %', 'New hard risk wall - e.g. 0.35 for 35%', 'MAX_RISK_CAP_OVERRIDE', 'input', {
        number: true,
        default: '0.05',
        locked: envData['NUCLEAR_OVERRIDES_ENABLED'] !== 'true',
        lockMessage: 'Requires Nuclear Mode Activation.'
    }));
    section.appendChild(createCard('Compounding Cap Override USD', 'New capital growth wall - e.g. 50000', 'COMPOUNDING_CAP_OVERRIDE', 'input', {
        number: true,
        default: '10000',
        locked: envData['NUCLEAR_OVERRIDES_ENABLED'] !== 'true',
        lockMessage: 'Requires Nuclear Mode Activation.'
    }));
    section.appendChild(createCard('Pyramid Cap Override USD', 'New risk ceiling for pyramids', 'PYRAMID_CAP_OVERRIDE', 'input', {
        number: true,
        default: '750',
        locked: envData['NUCLEAR_OVERRIDES_ENABLED'] !== 'true',
        lockMessage: 'Requires Nuclear Mode Activation.'
    }));

    section.appendChild(createDivider());
    section.appendChild(createSectionHeader('Safety Metrics (Live Feed)', 'query_stats'));

    const statsBox = document.createElement('div');
    statsBox.className = 'warning-box';
    statsBox.style.borderColor = 'rgba(20, 184, 166, 0.2)';
    statsBox.innerHTML = `
        <div class="flex flex-col gap-2 w-full text-xs">
            <div class="flex justify-between">
                <span class="text-slate-400">Current Safety Floor:</span>
                <span class="text-teal-400 font-bold">$100.00</span>
            </div>
            <div class="flex justify-between">
                <span class="text-slate-400">Daily HWM:</span>
                <span class="text-white font-bold">$100.00</span>
            </div>
            <div class="flex justify-between">
                <span class="text-slate-400">Max Allowable Drawdown:</span>
                <span class="text-rose-400/70 font-bold">$5.00</span>
            </div>
        </div>
    `;
    section.appendChild(statsBox);

    container.appendChild(section);
}

function renderPerformanceTab(container) {
    const section = document.createElement('div');
    section.className = 'settings-section';

    section.appendChild(createSectionHeader('Performance & Profits', 'trending_up'));
    section.appendChild(createWarningBox('<strong>Stackable Architecture:</strong> Select ONE Base Risk Foundation, then stack compatible Multipliers to boost performance.'));

    // 1. RISK FOUNDATION (Radio - Select One)
    const foundationGroup = document.createElement('div');
    foundationGroup.innerHTML = `<div class="text-sm text-slate-400 mb-2 font-bold uppercase tracking-wider">Step 1: Risk Foundation (Base Sizing)</div>`;
    section.appendChild(foundationGroup);

    // Foundations
    section.appendChild(createPerformanceToggle('Standard Mode', 'Fixed risk per trade (Default)', 'none', 'foundation',
        "<strong>The Baseline.</strong> Risks a fixed percentage (e.g., 1.5%) of your account balance on every trade. This is the foundation of professional trading: consistent, predictable, and devoid of emotional 'revenge' sizing. Best for scaling new accounts safely."));

    section.appendChild(createPerformanceToggle('Stability Mode', 'Survival first: 1% risk cap & 75+ score setup', 'stability', 'foundation',
        "<strong>Account Guardian.</strong> The ultimate defense against drawdown. If your account is 'bleeding' or you are experiencing a streak of losses, switch to this. It enforces a strict 1.0% risk ceiling and vetoes every trade setup that doesn't reach a Tier-1 Quality Score of 75+. It prioritizes total capital preservation above all else."));

    section.appendChild(createPerformanceToggle('Kelly Criterion', 'Mathematical optimal sizing via win-rate analytics', 'kelly', 'foundation',
        'The Gambler\'s Math. Uses your historical Win Rate and Reward Ratio to calculate the mathematically optimal bet size to maximize long-term wealth growth.'));

    section.appendChild(createPerformanceToggle('Compound Flywheel', 'Accelerate risk per trade at profit milestones', 'flywheel', 'foundation',
        'The Snowball Effect. Starts with standard risk, but as your daily profits grow, it slightly increases risk to accelerate the "good days".'));

    section.appendChild(createPerformanceToggle('Equity Smoothing', 'Anti-tilt: boost on highs, slash on lows', 'smooth', 'foundation',
        'The Tilt-Killer. If you are losing money today, it drastically cuts risk (Defensive). If you are winning, it slightly boosts it (Offensive).'));

    section.appendChild(createDivider());

    // 2. MULTIPLIERS (Checkbox - Stackable)
    const multiplierGroup = document.createElement('div');
    multiplierGroup.innerHTML = `<div class="text-sm text-slate-400 mb-2 font-bold uppercase tracking-wider">Step 2: Active Multipliers (Stackable Boosts)</div>`;
    section.appendChild(multiplierGroup);

    section.appendChild(createPerformanceToggle('The Sniper (A+)', 'Risk 1.5x on high-confidence (Score > 90) signals', 'sniper', 'multiplier',
        'Precision strike. If the AI Score is >90 (A+ Setup), we boost risk by 1.5x because the probability of winning is higher.'));

    section.appendChild(createPerformanceToggle('Regime Sync', 'Adaptive risk based on HTF trend strength (0.5x - 1.5x)', 'regime_sync', 'multiplier',
        'Go with the flow. If the Higher Timeframe is trending strongly in your direction, we boost risk. If fighting the trend, we dampen it.'));

    section.appendChild(createPerformanceToggle('House Money', 'Risk 1.5x if trade is financed by locked profit', 'house_money', 'multiplier',
        'Playing with the casino\'s money. If you have another trade already in profit (2R+), we boost risk on this new trade by 1.5x.'));

    section.appendChild(createPerformanceToggle('The Whale Watcher', '1.3x Boost on Volume Profile support', 'whale', 'multiplier',
        'Follow the big money. If Volume is 2x the average, it means institutions are interested. We boost risk by 1.3x to ride their wave.'));

    section.appendChild(createPerformanceToggle('The Contrarian', '1.5x Boost on RSI Reversals (Fade)', 'contrarian', 'multiplier',
        'Fade the retail herd. When everyone else is FOMO-buying (RSI Overbought) but the price stalls, we short big (1.5x Risk).'));

    section.appendChild(createPerformanceToggle('The News Surfer', '2.0x Boost on Post-News Compression', 'surfer', 'multiplier',
        'Catch the breakout. After a news event, markets get quiet (Volatility Squeeze). We bet double (2.0x) on the explosive move that follows.'));

    section.appendChild(createPerformanceToggle('Correlation Hydra', 'Basket coordination scaling', 'hydra', 'multiplier',
        'Calculates risk based on your exposure to correlated assets (e.g., EURUSD and GBPUSD). Prevents accidental double-risk.'));

    section.appendChild(createPerformanceToggle('Volatility Coil', 'Double risk on quiet-market breakouts', 'coil', 'multiplier',
        'The Spring-Load. If the market has been flat (coiling) for a long time, the breakout is usually massive. We double risk to catch it.'));

    section.appendChild(createPerformanceToggle('Power Hour Alpha', '1.2x Boost during key session overlaps', 'alpha', 'multiplier',
        'Session overlap trading. Markets are most active when London and NY sessions overlap (09:00-11:00 EST). We boost risk by 1.2x.'));

    section.appendChild(createPerformanceToggle('Gamma Squeeze', '1.2x Boost on vertical velocity', 'gamma', 'multiplier',
        'Vertical Velocity. If price moves exceptionally fast in a short time, we boost risk to capture the momentum surge.'));

    section.appendChild(createPerformanceToggle('AI Hype Fusion', '1.5x Boost if AI Sentiment aligns', 'sentiment', 'multiplier',
        'Sentiment Confirmation. If our LLM (Claude/GPT) analyzes the news and says "BULLISH", we boost our Long entries.'));

    section.appendChild(createPerformanceToggle('Harmonic Ghost', '1.5x Boost on psychological levels', 'ghost', 'multiplier',
        'Smart Money Levels. Boosts risk if price reacts at a key psychological level (e.g., 50000) or Institutional Order Block.'));

    section.appendChild(createPerformanceToggle('Phoenix Protocol', 'Recovery protocol after streaks', 'phoenix', 'multiplier',
        'Recovery Mode. If you lost 3 trades in a row and the "Streak Breaker" paused you, this mode slightly boosts the first trade back.'));

    // The Runner is unique (Exit Logic)
    section.appendChild(createDivider());
    section.appendChild(createPerformanceToggle('The Runner', 'Scale 50% profit; trail moonshots (Exit Logic)', 'runner', 'multiplier',
        'Let it ride. Instead of closing all profit at the target, we leave 50% open with a trailing stop to catch "Moonshots".'));

    section.appendChild(createDivider());
    section.appendChild(createSectionHeader('Wealth Weapons (Advanced Exits)', 'rocket_launch'));

    section.appendChild(createCard('Gamma Squeeze Trail', 'Exponentially tighter trail on vertical moves', 'WEALTH_EXIT_GAMMA_ENABLED', 'toggle'));
    section.appendChild(createCard('Moonshot Elevator', 'Double target if 1R is hit in <3 bars', 'WEALTH_EXIT_MOONSHOT_ENABLED', 'toggle'));
    section.appendChild(createCard('Blow-off Seller', 'Sell peak on volatility exhaustion', 'WEALTH_EXIT_BLOWOFF_ENABLED', 'toggle'));

    section.appendChild(createDivider());

    // 3. P&L REWARDS & RETENTION (NEW)
    const pnlGroup = document.createElement('div');
    pnlGroup.innerHTML = `<div class="text-sm text-slate-400 mb-2 font-bold uppercase tracking-wider">Step 3: P&L Rewards & Retention (Targets & Limits)</div>`;
    section.appendChild(pnlGroup);

    section.appendChild(createCard('Daily Profit Target %', 'Stop for the day once this % profit is reached (e.g. 0.02 = 2%)', 'TARGET_PROFIT_DAILY_PCT', 'input', { number: true, default: '0.0', step: 0.001 }));
    // Daily Loss Limit slider is in Strategy Workshop → Global Risk tab

    section.appendChild(createCard('Weekly Profit Target % (Not Yet Implemented)', 'Lock in weekly gains once reached (e.g. 0.05 = 5%)', 'TARGET_PROFIT_WEEKLY_PCT', 'input', { number: true, default: '0.0', step: 0.001, disabled: true }));
    section.appendChild(createCard('Weekly Loss Limit % (Not Yet Implemented)', 'Protect capital: stop for the week if hit (e.g. 0.15 = 15%)', 'LIMIT_LOSS_WEEKLY_PCT', 'input', { number: true, default: '0.15', step: 0.001, disabled: true }));

    section.appendChild(createCard('Monthly Profit Target % (Not Yet Implemented)', 'Monthly wealth goal: stop if reached (e.g. 0.10 = 10%)', 'TARGET_PROFIT_MONTHLY_PCT', 'input', { number: true, default: '0.0', step: 0.001, disabled: true }));
    section.appendChild(createCard('Monthly Loss Limit % (Not Yet Implemented)', 'Emergency floor: stop for the month if reached (e.g. 0.25 = 25%)', 'LIMIT_LOSS_MONTHLY_PCT', 'input', { number: true, default: '0.25', step: 0.001, disabled: true }));

    container.appendChild(section);
}

/**
 * Assistant to renderPerformanceTab for complex toggle behavior.
 * type: 'foundation' (Radio Behavior) or 'multiplier' (Checkbox Behavior)
 * tooltip: Detailed layman explanation.
 */
function createPerformanceToggle(title, desc, modeValue, type = 'foundation', tooltip = '') {
    const rawMode = envData['PERFORMANCE_MODE'] || 'none';
    const activeModes = rawMode.split(',').map(s => s.trim().toLowerCase());

    let isActive = false;
    if (type === 'foundation') {
        // If mode is "none" (Standard), and list is empty or has 'none', it's active
        if (modeValue === 'none' && (activeModes.includes('none') || activeModes.length === 0)) isActive = true;
        else isActive = activeModes.includes(modeValue);
    } else {
        isActive = activeModes.includes(modeValue);
    }

    const card = createCard(title, desc, `PERF_${modeValue.toUpperCase()}`, 'toggle', {
        default: isActive ? 'true' : 'false',
        tooltip: tooltip // Pass the tooltip here
    });

    const toggle = card.querySelector('.toggle');
    const newToggle = toggle.cloneNode(true);
    toggle.parentNode.replaceChild(newToggle, toggle); // Remove old listeners

    newToggle.addEventListener('click', (e) => {
        e.stopPropagation();

        let currentRaw = envData['PERFORMANCE_MODE'] || 'none';
        let currentList = currentRaw.split(',').map(s => s.trim().toLowerCase()).filter(s => s);

        // [STABILITY] Check for conflicts before proceeding
        if (checkConflicts('PERFORMANCE_MODE', modeValue)) return;

        // Remove 'none' from list if we are adding something else
        if (currentList.includes('none')) currentList = currentList.filter(s => s !== 'none');

        if (type === 'foundation') {
            // Radio Logic: Remove other foundations, add this one
            const foundations = ['kelly', 'flywheel', 'smooth', 'none'];
            currentList = currentList.filter(m => !foundations.includes(m)); // Clear existing foundation
            if (modeValue !== 'none') currentList.push(modeValue);
        }
        else {
            // Checkbox Logic: Toggle
            if (currentList.includes(modeValue)) {
                currentList = currentList.filter(m => m !== modeValue);
            } else {
                currentList.push(modeValue);
            }
        }

        const newValue = currentList.length > 0 ? currentList.join(',') : 'none';

        // [STABILITY] Sync performance mode 'stability' with the boolean flag
        if (modeValue === 'stability') {
            updateValue('SAFETY_STABILITY_MODE_ENABLED', 'true');
        } else if (type === 'foundation') {
            updateValue('SAFETY_STABILITY_MODE_ENABLED', 'false');
        }

        updateValue('PERFORMANCE_MODE', newValue);
        renderTab(); // Re-render to show updates
    });

    return card;
}


function updateValue(key, value) {
    const oldValue = getValue(key);
    if (oldValue === value) return;

    // 1. Update Secrets
    if (SECRETS_MAP[key]) {
        secretsData[SECRETS_MAP[key]] = value;
    }
    // 2. Update Global Config
    else if (CONFIG_MAP[key]) {
        const path = CONFIG_MAP[key];
        let current = configData;
        for (let i = 0; i < path.length - 1; i++) {
            if (!current[path[i]]) current[path[i]] = {};
            current = current[path[i]];
        }

        let val = value;
        if (value === 'true') val = true;
        else if (value === 'false') val = false;
        else if (!isNaN(value) && value.trim() !== "" && key !== 'OANDA_ACCOUNT_ID' && key !== 'IBKR_PORT' && key !== 'IBKR_CLIENT_ID') {
            val = Number(value);
        }

        current[path[path.length - 1]] = val;

        // Sync PnL timeframe back to renderer.js if changed
        if (key === 'GUI_PNL_TIMEFRAME' && typeof window.syncPnLTimeframe === 'function') {
            window.syncPnLTimeframe(value);
        }
    }
    // 3. Update Active Profile
    else {
        const active = configData.active_profile;
        if (active && configData.profiles && configData.profiles[active]) {
            let val = value;
            if (value === 'true') val = true;
            else if (value === 'false') val = false;
            else if (!isNaN(value) && value.trim() !== "") val = Number(value);
            configData.profiles[active][key.toLowerCase()] = val;
        }
    }

    localChanges[key] = true;
    envData[key] = String(value); // Keep flat map in sync

    // [STABILITY] Intercept toggle from Safety tab to sync with Performance foundation
    if (key === 'SAFETY_STABILITY_MODE_ENABLED') {
        let currentPerf = envData['PERFORMANCE_MODE'] || 'none';
        let perfList = currentPerf.split(',').map(s => s.trim().toLowerCase());
        const foundations = ['kelly', 'flywheel', 'smooth', 'stability', 'none'];

        if (value === 'true') {
            // Switch foundation to stability
            perfList = perfList.filter(m => !foundations.includes(m));
            perfList.push('stability');
        } else {
            // Revert foundation if it was stability
            if (perfList.includes('stability')) {
                perfList = perfList.filter(m => m !== 'stability');
                if (!perfList.some(m => foundations.includes(m))) perfList.push('none');
            }
        }
        const newValue = perfList.join(',') || 'none';
        envData['PERFORMANCE_MODE'] = newValue;
        localChanges['PERFORMANCE_MODE'] = true;

        const active = configData.active_profile;
        if (active && configData.profiles && configData.profiles[active]) {
            configData.profiles[active]['performance_mode'] = newValue;
        }
    }

    updateChangeCounter();
    autoSave();
}

/**
 * Debounced save to both .env and YAML
 */
function autoSave() {
    clearTimeout(autoSaveTimeout);
    autoSaveTimeout = setTimeout(async () => {
        console.log("[SETTINGS] Auto-saving changes...");
        await saveAll();
    }, 1000);
}

function updateChangeCounter() {
    changeCount = Object.keys(localChanges).length;
    const el = document.getElementById('change-counter');

    if (changeCount > 0) {
        el.textContent = `Saving ${changeCount} change${changeCount > 1 ? 's' : ''}...`;
        el.className = 'text-xs text-amber-400 font-bold';
    } else {
        el.textContent = 'All settings synced to disk';
        el.className = 'text-xs text-emerald-400/70 font-bold';
    }
}

async function saveAll() {
    if (Object.keys(localChanges).length === 0) {
        showNotice("No changes to save");
        return;
    }

    const indicator = document.getElementById('save-indicator');
    if (indicator) indicator.style.opacity = '1';

    // If Config Editor (JSON) was edited, parse it back into configData
    if (localChanges['_config_']) {
        try {
            configData = JSON.parse(profilesContent);
            console.log("[SETTINGS] Parsed updated JSON from editor");
        } catch (e) {
            showNotice("Invalid JSON Syntax", "red");
            if (indicator) indicator.style.opacity = '0';
            return;
        }
    }

    if (window.api) {
        try {
            // Save unified config
            const res1 = await window.api.saveConfig(configData);
            // Save secrets
            const res2 = await window.api.saveSecrets(secretsData);

            if (res1.success && res2.success) {
                console.log("[SETTINGS] Save successful.");
                showNotice("Settings Saved", "teal");
                localChanges = {};
                updateChangeCounter();
            } else {
                showNotice("Save Failed", "red");
            }
        } catch (e) {
            console.error("[SETTINGS] Save error:", e);
            showNotice("Save Error", "red");
        }
        setTimeout(() => { if (indicator) indicator.style.opacity = '0'; }, 2000);
    }
}

// ═══════════════════════════════════════════════════════════
// TOOLTIP
// ═══════════════════════════════════════════════════════════

function showTooltip(e, title, content) {
    const popup = document.getElementById('tooltip-popup');
    document.getElementById('tooltip-title').innerHTML = title;
    document.getElementById('tooltip-content').innerHTML = content;

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
    // Strategy selector using a responsive grid layout
    const nav = document.createElement('div');
    nav.className = 'strategy-selector-grid';
    nav.style.cssText = `
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
        gap: 10px;
        margin-bottom: 32px;
        padding: 16px;
        background: rgba(0, 0, 0, 0.3);
        border-radius: 16px;
        border: 1px solid rgba(255, 255, 255, 0.05);
    `;

    const strategies = [
        { id: 'icc', label: 'ICC Core', icon: 'auto_mode', color: '#14b8a6' },
        { id: 'rubberband_reaper', label: 'Rubberband Reaper', icon: 'elastic', color: '#f59e0b' },
        { id: 'robocop', label: 'RoboCop', icon: 'smart_toy', color: '#ef4444' },
        { id: 'evolution', label: 'Robot Evolution', icon: 'psychology', color: '#8b5cf6' },
        { id: 'quantum', label: 'Quantum', icon: 'blur_on', color: '#3b82f6' },
        { id: 'mean_reversion', label: 'Mean Reversion', icon: 'swap_vert', color: '#22c55e' },
        { id: 'hyper_scalper', label: 'HyperScalper', icon: 'speed', color: '#ec4899' },
        { id: 'london_breakout', label: 'London Breakout', icon: 'location_city', color: '#f97316' },
        { id: 'volatility_breakout', label: 'Volatility Breakout', icon: 'show_chart', color: '#06b6d4' },
        { id: 'aggregator', label: 'Aggregator', icon: 'hub', color: '#a855f7' },
        { id: 'supply_demand', label: 'Supply & Demand', icon: 'layers', color: '#eab308' },
        { id: 'orb_breakout', label: 'ORB (Break & Retest)', icon: 'rule', color: '#6366f1' },
        { id: 'meta_sci', label: 'Meta-SCI Alpha', icon: 'hub', color: '#14b8a6' },
        { id: 'trend_rider', label: 'Trend Rider', icon: 'trending_up', color: '#10b981' },
        { id: 'session_momentum', label: 'Session Momentum', icon: 'schedule_send', color: '#f43f5e' },
        { id: 'bearish_engulfing', label: 'Engulfing Reversal', icon: 'candlestick_chart', color: '#d946ef' },
        // 🪙 Crypto-Specific Strategies
        { id: 'crypto_rsi_macd', label: 'RSI + MACD', icon: 'currency_bitcoin', color: '#f59e0b' },
        { id: 'crypto_vwap_reversion', label: 'VWAP Reversion', icon: 'swap_horiz', color: '#84cc16' },
        { id: 'crypto_double_macd', label: 'Double MACD', icon: 'speed', color: '#fb923c' },
        { id: 'crypto_grid', label: 'Virtual Grid', icon: 'grid_on', color: '#a78bfa' }
    ];

    strategies.forEach(s => {
        const btn = document.createElement('button');
        const isActive = toolboxTab === s.id;
        btn.style.cssText = `
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 8px;
            padding: 16px 12px;
            border-radius: 12px;
            border: 1px solid ${isActive ? s.color + '60' : 'rgba(255,255,255,0.08)'};
            background: ${isActive ? s.color + '20' : 'rgba(255,255,255,0.03)'};
            color: ${isActive ? s.color : '#94a3b8'};
            cursor: pointer;
            transition: all 0.2s ease;
            font-size: 11px;
            font-weight: 600;
            text-align: center;
            min-height: 80px;
        `;
        btn.innerHTML = `
            <span class="material-symbols-outlined" style="font-size: 24px; opacity: ${isActive ? 1 : 0.6};">${s.icon}</span>
            <span style="line-height: 1.3;">${s.label}</span>
        `;
        btn.onmouseenter = () => {
            if (!isActive) {
                btn.style.background = 'rgba(255,255,255,0.08)';
                btn.style.borderColor = 'rgba(255,255,255,0.15)';
                btn.style.color = '#e2e8f0';
            }
        };
        btn.onmouseleave = () => {
            if (!isActive) {
                btn.style.background = 'rgba(255,255,255,0.03)';
                btn.style.borderColor = 'rgba(255,255,255,0.08)';
                btn.style.color = '#94a3b8';
            }
        };
        btn.onclick = () => {
            toolboxTab = s.id;
            renderTab();
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

    } else if (toolboxTab === 'meta_sci') {
        const stratInfo = STRATEGIES.meta_sci;
        section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'hub'));

        section.appendChild(createWarningBox(`
            <strong>Ensemble Master:</strong><br>
            Meta-SCI does not use its own logic. It orchestrates all other strategies in parallel. 
            The configuration below determines how it selects the "Winning" signal when multiple strategies agree.
        `));

        section.appendChild(createCard('Meta-SCI Active', 'Orchestrate all strategies in parallel', 'META_SCI_ENABLED', 'toggle'));
        section.appendChild(createCard('Min Consensus', 'Min strategies that must agree', 'META_SCI_MIN_CONSENSUS', 'input', {
            number: true,
            default: '1',
            min: 1,
            max: 5,
            tooltip: 'Minimum number of strategies that must signal the same direction before an entry is permitted. 1 = Highest score wins immediately.'
        }));

        section.appendChild(createCard('Strategy Blacklist', 'Comma-separated IDs to ignore', 'META_SCI_EXCLUDE_LIST', 'input', {
            default: '',
            tooltip: 'Strategies to exclude from consensus.'
        }));

    } else if (toolboxTab === 'orb_breakout') {
        const stratInfo = STRATEGIES.orb_breakout;
        section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'rule'));

        section.appendChild(createWarningBox(`
            <strong>Break & Retest Strategy:</strong><br>
            Trades the NY Opening Range (09:30 - 09:45 ET). Waits for Break -> Retest -> Flag pattern.
        `));

        section.appendChild(createCard('Session Start', 'Range start time (ET)', 'ORB_START_TIME', 'input', {
            default: '09:30',
            tooltip: 'The time the Opening Range begins. Usually 09:30 AM ET (NY Open).'
        }));
        section.appendChild(createCard('Duration (Min)', 'Length of the Range', 'ORB_DURATION', 'input', {
            number: true,
            default: '15',
            tooltip: 'How long the Opening Range lasts in minutes. Standard is 15 minutes (09:30-09:45).'
        }));
        section.appendChild(createCard('Risk %', 'Risk per trade', 'ORB_RISK_PCT', 'input', {
            number: true,
            default: '1.0',
            tooltip: 'Percentage of account to risk on this strategy.'
        }));



        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('Meta-SCI Strategy Feed', 'rss_feed'));

        const feedBox = document.createElement('div');
        feedBox.className = 'warning-box';
        feedBox.style.borderColor = 'rgba(20, 184, 166, 0.2)';
        feedBox.innerHTML = `
            <div class="flex flex-col gap-2 w-full text-xs">
                <div class="flex justify-between">
                    <span style="color: var(--text-dim);">Active Workers:</span>
                    <span style="color: var(--accent); font-weight: 700;">SND, RoboCop, Evolution, London, Reaper</span>
                </div>
                <div class="flex justify-between">
                    <span style="color: var(--text-dim);">Decision Logic:</span>
                    <span style="color: var(--text-secondary);">Highest A+ Entry Score</span>
                </div>
                <div class="flex justify-between">
                    <span style="color: var(--text-dim);">Status:</span>
                    <span style="color: var(--text-secondary);">Operational</span>
                </div>
            </div>
        `;
        section.appendChild(feedBox);

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
    // 1. Log to console for paper trail
    console.log(`[GUI-NOTICE] ${message} (${color})`);

    // 2. Also send to main process for persistent logging if possible
    if (window.api?.logNotice) {
        window.api.logNotice(message, color);
    }

    // 3. Color mapping for inline styles (no Tailwind dynamic classes)
    const colors = {
        teal: { bg: 'rgba(20, 184, 166, 0.15)', border: 'rgba(20, 184, 166, 0.5)', text: '#5eead4', dot: '#14b8a6', glow: 'rgba(20, 184, 166, 0.6)' },
        red: { bg: 'rgba(239, 68, 68, 0.15)', border: 'rgba(239, 68, 68, 0.5)', text: '#fca5a5', dot: '#ef4444', glow: 'rgba(239, 68, 68, 0.6)' },
        purple: { bg: 'rgba(168, 85, 247, 0.15)', border: 'rgba(168, 85, 247, 0.5)', text: '#c4b5fd', dot: '#a855f7', glow: 'rgba(168, 85, 247, 0.6)' },
    };
    const c = colors[color] || colors.teal;

    // 4. Build toast with inline styles (no broken Tailwind animate classes)
    const toast = document.createElement('div');
    Object.assign(toast.style, {
        position: 'fixed',
        top: '5.5rem',
        left: '50%',
        transform: 'translateX(-50%) translateY(-20px)',
        zIndex: '9999',
        padding: '0.875rem 2rem',
        borderRadius: '1rem',
        background: 'rgba(2, 6, 23, 0.95)',
        backdropFilter: 'blur(24px)',
        border: `2px solid ${c.border}`,
        boxShadow: `0 8px 32px rgba(0,0,0,0.5), 0 0 40px ${c.glow}`,
        opacity: '0',
        transition: 'opacity 0.4s ease, transform 0.4s ease',
        pointerEvents: 'none',
    });

    toast.innerHTML = `
        <div style="display:flex;align-items:center;gap:0.75rem;">
            <div style="width:10px;height:10px;border-radius:50%;background:${c.dot};box-shadow:0 0 12px ${c.glow};animation:pulse 1.5s infinite;"></div>
            <span style="font-size:0.8rem;font-weight:900;text-transform:uppercase;letter-spacing:0.15em;color:${c.text};">${message}</span>
        </div>
    `;

    document.body.appendChild(toast);

    // Animate in (next frame so transition triggers)
    requestAnimationFrame(() => {
        toast.style.opacity = '1';
        toast.style.transform = 'translateX(-50%) translateY(0)';
    });

    // Auto-dismiss after 3 seconds
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(-50%) translateY(-20px)';
        setTimeout(() => toast.remove(), 400);
    }, 3000);
}

// ═══════════════════════════════════════════════════════════
// SETTINGS MODULE EXPORT
// ═══════════════════════════════════════════════════════════
window.settingsModule = {
    init: init,
    switchTab: switchTab,
    renderTab: renderTab,
    saveAll: saveAll
};

