---
title: "51 Every Toggle, Every Flag: The Environment Variable Bible"
category: rtfm
icon: settings_applications
description: "The comprehensive reference for every environment variable used by TradeBot\
  \ SCI \u2014 including purpose, usage, and meaningful defaults. Covers GUI_AUTOSTART_BOT,\
  \ GUI_KEEP_BOT_RUNNING, kill switches, API keys, feature flags, broker credentials,\
  \ AI model selection, logging levels, and every hidden toggle the bot knows about."
---

# 51. Environment Variable Reference — The Hidden Levers

<table><tr><td width="170"><img src="img/ninja.png" width="150"></td><td><b>NINJA</b>:<br><em>"Environment variables are the hidden levers. Most users never touch them. But if you're reading this, you're not most users. You're the person who reads the owner's manual cover to cover. Respect."</em></td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"This right here is the encyclopedic reference. Every environment variable. Every single hidden switch. You probably don't need to touch these directly because the Settings GUI handles them for you. But I know you. You're gonna get in here and try to tweak something to be 'smarter' than the bot. So here's the map. When you break it, don't say I didn't warn you."</td></tr></table>

> 📺 **Most of these variables can be adjusted through the Settings UI** — you don't need to edit files directly. The Settings menu organizes them into tabs: **System**, **Strategy Workshop**, **Safety & Shields**, **Performance & Profits**, **Broker Suite**, **Intelligence**, and **Hours & Sabbath**. For raw access to any variable, use Settings → **Advanced**.

---

## GUI Settings

| Environment Variable | Description |
|----------------------|-------------|
| `GUI_AUTOSTART_BOT` | **Automatically start the bot when the GUI opens.** Checks if bot is already running; if not, starts it. If already running, attaches to existing state. |
| `GUI_KEEP_BOT_RUNNING` | **Keep the bot running after you close the GUI window.** Use this if you want a desktop view temporarily but want the bot running in background (or tmux). |
| `GUI_LOG_BROWSE` | **Pick which log file the GUI reads.** Choose active log or rotated file for historical context. |
| `TMUX_RESTART_PREVIEW` | **Shows the exact tmux restart command.** Review before clicking "Restart tmux" to verify flags. |
| `GUI_BROWSE_SYNTH_STOP_STORE` | **Where to store synthetic stop state on disk.** Persists synthetic stop details for safe position management after restarts. |
| `GUI_BROWSE_POSITION_HOLD_STORE` | **Where to store position-hold/age state.** Persists hold rules across restarts. |
| `ENV_FILTER` | **Filter the Advanced env table by key.** Type part of a key (case-insensitive) like `IBKR_` or `CCXT_`. |
| `ENV_TABLE_EDIT` | **Advanced mode: edit raw environment variables.** Double-click a Value cell to edit. Be careful with broker/live-trading keys. |

---

## Profile-Related Settings

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"Profiles are where the bot's personality lives. Each variable here shapes how the bot behaves — from which symbols to trade to how aggressively it enters."</td></tr></table>

