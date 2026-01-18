# Environment Variable Reference

This document provides comprehensive details for each environment variable used by Tradebot SCI, including its purpose, usage, and meaningful defaults.

---

## GUI Settings

| Environment Variable | Description |
|----------------------|-------------|
| `GUI_AUTOSTART_BOT` | **Automatically start the core bot process when the GUI opens.**<br>On GUI launch, the app checks whether the bot is already running. If it is NOT running, the GUI starts it using your current settings. If it IS already running, the GUI attaches to the existing logs/state. |
| `GUI_KEEP_BOT_RUNNING` | **Keep the bot running even after you close the GUI window.**<br>Use this if you want a desktop view temporarily but want the bot to keep running in the background (or in tmux). |
| `GUI_LOG_BROWSE` | **Pick which log file the GUI (and tmux log tail) reads.**<br>Choose the active log (usually `logs/tradebot.log`) or a rotated file for historical context. |
| `TMUX_RESTART_PREVIEW` | **Shows the exact tmux restart command that will be executed.**<br>Review this before clicking "Restart tmux" to verify flags and settings. |
| `GUI_BROWSE_SYNTH_STOP_STORE` | **Choose where to store synthetic stop state on disk.**<br>Persists synthetic stop details (e.g. for ZEROHASH) so the bot can manage positions safely after restarts. |
| `GUI_BROWSE_POSITION_HOLD_STORE` | **Choose where to store position-hold/age state on disk.**<br>Persists "hold rules" across restarts. |
| `ENV_FILTER` | **Filter the Advanced env table by key.**<br>Type part of a key (case-insensitive) like `IBKR_` or `CCXT_`. |
| `ENV_TABLE_EDIT` | **Advanced mode: edit raw environment variables directly.**<br>Double-click a Value cell to edit. Be careful changing broker/live-trading keys here. |

## Profile-Related Settings

| Environment Variable | Description |
|----------------------|-------------|
| `PROFILE_NAME` | **Pick a profile that defines how the bot behaves.**<br>Controls symbol universe, timeframe, scan cadence, and risk defaults. (e.g., `intraday`, `crypto_247`, `auto_schedule`). |
| `PROFILE_HTF_TIMEFRAME` | **Override the Higher Timeframe (HTF) used for ICC structure trend.**<br>Default is `4h` unless profile specifies otherwise. |
| `PROFILE_LTF_TIMEFRAME` | **Override the Lower Timeframe (LTF) used for ICC execution.**<br>Default is usually `15m` or `5m`. |
| `PROFILE_TREND_WINDOW` | **Number of candles used to classify HTF structure trend.**<br>Larger windows reduce noise but respond slower. |
| `PROFILE_LTF_TREND_WINDOW` | **Number of candles used to classify LTF structure trend.**<br>Keeps LTF aligned to recent structure. |
| `PROFILE_TREND_SWING_LOOKBACK` | **Fractal lookback for defining swing highs/lows.**<br>Higher lookback requires more separation between swings. |
| `PROFILE_TREND_MIN_SWINGS` | **Minimum confirmed swings needed to call a trend.**<br>Higher values mean stronger confirmation but fewer trades. |
| `PROFILE_TREND_STRENGTH_FLOOR` | **Minimum structure strength to treat a trend as non-neutral.**<br>Based on consistency of HH/HL or LH/LL sequences. |
| `PROFILE_STRUCTURE_SCORE_THRESHOLD` | **Score threshold for structure cleanliness (ICC gating).**<br>Influences selection/readiness scoring. |
| `PROFILE_PDT_GUARD_ENABLED` | **Enable the PDT guard for equities.**<br>Limits same-day roundtrips for accounts under $25k. |
| `PROFILE_MAX_EQUITY_ROUNDTRIPS_PER_DAY`| **Maximum equity roundtrips allowed per day.**<br>Keep low (e.g., 3) unless exempt from PDT rules. |
| `PROFILE_FLIP_ACTIONS_ENABLED` | **Allow flip_to_long / flip_to_short actions.**<br>Reserved for confirmed HTF structure flips. Disabled by default for safety. |
| `PROFILE_FLIP_COOLDOWN_SECONDS` | **Minimum seconds between flips when PDT guard is active.**<br>Prevents churn in chop zones. |
| `PROFILE_COOLDOWN_ENABLED` | **Enable ICC cooldowns after blocks or successes.**<br>Helps avoid re-entering during chop or failed attempts. |
| `PROFILE_COOLDOWN_CYCLES_AFTER_BLOCK` | **Cycles to skip after a blocked attempt.**<br>Reduces churn during noisy phases. |
| `PROFILE_COOLDOWN_CYCLES_AFTER_SUCCESS`| **Cycles to skip after a successful entry.**<br>Reduces over-trading. |
| `PROFILE_COOLDOWN_SCOPE` | **Cooldown scope (symbol vs global).**<br>Use `symbol` for broad scanning, `global` for hard pauses. |
| `PROFILE_STICK_TO_ACTIVE_SYMBOL_UNTIL` | **Stick to active symbol until cycle_end or decision_end.**<br>Reduces churn when a structure is close to forming. |
| `PROFILE_AUTO_SCHEDULE_ENABLED` | **Enable auto-schedule (equities in US hours, crypto off-hours).**<br>Aligns bot with market hours automatically. |
| `PROFILE_AUTO_FLATTEN_ON_CLOSE` | **Auto-flatten at end of scheduled windows.**<br>Avoid if holding ICC continuations overnight. |
| `PROFILE_CONTINUOUS_MODE` | **Keep runtime loop alive regardless of iteration limits.**<br>Best for always-on monitoring. |
| `PROFILE_CRYPTO_ONLY` | **Treat profile as crypto-only.**<br>Useful for off-hours ICC execution. |
| `PROFILE_ICC_AGGRESSIVE_MODE` | **Enable aggressive ICC sizing + guardrails.**<br>Defaults to `true` (Trade By SCI posture). |
| `PROFILE_AGGRESSIVE_RISK_PER_TRADE_PCT`| **Risk per trade in aggressive mode.**<br>Default 3% (0.03). |
| `PROFILE_MAX_DAILY_LOSS_PCT` | **Max daily loss % before blocking.**<br>Default 6% (0.06). |
| `PROFILE_MAX_EXPOSURE_PCT` | **Max total open exposure %.**<br>Default 40% (0.40). |
| `PROFILE_MAX_CONSECUTIVE_LOSSES` | **Consecutive loss limit before blocking.**<br>Default 2 losses. |

