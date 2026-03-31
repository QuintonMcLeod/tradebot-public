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
    'SABBATH_TIMEZONE': ['safety', 'sabbath_timezone'],
    'SABBATH_LAT': ['safety', 'sabbath_lat'],
    'SABBATH_LON': ['safety', 'sabbath_lon'],
    'SABBATH_START_LOCAL': ['safety', 'sabbath_start_local'],
    'SABBATH_END_LOCAL': ['safety', 'sabbath_end_local'],
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
    'GUI_DEBUG_NOTIFICATIONS': ['runtime', 'gui_debug_notifications'],
    'GLOBAL_RISK_PCT': ['runtime', 'global_default_risk_pct'],
    'FRIDAY_FADE_ENABLED': ['runtime', 'friday_fade_enabled'],
    'SABBATH_ASTRONOMICAL': ['safety', 'sabbath_astronomical'],
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
    'SAFETY_ROLLOVER_DEADZONE_ENABLED': ['safety', 'safety_rollover_deadzone_enabled'],
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
    'BREAKEVEN_TRAIL_AFTER_PYRAMIDS': ['global', 'breakeven_trail_after_pyramids'],
    'CONDUCTOR_PYRAMID_ENABLED': ['global', 'conductor_pyramid_enabled'],
    'CONDUCTOR_PYRAMID_START_R': ['global', 'conductor_pyramid_start_r'],
    'CONDUCTOR_PYRAMID_FIRST_PCT': ['global', 'conductor_pyramid_first_pct'],
    'EVICTION_MIN_HOLD_ENABLED': ['global', 'eviction_min_hold_enabled'],
    'EVICTION_MIN_HOLD_MINUTES': ['global', 'eviction_min_hold_minutes'],
    'SWAP_AVOIDANCE_ENABLED': ['safety', 'swap_avoidance_enabled'],
    'MTF_STRENGTH_FLOOR': ['global', 'mtf_strength_floor'],
    'MIN_PIP_FLOOR': ['global', 'min_pip_floor'],
    'SPREAD_GATE_MAX_PCT': ['safety', 'spread_gate_max_pct'],
    'BLOCK_RANGING_REGIME': ['global', 'block_ranging_regime'],
    // Strategy Specific
    'QUICK_RANGING_TP_ENABLED': ['global', 'quick_ranging_tp_enabled'],
    'TICK_SCALPING_ENABLED': ['global', 'tick_scalping_enabled'],
    'TICK_SCALPING_MIN_USD': ['global', 'tick_scalping_min_usd'],
    'TARGET_R': ['global', 'target_r'],
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
    'UNIVERSAL_EXIT_STRATEGIES': ['global', 'universal_exit_strategies'],
    'CHANDELIER_ATR_MULT': ['global', 'chandelier_atr_mult'],
    'TIME_DECAY_BARS': ['global', 'time_decay_bars'],
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
    'TREND_CORRELATION_STACKING_ENABLED': ['global', 'trend_correlation_stacking_enabled'],
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
    'RISK_DYNAMIC_AUTO': ['risk', 'risk_dynamic_auto'],
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
    'AI_SEASONED_TRADER_ENABLED': ['ai', 'ai_seasoned_trader_enabled'],
    'AI_MONETARY_PATH': ['ai', 'ai_monetary_path'],
    'AI_PERSONALITY': ['ai', 'ai_personality'],
    'AI_AUTOPILOT_INTERVAL_MINS': ['ai', 'ai_autopilot_interval_mins'],
    
    // AI Commentary (nested under configData.runtime)
    'COMMENTARY_ENABLED': ['runtime', 'commentary_enabled'],
    'COMMENTARY_LLM_POLICY': ['runtime', 'commentary_policy'],
    'COMMENTARY_INTERVAL_MINUTES': ['runtime', 'commentary_interval_minutes'],
    'COMMENTARY_LLM_DAILY_SLOTS': ['runtime', 'commentary_daily_slots'],
    'COMMENTARY_LLM_MAX_CALLS_PER_DAY': ['runtime', 'commentary_max_daily_calls']
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
    PAPER_SIM_ENABLED: "Practice Mode. Lets you test the bot with fake 'Monopoly money' so you can see how it performs without risking a real dime.",
    PAPER_REPLAY_MODE: "Time Machine. Replays past market days so you can instantly see how your strategy would have performed yesterday.",
    PAPER_SYNTHETIC_MODE: "Stress Test. Throws the bot into a wild, endless roller-coaster simulation to see if it can survive the absolute worst market conditions.",
    SABBATH_REPLAY_MODE: "Weekend Practice. During the real-world weekend when markets are closed, switch to the Time Machine mode so you can keep testing.",
    PAPER_FEE_BPS: "Fake Broker Fees. Simulates the small tax the broker charges on every trade, so your practice results match reality.",
    PAPER_SLIPPAGE_BPS: "Fake Slippage. Simulates the slight delay in getting your real order filled. Makes practice trading highly realistic.",
    PAPER_SPREAD_BPS: "Fake Spread. Simulates the difference between the 'buy' price and the 'sell' price in the market. Every market has a markup!",

    // System Settings
    APP_PROFILE: "Trading Profiles. Think of this like choosing a character in a video game. You can be a 'Day Trader', a 'Crypto Night Owl', or a 'Slow and Steady Investor'.",
    STRATEGY_VARIANT: "The Gameplan. This tells the bot exactly HOW to trade. Choose whether you want it to be a fast, aggressive scalper or a patient, long-term investor.",
    BOT_MODE: "Controls the bot's schedule. 'Continuous' means it works 24/7. 'Scheduled' means it only works during specific hours. 'Iterations' means it takes a few trades and goes to sleep.",
    EXECUTE_TRADES: "The Master Safety Switch. Turn this ON to trade with REAL MONEY. Turn it OFF to politely use fake Practice Money.",
    GUI_AUTOSTART_BOT: "Should the bot automatically start watching the markets the moment you open this app? Turn this ON for easy 'set and forget' convenience.",
    CONTINUOUS_MODE: "The Energizer Bunny Mode. Keeps the bot running forever without taking any naps between trading sessions.",
    GUI_WS_URL: "The internal address where the app talks to the bot. Just leave this alone unless you are a computer whiz running advanced server setups.",
    GLOBAL_RISK_PCT: "Your Safety Net. The overall percentage of your money you're willing to risk. 0.04 means 4%. This is your absolute maximum risk limit.",
    WS_SERVER_PORT: "The secret doorway the app uses to talk to the bot. Leave this at 8080 unless you know what you are doing.",
    FRIDAY_FADE_ENABLED: "Friday Afternoon Nap. The markets get crazy and unpredictable right before the weekend. This forces the bot to play it extremely safe after lunchtime on Fridays.",
    PDT_GUARD_ENABLED: "The Bureaucracy Blocker. Prevents you from breaking confusing government rules about 'Day Trading' if your account is small.",

    // Timeframes
    CANDLE_TIMEFRAME: "The Magnifying Glass. '15m' means the bot looks at price changes every 15 minutes. Short times = fast trades but lots of false alarms. Long times = slow trades but very reliable.",
    HTF_TIMEFRAME: "The Telescope. The bot uses this wide view to see the 'big picture' trend before it zooms in to take a trade.",
    LTF_TIMEFRAME: "The Microscope. Once the bot knows the big picture, it uses this zoomed-in view to find the absolute perfect second to jump in.",

    // Trend Detection
    TREND_WINDOW: "How far into the past the bot should look to decide if we are in a 'good, healthy trend' right now.",
    LTF_TREND_WINDOW: "Same as above, but for the zoomed-in Microscope view. Helps the bot react faster to sudden changes.",
    TREND_SWING_LOOKBACK: "How many past peaks and valleys the bot needs to check to figure out where the market is safely bouncing.",
    TREND_MIN_SWINGS: "The 'Show Me Proof' setting. How many bounces the market needs to make before the bot truly believes the trend is really happening.",
    TREND_STRENGTH_FLOOR: "The 'Boring Market' Filter. The bot won't take trades unless the market is moving fast enough to actually be interesting.",

    // Risk Management
    RISK_PER_TRADE_PCT: "How much of your entire piggy bank you are willing to risk on a single bet. 1% means if you have $10,000, the absolute worst you can do is lose $100. Never risk more than you can stomach!",
    MAX_EXPOSURE_PCT: "The Absolute Casino Limit. The maximum total risk allowed if the bot happens to be in multiple different trades at the same time.",
    MAX_DAILY_LOSS_PCT: "The Daily Fire Alarm. If you lose this percentage of your account in one single day, the bot pulls the plug and locks you out to protect your hard-earned money.",
    RISK_PER_TRADE_DOLLARS: "A fixed dollar amount to risk. Tell the bot 'I only want to risk exactly $50 on every trade', no matter what.",
    MAX_LOSS_PER_TRADE_DOLLARS: "The absolute highest dollar amount you can ever lose on one trade, even if the math gets confused. A hard, unbreakable cap.",
    LIMIT_LOSS_DAILY_PCT: "Maximum loss allowed for the day. If things go bad, the bot stops trading and goes to bed. Works like a fire alarm.",
    LIMIT_LOSS_WEEKLY_PCT: "Maximum loss allowed for the week. If you hit an unlucky streak, the bot takes the rest of the week off to clear its head.",
    LIMIT_LOSS_MONTHLY_PCT: "Maximum loss allowed for the month. Protects your wealth from multi-week disasters.",
    TARGET_PROFIT_DAILY_PCT: "Quit While You're Ahead (Daily). If you make this much profit today, the bot turns off so you don't accidentally give it back to the market.",
    TARGET_PROFIT_WEEKLY_PCT: "Quit While You're Ahead (Weekly). Locks in your gains for the week so you can enjoy your weekend stress-free.",
    TARGET_PROFIT_MONTHLY_PCT: "Quit While You're Ahead (Monthly). Protects your long-term monthly wealth accumulation.",

    // Safety & Shields
    MULTI_POSITION_ENABLED: "The Juggler. Allows the bot to keep multiple different trades open at the exact same time. If turned off, it focuses on just one trade until it finishes.",
    MAX_CONCURRENT_POSITIONS: "How many balls the Juggler can keep in the air. More trades = more chances to win, but also more tied-up money.",
    SMART_POSITIONS_ENABLED: "House Money Safety. Only allows the bot to open a new trade if you already have enough open profit to 'pay for' the risk. This protects your original cash.",

    // Pyramiding
    CONDUCTOR_PYRAMID_ENABLED: "Master Pyramid Switch. Allows the bot to automatically add more money to a trade that is already winning. Think of it like deciding to press your bet in poker because you're holding a great hand.",
    CONDUCTOR_PYRAMID_START_R: "When to Press the Bet. How deep into profit the trade needs to be before adding more money. For example, 1.0 means 'add more when my profit matches what I originally risked.' 0.5 means 'add more when I am halfway to my goal.'",
    CONDUCTOR_PYRAMID_FIRST_PCT: "How Much to Add. The size of the extra bet, compared to your original one. 100% means double down (match the original bet). 50% means add half as much as the first time.",
    EVICTION_MIN_HOLD_MINUTES: "Swap Hold Timer. How long (in minutes) a position must be held before it can be swapped out for a better opportunity. Low values = more aggressive swapping, high values = more patient holding.",
    MAX_PYRAMID_ENTRIES: "Maximum extra bets allowed. 'Pyramiding' means adding more as a trade goes in your favor. 1 = no extra bets, just the original trade.",
    BLOCK_RANGING_REGIME: "Sit Out The Chop. When enabled, the bot completely avoids opening new trades if the market is deemed 'ranging' or 'choppy' with no clear direction.",
    PYRAMID_RISK_LOAD: "The size of the VERY FIRST extra bet you place on a winning trade.",
    PYRAMID_RISK_SCALE: "The size of all the OTHER extra bets after the first one. Usually smaller, because your trade is getting pretty huge by now!",
    BREAKEVEN_TRAIL_AFTER_PYRAMIDS: "Free Ride Mode. After making this many extra bets, the bot moves your safety net up to your exact entry price, ensuring you absolutely cannot lose money on the trade. 0 turns this off.",
    BREAKEVEN_TRAIL_PCT: "Extra Cushion. How far 'above' the free ride line to place your safety net, just to guarantee a tiny sliver of profit even if the trade crashes.",

    // ICC Settings
    ICC_AUTO_ENTRY_ENABLED: "The Heartbeat Tracker. Turns on the bot's ability to watch the market's natural rhythm (push, pause, push) to find safe places to enter.",
    ICC_AGGRESSIVE_MODE: "Swing for the Fences. When the bot sees an absolutely perfect setup, it will bet a little more money than usual.",
    ICC_AUTO_ENTRY_REQUIRE_SWEEP: "Trap Detector. Forces the bot to only trade when it sees other traders getting tricked and 'swept' out of the market. Very safe, but doesn't happen often.",
    ICC_AUTO_ENTRY_MIN_HTF_STRENGTH: "The 'No Weak Trends' Filter. Forces the bot to avoid trading unless the big-picture trend is roaring.",
    ICC_CONFIRMATION_BARS: "Patience. How many minutes the bot waits to make sure the signal wasn't a fake-out before jumping in.",
    ICC_ENTRY_SCORE_THRESHOLD: "The Perfectionist. The bot grades every trade from 0 to 100. This sets the minimum passing grade. 75 = only takes good trades. 90 = only takes perfect trades.",

    // ICC Scoring
    ICC_SCORE_CONTINUATION_POINTS: "Bonus points given when the market proves it still wants to keep moving in the right direction.",
    ICC_SCORE_SWEEP_POINTS: "Huge bonus points given when the market successfully fakes out other traders, which usually means a big explosion is coming.",
    ICC_SCORE_HTF_LTF_ALIGN_POINTS: "Bonus points when both the 'Big Picture' view and the 'Microscope' view agree entirely.",
    ICC_SCORE_STRONG_HTF_POINTS: "Bonus points when the 'Big Picture' trend is practically a runaway freight train.",
    ICC_SCORE_PHASE_POINTS: "Bonus points for jumping into a market that is wide awake and moving cleanly, rather than a sleepy, choppy mess.",
    ICC_SCORE_INDICATION_POINTS: "Points just for seeing the very first sign of life that a new trend might be starting.",

    // Exit Settings
    EXIT_ON_HTF_FLIP_ONLY_IF_LOSING: "Mercy Rule. If the big-picture trend suddenly reverses while your trade is losing, the bot kills the trade instantly. But if you are winning, it lets the trade ride a bit longer to see if it recovers.",
    AUTO_FLATTEN_ON_CLOSE: "The End-of-Day Wash. Automatically closes ALL your trades when the daily trading session ends, so you never hold risk while you sleep.",
    TRAILING_STOP_ENABLED: "The Profit Chaser. A safety net that automatically follows the price upward. As you make more profit, the safety net moves up to lock it in!",
    TRAILING_STOP_MIN_PROFIT_PCT: "Breathing Room. Wait until the trade is AT LEAST this much in profit before starting the Profit Chaser.",
    STOP_ATR_MULTIPLIER: "<strong>The 'Safe Distance' Calculator.</strong> Markets naturally wiggle up and down a little bit. A 1.5 multiplier places your safety net 1.5x outside that normal wiggle room. Tight (1.0) = you might get shaken out by a random wiggle. Looser (2.5) = you survive the wiggles, but lose more if you are totally wrong.",
    SAFETY_STABILITY_MODE_ENABLED: "<strong>Master Survival Protocol.</strong> When your account is 'bleeding' or market conditions are totally uncertain, this is your primary shield. It forces strict rules: maximum 1% risk, only perfect 75+ graded trades, and turns off all aggressive accelerator modes. Use this to protect your capital during rough patches.",
    MIN_HOLD_HOURS: "Diamond Hands. The absolute minimum time the bot MUST hold a trade, to prevent it from panic-selling too early.",
    MAX_HOLD_HOURS: "Paper Hands. The absolute maximum time the bot is allowed to sit in a trade before kicking it out, win or lose.",
    HTF_NEUTRAL_EXIT_BARS: "The 'Boredom' Exit. If the market goes totally flat and stops moving for this long, the bot just takes your money out and leaves.",
    UNIVERSAL_EXIT_STRATEGY: "The Master Exit Controller. <strong>The Sniper (Fixed)</strong> sets a rigid target. <strong>Chandelier</strong> aggressively trails winners using volatility. <strong>Time-Decay</strong> forces an exit if the trade is stubbornly flat. <strong>Scale & Breakeven</strong> takes 50% profit early and gives you a free ride.",
    CHANDELIER_ATR_MULT: "Chandelier Tightness. How many 'normal market wiggles' (ATR) to trail below the absolute highest price reached. 2.0 is standard. 1.0 is a tight leash. 3.0 gives trades huge breathing room to ride monster trends.",
    TIME_DECAY_BARS: "The Patience Timer. If you select the Time-Decay exit, this is how many 'candles' the bot will wait for the trade to do something before closing it out of sheer boredom.",

    // Broker Settings - IBKR
    IBKR_HOST: "The House Address. Tells the bot exactly where to find the Interactive Brokers app on your computer (usually 127.0.0.1).",
    IBKR_PORT: "The Door Number. Tells the bot which specific door to knock on to get into your broker. (7497 = Paper Box, 7496 = Real Money).",
    IBKR_CLIENT_ID: "The Bot's Nametag. If you run multiple bots, they each need a different ID number so the broker doesn't get confused.",
    IBKR_ACCOUNT_ID: "Your Bank Account Number. Exactly as it appears in your broker dashboard (e.g. DU1234567 for paper, U1234567 for live).",
    GUI_PNL_TIMEFRAME: "The Scoreboard. Choose whether the big numbers on your dashboard show how much you made today, this week, or this year.",
    IBKR_PAPER: "The 'Monopoly Money' switch for Interactive Brokers. Always flip this ON for testing before you ever risk real cash!",
    IBKR_READ_ONLY: "Look But Don't Touch. The bot can see your balances and watch the market, but its hands are tied—it cannot buy or sell anything.",
    IBKR_DEFAULT_CCY: "Your Home Currency. Normally USD, but you can set this to EUR or GBP if you live in Europe.",

    // Broker Settings - OANDA
    OANDA_ACCOUNT_ID: "Your OANDA Account Number. Found right on your OANDA dashboard (looks like 101-001-1234567-001).",
    OANDA_API_KEY: "Your Secret Trading Password. Gives the bot permission to trade your OANDA account. Never share this with anyone!",
    OANDA_ENVIRONMENT: "Choose 'practice' to play with fake money, or 'live' to trade for real. Always practice first!",
    OANDA_READ_ONLY: "Look But Don't Touch. The bot can watch the market but is strictly forbidden from placing any trades.",

    // Broker Settings - CCXT/Coinbase
    CCXT_EXCHANGE: "Which Crypto Exchange you want to use (like Coinbase, Binance, or Kraken).",
    CCXT_DEFAULT_TYPE: "The Type of Trading. 'Spot' means actually buying the coin. 'Swap' means betting on the future price using leverage.",
    CCXT_API_KEY: "Your Crypto Username. Lets the bot log into your exchange.",
    CCXT_SECRET: "Your Crypto Password. Pairs with the Key above. Guard this with your life!",
    CCXT_SANDBOX: "The Crypto Playpen. Connects to a fake exchange where you can practice trading Bitcoin without spending a dime.",
    CCXT_ENABLE_RATE_LIMIT: "The Polite Knocker. Automatically stops the bot from spamming the exchange so you don't get accidentally banned.",

    // Broker Settings - Gemini
    GEMINI_API_KEY: "Your Gemini Username. Lets the bot log into your Gemini account.",
    GEMINI_API_SECRET: "Your Gemini Password. The ultra-secret code that lets the bot actually place trades.",
    GEMINI_SANDBOX: "The Gemini Playpen. Connects you to Gemini's practice server so you can test safely.",

    // Broker Settings - Kraken
    KRAKEN_API_KEY: "Your Kraken Username. Lets the bot log into your Kraken account.",
    KRAKEN_API_SECRET: "Your Kraken Password. The ultra-secret code that lets the bot actually place trades.",
    KRAKEN_ENVIRONMENT: "Choose 'sandbox' to safely practice, or 'production' to trade real money.",

    // Crypto Order Settings
    CRYPTO_FRACTIONAL_ENABLED: "Pizza Slices. Allows the bot to buy tiny pieces of a crypto coin (like 0.001 Bitcoin) instead of forcing you to buy a whole expensive coin.",
    CRYPTO_MIN_NOTIONAL_USD: "The Minimum Bet. The smallest dollar amount the exchange will accept for a trade.",
    CRYPTO_MAX_NOTIONAL_USD: "The Absolute Ceiling. A safety net that stops the bot from ever accidentally placing a ridiculously huge, account-destroying order.",
    CRYPTO_ORDER_TYPE: "How to buy. 'LIMIT' means 'only buy if I get this exact price'. 'MARKET' means 'I don't care about the price, buy it right now!'",

    // Data Routing
    MARKET_DATA_MODE: "Who is supplying the price charts? 'Primary' = IBKR, 'Alternative' = Crypto, 'Oanda' = Forex.",
    BROKER_MODE: "Who is executing the trades? Usually matches your Data supplier above.",
    ALTERNATIVE_MARKET_DATA: "The Backup Generator. If your main data supplier crashes, the bot automatically switches to this backup to keep you safe.",
    ALTERNATIVE_BROKER: "The Backup Broker. A secondary account the bot can use in an emergency.",

    // AI Settings
    TRADE_SCI_PROVIDER: "Which Artificial Intelligence you want to use (like ChatGPT, Google Gemini, or Claude).",
    TRADE_SCI_MODEL_NAME: "The Specific Brain. Chooses exactly which version of the AI to use. The default is usually the smartest option for trading.",
    CHATGPT_KEY: "The Token. Your API key that pays the AI for its time. You get this from the AI provider's website.",
    AI_TEMPERATURE: "The Creativity Knob. 0 = purely logical and robotic. 2.0 = poetic but completely crazy. We recommend 0.2 for trading.",
    AI_MAX_TOKENS: "The Word Limit. How long the AI's answer is allowed to be. Higher limits cost slightly more pennies.",
    COMMENTARY_ENABLED: "The Master Toggle for AI Insights. Turn this ON to let the AI give you real-time advice and commentary as it trades.",
    COMMENTARY_LLM_POLICY: "When should the AI speak? 'Interval' = every few minutes. 'On_Signal' = only when a trade happens. 'Disabled' = quiet mode.",
    COMMENTARY_INTERVAL_MINUTES: "The Chatty Timer. If set to 15, the AI will give you an update every 15 minutes.",
    COMMENTARY_LLM_DAILY_SLOTS: "The Scheduled Briefing. Tell the AI 'Only talk to me exactly at 9:00 AM and 4:00 PM'.",
    COMMENTARY_LLM_MAX_CALLS_PER_DAY: "The Penny Saver. The absolute maximum number of times the AI is allowed to speak per day, just to make sure you don't overspend on API fees.",

    // Seasoned Trader (Autopilot)
    AI_SEASONED_TRADER_ENABLED: "The Big Red Switch. When you flip this ON, you are handing the keys to a 20-year veteran AI trader. It will actively manage your bot — adjusting risk, switching strategies, reading global news, and making real-time decisions on your behalf. This is NOT the regular commentary AI. This AI physically RUNS the bot. It watches your PnL, monitors the news, and makes adjustments like a seasoned professional sitting at your desk. Turn this off and the bot goes back to following your manual settings.",
    AI_MONETARY_PATH: "What's Your Goal? This tells the AI what kind of trader YOU want to be. 'Aggressive Growth' means the AI will take bigger, calculated risks to grow your account fast — think wolf of Wall Street energy. 'Balanced Compounder' means steady, consistent gains without wild swings — the tortoise approach. 'Capital Preservation' means the AI's #1 job is to NOT lose your money, even if that means making less profit. Pick the one that lets you sleep at night.",
    AI_PERSONALITY: "Who's Driving? This changes HOW the AI thinks and talks. 'The Calculating Quant' is cold, mathematical, and emotionless — pure numbers. 'The 20-Year Veteran' is experienced and measured — been through crashes and knows when to sit tight. 'The Aggressive Scalper' is fast and hungry — loves quick trades and small wins that add up. 'The Patient Sniper' waits for hours or days for the PERFECT shot, then strikes once and walks away. Each personality produces different commentary and makes different trading decisions.",
    AI_AUTOPILOT_INTERVAL_MINS: "How Often Does the AI Check In? Every this-many minutes, the AI wakes up, looks at your account, reads the latest news, reviews what it did last time, and decides if anything needs to change. 30 minutes is the default — frequent enough to catch problems, but not so frequent that it's burning through your API budget. Set it lower (like 5) if you want the AI hyper-attentive during volatile markets. Set it higher (like 60) if things are calm and you want to save on API costs.",

    GUI_CAPITAL_DISPLAY_MODE: "Dashboard Display preference. 'Overall' shows your total net worth. 'Buying Power' shows only the cash you have left to spend.",

    // Sabbath Settings
    SABBATH_ENABLED: "The Day of Rest. The bot will automatically stop taking ALL new trades during the Jewish Sabbath (Friday night to Saturday night).",
    SABBATH_ASTRONOMICAL: "Star Tracker. Uses actual astronomy to calculate the exact minute the sun sets in your city, rather than using a fixed clock time.",
    SABBATH_TIMEZONE: "Where do you live? Tell the bot your timezone (like 'America/New_York') so it gets the sunset perfectly right.",
    SABBATH_LAT: "Your city's North/South GPS coordinate to help calculate the accurate sunset.",
    SABBATH_LON: "Your city's East/West GPS coordinate to help calculate the accurate sunset.",
    SABBATH_START_LOCAL: "The manual backup Start Time for the Sabbath, if the Star Tracker is disabled (Usually 6:00 PM).",
    SABBATH_END_LOCAL: "The manual backup End Time for the Sabbath (Usually 6:00 PM on Saturday).",

    // Session Settings
    SESSION_GATE_ENABLED: "The 9-to-5 Switch. Forces the bot to only trade during active, busy market hours. It will take a nap during the quiet, risky hours.",
    SESSION_OVERLAP_START_HOUR: "The Opening Bell. When should the bot wake up and start looking for trades?",
    SESSION_OVERLAP_END_HOUR: "The Closing Bell. When should the bot stop taking new trades and wrap up its work for the day?",
    SESSION_OVERLAP_TIMEZONE: "The timezone the bot uses to understand when bells ring.",
    AUTO_SCHEDULE_ENABLED: "The Smart Calendar. Automatically switches between Wall Street hours (9:30-4) and Crypto hours (24/7) without you having to touch it.",
    SUPPLY_DEMAND: "The Wholesale Finder. Looks for the hidden 'wholesale price' where big banks buy and sell, and tries to sneak into their trades. Very high accuracy.",

    // Safety & Shields

    // Trend Detection Indicator Tooltips
    TREND_ADX_ENABLED: "<strong>Average Directional Index (ADX)</strong><br><span style='color:#818cf8;font-size:10px'>Type: Strength</span><br><br>Think of ADX like a speedometer for trends. It doesn't tell you <em>which way</em> the market is going — just <em>how strongly</em> it's moving on a scale of 0 to 100.<br><br>When ADX is below 20, the market is going sideways with no real direction — like a car idling. Above 20, there's a real trend the bot can work with.<br><br><span style='color:#22c55e'>✓ Good for:</span> Keeping the bot from trading in sloppy, sideways markets where there's no clear direction.<br><span style='color:#ef4444'>✗ Heads up:</span> ADX tells you <em>how strong</em> but not <em>which way</em>. It also reacts slowly to sudden reversals.",
    TREND_CORRELATION_STACKING_ENABLED: "<strong>Macro Correlation Stacking</strong><br><span style='color:#f59e0b;font-size:10px'>Type: Basket Allowance</span><br><br>When enabled, the bot is allowed to open multiple highly-correlated pairs in the same direction simultaneously (e.g., buying EURUSD and GBPUSD at the exact same time when the USD Index drops).<br><br><span style='color:#ef4444'>⚠ Aggressive Flipping:</span> Keeping this ON acts as a massive correlation multiplier. You are effectively stacking your account risk on a single macroeconomic move. If you are risk-averse, turn this OFF.",
    TREND_RSI_ENABLED: "<strong>Relative Strength Index (RSI)</strong><br><span style='color:#818cf8;font-size:10px'>Type: Momentum</span><br><br>RSI measures how much buying vs selling pressure there is, on a scale from 0 to 100. Below 30 means everyone's been selling (oversold — could bounce). Above 70 means everyone's been buying (overbought — could dip).<br><br>The bot uses RSI as a direction hint: above 55 leans bullish, below 45 leans bearish.<br><br><span style='color:#22c55e'>✓ Good for:</span> Spotting when a market has been pushed too far in one direction and might reverse.<br><span style='color:#ef4444'>✗ Heads up:</span> In a strong uptrend, RSI can stay 'overbought' for a long time — it doesn't mean the trend is over.",
    TREND_MACD_ENABLED: "<strong>MACD (Moving Average Convergence Divergence)</strong><br><span style='color:#818cf8;font-size:10px'>Type: Momentum</span><br><br>MACD tracks the gap between a fast and slow moving average. When the fast one crosses above the slow one, momentum is shifting upward. When it crosses below, momentum is shifting down.<br><br>The histogram bar shows how fast momentum is changing — taller bars mean stronger moves.<br><br><span style='color:#22c55e'>✓ Good for:</span> Catching the moment a trend starts picking up steam in one direction.<br><span style='color:#ef4444'>✗ Heads up:</span> In flat, directionless markets, MACD bounces back and forth near zero giving false signals.",
    TREND_BOLLINGER_ENABLED: "<strong>Bollinger Bands</strong><br><span style='color:#818cf8;font-size:10px'>Type: Volatility</span><br><br>Bollinger Bands are like an elastic band around the price. When the bands squeeze tight, the market is quiet — but a big move is usually coming. When they spread wide, the market is already moving fast.<br><br>The bot watches for squeezes and uses them to lower confidence — because during a squeeze, nobody knows <em>which way</em> the breakout will go.<br><br><span style='color:#22c55e'>✓ Good for:</span> Warning when the market is 'coiling up' before a big move, and measuring how wild price swings are.<br><span style='color:#ef4444'>✗ Heads up:</span> In strong trends, price 'rides' the outer band — touching it is NOT a reversal signal.",
    TREND_SUPERTREND_ENABLED: "<strong>Supertrend</strong><br><span style='color:#818cf8;font-size:10px'>Type: Trend-Following</span><br><br>Supertrend places an invisible line that follows the price. When price is above the line, the trend is UP (buy). When price drops below, the trend flips to DOWN (sell). Simple as that — always one or the other, never 'maybe'.<br><br><span style='color:#22c55e'>✓ Good for:</span> Clear, no-nonsense direction calls. Great for markets that are trending cleanly in one direction.<br><span style='color:#ef4444'>✗ Heads up:</span> In choppy sideways markets, Supertrend flips back and forth rapidly — every flip is a potential false signal.",
    TREND_EMA_RIBBON_ENABLED: "<strong>EMA Ribbon (8/21/55)</strong><br><span style='color:#818cf8;font-size:10px'>Type: Structure</span><br><br>The EMA Ribbon uses three trend lines of different speeds (fast, medium, slow). When all three are stacked in order — fast on top — the trend is solidly UP. When stacked in reverse, it's solidly DOWN. When they tangle together, there's no clear trend.<br><br><span style='color:#22c55e'>✓ Good for:</span> Confirming that a trend is real and has momentum across multiple timeframes. The 'fanning out' of the ribbon is one of the strongest trend signals.<br><span style='color:#ef4444'>✗ Heads up:</span> Slow to react to sudden reversals. The ribbon tangles during market transitions, which can delay signals.",
    TREND_ICHIMOKU_ENABLED: "<strong>Ichimoku Cloud</strong><br><span style='color:#818cf8;font-size:10px'>Type: Structure</span><br><br>Ichimoku draws a 'cloud' on the chart made from averaged highs and lows. When the price is <em>above</em> the cloud, the market is bullish. When it's <em>below</em> the cloud, it's bearish. When price is <em>inside</em> the cloud, the market is undecided.<br><br>The thicker the cloud, the stronger the support/resistance. This is one of the most complete indicators — it shows trend, momentum, and key levels all in one.<br><br><span style='color:#22c55e'>✓ Good for:</span> A comprehensive read on market direction. Very popular with professional crypto traders. The cloud acts as a 'comfort zone' for the price.<br><span style='color:#ef4444'>✗ Heads up:</span> Needs lots of data (52 candles minimum). In fast-moving markets, the cloud can lag behind the actual price action.",
    TREND_PARABOLIC_SAR_ENABLED: "<strong>Parabolic SAR (Stop & Reverse)</strong><br><span style='color:#818cf8;font-size:10px'>Type: Trend-Following</span><br><br>Parabolic SAR places dots above or below the price. Dots below = trend is UP. Dots above = trend is DOWN. When the dots 'flip' from one side to the other, the trend has reversed.<br><br>The dots accelerate as the trend continues — they follow more closely over time, almost like a trailing stop-loss that tightens automatically.<br><br><span style='color:#22c55e'>✓ Good for:</span> Catching trend reversals quickly. The flip is a clear, unmistakable signal. Also useful as a dynamic trailing stop level.<br><span style='color:#ef4444'>✗ Heads up:</span> In sideways markets, the dots flip constantly — every flip looks like a reversal but isn't.",
    TREND_VWAP_ENABLED: "<strong>VWAP (Volume-Weighted Average Price)</strong><br><span style='color:#818cf8;font-size:10px'>Type: Volume</span><br><br>VWAP is the average price that accounts for trading volume — it tells you what the 'fair price' is based on where the most trading happened. Big institutional traders (banks, hedge funds) use VWAP to judge whether they're getting a good deal.<br><br>Price above VWAP = buyers are in control (bullish). Price below VWAP = sellers are in control (bearish).<br><br><span style='color:#22c55e'>✓ Good for:</span> Understanding where the 'smart money' thinks the fair price is. Great for crypto and intraday trading.<br><span style='color:#ef4444'>✗ Heads up:</span> Less useful for long-term trends since VWAP resets with each session. Needs volume data to work properly.",
    TREND_HULL_MA_ENABLED: "<strong>Hull Moving Average (HMA)</strong><br><span style='color:#818cf8;font-size:10px'>Type: Smoothed Moving Average</span><br><br>A regular moving average is like looking in the rear-view mirror — you see where the price <em>was</em>, not where it <em>is</em>. Hull MA uses a special math trick to dramatically reduce this lag, giving you a smoother and more current read on the trend.<br><br>When the Hull MA is rising, the trend is UP. When it's falling, the trend is DOWN.<br><br><span style='color:#22c55e'>✓ Good for:</span> Getting a clean, responsive trend direction without the noise. Much faster than regular moving averages while still being smooth.<br><span style='color:#ef4444'>✗ Heads up:</span> Can be <em>too</em> responsive in very choppy markets, flipping direction on minor pullbacks.",
    TREND_ADX_THRESHOLD: "The Snooze Button. If the market is moving too slow (below this number), the bot takes a nap instead of trading. Default is 20. 0 means it never naps.",
    SAFETY_ATR_SHIELD_ENABLED: "The Invisible Bodyguard. Automatically moves your safety net up to break-even as soon as your trade gets safely into profit.",
    SAFETY_DRAWDOWN_BREAKER_ENABLED: "The Big Red Panic Button. If your account drops by a certain percentage, the bot completely locks down and refuses to trade for 24 hours to protect you from a bad market.",
    SAFETY_SESSION_LOCKOUT_ENABLED: "The Afternoon Siesta. Automatically stops taking new trades after lunch (12:00 PM EST) when the market gets messy and unpredictable.",
    SAFETY_ROLLOVER_DEADZONE_ENABLED: "The 5 O'clock Shadow. Blocks taking trades exactly at 5 PM EST when banks close out their books for the day, which causes nasty, unpredictable price spikes.",

    // Safety Suite 2.0 (New Additions)
    SAFETY_GREED_GUARD_ENABLED: "The 'Quit While You're Ahead' Switch. Once you make your daily profit goal, the bot stops trading so you don't instantly give the money back to the market.",
    SAFETY_CHURN_BURNER_ENABLED: "The Anti-Spam Filter. Stops the bot from taking too many trades in a single hour if the market is just wiggling back and forth.",
    SAFETY_LEVERAGE_SENTRY_ENABLED: "The Credit Card Limit. Stops the bot from borrowing too much money from the broker if you have a lot of trades open at once.",
    SAFETY_VOLATILITY_VETO_ENABLED: "The Goldilocks Filter. Prevents trading if the market is too painfully slow, or too violently explosive. It waits for it to be 'just right'.",
    SAFETY_STREAK_BREAKER_ENABLED: "The 'Walk It Off' Timer. If the bot loses 3 times in a row on the same coin, it puts that coin in timeout for 4 hours to cool off.",
    SAFETY_OPENING_SENTRY_ENABLED: "The Morning Commute Guard. Blocks the bot from trading during the crazy, volatile first 15 minutes right after the market opens.",
    SAFETY_SENTIMENT_SHIELD_ENABLED: "The AI Co-Pilot. Asks your selected AI (like ChatGPT) to quickly look at the chart right before taking a trade. If the AI says 'this looks dangerous,' the bot cancels the trade.",

    // Performance & Profits (Wealth Creation) - Detailed Layman Tooltips
    PERFORMANCE_MODE_NONE: "<strong>Safe Mode (Standard):</strong> The boring, reliable way to trade. No crazy risk-taking, just standard, mathematical position sizes.",
    PERFORMANCE_MODE_HOUSE_MONEY: "<strong>The Casino's Money:</strong> Once one of your trades is deeply in profit, the bot treats that profit as 'free money' and uses it to fund a brand new trade, multiplying your chances without risking your actual cash.",
    PERFORMANCE_MODE_SNIPER: "<strong>The Perfect Shot:</strong> The bot normally bets its usual size. But if it spots a 'unicorn' setup that scores over 90/100, it automatically triples the bet size.",
    PERFORMANCE_MODE_RUNNER: "<strong>The Long Haul:</strong> When the trade hits its goal, it only sells half, keeping the other half safely running forever to catch massive, lucky trends.",
    PERFORMANCE_MODE_REGIME_SYNC: "<strong>The Weather Vane:</strong> Automatically bets more money when the market is beautifully trending, and bets less money when the market is choppy and ugly.",
    PERFORMANCE_MODE_FLYWHEEL: "<strong>The Snowball Effect:</strong> Every time you make $200, the bot permanently raises your risk by a tiny percentage, slowly turning a small account into a huge one.",
    PERFORMANCE_MODE_STACKER: "<strong>The Double Whammy:</strong> If two totally different betting strategies both agree exactly on the same trade at the exact same time, the bot doubles the bet size because they are probably right.",

    // New Performance Weapons
    PERFORMANCE_MODE_KELLY: "<strong>The Math Genius:</strong> Automatically calculates exactly how much to bet based on your recent winning streak. It naturally bets heavier when you are hot, and scales back to pennies when you are cold.",
    PERFORMANCE_MODE_HYDRA: "<strong>The Multi-Armed Monster:</strong> Trades multiple related pairs (like EURUSD and GBPUSD) together as one single giant trade to safely capture huge global market moves.",
    PERFORMANCE_MODE_COIL: "<strong>The Coiled Spring:</strong> Triples the bet size if the market has been totally dead and asleep for hours, betting that the breakout will be massive and explosive.",
    PERFORMANCE_MODE_VACUUM: "<strong>The Bear Trap:</strong> Waits for other traders to get completely tricked into a fake breakout, then happily bets large in the opposite direction while they panic.",
    PERFORMANCE_MODE_ALPHA: "<strong>The Power Hour:</strong> Automatically doubles the bet size during the busiest, highest-volume hours of the day, and drops to minimum size during sleepy lunch hours.",
    PERFORMANCE_MODE_GAMMA: "<strong>The Squeeze:</strong> Detects rare moments when the market price is physically moving too fast to stop, and instantly jumps in with heavy leverage.",
    PERFORMANCE_MODE_SMOOTH: "<strong>The Protector:</strong> Every time your account hits a new all-time high, it gets a tiny boost. If your account drops, it slashes risk in half until the bot 'earns' its right to trade normally again.",

    // Meta-SCI (Auto Strategy)
    META_SCI_ENABLED: "<strong>The Boardroom Switch:</strong> Turns on the AI Manager. The bot will run every single strategy at once in the background, take a vote, and only trade the one that everyone agrees is the safest bet.",
    META_SCI_MIN_CONSENSUS: "<strong>The Voting Rules:</strong> How many strategies must vote YES before the bot takes a trade. 1 = first one wins. 2 or more = much safer, less frequent trades.",
    META_SCI_EXCLUDE_LIST: "<strong>The Blacklist:</strong> A list of strategies you specifically DO NOT want the AI Manager to ever use (like 'evolution, quantum').",
    PERFORMANCE_MODE_SENTIMENT: "<strong>The News Junkie:</strong> Only allows the biggest, riskiest bets when the global news on Twitter and TV is overwhelmingly positive for the coin.",
    PERFORMANCE_MODE_GHOST: "<strong>The Ghost Hunter:</strong> Sneaks into trades perfectly aligned with 'hidden' wholesale prices that big banks are secretly watching.",
    PERFORMANCE_MODE_PHOENIX: "<strong>The Gambler's Fallacy:</strong> If the bot hits a punishing losing streak and gets put in timeout, it comes back from timeout swinging twice as hard, assuming a win is mathematically 'overdue'.",

    // Advanced Exit Shields
    SAFETY_STALE_SNIPER_ENABLED: "The Zombie Killer. Automatically kills any trade that has been going sideways boringly for too long, freeing up your money for better opportunities.",
    SAFETY_STALE_SNIPER_BARS: "How many candle bars to patiently wait before the Zombie Killer steps in.",
    SAFETY_FLASH_TRAP_ENABLED: "The Airbag. Instantly closes your trades and ejects you from the market if a sudden, violent 'flash crash' is detected.",
    SAFETY_REGIME_FLIP_ENABLED: "The Eject Button. If the 'Big Picture' big trend suddenly reverses while you are making a tiny 'Microscope' trade, the bot ejects you immediately to keep you safe.",
    BLOCK_COUNTER_TREND_ENTRIES: "Don't Catch Falling Knives. Prevents the bot from ever buying when the overall trend is heavily downward.",

    // Wealth Weapons Exits
    WEALTH_EXIT_GAMMA_ENABLED: "The Lasso. Dramatically tightens your trailing safety net during explosive, vertical price moves to make sure you capture 90% of the giant squeeze.",
    WEALTH_EXIT_MOONSHOT_ENABLED: "The Elevator. If a trade hits its goal in less than 3 candles (too fast!), the bot instantly doubles the profit target because a massive breakout is happening.",
    WEALTH_EXIT_BLOWOFF_ENABLED: "The Top Caller. Instantly sells 100% of your position if the market gets too crazy and vertical, cashing you out exactly at the top.",

    // Stop-and-Reverse
    STOP_AND_REVERSE_ENABLED: "<strong>The Uno Reverse Card.</strong> If the bot's safety net is hit because the market moved violently the wrong way, this tells the bot to instantly 'flip' its bet and ride the new wave.",
    COUNTER_REVERSAL_ENABLED: "<strong>The Double Uno Reverse.</strong> If the first Uno Reverse Card was ALSO wrong, fire a second, huge bet in the original direction just in case the market is toying with you.",
    SAR_KEEP_OPEN: "<strong>Keep Uno Card Alive.</strong> Decides if the bot should nervously hold onto the first reverse card while the second reverse card is firing.",
    REVERSAL_TP_R: "<strong>The Uno Target.</strong> How much profit you want the Uno Reverse trade to target before cashing out.",
    REVERSAL_COST_AWARE_TP: "<strong>The Tax Accountant.</strong> Automatically makes the profit target just a tiny bit larger to completely cover the broker's hidden 'spread' taxes.",
    REVERSAL_RISK_PER_TRADE: "<strong>The Uno Bet Size.</strong> How much of your account to risk on the Uno Reverse swing. Usually larger than a normal trade because vengeance is expensive.",
    SCALE_OUT_FRACTION: "<strong>The De-Risk Slice.</strong> When the bot decides it's time to 'take some chips off the table', what percentage of your bet should it cash out? (e.g., 0.95 means cash out 95% and let 5% ride on luck).",
};