| Environment Variable | Description |
|----------------------|-------------|
| `PROFILE_NAME` | **Pick a profile.** Controls symbol universe, timeframe, scan cadence, and risk defaults. |
| `PROFILE_HTF_TIMEFRAME` | **Override HTF for ICC structure trend.** Default `4h`. |
| `PROFILE_LTF_TIMEFRAME` | **Override LTF for ICC execution.** Default `15m` or `5m`. |
| `PROFILE_TREND_WINDOW` | **Candles used to classify HTF trend.** Larger = less noise, slower response. |
| `PROFILE_LTF_TREND_WINDOW` | **Candles used to classify LTF trend.** |
| `PROFILE_TREND_SWING_LOOKBACK` | **Fractal lookback for swing highs/lows.** Higher = more separation between swings. |
| `PROFILE_TREND_MIN_SWINGS` | **Min confirmed swings to call a trend.** Higher = stronger confirmation, fewer trades. |
| `PROFILE_TREND_STRENGTH_FLOOR` | **Min structure strength for non-neutral trend.** Based on HH/HL or LH/LL consistency. |
| `PROFILE_STRUCTURE_SCORE_THRESHOLD` | **Score threshold for structure cleanliness.** Influences ICC gating. |
| `PROFILE_PDT_GUARD_ENABLED` | **PDT guard for equities.** Limits same-day roundtrips for accounts under $25k. |
| `PROFILE_MAX_EQUITY_ROUNDTRIPS_PER_DAY` | **Max equity roundtrips/day.** Keep low (e.g., 3) unless PDT exempt. |
| `PROFILE_FLIP_ACTIONS_ENABLED` | **Allow flip_to_long / flip_to_short.** Reserved for confirmed HTF flips. Disabled by default. |
| `PROFILE_FLIP_COOLDOWN_SECONDS` | **Min seconds between flips.** Prevents churn in chop. |
| `PROFILE_COOLDOWN_ENABLED` | **Enable ICC cooldowns.** Helps avoid re-entering during chop. |
| `PROFILE_COOLDOWN_CYCLES_AFTER_BLOCK` | **Cycles to skip after a blocked attempt.** |
| `PROFILE_COOLDOWN_CYCLES_AFTER_SUCCESS` | **Cycles to skip after a successful entry.** Reduces over-trading. |
| `PROFILE_COOLDOWN_SCOPE` | **Cooldown scope.** `symbol` for broad scanning, `global` for hard pauses. |
| `PROFILE_STICK_TO_ACTIVE_SYMBOL_UNTIL` | **Stick to active symbol until `cycle_end` or `decision_end`.** Reduces churn. |
| `PROFILE_AUTO_SCHEDULE_ENABLED` | **Auto-schedule: equities in US hours, crypto off-hours.** |
| `PROFILE_AUTO_FLATTEN_ON_CLOSE` | **Auto-flatten at end of scheduled windows.** Avoid if holding overnight. |
| `PROFILE_CONTINUOUS_MODE` | **Keep runtime loop alive regardless of iteration limits.** Best for always-on. |
| `PROFILE_CRYPTO_ONLY` | **Treat profile as crypto-only.** Useful for off-hours execution. |
| `PROFILE_ICC_AGGRESSIVE_MODE` | **Aggressive ICC sizing + guardrails.** Default `true`. |
| `PROFILE_AGGRESSIVE_RISK_PER_TRADE_PCT` | **Risk per trade in aggressive mode.** Default 3%. |
| `PROFILE_MAX_DAILY_LOSS_PCT` | **Max daily loss % before blocking.** Default 6%. |
| `PROFILE_MAX_EXPOSURE_PCT` | **Max total open exposure %.** Default 40%. |
| `PROFILE_MAX_CONSECUTIVE_LOSSES` | **Consecutive loss limit before blocking.** Default 2. |

---

## Bot Runtime & General Settings

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"These are the master controls! The heavy machinery! Runtime mode, live trading toggle, logging. Don't flip these switches unless you actually know what they do. You're not flying a spaceship in an arcade, this is real money."</td></tr></table>

