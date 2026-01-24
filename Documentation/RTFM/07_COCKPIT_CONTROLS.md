# 7. The Cockpit Controls (Configuration)

> *"What does this button do?" — Last words of a former trader.*

The bot is configured through the **Settings GUI** or directly via `config/settings_profiles.yaml` and `.env` files. This guide covers the most important controls.

---

## Quick Access: Settings GUI

Launch the visual Settings interface:
```bash
./scripts/tradebot.sh --settings
```

Or from within the GUI dashboard, click the **Settings** button.

### GUI Tabs Overview

| Tab | Purpose |
|-----|---------|
| **System** | Profile selection, execution mode, timeframes, trend detection |
| **Strategy Workshop** | Asset strategies, risk management, pyramiding, ICC scoring, exits |
| **Broker Suite** | IBKR, OANDA, Coinbase/CCXT configuration |
| **Intelligence** | AI provider, model settings, commentary policy |
| **Hours & Sabbath** | Session gates, Sabbath blocking, timezone |
| **Advanced** | Raw environment variable editor |

---

## Strategy Selection

### Per-Asset Strategy Assignment

The most important new control: **different strategies for different asset classes**.

**In GUI:** Settings → Strategy Workshop → Asset Strategies

**In YAML:**
```yaml
strategies:
  crypto: rubberband_reaper    # Mean reversion for volatile crypto
  forex: rubberband_reaper     # Proven +7,036% on forex
  stocks: quantum              # Trend-following for equities
  etf: quantum                 # Works well on SPY, QQQ
  metals: mean_reversion       # Gold/Silver tend to range
  futures: volatility_breakout # Catch breakouts on ES, NQ
```

### Available Strategies

| Strategy | Key | Best For |
|----------|-----|----------|
| Rubberband Reaper | `rubberband_reaper` | Ranging markets, anti-martingale |
| RoboCop | `robocop` | Aggressive trending markets |
| Robot Evolution | `evolution` | Sideways/consolidation |
| Quantum | `quantum` | Strong trending pairs |
| Mean Reversion | `mean_reversion` | Ranging crypto/forex |
| HyperScalper | `hyper_scalper` | Fast markets, scalping |
| London Breakout | `london_breakout` | GBP pairs, European session |
| Volatility Breakout | `volatility_breakout` | Compressed markets |
| Singularity Aggregator | `aggregator` | Multi-strategy parallel |

---

## The "Aggression" Levers

### `icc_entry_score_threshold` (Default: `35.0`)
- **What it does:** Sets the quality bar for trade entries (0-100 scale)
- **Higher (e.g., 60.0):** Only A+ setups. May wait days for a trade.
- **Lower (e.g., 25.0):** More trades, lower quality. Higher risk.
- **Danger Zone:** Below 20.0 is basically random.

### `icc_aggressive_mode` (Default: `true`)
- **What it does:** Enables aggressive sizing and pyramiding
- **On:** Uses larger positions on high-confidence setups
- **Off:** Conservative fixed sizing

### `risk_per_trade_pct` (Default: `0.01` = 1%)
- **What it does:** How much of your account to risk per trade
- **Conservative:** 0.5% - 1%
- **Moderate:** 2% - 3%
- **Aggressive:** 5%+ (not recommended for beginners)

---

## The "Safety" Levers

### `EXECUTE_TRADES` (Default: `false`)
- **THE MASTER SWITCH:** Must be `true` to place real orders
- **`false`:** Simulation mode - logs decisions but doesn't trade
- **`true`:** Live trading - real money at risk

### `max_daily_loss_pct` (Default: `0.06` = 6%)
- **What it does:** Circuit breaker. Bot stops if daily loss exceeds this.
- **Advice:** Keep this enabled. It saves you from "tilt" spirals.

### `max_concurrent_positions` (Default: `1`)
- **What it does:** How many symbols can be traded simultaneously
- **Safe:** 1-2 positions
- **Advanced:** 3-5 positions (requires more capital)

---

## The "Time" Levers

