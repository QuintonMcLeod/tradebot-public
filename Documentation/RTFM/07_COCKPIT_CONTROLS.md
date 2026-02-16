# 7. The Cockpit Controls (Configuration)

> *"What does this button do?" — Last words of a former trader.*

The bot is configured through the **Settings GUI**, `config.json`, or `config/settings_profiles.yaml` (legacy). This guide covers the most important controls.

---

## Quick Access: Settings GUI

Launch the visual Settings interface:
```bash
./scripts/tradebot.sh --gui
```

Or from within the GUI dashboard, click the **Settings** button.

### GUI Tabs Overview

| Tab | Purpose |
|-----|---------|
| **System** | Profile selection, **Live Trading** toggle, timeframes, trend detection |
| **Strategy Workshop** | Asset Strategies, Strategy Toolbox, Global Risk, Pyramiding, Exit Logic |
| **Safety & Shields** | Position protection, ATR Armor, Drawdown Breaker, Volatility Veto |
| **Performance & Profits** | Trailing stop mode, compounding, performance tuning |
| **Broker Suite** | IBKR, OANDA, CCXT (Gemini, Coinbase, Kraken) configuration |
| **Intelligence** | AI provider, model selection, commentary policy |
| **Hours & Sabbath** | Sabbath blocking, session gate, Auto Schedule |
| **Appearance** | Themes & colors |
| **Advanced** | Raw environment variable editor |

---

## Strategy Selection

### Per-Asset Strategy Assignment

The most important control: **different strategies for different asset classes**.

**In GUI:** Settings → Strategy Workshop → Asset Strategies

**In config.json:**
```json
{
  "profiles": {
    "forex_continuous": {
      "strategy": "meta_sci",
      "strategies": {
        "crypto": "meta_sci",
        "forex": "rubberband_reaper",
        "stocks": "trend_rider",
        "metals": "mean_reversion"
      }
    }
  }
}
```

### Available Strategies (20)

| Strategy | Key | Best For |
|----------|-----|----------|
| **Meta-SCI** ⭐ | `meta_sci` | All markets — auto-selects best strategy |
| **Rubberband Reaper** | `rubberband_reaper` | Ranging markets, anti-martingale |
| **RoboCop** | `robocop` | Sniper precision, high-conviction |
| **Mean Reversion** | `mean_reversion` | Ranging crypto/forex |
| **Supply & Demand** | `supply_demand` | Institutional zone trading |
| **Trend Rider** | `trend_rider` | Strong trending markets |
| **Session Momentum** | `session_momentum` | London/NY session opens |
| **Engulfing Reversal** | `bearish_engulfing` | Candlestick reversal patterns |
| **ICC Core** | `icc_core` | Pure structure trading |
| **ORB Breakout** | `orb_breakout` | Opening range breakouts |
| **Robot Evolution** | `evolution` | NTZ edge scalping |
| **Quantum** | `quantum` | SMA trend following |
| **HyperScalper** | `hyper_scalper` | Fast EMA crossover |
| **London Breakout** | `london_breakout` | GBP pairs, European session |
| **Volatility Breakout** | `volatility_breakout` | Range compression |
| **Aggregator** | `aggregator` | Multi-strategy parallel |
| 🪙 **RSI + MACD** | `crypto_rsi_macd` | Crypto trending |
| 🪙 **VWAP Reversion** | `crypto_vwap_reversion` | Crypto ranging |
| 🪙 **Double MACD** | `crypto_double_macd` | Crypto scalping |
| 🪙 **Virtual Grid** | `crypto_grid` | Crypto sideways markets |

See `09_FEET_WET_STRATEGY.md` for detailed explanations of each strategy.

---

## The "Aggression" Levers

### `icc_entry_score_threshold` (Default: `55.0`)
- **What it does:** Sets the quality bar for trade entries (0-100 scale)
- **Higher (e.g., 70.0):** Only A+ setups. May wait days for a trade.
- **Lower (e.g., 40.0):** More trades, lower quality. Higher risk.
- **Danger Zone:** Below 30.0 is basically random.
- 📺 **In the UI:** Settings → **Strategy Workshop** → **Strategy Toolbox** sub-tab (ICC scoring thresholds are per-strategy)

### `risk_per_trade_pct` (Default: `0.02` = 2%)
- **What it does:** How much of your account to risk per trade
- **Conservative:** 1-2%
- **Moderate:** 2-3%
- **Aggressive:** 4-5% (not recommended for beginners)
- 📺 **In the UI:** Settings → **Strategy Workshop** → **Global Risk** sub-tab → **Default Risk %** slider

---

## Safety & Shields

These are your protective guardrails. Most are enabled by default.

### Position Lock (Always On)
- **What it does:** Once a position is open on a symbol, ALL new entry signals for that symbol are rejected until the position closes naturally (SL/TP/exit logic).
- **Why:** Prevents whipsaw flipping (long→short→long) which destroys accounts.
- **Override:** Cannot be disabled. This is by design.
- **Important:** If you manually close a bot-managed trade, Position Lock won't know. Restart the bot to clear it.

### Leverage Sentry
- **What it does:** Blocks new trades if total leverage exceeds your cap
- **Default:** 3.0x for forex, varies by asset class
- **Configure:** Settings → System → Max Leverage
- **Logs:** `[SAFETY] Entry Blocked: Leverage Sentry (FOREX): 4.0x > 3.0x cap`

### Daily Loss Limit
| Setting | Default | Description |
|---------|---------|-------------|
| `max_daily_loss_pct` | `0.10` (10%) | Circuit breaker — stops all trading |
- **What it does:** If daily losses exceed this % of equity, ALL trading stops
- **Why:** Prevents "tilt" spirals during bad days
- **Reset:** Resets automatically at midnight (UTC) or on restart