| Environment Variable | Description |
|----------------------|-------------|
| `BOT_MODE` | **Runtime mode.** `continuous` (forever), `scheduled` (windows), `iterations` (N loops). |
| `BOT_ITERATIONS` | **Number of cycles for `iterations` mode.** Use small numbers (20-200) for testing. |
| `EXECUTE_TRADES` | **MASTER SWITCH for live orders.** `true` = real money. `false` = simulation. |
| `BOT_SABBATH` | **Sabbath entry blocking.** `Auto`, `Force ON`, `Force OFF`. |
| `APP_ENVIRONMENT` | **Environment tag** (dev/staging/prod). |
| `LOG_LEVEL` | **Log verbosity.** `INFO`, `DEBUG`, `WARNING`, `ERROR`. |
| `TRADEBOT_LOG` | **Path to main log file.** Default `logs/tradebot.log`. |
| `SESSION_NAME` | **tmux session name.** Default `tradebot`. |
| `EMERGENCY_STOP_PCT` | **Emergency protective stop %.** Last-resort safety net. |
| `AUTO_RESTART_ON_ERROR` | **Auto-restart if IBKR health is stuck.** |
| `AUTO_RESTART_STALE_SECONDS` | **Stale threshold.** Default 300s. |
| `AUTO_RESTART_MIN_UPTIME_SECONDS` | **Min uptime before allowing restart.** Prevents boot loops. |
| `AUTO_RESTART_COOLDOWN_SECONDS` | **Min seconds between restarts.** Prevents rapid cycling. |
| `SCALE_OUT_FRACTION` | **Fraction to sell when scaling out.** e.g. 0.5 = sell half. |
| `MAX_SCALE_INS_PER_LEG` | **Max pyramid additions per leg.** Start low (0-2). |
| `MIN_POSITION_SIZE_TO_SCALE` | **Min size to allow scaling.** Prevents managing dust. |
| `STARTUP_CRYPTO_UNPROTECTED_POLICY` | **Action for unprotected crypto on startup.** `REARM`, `PAUSE`, `FLATTEN`. |
| `SYNTH_STOP_STORE_PATH` | **Path for synthetic stop JSON.** Critical for ZEROHASH. |
| `POSITION_HOLD_STORE_PATH` | **Path for position age JSON.** Tracks hold times across restarts. |
| `ALLOW_INHERITED_POSITION` | **Manage pre-existing broker positions.** Enable to adopt manual trades. |
| `CANCEL_ORDERS_ON_START` | **Cancel pending orders on startup.** Safety cleanup. |
| `FLATTEN_ON_EXIT` | **Flatten positions on shutdown.** Use for paper/sim. |
| `INTRADAY_FLATTEN` | **Flatten at end of session.** For strict intraday strategies. |

---

## Sabbath-Related Settings

| Environment Variable | Description |
|----------------------|-------------|
| `SABBATH_ENABLED` | **Override profile sabbath flag.** Controls whether the window is respected. |
| `SABBATH_ASTRONOMICAL` | **Use sunset times vs fixed times.** Requires lat/lon. |
| `SABBATH_TIMEZONE` | **Timezone.** e.g. `America/New_York`. |
| `SABBATH_START_LOCAL` | **Fixed start time (Friday).** HH:MM (24h). |
| `SABBATH_END_LOCAL` | **Fixed end time (Saturday).** HH:MM (24h). |
| `SABBATH_LAT` / `SABBATH_LON` | **Latitude/Longitude.** Required for `SABBATH_ASTRONOMICAL=true`. |
| `SABBATH_CITY` | **Helper to resolve lat/lon.** e.g. "New York". |

---

## Market/Broker Settings

| Environment Variable | Description |
|----------------------|-------------|
| `EXCHANGE_PROVIDER` | **Primary stack.** `IBKR` or `CCXT`. |
| `MARKET_DEFAULT_SYMBOL` | **Fallback symbol for GUI charts.** e.g. `SPY`, `BTCUSD`. |
| `MARKET_DEFAULT_TIMEFRAME` | **Fallback timeframe.** e.g. `1h`. |
| `MARKET_MAX_CANDLES` | **Max history for GUI charts.** Balance context vs performance. |
| `MARKET_SYMBOLS` | **Watchlist for GUI rotation.** Comma-separated. |

---

## IBKR-Specific Settings

| Environment Variable | Description |
|----------------------|-------------|
| `IBKR_HOST` | **Host/IP.** `127.0.0.1` for TWS/Gateway. |
| `IBKR_PORT` | **Port.** 7497 (Paper), 7496 (Live). |
| `IBKR_CLIENT_ID` | **Client ID.** Must be unique per connection. |
| `IBKR_ACCOUNT_ID` | **Account Target.** Required for multi-account. |
| `IBKR_DEFAULT_CCY` | **Base Currency.** Usually `USD`. |
| `IBKR_PAPER` | **Connection Mode.** Selects endpoint. |
| `IBKR_READ_ONLY` | **Safety Lock.** Refuses orders at adapter level. |
| `IBKR_CRYPTO_EXCHANGE` | **Crypto Venue.** e.g. `ZEROHASH`. |
| `IBKR_ZEROHASH_CRYPTO_TIF` | **TIF for Crypto.** `IOC` or `DAY`. |
| `IBKR_MAX_SHARES_PER_SYMBOL` | **Hard Share Cap.** Safety limit. |
| `IBKR_MAX_DOLLAR_RISK_PER_SYMBOL` | **Hard Dollar Risk Cap.** |
| `IBKR_MAX_DOLLAR_RISK_PER_ACCOUNT` | **Total Account Risk Cap.** |
| `IBKR_AUTO_RISK_FRACTION_OF_BUYING_POWER` | **Auto-sizing scale factor.** |