### `candle_timeframe` (Default: `5m`)
- **What it does:** Main chart resolution
- **1m:** Scalping. High noise, fast action.
- **5m:** Standard intraday.
- **15m:** Slower intraday, cleaner signals.
- **1h:** Swing trading.

### `htf_timeframe` / `ltf_timeframe`
- **HTF:** Higher timeframe for trend direction (e.g., `15m`, `1h`)
- **LTF:** Lower timeframe for entry precision (e.g., `5m`)

### `sabbath_enabled` (Default: `true`)
- **What it does:** Blocks new entries Friday sunset to Saturday sunset
- **Why:** Lower liquidity, choppy markets, and rest is important
- **Override:** Force OFF in settings if you need 24/7 operation

---

## Broker Controls

### IBKR Settings
| Setting | Purpose |
|---------|---------|
| `IBKR_HOST` | IP address (usually `127.0.0.1`) |
| `IBKR_PORT` | 7497 (Paper) or 7496 (Live) |
| `IBKR_CLIENT_ID` | Unique ID for this connection |
| `IBKR_PAPER` | Enable paper trading mode |
| `IBKR_READ_ONLY` | Monitor only, no orders |

### OANDA Settings (NEW)
| Setting | Purpose |
|---------|---------|
| `OANDA_ACCOUNT_ID` | Your OANDA account number |
| `OANDA_API_KEY` | API token from OANDA Hub |
| `OANDA_ENVIRONMENT` | `practice` or `live` |
| `OANDA_READ_ONLY` | Monitor only, no orders |

### Coinbase/CCXT Settings
| Setting | Purpose |
|---------|---------|
| `CCXT_EXCHANGE` | Exchange ID (e.g., `coinbase`) |
| `CCXT_API_KEY` | API key |
| `CCXT_SECRET` | API secret |
| `CCXT_SANDBOX` | Enable testnet |

### Data Routing
| Setting | Options |
|---------|---------|
| `MARKET_DATA_MODE` | `primary` (IBKR), `oanda`, `alternative` (CCXT), `hybrid` |
| `BROKER_MODE` | `primary` (IBKR), `oanda`, `alternative` (CCXT), `hybrid` |

---

## Pyramiding Controls

### `max_pyramid_entries` (Default: `6`)
- **What it does:** Maximum times to add to a winning position
- **1:** No pyramiding (single entry only)
- **3-6:** Moderate scaling
- **10+:** Aggressive (requires strong trends)

### `pyramid_profit_buffer_pct` (Default: `0.0015` = 0.15%)
- **What it does:** Minimum profit required before first add
- **Why:** Prevents adding to trades that haven't proven themselves

### `breakeven_trail_after_pyramids` (Default: `1`)
- **What it does:** Move stop to breakeven after N pyramid entries
- **0:** Disabled
- **1:** After first add, protect capital

---

## AI/Commentary Controls

### `TRADE_SCI_PROVIDER`
- **Options:** `gemini`, `openai`, `claude`, `deepseek`, `openrouter`
- **Recommended:** `gemini` (good balance of quality and cost)

### `COMMENTARY_LLM_POLICY`
- **`a_plus_or_4x`:** AI commentary on A+ setups or 4x daily (recommended)
- **`a_plus_only`:** Only exceptional setups
- **`interval`:** Fixed schedule

---

## Control Summary

### Green Levers (Safe to Adjust)
- `icc_entry_score_threshold` - Quality filter
- `sabbath_enabled` - Weekend blocking
- `candle_timeframe` - Chart resolution
- `strategies.*` - Per-asset strategy assignment
- `risk_per_trade_pct` - Position sizing

### Yellow Levers (Understand Before Changing)
- `max_pyramid_entries` - Scaling aggressiveness
- `icc_aggressive_mode` - Position sizing mode
- `max_concurrent_positions` - Multi-symbol trading

### Red Levers (Danger - Expert Only)
- `EXECUTE_TRADES` - Live trading toggle
- `IBKR_PORT` - Wrong port = wrong account
- `market_poll_interval_seconds` - Too low = API ban

---

> *"The best traders aren't the ones who touch every button. They're the ones who know which buttons NOT to touch."*
