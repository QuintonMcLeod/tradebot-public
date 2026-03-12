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
    'PAPER_SIM_ENABLED': ['paper', 'enabled'],
    'PAPER_REPLAY_MODE': ['paper', 'replay_mode'],
    'PAPER_SYNTHETIC_MODE': ['paper', 'synthetic_mode'],
    'SABBATH_REPLAY_MODE': ['safety', 'sabbath_replay_mode'],
    'PAPER_FEE_BPS': ['paper', 'fee_bps'],
    'PAPER_SLIPPAGE_BPS': ['paper', 'slippage_bps'],
    'PAPER_SPREAD_BPS': ['paper', 'spread_bps'],
    'LOG_LEVEL': ['logging', 'level'],
    'TRADEBOT_LOG': ['logging', 'file'],
    'WS_SERVER_PORT': ['runtime', 'ws_server_port'],
    'GUI_WS_URL': ['runtime', 'gui_ws_url'],
    'GUI_PNL_TIMEFRAME': ['runtime', 'pnl_timeframe'],
    'GLOBAL_RISK_PCT': ['runtime', 'global_default_risk_pct'],
    'FRIDAY_FADE_ENABLED': ['runtime', 'friday_fade_enabled'],
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
    'SAFETY_SESSION_LOCKOUT_ENABLED': ['safety', 'safety_session_lockout_enabled'],
    'SAFETY_SESSION_LOCKOUT_HOUR': ['safety', 'safety_session_lockout_hour'],
    // Performance
    'PERFORMANCE_MODE': ['performance', 'performance_mode'],
    'TRAILING_STOP_ENABLED': ['performance', 'trailing_stop_enabled'],
    'PYRAMID_CAP_OVERRIDE': ['performance', 'pyramid_cap_override'],
    'COMPOUNDING_CAP_OVERRIDE': ['performance', 'compounding_cap_override'],
    // Asset Strategies (global SSOT — read by loader.py)
    'STRATEGY_CRYPTO': ['global', 'strategy_crypto'],
    'STRATEGY_FOREX': ['global', 'strategy_forex'],
    'STRATEGY_STOCKS': ['global', 'strategy_stocks'],
    'STRATEGY_ETF': ['global', 'strategy_etf'],
    'STRATEGY_METALS': ['global', 'strategy_metals'],
    'STRATEGY_FUTURES': ['global', 'strategy_futures'],
    // Pyramiding (under global in config.json)
    'MAX_PYRAMID_ENTRIES': ['global', 'max_pyramid_entries'],
    'PYRAMID_PROFIT_BUFFER_PCT': ['global', 'pyramid_profit_buffer_pct'],
    'PYRAMID_RISK_LOAD': ['global', 'pyramid_risk_load'],
    'PYRAMID_RISK_SCALE': ['global', 'pyramid_risk_scale'],
    'BREAKEVEN_TRAIL_AFTER_PYRAMIDS': ['global', 'breakeven_trail_after_pyramids'],
    // Exit Logic & Position Management (under global in config.json)
    'MIN_HOLD_HOURS': ['global', 'min_hold_hours'],
    'MAX_HOLD_HOURS': ['global', 'max_hold_hours'],
    'HTF_NEUTRAL_EXIT_BARS': ['global', 'htf_neutral_exit_bars'],
    'TRAILING_STOP_MIN_PROFIT_PCT': ['global', 'trailing_stop_min_profit_pct'],
    'AUTO_FLATTEN_ON_CLOSE': ['global', 'flatten_on_exit'],
    'MULTI_POSITION_ENABLED': ['global', 'multi_position_enabled'],
    'MAX_CONCURRENT_POSITIONS': ['global', 'max_concurrent_positions'],
    'SMART_POSITIONS_ENABLED': ['global', 'smart_positions_enabled'],
    'TARGET_PROFIT_DAILY_PCT': ['global', 'target_profit_daily_pct'],
    // Stop-and-Reverse
    'STOP_AND_REVERSE_ENABLED': ['global', 'stop_and_reverse_enabled'],
    'COUNTER_REVERSAL_ENABLED': ['global', 'counter_reversal_enabled'],
    'SAR_KEEP_OPEN': ['global', 'sar_keep_open'],
    'REVERSAL_TP_R': ['global', 'reversal_tp_r'],
    'REVERSAL_COST_AWARE_TP': ['global', 'reversal_cost_aware_tp'],
    'REVERSAL_RISK_PER_TRADE': ['global', 'reversal_risk_per_trade'],
    'SCALE_OUT_FRACTION': ['runtime', 'scale_out_fraction'],
    // Trend Detection (under global in config.json)
    'TREND_ADX_ENABLED': ['global', 'trend_adx_enabled'],
    'TREND_RSI_ENABLED': ['global', 'trend_rsi_enabled'],
    'TREND_MACD_ENABLED': ['global', 'trend_macd_enabled'],
    'TREND_BOLLINGER_ENABLED': ['global', 'trend_bollinger_enabled'],
    'TREND_SUPERTREND_ENABLED': ['global', 'trend_supertrend_enabled'],
    'TREND_EMA_RIBBON_ENABLED': ['global', 'trend_ema_ribbon_enabled'],
    'TREND_ICHIMOKU_ENABLED': ['global', 'trend_ichimoku_enabled'],
    'TREND_PARABOLIC_SAR_ENABLED': ['global', 'trend_parabolic_sar_enabled'],
    'TREND_VWAP_ENABLED': ['global', 'trend_vwap_enabled'],
    'TREND_HULL_MA_ENABLED': ['global', 'trend_hull_ma_enabled'],
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
    'SAFETY_DRAWDOWN_MAX_PCT': ['safety', 'safety_drawdown_max_pct'],
    'SAFETY_GREED_GUARD_ENABLED': ['safety', 'safety_greed_guard_enabled'],
    'SAFETY_GREED_GUARD_TARGET': ['safety', 'safety_greed_guard_target'],
    'SAFETY_STREAK_BREAKER_ENABLED': ['safety', 'safety_streak_breaker_enabled'],
    'SAFETY_CHURN_BURNER_ENABLED': ['safety', 'safety_churn_burner_enabled'],
    'SAFETY_CHURN_BURNER_MAX': ['safety', 'safety_churn_burner_max'],
    'SAFETY_LEVERAGE_SENTRY_ENABLED': ['safety', 'safety_leverage_sentry_enabled'],
    'SAFETY_MAX_TOTAL_LEVERAGE': ['safety', 'safety_max_total_leverage'],
    'SAFETY_OPENING_SENTRY_ENABLED': ['safety', 'safety_opening_sentry_enabled'],
    // AI Provider (nested under configData.ai)
    'TRADE_SCI_PROVIDER': ['ai', 'provider'],
    'TRADE_SCI_MODEL_NAME': ['ai', 'model'],
    'TRADE_SCI_API_BASE_URL': ['ai', 'base_url'],
    'AI_TEMPERATURE': ['ai', 'temperature'],
    'AI_MAX_TOKENS': ['ai', 'max_tokens'],
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
    'TRADE_SCI_API_KEY': 'TRADE_SCI_API_KEY',
    'CHATGPT_KEY': 'CHATGPT_KEY',
};

// ═══════════════════════════════════════════════════════════
// TOOLTIP LIBRARY - Detailed, layman-friendly explanations
// ═══════════════════════════════════════════════════════════

const TOOLTIPS = {
    // Engine Settings
    PAPER_SIM_ENABLED: "Enable Paper Trading Simulator. Bypasses real broker execution and tracks simulated PnL.",
    PAPER_REPLAY_MODE: "Run the Paper Simulator using historical Replay data instead of the live WebSocket feed.",
    PAPER_SYNTHETIC_MODE: "Run the Paper Simulator in Synthetic Fire Mode using algorithmically generated endless massive volatility for stress testing.",
    SABBATH_REPLAY_MODE: "During Sabbath hours (Friday sunset to Saturday sunset), switch the Paper Simulator to read from Replay data so you can continue testing.",
    PAPER_FEE_BPS: "The simulated round-trip broker fee in basis points (e.g. 5.0 = 0.05%).",
    PAPER_SLIPPAGE_BPS: "The simulated slippage per leg in basis points. Applied instantly on entry.",
    PAPER_SPREAD_BPS: "The simulated bid/ask spread in basis points. Defines the distance between fill price and mid price.",

    // System Settings
    APP_PROFILE: "Trading profiles define which markets you trade (stocks, forex, crypto), how often the bot checks for opportunities, and when it's allowed to trade. Think of it like choosing between 'day trader mode' vs '24/7 crypto mode'.",
    STRATEGY_VARIANT: "The trading strategy determines HOW the bot decides to enter and exit trades. Each strategy has different rules - some are aggressive scalpers, others wait for perfect setups. Choose based on your risk tolerance and market conditions.",
    BOT_MODE: "Controls how the bot runs: 'Continuous' keeps trading forever until you stop it. 'Scheduled' only trades during specific hours (like market open). 'Iterations' runs a fixed number of trade cycles then stops.",
    EXECUTE_TRADES: "The master ON/OFF switch for real trading. When OFF, the bot runs in Paper Trading mode — it still scans markets and executes simulated trades with a virtual balance, but never places actual orders. Perfect for testing strategies risk-free. A broker must still be configured for market data.",
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

    // Trend Detection Indicator Tooltips
    TREND_ADX_ENABLED: "<strong>Average Directional Index (ADX)</strong><br><span style='color:#818cf8;font-size:10px'>Type: Strength</span><br><br>Think of ADX like a speedometer for trends. It doesn't tell you <em>which way</em> the market is going — just <em>how strongly</em> it's moving on a scale of 0 to 100.<br><br>When ADX is below 20, the market is going sideways with no real direction — like a car idling. Above 20, there's a real trend the bot can work with.<br><br><span style='color:#22c55e'>✓ Good for:</span> Keeping the bot from trading in sloppy, sideways markets where there's no clear direction.<br><span style='color:#ef4444'>✗ Heads up:</span> ADX tells you <em>how strong</em> but not <em>which way</em>. It also reacts slowly to sudden reversals.",
    TREND_RSI_ENABLED: "<strong>Relative Strength Index (RSI)</strong><br><span style='color:#818cf8;font-size:10px'>Type: Momentum</span><br><br>RSI measures how much buying vs selling pressure there is, on a scale from 0 to 100. Below 30 means everyone's been selling (oversold — could bounce). Above 70 means everyone's been buying (overbought — could dip).<br><br>The bot uses RSI as a direction hint: above 55 leans bullish, below 45 leans bearish.<br><br><span style='color:#22c55e'>✓ Good for:</span> Spotting when a market has been pushed too far in one direction and might reverse.<br><span style='color:#ef4444'>✗ Heads up:</span> In a strong uptrend, RSI can stay 'overbought' for a long time — it doesn't mean the trend is over.",
    TREND_MACD_ENABLED: "<strong>MACD (Moving Average Convergence Divergence)</strong><br><span style='color:#818cf8;font-size:10px'>Type: Momentum</span><br><br>MACD tracks the gap between a fast and slow moving average. When the fast one crosses above the slow one, momentum is shifting upward. When it crosses below, momentum is shifting down.<br><br>The histogram bar shows how fast momentum is changing — taller bars mean stronger moves.<br><br><span style='color:#22c55e'>✓ Good for:</span> Catching the moment a trend starts picking up steam in one direction.<br><span style='color:#ef4444'>✗ Heads up:</span> In flat, directionless markets, MACD bounces back and forth near zero giving false signals.",
    TREND_BOLLINGER_ENABLED: "<strong>Bollinger Bands</strong><br><span style='color:#818cf8;font-size:10px'>Type: Volatility</span><br><br>Bollinger Bands are like an elastic band around the price. When the bands squeeze tight, the market is quiet — but a big move is usually coming. When they spread wide, the market is already moving fast.<br><br>The bot watches for squeezes and uses them to lower confidence — because during a squeeze, nobody knows <em>which way</em> the breakout will go.<br><br><span style='color:#22c55e'>✓ Good for:</span> Warning when the market is 'coiling up' before a big move, and measuring how wild price swings are.<br><span style='color:#ef4444'>✗ Heads up:</span> In strong trends, price 'rides' the outer band — touching it is NOT a reversal signal.",
    TREND_SUPERTREND_ENABLED: "<strong>Supertrend</strong><br><span style='color:#818cf8;font-size:10px'>Type: Trend-Following</span><br><br>Supertrend places an invisible line that follows the price. When price is above the line, the trend is UP (buy). When price drops below, the trend flips to DOWN (sell). Simple as that — always one or the other, never 'maybe'.<br><br><span style='color:#22c55e'>✓ Good for:</span> Clear, no-nonsense direction calls. Great for markets that are trending cleanly in one direction.<br><span style='color:#ef4444'>✗ Heads up:</span> In choppy sideways markets, Supertrend flips back and forth rapidly — every flip is a potential false signal.",
    TREND_EMA_RIBBON_ENABLED: "<strong>EMA Ribbon (8/21/55)</strong><br><span style='color:#818cf8;font-size:10px'>Type: Structure</span><br><br>The EMA Ribbon uses three trend lines of different speeds (fast, medium, slow). When all three are stacked in order — fast on top — the trend is solidly UP. When stacked in reverse, it's solidly DOWN. When they tangle together, there's no clear trend.<br><br><span style='color:#22c55e'>✓ Good for:</span> Confirming that a trend is real and has momentum across multiple timeframes. The 'fanning out' of the ribbon is one of the strongest trend signals.<br><span style='color:#ef4444'>✗ Heads up:</span> Slow to react to sudden reversals. The ribbon tangles during market transitions, which can delay signals.",
    TREND_ICHIMOKU_ENABLED: "<strong>Ichimoku Cloud</strong><br><span style='color:#818cf8;font-size:10px'>Type: Structure</span><br><br>Ichimoku draws a 'cloud' on the chart made from averaged highs and lows. When the price is <em>above</em> the cloud, the market is bullish. When it's <em>below</em> the cloud, it's bearish. When price is <em>inside</em> the cloud, the market is undecided.<br><br>The thicker the cloud, the stronger the support/resistance. This is one of the most complete indicators — it shows trend, momentum, and key levels all in one.<br><br><span style='color:#22c55e'>✓ Good for:</span> A comprehensive read on market direction. Very popular with professional crypto traders. The cloud acts as a 'comfort zone' for the price.<br><span style='color:#ef4444'>✗ Heads up:</span> Needs lots of data (52 candles minimum). In fast-moving markets, the cloud can lag behind the actual price action.",
    TREND_PARABOLIC_SAR_ENABLED: "<strong>Parabolic SAR (Stop & Reverse)</strong><br><span style='color:#818cf8;font-size:10px'>Type: Trend-Following</span><br><br>Parabolic SAR places dots above or below the price. Dots below = trend is UP. Dots above = trend is DOWN. When the dots 'flip' from one side to the other, the trend has reversed.<br><br>The dots accelerate as the trend continues — they follow more closely over time, almost like a trailing stop-loss that tightens automatically.<br><br><span style='color:#22c55e'>✓ Good for:</span> Catching trend reversals quickly. The flip is a clear, unmistakable signal. Also useful as a dynamic trailing stop level.<br><span style='color:#ef4444'>✗ Heads up:</span> In sideways markets, the dots flip constantly — every flip looks like a reversal but isn't.",
    TREND_VWAP_ENABLED: "<strong>VWAP (Volume-Weighted Average Price)</strong><br><span style='color:#818cf8;font-size:10px'>Type: Volume</span><br><br>VWAP is the average price that accounts for trading volume — it tells you what the 'fair price' is based on where the most trading happened. Big institutional traders (banks, hedge funds) use VWAP to judge whether they're getting a good deal.<br><br>Price above VWAP = buyers are in control (bullish). Price below VWAP = sellers are in control (bearish).<br><br><span style='color:#22c55e'>✓ Good for:</span> Understanding where the 'smart money' thinks the fair price is. Great for crypto and intraday trading.<br><span style='color:#ef4444'>✗ Heads up:</span> Less useful for long-term trends since VWAP resets with each session. Needs volume data to work properly.",
    TREND_HULL_MA_ENABLED: "<strong>Hull Moving Average (HMA)</strong><br><span style='color:#818cf8;font-size:10px'>Type: Smoothed Moving Average</span><br><br>A regular moving average is like looking in the rear-view mirror — you see where the price <em>was</em>, not where it <em>is</em>. Hull MA uses a special math trick to dramatically reduce this lag, giving you a smoother and more current read on the trend.<br><br>When the Hull MA is rising, the trend is UP. When it's falling, the trend is DOWN.<br><br><span style='color:#22c55e'>✓ Good for:</span> Getting a clean, responsive trend direction without the noise. Much faster than regular moving averages while still being smooth.<br><span style='color:#ef4444'>✗ Heads up:</span> Can be <em>too</em> responsive in very choppy markets, flipping direction on minor pullbacks.",
    TREND_ADX_THRESHOLD: "The ADX value below which entries are blocked. When ADX is below this threshold, the bot considers the market 'choppy' and stands aside. Default: 20. Set to 0 to disable the gate entirely.",
    SAFETY_ATR_SHIELD_ENABLED: "Advanced ATR-based protection. Moves stops to breakeven after 1x ATR move and uses dynamic trailing stops.",
    SAFETY_DRAWDOWN_BREAKER_ENABLED: "Account Circuit Breaker. If the account drawdown exceeds the adaptive limit (25% for small accounts down to 5% for large accounts), all entries pause for 24h.",
    SAFETY_SESSION_LOCKOUT_ENABLED: "Prevents over-trading in choppy late-session markets. Automatically stops taking signals after 12:00 PM EST.",

    // Safety Suite 2.0 (New Additions)
    SAFETY_GREED_GUARD_ENABLED: "Profit Lock. Stops trading for the day once a specified daily profit target is hit (Quit while ahead).",
    SAFETY_CHURN_BURNER_ENABLED: "Anti-Churn. Limits the maximum number of trades per hour to prevent over-trading in chop.",
    SAFETY_LEVERAGE_SENTRY_ENABLED: "Leverage Cap. Blocks new entries once total notional exposure exceeds a leverage multiple of your account equity. Disable for small accounts where even one position exceeds the cap.",
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

    // Stop-and-Reverse
    STOP_AND_REVERSE_ENABLED: "<strong>The Uno Reverse Card.</strong><br><br>When ANY stop loss fires, immediately open a new position in the <em>opposite</em> direction with a quick TP target. The logic: if price moved hard enough to stop you, it's probably still moving — ride it the other way.<br><br>This turns losing trades into <em>recovery trades</em>. Each reversal uses the 'Reversal Risk %' setting for sizing and targets a quick 1R profit.",
    COUNTER_REVERSAL_ENABLED: "<strong>Counter-Reversal (CR).</strong><br><br>When the SAR trade starts losing, fire a <em>second</em> trade in the opposite direction at 2× risk with a tight 0.5R stop. If the SAR was wrong, the CR catches the real move. Think of it as insurance: small cost if wrong, big payoff if right.<br><br>CR has its own trailing stop that activates at 0.5R profit.",
    SAR_KEEP_OPEN: "<strong>Keep SAR Open (Strategy-Specific).</strong><br><br>Controls how SAR and CR interact:<br>• <em>ON:</em> SAR stays open when CR fires (triggers at SAR -0.5R). CR exits if SAR recovers to break-even. Best for RoboCop and Evolution.<br>• <em>OFF:</em> SAR closes at break-even and CR fires immediately. Best for Session Momentum, Quantum, and Supply Demand.<br><br>This is a per-strategy optimization.",
    REVERSAL_TP_R: "<strong>Reversal Take Profit (R-Multiple).</strong><br><br>How much profit to target on stop-and-reverse trades, measured in R (risk units). 1.0R means the TP distance equals the risk distance. Higher values let reversals run further but risk more pullback.",
    REVERSAL_COST_AWARE_TP: "<strong>Cost-Aware TP.</strong><br><br>Adds the estimated spread/fee cost to the reversal's TP distance. This ensures the <em>actual</em> bank balance sees a true 1:1 profit after Oanda/broker fees, instead of a slightly-below 1R fill.",
    REVERSAL_RISK_PER_TRADE: "<strong>Reversal Risk %.</strong><br><br>Risk percentage for stop-and-reverse entries. Higher than normal entry risk because the reversal catches momentum. 4.5% means risking $337 on a $7,500 account per reversal.",
    SCALE_OUT_FRACTION: "<strong>Partial Close %.</strong><br><br>When the Conductor fires a 'scale out' (de-risk) signal, this is the fraction of the position to close. 0.95 = close 95% of the position, leaving only 5% to absorb the stop. Higher = smaller losses but less room for recovery.",
};