### Breakeven Trail
| Setting | Default | Description |
|---------|---------|-------------|
| `breakeven_enabled` | `true` | Move SL to breakeven after profit threshold |
| `breakeven_trigger_pct` | `0.005` (0.5%) | Minimum unrealized profit to trigger |
- **What it does:** After price moves X% in your favor, moves stop-loss to entry price (breakeven)
- **Why:** Ensures you can't lose money once a trade has shown sufficient profit

### Trailing Stop
| Setting | Default | Description |
|---------|---------|-------------|
| `trailing_stop_enabled` | `true` | Ratchet SL up as price advances |
| `trailing_stop_pct` | `0.01` (1%) | Trail distance from current price |
- **What it does:** As price moves in your favor, the stop-loss follows behind
- **Why:** Locks in profits without capping upside

---

## The "Safety" Master Switches

### `EXECUTE_TRADES` (Default: `false`)
- **THE MASTER SWITCH:** Must be `true` to place real orders
- **`false`:** Simulation mode — logs decisions but doesn't trade
- **`true`:** Live trading — real money at risk
- 📺 **In the UI:** Settings → **System** → toggle **Live Trading**

### `max_concurrent_positions` (Default: `5`)
- **What it does:** How many symbols can be traded simultaneously
- **Safe:** 3-4 positions
- **Advanced:** 5-8 positions (requires more capital)
- 📺 **In the UI:** Settings → **Safety & Shields** → **Max Concurrent Positions**

---

## The "Time" Levers

### `candle_timeframe` (Default: `1h`)
- **What it does:** Main chart resolution
- **5m:** Scalping. High noise, fast action.
- **15m:** Intraday, cleaner signals.
- **1h:** Swing trading (recommended).
- **4h:** Position trading.
- 📺 **In the UI:** Settings → **System** → **Candle Timeframe** dropdown

### `htf_timeframe` / `ltf_timeframe`
- **HTF:** Higher timeframe for trend direction (e.g., `4h`)
- **LTF:** Lower timeframe for entry precision (e.g., `15m`)
- 📺 **In the UI:** Settings → **System** → **HTF Timeframe** / **LTF Timeframe** dropdowns

### `sabbath_enabled` (Default: `true`)
- **What it does:** Blocks new entries Friday sunset to Saturday sunset
- **Why:** Lower liquidity, choppy markets, and rest is important
- **Override:** Force OFF in settings if you need 24/7 operation
- 📺 **In the UI:** Settings → **Hours & Sabbath** → toggle **Enable Sabbath**

---

## Broker Controls

All broker settings are available in the UI: Settings → **Broker Suite**.

### IBKR Settings
| Setting | Purpose |
|---------|---------|
| `IBKR_HOST` | IP address (usually `127.0.0.1`) |
| `IBKR_PORT` | 7497 (Paper) or 7496 (Live) |
| `IBKR_CLIENT_ID` | Unique ID for this connection |
| `IBKR_PAPER` | Enable paper trading mode |
| `IBKR_READ_ONLY` | Monitor only, no orders |

### OANDA Settings
| Setting | Purpose |
|---------|---------|
| `OANDA_ACCOUNT_ID` | Your OANDA account number |
| `OANDA_API_KEY` | API token from OANDA Hub |
| `OANDA_ENVIRONMENT` | `practice` or `live` |
| `OANDA_READ_ONLY` | Monitor only, no orders |

### CCXT / Crypto Exchange Settings
| Setting | Purpose |
|---------|---------|
| `CCXT_EXCHANGE` | Exchange ID (e.g., `gemini`, `coinbase`, `kraken`) |
| `CCXT_API_KEY` | API key |
| `CCXT_SECRET` | API secret |
| `CCXT_SANDBOX` | Enable testnet |

### Data Routing
| Setting | Options |
|---------|---------|
| `MARKET_DATA_MODE` | `primary` (IBKR), `oanda`, `alternative` (CCXT), `hybrid` |
| `BROKER_MODE` | `primary` (IBKR), `oanda`, `alternative` (CCXT), `hybrid` |

---

## AI/Commentary Controls

> 📺 **In the UI:** Settings → **Intelligence** — select provider, model, and commentary policy

### `TRADE_SCI_PROVIDER`
- **Options:** `gemini`, `openai`, `claude`, `deepseek`, `openrouter`, `local`
- **Recommended:** `gemini` (good balance of quality and cost)

### `COMMENTARY_LLM_POLICY`
- **`a_plus_or_4x`:** AI commentary on A+ setups or 4x daily (recommended)
- **`a_plus_only`:** Only exceptional setups
- **`interval`:** Fixed schedule

---

## Control Summary

### Green Levers ✅ (Safe to Adjust)
- `icc_entry_score_threshold` — Quality filter
- `sabbath_enabled` — Weekend blocking
- `candle_timeframe` — Chart resolution
- Strategy assignment per asset class
- `risk_per_trade_pct` — Position sizing
- `breakeven_enabled` / `breakeven_trigger_pct` — Profit protection

### Yellow Levers ⚠️ (Understand Before Changing)
- `max_concurrent_positions` — Multi-symbol trading
- `trailing_stop_pct` — Trail distance affects hold duration
- `max_daily_loss_pct` — Circuit breaker threshold

### Red Levers 🔴 (Danger — Expert Only)
- `EXECUTE_TRADES` — Live trading toggle
- `IBKR_PORT` — Wrong port = wrong account
- `market_poll_interval_seconds` — Too low = API ban
- Lowering `icc_entry_score_threshold` below 35 — Nearly random trades

---

> *"The best traders aren't the ones who touch every button. They're the ones who know which buttons NOT to touch."*