## Bot Runtime & General Settings

| Environment Variable | Description |
|----------------------|-------------|
| `BOT_MODE` | **Runtime mode.**<br>`continuous`: runs forever. `scheduled`: runs inside windows. `iterations`: runs N loops. |
| `BOT_ITERATIONS` | **Number of cycles for `iterations` mode.**<br>Use small numbers (20-200) for testing. |
| `EXECUTE_TRADES` | **Master switch for live order placement.**<br>`true` = live orders allowed (with confirmation). `false` = simulation/dry-run. |
| `BOT_SABBATH` | **Sabbath entry blocking control.**<br>`Auto` (default), `Force ON`, or `Force OFF`. |
| `APP_ENVIRONMENT` | **Environment tag (dev/staging/prod).**<br>Optional labeling for config loaders. |
| `LOG_LEVEL` | **Log verbosity.**<br>`INFO`, `DEBUG`, `WARNING`, `ERROR`. |
| `TRADEBOT_LOG` | **Path to main log file.**<br>Defaults to `logs/tradebot.log`. |
| `SESSION_NAME` | **tmux session name.**<br>Defaults to `tradebot`. |
| `EMERGENCY_STOP_PCT` | **Emergency protective stop %.**<br>Last-resort safety net (not ICC invalidation). |
| `AUTO_RESTART_ON_ERROR` | **Auto-restart if IBKR health is stuck.**<br>Watches for stale account summary updates. |
| `AUTO_RESTART_STALE_SECONDS` | **Stale threshold for auto-restart.**<br>Default 300s. |
| `AUTO_RESTART_MIN_UPTIME_SECONDS` | **Min uptime before allowing restart.**<br>Prevents boot loops. |
| `AUTO_RESTART_COOLDOWN_SECONDS` | **Min seconds between restarts.**<br>Prevents rapid cycling. |
| `SCALE_OUT_FRACTION` | **Fraction to sell when scaling out.**<br>e.g. 0.5 = sell half. |
| `MAX_SCALE_INS_PER_LEG` | **Max additions (pyramiding) per leg.**<br>Start low (0-2) to manage risk. |
| `MIN_POSITION_SIZE_TO_SCALE` | **Min size required to allow scaling.**<br>Prevents managing dust. |
| `STARTUP_CRYPTO_UNPROTECTED_POLICY` | **Action for unprotected crypto positions on startup.**<br>`REARM` (preferred), `PAUSE`, `FLATTEN`. |
| `SYNTH_STOP_STORE_PATH` | **Path for synthetic stop JSON.**<br>Critical for ZEROHASH safety. |
| `POSITION_HOLD_STORE_PATH` | **Path for position age JSON.**<br>Tracks hold times across restarts. |
| `ALLOW_INHERITED_POSITION` | **Manage pre-existing broker positions.**<br>Enable to adopt manual trades or existing inventory. |
| `CANCEL_ORDERS_ON_START` | **Cancel pending orders on startup.**<br>Cleanup safety measure. |
| `FLATTEN_ON_EXIT` | **Flatten positions on shutdown.**<br>Use for paper/sim, avoid for swing trading. |
| `INTRADAY_FLATTEN` | **Flatten at end of session.**<br>Enable for strict intraday strategies. |

## Sabbath-Related Settings