function getValue(key, strategyNamespace = null) {
    // Authority: Use the current session's timeframe from renderer.js
    if (key === 'GUI_PNL_TIMEFRAME' && typeof window.pnlTimeframe !== 'undefined') {
        return window.pnlTimeframe;
    }

    if (strategyNamespace && configData && configData.active_profile) {
        const active = configData.active_profile;
        if (configData.profiles[active] && configData.profiles[active].strategy_overrides) {
            const stratOverrides = configData.profiles[active].strategy_overrides[strategyNamespace];
            if (stratOverrides && stratOverrides[key.toLowerCase()] !== undefined) {
                return String(stratOverrides[key.toLowerCase()]); // contextual masked value
            }
        }
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
        targets: ['PERFORMANCE_MODE', 'NUCLEAR_OVERRIDES_ENABLED'],
        message: "<strong>Stability Mode</strong> is a survival-first protocol. Enabling it will reset your Performance Mode to 'Standard', disable Nuclear Overrides, and enforce a strict 1% risk ceiling.",
        type: 'modal'
    },
    'NUCLEAR_OVERRIDES_ENABLED:true': {
        targets: ['SAFETY_STABILITY_MODE_ENABLED'],
        message: "<strong>Nuclear Mode</strong> removes all hard-coded safety ceilings. This is incompatible with <strong>Stability Mode</strong> — Stability will be disabled.",
        type: 'modal'
    },
    'performance:gamma': {
        targets: ['TRAILING_STOP_ENABLED'],
        message: "<strong>Gamma Squeeze</strong> uses hyper-tight trailing stops to lock in velocity. This will override your standard 'Trailing Stop' settings.",
        type: 'ghost',
        requires: { key: 'SAFETY_ATR_SHIELD_ENABLED', message: '<strong>Gamma Squeeze</strong> requires <strong>ATR Armor</strong> to be enabled. Its trailing logic runs inside the ATR Armor block — without it, Gamma is silently dead.' }
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
    },
    // ── Loader-Silent Conflicts (P10: UI now warns instead of silent override) ──
    'PDT_GUARD_ENABLED:true': {
        targets: ['AUTO_FLATTEN_ON_CLOSE'],
        message: "<strong>PDT Guard</strong> is incompatible with <strong>Auto-Flatten</strong>. The backend will force Auto-Flatten OFF to prevent accidental pattern day-trading violations.",
        type: 'modal'
    },
    'CONTINUOUS_MODE:true': {
        targets: ['INTRADAY_FLATTEN'],
        message: "<strong>Continuous Mode</strong> runs 24/7 — <strong>Intraday Flatten</strong> will be forced OFF by the backend since there is no 'session end' to flatten at.",
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
        // Skip modal if all targets are already in the desired state (off/false)
        if (config.type === 'modal' && config.targets.length > 0) {
            const allAlreadyOff = config.targets.every(t => {
                const cur = getActiveProfileSettings()[t];
                return cur === false || cur === 'false' || cur === '' || cur === undefined || cur === null || cur === 'off' || cur === 'none';
            });
            if (allAlreadyOff) {
                // No conflict — targets already disabled, just apply the change
                updateValue(sourceKey, value);
                renderTab();
                return true;
            }
        }

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
    // Remove any existing modal
    let modal = document.getElementById('conflict-modal');
    if (modal) modal.remove();

    modal = document.createElement('div');
    modal.id = 'conflict-modal';
    Object.assign(modal.style, {
        position: 'fixed', top: '0', left: '0', width: '100vw', height: '100vh',
        zIndex: '99999', display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: 'rgba(0,0,0,0.85)', backdropFilter: 'blur(8px)',
        WebkitBackdropFilter: 'blur(8px)', padding: '24px',
        opacity: '0', transition: 'opacity 0.3s ease',
    });

    modal.innerHTML = `
        <div style="
            background: linear-gradient(145deg, #1a1e2e 0%, #0f1219 100%);
            border: 1px solid rgba(245,158,11,0.3);
            border-radius: 16px; padding: 28px; max-width: 440px; width: 100%;
            box-shadow: 0 25px 60px rgba(0,0,0,0.6), 0 0 40px rgba(245,158,11,0.08);
            animation: modalSlideIn 0.3s ease forwards;
        ">
            <style>
                @keyframes modalSlideIn {
                    from { transform: translateY(20px) scale(0.95); opacity: 0; }
                    to { transform: translateY(0) scale(1); opacity: 1; }
                }
            </style>
            <div style="display:flex; align-items:center; gap:12px; margin-bottom:16px;">
                <span class="material-symbols-outlined" style="color:#f59e0b; font-size:28px;">warning</span>
                <h3 id="modal-title" style="font-size:18px; font-weight:700; color:#fff; margin:0;"></h3>
            </div>
            <div id="modal-message" style="
                font-size:14px; color:#94a3b8; line-height:1.7; margin-bottom:24px;
                padding: 14px 16px; background: rgba(245,158,11,0.06);
                border-left: 3px solid rgba(245,158,11,0.4); border-radius: 8px;
            "></div>
            <div style="display:flex; gap:12px; justify-content:flex-end;">
                <button id="modal-cancel" style="
                    padding:10px 20px; border-radius:10px; border:1px solid rgba(255,255,255,0.1);
                    background:rgba(255,255,255,0.05); color:#94a3b8; cursor:pointer;
                    font-size:13px; font-weight:500; transition:all 0.2s ease;
                " onmouseover="this.style.background='rgba(255,255,255,0.1)';this.style.color='#fff'"
                  onmouseout="this.style.background='rgba(255,255,255,0.05)';this.style.color='#94a3b8'"
                >Cancel</button>
                <button id="modal-confirm" style="
                    padding:10px 20px; border-radius:10px; border:none;
                    background:linear-gradient(135deg, #f59e0b, #d97706); color:#000; cursor:pointer;
                    font-size:13px; font-weight:700; transition:all 0.2s ease;
                    box-shadow: 0 4px 12px rgba(245,158,11,0.3);
                " onmouseover="this.style.background='linear-gradient(135deg, #fbbf24, #f59e0b)';this.style.transform='translateY(-1px)'"
                  onmouseout="this.style.background='linear-gradient(135deg, #f59e0b, #d97706)';this.style.transform='none'"
                >Proceed & Resolve</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);

    modal.querySelector('#modal-title').innerHTML = title;
    modal.querySelector('#modal-message').innerHTML = message;

    const closeModal = () => {
        modal.style.opacity = '0';
        setTimeout(() => modal.remove(), 300);
    };

    modal.querySelector('#modal-confirm').onclick = () => { onConfirm(); closeModal(); };
    modal.querySelector('#modal-cancel').onclick = closeModal;
    modal.onclick = (e) => { if (e.target === modal) closeModal(); };

    // Fade in
    requestAnimationFrame(() => { modal.style.opacity = '1'; });
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
        assetClass: "forex",
        description: "The Opening Range Breakout (ORB) strategy. It watches the first 15 minutes of the New York Stock Market open (9:30 AM ET) to see where the big money is moving. It waits for the price to break out of that range, come back to test the level for safety, and form a 'flag' pattern before entering. ⚠️ BACKTESTED: 0% win rate on Forex — broken for short timeframes. Needs session-specific data.",
        style: "Breakout",
        risk: "Low-Medium",
        bestFor: "Forex: NY Open (9:30-11:00 ET), Stocks/ETFs",
        stats: { verified: "❌ Forex: -$1.7K", winRate: "0%", riskReward: "2:1" }
    },
    rubberband_reaper: {
        name: "Rubberband Reaper",
        shortDesc: "Anti-Martingale Mean Reversion",
        assetClass: "universal",
        description: "Uses Bollinger Bands and RSI to catch price reversals at extremes. Features intelligent tiered risk management that INCREASES position size after wins and DECREASES after losses. Targets the opposite Bollinger Band for 3:1+ reward-to-risk ratios.",
        style: "Mean Reversion",
        risk: "Adaptive",
        bestFor: "Universal: ranging markets, volatile assets",
        stats: { verified: "+7,036%", winRate: "39%", riskReward: "3.7:1" }
    },
    robocop: {
        name: "RoboCop",
        shortDesc: "Aggressive High-Frequency ICC",
        assetClass: "crypto",
        description: "Lightning-fast execution with minimal confirmation requirements. Reacts to ANY valid micro-signal without waiting for corrections. Uses 1-bar confirmation and targets 3.0 ATR for maximum profit potential. Includes fast 'chop exit' to avoid ranging traps. ✅ CRYPTO: $2.5M profit, 33% win rate. ❌ FOREX: -$2K (spread eats all profit).",
        style: "Aggressive Scalping",
        risk: "High",
        bestFor: "Crypto: high-frequency scalping — DO NOT use for Forex",
        stats: { crypto: "✅ +$2.5M", forex: "❌ -$2K", target: "3.0 ATR" }
    },
    evolution: {
        name: "Robot Evolution",
        shortDesc: "NTZ Range Scalper",
        assetClass: "crypto",
        description: "Optimized for choppy, ranging markets. Identifies the 'No-Trade-Zone' (NTZ) between swing highs and lows, then trades liquidity sweeps at the edges. Targets 2.0R with conservative 1.5 ATR stops. ✅ CRYPTO: $2.3M profit, 27% win rate. ❌ FOREX: -$1.1K (NTZ scalping can't overcome OANDA spreads).",
        style: "Range Trading",
        risk: "Low-Medium",
        bestFor: "Crypto: ranging markets, NTZ liquidity sweeps",
        stats: { crypto: "✅ +$2.3M", forex: "❌ -$1.1K", focus: "NTZ edges" }
    },
    quantum: {
        name: "Quantum",
        shortDesc: "Trend-Following with SMA Pullback",
        assetClass: "crypto",
        description: "Classic trend-following strategy that waits for price to pull back to the 20-period SMA before entering in the trend direction. Requires HTF/LTF alignment and momentum confirmation. ⚠️ BACKTESTED: -$2K on Forex 15m (6% win rate). Forex spreads destroy the 2:1 R:R edge. May work on 4H+ timeframes or crypto where trends are stronger.",
        style: "Trend Following",
        risk: "Medium",
        bestFor: "Crypto: trend pullbacks, or 4H+ Forex only",
        stats: { forex15m: "❌ -$2K", indicator: "20 SMA", target: "2:1 R:R" }
    },
    mean_reversion: {
        name: "Mean Reversion",
        shortDesc: "Bollinger + RSI Extremes",
        assetClass: "universal",
        description: "Enters when price breaks outside Bollinger Bands (15-period, 2.5 std) with RSI confirmation of oversold (<25) or overbought (>75). Supports pyramiding with 6-bar cooldown between adds. Simple but effective for ranging markets.",
        style: "Mean Reversion",
        risk: "Medium",
        bestFor: "Universal: ranging Forex and Crypto markets",
        stats: { bands: "15p/2.5σ", rsi: "<25/>75", pyramid: "6-bar cool" }
    },
    hyper_scalper: {
        name: "HyperScalper",
        shortDesc: "EMA Crossover Speed Trading",
        assetClass: "universal",
        description: "High-frequency 5-minute scalper using 9/21 EMA crossovers filtered by 200 EMA trend and RSI. Designed for aggressive compounding with 1% default risk per trade. ❌ BACKTESTED: 0% win rate on Forex, lost 100% of capital. Spread noise triggers false crossovers constantly.",
        style: "Fast Scalping",
        risk: "Very High",
        bestFor: "Universal: ❌ NOT RECOMMENDED — 0% win rate",
        stats: { ema: "9/21/200", forex: "❌ -$2K (0% win)", risk: "1%" }
    },
    london_breakout: {
        name: "London Breakout",
        shortDesc: "Session Opening Range",
        assetClass: "forex",
        description: "Trades the breakout of the first hour of London session (08:00-09:00 GMT). Waits for the range to establish, then enters on breakout of the high or low before noon. Classic institutional strategy with 1.5R targets.",
        style: "Breakout",
        risk: "Medium",
        bestFor: "Forex: GBP pairs, European session",
        stats: { session: "08:00-12:00", target: "1.5R", window: "London" }
    },
    volatility_breakout: {
        name: "Volatility Breakout",
        shortDesc: "Range Expansion Momentum",
        assetClass: "universal",
        description: "Catches explosive moves when price breaks out of a 20-period range with RSI confirmation (>60 long, <40 short). Features fast momentum exit when RSI reverses. Great for catching the start of new trends.",
        style: "Breakout",
        risk: "Medium-High",
        bestFor: "Universal: any market showing compression",
        stats: { range: "20 periods", target: "2.0R", rsi: ">60/<40" }
    },
    aggregator: {
        name: "Singularity Aggregator",
        shortDesc: "Multi-Strategy Parallel",
        assetClass: "universal",
        description: "Runs Mean Reversion + HyperScalper simultaneously for maximum capital utilization. Prioritizes scale-ins on existing winners, then new entries. Keeps the bot 'always loaded' for potential 400%+ returns by never missing opportunities.",
        style: "Multi-Strategy",
        risk: "Variable",
        bestFor: "Universal: maximizing capital efficiency",
        stats: { strategies: "2 parallel", priority: "Scale > New", goal: "Always loaded" }
    },
    icc_core_standalone: {
        name: "ICC Core (ICT Methodology)",
        shortDesc: "Displacement + OTE Pullback",
        assetClass: "universal",
        description: "Pure ICT (Inner Circle Trader) methodology: detects displacement (consecutive momentum candles), then enters on pullback to the Optimal Trade Entry zone (50-78.6% Fibonacci) or at a Fair Value Gap. Uses engine trend as directional bias. Tight 1.5× ATR stops for better risk control.",
        style: "Price Action / ICT",
        risk: "Low-Medium",
        bestFor: "Universal: ICT methodology with tight risk",
        stats: { method: "ICT OTE+FVG", stop: "1.5× ATR", target: "2.0R" }
    },
    supply_demand: {
        name: "Supply & Demand",
        shortDesc: "Institutional Price Action",
        assetClass: "universal",
        description: "Uses the pure institutional methodology of Supply and Demand zones. Waits for a clear Break of Structure, tags the 'Base' candle as a high-probability zone, enters when price returns to 'tap' that zone. ✅ BACKTESTED #1 FOREX: $1.4M profit. ✅ #2 CRYPTO: $4.7M profit. Extreme R:R (avg win 250× avg loss) compensates for low 5-20% win rate.",
        style: "Price Action / Institutional",
        risk: "Low-Medium",
        bestFor: "Universal: ✅ BEST for both Forex and Crypto",
        stats: { forex: "✅ #1 +$1.4M", crypto: "✅ #2 +$4.7M", method: "SND Zones" }
    },
    meta_sci: {
        name: 'Meta-SCI',
        icon: 'auto_awesome',
        shortDesc: 'AI-Enhanced Ensemble Strategy',
        assetClass: "universal",
        description: "The ultimate AI Brain. Runs multiple trading strategies simultaneously and uses an AI ensemble to pick the best signal per trade — like a manager who only listens to the most successful expert for each situation. ✅ BACKTESTED #1 CRYPTO: $8.2M profit, 30% win rate. ✅ #2 FOREX: $951K profit. Consistently profitable across all markets.",
        style: "AI Ensemble",
        risk: "Dynamic",
        bestFor: "Universal: ✅ BEST for Crypto, EXCELLENT for Forex",
        stats: { crypto: "✅ #1 +$8.2M", forex: "✅ #2 +$951K", ai: "Ensemble" }
    },
    forex_conductor: {
        name: 'Forex Conductor',
        icon: 'route',
        shortDesc: 'Regime-Based Strategy Router',
        assetClass: "forex",
        description: "Reads the market regime in real-time and routes to the right strategy: Trending → Trend Rider (EMA pullback entries), Ranging → Mean Reversion (Bollinger bounces), Transitional → Session Breakout (London open). Blocks ALL entries in choppy markets (HTF/LTF disagreement). Gates include 19% HTF strength minimum, 2h entry cooldown, loss streak cooldown, and HTF/LTF alignment checks. Trades in bursts when conditions align, sits out when they don't.",
        style: "Regime Router",
        risk: "Dynamic (conservative gates)",
        bestFor: "Forex: adapts to market conditions automatically",
        stats: { regimes: "4 (trend/range/transition/choppy)", cooldown: "2h", gate: "HTF/LTF align" }
    },
    trend_rider: {
        name: 'Trend Rider',
        shortDesc: 'EMA Pullback in Strong Trend',
        assetClass: "forex",
        description: "Waits for price to pull back to the EMA(21) during a confirmed strong HTF trend (strength ≥ 0.5). Requires EMA(8)/EMA(21) alignment, RSI 40-60 pullback zone, price within 0.3 ATR of slow EMA, and a confirming bounce. Used by the Conductor as its trending-regime sub-strategy — the Conductor's loss-cutting gates (Structure Invalidation at 0.5× ATR) keep avg losses to ~$3-8.",
        style: "Trend Following",
        risk: "Medium (low when inside Conductor)",
        bestFor: "Forex: trending regimes via Conductor",
        stats: { filters: "6 entry gates", indicator: "EMA 8/21", avgLoss: "$3-8 (Conductor)" }
    },
    session_momentum: {
        name: 'Session Momentum',
        shortDesc: 'VWAP + Volume Surge at Open',
        assetClass: "forex",
        description: "Captures the initial directional move during the highest-volume period of the trading day. Active only in the first 30 minutes of London (08:00-08:30 UTC) or New York (09:30-10:00 ET) session. Requires a VWAP break with 2× average volume surge for entry.",
        style: "Momentum / Session",
        risk: "Medium-High",
        bestFor: "Forex: London & NY session opens",
        stats: { indicator: "VWAP", volume: "2× avg", target: "2.0R" }
    },
    bearish_engulfing: {
        name: 'Engulfing Reversal',
        shortDesc: 'Candle Pattern at Key Structure',
        assetClass: "universal",
        description: "Classic price action reversal pattern. Enters when a bullish or bearish engulfing candle forms at a key structural level (swing high/low) with HTF alignment. Optional RSI divergence detection for higher probability setups. Stop placed beyond the engulfing candle's wick.",
        style: "Price Action / Reversal",
        risk: "Medium",
        bestFor: "Universal: reversal zones, supply/demand levels",
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
        assetClass: "crypto",
        description: "Combines RSI oversold/overbought readings with MACD crossover confirmations. Designed for 24/7 crypto markets — no session gating. Waits for RSI to exit extreme zones while MACD histogram flips direction. ATR-based stops.",
        style: "Momentum / Crypto",
        risk: "Medium",
        bestFor: "Crypto: trending markets, BTC/ETH swing trades",
        stats: { rsi: "30/70", macd: "12/26/9", target: "2.0R" }
    },
    crypto_vwap_reversion: {
        name: 'VWAP Reversion (Crypto)',
        shortDesc: 'Mean Reversion to VWAP',
        assetClass: "crypto",
        description: "Enters when price deviates significantly from the volume-weighted average price and shows signs of reverting. Uses Bollinger-style bands around VWAP with volume confirmation. Optimized for high-volume crypto pairs.",
        style: "Mean Reversion / Crypto",
        risk: "Medium",
        bestFor: "Crypto: ranging markets, high-volume pairs",
        stats: { indicator: "VWAP", bands: "2σ", target: "1.5R" }
    },
    crypto_double_macd: {
        name: 'Double MACD Scalper (Crypto)',
        shortDesc: 'Dual-Timeframe MACD Momentum',
        assetClass: "crypto",
        description: "Uses two MACD indicators on different timeframes for confluence. Fast MACD (5/13/4) for entry timing, slow MACD (12/26/9) for trend filter. Designed for tight crypto scalps with quick exits on momentum fade.",
        style: "Scalping / Crypto",
        risk: "High",
        bestFor: "Crypto: active pairs, scalping BTC/SOL",
        stats: { fast: "5/13/4", slow: "12/26/9", target: "1.5R" }
    },
    crypto_grid: {
        name: 'Virtual Grid (Crypto)',
        shortDesc: 'Grid Trading with Dynamic Levels',
        assetClass: "crypto",
        description: "Places a virtual grid of buy/sell zones around the current market price. Profits from price oscillation within a range. Automatically adjusts grid spacing based on ATR volatility. No physical grid orders — all managed internally.",
        style: "Grid / Crypto",
        risk: "Medium-High",
        bestFor: "Crypto: sideways/ranging markets",
        stats: { levels: "Dynamic", spacing: "ATR-based", target: "0.5-1.0R" }
    },
    yoyo: {
        name: 'Yo-Yo',
        shortDesc: 'Momentum Reversal Engine',
        assetClass: "universal",
        description: "Proven trend-following SAR strategy. Uses 50 SMA as trend filter (only long above, short below), requires strong directional candle confirmation (close in top/bottom 30% of range), and swing-based structural stops. 2:1 R:R target. On stop hit, SAR reverses automatically. Risk escalates +1% after each profitable exit. Best with SAR enabled.",
        style: "Trend / SAR",
        risk: "Medium",
        bestFor: "Universal: trending markets with SAR enabled",
        stats: { target: "2:1 R:R", stop: "Swing-based", sar: "Auto-reverse", cap: "3/day/symbol" }
    }
};

// ═══════════════════════════════════════════════════════════
// STRATEGY PRESETS — optimal settings per strategy
// When a strategy is selected, these settings auto-apply.
// Users can still adjust individual settings afterwards.
// ═══════════════════════════════════════════════════════════

const STRATEGY_PRESETS = {
    // --- Universal Strategies ---
    rubberband_reaper: {
        RISK_PER_TRADE_PCT: '1.0',
        STOP_AND_REVERSE_ENABLED: 'false',
        TRAILING_STOP_ENABLED: 'true',
        MAX_PYRAMID_ENTRIES: '6',
        RISK_REWARD_RATIO: '3.0',
        SCALE_OUT_FRACTION: '0.50',
    },
    mean_reversion: {
        RISK_PER_TRADE_PCT: '2.0',  // Backtested optimal: +$881 at 2.0% (was +$535 at 1%)
        STOP_AND_REVERSE_ENABLED: 'false', // SAR hurts MR (-$589)
        TRAILING_STOP_ENABLED: 'false',
        MAX_PYRAMID_ENTRIES: '6',
        RISK_REWARD_RATIO: '2.0',
        SCALE_OUT_FRACTION: '0.95',
    },
    supply_demand: {
        RISK_PER_TRADE_PCT: '1.0',
        STOP_AND_REVERSE_ENABLED: 'false',
        TRAILING_STOP_ENABLED: 'true',
        MAX_PYRAMID_ENTRIES: '50',
        RISK_REWARD_RATIO: '2.0',
        SCALE_OUT_FRACTION: '0.95',
    },
    bearish_engulfing: {
        RISK_PER_TRADE_PCT: '2.5',  // Backtested optimal: +$11 at 2.5% (only profitable level)
        STOP_AND_REVERSE_ENABLED: 'false', // SAR hurts BE
        TRAILING_STOP_ENABLED: 'true',
        MAX_PYRAMID_ENTRIES: '3',
        RISK_REWARD_RATIO: '2.0',
        SCALE_OUT_FRACTION: '0.95',
    },
    // --- Forex Strategies ---
    london_breakout: {
        RISK_PER_TRADE_PCT: '0.5',  // Backtested optimal: -$55 at 0.5% (1.17 R:R, best loss level)
        STOP_AND_REVERSE_ENABLED: 'false',
        TRAILING_STOP_ENABLED: 'true',
        MAX_PYRAMID_ENTRIES: '1',
        RISK_REWARD_RATIO: '1.5',
        SCALE_OUT_FRACTION: '0.95',
    },
    forex_conductor: {
        RISK_PER_TRADE_PCT: '1.0',
        STOP_AND_REVERSE_ENABLED: 'true',   // SAR is the Conductor's cornerstone
        REVERSAL_TP_R: '1.0',
        REVERSAL_COST_AWARE_TP: 'true',
        REVERSAL_RISK_PER_TRADE: '0.045',
        TRAILING_STOP_ENABLED: 'true',
        MAX_PYRAMID_ENTRIES: '50',
        RISK_REWARD_RATIO: '2.0',
        SCALE_OUT_FRACTION: '0.95',
    },
    trend_rider: {
        RISK_PER_TRADE_PCT: '1.0',
        STOP_AND_REVERSE_ENABLED: 'false',
        TRAILING_STOP_ENABLED: 'true',
        MAX_PYRAMID_ENTRIES: '3',
        RISK_REWARD_RATIO: '2.0',
        SCALE_OUT_FRACTION: '0.95',
    },
    session_momentum: {
        RISK_PER_TRADE_PCT: '1.5',
        STOP_AND_REVERSE_ENABLED: 'false',
        TRAILING_STOP_ENABLED: 'true',
        MAX_PYRAMID_ENTRIES: '1',
        RISK_REWARD_RATIO: '2.0',
        SCALE_OUT_FRACTION: '0.95',
    },
    // --- RoboCop: ICC Core + SAR + Guillotine + higher risk ---
    robocop: {
        RISK_PER_TRADE_PCT: '2.0',
        STOP_AND_REVERSE_ENABLED: 'true',
        REVERSAL_TP_R: '1.0',
        REVERSAL_COST_AWARE_TP: 'true',
        REVERSAL_RISK_PER_TRADE: '0.02',
        TRAILING_STOP_ENABLED: 'true',
        MAX_PYRAMID_ENTRIES: '50',
        RISK_REWARD_RATIO: '2.0',
        SCALE_OUT_FRACTION: '0.95',
    },
    // --- Yo-Yo: SAR reversal engine ---
    yoyo: {
        RISK_PER_TRADE_PCT: '1.0',
        STOP_AND_REVERSE_ENABLED: 'true',
        REVERSAL_TP_R: '1.0',
        REVERSAL_COST_AWARE_TP: 'true',
        REVERSAL_RISK_PER_TRADE: '0.015',
        TRAILING_STOP_ENABLED: 'false',
        MAX_PYRAMID_ENTRIES: '1',
        RISK_REWARD_RATIO: '1.0',
        SCALE_OUT_FRACTION: '0.95',
    },
    // --- ICC Core variants ---
    icc_core: {
        RISK_PER_TRADE_PCT: '1.0',
        STOP_AND_REVERSE_ENABLED: 'false',
        TRAILING_STOP_ENABLED: 'true',
        MAX_PYRAMID_ENTRIES: '50',
        RISK_REWARD_RATIO: '2.0',
        SCALE_OUT_FRACTION: '0.95',
    },
    icc_core_standalone: {
        RISK_PER_TRADE_PCT: '1.6',  // Backtested optimal: +$3,564 at 1.6% with SAR
        STOP_AND_REVERSE_ENABLED: 'true', // SAR critical for ICC Core
        REVERSAL_TP_R: '1.0',
        REVERSAL_COST_AWARE_TP: 'true',
        REVERSAL_RISK_PER_TRADE: '0.016',
        TRAILING_STOP_ENABLED: 'true',
        MAX_PYRAMID_ENTRIES: '50',
        RISK_REWARD_RATIO: '2.0',
        SCALE_OUT_FRACTION: '0.95',
    },
    // --- Evolution and Quantum ---
    evolution: {
        RISK_PER_TRADE_PCT: '1.0',
        STOP_AND_REVERSE_ENABLED: 'false',
        TRAILING_STOP_ENABLED: 'true',
        MAX_PYRAMID_ENTRIES: '50',
        RISK_REWARD_RATIO: '2.0',
        SCALE_OUT_FRACTION: '0.95',
    },
    quantum: {
        RISK_PER_TRADE_PCT: '1.0',
        STOP_AND_REVERSE_ENABLED: 'false',
        TRAILING_STOP_ENABLED: 'true',
        MAX_PYRAMID_ENTRIES: '3',
        RISK_REWARD_RATIO: '2.0',
        SCALE_OUT_FRACTION: '0.95',
    },
    // --- Crypto Strategies ---
    hyper_scalper: {
        RISK_PER_TRADE_PCT: '1.0',
        STOP_AND_REVERSE_ENABLED: 'false',
        TRAILING_STOP_ENABLED: 'false',
        MAX_PYRAMID_ENTRIES: '1',
        RISK_REWARD_RATIO: '2.0',
        SCALE_OUT_FRACTION: '0.50',
    },
    crypto_rsi_macd: {
        RISK_PER_TRADE_PCT: '1.0',
        STOP_AND_REVERSE_ENABLED: 'false',
        TRAILING_STOP_ENABLED: 'true',
        MAX_PYRAMID_ENTRIES: '3',
        RISK_REWARD_RATIO: '2.0',
        SCALE_OUT_FRACTION: '0.50',
    },
    crypto_vwap_reversion: {
        RISK_PER_TRADE_PCT: '1.0',
        STOP_AND_REVERSE_ENABLED: 'false',
        TRAILING_STOP_ENABLED: 'false',
        MAX_PYRAMID_ENTRIES: '3',
        RISK_REWARD_RATIO: '1.5',
        SCALE_OUT_FRACTION: '0.50',
    },
    // --- Multi/Meta ---
    meta_sci: {
        RISK_PER_TRADE_PCT: '1.0',
        STOP_AND_REVERSE_ENABLED: 'true',
        REVERSAL_TP_R: '1.0',
        REVERSAL_COST_AWARE_TP: 'true',
        REVERSAL_RISK_PER_TRADE: '0.045',
        TRAILING_STOP_ENABLED: 'true',
        MAX_PYRAMID_ENTRIES: '50',
        RISK_REWARD_RATIO: '2.0',
        SCALE_OUT_FRACTION: '0.95',
    },
};

/**
 * Apply a strategy's preset settings when selected.
 * Updates all mapped settings via updateValue() and shows a notification.
 */
function applyStrategyPreset(strategyKey) {
    const preset = STRATEGY_PRESETS[strategyKey];
    if (!preset) return; // No preset defined for this strategy

    const stratName = STRATEGIES[strategyKey]?.name || strategyKey;
    const changes = [];

    for (const [key, value] of Object.entries(preset)) {
        const current = getValue(key);
        if (String(current) !== String(value)) {
            updateValue(key, value);
            changes.push(key);
        }
    }

    if (changes.length > 0) {
        console.log(`[PRESET] Applied ${stratName} preset: ${changes.join(', ')}`);
        showNotice(`${stratName} preset applied (${changes.length} settings)`, 'teal');
        renderTab(); // Refresh UI to reflect changes
    }
}

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
    paper: { icon: 'history', label: 'Paper & Replay', render: renderPaperTab },
    safety: { icon: 'shield', label: 'Safety', render: renderSafetyTab },
    performance: { icon: 'trending_up', label: 'Performance', render: renderPerformanceTab },
    brokers: { icon: 'lan', label: 'Brokers', render: renderBrokersTab },
    ai: { icon: 'auto_awesome', label: 'Intelligence', render: renderAITab },
    schedule: { icon: 'event_repeat', label: 'Schedule', render: renderScheduleTab },
    appearance: { icon: 'palette', label: 'Appearance', render: renderAppearanceTab },
    advanced: { icon: 'terminal', label: 'Advanced', render: renderAdvancedTab },
    trends: { icon: 'analytics', label: 'Trends', render: renderTrendsTab },
};

// ═══════════════════════════════════════════════════════════
// INITIALIZATION
// ═══════════════════════════════════════════════════════════

async function init() {
    // ── Browser Mock Mode ────────────────────────────────────────────
    // When opened outside Electron (e.g. file:// in a plain browser),
    // stub window.api so the entire settings UI renders interactively.
    if (!window.api && !window.electronAPI) {
        console.warn("[SETTINGS] No Electron API — running in BROWSER MOCK MODE");
        const mockProfile = {
            bot_mode: 'continuous',
            TREND_ADX_ENABLED: 'true',
            TREND_ADX_THRESHOLD: '20',
            TREND_RSI_ENABLED: 'false',
            TREND_MACD_ENABLED: 'false',
            TREND_BOLLINGER_ENABLED: 'false',
            TREND_SUPERTREND_ENABLED: 'false',
            TREND_EMA_RIBBON_ENABLED: 'false',
            TREND_ICHIMOKU_ENABLED: 'false',
            TREND_PARABOLIC_SAR_ENABLED: 'false',
            TREND_VWAP_ENABLED: 'false',
            TREND_HULL_MA_ENABLED: 'false',
            SAFETY_ATR_SHIELD_ENABLED: 'true',
            SAFETY_DRAWDOWN_BREAKER_ENABLED: 'true',
            SAFETY_SESSION_LOCKOUT_ENABLED: 'false',
            PERFORMANCE_MODE: 'balanced',
        };
        window.api = {
            readConfig: async () => ({
                global: { bot_mode: 'continuous' },
                active_profile: 'default',
                profiles: { default: mockProfile },
            }),
            readSecrets: async () => ({}),
            setEnv: async (key, val) => { console.log(`[MOCK] setEnv ${key}=${val}`); },
            saveConfig: async (cfg) => { console.log('[MOCK] saveConfig', cfg); },
            getBotStatus: () => { },
            onBotStatus: () => { },
            onConfigUpdated: () => { },
        };
    }

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

    // Also pull global per-asset strategies (set by AI Optimize) as fallbacks
    const g = configData.global || {};
    const globalStrategyMap = {
        crypto: g.strategy_crypto, forex: g.strategy_forex,
        stocks: g.strategy_stocks, etf: g.strategy_etf,
        metals: g.strategy_metals, futures: g.strategy_futures,
    };
    for (const [asset, val] of Object.entries(globalStrategyMap)) {
        if (val && !settings.strategies[asset]) {
            settings.strategies[asset] = val;
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

function createSectionHeader(title, icon = null, tooltip = null) {
    const header = document.createElement('div');
    header.className = 'settings-label text-glow-teal';
    let html = icon
        ? `<span class="material-symbols-outlined">${icon}</span>${title}`
        : title;
    if (tooltip) {
        html += ` <span class="material-symbols-outlined info-icon" style="font-size:14px;cursor:help;vertical-align:middle;color:var(--accent-teal);opacity:0.6">info</span>`;
    }
    header.innerHTML = html;
    // Wire up tooltip hover if content provided
    if (tooltip) {
        const infoIcon = header.querySelector('.info-icon');
        if (infoIcon && typeof showTooltip === 'function') {
            infoIcon.addEventListener('mouseenter', (e) => showTooltip(e, title, tooltip));
            infoIcon.addEventListener('mouseleave', hideTooltip);
        }
    }
    return header;
}

let currentStrategyContext = null;

function createCard(title, desc, key, controlType, options = {}) {
    const stratNamespace = options.strategy || currentStrategyContext;
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
    const rawValue = getValue(key, stratNamespace);
    const value = (rawValue !== null && rawValue !== undefined && rawValue !== '') ? rawValue : (options.default || '');

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
            updateValue(key, strVal, stratNamespace);
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
        input.addEventListener('change', (e) => updateValue(key, e.target.value, stratNamespace));
        // Auto-save on typing (debounced) — critical for password/API key fields
        // where users type and switch tabs without clicking away (blur), so 'change' never fires
        let _inputDebounce;
        input.addEventListener('input', (e) => {
            clearTimeout(_inputDebounce);
            _inputDebounce = setTimeout(() => updateValue(key, e.target.value, stratNamespace), 800);
        });

        if (options.password) {
            // Wrap in a container with an eyeball reveal/hide toggle
            const wrapper = document.createElement('div');
            wrapper.style.cssText = 'position:relative;display:flex;align-items:center;width:100%;';
            input.style.cssText += 'flex:1;padding-right:36px;';
            const eyeBtn = document.createElement('button');
            eyeBtn.type = 'button';
            eyeBtn.innerHTML = '👁';
            eyeBtn.title = 'Show/hide value';
            eyeBtn.style.cssText = 'position:absolute;right:8px;background:none;border:none;cursor:pointer;font-size:16px;opacity:0.5;padding:2px 4px;transition:opacity 0.2s;';
            eyeBtn.addEventListener('mouseenter', () => { eyeBtn.style.opacity = '1'; });
            eyeBtn.addEventListener('mouseleave', () => { eyeBtn.style.opacity = '0.5'; });
            eyeBtn.addEventListener('click', () => {
                if (input.type === 'password') {
                    input.type = 'text';
                    eyeBtn.innerHTML = '👁‍🗨';
                    eyeBtn.title = 'Hide value';
                } else {
                    input.type = 'password';
                    eyeBtn.innerHTML = '👁';
                    eyeBtn.title = 'Show value';
                }
            });
            wrapper.appendChild(input);
            wrapper.appendChild(eyeBtn);
            controlContainer.appendChild(wrapper);
        } else {
            controlContainer.appendChild(input);
        }
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

function createSliderCard(title, desc, key, min, max, step, unit = '%', options = {}) {
    const stratNamespace = options.strategy || currentStrategyContext;
    const card = document.createElement('div');
    card.className = 'slider-card';
    const _raw = getValue(key, stratNamespace);
    let rawValue = (_raw !== null && _raw !== undefined && _raw !== '') ? _raw : min;

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
        updateValue(key, saveValue, stratNamespace);
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
    section.appendChild(createSectionHeader('Core Runtime', 'dashboard',
        "<strong>Core Runtime</strong><br><br>The fundamental settings that control how the bot operates — which strategy to use, how it loops, and whether it places real orders. Think of this as the cockpit's master control panel."
    ));

    // Active Profile selection moved to Profile tab (activate button on each profile card)



    section.appendChild(createCard('Execution Mode', 'How the bot cycles through iterations', 'BOT_MODE', 'dropdown', {
        items: [
            { value: 'continuous', label: 'Continuous Loop' },
            { value: 'scheduled', label: 'Session Windows' },
            { value: 'iterations', label: 'Fixed Iterations' }
        ]
    }));

    section.appendChild(createCard('Live Trading', 'Master switch for real order execution', 'EXECUTE_TRADES', 'toggle'));
    // REMOVED: 'Auto-Start Bot' (GUI_AUTOSTART_BOT) — Dead toggle, 0 runtime refs (Audit P0)
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
    // ── Profile Overrides ──────────────────────────────────
    section.appendChild(createDivider());
    section.appendChild(createSectionHeader('Profile Overrides', 'tune',
        "<strong>What are Profile Overrides?</strong><br><br>When enabled, global settings are saved separately for each profile. Switching profiles will load that profile's custom global settings.<br><br>When disabled, all profiles share the same global settings."
    ));
    section.appendChild(createCard('Profile Overrides', 'Allow each profile to have its own global settings', 'PROFILE_OVERRIDES_ENABLED', 'toggle', { default: 'false' }));

    section.appendChild(createDivider());

    // Runtime Control (Start/Stop/Restart)
    section.appendChild(createSectionHeader('Runtime Control', 'play_circle',
        "<strong>Runtime Control</strong><br><br>Start, stop, or restart the trading bot directly from this panel. The bot runs in the background — use these buttons to control its lifecycle."
    ));

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
    section.appendChild(createSectionHeader('Timeframes', 'schedule',
        "<strong>Timeframes</strong><br><br>Controls how often the bot checks the market and on what candle sizes. The <em>Higher Timeframe (HTF)</em> gives the big-picture trend (e.g. 15-minute candles), while the <em>Lower Timeframe (LTF)</em> is used for timing entries precisely (e.g. 5-minute candles)."
    ));

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



    section.appendChild(createSectionHeader('Market Guards', 'security',
        "<strong>Market Guards</strong><br><br>Safety checks that run before any trade is placed. These include things like the PDT (Pattern Day Trader) guard, automatic position flattening at market close, and cooldown timers that prevent overtrading."
    ));
    section.appendChild(createCard('PDT Safety Guard', 'Prevent US Equity 25k rule violations', 'PDT_GUARD_ENABLED', 'toggle'));

    container.appendChild(section);
}


function renderPaperTab(container) {
    const section = document.createElement('div');
    section.className = 'settings-section';

    section.appendChild(createSectionHeader('Simulation Engine', 'history',
        "<strong>Paper & Replay Engine</strong><br><br>Control how the bot simulates trades when real execution is disabled. Replay mode allows you to fast-forward through historical data to validate strategy changes instantly."
    ));

    section.appendChild(createCard('Paper Simulator Enabled', 'Simulate PnL without placing real orders (must disable Live Trading)', 'PAPER_SIM_ENABLED', 'toggle', { default: 'true' }));
    section.appendChild(createCard('Replay Mode', 'Use historical data feed instead of live WebSocket', 'PAPER_REPLAY_MODE', 'toggle', { default: 'false' }));
    section.appendChild(createCard('Synthetic 💥 Fire Mode', 'Replay infinite algorithmic volatility instead of historical data', 'PAPER_SYNTHETIC_MODE', 'toggle', { default: 'false' }));
    section.appendChild(createCard('Sabbath Replay', 'Auto-switch to Replay data during Sabbath hours', 'SABBATH_REPLAY_MODE', 'toggle', { default: 'true' }));

    section.appendChild(createDivider());

    section.appendChild(createSectionHeader('Execution Friction', 'money_off',
        "<strong>Friction Simulation</strong><br><br>Set the artificial spread, slippage, and round-trip fees the Paper Broker will experience. Use Broker Presets to autofill realistic values."
    ));

    const presetsHtml = `
        <div style="margin-bottom: 20px; padding: 15px; background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); border-radius: 12px;">
            <div style="font-size: 11px; font-weight: 800; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 8px;">Broker Presets</div>
            <select id="paper-broker-preset" class="settings-input" style="width: 100%; color-scheme: dark; padding: 10px; background: rgba(0,0,0,0.5); border: 1px solid rgba(20,184,166,0.2); border-radius: 8px; color: #14b8a6; font-weight: 600; cursor: pointer;">
                <option value="custom">Preset Values...</option>
                <option value="oanda">OANDA (Forex)</option>
                <option value="gemini">Gemini API (Crypto)</option>
                <option value="kraken">Kraken Pro (Crypto)</option>
                <option value="coinbase">Coinbase Adv (Crypto)</option>
                <option value="ibkr_pro">IBKR Pro (Equities)</option>
            </select>
        </div>
    `;
    const presetDiv = document.createElement('div');
    presetDiv.innerHTML = presetsHtml;
    section.appendChild(presetDiv);

    section.appendChild(createCard('Round-Trip Fee (bps)', 'Broker transaction fee basis points', 'PAPER_FEE_BPS', 'input', { number: true, step: '0.1', default: '0.0' }));
    section.appendChild(createCard('Slippage per Leg (bps)', 'Expected execution slippage', 'PAPER_SLIPPAGE_BPS', 'input', { number: true, step: '0.1', default: '0.0' }));
    section.appendChild(createCard('Simulated Spread (bps)', 'Distance between bid and ask', 'PAPER_SPREAD_BPS', 'input', { number: true, step: '0.1', default: '0.0' }));

    // Wire up presets logic
    setTimeout(() => {
        const select = document.getElementById('paper-broker-preset');
        if (!select) return;
        select.addEventListener('change', (e) => {
            const presets = {
                oanda: { fee: '0.5', spread: '1.2', slip: '0.5' },
                gemini: { fee: '20.0', spread: '2.0', slip: '1.0' },
                kraken: { fee: '16.0', spread: '1.5', slip: '1.0' },
                coinbase: { fee: '30.0', spread: '2.0', slip: '1.5' },
                ibkr_pro: { fee: '5.0', spread: '1.0', slip: '0.5' }
            };
            const p = presets[e.target.value];
            if (p) {
                updateValue('PAPER_FEE_BPS', p.fee);
                updateValue('PAPER_SPREAD_BPS', p.spread);
                updateValue('PAPER_SLIPPAGE_BPS', p.slip);
                renderTab(); // Refresh UI
                showNotice('Applied Preset', 'teal');
            }
        });

        // ── Disable inputs if Live Trading is ON ──
        const isLive = String(getValue('EXECUTE_TRADES')) === 'true';
        if (isLive) {
            const paperKeys = [
                'PAPER_SIM_ENABLED', 'PAPER_REPLAY_MODE', 'PAPER_SYNTHETIC_MODE',
                'SABBATH_REPLAY_MODE', 'PAPER_FEE_BPS', 'PAPER_SLIPPAGE_BPS', 'PAPER_SPREAD_BPS'
            ];
            paperKeys.forEach(k => {
                const el = document.getElementById(`input-${k}`);
                if (el) {
                    el.disabled = true;
                    // Dim the parent card visually
                    const card = el.closest('.settings-card') || el.closest('.settings-item') || el.parentElement.parentElement;
                    if (card) card.style.opacity = '0.4';
                }
            });
            if (select) select.disabled = true;

            // Show a warning box at the top
            const warn = createWarningBox('Paper Simulator is <strong>DISABLED</strong> because <strong>Live Trading is ON</strong>.<br>Go to the Core Runtime chapter in the System tab to disable Live Execution first.');
            section.insertBefore(warn, section.childNodes[1]);
        }
    }, 50);

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
        section.appendChild(createSectionHeader('Strategy per Asset Class', 'precision_manufacturing',
            "<strong>Strategy per Asset Class</strong><br><br>Each type of market (crypto, forex, stocks, etc.) can use a different trading strategy. For example, you might use a momentum strategy for crypto but a mean-reversion strategy for forex."
        ));

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
                        ${(() => {
                    const groups = { forex: [], crypto: [], universal: [] };
                    const labels = { forex: '📈 Forex', crypto: '🪙 Crypto', universal: '🌐 Universal' };
                    Object.entries(STRATEGIES).forEach(([key, strat]) => {
                        const cls = strat.assetClass || 'universal';
                        groups[cls] = groups[cls] || [];
                        groups[cls].push([key, strat]);
                    });
                    return Object.entries(groups)
                        .filter(([, items]) => items.length > 0)
                        .map(([cls, items]) => `
                                    <optgroup label="${labels[cls] || cls}">
                                        ${items.map(([key, strat]) => `
                                            <option value="${key}" ${key === currentStrategy ? 'selected' : ''}>
                                                ${strat.name} — ${strat.shortDesc}
                                            </option>
                                        `).join('')}
                                    </optgroup>
                                `).join('');
                })()}
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

                // Auto-apply strategy preset settings
                applyStrategyPreset(newStrategy);
            });

            section.appendChild(card);
        });

    } else if (subTabs.strategy === 'toolbox') {
        // Delegate to specific toolbox renderer
        renderStrategyToolbox(container);
        return;

    } else if (subTabs.strategy === 'risk') {
        section.appendChild(createSectionHeader('Global Risk Limits', 'account_balance',
            "<strong>Global Risk Limits</strong><br><br>How much of your account you're willing to risk on each trade. These limits apply across all profiles and strategies — think of them as the guardrails that prevent any single trade from doing serious damage."
        ));

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
        section.appendChild(createSectionHeader('Position Management', 'layers',
            "<strong>Position Management</strong><br><br>Controls for how many trades the bot can hold at once across different symbols. Multi-position mode lets the bot trade multiple symbols simultaneously."
        ));

        const grid2 = document.createElement('div');
        grid2.className = 'card-grid';
        // (Moved Multi-Position and Smart Positions to Safety Tab)
        section.appendChild(grid2);
        // REMOVED: Opening Range Sentry + AI Sentiment Shield duplicates — canonical controls live in Safety tab (Audit P2)

        // Initialize Financed Risk state
        setTimeout(() => {
            const multiEnabled = getValue('MULTI_POSITION_ENABLED') === 'true';
            const smartToggle = section.querySelector('.control-card[data-key="SMART_POSITIONS_ENABLED"]');
            if (smartToggle && !multiEnabled) {
                smartToggle.classList.add('opacity-50', 'pointer-events-none');
            }
        }, 0);

    } else if (subTabs.strategy === 'pyramid') {
        section.appendChild(createSectionHeader('Pyramid Configuration', 'stacked_line_chart',
            "<strong>Pyramid Configuration</strong><br><br>Pyramiding means adding to a winning position. Instead of entering all at once, the bot can gradually add more as the trade moves in your favor. These settings control how many additional entries are allowed and what profit buffer is required before adding more."
        ));

        section.appendChild(createCard('Max Pyramid Entries', 'Total entries per position', 'MAX_PYRAMID_ENTRIES', 'input', { number: true, default: '6', min: 1, max: 20 }));
        section.appendChild(createSliderCard('Profit Buffer %', 'Min profit before first add', 'PYRAMID_PROFIT_BUFFER_PCT', 0, 5, 0.1, '%'));

        const pyramidGrid = document.createElement('div');
        pyramidGrid.className = 'card-grid';
        pyramidGrid.appendChild(createSliderCard('Load Risk', 'First add risk %', 'PYRAMID_RISK_LOAD', 5, 100, 5, '%'));
        pyramidGrid.appendChild(createSliderCard('Scale Risk', 'Subsequent adds risk %', 'PYRAMID_RISK_SCALE', 5, 50, 5, '%'));
        section.appendChild(pyramidGrid);

        // ── Conductor Pyramid & Cost Savings ──
        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('Conductor Pyramid Tuning', 'tune',
            "<strong>Conductor Pyramid Tuning</strong><br><br>These controls configure the Forex Conductor's R-milestone pyramid system. The Conductor adds to winning trades at profit milestones — the first pyramid fires at the configured R-level, with follow-up adds every 0.5R after. Adjust the trigger level and sizes to match your trading style."
        ));

        // Conductor controls that seamlessly read/write from active profile via our updateValue interceptor
        section.appendChild(createCard('Pyramid on Winners', 'Add to winning trades at profit milestones', 'conductor_pyramid_enabled', 'toggle'));
        section.appendChild(createSliderCard('Pyramid Trigger Level', 'R-multiple distance before first add', 'conductor_pyramid_start_r', 0.3, 2.0, 0.1, 'R', { default: '1.0' }));
        section.appendChild(createSliderCard('First Pyramid Size', 'Risk % of initial position size', 'conductor_pyramid_first_pct', 0.05, 0.50, 0.05, '%', { default: '30' }));

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('Breakeven Trail', 'shield',
            "<strong>Breakeven Trail</strong><br><br>Once a trade is profitable enough, the stop-loss moves up to your entry price. This means even if the market reverses, you won't lose money on that trade — you 'lock in' at breakeven."
        ));

        section.appendChild(createCard('Trail After N Pyramids', '0 = disabled', 'BREAKEVEN_TRAIL_AFTER_PYRAMIDS', 'input', { number: true, default: '1', min: 0, max: 10 }));
        // REMOVED: 'Trail Percentage' (BREAKEVEN_TRAIL_PCT) duplicate — canonical in Safety tab (Audit P2)

    } else if (subTabs.strategy === 'exits') {
        section.appendChild(createSectionHeader('Exit Configuration', 'exit_to_app',
            "<strong>Exit Configuration</strong><br><br>Rules for how the bot decides when to close a position. This includes the risk/reward ratio (e.g. risk $1 to make $2) and how it uses the ATR (Average True Range) to set stop-loss distance."
        ));

        // REMOVED: 'HTF Flip Exit (Loss Only)' (EXIT_ON_HTF_FLIP_ONLY_IF_LOSING) — Dead toggle, 0 Python refs (Audit P0)
        section.appendChild(createCard('Auto-Flatten on Close', 'Flatten positions at session end', 'AUTO_FLATTEN_ON_CLOSE', 'toggle'));

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('Trailing Stop', 'trending_down',
            "<strong>Trailing Stop</strong><br><br>A stop-loss that moves up with the price as your trade becomes more profitable. Once the profit reaches a minimum threshold, the trailing stop activates and follows the price upward — locking in profits while still giving the trade room to grow."
        ));

        section.appendChild(createCard('The "Greedy Exit"', 'Enable trailing stop logic', 'TRAILING_STOP_ENABLED', 'toggle'));
        section.appendChild(createSliderCard('The "Sniper Target"', 'Target Reward Ratio (R:R)', 'RISK_REWARD_RATIO', 1, 5, 0.5, 'R'));
        section.appendChild(createSliderCard('Trailing Stop Min Profit %', 'Min profit to activate trail', 'TRAILING_STOP_MIN_PROFIT_PCT', 0, 10, 0.5, '%'));
        // REMOVED: 'Stop ATR Multiplier' (STOP_ATR_MULTIPLIER) duplicate — canonical in Safety tab (Audit P2)

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('Hold Time Rules', 'timer',
            "<strong>Hold Time Rules</strong><br><br>How long the bot should hold a trade before considering an exit. The minimum hold prevents premature exits from short-term noise, while the maximum hold forces exits on stale positions that aren't going anywhere."
        ));

        section.appendChild(createSliderCard('Min Hold Hours', '0 = disabled', 'MIN_HOLD_HOURS', 0, 48, 1, 'hrs'));
        section.appendChild(createSliderCard('Max Hold Hours', '0 = disabled', 'MAX_HOLD_HOURS', 0, 168, 1, 'hrs'));
        section.appendChild(createSliderCard('HTF Neutral Exit Bars', 'Exit after N neutral bars', 'HTF_NEUTRAL_EXIT_BARS', 0, 200, 5, 'bars'));

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('Stop-and-Reverse', 'swap_horiz',
            "<strong>Stop-and-Reverse (The Uno Reverse Card)</strong><br><br>When a stop loss fires, the bot can immediately open a new position in the opposite direction. This captures the momentum that just stopped you out. Configurable risk, TP target, and cost-awareness."
        ));

        section.appendChild(createCard('Enable Stop-and-Reverse', 'Flip direction on stop loss hits', 'STOP_AND_REVERSE_ENABLED', 'toggle'));
        section.appendChild(createCard('Enable Counter-Reversal', 'Fire 2× trade when SAR is losing', 'COUNTER_REVERSAL_ENABLED', 'toggle'));
        section.appendChild(createCard('Keep SAR Open', 'SAR stays open alongside CR (per-strategy)', 'SAR_KEEP_OPEN', 'toggle'));
        section.appendChild(createSliderCard('Reversal TP (R-Multiple)', 'Take profit target for reversals', 'REVERSAL_TP_R', 0.5, 5.0, 0.5, 'R'));
        section.appendChild(createSliderCard('Reversal Risk %', 'Risk per reversal trade', 'REVERSAL_RISK_PER_TRADE', 0.01, 0.10, 0.005, '', { pctFormat: true }));
        section.appendChild(createCard('Cost-Aware TP', 'Add spread buffer to TP target', 'REVERSAL_COST_AWARE_TP', 'toggle'));
        section.appendChild(createSliderCard('Partial Close Fraction', 'De-risk close percentage', 'SCALE_OUT_FRACTION', 0.25, 1.0, 0.05, ''));

    } else if (subTabs.strategy === 'yaml') {
        section.appendChild(createSectionHeader('Config JSON Editor', 'code',
            "<strong>Config JSON Editor</strong><br><br>Advanced: directly view and edit the raw JSON configuration file. All the settings you see in the GUI ultimately live in this file. Power users can make bulk changes here."
        ));
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
        section.appendChild(createSectionHeader('IBKR Connection', 'lan',
            "<strong>IBKR Connection</strong><br><br>Connect to Interactive Brokers (IBKR) for executing stock, ETF, futures, and forex trades. You need TWS or IB Gateway running on the same machine or network."
        ));

        section.appendChild(createCard('Host', 'TWS/Gateway IP address', 'IBKR_HOST', 'input', { default: '127.0.0.1' }));
        section.appendChild(createCard('Port', '7497 (Paper) / 4001 (Live Gateway)', 'IBKR_PORT', 'input', { number: true, default: '7497' }));
        section.appendChild(createCard('Client ID', 'Unique connection identifier', 'IBKR_CLIENT_ID', 'input', { number: true, default: '1' }));
        section.appendChild(createCard('Account ID', 'Specific sub-account', 'IBKR_ACCOUNT_ID', 'input'));
        section.appendChild(createCard('Paper Trading', 'Use paper trading mode', 'IBKR_PAPER', 'toggle', { default: 'true' }));
        section.appendChild(createCard('Read Only', 'Monitor mode only (no orders)', 'IBKR_READ_ONLY', 'toggle'));
        section.appendChild(createCard('Default Currency', 'Base currency for positions', 'IBKR_DEFAULT_CCY', 'dropdown', { items: [{ value: 'USD', label: 'USD' }, { value: 'EUR', label: 'EUR' }, { value: 'GBP', label: 'GBP' }, { value: 'CHF', label: 'CHF' }, { value: 'JPY', label: 'JPY' }, { value: 'CAD', label: 'CAD' }, { value: 'AUD', label: 'AUD' }, { value: 'NZD', label: 'NZD' }], default: 'USD' }));

    } else if (subTabs.brokers === 'oanda') {
        section.appendChild(createSectionHeader('OANDA Forex Connection', 'currency_exchange',
            "<strong>OANDA Forex Connection</strong><br><br>Connect to OANDA for forex (currency pair) trading. OANDA provides tight spreads and fractional position sizing. Enter your API key and account ID from your OANDA account dashboard."
        ));

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

        // ── OANDA Cost Savings ──
        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('Cost Savings', 'savings',
            "<strong>Cost Savings</strong><br><br>OANDA-specific settings to reduce trading costs. The spread gate blocks entries when spreads are too wide, and swap avoidance closes marginal trades before OANDA's Wednesday 3× swap charge."
        ));

        // OANDA controls that seamlessly read/write from active profile via our updateValue interceptor
        section.appendChild(createSliderCard('Max Spread (% of SL)', 'Blocks entries if spread is too wide', 'spread_gate_max_pct', 0.10, 0.50, 0.05, '%', { default: '30' }));
        section.appendChild(createCard('Wed Swap Avoidance', 'Closes marginal trades before 5PM Wed swap charge', 'swap_avoidance_enabled', 'toggle'));

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('OANDA Info', 'info',
            "<strong>OANDA Account Info</strong><br><br>Displays your OANDA account balance, open trades, and connection status. This data refreshes automatically when the bot is running."
        ));

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
        section.appendChild(createSectionHeader('Gemini.com Connection', 'security',
            "<strong>Gemini Connection</strong><br><br>Connect to the Gemini crypto exchange for trading Bitcoin, Ethereum, and other cryptocurrencies. You'll need an API key and secret from your Gemini account settings."
        ));

        section.appendChild(createCard('API Key', 'Gemini Master Key', 'GEMINI_API_KEY', 'input', { password: true }));
        section.appendChild(createCard('API Secret', 'Gemini Secret', 'GEMINI_API_SECRET', 'input', { password: true }));
        section.appendChild(createCard('Sandbox Mode', 'Use Gemini Exchange Testnet', 'GEMINI_SANDBOX', 'toggle', { default: 'false' }));

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('Gemini Info', 'info',
            "<strong>Gemini Account Info</strong><br><br>Your Gemini exchange account status, available balance, and connection health."
        ));

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
        section.appendChild(createSectionHeader('Kraken Connection', 'account_balance_wallet',
            "<strong>Kraken Connection</strong><br><br>Connect to the Kraken crypto exchange. Kraken supports advanced order types and a wide range of crypto pairs."
        ));

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
        section.appendChild(createSectionHeader('Kraken Info', 'info',
            "<strong>Kraken Account Info</strong><br><br>Your Kraken exchange account status and connection health."
        ));
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
        section.appendChild(createSectionHeader('Paxos / itBit Connection', 'token',
            "<strong>Paxos / itBit Connection</strong><br><br>Connect to the Paxos (itBit) crypto exchange. This is a regulated US exchange often used for institutional-grade trading."
        ));

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
        section.appendChild(createSectionHeader('Paxos Info', 'info',
            "<strong>Paxos Account Info</strong><br><br>Your Paxos exchange connection status and account details."
        ));
        section.appendChild(createWarningBox('<strong>Note:</strong> Used for direct Crypto Spot trading. Ensure "Data Routing" is set to use Paxos for Crypto.'));

    } else if (subTabs.brokers === 'ccxt') {
        section.appendChild(createSectionHeader('Coinbase / CCXT Engine', 'currency_bitcoin',
            "<strong>Coinbase / CCXT Engine</strong><br><br>Connect to Coinbase (or any CCXT-supported exchange) for crypto trading. CCXT is a universal adapter that supports 100+ crypto exchanges with a single configuration."
        ));

        section.appendChild(createCard('Exchange ID', 'Provider name', 'CCXT_EXCHANGE', 'dropdown', { items: [{ value: 'coinbase', label: 'Coinbase' }, { value: 'kraken', label: 'Kraken' }, { value: 'binance', label: 'Binance' }, { value: 'binanceus', label: 'Binance US' }, { value: 'bybit', label: 'Bybit' }, { value: 'okx', label: 'OKX' }, { value: 'bitfinex', label: 'Bitfinex' }, { value: 'gemini', label: 'Gemini' }, { value: 'kucoin', label: 'KuCoin' }], default: 'coinbase' }));
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
        section.appendChild(createSectionHeader('Crypto Order Settings', 'paid',
            "<strong>Crypto Order Settings</strong><br><br>Controls for how crypto orders are placed — including maker-first mode (limit orders for lower fees), slippage tolerance, and order timeouts. Fine-tune these to balance execution speed vs. cost."
        ));

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
        section.appendChild(createSectionHeader('Data & Execution Routing', 'route',
            "<strong>Data & Execution Routing</strong><br><br>Choose which broker provides market data and which one executes trades. In hybrid mode, you can get data from one source and execute on another."
        ));

        section.appendChild(createSectionHeader('Asset-Based Routing', 'route',
            "<strong>Asset-Based Routing</strong><br><br>Route different asset classes to different brokers automatically. For example, send forex orders to OANDA but crypto orders to Gemini — all from the same bot."
        ));

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

    section.appendChild(createSectionHeader('AI Provider', 'smart_toy',
        "<strong>AI Provider</strong><br><br>Configure the AI model that powers the bot's analysis commentary. This is the AI that writes market insights on the dashboard — it does NOT make trading decisions (the strategy engine does that)."
    ));

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
    section.appendChild(createSliderCard('Temperature', 'AI creativity (0 = precise, 2 = wild)', 'AI_TEMPERATURE', 0, 2, 0.1, ''));
    section.appendChild(createCard('Max Tokens', 'Response length limit', 'AI_MAX_TOKENS', 'input', { number: true, default: '2048' }));

    section.appendChild(createDivider());
    section.appendChild(createSectionHeader('AI Commentary', 'comment',
        "<strong>AI Commentary</strong><br><br>Settings for the AI-generated market analysis that appears on the dashboard. You can control how often it updates and what template it uses to generate insights."
    ));

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

    section.appendChild(createSectionHeader('Sabbath Configuration', 'synagogue',
        "<strong>Sabbath Configuration</strong><br><br>When enabled, the bot automatically stops placing real trades from Friday sundown to Saturday sundown. During this time it switches to a simulated Paper Broker so no real money is at risk. You can set your location for accurate sunset times."
    ));

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
    section.appendChild(createCard('Timezone', 'IANA zone name', 'SABBATH_TIMEZONE', 'dropdown', { items: [{ value: 'America/New_York', label: 'America/New_York' }, { value: 'America/Chicago', label: 'America/Chicago' }, { value: 'America/Denver', label: 'America/Denver' }, { value: 'America/Los_Angeles', label: 'America/Los_Angeles' }, { value: 'America/Toronto', label: 'America/Toronto' }, { value: 'Europe/London', label: 'Europe/London' }, { value: 'Europe/Paris', label: 'Europe/Paris' }, { value: 'Europe/Berlin', label: 'Europe/Berlin' }, { value: 'Asia/Jerusalem', label: 'Asia/Jerusalem' }, { value: 'Asia/Tokyo', label: 'Asia/Tokyo' }, { value: 'Australia/Sydney', label: 'Australia/Sydney' }, { value: 'UTC', label: 'UTC' }], default: 'America/New_York' }));
    section.appendChild(createCard('Latitude', 'Decimal coordinate', 'SABBATH_LAT', 'input'));
    section.appendChild(createCard('Longitude', 'Decimal coordinate', 'SABBATH_LON', 'input'));
    section.appendChild(createCard('Start Time', 'Friday sunset - HH:MM', 'SABBATH_START_LOCAL', 'time', { default: '18:00' }));
    section.appendChild(createCard('End Time', 'Saturday sunset - HH:MM', 'SABBATH_END_LOCAL', 'time', { default: '18:00' }));

    section.appendChild(createDivider());
    section.appendChild(createSectionHeader('Session Gate', 'access_time',
        "<strong>Session Gate</strong><br><br>Restricts trading to specific market session hours. This prevents the bot from trading during low-liquidity periods (like overnight or between sessions) when spreads are wide and moves can be unpredictable."
    ));

    section.appendChild(createCard('Session Gate Enabled', 'Enforce session health checks', 'SESSION_GATE_ENABLED', 'toggle', { default: 'true' }));
    section.appendChild(createCard('Overlap Start Hour', 'Active session start', 'SESSION_OVERLAP_START_HOUR', 'time', { default: '12:00' }));
    section.appendChild(createCard('Overlap End Hour', 'Active session end', 'SESSION_OVERLAP_END_HOUR', 'time', { default: '16:00' }));
    section.appendChild(createCard('Session Timezone', 'For overlap hours', 'SESSION_OVERLAP_TIMEZONE', 'dropdown', { items: [{ value: 'UTC', label: 'UTC' }, { value: 'America/New_York', label: 'America/New_York' }, { value: 'America/Chicago', label: 'America/Chicago' }, { value: 'America/Denver', label: 'America/Denver' }, { value: 'America/Los_Angeles', label: 'America/Los_Angeles' }, { value: 'Europe/London', label: 'Europe/London' }, { value: 'Europe/Paris', label: 'Europe/Paris' }, { value: 'Asia/Tokyo', label: 'Asia/Tokyo' }, { value: 'Asia/Shanghai', label: 'Asia/Shanghai' }], default: 'UTC' }));
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
    section.appendChild(createSectionHeader('Theme', 'palette',
        "<strong>Theme</strong><br><br>Customize the look and feel of the dashboard. Choose from multiple color themes to match your preference."
    ));

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

// ═══════════════════════════════════════════════════════════
// TREND DETECTION TAB
// ═══════════════════════════════════════════════════════════
function renderTrendsTab(container) {
    const section = document.createElement('div');
    section.className = 'settings-section';

    // ── Intro blurb ────────────────────────────────────────
    const intro = document.createElement('div');
    intro.className = 'text-xs text-slate-400 leading-relaxed mb-4 px-1';
    intro.innerHTML = `Choose which trend detection indicators the bot uses when evaluating trade setups. 
        Each indicator has strengths and blind spots — hover over the <span class="material-symbols-outlined text-xs align-middle text-teal-400">info</span> icon for a full breakdown. 
        Enabled indicators contribute to the bot's trend-reading confidence score.`;
    section.appendChild(intro);

    // ── Trend Strength ────────────────────────────────────
    section.appendChild(createSectionHeader('Trend Strength', 'signal_cellular_alt',
        "<strong>What is Trend Strength?</strong><br><br>These indicators measure <em>how strong</em> the current trend is — like a speedometer. They don't tell you which way the market is heading, just whether it's moving with conviction or sitting still.<br><br>When trend strength is low, the bot avoids trading because there's no clear direction to follow."
    ));
    section.appendChild(createCard('ADX — Trend Strength Gate', 'Blocks entries when market has no clear trend (ADX < threshold)', 'TREND_ADX_ENABLED', 'toggle', { default: 'true' }));
    section.appendChild(createSliderCard('ADX Threshold', 'Entries blocked below this ADX value (0 = disabled)', 'TREND_ADX_THRESHOLD', 0, 60, 1, ''));

    section.appendChild(createDivider());

    // ── Momentum Indicators ───────────────────────────────
    section.appendChild(createSectionHeader('Momentum', 'speed',
        "<strong>What are Momentum Indicators?</strong><br><br>Momentum indicators measure how fast the price is moving and in which direction. Think of it like the engine under a trend — even if the 'direction' is unclear, momentum tells you which side has more energy right now.<br><br><span style='color:#818cf8'>💡 Tip:</span> You can enable both RSI and MACD — when they agree, the signal is stronger. When they disagree, the bot stays cautious."
    ));
    section.appendChild(createCard('RSI — Relative Strength Index', 'Detects overbought/oversold conditions (14-period)', 'TREND_RSI_ENABLED', 'toggle', { default: 'false' }));
    section.appendChild(createCard('MACD — Momentum Crossover', 'Catches momentum shifts via EMA crossovers (12/26/9)', 'TREND_MACD_ENABLED', 'toggle', { default: 'false' }));

    section.appendChild(createDivider());

    // ── Volatility ────────────────────────────────────────
    section.appendChild(createSectionHeader('Volatility', 'expand',
        "<strong>What are Volatility Indicators?</strong><br><br>Volatility measures how wildly the price is swinging. High volatility means big moves (up or down). Low volatility (a 'squeeze') means the market is quiet — but a big move is usually about to happen.<br><br>The bot uses volatility to adjust its confidence. During a squeeze, nobody knows which way the breakout will go, so the bot lowers its conviction."
    ));
    section.appendChild(createCard('Bollinger Bands — Squeeze Detection', 'Identifies low-volatility squeezes before breakouts (20-period, 2σ)', 'TREND_BOLLINGER_ENABLED', 'toggle', { default: 'false' }));

    section.appendChild(createDivider());

    // ── Direction Detection ───────────────────────────────
    section.appendChild(createSectionHeader('Direction Detection', 'swap_vert',
        "<strong>What are Direction Detectors?</strong><br><br>These are the most important indicators — they tell the bot <em>which way</em> to trade (up or down). Each one uses a different method to read the market, and each has blind spots.<br><br><span style='color:#818cf8'>💡 Why enable multiple?</span> No single indicator is right all the time. When you enable multiple direction detectors, they <strong>vote</strong> together. The bot only commits to a direction when the majority agree — this filters out false signals that any one indicator would produce alone. Think of it like asking 3 different experts instead of trusting just one."
    ));
    section.appendChild(createCard('Supertrend — Trend-Following Direction', 'Always gives a clear UP or DOWN signal using price volatility. Like a compass that always points somewhere.', 'TREND_SUPERTREND_ENABLED', 'toggle', { default: 'false' }));
    section.appendChild(createCard('EMA Ribbon — Structural Alignment', 'Three trend lines that show whether short, medium, and long-term trends all agree on direction.', 'TREND_EMA_RIBBON_ENABLED', 'toggle', { default: 'false' }));
    section.appendChild(createCard('Ichimoku Cloud — Complete Trend Picture', 'A \'cloud\' on the chart — price above it means uptrend, below means downtrend, inside means undecided.', 'TREND_ICHIMOKU_ENABLED', 'toggle', { default: 'false' }));
    section.appendChild(createCard('Parabolic SAR — Reversal Detector', 'Dots that flip above/below price when the trend changes direction. Great for catching trend reversals.', 'TREND_PARABOLIC_SAR_ENABLED', 'toggle', { default: 'false' }));
    section.appendChild(createCard('Hull Moving Average — Fast Trend Line', 'A moving average that reacts quickly to price changes with minimal lag. Rising = uptrend, falling = downtrend.', 'TREND_HULL_MA_ENABLED', 'toggle', { default: 'false' }));

    section.appendChild(createDivider());

    // ── Volume-Weighted ─────────────────────────────────
    section.appendChild(createSectionHeader('Volume-Weighted', 'bar_chart',
        "<strong>What are Volume-Weighted Indicators?</strong><br><br>Volume tells you <em>how many people</em> are trading, not just the price. VWAP combines price with volume to show the 'fair price' — the price where the most trading activity happened.<br><br>Big institutional traders (banks, hedge funds) use VWAP as their reference point. When the price is above VWAP, buyers are in control. Below VWAP, sellers are winning."
    ));
    section.appendChild(createCard('VWAP — Fair Value Reference', 'The average price weighted by trading volume. Used by big institutional traders to judge if the market is fairly priced.', 'TREND_VWAP_ENABLED', 'toggle', { default: 'false' }));

    container.appendChild(section);
}

function renderAdvancedTab(container, filter = "") {
    const section = document.createElement('div');
    section.className = 'settings-section';

    section.appendChild(createSectionHeader('All Environment Variables', 'terminal',
        "<strong>All Environment Variables</strong><br><br>Advanced: a raw view of every environment variable the bot reads. These are the underlying settings that power everything. Most users won't need to touch these directly."
    ));

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

    section.appendChild(createSectionHeader('Position Protection', 'layers',
        "<strong>Position Protection</strong><br><br>Software-based stop-losses that protect your open positions even when the broker doesn't support native stops (like most crypto exchanges). These 'synthetic stops' are monitored by the bot and trigger market sells when hit."
    ));
    section.appendChild(createCard('Multi-Position', 'Trade multiple symbols simultaneously', 'MULTI_POSITION_ENABLED', 'toggle'));
    section.appendChild(createSliderCard('Max Concurrent Positions', 'Maximum open positions', 'MAX_CONCURRENT_POSITIONS', 1, 10, 1, ''));
    section.appendChild(createCard('Smart Positions', 'Fund new risk with open profits', 'SMART_POSITIONS_ENABLED', 'toggle'));

    section.appendChild(createDivider());
    section.appendChild(createSectionHeader('Account Safety & Shields', 'shield',
        "<strong>Account Safety & Shields</strong><br><br>Master safety switches that protect your entire account. These include maximum drawdown limits, equity circuit breakers, and loss caps that automatically shut down trading if things go wrong."
    ));

    section.appendChild(createCard('Stability Mode', 'Ultra-safe risk management & quality filters (1% Cap)', 'SAFETY_STABILITY_MODE_ENABLED', 'toggle', {
        tooltip: "<strong>Survival First.</strong> This is your emergency brake. It forces 1% max risk and a 75+ quality score floor. Perfect for preventing account 'bleeding' during choppy or unpredictable market regimes."
    }));
    section.appendChild(createCard('ATR Armor', 'Profit Protection via Break-even & Trailing stops', 'SAFETY_ATR_SHIELD_ENABLED', 'toggle', { default: 'true' }));
    section.appendChild(createSliderCard('Stop ATR Multiplier', 'Standard stop distance (× ATR)', 'STOP_ATR_MULTIPLIER', 0.5, 5, 0.1, '×'));
    section.appendChild(createSliderCard('The "Lock-In"', 'Lock Risk-Free at this profit level', 'BREAKEVEN_TRAIL_PCT', 0, 5, 0.1, '%'));
    section.appendChild(createCard('Drawdown Breaker', 'Account Circuit Breaker — Adaptive (25% small → 5% large accounts)', 'SAFETY_DRAWDOWN_BREAKER_ENABLED', 'toggle', { default: 'true' }));
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
    section.appendChild(createSliderCard('Churn Burner Max', 'Maximum trades allowed per hour', 'SAFETY_CHURN_BURNER_MAX', 1, 20, 1, 'trades/hr'));

    section.appendChild(createCard('Leverage Sentry', 'Block entries above leverage cap', 'SAFETY_LEVERAGE_SENTRY_ENABLED', 'toggle', { default: 'true' }));
    section.appendChild(createSliderCard('Max Leverage', 'Maximum total leverage allowed', 'SAFETY_MAX_TOTAL_LEVERAGE', 1, 50, 1, 'x'));

    section.appendChild(createCard('Volatility Veto', 'Block entries if ATR is too Low/High', 'SAFETY_VOLATILITY_VETO_ENABLED', 'toggle'));
    section.appendChild(createSliderCard('Veto Min ATR %', 'Block if volatility falls below this', 'SAFETY_VOLATILITY_MIN_PCT', 0, 100, 1, '%'));
    section.appendChild(createSliderCard('Veto Max ATR %', 'Block if volatility exceeds this', 'SAFETY_VOLATILITY_MAX_PCT', 0, 100, 1, '%'));
    section.appendChild(createCard('Streak Breaker', 'Pause Symbol 4h after 3 Consecutive Losses', 'SAFETY_STREAK_BREAKER_ENABLED', 'toggle', { default: 'true' }));
    section.appendChild(createCard('Opening Range Sentry', 'Avoid first 15 mins (9:30-9:45 ET)', 'SAFETY_OPENING_SENTRY_ENABLED', 'toggle', { default: 'true' }));
    section.appendChild(createCard('AI Sentiment Shield', 'Smart Veto. AI blocks "Dangerous" setups.', 'SAFETY_SENTIMENT_SHIELD_ENABLED', 'toggle'));

    section.appendChild(createDivider());
    section.appendChild(createSectionHeader('Advanced Exit Shields', 'cancel_schedule',
        "<strong>Advanced Exit Shields</strong><br><br>Intelligent exit protections that go beyond simple stop-losses. These include ATR Armor (volatility-adjusted stops), Stability Mode (blocks trades during wild market swings), and the Drawdown Breaker (emergency kill switch)."
    ));

    section.appendChild(createCard('Stale Sniper', 'Terminate trades after N bars of no progress', 'SAFETY_STALE_SNIPER_ENABLED', 'toggle'));
    section.appendChild(createSliderCard('Sniper Bars', 'Maximum bars to hold a trade', 'SAFETY_STALE_SNIPER_BARS', 5, 100, 5, 'bars'));
    section.appendChild(createCard('Flash-Trap Shield', 'Exit instantly on extreme ATR spikes', 'SAFETY_FLASH_TRAP_ENABLED', 'toggle'));
    section.appendChild(createCard('Regime-Flip Veto', 'Exit if HTF trend turns against position', 'SAFETY_REGIME_FLIP_ENABLED', 'toggle'));
    section.appendChild(createCard('Counter-Trend Block', 'Block entries against HTF trend direction', 'BLOCK_COUNTER_TREND_ENTRIES', 'toggle', { default: 'true' }));

    section.appendChild(createDivider());
    section.appendChild(createSectionHeader('☢️ NUCLEAR OVERRIDES', 'emergency_home',
        "<strong>☢️ Nuclear Overrides</strong><br><br><strong>DANGER ZONE.</strong> These switches override all other safety logic. Use only in emergencies — like force-closing all positions or bypassing all risk checks. Think of these as the 'break glass in case of fire' controls."
    ));

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
    section.appendChild(createSliderCard('Risk Cap Override %', 'New hard risk wall', 'MAX_RISK_CAP_OVERRIDE', 0, 50, 1, '%'));
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
    section.appendChild(createSectionHeader('Safety Metrics (Live Feed)', 'query_stats',
        "<strong>Safety Metrics (Live Feed)</strong><br><br>Real-time readout of the bot's current safety status — equity levels, drawdown percentage, active shields, and circuit breaker status. Refreshes automatically while the bot is running."
    ));

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
                <span class="text-teal-300">Adaptive (auto-scaled by account size)</span>
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

    section.appendChild(createSectionHeader('Performance & Profits', 'trending_up',
        "<strong>Performance & Profits</strong><br><br>Controls how the bot calculates and reports performance — including fee handling, cost-basis methods, and PnL calculation. Properly configured, this ensures your reported numbers match reality."
    ));
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
    section.appendChild(createSectionHeader('Wealth Weapons (Advanced Exits)', 'rocket_launch',
        "<strong>Wealth Weapons (Advanced Exits)</strong><br><br>Premium exit strategies designed to maximize profits on winning trades. These include partial profit-taking at milestones, aggressive trailing stops, and momentum-based exit timing."
    ));

    section.appendChild(createCard('Gamma Squeeze Trail', 'Exponentially tighter trail on vertical moves', 'WEALTH_EXIT_GAMMA_ENABLED', 'toggle'));
    section.appendChild(createCard('Moonshot Elevator', 'Double target if 1R is hit in <3 bars', 'WEALTH_EXIT_MOONSHOT_ENABLED', 'toggle'));
    section.appendChild(createCard('Blow-off Seller', 'Sell peak on volatility exhaustion', 'WEALTH_EXIT_BLOWOFF_ENABLED', 'toggle'));

    section.appendChild(createDivider());

    // 3. P&L REWARDS & RETENTION (NEW)
    const pnlGroup = document.createElement('div');
    pnlGroup.innerHTML = `<div class="text-sm text-slate-400 mb-2 font-bold uppercase tracking-wider">Step 3: P&L Rewards & Retention (Targets & Limits)</div>`;
    section.appendChild(pnlGroup);

    section.appendChild(createSliderCard('Daily Profit Target %', 'Stop for the day once reached (0 = disabled)', 'TARGET_PROFIT_DAILY_PCT', 0, 10, 0.5, '%'));
    // Daily Loss Limit slider is in Strategy Workshop → Global Risk tab

    // REMOVED: 4 dead placeholders — WEEKLY/MONTHLY profit/loss targets not implemented (Audit P10)

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


function updateValue(key, value, strategyNamespace = null) {
    const oldValue = getValue(key, strategyNamespace);
    if (oldValue === value) return;

    // ── INTERCEPT PROFILE-LEVEL SETTINGS ──
    const profileKeys = ['conductor_pyramid_enabled', 'swap_avoidance_enabled', 'conductor_pyramid_start_r', 'conductor_pyramid_first_pct', 'spread_gate_max_pct'];
    if (profileKeys.includes(key)) {
        const activeName = configData.active_profile;
        if (window.profilesModule?.allProfiles && activeName) {
            window.profilesModule.allProfiles[activeName][key] = (value === 'true' || value === true) ? true : (value === 'false' || value === false) ? false : parseFloat(value);
            if (window.profilesModule._saveProfile) window.profilesModule._saveProfile();
        }
        return; // Skip global config.json save
    }

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

        // Sync STRATEGY_* to active profile's nested strategies object
        const stratKeyMatch = key.match(/^STRATEGY_(CRYPTO|FOREX|STOCKS|ETF|METALS|FUTURES)$/);
        if (stratKeyMatch) {
            const assetClass = stratKeyMatch[1].toLowerCase();
            const active = configData.active_profile;
            if (active && configData.profiles && configData.profiles[active]) {
                if (!configData.profiles[active].strategies) configData.profiles[active].strategies = {};
                configData.profiles[active].strategies[assetClass] = val;
            }
        }

        // Sync PnL timeframe back to renderer.js if changed
        if (key === 'GUI_PNL_TIMEFRAME' && typeof window.syncPnLTimeframe === 'function') {
            window.syncPnLTimeframe(value);
        }

        // [BUGFIX] If the active profile currently overrides this global setting, update the override too
        const active = configData.active_profile;
        if (active && configData.profiles && configData.profiles[active]) {
            if (configData.profiles[active][key.toLowerCase()] !== undefined) {
                configData.profiles[active][key.toLowerCase()] = val;
            }
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

            if (strategyNamespace) {
                if (!configData.profiles[active].strategy_overrides) configData.profiles[active].strategy_overrides = {};
                if (!configData.profiles[active].strategy_overrides[strategyNamespace]) configData.profiles[active].strategy_overrides[strategyNamespace] = {};
                configData.profiles[active].strategy_overrides[strategyNamespace][key.toLowerCase()] = val;
            } else {
                configData.profiles[active][key.toLowerCase()] = val;
            }
        }
    }

    localChanges[key] = true;
    if (!strategyNamespace) {
        envData[key] = String(value); // Keep flat map in sync for global values
    }

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
    currentStrategyContext = toolboxTab;
    // Strategy selector using a responsive grid layout
    const nav = document.createElement('div');
    nav.className = 'strategy-selector-grid';
    const isLightGrid = document.documentElement.getAttribute('data-theme') === 'light';
    nav.style.cssText = `
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
        gap: 10px;
        margin-bottom: 32px;
        padding: 16px;
        background: ${isLightGrid ? '#f0f9ff' : 'rgba(0, 0, 0, 0.3)'};
        border-radius: 16px;
        border: 1px solid ${isLightGrid ? '#bae6fd' : 'rgba(255, 255, 255, 0.05)'};
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
        { id: 'forex_conductor', label: 'Forex Conductor', icon: 'route', color: '#f59e0b' },
        { id: 'trend_rider', label: 'Trend Rider', icon: 'trending_up', color: '#10b981' },
        { id: 'session_momentum', label: 'Session Momentum', icon: 'schedule_send', color: '#f43f5e' },
        { id: 'bearish_engulfing', label: 'Engulfing Reversal', icon: 'candlestick_chart', color: '#d946ef' },
        // 🪙 Crypto-Specific Strategies
        { id: 'crypto_rsi_macd', label: 'RSI + MACD', icon: 'currency_bitcoin', color: '#f59e0b' },
        { id: 'crypto_vwap_reversion', label: 'VWAP Reversion', icon: 'swap_horiz', color: '#84cc16' },
        { id: 'crypto_double_macd', label: 'Double MACD', icon: 'speed', color: '#fb923c' },
        { id: 'crypto_grid', label: 'Virtual Grid', icon: 'grid_on', color: '#a78bfa' }
    ];

    const isLight = document.documentElement.getAttribute('data-theme') === 'light';

    strategies.forEach(s => {
        const btn = document.createElement('button');
        const isActive = toolboxTab === s.id;

        // Theme-aware colors
        const inactiveBg = isLight ? '#ffffff' : 'rgba(255,255,255,0.03)';
        const inactiveBorder = isLight ? '#bae6fd' : 'rgba(255,255,255,0.08)';
        const inactiveColor = isLight ? '#334155' : '#94a3b8';
        const hoverBg = isLight ? '#e0f2fe' : 'rgba(255,255,255,0.08)';
        const hoverBorder = isLight ? '#7dd3fc' : 'rgba(255,255,255,0.15)';
        const hoverColor = isLight ? '#0f172a' : '#e2e8f0';

        btn.style.cssText = `
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 8px;
            padding: 16px 12px;
            border-radius: 12px;
            border: 1px solid ${isActive ? s.color + '60' : inactiveBorder};
            background: ${isActive ? s.color + '20' : inactiveBg};
            color: ${isActive ? s.color : inactiveColor};
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
                btn.style.background = hoverBg;
                btn.style.borderColor = hoverBorder;
                btn.style.color = hoverColor;
            }
        };
        btn.onmouseleave = () => {
            if (!isActive) {
                btn.style.background = inactiveBg;
                btn.style.borderColor = inactiveBorder;
                btn.style.color = inactiveColor;
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
        section.appendChild(createSectionHeader('ICC Core Logic', 'auto_mode',
            "<strong>ICC Core Logic</strong><br><br>The ICC (Indication, Correction, Continuation) system automatically enters trades when it detects the classic three-phase pattern: a strong move (indication), a pullback (correction), and a resumption (continuation). These settings control whether it can auto-trade and how aggressive it is."
        ));

        section.appendChild(createCard('ICC Auto-Entry', 'Auto-enter on valid signals', 'ICC_AUTO_ENTRY_ENABLED', 'toggle', { default: 'true' }));
        section.appendChild(createCard('Aggressive Mode', 'Enable aggressive sizing', 'ICC_AGGRESSIVE_MODE', 'toggle', { default: 'true' }));
        section.appendChild(createCard('Require Sweep', 'Must have liquidity sweep', 'ICC_AUTO_ENTRY_REQUIRE_SWEEP', 'toggle'));
        section.appendChild(createSliderCard('Min HTF Strength', 'Minimum trend strength', 'ICC_AUTO_ENTRY_MIN_HTF_STRENGTH', 0, 100, 5, '%'));
        section.appendChild(createSliderCard('Confirmation Bars', 'Bars to confirm signal', 'ICC_CONFIRMATION_BARS', 1, 5, 1, 'bars'));

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('ICC Scoring Weights', 'leaderboard',
            "<strong>ICC Scoring Weights</strong><br><br>How many points each signal component contributes to the overall ICC score. Higher scores mean more conviction. The entry threshold determines the minimum score needed before the bot places a trade."
        ));

        section.appendChild(createSliderCard('Entry Score Threshold', 'Minimum score for entry', 'ICC_ENTRY_SCORE_THRESHOLD', 0, 100, 5, 'pts'));

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

        section.appendChild(createCard('Session Start', 'Range start time (ET)', 'ORB_START_TIME', 'time', {
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

    } else if (toolboxTab === 'icc_legacy_dead') {
        // REMOVED: Dead ICC duplicate block — same condition already handled at line 2615 (Audit P2)
        // The original ICC tab with scoring weights is the canonical one.

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

        section.appendChild(createCard('Combat Mode', 'Bypass RoboCop HTF/Score gates only', 'COMBAT_MODE_ENABLED', 'toggle', {
            tooltip: 'If enabled, RoboCop ignores its own "HTF Strength" and "Score Threshold" gates. It will take every valid liquidity sweep or continuation signal regardless of broader context. <strong>Note:</strong> This does NOT bypass global Safety Guards (Drawdown Breaker, Session Lockout, etc.) — only RoboCop-specific entry filters.'
        }));

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('Aggressive Targets', 'gps_fixed'));

        section.appendChild(createCard('Confirmation Bars', 'Bars to wait', 'CONFIRMATION_BARS', 'input', {
            number: true,
            default: '1',
            min: 1, limit: 3,
            tooltip: 'How many candles to wait after a signal before entering. RoboCop defaults to 1 for speed. Increasing this adds safety but may miss fast moves.'
        }));
        section.appendChild(createCard('Target Multiplier', 'R-multiple', 'TARGET_R', 'input', {
            number: true,
            default: '3.0',
            tooltip: 'Multiplies the ATR (volatility) to set the Take Profit level. 3.0 means targeting a move 3x the average volatility size.'
        }));
        section.appendChild(createCard('Stop ATR Buffer', 'Protection width buffer', 'STOP_ATR_BUFFER', 'input', {
            number: true,
            default: '0.2',
            tooltip: 'A tiny buffer added beyond the structural swing stop level using the ATR (Average True Range).'
        }));
        section.appendChild(createCard('Guillotine Cut %', 'Scale-out fraction when losing', 'GUILLOTINE_CUT_PCT', 'input', {
            number: true,
            default: '0.80',
            tooltip: 'The percentage of the stop loss distance reached before the Guillotine cuts 95% of the position to preserve capital.'
        }));
        section.appendChild(createCard('Chandelier Multiplier', 'Trailing stop volatility multiplier', 'CHANDELIER_MULT', 'input', {
            number: true,
            default: '2.0',
            tooltip: 'Multiplies the ATR to set the trailing stop distance once the trade enters profit.'
        }));

    } else if (toolboxTab === 'evolution') {
        const stratInfo = STRATEGIES.evolution;
        section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'smart_toy'));

        section.appendChild(createCard('Target Risk:Reward', 'R-Multiple', 'TARGET_R', 'input', {
            number: true,
            default: '2.0',
            tooltip: 'The fixed Reward-to-Risk ratio. A value of 2.0 means the bot calculates position size such that the Profit Target is 2x the distance of the Stop Loss.'
        }));
        section.appendChild(createCard('Stop ATR Mult', 'Volatility based stop', 'STOP_ATR_MULT', 'input', {
            number: true,
            default: '1.0',
            tooltip: 'Sets the stop loss distance based on market volatility (ATR). 1.0 is standard for this strategy to survive random noise while chopping.'
        }));
        section.appendChild(createCard('Chandelier Trail Multiplier', 'Trailing stop volatility multiplier', 'CHANDELIER_MULT', 'input', {
            number: true,
            default: '2.0',
            tooltip: 'Multiplies the ATR to set the trailing stop distance once the trade enters profit.'
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

    } else if (toolboxTab === 'forex_conductor') {
        const stratInfo = STRATEGIES.forex_conductor;
        section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'orchestration',
            "<strong>Forex Conductor</strong><br><br>The Conductor orchestrates sub-strategies (Trend Rider, Mean Reversion) and manages entries, exits, and risk. SAR (Stop And Reverse) automatically flips direction after a losing trade when conditions support a reversal — preventing consecutive losses in the same direction."
        ));

        section.appendChild(createCard('Base Risk %', `Specific risk for ${stratInfo.name}`, 'RISK_PER_TRADE_PCT', 'input', {
            number: true,
            placeholder: 'Default',
            tooltip: `Define the specific risk percentage for ${stratInfo.name}. This overrides the global "Default Risk %" setting.`
        }));

        section.appendChild(createCard('Stop & Reverse (SAR)', 'Auto-flip direction after a stopped trade', 'STOP_AND_REVERSE_ENABLED', 'toggle', {
            default: 'true',
            tooltip: '<strong>Stop And Reverse.</strong><br><br>When enabled, after a trade is stopped out, the Conductor checks if conditions support a trade in the opposite direction. If yes, it immediately enters the reversal — bypassing cooldowns. This prevents 3 consecutive shorts on GBPUSD when the pair is actually going long.<br><br><strong>Recommended: ON.</strong> This is the Conductor\'s cornerstone defense against trending losses.'
        }));

        section.appendChild(createCard('Scale-Out Fraction', 'Partial close % on de-risk signal', 'SCALE_OUT_FRACTION', 'input', {
            number: true,
            default: '0.95',
            tooltip: 'When the Conductor fires a de-risk signal, this is the fraction to close. 0.95 = close 95%, keep 5% as a runner.'
        }));

        section.appendChild(createCard('R:R Ratio', 'Reward-to-Risk target', 'RISK_REWARD_RATIO', 'input', {
            number: true,
            default: '2.0',
            tooltip: 'The target Reward-to-Risk ratio for the Conductor\'s entries.'
        }));

        section.appendChild(createCard('Quick Ranging TP', 'Cap profits at 0.7R during choppy/ranging sessions', 'QUICK_RANGING_TP_ENABLED', 'toggle', {
            default: 'false',
            tooltip: 'When the market is consolidating (ranging), Conductor tries to capture ping-pong oscillation peaks by forcing a 0.7R profit target. Disable this to let profitable trades run beyond 1R and capture sudden breakouts.'
        }));

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('Reversal (SAR) Settings', 'swap_horiz',
            "<strong>SAR Reversal Config</strong><br><br>Fine-tune how the Stop-And-Reverse mechanism behaves when it flips direction."
        ));

        section.appendChild(createCard('Reversal TP (R)', 'Take-profit R-multiple for SAR entries', 'REVERSAL_TP_R', 'input', {
            number: true,
            default: '1.0',
            tooltip: 'The R-multiple for SAR reversal take-profit. 1.0 = target equals risk amount (conservative recovery).'
        }));

        section.appendChild(createCard('Cost-Aware TP', 'Adjust TP to cover previous loss + spread', 'REVERSAL_COST_AWARE_TP', 'toggle', {
            default: 'true',
            tooltip: 'Automatically adjusts the reversal TP to recover the previous trade\'s loss plus estimated spread costs.'
        }));

    } else if (toolboxTab === 'hyper_scalper') {
        const stratInfo = STRATEGIES.hyper_scalper;
        section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'speed'));

        section.appendChild(createCard('Fast EMA Period', 'Fast EMA line', 'FAST_EMA', 'input', { number: true, default: '9' }));
        section.appendChild(createCard('Slow EMA Period', 'Slow EMA line', 'SLOW_EMA', 'input', { number: true, default: '21' }));
        section.appendChild(createCard('Trend EMA Period', 'Trend baseline', 'TREND_EMA', 'input', { number: true, default: '200' }));
        section.appendChild(createCard('Stop ATR Mult', 'Stop distance', 'STOP_ATR_MULT', 'input', { number: true, default: '2.0' }));
        section.appendChild(createCard('Target R', 'Target R ratio', 'TARGET_R', 'input', { number: true, default: '3.0' }));

    } else if (toolboxTab === 'rubberband_reaper') {
        const stratInfo = STRATEGIES.rubberband_reaper;
        section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'architecture'));

        section.appendChild(createCard('BB Period', 'Bollinger Period', 'BB_PERIOD', 'input', { number: true, default: '20' }));
        section.appendChild(createCard('BB StdDev', 'Bollinger Std', 'BB_STD', 'input', { number: true, default: '2.5' }));
        section.appendChild(createCard('RSI Period', 'RSI Lookback', 'RSI_PERIOD', 'input', { number: true, default: '7' }));
        section.appendChild(createCard('RSI Overbought', 'OB threshold', 'RSI_OVERBOUGHT', 'input', { number: true, default: '75' }));
        section.appendChild(createCard('RSI Oversold', 'OS threshold', 'RSI_OVERSOLD', 'input', { number: true, default: '25' }));

    } else if (toolboxTab === 'supply_demand') {
        const stratInfo = STRATEGIES.supply_demand;
        section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'account_balance'));

        section.appendChild(createCard('Target R', 'Target R ratio', 'TARGET_R', 'input', { number: true, default: '2.0' }));
        section.appendChild(createCard('Zone Lookback', 'Candles to check for BOS', 'ZONE_WINDOW', 'input', { number: true, default: '100' }));

    } else if (toolboxTab === 'london_breakout') {
        const stratInfo = STRATEGIES.london_breakout;
        section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'timer'));

        section.appendChild(createCard('Asian Start (UTC)', 'Asian session start', 'ASIAN_START', 'time', { default: '00:00' }));
        section.appendChild(createCard('Asian End (UTC)', 'Asian session end', 'ASIAN_END', 'time', { default: '06:00' }));
        section.appendChild(createCard('London Start (UTC)', 'London session start', 'LONDON_START', 'time', { default: '07:00' }));
        section.appendChild(createCard('Stop Box Mult', 'Stop multiplier against box', 'STOP_BOX_MULT', 'input', { number: true, default: '0.5' }));
        section.appendChild(createCard('Target Box Mult', 'Target multiplier against box', 'TARGET_BOX_MULT', 'input', { number: true, default: '1.5' }));

    } else if (toolboxTab === 'mean_reversion') {
        const stratInfo = STRATEGIES.mean_reversion;
        section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'compare_arrows'));

        section.appendChild(createCard('BB Period', 'Bollinger Period', 'BB_PERIOD', 'input', { number: true, default: '20' }));
        section.appendChild(createCard('BB StdDev', 'Bollinger Std', 'BB_STD', 'input', { number: true, default: '2.0' }));
        section.appendChild(createCard('RSI Period', 'RSI Lookback', 'RSI_PERIOD', 'input', { number: true, default: '14' }));
        section.appendChild(createCard('RSI Overbought', 'OB threshold', 'RSI_OVERBOUGHT', 'input', { number: true, default: '70' }));
        section.appendChild(createCard('RSI Oversold', 'OS threshold', 'RSI_OVERSOLD', 'input', { number: true, default: '30' }));

    } else if (toolboxTab === 'crypto_vwap_reversion') {
        const stratInfo = STRATEGIES.crypto_vwap_reversion;
        if (stratInfo) {
            section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'timeline'));
            section.appendChild(createCard('EMA Period', 'Trend EMA', 'EMA_PERIOD', 'input', { number: true, default: '20' }));
            section.appendChild(createCard('RSI Period', 'RSI Check', 'RSI_PERIOD', 'input', { number: true, default: '14' }));
            section.appendChild(createCard('RSI Long Threshold', 'Max RSI for Long', 'RSI_LONG_THRESHOLD', 'input', { number: true, default: '40' }));
            section.appendChild(createCard('VWAP Dev %', 'VWAP deviation', 'VWAP_DEVIATION_PCT', 'input', { number: true, default: '0.003' }));
        }

    } else if (toolboxTab === 'icc_core_standalone') {
        const stratInfo = STRATEGIES.icc_core_standalone;
        section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'precision_manufacturing'));

        section.appendChild(createCard('Target R', 'Target R ratio', 'TARGET_R', 'input', { number: true, default: '2.0' }));
        section.appendChild(createCard('Stop ATR Mult', 'Stop buffer', 'STOP_ATR_MULT', 'input', { number: true, default: '1.5' }));
        section.appendChild(createCard('Entry Cooldown', 'Bars to wait between entries', 'ENTRY_COOLDOWN_BARS', 'input', { number: true, default: '8' }));

    } else if (toolboxTab === 'crypto_grid') {
        const stratInfo = STRATEGIES.crypto_grid;
        if (stratInfo) {
            section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'grid_on'));
            section.appendChild(createCard('Grid ATR Mult', 'Grid spacing mult', 'GRID_ATR_MULT', 'input', { number: true, default: '1.5' }));
            section.appendChild(createCard('Grid Levels', 'Levels to deploy', 'GRID_LEVELS', 'input', { number: true, default: '5' }));
            section.appendChild(createCard('Trend Guard', 'Max HTF trend strength', 'TREND_GUARD_THRESHOLD', 'input', { number: true, default: '0.5' }));
        }

    } else if (toolboxTab === 'yoyo') {
        const stratInfo = STRATEGIES.yoyo;
        if (stratInfo) {
            section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'wifi_tethering'));
            section.appendChild(createCard('SMA Period', 'Trend Filter', 'SMA_PERIOD', 'input', { number: true, default: '50' }));
            section.appendChild(createCard('Risk Escalation', 'Risk to add per win', 'RISK_ESCALATION', 'input', { number: true, default: '0.01' }));
            section.appendChild(createCard('Max Risk', 'Hard cap risk %', 'MAX_RISK_PCT', 'input', { number: true, default: '0.05' }));
            section.appendChild(createCard('Target R', 'Target R ratio', 'TARGET_R', 'input', { number: true, default: '2.0' }));
        }

    } else {
        // Generic fallback for others (Bearish Engulfing, Volatility Breakout, etc)
        const stratInfo = STRATEGIES[toolboxTab];
        if (stratInfo) {
            section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'tune'));

            section.appendChild(createWarningBox(`
                <strong>Strategy Override Enabled:</strong><br>
                Settings configured here for <em>${stratInfo.name}</em> will take precedence over global Global Risk limits.
            `));

            section.appendChild(createCard('Base Risk %', `Specific risk for ${stratInfo.name}`, 'RISK_PER_TRADE_PCT', 'input', {
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
    currentStrategyContext = null;
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