function getValue(key, strategyNamespace = null) {
    // Authority: Use the current session's timeframe from renderer.js
    if (key === 'GUI_PNL_TIMEFRAME' && typeof window.pnlTimeframe !== 'undefined') {
        return window.pnlTimeframe;
    }

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
        targets: ['RISK_DYNAMIC_AUTO'],
        message: "<strong>Equity Smoothing</strong> dynamically calculates risk based on your real-time equity curve. This overrides standard <strong>Auto Risk</strong> scaling.",
        type: 'modal'
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
function checkConflicts(sourceKey, value, customConfirm = null) {
    let conflictId = `${sourceKey}:${value}`;
    if (sourceKey === 'PERFORMANCE_MODE') {
        conflictId = `performance:${value.toLowerCase()}`;
    }
    const config = CONFLICT_MAP[conflictId];

    if (config) {
        if (config.requires) {
            const reqVal = getValue(config.requires.key);
            if (reqVal !== 'true' && reqVal !== true) {
                showConflictModal(
                    "Missing Requirement",
                    config.requires.message + "<br><br><i>Proceeding will automatically enable the required setting.</i>",
                    () => {
                        updateValue(config.requires.key, 'true');
                        // Then proceed with the ghosting/normal config targets:
                        config.targets.forEach(t => updateValue(t, 'false'));
                        if (customConfirm) customConfirm();
                        else {
                            updateValue(sourceKey, value);
                            renderTab();
                        }
                    }
                );
                return true;
            }
        }

        // Skip modal if all targets are already in the desired state (off/false)
        if (config.type === 'modal' && config.targets.length > 0) {
            const allAlreadyOff = config.targets.every(t => {
                const cur = getActiveProfileSettings()[t];
                return cur === false || cur === 'false' || cur === '' || cur === undefined || cur === null || cur === 'off' || cur === 'none';
            });
            if (allAlreadyOff) {
                // No conflict — targets already disabled, just apply the change
                if (customConfirm) customConfirm();
                else {
                    updateValue(sourceKey, value);
                    renderTab();
                }
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
                    if (customConfirm) {
                        customConfirm();
                    } else {
                        updateValue(sourceKey, value);
                        renderTab();
                    }
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

    const performanceModeRaw = getValue('PERFORMANCE_MODE') || 'none';
    const modes = performanceModeRaw.split(',').map(s => s.trim().toLowerCase()).filter(s => s);
    
    for (const mode of modes) {
        const activePerformance = `performance:${mode}`;
        const config = CONFLICT_MAP[activePerformance];
        if (config && config.targets.includes(key)) {
            return true;
        }
    }
    return false;
}

// ═══════════════════════════════════════════════════════════
// STRATEGY DEFINITIONS with detailed descriptions
// ═══════════════════════════════════════════════════════════

const STRATEGIES = {
    orb_breakout: {
        name: "ORB (Opening Range Breakout)",
        shortDesc: "NY Opening Range Breakout",
        assetClass: "forex",
        description: "Watches the first 15 minutes of the stock market opening bell to see which way the morning crowd is rushing. It waits for a clear breakout before jumping in to ride the wave. ⚠️ WARNING: Does not work well for Forex.",
        style: "Breakout",
        risk: "Low-Medium",
        bestFor: "Forex: NY Open (9:30-11:00 ET), Stocks/ETFs",
        stats: { verified: "❌ Forex: -$1.7K", winRate: "0%", riskReward: "2:1" }
    },
    rubberband_reaper: {
        name: "Rubberband Reaper",
        shortDesc: "Anti-Martingale Mean Reversion",
        assetClass: "universal",
        description: "Like stretching a rubber band until it snaps back! It waits for the price to get pushed way too far in one direction, then bets that it will naturally bounce back to the middle. It smartly adjusts its bet sizes based on whether it is winning or losing.",
        style: "Mean Reversion",
        risk: "Adaptive",
        bestFor: "Universal: ranging markets, volatile assets",
        stats: { verified: "+7,036%", winRate: "39%", riskReward: "3.7:1" }
    },
    robocop: {
        name: "RoboCop",
        shortDesc: "Aggressive High-Frequency ICC",
        assetClass: "crypto",
        description: "A lightning-fast robot that takes quick, aggressive trades at the very first sign of movement. It doesn't wait around for extra proof to confirm its guess. ✅ Great for Crypto. ❌ Bad for Forex (fees eat the profits).",
        style: "Aggressive Scalping",
        risk: "High",
        bestFor: "Crypto: high-frequency scalping — DO NOT use for Forex",
        stats: { crypto: "✅ +$2.5M", forex: "❌ -$2K", target: "3.0 ATR" }
    },
    evolution: {
        name: "Robot Evolution",
        shortDesc: "NTZ Range Scalper",
        assetClass: "crypto",
        description: "Built for boring, sideways markets where nothing much is happening. It waits for the price to briefly poke its head outside the normal range, grabs a quick profit, and gets right back out. ✅ Good for Crypto.",
        style: "Range Trading",
        risk: "Low-Medium",
        bestFor: "Crypto: ranging markets, NTZ liquidity sweeps",
        stats: { crypto: "✅ +$2.3M", forex: "❌ -$1.1K", focus: "NTZ edges" }
    },
    quantum: {
        name: "Quantum",
        shortDesc: "Trend-Following with SMA Pullback",
        assetClass: "crypto",
        description: "A patient trend-follower. It identifies a strong, moving train of a trend, then waits for the price to simply take a little 'breather' (pull back) before jumping in to join the ride.",
        style: "Trend Following",
        risk: "Medium",
        bestFor: "Crypto: trend pullbacks, or 4H+ Forex only",
        stats: { forex15m: "❌ -$2K", indicator: "20 SMA", target: "2:1 R:R" }
    },
    mean_reversion: {
        name: "Mean Reversion",
        shortDesc: "Bollinger + RSI Extremes",
        assetClass: "universal",
        description: "Waits for the price to stray way too far from home, then bets that it will return back to normal. Simple and effective for markets that are just bouncing back and forth in a sideways pattern.",
        style: "Mean Reversion",
        risk: "Medium",
        bestFor: "Universal: ranging Forex and Crypto markets",
        stats: { bands: "15p/2.5σ", rsi: "<25/>75", pyramid: "6-bar cool" }
    },
    hyper_scalper: {
        name: "HyperScalper",
        shortDesc: "EMA Crossover Speed Trading",
        assetClass: "universal",
        description: "An extremely hyperactive trader that tries to catch tiny little moves every 5 minutes by watching speed lines cross each other. ❌ WARNING: Not recommended for most markets because the broker fees will eat all your money.",
        style: "Fast Scalping",
        risk: "Very High",
        bestFor: "Universal: ❌ NOT RECOMMENDED — 0% win rate",
        stats: { ema: "9/21/200", forex: "❌ -$2K (0% win)", risk: "1%" }
    },
    london_breakout: {
        name: "London Breakout",
        shortDesc: "Session Opening Range",
        assetClass: "forex",
        description: "Wakes up specifically for the London morning bell, watches the first hour to see the early morning mood, and then trades enthusiastically in the direction of the huge morning rush.",
        style: "Breakout",
        risk: "Medium",
        bestFor: "Forex: GBP pairs, European session",
        stats: { session: "08:00-12:00", target: "1.5R", window: "London" }
    },
    volatility_breakout: {
        name: "Volatility Breakout",
        shortDesc: "Range Expansion Momentum",
        assetClass: "universal",
        description: "Looks for markets that have been completely asleep and quiet. As soon as the market violently wakes up and breaks out of its nap, this strategy jumps on for the explosive ride.",
        style: "Breakout",
        risk: "Medium-High",
        bestFor: "Universal: any market showing compression",
        stats: { range: "20 periods", target: "2.0R", rsi: ">60/<40" }
    },
    aggregator: {
        name: "Singularity Aggregator",
        shortDesc: "Multi-Strategy Parallel",
        assetClass: "universal",
        description: "A multi-tasker that runs two completely different trading strategies at the same time so your money is always working. It prioritizes adding to trades that are already winning rather than opening brand new ones.",
        style: "Multi-Strategy",
        risk: "Variable",
        bestFor: "Universal: maximizing capital efficiency",
        stats: { strategies: "2 parallel", priority: "Scale > New", goal: "Always loaded" }
    },
    icc_core_standalone: {
        name: "ICC Core (ICT Methodology)",
        shortDesc: "Displacement + OTE Pullback",
        assetClass: "universal",
        description: "Looks for giant 'footprints' left by big banks entering the market. When the banks push the price really hard, it waits for a tiny pullback and then immediately tags along behind the smart money.",
        style: "Price Action / ICT",
        risk: "Low-Medium",
        bestFor: "Universal: ICT methodology with tight risk",
        stats: { method: "ICT OTE+FVG", stop: "1.5× ATR", target: "2.0R" }
    },
    supply_demand: {
        name: "Supply & Demand",
        shortDesc: "Institutional Price Action",
        assetClass: "universal",
        description: "Finds the hidden 'wholesale price areas' where big institutions like to buy and sell. It patiently waits for the price to return precisely to these quiet zones before taking a trade. Low win rate, but massive payouts when it gets it right.",
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
        description: "The ultimate AI Manager. It quietly runs a whole team of different strategies at the exact same time, and uses Artificial Intelligence to pick the very best one for each trade. It's like having a boardroom of experts voting on what to do next.",
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
        description: "The Smart Director. It looks at the market's 'weather' (trending, choppy, or transitioning) and automatically switches to the perfect strategy for those exact conditions. If the market is too stormy and confused, it simply refuses to trade at all to keep you safe.",
        style: "Regime Router",
        risk: "Dynamic (conservative gates)",
        bestFor: "Forex: adapts to market conditions automatically",
        stats: { regimes: "4 (trend/range/transition/choppy)", cooldown: "2h", gate: "HTF/LTF align" }
    },
    trend_rider: {
        name: 'Trend Rider',
        shortDesc: 'EMA Pullback in Strong Trend',
        assetClass: "forex",
        description: "Finds a strong, undeniable trend, then waits for the price to take a tiny step backward before happily hitching a ride in the exact direction of the main trend.",
        style: "Trend Following",
        risk: "Medium (low when inside Conductor)",
        bestFor: "Forex: trending regimes via Conductor",
        stats: { filters: "6 entry gates", indicator: "EMA 8/21", avgLoss: "$3-8 (Conductor)" }
    },
    session_momentum: {
        name: 'Session Momentum',
        shortDesc: 'VWAP + Volume Surge at Open',
        assetClass: "forex",
        description: "Trades only during the busiest 30 minutes of the morning when everyone is rushing into the market. It catches the big wave of trading volume right at the opening bell before things quiet down.",
        style: "Momentum / Session",
        risk: "Medium-High",
        bestFor: "Forex: London & NY session opens",
        stats: { indicator: "VWAP", volume: "2× avg", target: "2.0R" }
    },
    bearish_engulfing: {
        name: 'Engulfing Reversal',
        shortDesc: 'Candle Pattern at Key Structure',
        assetClass: "universal",
        description: "Looks for a specific pattern where a giant, powerful price movement completely 'swallows' the previous tiny price movement, signaling that the entire market is about to dramatically reverse direction.",
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
        description: "Combines two classic speedometers. It waits for a crypto coin to cool off after a big run, and then checks if the momentum is starting to shift before jumping back in.",
        style: "Momentum / Crypto",
        risk: "Medium",
        bestFor: "Crypto: trending markets, BTC/ETH swing trades",
        stats: { rsi: "30/70", macd: "12/26/9", target: "2.0R" }
    },
    crypto_vwap_reversion: {
        name: 'VWAP Reversion (Crypto)',
        shortDesc: 'Mean Reversion to VWAP',
        assetClass: "crypto",
        description: "Finds where the 'average fair price' is, based on trading volume. If a coin wanders too wildly away from this fair price, it bets that it will get pulled back like a magnet.",
        style: "Mean Reversion / Crypto",
        risk: "Medium",
        bestFor: "Crypto: ranging markets, high-volume pairs",
        stats: { indicator: "VWAP", bands: "2σ", target: "1.5R" }
    },
    crypto_double_macd: {
        name: 'Double MACD Scalper (Crypto)',
        shortDesc: 'Dual-Timeframe MACD Momentum',
        assetClass: "crypto",
        description: "Uses two different momentum trackers at once—one fast and one slow—to perfectly time quick trades in the 24/7 crypto markets.",
        style: "Scalping / Crypto",
        risk: "High",
        bestFor: "Crypto: active pairs, scalping BTC/SOL",
        stats: { fast: "5/13/4", slow: "12/26/9", target: "1.5R" }
    },
    crypto_grid: {
        name: 'Virtual Grid (Crypto)',
        shortDesc: 'Grid Trading with Dynamic Levels',
        assetClass: "crypto",
        description: "Casts a virtual 'fishing net' of buy and sell lines around the current price. It profits by continuously catching the small price bounces back and forth within a sideways market.",
        style: "Grid / Crypto",
        risk: "Medium-High",
        bestFor: "Crypto: sideways/ranging markets",
        stats: { levels: "Dynamic", spacing: "ATR-based", target: "0.5-1.0R" }
    },
    yoyo: {
        name: 'Yo-Yo',
        shortDesc: 'Momentum Reversal Engine',
        assetClass: "universal",
        description: "The ultimate bounce-back strategy. It follows the main trend, but if it gets stopped out for a loss, it acts just like a Yo-Yo—it immediately spins around and places a trade in the opposite direction!",
        style: "Trend / SAR",
        risk: "Medium",
        bestFor: "Universal: trending markets with SAR enabled",
        stats: { target: "2:1 R:R", stop: "Swing-based", sar: "Auto-reverse", cap: "3/day/symbol" }
    },
    // 📈 ADVANCED QUANTITATIVE STRATEGIES
    qs_sma_filter: {
        name: 'QS 200-SMA Filter',
        icon: 'filter_alt',
        shortDesc: 'Market Weather Thermometer',
        assetClass: 'universal',
        description: 'Before stepping outside, it checks the weather! If the market is crashing, it completely shuts down to protect your money. It only trades when the long-term trend is clearly going up.',
        style: 'Regime Filter',
        risk: 'Low',
        bestFor: 'Universal: protecting capital during bear markets',
        stats: { indicator: '200-Day Average', action: 'Blocks trades' }
    },
    qs_golden_cross: {
        name: 'QS Golden Cross',
        icon: 'timeline',
        shortDesc: 'Big Picture Momentum',
        assetClass: 'universal',
        description: 'Looks for the rare moment when a fast-moving trend successfully crosses over a slow, sturdy trend. When this Golden Cross happens, it signals the start of a massive, long-term wealth run.',
        style: 'Long-term Trend',
        risk: 'Medium',
        bestFor: 'Universal: catching major bull runs early',
        stats: { fast: '50-Day', slow: '200-Day', hold: 'Months' }
    },
    qs_rsi_mean_reversion: {
        name: 'QS RSI-2 Mean Reversion',
        icon: 'multiline_chart',
        shortDesc: 'Panic Buying Engine',
        assetClass: 'universal',
        description: 'Wait for everyone to panic! When the market violently crashes for a couple of days and gets way too cheap, this strategy buys the massive dip for an immediate, sharp bounce back.',
        style: 'Mean Reversion',
        risk: 'Medium',
        bestFor: 'Universal: buying aggressive dips in an uptrend',
        stats: { trigger: 'RSI under 10', hold: '1-3 days' }
    },
    qs_3_10_trend: {
        name: 'QS 3/10 Trend Follower',
        icon: 'insights',
        shortDesc: 'Smooth Monthly Trend Rider',
        assetClass: 'universal',
        description: 'Ignores the daily noise completely. It looks at the 3-month and 10-month averages to jump on massive, slow-moving trains. Perfect for investors who don\'t want to stress about daily price swings.',
        style: 'Macro Trend',
        risk: 'Low',
        bestFor: 'Universal: stress-free, slow wealth building',
        stats: { fast: '3-Month', slow: '10-Month' }
    },
    qs_tqqq_btal: {
        name: 'QS TQQQ/BTAL Rebalancer',
        icon: 'pie_chart',
        shortDesc: 'Monthly Portfolio Guard',
        assetClass: 'universal',
        description: 'A proxy for holding tech stocks and a crash-insurance fund at the same time. On the very first day of the month, it neatly re-balances the two so you are always protected against sudden market drops.',
        style: 'Rebalancing',
        risk: 'Low',
        bestFor: 'Universal: monthly index fund management',
        stats: { frequency: 'Monthly', focus: 'Risk Parity' }
    },
    qs_choppiness: {
        name: 'QS Choppiness Index',
        icon: 'waves',
        shortDesc: 'Sideways Market Detector',
        assetClass: 'universal',
        description: 'Is the market actually going somewhere, or just running in circles? This uses advanced math to measure the "choppiness", ensuring you never get trapped in a boring, unprofitable sideways mess.',
        style: 'Measurement Filter',
        risk: 'Low',
        bestFor: 'Universal: avoiding fake breakouts',
        stats: { threshold: 'Under 38.2', action: 'Confirms trend' }
    },
    qs_first_day_month: {
        name: 'QS Seasonal First DOM',
        icon: 'calendar_month',
        shortDesc: 'The Payday Anomaly',
        assetClass: 'universal',
        description: 'Capitalizes on a massive human habit: millions of workers automatically investing their new paychecks at the very start of the month! It buys right before the new month starts to ride this predictable wave of cash.',
        style: 'Seasonal / Calendar',
        risk: 'Low',
        bestFor: 'Stocks/Indices: End of Month / Start of Month',
        stats: { holding: '1 to 5 days', edge: 'Institutional Flows' }
    }
};

// ── Trading Defaults: the "zeroed out" safe state ──────────────────────────
// When a strategy is selected, ALL these keys reset to these values FIRST,
// then the strategy-specific preset is applied on top.
// NEVER includes: API keys, secrets, broker configs, theme, schedule, symbols.
const TRADING_DEFAULTS = {
    // ── Risk ──
    RISK_PER_TRADE_PCT: '1.0',
    RISK_DYNAMIC_AUTO: 'false',
    MAX_EXPOSURE_PCT: '25',
    LIMIT_LOSS_DAILY_PCT: '5',
    AGGRESSIVE_RISK_PER_TRADE_PCT: '2.0',
    // ── Exit Logic ──
    TARGET_R: '2.0',
    RISK_REWARD_RATIO: '3.0',
    TRAILING_STOP_ENABLED: 'false',
    TRAILING_STOP_MIN_PROFIT_PCT: '0',
    MIN_HOLD_HOURS: '0',
    MAX_HOLD_HOURS: '0',
    HTF_NEUTRAL_EXIT_BARS: '0',
    SCALE_OUT_FRACTION: '0.5',
    // ── Stop-and-Reverse ──
    STOP_AND_REVERSE_ENABLED: 'false',
    COUNTER_REVERSAL_ENABLED: 'false',
    SAR_KEEP_OPEN: 'false',
    REVERSAL_TP_R: '1.0',
    REVERSAL_COST_AWARE_TP: 'false',
    REVERSAL_RISK_PER_TRADE: '0.045',
    // ── Positions ──
    MULTI_POSITION_ENABLED: 'false',
    MAX_CONCURRENT_POSITIONS: '1',
    SMART_POSITIONS_ENABLED: 'false',
    AUTO_FLATTEN_ON_CLOSE: 'false',
    // ── Pyramiding ──
    MAX_PYRAMID_ENTRIES: '0',
    CONDUCTOR_PYRAMID_ENABLED: 'false',
    CONDUCTOR_PYRAMID_START_R: '0.2',
    CONDUCTOR_PYRAMID_FIRST_PCT: '30',
    BREAKEVEN_TRAIL_AFTER_PYRAMIDS: 'false',
    EVICTION_MIN_HOLD_ENABLED: 'false',
    EVICTION_MIN_HOLD_MINUTES: '30',
    // ── Strategy-Specific ──
    MTF_STRENGTH_FLOOR: '0',
    MIN_PIP_FLOOR: '10',
    BLOCK_RANGING_REGIME: 'false',
    QUICK_RANGING_TP_ENABLED: 'false',
    TICK_SCALPING_ENABLED: 'false',
    TICK_SCALPING_MIN_USD: '0',
    SPREAD_GATE_MAX_PCT: '30',
    TARGET_PROFIT_DAILY_PCT: '0',
    STOP_ATR_MULTIPLIER: '2.0',
    BREAKEVEN_TRAIL_PCT: '0',
    MAX_RISK_CAP_OVERRIDE: '0',
    // ── Safety Guards ──
    SAFETY_GREED_GUARD_ENABLED: 'false',
    SAFETY_ROLLOVER_DEADZONE_ENABLED: 'false',
    SAFETY_DRAWDOWN_BREAKER_ENABLED: 'false',
    SAFETY_LEVERAGE_SENTRY_ENABLED: 'false',
    SAFETY_STREAK_BREAKER_ENABLED: 'false',
    SAFETY_CHURN_BURNER_ENABLED: 'false',
    SAFETY_CHURN_BURNER_MAX: '5',
    SAFETY_MAX_TOTAL_LEVERAGE: '10',
    SAFETY_STALE_SNIPER_ENABLED: 'false',
    SAFETY_STALE_SNIPER_BARS: '50',
    SAFETY_FLASH_TRAP_ENABLED: 'false',
    SAFETY_REGIME_FLIP_ENABLED: 'false',
    SAFETY_ATR_SHIELD_ENABLED: 'false',
    SAFETY_SENTIMENT_SHIELD_ENABLED: 'false',
    SAFETY_VOLATILITY_VETO_ENABLED: 'false',
    SAFETY_VOLATILITY_MIN_PCT: '0',
    SAFETY_VOLATILITY_MAX_PCT: '0',
    SAFETY_SESSION_LOCKOUT_ENABLED: 'false',
    SAFETY_OPENING_SENTRY_ENABLED: 'false',
    BLOCK_COUNTER_TREND_ENTRIES: 'false',
    SWAP_AVOIDANCE_ENABLED: 'false',
    // ── Wealth Exits ──
    WEALTH_EXIT_GAMMA_ENABLED: 'false',
    WEALTH_EXIT_MOONSHOT_ENABLED: 'false',
    WEALTH_EXIT_BLOWOFF_ENABLED: 'false',
    // ── Trend Detection ──
    TREND_ADX_ENABLED: 'false',
    TREND_ADX_THRESHOLD: '0',
    TREND_CORRELATION_STACKING_ENABLED: 'false',
    TREND_RSI_ENABLED: 'false',
    TREND_MACD_ENABLED: 'false',
    TREND_BOLLINGER_ENABLED: 'false',
    TREND_SUPERTREND_ENABLED: 'false',
    TREND_EMA_RIBBON_ENABLED: 'false',
    TREND_ICHIMOKU_ENABLED: 'false',
    TREND_PARABOLIC_SAR_ENABLED: 'false',
    TREND_VWAP_ENABLED: 'false',
    TREND_HULL_MA_ENABLED: 'false',
    // ── ICC ──
    ICC_AUTO_ENTRY_ENABLED: 'false',
    ICC_AGGRESSIVE_MODE: 'false',
    ICC_ENTRY_SCORE_THRESHOLD: '80',
    ICC_AUTO_ENTRY_REQUIRE_SWEEP: 'false',
    ICC_AUTO_ENTRY_MIN_HTF_STRENGTH: '50',
    ICC_TWO_SIGNAL_OVERRIDE_ENABLED: 'false',
    ICC_AUTO_ENTRY_COOLDOWN_MINUTES: '15',
    // ── Performance ──
    PERFORMANCE_MODE: 'none',
};

// ── Strategy presets: only values that DIFFER from TRADING_DEFAULTS ──────────
// When selected, TRADING_DEFAULTS is applied first, then these overrides.
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
        REVERSAL_TP_R: '0.2',
        REVERSAL_COST_AWARE_TP: 'true',
        REVERSAL_RISK_PER_TRADE: '0.045',
        TRAILING_STOP_ENABLED: 'true',
        MAX_PYRAMID_ENTRIES: '50',
        RISK_REWARD_RATIO: '2.0',
        SCALE_OUT_FRACTION: '0.95',
        // Conductor-specific settings (previously hardcoded)
        MTF_STRENGTH_FLOOR: '0.50',
        MIN_PIP_FLOOR: '25',
        BLOCK_RANGING_REGIME: 'false',
        // Safety guards — Conductor defaults these OFF (user can re-enable)
        SAFETY_GREED_GUARD_ENABLED: 'false',
        SAFETY_ROLLOVER_DEADZONE_ENABLED: 'false',
        SAFETY_DRAWDOWN_BREAKER_ENABLED: 'false',
        SAFETY_LEVERAGE_SENTRY_ENABLED: 'false',
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
        REVERSAL_TP_R: '0.2',
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
        REVERSAL_TP_R: '0.2',
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
        REVERSAL_TP_R: '0.2',
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
        REVERSAL_TP_R: '0.2',
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
 * ZERO-RESET: First resets ALL trading settings to safe defaults,
 * then applies the strategy-specific overrides on top.
 */
function applyStrategyPreset(strategyKey) {
    const preset = STRATEGY_PRESETS[strategyKey];
    if (!preset) return; // No preset defined for this strategy

    const stratName = STRATEGIES[strategyKey]?.name || strategyKey;

    // Step 1: Reset ALL trading settings to zero/safe defaults
    for (const [key, value] of Object.entries(TRADING_DEFAULTS)) {
        updateValue(key, value);
    }

    // Step 2: Apply strategy-specific overrides
    for (const [key, value] of Object.entries(preset)) {
        updateValue(key, value);
    }

    const totalChanged = Object.keys(TRADING_DEFAULTS).length;
    const overrides = Object.keys(preset).length;
    console.log(`[PRESET] Reset ${totalChanged} settings → applied ${overrides} ${stratName} overrides`);
    showNotice(`${stratName}: ${totalChanged} settings reset, ${overrides} overrides applied`, 'teal');
    renderTab(); // Refresh UI to reflect changes
}

/**
 * Check if the current config has deviated from a strategy's expected state.
 * The expected state = TRADING_DEFAULTS merged with STRATEGY_PRESETS[strategyKey].
 * Returns { customized: bool, changedKeys: string[] }
 */
function isStrategyCustomized(strategyKey) {
    const preset = STRATEGY_PRESETS[strategyKey];
    if (!preset) return { customized: false, changedKeys: [] };

    // Build the complete expected state: defaults + strategy overrides
    const expectedState = { ...TRADING_DEFAULTS, ...preset };

    const changedKeys = [];
    for (const [key, expectedValue] of Object.entries(expectedState)) {
        const current = getValue(key);
        if (current !== undefined && String(current) !== String(expectedValue)) {
            changedKeys.push(key);
        }
    }
    return { customized: changedKeys.length > 0, changedKeys };
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
    exit_logic: { icon: 'logout', label: 'Exit Logic', render: renderExitLogicTab },
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
            TREND_CORRELATION_STACKING_ENABLED: 'true',
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
            SAFETY_ROLLOVER_DEADZONE_ENABLED: 'true',
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

    const tooltipContent = options.tooltip || TOOLTIPS[key];
    const iconHtml = tooltipContent && !locked ? `<span class="material-symbols-outlined" style="font-size: 14px; opacity: 0.5; margin-left: 6px; cursor: help;">info</span>` : '';

    card.innerHTML = `
        <div class="card-info">
            <span class="card-title" style="display:flex; align-items:center;">${title}${iconHtml}</span>
            <span class="card-desc">${finalDesc}</span>
        </div>
        <div class="card-control no-drag"></div>
    `;

    const controlContainer = card.querySelector('.card-control');
    const rawValue = getValue(key, stratNamespace);
    const value = (rawValue !== null && rawValue !== undefined && rawValue !== '') ? rawValue : (options.default || '');

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
    let rawValue = (_raw !== null && _raw !== undefined && _raw !== '') ? _raw : (options.default !== undefined ? options.default : min);

    // The model stores fractions (0.045 = 4.5%).
    // The slider displays human-friendly percentages (4.5%).
    // Convert stored fraction → display % on load, and display % → fraction on save.
    const isPct = (unit === '%');
    const displayValue = isPct && rawValue < 1 ? (rawValue * 100).toFixed(1) : rawValue;

    let toggleHtml = '';
    let isToggledOn = false;
    let sliderDisabledClass = '';
    if (options.toggleKey) {
        const tVal = getValue(options.toggleKey, stratNamespace);
        isToggledOn = (tVal === 'true');
        if (isToggledOn && options.toggleDisables) {
            sliderDisabledClass = 'opacity-50 pointer-events-none grayscale';
        }
        toggleHtml = `
            <label class="flex items-center gap-1.5 cursor-pointer select-none hover:bg-white/5 transition-colors px-2 py-0.5 rounded" style="position: absolute; bottom: 12px; right: 12px;">
                <input type="checkbox" class="accent-teal-500 w-3.5 h-3.5" ${isToggledOn ? 'checked' : ''} id="chk-${options.toggleKey}">
                <span class="text-[10px] font-black text-teal-400/90 uppercase tracking-widest">${options.toggleLabel}</span>
            </label>
        `;
        card.style.position = 'relative';
        card.style.paddingBottom = '36px'; // Extra space at bottom to fit the toggle nicely
    }

    const tooltipContent = options.tooltip || TOOLTIPS[key];
    const iconHtml = tooltipContent ? `<span class="material-symbols-outlined" style="font-size: 14px; opacity: 0.5; margin-left: 6px; cursor: help;">info</span>` : '';

    if (tooltipContent) {
        card.addEventListener('mouseenter', (e) => showTooltip(e, key, tooltipContent));
        card.addEventListener('mouseleave', hideTooltip);
    }

    card.innerHTML = `
        <div class="slider-header" style="align-items:flex-start;">
            <div>
                <div class="slider-title" style="display:flex; align-items:center;">${title}${iconHtml}</div>
                <div class="slider-desc">${desc}</div>
            </div>
            <div style="display:flex; flex-direction:column; align-items:flex-end;">
                <div class="slider-value">${displayValue}<span class="slider-value-small">${unit}</span></div>
            </div>
        </div>
        <input type="range" class="slider-input ${sliderDisabledClass}" min="${min}" max="${max}" step="${step}" value="${displayValue}">
        <div class="slider-key">${key}</div>
        ${toggleHtml}
    `;

    const slider = card.querySelector('.slider-input');
    const valueDisplay = card.querySelector('.slider-value');

    if (TOOLTIPS[key]) {
        card.addEventListener('mouseenter', (e) => showTooltip(e, key, TOOLTIPS[key]));
        card.addEventListener('mouseleave', hideTooltip);
    }

    if (options.toggleKey) {
        const chk = card.querySelector(`#chk-${options.toggleKey}`);
        chk.addEventListener('change', (e) => {
            const isChecked = e.target.checked;
            updateValue(options.toggleKey, isChecked ? 'true' : 'false', stratNamespace);
            if (options.toggleDisables) {
                if (isChecked) {
                    slider.classList.add('opacity-50', 'pointer-events-none', 'grayscale');
                } else {
                    slider.classList.remove('opacity-50', 'pointer-events-none', 'grayscale');
                }
            }
        });
    }

    let saveTimeout;
    slider.addEventListener('input', (e) => {
        valueDisplay.innerHTML = `${e.target.value}<span class="slider-value-small">${unit}</span>`;
        if (saveTimeout) clearTimeout(saveTimeout);
        saveTimeout = setTimeout(() => {
            // Save as fraction if unit is '%' (e.g. slider 4.5 → save 0.045)
            const saveValue = isPct ? (parseFloat(e.target.value) / 100).toString() : e.target.value;
            updateValue(key, saveValue, stratNamespace);
        }, 500);
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

    // Add Import/Export Buttons (Relocated to bottom)

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

    section.appendChild(createDivider());
    section.appendChild(createSectionHeader('System & Debug', 'bug_report',
        "<strong>Developer Options</strong><br><br>Enable these to diagnose issues or receive deep system notifications."
    ));
    section.appendChild(createCard('Debug Notifications', 'Show desktop push notifications for backend events like Pyramiding.', 'GUI_DEBUG_NOTIFICATIONS', 'toggle'));

    section.appendChild(createDivider());
    section.appendChild(createSectionHeader('Notifications & Sounds', 'notifications_active',
        "<strong>Audio Alerts</strong><br><br>Customize the sound played when you secure a profitable exit ('Cha-Ching!')."
    ));

    const soundHtml = `
        <div style="margin-bottom: 20px; padding: 15px; background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); border-radius: 12px; position: relative;">
            <div style="font-size: 11px; font-weight: 800; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 8px;">Payout Alert</div>
            <select id="win-sound-type" class="settings-input" style="width: 100%; color-scheme: dark; padding: 10px; background: rgba(0,0,0,0.5); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; color: #f8fafc; font-weight: 500; cursor: pointer;">
                <option value="default">Default ("Cha-Ching")</option>
                <option value="disabled">Disabled (Silent)</option>
                <option value="custom">Custom Audio File...</option>
            </select>
            <div id="custom-sound-path" style="display: none; margin-top: 10px; font-size: 11px; color: #14b8a6; word-break: break-all; background: rgba(20,184,166,0.1); padding: 8px; border-radius: 6px;"></div>
            <input type="file" id="custom-sound-upload" accept="audio/*" style="display: none;">
        </div>
    `;
    const soundDiv = document.createElement('div');
    soundDiv.innerHTML = soundHtml;
    section.appendChild(soundDiv);

    // Wire up the sound logic after appending
    setTimeout(() => {
        const select = document.getElementById('win-sound-type');
        const upload = document.getElementById('custom-sound-upload');
        const pathDisplay = document.getElementById('custom-sound-path');

        if (!select || !upload || !pathDisplay) return;

        // Init values from localStorage
        const savedType = localStorage.getItem('GUI_WIN_SOUND_TYPE') || 'default';
        const savedPath = localStorage.getItem('GUI_WIN_SOUND_PATH') || '';
        select.value = savedType;

        if (savedType === 'custom' && savedPath) {
            pathDisplay.style.display = 'block';
            pathDisplay.textContent = 'Current: ' + savedPath.split('/').pop();
        }

        select.addEventListener('change', (e) => {
            const val = e.target.value;
            localStorage.setItem('GUI_WIN_SOUND_TYPE', val);
            
            if (val === 'custom') {
                upload.click(); // Trigger file picker
            } else {
                pathDisplay.style.display = 'none';
                localStorage.removeItem('GUI_WIN_SOUND_PATH');
            }
        });

        upload.addEventListener('change', (e) => {
            if (e.target.files && e.target.files.length > 0) {
                // Electron provides the absolute path on the file object
                const absolutePath = e.target.files[0].path;
                localStorage.setItem('GUI_WIN_SOUND_PATH', absolutePath);
                pathDisplay.style.display = 'block';
                pathDisplay.textContent = 'Current: ' + absolutePath.split('/').pop();
            } else {
                // User cancelled logic
                if (!localStorage.getItem('GUI_WIN_SOUND_PATH')) {
                    select.value = 'default';
                    localStorage.setItem('GUI_WIN_SOUND_TYPE', 'default');
                    pathDisplay.style.display = 'none';
                }
            }
        });
    }, 50);

    section.appendChild(createDivider());
    
    // Data Management
    section.appendChild(createSectionHeader('Data Management', 'save',
        "<strong>Configuration Backups</strong><br><br>Export your entire configuration back to a JSON file for safekeeping, or import a previously saved configuration. Imported settings take effect immediately."
    ));

    const dataGrid = document.createElement('div');
    dataGrid.className = 'card-grid card-grid-3 mb-8';

    const btnImport = createControlButton('Import Settings', 'download', 'purple', async () => {
        if (!window.api || !window.api.invoke) return;
        const res = await window.api.invoke('import-config');
        if (res && res.success) {
            setTimeout(() => {
                if (window.showToast) window.showToast('Settings imported successfully.', 'success');
            }, 100);
        } else if (res && !res.canceled) {
            if (window.showToast) window.showToast(`Import failed: ${res.error}`, 'error');
        }
    });

    const btnExport = createControlButton('Export Settings', 'upload', 'teal', async () => {
        if (!window.api || !window.api.invoke) return;
        const res = await window.api.invoke('export-config');
        if (res && res.success) {
            if (window.showToast) window.showToast(`Settings exported successfully.`, 'success');
        } else if (res && !res.canceled) {
            if (window.showToast) window.showToast(`Export failed: ${res.error}`, 'error');
        }
    });

    const btnReset = createControlButton('Factory Reset', 'delete_forever', 'red', async () => {
        if (!window.api || !window.api.invoke) return;
        if (confirm("Are you ABSOLUTELY SURE you want to perform a Factory Reset?\n\nThis will permanently delete your configuration, Secret API keys, Profit Logs, and all profile templates before restarting the application.")) {
            // First send hard kill via node child_process directly, independent of the electron API
            try {
                const pkillCmd = 'pkill -9 -f "tradebot_sci.runtime.controller"';
                require('child_process').execSync(pkillCmd);
            } catch (e) {} // ignore kill errors if already dead
            
            const res = await window.api.invoke('reset-config');
            if (res && res.success) {
                if (window.showToast) window.showToast(`Application is restarting...`, 'success');
            } else if (res && !res.canceled) {
                if (window.showToast) window.showToast(`Reset failed: ${res.error}`, 'error');
            }
        }
    });

    dataGrid.appendChild(btnImport);
    dataGrid.appendChild(btnExport);
    dataGrid.appendChild(btnReset);
    section.appendChild(dataGrid);

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
    section.appendChild(createSectionHeader('Account Setup', 'account_balance_wallet',
        "<strong>Initial Capital</strong><br><br>Set the starting balance for your paper trading account. If you reset paper trading from the dashboard, it will go back to this amount."
    ));
    section.appendChild(createCard('Initial Capital (USD)', 'Starting balance for paper trading', 'PAPER_BALANCE', 'input', { number: true, step: '100', default: '10000.0' }));

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
                    ${(() => {
                        const { customized, changedKeys } = isStrategyCustomized(currentStrategy);
                        if (customized) {
                            return `<div style="margin-top: 8px; padding: 4px 8px; background: rgba(245,158,11,0.15); border: 1px solid rgba(245,158,11,0.3); border-radius: 6px; font-size: 11px; color: #f59e0b;">⚠ Custom — ${changedKeys.length} setting${changedKeys.length > 1 ? 's' : ''} modified from preset</div>`;
                        }
                        return '';
                    })()}
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
        grid.appendChild(createSliderCard('Default Risk %', 'Fallback equity risk', 'RISK_PER_TRADE_PCT', 0.1, 20.0, 0.1, '%', { toggleKey: 'RISK_DYNAMIC_AUTO', toggleLabel: 'Auto', toggleDisables: true }));
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
        grid2.appendChild(createSliderCard('Eviction Hold Timer', 'Min minutes before a loser can be swapped', 'EVICTION_MIN_HOLD_MINUTES', 5, 240, 5, 'min', { toggleKey: 'EVICTION_MIN_HOLD_ENABLED', toggleLabel: 'Enabled', toggleDisables: true, default: '30' }));
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

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('Forex Conductor Execution Constraints', 'network_node',
            "<strong>Forex Execution Constraints</strong><br><br>Specific controls for the Forex Conductor architecture. The MTF Floor enforces macro trend strength, and the Pip Floor prevents 1-minute execution from placing stops too tightly and getting whipsawed out by noise."
        ));
        
        const grid3 = document.createElement('div');
        grid3.className = 'card-grid';
        grid3.appendChild(createSliderCard('MTF Strength Floor', 'Min MTF trend alignment (0 = off)', 'MTF_STRENGTH_FLOOR', 0.0, 1.0, 0.05, '', { default: '0.50' }));
        grid3.appendChild(createSliderCard('Minimum Pip Floor', 'Stop-loss minimum distance', 'MIN_PIP_FLOOR', 5, 50, 1, 'pips', { default: '25' }));
        section.appendChild(grid3);

    } else if (subTabs.strategy === 'pyramid') {
        section.appendChild(createSectionHeader('Pyramid Configuration', 'stacked_line_chart',
            "<strong>Pyramid Configuration</strong><br><br>Pyramiding means adding to a winning position. This setting controls the global maximum number of allowed pyramided entries for simple mean-reversion strategies."
        ));

        section.appendChild(createCard('Max Pyramid Entries', 'Total entries per position', 'MAX_PYRAMID_ENTRIES', 'input', { number: true, default: '6', min: 1, max: 20 }));

        // ── Conductor Pyramid & Cost Savings ──
        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('Conductor Pyramid Tuning', 'tune',
            "<strong>Conductor Pyramid Tuning</strong><br><br>These controls configure the Forex Conductor's R-milestone pyramid system. The Conductor adds to winning trades at profit milestones — the first pyramid fires at the configured R-level, with follow-up adds every 0.5R after. Adjust the trigger level and sizes to match your trading style."
        ));

        // Conductor controls (saves to global config, promoted to active profile)
        section.appendChild(createCard('Pyramid on Winners', 'Add to winning trades at profit milestones', 'CONDUCTOR_PYRAMID_ENABLED', 'toggle'));
        section.appendChild(createSliderCard('Pyramid Trigger Level', 'R-multiple distance before first add', 'CONDUCTOR_PYRAMID_START_R', 0.1, 2.0, 0.1, 'R', { default: '0.2' }));
        section.appendChild(createSliderCard('First Pyramid Size', 'Risk % of initial position size', 'CONDUCTOR_PYRAMID_FIRST_PCT', 5, 100, 5, '%', { default: '30' }));

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('Breakeven Trail', 'shield',
            "<strong>Breakeven Trail</strong><br><br>Once a trade is profitable enough, the stop-loss moves up to your entry price. This means even if the market reverses, you won't lose money on that trade — you 'lock in' at breakeven."
        ));

        section.appendChild(createCard('Trail After N Pyramids', '0 = disabled', 'BREAKEVEN_TRAIL_AFTER_PYRAMIDS', 'input', { number: true, default: '1', min: 0, max: 10 }));
        // REMOVED: 'Trail Percentage' (BREAKEVEN_TRAIL_PCT) duplicate — canonical in Safety tab (Audit P2)

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

function renderExitLogicTab(container) {
    const section = document.createElement('div');
    section.className = 'settings-section';

    section.appendChild(createSectionHeader('Universal Exit Router', 'logout',
        "<strong>Universal Exit Router</strong><br><br>The Master Controller for trade exits. By centralizing exit logic here, all strategies are forced to obey a single, unified mathematical rule for taking profits and cutting losses."
    ));

    const intro = document.createElement('div');
    intro.className = 'strategy-intro';
    intro.innerHTML = `
        <p style="color: var(--text-secondary); font-size: 13px; line-height: 1.7; margin-bottom: 24px;">
            Choose a centralized exit methodology. <strong>The Sniper</strong> sets rigid targets, <strong>Chandelier</strong> aggressively trails winners, and <strong>Scale & Breakeven</strong> guarantees a free ride after securing initial profits.
        </p>
    `;
    section.appendChild(intro);

    const exitStrategies = [
        { id: 'fixed_rr', label: 'The Sniper (Fixed Target)', desc: 'Sets a rigid mathematical target and stop.', tooltip: 'Think of this like a set-and-forget alarm clock. It will only wake you up when you hit your exact profit goal or your maximum allowed loss.' },
        { id: 'chandelier', label: 'Chandelier Trailing', desc: 'Aggressively trails winners using ATR volatility.', tooltip: 'Like a dog on a leash that walks forward. As the market goes up, it pulls your stop loss up with it. If the market backs up, the leash catches it and you keep the money.', param: { name: 'Chandelier ATR Multiplier', desc: 'Tightness of the trailing stop. Lower is tighter.', key: 'CHANDELIER_ATR_MULT', min: 1.0, max: 5.0, step: 0.1, unit: 'ATR', default: '2.0' } },
        { id: 'scale_breakeven', label: 'Scale & Breakeven', desc: 'Sells 50% at 1R, moves stop to entry.', tooltip: 'Takes half your chips off the table as soon as you are in profit, and moves your risk to zero. It guarantees a free ride for the rest of the trade.' },
        { id: 'parabolic_sar', label: 'Parabolic SAR Trail', desc: 'Trails stops using the SAR dots.', tooltip: 'Uses a classic indicator that puts dots under the price. The longer the trade goes, the closer the dots get, eventually forcing you out to secure the bag.' },
        { id: 'ma_crossover', label: 'Moving Average Crossover', desc: 'Exits when fast MA crosses below slow MA.', tooltip: 'Exits the trade the moment the short-term trend crosses underneath the long-term trend, signaling the momentum is officially over.' },
        { id: 'time_decay', label: 'Time-Decay Timer', desc: 'Kills the trade if it stays flat for too long.', tooltip: 'If the trade is just wandering sideways and boring you to death, this timer automatically closes it so your money isn\'t trapped doing nothing.', param: { name: 'Time-Decay Bars', desc: 'Bars to wait before boredom exit', key: 'TIME_DECAY_BARS', min: 5, max: 100, step: 1, unit: 'bars', default: '24' } },
        { id: 'swing_trailing', label: 'Trailing Swing Lows', desc: 'Trails the stop beneath the M15 higher-lows.', tooltip: 'Like climbing a staircase. It places your safety net under the previous step. As long as the market keeps making new steps up, you stay in.' },
        { id: 'rsi_exhaustion', label: 'RSI Momentum Exhaustion', desc: 'Exits if RSI stays overbought/oversold then diverges.', tooltip: 'Detects when the market has run completely out of breath. It cashes you out before the inevitable reversal hits.' },
        { id: 'bollinger_snap', label: 'Bollinger Band Snap-Back', desc: 'Exits when price violently snaps the outer bands.', tooltip: 'If the price spikes so hard it breaks the normal boundaries of reality, this exits instantly to capture that freak spike before it violently snaps back.' },
        { id: 'ratchet_milestone', label: 'The Ratchet', desc: 'Locks in 25% profit at escalating rigid milestones.', tooltip: 'Every time the trade hits a new major profit milestone, it permanently secures a chunk of cash. A true ratchet only goes one way: up.' },
        { id: 'adx_death', label: 'ADX Trend Death', desc: 'Exits immediately if trend strength (ADX) collapses.', tooltip: 'Monitors the absolute strength of the trend. The second the market loses its conviction and goes limp, this ejects you.' }
    ];

    let activeRaw = getValue('UNIVERSAL_EXIT_STRATEGIES') || "fixed_rr";
    let activeStrategies = Array.isArray(activeRaw) ? activeRaw : activeRaw.split(',').map(s => s.trim());

    const listContainer = document.createElement('div');
    listContainer.className = 'card-list';
    listContainer.style.display = 'flex';
    listContainer.style.flexDirection = 'column';
    listContainer.style.gap = '12px';

    exitStrategies.forEach(strat => {
        const isActive = activeStrategies.includes(strat.id);
        const stratWrapper = document.createElement('div');
        stratWrapper.style.display = 'flex';
        stratWrapper.style.flexDirection = 'column';
        stratWrapper.style.transition = 'all 0.3s ease';

        const cardHtml = `
            <div class="control-card exit-toggle-card" data-strat-id="${strat.id}" data-tooltip="${strat.tooltip}" style="margin-bottom: 0;">
                <div class="card-info">
                    <span class="card-title" style="display:flex; align-items:center;">
                        ${strat.label}
                        <span class="material-symbols-outlined" style="font-size: 14px; margin-left: 6px; opacity: 0.5;">info</span>
                    </span>
                    <span class="card-desc">${strat.desc}</span>
                </div>
                <div class="card-control no-drag">
                    <div class="toggle ${isActive ? 'toggle-active' : ''}"></div>
                </div>
            </div>
        `;
        stratWrapper.innerHTML = cardHtml;

        const toggleCard = stratWrapper.querySelector('.exit-toggle-card');
        const toggleBtn = stratWrapper.querySelector('.toggle');
        
        let subParamWrap = null;
        if (strat.param) {
            subParamWrap = document.createElement('div');
            subParamWrap.className = 'sub-param-wrapper';
            subParamWrap.style.transition = 'all 0.3s ease';
            subParamWrap.style.paddingLeft = '16px';
            subParamWrap.style.borderLeft = '2px solid var(--accent-dim)';
            subParamWrap.style.marginLeft = '16px';
            
            if (!isActive) {
                subParamWrap.style.opacity = '0.3';
                subParamWrap.style.pointerEvents = 'none';
                subParamWrap.style.filter = 'grayscale(100%)';
            }
            
            const p = strat.param;
            const sliderCard = createSliderCard(p.name, p.desc, p.key, p.min, p.max, p.step, p.unit, { default: p.default });
            sliderCard.style.background = 'rgba(255,255,255,0.02)';
            sliderCard.style.boxShadow = 'none';
            subParamWrap.appendChild(sliderCard);
            stratWrapper.appendChild(subParamWrap);
        }

        toggleCard.addEventListener('click', (e) => {
            e.stopPropagation();
            const stratId = toggleCard.dataset.stratId;
            const isNowActive = !toggleBtn.classList.contains('toggle-active');
            toggleBtn.classList.toggle('toggle-active', isNowActive);
            
            stratWrapper.style.border = isNowActive ? '1px solid var(--accent-dim)' : '1px solid transparent';
            
            if (subParamWrap) {
                subParamWrap.style.opacity = isNowActive ? '1' : '0.3';
                subParamWrap.style.pointerEvents = isNowActive ? 'auto' : 'none';
                subParamWrap.style.filter = isNowActive ? 'none' : 'grayscale(100%)';
            }
            
            let currentStrats = Array.isArray(configData.global.universal_exit_strategies) 
                ? [...configData.global.universal_exit_strategies] 
                : (configData.global.universal_exit_strategies || "fixed_rr").split(',').map(s => s.trim());
                
            if (isNowActive) {
                if (!currentStrats.includes(stratId)) currentStrats.push(stratId);
            } else {
                currentStrats = currentStrats.filter(s => s !== stratId);
            }
            if (currentStrats.length === 0) currentStrats = ['fixed_rr']; 
            
            // Bypass stringification to correctly persist RAW Array objects
            configData.global.universal_exit_strategies = currentStrats;
            syncEnvData();
            localChanges['_config_'] = true;
            if (typeof updateChangeCounter === 'function') updateChangeCounter();
            renderTab(); // Refresh the DOM elements
        });
        
        listContainer.appendChild(stratWrapper);
    });

    section.appendChild(listContainer);

    section.appendChild(createDivider());
    section.appendChild(createSectionHeader('Exit Configuration', 'exit_to_app',
        "<strong>Secondary Exit Rules</strong><br><br>Additional conditions that can override or supplement the Universal Router."
    ));

    section.appendChild(createCard('Auto-Flatten on Close', 'Flatten positions at session end', 'AUTO_FLATTEN_ON_CLOSE', 'toggle'));

    section.appendChild(createDivider());
    section.appendChild(createSectionHeader('Trailing Stop', 'trending_down',
        "<strong>Trailing Stop</strong><br><br>A stop-loss that moves up with the price as your trade becomes more profitable. Once the profit reaches a minimum threshold, the trailing stop activates and follows the price upward — locking in profits while still giving the trade room to grow."
    ));

    section.appendChild(createCard('The "Greedy Exit"', 'Enable trailing stop logic', 'TRAILING_STOP_ENABLED', 'toggle'));
    section.appendChild(createSliderCard('Strategy Base Target R', 'Default Take-Profit R-multiple', 'TARGET_R', 0.5, 20.0, 0.5, 'R', { default: '2.0', tooltip: "The default base risk-to-reward target used by sub-strategies to plan their exits." }));
    section.appendChild(createSliderCard('Safety Sniper Override', 'Hard cap Reward Ratio (R:R)', 'RISK_REWARD_RATIO', 1, 20, 0.5, 'R', { default: '3.0', tooltip: "Global safety override. If a position hits this R-multiple, the safety guard instantly flattens it regardless of the core strategy." }));
    section.appendChild(createSliderCard('Trailing Stop Min Profit %', 'Min profit to activate trail', 'TRAILING_STOP_MIN_PROFIT_PCT', 0, 10, 0.5, '%'));

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
    section.appendChild(createSliderCard('Reversal TP (R-Multiple)', 'Take profit target for reversals', 'REVERSAL_TP_R', 0.1, 5.0, 0.1, 'R'));
    section.appendChild(createSliderCard('Reversal Risk %', 'Risk per reversal trade', 'REVERSAL_RISK_PER_TRADE', 1.0, 10.0, 0.5, '', { pctFormat: true }));
    section.appendChild(createCard('Cost-Aware TP', 'Add spread buffer to TP target', 'REVERSAL_COST_AWARE_TP', 'toggle'));
    section.appendChild(createSliderCard('Partial Close Fraction', 'De-risk close percentage', 'SCALE_OUT_FRACTION', 0.25, 1.0, 0.05, ''));

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
        section.appendChild(createSliderCard('Max Spread (% of SL)', 'Blocks entries if spread is too wide', 'SPREAD_GATE_MAX_PCT', 10, 50, 5, '%', { default: '30' }));
        section.appendChild(createCard('Wed Swap Avoidance', 'Closes marginal trades before 5PM Wed swap charge', 'SWAP_AVOIDANCE_ENABLED', 'toggle'));

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

    const modelCard = document.createElement('div');
    modelCard.className = 'control-card';
    modelCard.style.cssText = 'flex-direction: column; align-items: stretch; gap: 12px; padding-bottom: 16px; margin-bottom: 8px;';
    modelCard.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 4px;">
            <div class="card-info" style="flex: 1;">
                <span class="card-title">Model Name</span>
                <span class="card-desc">e.g., gemini-1.5-pro-002</span>
            </div>
        </div>
        <div style="display: flex; gap: 8px;">
            <select id="model-dropdown" class="input-field" style="flex: 1; padding: 10px 14px; border-radius: 8px;">
                <option value="">-- Load Models --</option>
                <option value="__other__">Other (Manual Entry)...</option>
            </select>
            <input type="text" id="model-manual-input" class="input-field" style="flex: 1; display: none; padding: 10px 14px; border-radius: 8px;" placeholder="Enter custom model ID">
        </div>
        <div id="model-fetch-status" style="font-size: 10px; color: var(--error); display: none; margin-top: 4px;"></div>
    `;
    section.appendChild(modelCard);

    setTimeout(() => {
        const btnFetch = document.getElementById('btn-fetch-models');
        const dropdown = document.getElementById('model-dropdown');
        const manualInput = document.getElementById('model-manual-input');
        const statusMsg = document.getElementById('model-fetch-status');
        const provider = envData['TRADE_SCI_PROVIDER'] || 'openai';
        const defaultM = {
            'gemini': ['gemini-2.5-pro', 'gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-2.0-flash-lite-preview-02-05', 'gemini-1.5-pro', 'gemini-1.5-flash'],
            'openai': ['o3-mini', 'o1', 'o1-mini', 'gpt-4.5-preview', 'gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo'],
            'deepseek': ['deepseek-chat', 'deepseek-reasoner'],
            'claude': ['claude-3-7-sonnet-latest', 'claude-3-5-sonnet-latest', 'claude-3-opus-latest', 'claude-3-haiku-20240307'],
            'local': ['llama3', 'mistral', 'qwen2.5', 'phi3']
        };
        const fallbacks = defaultM[provider] || [];
        
        let currentModel = envData['TRADE_SCI_MODEL_NAME'] || '';
        dropdown.innerHTML = '<option value="">-- Select Model --</option>' + fallbacks.map(m => `<option value="${m}">${m}</option>`).join('') + '<option value="__other__">Other (Manual Entry)...</option>';
        
        if (currentModel) {
            manualInput.value = currentModel;
            if (fallbacks.includes(currentModel)) {
                dropdown.value = currentModel;
                manualInput.style.display = 'none';
            } else {
                dropdown.value = '__other__';
                manualInput.style.display = 'block';
            }
        }
        
        const syncModelValue = () => {
            const val = dropdown.value === '__other__' ? manualInput.value : dropdown.value;
            updateValue('TRADE_SCI_MODEL_NAME', val);
        };
        
        dropdown.addEventListener('change', () => {
            if (dropdown.value === '__other__') {
                manualInput.style.display = 'block';
                manualInput.focus();
            } else {
                manualInput.style.display = 'none';
            }
            syncModelValue();
        });
        
        manualInput.addEventListener('input', () => {
            syncModelValue();
        });
        const autoApiKey = envData['CHATGPT_KEY'] || envData['TRADE_SCI_API_KEY'] || '';
        const autoBaseUrl = envData['TRADE_SCI_API_BASE_URL'] || '';
        
        if (window.api && window.api.invoke && autoApiKey) {
            window.api.invoke('fetch-ai-models', provider, autoBaseUrl, autoApiKey).then(res => {
                if (res && res.success) {
                    const models = res.models;
                    dropdown.innerHTML = '<option value="">-- Select Model --</option>' + models.map(m => `<option value="${m}">${m}</option>`).join('') + '<option value="__other__">Other (Manual Entry)...</option>';
                    
                    if (models.includes(currentModel)) {
                        dropdown.value = currentModel;
                        manualInput.style.display = 'none';
                    } else if (currentModel) {
                        dropdown.value = '__other__';
                        manualInput.style.display = 'block';
                    }
                    
                    if (res.notice) {
                        statusMsg.textContent = res.notice;
                        statusMsg.style.color = 'var(--warning)';
                        statusMsg.style.display = 'block';
                    }
                } else {
                    statusMsg.textContent = res.error || 'Failed to fetch live models. Using defaults.';
                    statusMsg.style.display = 'block';
                }
            }).catch(err => {
                statusMsg.textContent = 'Error: ' + err.message;
                statusMsg.style.display = 'block';
            });
        } else if (!autoApiKey && provider !== 'local') {
            statusMsg.textContent = 'Showing defaults (No API key provided)';
            statusMsg.style.color = 'var(--warning)';
            statusMsg.style.display = 'block';
        }
    }, 50);
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

    // ── SEASONED TRADER AUTOPILOT ────────────────────────────────────────────────
    section.appendChild(createDivider());
    section.appendChild(createSectionHeader('Seasoned Trader (Autopilot)', 'psychiatry',
        "<strong>Seasoned Trader (Autopilot)</strong><br><br>Activates the 20-year veteran AI daemon that physically runs the bot on your behalf. It analyzes global news, monitors your PnL, adjusts settings dynamically, and executes advanced safeguards like Synthetic Pre-Flight tests."
    ));

    section.appendChild(createCard('Enable Seasoned Trader', 'AI assumes complete execution control', 'AI_SEASONED_TRADER_ENABLED', 'toggle', { default: 'false' }));

    section.appendChild(createCard('Monetary Path', 'The core AI objective function', 'AI_MONETARY_PATH', 'dropdown', {
        items: [
            { value: 'aggressive', label: 'Aggressive Growth' },
            { value: 'balanced', label: 'Balanced Compounder' },
            { value: 'preservation', label: 'Capital Preservation' }
        ],
        default: 'balanced'
    }));

    section.appendChild(createCard('AI Personality', 'Execution persona & commentary style', 'AI_PERSONALITY', 'dropdown', {
        items: [
            { value: 'quant', label: 'The Calculating Quant' },
            { value: 'veteran', label: 'The 20-Year Veteran' },
            { value: 'scalper', label: 'The Aggressive Scalper' },
            { value: 'sniper', label: 'The Patient Sniper' }
        ],
        default: 'veteran'
    }));

    section.appendChild(createCard('Autopilot Interval (Mins)', 'How often the AI daemon evaluates', 'AI_AUTOPILOT_INTERVAL_MINS', 'input', {
        number: true,
        default: '30',
        min: 1,
        max: 1440,
        step: 1
    }));

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
    section.appendChild(createSectionHeader('Global Scheduler', 'calendar_month',
        "<strong>Global Scheduler</strong><br><br>Manage active trading hours for each profile. If a profile is outside its scheduled window, the bot will sleep. If 'Off-Hours Paper Trading' is enabled, the bot will automatically swap to simulation mode instead of sleeping."
    ));

    const sessionsContainer = document.createElement('div');
    sessionsContainer.className = 'mb-6 px-1';

    function renderSessionsList() {
        sessionsContainer.innerHTML = '';
        if (!configData.schedule) configData.schedule = {};
        if (!configData.schedule.sessions) configData.schedule.sessions = [];
        
        const sessions = configData.schedule.sessions;
        
        if (sessions.length === 0) {
            const emptyState = document.createElement('div');
            emptyState.style.cssText = 'text-align: center; padding: 24px; color: var(--text-muted); background: rgba(0,0,0,0.2); border-radius: 12px; border: 1px dashed rgba(255,255,255,0.1); font-size: 13px;';
            emptyState.innerHTML = 'No schedules configured.<br>Profiles will trade 24/7 unless a schedule is added.';
            sessionsContainer.appendChild(emptyState);
        } else {
            sessions.forEach((sess, idx) => {
                const card = document.createElement('div');
                card.className = 'control-card';
                card.style.marginBottom = '10px';
                
                const rightCol = sess.mode === '24/7' ? 'ALWAYS ACTIVE' : `${sess.start_time} — ${sess.end_time}`;
                const modeLabel = sess.mode === '24/7' 
                    ? `<span style="font-size: 9px; padding: 2px 6px; border-radius: 4px; border: 1px solid var(--warning); color: var(--warning); background: rgba(245, 158, 11, 0.1); margin-left: 10px; font-weight: 800; letter-spacing: 0.1em;">24/7</span>`
                    : (sess.mode === 'one_time' ? `<span style="font-size: 9px; padding: 2px 6px; border-radius: 4px; border: 1px solid var(--success); color: var(--success); background: rgba(16, 185, 129, 0.1); margin-left: 10px; font-weight: 800; letter-spacing: 0.1em;">ONE-TIME</span>` : `<span style="font-size: 9px; padding: 2px 6px; border-radius: 4px; border: 1px solid var(--accent); color: var(--accent); background: var(--accent-dim); margin-left: 10px; font-weight: 800; letter-spacing: 0.1em;">RECURRING</span>`);
                
                const dayMap = {"Sunday": "Su", "Monday": "Mo", "Tuesday": "Tu", "Wednesday": "We", "Thursday": "Th", "Friday": "Fr", "Saturday": "Sa"};
                let daysStr = 'None';
                if (sess.mode === 'one_time' && sess.specific_date) {
                    daysStr = sess.specific_date;
                } else if (sess.days_of_week && sess.days_of_week.length > 0) {
                    daysStr = sess.days_of_week.length === 7 ? 'Everyday' : sess.days_of_week.map(d => dayMap[d]).join(', ');
                }

                card.innerHTML = `
                    <div class="card-info sched-edit-area" style="flex: 1; cursor: pointer; transition: opacity 0.2s;" onmouseenter="this.style.opacity='0.8'" onmouseleave="this.style.opacity='1'" title="Click to edit schedule">
                        <span class="card-title" style="display:flex; align-items:center;">
                            ${sess.profile_name} ${modeLabel}
                        </span>
                        <span class="card-desc" style="margin-top: 8px; display: flex; gap: 24px; color: var(--text-muted);">
                            <span><strong style="color: var(--text-secondary);">Days:</strong> <span style="color: var(--text-main);">${daysStr}</span></span>
                            <span><strong style="color: var(--text-secondary);">Window:</strong> <span style="color: var(--text-main);">${rightCol}</span></span>
                            <span><strong style="color: var(--text-secondary);">Paper Off-Hours:</strong> <span style="color: ${sess.paper_trade_off_hours ? 'var(--accent)' : 'inherit'}">${sess.paper_trade_off_hours ? 'ENABLED' : 'DISABLED'}</span></span>
                        </span>
                    </div>
                    <div class="card-control no-drag">
                        <button class="btn-delete material-symbols-outlined" style="background: transparent; border: none; color: var(--text-muted); cursor: pointer; transition: all 0.2s; font-size: 20px;" title="Delete Schedule">delete</button>
                    </div>
                `;
                
                card.querySelector('.sched-edit-area').addEventListener('click', () => {
                    openAddScheduleModal(sess, idx);
                });
                
                const delBtn = card.querySelector('.btn-delete');
                delBtn.addEventListener('mouseenter', () => delBtn.style.color = 'var(--error)');
                delBtn.addEventListener('mouseleave', () => delBtn.style.color = 'var(--text-muted)');
                
                delBtn.addEventListener('click', () => {
                    configData.schedule.sessions.splice(idx, 1);
                    renderSessionsList();
                    if (window.api && window.api.saveConfig) window.api.saveConfig(configData);
                });
                sessionsContainer.appendChild(card);
            });
        }
    }
    
    function openAddScheduleModal(existingSess = null, existingIdx = -1) {
        const overlay = document.createElement('div');
        overlay.style.cssText = 'position: fixed; inset: 0; z-index: 1000; display: flex; align-items: center; justify-content: center; padding: 16px; background: rgba(2, 6, 23, 0.8); backdrop-filter: blur(8px);';
        
        const profileNames = Object.keys(configData.profiles || {});
        if (profileNames.length === 0) profileNames.push('Default');
        
        const titleText = existingSess ? "Edit Schedule" : "Add Schedule";
        const iconText = existingSess ? "edit" : "add_task";
        
        overlay.innerHTML = `
            <div style="background: linear-gradient(135deg, var(--bg-card) 0%, rgba(15, 23, 42, 0.95) 100%); backdrop-filter: var(--glass-blur); border: 1px solid var(--accent-glow); padding: 32px; border-radius: 20px; width: 100%; max-width: 440px; box-shadow: 0 20px 60px rgba(0, 0, 0, 0.6); position: relative; animation: fadeSlideUp 0.3s cubic-bezier(0.23, 1, 0.32, 1);">
                <h3 style="font-size: 16px; font-weight: 700; color: var(--text-main); margin-bottom: 24px; display: flex; align-items: center; gap: 8px;">
                    <span class="material-symbols-outlined text-glow-teal" style="color: var(--accent);">${iconText}</span> ${titleText}
                </h3>
                
                <div style="display: flex; flex-direction: column; gap: 16px;">
                    <div>
                        <label style="display: block; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.15em; color: var(--accent); margin-bottom: 8px;">Target Profile <span class="material-symbols-outlined" style="font-size: 14px; opacity: 0.5; margin-left: 6px; cursor: help; vertical-align: middle;" onmouseenter="showTooltip(event, 'Target Profile', 'Which profile should these rules apply to? Think of it like deciding which car gets these specific driving hours.')" onmouseleave="hideTooltip()">info</span></label>
                        <select id="modal-profile" class="input-field" style="width: 100%;">
                            ${profileNames.map(p => `<option value="${p}" ${existingSess && existingSess.profile_name === p ? 'selected' : ''}>${p}</option>`).join('')}
                        </select>
                    </div>
                    
                    <div>
                        <label style="display: block; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.15em; color: var(--accent); margin-bottom: 8px;">Schedule Mode <span class="material-symbols-outlined" style="font-size: 14px; opacity: 0.5; margin-left: 6px; cursor: help; vertical-align: middle;" onmouseenter="showTooltip(event, 'Schedule Mode', 'How often should this run? Recurring runs every week on your chosen days. One-Time runs exactly once and never again. 24/7 means it never stops.')" onmouseleave="hideTooltip()">info</span></label>
                        <select id="modal-mode" class="input-field" style="width: 100%;">
                            <option value="business_hours" ${existingSess && existingSess.mode === 'business_hours' ? 'selected' : (!existingSess ? 'selected' : '')}>Recurring (Weekly)</option>
                            <option value="one_time" ${existingSess && existingSess.mode === 'one_time' ? 'selected' : ''}>One-Time Execution</option>
                            <option value="24/7" ${existingSess && existingSess.mode === '24/7' ? 'selected' : ''}>24/7 Continuous Trading</option>
                        </select>
                    </div>
                    
                    <div id="modal-date-container" style="display: none;">
                        <label style="display: block; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.15em; color: var(--accent); margin-bottom: 8px;">Execution Date <span class="material-symbols-outlined" style="font-size: 14px; opacity: 0.5; margin-left: 6px; cursor: help; vertical-align: middle;" onmouseenter="showTooltip(event, 'Execution Date', 'The exact day you want the bot to wake up, execute this schedule once, and then ignore it forever.')" onmouseleave="hideTooltip()">info</span></label>
                        <input type="date" id="modal-date" value="${existingSess && existingSess.specific_date ? existingSess.specific_date : ''}" class="input-field time-picker" style="width: 100%; color-scheme: dark;">
                    </div>
                    
                    <div id="modal-days-container">
                        <label style="display: block; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.15em; color: var(--accent); margin-bottom: 8px;">Active Days <span class="material-symbols-outlined" style="font-size: 14px; opacity: 0.5; margin-left: 6px; cursor: help; vertical-align: middle;" onmouseenter="showTooltip(event, 'Active Days', 'Click the days you want the bot to actively trade. If a day is dark, the bot sleeps (or paper trades) that day.')" onmouseleave="hideTooltip()">info</span></label>
                        <div style="display: flex; gap: 6px; justify-content: space-between;" id="modal-days-row">
                            <button class="modal-day-btn" data-day="Sunday" style="flex:1; height: 32px; border-radius: 8px; background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.1); color: var(--text-muted); font-size: 11px; font-weight: 700; cursor: pointer; transition: all 0.2s;">S</button>
                            <button class="modal-day-btn active" data-day="Monday" style="flex:1; height: 32px; border-radius: 8px; background: var(--accent-dim); border: 1px solid var(--accent); color: var(--accent); font-size: 11px; font-weight: 700; cursor: pointer; transition: all 0.2s; box-shadow: 0 0 10px rgba(20,184,166,0.2);">M</button>
                            <button class="modal-day-btn active" data-day="Tuesday" style="flex:1; height: 32px; border-radius: 8px; background: var(--accent-dim); border: 1px solid var(--accent); color: var(--accent); font-size: 11px; font-weight: 700; cursor: pointer; transition: all 0.2s; box-shadow: 0 0 10px rgba(20,184,166,0.2);">T</button>
                            <button class="modal-day-btn active" data-day="Wednesday" style="flex:1; height: 32px; border-radius: 8px; background: var(--accent-dim); border: 1px solid var(--accent); color: var(--accent); font-size: 11px; font-weight: 700; cursor: pointer; transition: all 0.2s; box-shadow: 0 0 10px rgba(20,184,166,0.2);">W</button>
                            <button class="modal-day-btn active" data-day="Thursday" style="flex:1; height: 32px; border-radius: 8px; background: var(--accent-dim); border: 1px solid var(--accent); color: var(--accent); font-size: 11px; font-weight: 700; cursor: pointer; transition: all 0.2s; box-shadow: 0 0 10px rgba(20,184,166,0.2);">T</button>
                            <button class="modal-day-btn active" data-day="Friday" style="flex:1; height: 32px; border-radius: 8px; background: var(--accent-dim); border: 1px solid var(--accent); color: var(--accent); font-size: 11px; font-weight: 700; cursor: pointer; transition: all 0.2s; box-shadow: 0 0 10px rgba(20,184,166,0.2);">F</button>
                            <button class="modal-day-btn" data-day="Saturday" style="flex:1; height: 32px; border-radius: 8px; background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.1); color: var(--text-muted); font-size: 11px; font-weight: 700; cursor: pointer; transition: all 0.2s;">S</button>
                        </div>
                    </div>
                    
                    <div id="modal-time-container" style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                        <div>
                            <label style="display: block; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.15em; color: var(--accent); margin-bottom: 8px;">Start Time <span class="material-symbols-outlined" style="font-size: 14px; opacity: 0.5; margin-left: 6px; cursor: help; vertical-align: middle;" onmouseenter="showTooltip(event, 'Start Time', 'When the bot wakes up and starts looking for trades.')" onmouseleave="hideTooltip()">info</span></label>
                            <input type="time" id="modal-start" value="${existingSess ? existingSess.start_time : '09:30'}" class="input-field time-picker" style="width: 100%; color-scheme: dark;">
                        </div>
                        <div>
                            <label style="display: block; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.15em; color: var(--accent); margin-bottom: 8px;">End Time <span class="material-symbols-outlined" style="font-size: 14px; opacity: 0.5; margin-left: 6px; cursor: help; vertical-align: middle;" onmouseenter="showTooltip(event, 'End Time', 'When the bot stops taking new trades and manages existing ones.')" onmouseleave="hideTooltip()">info</span></label>
                            <input type="time" id="modal-end" value="${existingSess ? existingSess.end_time : '16:00'}" class="input-field time-picker" style="width: 100%; color-scheme: dark;">
                        </div>
                    </div>
                    
                    <div class="control-card" style="margin-top: 8px; margin-bottom: 0; padding: 16px; cursor: pointer;" id="modal-paper-row">
                        <div class="card-info" style="pointer-events: none;">
                            <span class="card-title">Off-Hours Simulation <span class="material-symbols-outlined" style="font-size: 14px; opacity: 0.5; margin-left: 6px; cursor: help; vertical-align: middle;" onmouseenter="showTooltip(event, 'Off-Hours Simulation', 'If enabled, when the bot goes to sleep outside its schedule, it will secretly switch to Paper Trading to practice and gather data instead of actually doing nothing.')" onmouseleave="hideTooltip()">info</span></span>
                            <span class="card-desc">Trade in paper mode while sleeping</span>
                        </div>
                        <div class="card-control no-drag">
                            <div class="toggle" id="modal-paper"></div>
                        </div>
                    </div>
                </div>
                
                <div style="display: flex; justify-content: flex-end; gap: 12px; margin-top: 32px;">
                    <button id="btn-modal-cancel" style="padding: 12px 24px; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em; border-radius: 12px; background: transparent; border: 1px solid rgba(255,255,255,0.1); color: var(--text-secondary); cursor: pointer; transition: all 0.2s;">Cancel</button>
                    <button id="btn-modal-save" style="padding: 12px 24px; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em; border-radius: 12px; background: linear-gradient(135deg, var(--accent) 0%, var(--accent-hover) 100%); color: #000; border: none; cursor: pointer; transition: all 0.2s; box-shadow: 0 4px 20px var(--accent-glow);">Confirm</button>
                </div>
            </div>
        `;
        
        document.body.appendChild(overlay);
        
        const modeSelect = overlay.querySelector('#modal-mode');
        const timeContainer = overlay.querySelector('#modal-time-container');
        const daysContainer = overlay.querySelector('#modal-days-container');
        const dateContainer = overlay.querySelector('#modal-date-container');
        
        function updateVisibility() {
            const val = modeSelect.value;
            timeContainer.style.display = val === '24/7' ? 'none' : 'grid';
            daysContainer.style.display = val === 'business_hours' ? 'block' : 'none';
            dateContainer.style.display = val === 'one_time' ? 'block' : 'none';
        }
        
        modeSelect.addEventListener('change', updateVisibility);
        updateVisibility();
        
        const dayBtns = overlay.querySelectorAll('.modal-day-btn');
        dayBtns.forEach(btn => {
            const dayName = btn.getAttribute('data-day');
            if (existingSess && existingSess.mode === 'business_hours') {
                if (!existingSess.days_of_week.includes(dayName)) {
                    btn.classList.remove('active');
                    btn.style.background = 'rgba(0,0,0,0.3)';
                    btn.style.border = '1px solid rgba(255,255,255,0.1)';
                    btn.style.color = 'var(--text-muted)';
                    btn.style.boxShadow = 'none';
                }
            }
            
            btn.addEventListener('click', (e) => {
                const isActive = btn.classList.contains('active');
                if (isActive) {
                    btn.classList.remove('active');
                    btn.style.background = 'rgba(0,0,0,0.3)';
                    btn.style.border = '1px solid rgba(255,255,255,0.1)';
                    btn.style.color = 'var(--text-muted)';
                    btn.style.boxShadow = 'none';
                } else {
                    btn.classList.add('active');
                    btn.style.background = 'var(--accent-dim)';
                    btn.style.border = '1px solid var(--accent)';
                    btn.style.color = 'var(--accent)';
                    btn.style.boxShadow = '0 0 10px rgba(20,184,166,0.2)';
                }
            });
        });
        
        const paperRow = overlay.querySelector('#modal-paper-row');
        const paperCheck = overlay.querySelector('#modal-paper');
        paperCheck.is_active = existingSess ? existingSess.paper_trade_off_hours : false;
        if (paperCheck.is_active) {
            paperCheck.classList.add('toggle-active');
        }
        
        function togglePaper() {
            paperCheck.is_active = !paperCheck.is_active;
            paperCheck.classList.toggle('toggle-active', paperCheck.is_active);
        }
        
        paperRow.addEventListener('click', (e) => {
            e.stopPropagation();
            togglePaper();
        });
        
        overlay.querySelector('#btn-modal-cancel').addEventListener('click', () => {
            document.body.removeChild(overlay);
        });
        
        overlay.querySelector('#btn-modal-save').addEventListener('click', () => {
            const profile = overlay.querySelector('#modal-profile').value;
            const mode = overlay.querySelector('#modal-mode').value;
            const start = overlay.querySelector('#modal-start').value || "09:30";
            const end = overlay.querySelector('#modal-end').value || "16:00";
            const paper = paperCheck.is_active;
            const dateVal = overlay.querySelector('#modal-date').value;
            
            const activeDays = Array.from(dayBtns)
                                    .filter(btn => btn.classList.contains('active'))
                                    .map(btn => btn.getAttribute('data-day'));
            
            if (!configData.schedule) configData.schedule = {};
            if (!configData.schedule.sessions) configData.schedule.sessions = [];
            
            const scheduleObj = {
                id: existingSess ? existingSess.id : Math.random().toString(36).substr(2, 9),
                profile_name: profile,
                mode: mode,
                days_of_week: mode === 'business_hours' ? activeDays : ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
                weeks_of_month: existingSess ? existingSess.weeks_of_month : [1, 2, 3, 4, 5],
                specific_date: mode === 'one_time' ? dateVal : null,
                start_time: start,
                end_time: end,
                paper_trade_off_hours: paper
            };
            
            if (existingIdx >= 0) {
                configData.schedule.sessions[existingIdx] = scheduleObj;
            } else {
                configData.schedule.sessions.push(scheduleObj);
            }
            
            if (window.api && window.api.saveConfig) window.api.saveConfig(configData);
            document.body.removeChild(overlay);
            renderSessionsList();
        });
    }

    renderSessionsList();

    const addContainer = document.createElement('div');
    addContainer.style.cssText = 'margin-top: 16px; margin-bottom: 24px;';
    const btnAdd = document.createElement('button');
    btnAdd.style.cssText = 'width: 100%; padding: 14px; background: rgba(255, 255, 255, 0.03); border: 1px dashed rgba(255, 255, 255, 0.2); border-radius: 12px; color: var(--text-secondary); font-weight: 700; font-size: 11px; letter-spacing: 0.15em; text-transform: uppercase; cursor: pointer; transition: all 0.2s var(--transition-smooth); display: flex; justify-content: center; align-items: center; gap: 8px;';
    btnAdd.onmouseenter = () => { btnAdd.style.background = 'rgba(255, 255, 255, 0.06)'; btnAdd.style.borderColor = 'var(--accent-dim)'; btnAdd.style.color = 'var(--text-main)'; };
    btnAdd.onmouseleave = () => { btnAdd.style.background = 'rgba(255, 255, 255, 0.03)'; btnAdd.style.borderColor = 'rgba(255, 255, 255, 0.2)'; btnAdd.style.color = 'var(--text-secondary)'; };
    btnAdd.innerHTML = '<span class="material-symbols-outlined" style="font-size: 18px;">add</span> Add Profile Schedule';
    btnAdd.addEventListener('click', openAddScheduleModal);
    addContainer.appendChild(btnAdd);

    section.appendChild(sessionsContainer);
    section.appendChild(addContainer);

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
    section.appendChild(createCard('Macro Correlation Stacking', 'Allow simultaneous entries on correlated pairs (e.g., EURUSD + GBPUSD)', 'TREND_CORRELATION_STACKING_ENABLED', 'toggle', { default: 'true' }));
    section.appendChild(createCard('ADX — Trend Strength Gate', 'Blocks entries when market has no clear trend (ADX < threshold)', 'TREND_ADX_ENABLED', 'toggle', { default: 'true' }));
    section.appendChild(createSliderCard('ADX Threshold', 'Entries blocked below this ADX value (0 = disabled)', 'TREND_ADX_THRESHOLD', 0, 60, 1, ''));
    section.appendChild(createCard('Block Ranging Regimes', 'Stand aside during choppy/ranging markets instead of attempting to trade.', 'BLOCK_RANGING_REGIME', 'toggle', { default: 'true' }));

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
    section.appendChild(createCard('Rollover Deadzone', 'Block entries during 5 PM EST spread spike', 'SAFETY_ROLLOVER_DEADZONE_ENABLED', 'toggle', { default: 'true' }));
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

function getValue(key, strategyNamespace = null) {
    // 1. Check Secrets
    if (SECRETS_MAP[key]) {
        return secretsData[SECRETS_MAP[key]] || '';
    }

    // 2. Fallback to Global Config
    if (CONFIG_MAP[key]) {
        const path = CONFIG_MAP[key];
        let current = configData;
        for (let i = 0; i < path.length - 1; i++) {
            if (!current[path[i]]) return undefined; // Path does not exist
            current = current[path[i]];
        }
        const value = current[path[path.length - 1]];
        if (value === undefined) return undefined;
        return value === true ? 'true' : value === false ? 'false' : String(value);
    }

    // 3. Fallback to envData (for values not in config/secrets, e.g., dynamically set ones)
    const value = envData[key];
    if (value === undefined) return undefined;
    return value === true ? 'true' : value === false ? 'false' : String(value);
}


function updateValue(key, value, strategyNamespace = null) {
    const oldValue = getValue(key, strategyNamespace);
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
    const tooltipHeight = popup.offsetHeight;
    const windowWidth = window.innerWidth;
    const windowHeight = window.innerHeight;
    const gap = 16;

    // Default: Position to the right
    let leftPos = rect.right + gap;
    let topPos = rect.top;

    // Collision detection: If generic right position + width exceeds window width, flip to left
    if (leftPos + tooltipWidth > windowWidth - 20) { // 20px safety buffer
        leftPos = rect.left - tooltipWidth - gap;
    }

    // Collision detection: If generic bottom position + height exceeds window height, shift up
    if (topPos + tooltipHeight > windowHeight - 20) {
        topPos = windowHeight - tooltipHeight - 20;
    }

    // Secondary sanity check in case tooltip height is massive
    if (topPos < 20) topPos = 20;

    popup.style.left = `${leftPos}px`;
    popup.style.top = `${topPos}px`;
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
        { id: 'crypto_grid', label: 'Virtual Grid', icon: 'grid_on', color: '#a78bfa' },
        // 📈 Advanced Quantitative Strategies
        { id: 'qs_sma_filter', label: 'QS SMA Filter', icon: 'filter_alt', color: '#38bdf8' },
        { id: 'qs_golden_cross', label: 'QS Golden Cross', icon: 'timeline', color: '#fcd34d' },
        { id: 'qs_rsi_mean_reversion', label: 'QS RSI-2 MR', icon: 'multiline_chart', color: '#2dd4bf' },
        { id: 'qs_3_10_trend', label: 'QS 3/10 Trend', icon: 'insights', color: '#a78bfa' },
        { id: 'qs_tqqq_btal', label: 'QS TQQQ/BTAL', icon: 'pie_chart', color: '#f472b6' },
        { id: 'qs_choppiness', label: 'QS Choppiness', icon: 'waves', color: '#fb923c' },
        { id: 'qs_first_day_month', label: 'QS Seasonal FDOM', icon: 'calendar_month', color: '#4ade80' }
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

        section.appendChild(createCard('ICC Auto-Entry', 'Let the bot trade this automatically', 'ICC_AUTO_ENTRY_ENABLED', 'toggle', { 
            default: 'true',
            tooltip: "When turned on, the bot has your permission to automatically open trades whenever it sees a picture-perfect trend pullback. If you turn this off, it will only watch the market and wait for you to manually make the final call."
        }));
        section.appendChild(createCard('Aggressive Mode', 'Take bolder, larger trades', 'ICC_AGGRESSIVE_MODE', 'toggle', { 
            default: 'true',
            tooltip: "When turned on, the bot will risk a little more money on trades it feels extremely confident about. It's like pressing the gas pedal when the road is completely clear. Turn this off if you want it to drive the speed limit no matter what."
        }));
        section.appendChild(createCard('Require Sweep', 'Wait for the market to trap others', 'ICC_AUTO_ENTRY_REQUIRE_SWEEP', 'toggle', {
            tooltip: "When turned on, the bot will patiently wait to see other impatient traders get trapped and lose their money first before it enters the trade. It's a very safe, sneaky way to trade, but you might miss out on fast-moving trains."
        }));
        section.appendChild(createSliderCard('Min HTF Strength', 'How strong the big picture trend must be', 'ICC_AUTO_ENTRY_MIN_HTF_STRENGTH', 0, 100, 5, '%', { tooltip: 'The minimum strength required from the overall market trend before the bot will consider taking a trade.' }));
        section.appendChild(createSliderCard('Confirmation Bars', 'Candles to wait before jumping in', 'ICC_CONFIRMATION_BARS', 1, 5, 1, 'bars', { tooltip: 'How many candles the bot waits after seeing a signal to make sure it is a real move and not a fakeout.' }));

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('ICC Scoring Weights', 'leaderboard',
            "<strong>ICC Scoring Weights</strong><br><br>How many points each signal component contributes to the overall ICC score. Higher scores mean more conviction. The entry threshold determines the minimum score needed before the bot places a trade."
        ));

        section.appendChild(createSliderCard('Entry Score Threshold', 'Minimum score for entry', 'ICC_ENTRY_SCORE_THRESHOLD', 0, 100, 5, 'pts', { tooltip: 'The passing grade a trade setup must achieve before the bot will pull the trigger. 80 is usually an A+ setup.' }));

        const scoreGrid = document.createElement('div');
        scoreGrid.className = 'card-grid';
        scoreGrid.appendChild(createSliderCard('Continuation', 'Points for continuation', 'ICC_SCORE_CONTINUATION_POINTS', 0, 100, 5, 'pts', { tooltip: 'Points awarded if the setup aligns with a successful push in the main trend direction.' }));
        scoreGrid.appendChild(createSliderCard('Sweep', 'Points for liquidity sweep', 'ICC_SCORE_SWEEP_POINTS', 0, 50, 5, 'pts', { tooltip: 'Points awarded if the market just trapped a bunch of amateur traders trying to pick a top or bottom.' }));
        scoreGrid.appendChild(createSliderCard('HTF/LTF Align', 'Points for alignment', 'ICC_SCORE_HTF_LTF_ALIGN_POINTS', 0, 50, 5, 'pts', { tooltip: 'Points awarded when both the big picture (HTF) and small picture (LTF) timeframes completely agree.' }));
        scoreGrid.appendChild(createSliderCard('Strong HTF', 'Points for strong trend', 'ICC_SCORE_STRONG_HTF_POINTS', 0, 30, 5, 'pts', { tooltip: 'Bonus points if the overarching massive market trend is extremely powerful right now.' }));
        scoreGrid.appendChild(createSliderCard('Phase', 'Points for good phase', 'ICC_SCORE_PHASE_POINTS', 0, 20, 5, 'pts', { tooltip: 'Points awarded if we are correctly catching the pullback phase rather than chasing the extended phase.' }));
        scoreGrid.appendChild(createSliderCard('Indication', 'Points for indication', 'ICC_SCORE_INDICATION_POINTS', 0, 20, 5, 'pts', { tooltip: 'Points awarded if the initial strong move (Indication) that started the pattern was unusually aggressive or large.' }));
        section.appendChild(scoreGrid);
    } else if (toolboxTab === 'rubberband_reaper') {
        const stratInfo = STRATEGIES.rubberband_reaper;
        section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'tune', `<strong>${stratInfo.name}</strong><br><br>${stratInfo.description}`));

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
            tooltip: "How far back in time the bot looks to figure out what 'normal' price movement is right now. A smaller number reacts faster, while a larger number is smoother and more patient."
        }));
        section.appendChild(createCard('Std Dev', 'Width multiplier', 'BB_STD', 'input', {
            number: true,
            default: '2.5',
            tooltip: "How far price has to stretch away from 'normal' before the Rubberband snaps back. A higher number like 3.0 means it waits for a massive, rare stretch. A lower number like 2.0 triggers more often but might get it wrong more."
        }));

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('RSI Config', 'ssid_chart'));

        section.appendChild(createCard('Period', 'RSI Lookback', 'RSI_PERIOD', 'input', {
            number: true,
            default: '14',
            tooltip: "How many recent candles the bot looks at to judge if buyers or sellers are exhausted. 14 is the industry standard."
        }));
        section.appendChild(createCard('Overbought', 'Short threshold', 'RSI_OVERBOUGHT', 'input', {
            number: true,
            default: '75',
            tooltip: "When the market is buying too much, too fast, this is the number that tells the bot the buyers are probably exhausted and a drop is coming."
        }));
        section.appendChild(createCard('Oversold', 'Long threshold', 'RSI_OVERSOLD', 'input', {
            number: true,
            default: '25',
            tooltip: "When the market is selling too much, too fast, this is the number that tells the bot the sellers are probably exhausted and a bounce is coming."
        }));

    } else if (toolboxTab === 'supply_demand') {
        const stratInfo = STRATEGIES.supply_demand;
        section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'account_balance_wallet', `<strong>${stratInfo.name}</strong><br><br>${stratInfo.description}`));

        section.appendChild(createWarningBox(`
            <strong>Institutional Logic:</strong><br>
            Supply & Demand focuses on "Unfilled Orders". It ignores minor noise and only enters when price returns to a high-probability zone after a solid Break of Structure (BOS).
        `));

        section.appendChild(createCard('RR Target', 'Reward-to-Risk Goal', 'SND_RR_TARGET', 'input', {
            number: true,
            default: '2.0',
            tooltip: "When the bot finds a great zone, this is how much profit it tries to capture compared to what it risks. A 2.0 means if it risks $10, it tries to make $20."
        }));

        section.appendChild(createCard('Zone Window', 'Candle Lookback for Zones', 'SND_ZONE_WINDOW', 'input', {
            number: true,
            default: '100',
            tooltip: "How far back in history the bot will scan to find powerful, unfilled institutional orders. A bigger number finds older, stronger zones."
        }));

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('Advanced SND Filters', 'military_tech'));

        section.appendChild(createCard('Max Daily Trades', 'Daily Trade Cap', 'MAX_DAILY_TRADES', 'input', {
            number: true,
            default: '20',
            tooltip: "A safety brake that tells the bot to stop trading for the day if it has taken this many trades. It prevents the bot from overworking in messy markets."
        }));

    } else if (toolboxTab === 'meta_sci') {
        const stratInfo = STRATEGIES.meta_sci;
        section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'hub', `<strong>${stratInfo.name}</strong><br><br>${stratInfo.description}`));

        section.appendChild(createWarningBox(`
            <strong>Ensemble Master:</strong><br>
            Meta-SCI does not use its own logic. It orchestrates all other strategies in parallel. 
            The configuration below determines how it selects the "Winning" signal when multiple strategies agree.
        `));

        section.appendChild(createCard('Meta-SCI Active', 'Orchestrate all strategies in parallel', 'META_SCI_ENABLED', 'toggle', {
            tooltip: "Turn this on to let Meta-SCI act like the boss of all the other strategies. Instead of one strategy deciding to trade, Meta-SCI asks all of them for their opinion and only trades when they agree."
        }));
        section.appendChild(createCard('Min Consensus', 'Min strategies that must agree', 'META_SCI_MIN_CONSENSUS', 'input', {
            number: true,
            default: '1',
            min: 1,
            max: 5,
            tooltip: "How many different strategies have to agree on a trade before Meta-SCI actually pulls the trigger. Setting this to 1 means it just takes the loudest voice in the room. Setting it higher is safer but trades less often."
        }));

        section.appendChild(createCard('Strategy Blacklist', 'Comma-separated IDs to ignore', 'META_SCI_EXCLUDE_LIST', 'input', {
            default: '',
            tooltip: "Type the names of any strategies you want Meta-SCI to completely ignore when it's asking for opinions around the room."
        }));

    } else if (toolboxTab === 'orb_breakout') {
        const stratInfo = STRATEGIES.orb_breakout;
        section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'rule', `<strong>${stratInfo.name}</strong><br><br>${stratInfo.description}`));

        section.appendChild(createWarningBox(`
            <strong>Break & Retest Strategy:</strong><br>
            Trades the NY Opening Range (09:30 - 09:45 ET). Waits for Break -> Retest -> Flag pattern.
        `));

        section.appendChild(createCard('Session Start', 'Range start time (ET)', 'ORB_START_TIME', 'time', {
            default: '09:30',
            tooltip: "The exact time in the morning when the opening bell rings and the wild trading begins. Usually 09:30 AM Eastern Time."
        }));
        section.appendChild(createCard('Duration (Min)', 'Length of the Range', 'ORB_DURATION', 'input', {
            number: true,
            default: '15',
            tooltip: "How many minutes the bot should patiently watch the morning chaos to figure out the high and low boundaries before it starts hunting for breakouts."
        }));
        section.appendChild(createCard('Risk %', 'Risk per trade', 'ORB_RISK_PCT', 'input', {
            number: true,
            default: '1.0',
            tooltip: "How much of your account money you're willing to lose if this morning breakout trade goes wrong. 1.0 means 1%."
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
        section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'local_police', `<strong>${stratInfo.name}</strong><br><br>${stratInfo.description}`));

        section.appendChild(createWarningBox(`
            <strong>High Frequency Trading:</strong><br>
            RoboCop is designed for speed. Use "Combat Mode" to bypass safety checks (like HTF alignment) for maximum aggression.
        `));

        section.appendChild(createCard('Combat Mode', 'Bypass RoboCop HTF/Score gates only', 'COMBAT_MODE_ENABLED', 'toggle', {
            tooltip: "When turned on, RoboCop ignores the big picture trend and its own safety checks to take every single fast signal it sees. It's extremely aggressive, like speeding with the seatbelt off. Only use this in wild and choppy markets where fast trades win."
        }));

        section.appendChild(createDivider());
        section.appendChild(createSectionHeader('Aggressive Targets', 'gps_fixed'));

        section.appendChild(createCard('Confirmation Bars', 'Bars to wait', 'CONFIRMATION_BARS', 'input', {
            number: true,
            default: '1',
            min: 1, limit: 3,
            tooltip: "How many candles RoboCop waits after seeing a signal before jumping in. 1 means it shoots first and asks questions later. Higher numbers mean it waits to make sure it's not a head-fake."
        }));
        section.appendChild(createCard('Stop ATR Buffer', 'Protection width buffer', 'STOP_ATR_BUFFER', 'input', {
            number: true,
            default: '0.2',
            tooltip: "A tiny bit of extra breathing room added to the stop loss so market noise doesn't accidentally trigger it before the real move happens."
        }));
        section.appendChild(createCard('Guillotine Cut %', 'Scale-out fraction when losing', 'GUILLOTINE_CUT_PCT', 'input', {
            number: true,
            default: '0.80',
            tooltip: "When a trade goes bad and hits this percentage of the way to the stop loss, the bot gets scared and chops off 95% of the trade early to save your money instead of waiting for the full loss."
        }));
        section.appendChild(createCard('Chandelier Multiplier', 'Trailing stop volatility multiplier', 'CHANDELIER_MULT', 'input', {
            number: true,
            default: '2.0',
            tooltip: "Once the trade is in deep profit, the bot sets a trailing stop to follow the price up. This number tells it how closely to hug the price. 2.0 is a wide hug, giving it room to breathe."
        }));

    } else if (toolboxTab === 'evolution') {
        const stratInfo = STRATEGIES.evolution;
        section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'smart_toy', `<strong>${stratInfo.name}</strong><br><br>${stratInfo.description}`));

        section.appendChild(createCard('Stop ATR Mult', 'Volatility based stop', 'STOP_ATR_MULT', 'input', {
            number: true,
            default: '1.0',
            tooltip: "How much wiggle room the trade gets based on how crazy the market is acting right now. 1.0 is standard – it survives normal bumps without dying early."
        }));
        section.appendChild(createCard('Chandelier Trail Multiplier', 'Trailing stop volatility multiplier', 'CHANDELIER_MULT', 'input', {
            number: true,
            default: '2.0',
            tooltip: "Once the trade is in deep profit, the bot sets a trailing stop to follow the price up. This number tells it how closely to hug the price. 2.0 is a wide hug, giving it room to breathe."
        }));

    } else if (toolboxTab === 'quantum') {
        const stratInfo = STRATEGIES.quantum;
        section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'science', `<strong>${stratInfo.name}</strong><br><br>${stratInfo.description}`));

        section.appendChild(createCard('SMA Period', 'Trend baseline', 'QUANTUM_SMA_PERIOD', 'input', {
            number: true,
            default: '20',
            tooltip: "The moving average line that Quantum uses as the 'center of gravity'. It waits for price to snap back to this line before firing."
        }));
        section.appendChild(createCard('Stop ATR Mult', 'Protection width', 'QUANTUM_STOP_ATR_MULT', 'input', {
            number: true,
            default: '2.5',
            tooltip: "Quantum uses a very wide safety net (2.5) because it's trying to ride massive, long-term waves and doesn't want to get shaken off by normal ripples."
        }));
        section.appendChild(createCard('Target R', 'Profit target', 'QUANTUM_TARGET_R', 'input', {
            number: true,
            default: '1.6',
            tooltip: "Since Quantum is trading very large moves, a smaller target like 1.6 still brings in good money while keeping the win rate high."
        }));

    } else if (toolboxTab === 'forex_conductor') {
        const stratInfo = STRATEGIES.forex_conductor;
        section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'orchestration',
            "<strong>Forex Conductor</strong><br><br>The Conductor orchestrates sub-strategies (Trend Rider, Mean Reversion) and manages entries, exits, and risk. SAR (Stop And Reverse) automatically flips direction after a losing trade when conditions support a reversal — preventing consecutive losses in the same direction."
        ));

        section.appendChild(createCard('Quick Ranging TP', 'Cap profits at 0.7R during choppy/ranging sessions', 'QUICK_RANGING_TP_ENABLED', 'toggle', {
            default: 'false',
            tooltip: "When the market is boring and just bouncing up and down in a tight tunnel, the bot usually just gets stopped out waiting for a big move. Turn this ON to tell the bot to settle for small, quick profits during the boring times."
        }));

        section.appendChild(createCard('Tick Scalping', 'Exit immediately on ANY net profit', 'TICK_SCALPING_ENABLED', 'toggle', {
            default: 'false',
            tooltip: "Instantly closes any trade the moment it reaches net profit (covering spread). Does not let the bot ride trades."
        }));

        section.appendChild(createCard('Min Scalp Profit ($)', 'Minimum net USD before scalping', 'TICK_SCALPING_MIN_USD', 'input', {
            number: true,
            default: '0.0',
            tooltip: "The absolute minimum profit in dollars to accept before bailing out. If set to 2.0, the bot will wait until it clears the spread AND makes $2.00 before closing the trade."
        }));


    } else if (toolboxTab === 'hyper_scalper') {
        const stratInfo = STRATEGIES.hyper_scalper;
        section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'speed', `<strong>${stratInfo.name}</strong><br><br>${stratInfo.description}`));

        section.appendChild(createCard('Fast EMA Period', 'Fast EMA line', 'FAST_EMA', 'input', { number: true, default: '9', tooltip: "How many recent candles to average to find the ultra-short-term momentum. 9 is standard." }));
        section.appendChild(createCard('Slow EMA Period', 'Slow EMA line', 'SLOW_EMA', 'input', { number: true, default: '21', tooltip: "The slightly slower moving average. When the fast line crosses the slow line, that's the trigger." }));
        section.appendChild(createCard('Trend EMA Period', 'Trend baseline', 'TREND_EMA', 'input', { number: true, default: '200', tooltip: "The massive baseline that tells the bot whether the big picture is going up or down. Never trade against this." }));
        section.appendChild(createCard('Stop ATR Mult', 'Stop distance', 'STOP_ATR_MULT', 'input', { number: true, default: '2.0', tooltip: "How wide the safety net should be based on market noise." }));

    } else if (toolboxTab === 'rubberband_reaper') {
        const stratInfo = STRATEGIES.rubberband_reaper;
        section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'architecture', `<strong>${stratInfo.name}</strong><br><br>${stratInfo.description}`));

        section.appendChild(createCard('BB Period', 'Bollinger Period', 'BB_PERIOD', 'input', { number: true, default: '20', tooltip: "How far back in time the bot looks to figure out what 'normal' price movement is right now." }));
        section.appendChild(createCard('BB StdDev', 'Bollinger Std', 'BB_STD', 'input', { number: true, default: '2.5', tooltip: "How far price has to stretch away from 'normal' before the Rubberband snaps back. A higher number like 3.0 means it waits for a massive, rare stretch." }));
        section.appendChild(createCard('RSI Period', 'RSI Lookback', 'RSI_PERIOD', 'input', { number: true, default: '7', tooltip: "How many recent candles the bot looks at to judge if buyers or sellers are exhausted. 7 is very fast and sensitive." }));
        section.appendChild(createCard('RSI Overbought', 'OB threshold', 'RSI_OVERBOUGHT', 'input', { number: true, default: '75', tooltip: "When the market is buying too much, too fast, this number tells the bot the buyers are exhausted." }));
        section.appendChild(createCard('RSI Oversold', 'OS threshold', 'RSI_OVERSOLD', 'input', { number: true, default: '25', tooltip: "When the market is selling too much, too fast, this number tells the bot the sellers are exhausted." }));

    } else if (toolboxTab === 'supply_demand') {
        const stratInfo = STRATEGIES.supply_demand;
        section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'account_balance'));

        section.appendChild(createCard('Zone Lookback', 'Candles to check for BOS', 'ZONE_WINDOW', 'input', { number: true, default: '100', tooltip: "How far back in history the bot will scan to find powerful, unfilled institutional orders." }));

    } else if (toolboxTab === 'london_breakout') {
        const stratInfo = STRATEGIES.london_breakout;
        section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'timer', `<strong>${stratInfo.name}</strong><br><br>${stratInfo.description}`));

        section.appendChild(createCard('Asian Start (UTC)', 'Asian session start', 'ASIAN_START', 'time', { default: '00:00', tooltip: "The exact time the boring, slow Asian trading session begins in UTC time." }));
        section.appendChild(createCard('Asian End (UTC)', 'Asian session end', 'ASIAN_END', 'time', { default: '06:00', tooltip: "The exact time the boring Asian session ends, drawing the 'box' that the bot will wait to break out of." }));
        section.appendChild(createCard('London Start (UTC)', 'London session start', 'LONDON_START', 'time', { default: '07:00', tooltip: "The exact time the London market opens and traders rush in, causing massive price spikes." }));
        section.appendChild(createCard('Stop Box Mult', 'Stop multiplier against box', 'STOP_BOX_MULT', 'input', { number: true, default: '0.5', tooltip: "How much of the Asian box width should act as the safety net (stop loss). 0.5 means half the box size." }));
        section.appendChild(createCard('Target Box Mult', 'Target multiplier against box', 'TARGET_BOX_MULT', 'input', { number: true, default: '1.5', tooltip: "How much profit it wants based on the Asian box size. 1.5 means it wants to make 1.5 times the size of the box." }));

    } else if (toolboxTab === 'mean_reversion') {
        const stratInfo = STRATEGIES.mean_reversion;
        section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'compare_arrows', `<strong>${stratInfo.name}</strong><br><br>${stratInfo.description}`));

        section.appendChild(createCard('BB Period', 'Bollinger Period', 'BB_PERIOD', 'input', { number: true, default: '20', tooltip: "How far back in time the bot looks to figure out what 'normal' price movement is right now." }));
        section.appendChild(createCard('BB StdDev', 'Bollinger Std', 'BB_STD', 'input', { number: true, default: '2.0', tooltip: "How far price has to stretch away from 'normal' before the bot expects a snap back to the middle." }));
        section.appendChild(createCard('RSI Period', 'RSI Lookback', 'RSI_PERIOD', 'input', { number: true, default: '14', tooltip: "How many recent candles the bot looks at to judge if buyers or sellers are exhausted." }));
        section.appendChild(createCard('RSI Overbought', 'OB threshold', 'RSI_OVERBOUGHT', 'input', { number: true, default: '70', tooltip: "When the market is buying too much, too fast, this number tells the bot the buyers are exhausted." }));
        section.appendChild(createCard('RSI Oversold', 'OS threshold', 'RSI_OVERSOLD', 'input', { number: true, default: '30', tooltip: "When the market is selling too much, too fast, this number tells the bot the sellers are exhausted." }));

    } else if (toolboxTab === 'crypto_vwap_reversion') {
        const stratInfo = STRATEGIES.crypto_vwap_reversion;
        if (stratInfo) {
            section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'timeline', `<strong>${stratInfo.name}</strong><br><br>${stratInfo.description}`));
            section.appendChild(createCard('EMA Period', 'Trend EMA', 'EMA_PERIOD', 'input', { number: true, default: '20', tooltip: "The baseline that tells the bot the general direction of the market." }));
            section.appendChild(createCard('RSI Period', 'RSI Check', 'RSI_PERIOD', 'input', { number: true, default: '14', tooltip: "How many recent candles the bot looks at to judge if buyers or sellers are exhausted." }));
            section.appendChild(createCard('RSI Long Threshold', 'Max RSI for Long', 'RSI_LONG_THRESHOLD', 'input', { number: true, default: '40', tooltip: "The bot won't buy unless the RSI is below this number, proving the asset is 'on sale'." }));
            section.appendChild(createCard('VWAP Dev %', 'VWAP deviation', 'VWAP_DEVIATION_PCT', 'input', { number: true, default: '0.003', tooltip: "How far price must stretch away from the massive daily volume average (VWAP) before the bot claims it's overstretched." }));
        }

    } else if (toolboxTab === 'icc_core_standalone') {
        const stratInfo = STRATEGIES.icc_core_standalone;
        section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'precision_manufacturing', `<strong>${stratInfo.name}</strong><br><br>${stratInfo.description}`));

        section.appendChild(createCard('Target R', 'Target R ratio', 'TARGET_R', 'input', { number: true, default: '2.0', tooltip: "How much profit it wants compared to the risk. 2.0 means it wants double what it risks." }));
        section.appendChild(createCard('Stop ATR Mult', 'Stop buffer', 'STOP_ATR_MULT', 'input', { number: true, default: '1.5', tooltip: "How much extra 'wiggle room' is added to the stop loss based on normal market volatility." }));
        section.appendChild(createCard('Entry Cooldown', 'Bars to wait between entries', 'ENTRY_COOLDOWN_BARS', 'input', { number: true, default: '8', tooltip: "After taking a trade, how many candles it has to wait before it's allowed to take another one." }));

    } else if (toolboxTab === 'crypto_grid') {
        const stratInfo = STRATEGIES.crypto_grid;
        if (stratInfo) {
            section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'grid_on', `<strong>${stratInfo.name}</strong><br><br>${stratInfo.description}`));
            section.appendChild(createCard('Grid ATR Mult', 'Grid spacing mult', 'GRID_ATR_MULT', 'input', { number: true, default: '1.5', tooltip: "How far apart (based on market volatility) your layered entry orders will be placed." }));
            section.appendChild(createCard('Grid Levels', 'Levels to deploy', 'GRID_LEVELS', 'input', { number: true, default: '5', tooltip: "How many separate orders the bot will place in the grid to catch deep pullbacks." }));
            section.appendChild(createCard('Trend Guard', 'Max HTF trend strength', 'TREND_GUARD_THRESHOLD', 'input', { number: true, default: '0.5', tooltip: "The bot won't build a grid if the massive overall trend is violently moving the wrong way. 0.5 is a standard caution level." }));
        }

    } else if (toolboxTab === 'yoyo') {
        const stratInfo = STRATEGIES.yoyo;
        if (stratInfo) {
            section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'wifi_tethering', `<strong>${stratInfo.name}</strong><br><br>${stratInfo.description}`));
            section.appendChild(createCard('SMA Period', 'Trend Filter', 'SMA_PERIOD', 'input', { number: true, default: '50', tooltip: "The baseline that tells the bot the general direction of the market." }));
            section.appendChild(createCard('Risk Escalation', 'Risk to add per win', 'RISK_ESCALATION', 'input', { number: true, default: '0.01', tooltip: "Every time the bot wins, it adds this much extra risk to the next trade to snowball profits." }));
            section.appendChild(createCard('Max Risk', 'Hard cap risk %', 'MAX_RISK_PCT', 'input', { number: true, default: '0.05', tooltip: "The absolute maximum percentage of your account YoYo is allowed to risk, no matter how many times it wins." }));
        }

    } else {
        // Generic fallback for others (Bearish Engulfing, Volatility Breakout, etc)
        const stratInfo = STRATEGIES[toolboxTab];
        if (stratInfo) {
            section.appendChild(createSectionHeader(`${stratInfo.name} Configuration`, 'tune', `<strong>${stratInfo.name}</strong><br><br>${stratInfo.description}`));

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
    const dot = document.getElementById('status-dot');
    const text = document.getElementById('status-text');

    if (!dot || !text) return;

    if (isRunning) {
        dot.className = 'w-2 h-2 rounded-full bg-teal-500 shadow-[0_0_10px_rgba(20,184,166,0.8)]';
        text.textContent = 'Status: Connected';
        text.className = 'text-[10px] font-black uppercase tracking-widest text-teal-400';
    } else {
        dot.className = 'w-2 h-2 rounded-full bg-slate-500 animate-pulse';
        text.textContent = 'Status: Disconnected';
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