---

## CCXT-Specific Settings

| Environment Variable | Description |
|----------------------|-------------|
| `CCXT_EXCHANGE` | **Exchange ID.** e.g. `binance`, `coinbase`. |
| `CCXT_DEFAULT_TYPE` | **Market Type.** `spot`, `swap`, `future`. |
| `CCXT_ENABLE_RATE_LIMIT` | **Rate Limiting.** Avoid bans. |
| `CCXT_SANDBOX` | **Testnet Mode.** |
| `CCXT_SYMBOL_MAP` | **Symbol Translation.** Map bot `BTCUSD` to exchange format. |
| `CCXT_API_KEY` / `SECRET` / `PASS` | **Credentials.** |

---

## OANDA-Specific Settings

| Environment Variable | Description |
|----------------------|-------------|
| `OANDA_ACCOUNT_ID` | **Account ID.** Format: `101-001-1234567-001`. |
| `OANDA_API_KEY` | **API Token.** Generate in OANDA Hub. Keep secret! |
| `OANDA_ENVIRONMENT` | **Environment.** `practice` (demo) or `live` (real money). |
| `OANDA_READ_ONLY` | **Read-Only Mode.** Fetch prices, no orders. |

---

## Strategy Selection Settings

| Environment Variable | Description |
|----------------------|-------------|
| `STRATEGY_VARIANT` | **Default Strategy.** Fallback when per-asset not configured. Options: `meta_sci` ⭐, `rubberband_reaper`, `robocop`, `mean_reversion`, `supply_demand`, `trend_rider`, `session_momentum`, `bearish_engulfing`, `icc_core`, `orb_breakout`, `evolution`, `quantum`, `hyper_scalper`, `london_breakout`, `volatility_breakout`, `aggregator`, `crypto_rsi_macd`, `crypto_vwap_reversion`, `crypto_double_macd`, `crypto_grid`. |
| `STRATEGY_CRYPTO` | **Crypto Strategy.** Overrides default for crypto symbols. |
| `STRATEGY_FOREX` | **Forex Strategy.** Overrides default for forex pairs. |
| `STRATEGY_STOCKS` | **Stocks Strategy.** |
| `STRATEGY_ETF` | **ETF Strategy.** |
| `STRATEGY_METALS` | **Metals Strategy.** |
| `STRATEGY_FUTURES` | **Futures Strategy.** |

---

## AI/Commentary Settings

| Environment Variable | Description |
|----------------------|-------------|
| `CHATGPT_KEY` | **OpenAI/Compatible Key.** Enables AI features. |
| `TRADE_SCI_PROVIDER` | **LLM Provider.** `openai`, `anthropic`, `deepseek`, etc. |
| `TRADE_SCI_MODEL_NAME` | **Model ID.** Balance intelligence vs cost. |
| `TRADE_SCI_MAX_TOKENS` | **Response Length.** Controls verbosity. |
| `TRADE_SCI_TEMPERATURE` | **Creativity.** Low for analysis, higher for commentary. |
| `COMMENTARY_LLM` | **Commentary Toggle.** `Auto`, `Off`, `Internal`. |
| `COMMENTARY_LLM_POLICY` | **Calling Frequency.** `a_plus_or_4x` (recommended), `interval`. |
| `COMMENTARY_LLM_DAILY_SLOTS` | **Fixed Commentary Times.** HH:MM list. |
| `MULTI_POSITION_ENABLED` | **Multi-Position Mode.** Allow concurrent trades. |
| `MAX_CONCURRENT_POSITIONS` | **Concurrent Limit.** Cap total active symbols. |

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"If you made it all the way down here, congratulations! You just read every environment variable in the system. You now know more about this bot than 99% of the people running it. Use this knowledge to make money. And for the love of God, don't break anything."</td></tr></table>

---

## 📖 Continue Reading

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"Wow, okay I think I get it now. What's next?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Turn the page. We are going to talk about <b>Update Protocol</b>. Try to keep up."</td></tr></table>