| Environment Variable | Description |
|----------------------|-------------|
| `SABBATH_ENABLED` | **Override profile sabbath flag.**<br> Controls whether the window is respected. |
| `SABBATH_ASTRONOMICAL` | **Use sunset times vs fixed times.**<br>Requires lat/lon. |
| `SABBATH_TIMEZONE` | **Timezone for sabbath calculations.**<br>e.g. `America/New_York`. |
| `SABBATH_START_LOCAL` | **Fixed start time (Friday).**<br>HH:MM (24h). |
| `SABBATH_END_LOCAL` | **Fixed end time (Saturday).**<br>HH:MM (24h). |
| `SABBATH_LAT` / `SABBATH_LON` | **Latitude/Longitude.**<br>Required for `SABBATH_ASTRONOMICAL=true`. |
| `SABBATH_CITY` | **Helper to resolve lat/lon.**<br>e.g. "New York". |

## Market/Broker Settings

| Environment Variable | Description |
|----------------------|-------------|
| `EXCHANGE_PROVIDER` | **Primary stack (IBKR vs CCXT).**<br>`IBKR` (default) or `CCXT`. |
| `MARKET_DEFAULT_SYMBOL` | **Fallback symbol for GUI charts.**<br>e.g. `SPY`, `BTCUSD`. |
| `MARKET_DEFAULT_TIMEFRAME` | **Fallback timeframe for GUI charts.**<br>e.g. `1h`. |
| `MARKET_MAX_CANDLES` | **Max history for GUI charts.**<br>Balance context vs performance. |
| `MARKET_SYMBOLS` | **Watchlist for GUI rotation.**<br>Comma-separated list. |

## IBKR-Specific Settings

| Environment Variable | Description |
|----------------------|-------------|
| `IBKR_HOST` | **Host/IP.**<br>`127.0.0.1` (TWS/Gateway). |
| `IBKR_PORT` | **Connection Port.**<br>7497 (Paper), 7496 (Live). |
| `IBKR_CLIENT_ID` | **Client ID.**<br>Distinguishes apps. |
| `IBKR_ACCOUNT_ID` | **Account Target.**<br>Required for multi-account logins. |
| `IBKR_DEFAULT_CCY` | **Base Currency.**<br>Usually `USD`. |
| `IBKR_PAPER` | **Connection Mode.**<br>Selects endpoint independent of `EXECUTE_TRADES`. |
| `IBKR_READ_ONLY` | **Safety Lock.**<br>Refuses orders at the adapter level. |
| `IBKR_CRYPTO_EXCHANGE` | **Crypto Venue.**<br>e.g. `ZEROHASH`. |
| `IBKR_ZEROHASH_CRYPTO_TIF` | **TIF for Crypto.**<br>e.g. `IOC` or `DAY`. |
| `IBKR_MAX_SHARES_PER_SYMBOL` | **Hard Share Cap.**<br>Safety limit. |
| `IBKR_MAX_DOLLAR_RISK_PER_SYMBOL`| **Hard Dollar Risk Cap.**<br>Stop-loss distance * shares. |
| `IBKR_MAX_DOLLAR_RISK_PER_ACCOUNT`| **Total Account Risk Cap.**<br>Sum of all open risk. |
| `IBKR_AUTO_RISK_FRACTION_OF_BUYING_POWER`| **Auto-sizing scale factor.**<br>Fraction of BP to risk (conservative). |

## CCXT-Specific Settings

| Environment Variable | Description |
|----------------------|-------------|
| `CCXT_EXCHANGE` | **Exchange ID.**<br>e.g. `binance`, `coinbase`. |
| `CCXT_DEFAULT_TYPE` | **Market Type.**<br>`spot`, `swap`, `future`. |
| `CCXT_ENABLE_RATE_LIMIT` | **Rate Limiting.**<br>Avoid bans. |
| `CCXT_SANDBOX` | **Testnet Mode.**<br>Use for testing. |
| `CCXT_SYMBOL_MAP` | **Symbol Translation.**<br>Map bot `BTCUSD` to exchange `BTC/USDT`. |
| `CCXT_API_KEY` / `SECRET` / `PASS` | **Credentials.**<br>Secure authentication. |

## AI/Commentary Settings

| Environment Variable | Description |
|----------------------|-------------|
| `CHATGPT_KEY` | **OpenAI/Compatible Key.**<br>Enables AI features. |
| `TRADE_SCI_PROVIDER` | **LLM Provider.**<br>`openai`, `anthropic`, `deepseek`, etc. |
| `TRADE_SCI_MODEL_NAME` | **Model ID.**<br>Balance intelligence vs cost. |
| `TRADE_SCI_MAX_TOKENS` | **Response Length.**<br>Controls verbosity. |
| `TRADE_SCI_TEMPERATURE` | **Creativity.**<br>Low for analysis, higher for commentary style. |
| `COMMENTARY_LLM` | **Commentary Toggle.**<br>`Auto`, `Off`, `Internal`. |
| `COMMENTARY_LLM_POLICY` | **Calling Frequency.**<br>`a_plus_or_4x` (recommended), `interval`. |
| `COMMENTARY_LLM_DAILY_SLOTS` | **Fixed Commentary Times.**<br>HH:MM list. |
| `MULTI_POSITION_ENABLED` | **Multi-Position Mode.**<br>Allow concurrent trades. |
| `MAX_CONCURRENT_POSITIONS` | **Concurrent Limit.**<br>Cap total active symbols. |
