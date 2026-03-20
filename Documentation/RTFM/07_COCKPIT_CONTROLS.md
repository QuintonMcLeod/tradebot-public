# 7. The Cockpit Controls — Configuration Guide

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"What does this button do?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Famous last words! That's literally etched onto the tombstone of a former trader. He clicked 'EXECUTE_TRADES = true' before he understood what anything else meant and incinerated $1,200 in forty-five minutes. <br><br>This chapter explains every single knob, lever, and switch in the cockpit. READ IT before you start pressing buttons like a toddler in an elevator."</td></tr></table>

---

## Quick Access: Settings GUI

```bash
./scripts/tradebot.sh --gui
```
Or from within the dashboard, click **Settings**.

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

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"The most important control in the entire cockpit: <b>different strategies for different asset classes.</b> Crypto behaves nothing like forex. Forex behaves nothing like metals. If you're running the same strategy on everything, you're wearing the same outfit to the beach AND the boardroom."</td></tr></table>

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

See Chapter 9 (**20 Weapons of War**) for detailed explanations of each.

---

## The "Aggression" Levers

<table><tr><td width="170"><img src="img/pirate.png" width="150"></td><td><b>PIRATE</b>:<br>"Where's the 'FULL SEND' button?! 🏴‍☠️"</td></tr></table>

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"There is no 'FULL SEND' button, honey. And if there were, I'd disable it. But here are the aggression levers, and please be careful with them..."</td></tr></table>

### `icc_entry_score_threshold` (Default: `55.0`)
- **What it does:** Sets the quality bar for trade entries (0-100 scale)
- **Higher (70.0):** Only A+ setups. May wait days.
- **Lower (40.0):** More trades, lower quality. Higher risk.
- **Danger Zone:** Below 30.0 is basically random.
- 📺 **In the UI:** Settings → **Strategy Workshop** → **Strategy Toolbox** sub-tab

### `risk_per_trade_pct` (Default: `0.02` = 2%)
- **What it does:** How much of your account to risk per trade
- **Conservative:** 1-2%
- **Moderate:** 2-3%
- **Aggressive:** 4-5% (not recommended for beginners)
- 📺 **In the UI:** Settings → **Strategy Workshop** → **Global Risk** sub-tab → **Default Risk %** slider

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"The difference between 2% and 5% risk doesn't sound like much to you, does it? It's just three little points. But after 5 consecutive losses, 2% risk means you're down 9.6%. 5% risk means you're down almost 23%! Some differences only reveal themselves under pressure. Like your character. Stop trying to be a hero and turn the slider down."</td></tr></table>

---

## Safety & Shields

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"These are your protective guardrails. Most are enabled by default. Do not disable them unless you understand the consequences. And 'I want more trades' is not understanding the consequences."</td></tr></table>

### Position Lock (Always On)
- **What it does:** Once a position is open on a symbol, ALL new entry signals for that symbol are rejected until the position closes naturally.
- **Why:** Prevents whipsaw flipping (long→short→long) which destroys accounts.
- **Override:** Cannot be disabled. This is by design. Not a limitation — a feature.
- **Important:** If you manually close a bot-managed trade, Position Lock won't know. Restart the bot.

### Leverage Sentry
- **What it does:** Blocks new trades if total leverage exceeds your cap
- **Default:** 3.0x for forex, varies by asset class
- **Configure:** Settings → System → Max Leverage
- **Logs:** `[SAFETY] Entry Blocked: Leverage Sentry (FOREX): 4.0x > 3.0x cap`

### Daily Loss Limit
| Setting | Default | Description |
|---------|---------|-------------|
| `max_daily_loss_pct` | `0.10` (10%) | Circuit breaker — stops all trading |

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"If you lose 10% in a day, the bot SHUTS DOWN. Completely! That's not a suggestion, it's a circuit breaker. Because when you lose 10%, your fragile little human brain goes, 'I gotta win it back right now!' And then you lose another 10%. And then you're holding a sign on the freeway. The circuit breaker says 'go to bed.' Listen to the circuit breaker!"</td></tr></table>

### Breakeven Trail
| Setting | Default | Description |
|---------|---------|-------------|
| `breakeven_enabled` | `true` | Move SL to breakeven after profit threshold |
| `breakeven_trigger_pct` | `0.005` (0.5%) | Minimum unrealized profit to trigger |

<table><tr><td width="170"><img src="img/bot.png" width="150"></td><td><b>THE BOT</b>:<br><em>"After price moves in your favor, I move your stop-loss to entry price. You can't lose money on a trade that's already proven itself. Free ride."</em></td></tr></table>

### Trailing Stop
| Setting | Default | Description |
|---------|---------|-------------|
| `trailing_stop_enabled` | `true` | Ratchet SL up as price advances |
| `trailing_stop_pct` | `0.01` (1%) | Trail distance from current price |

---

## The Safety Master Switches

### `EXECUTE_TRADES` (Default: `false`)

<table><tr><td width="170"><img src="img/bear.png" width="150"></td><td><b>BEAR</b>:<br>"This is <b>THE MASTER SWITCH.</b> Must be <code>true</code> to place real orders. Leave it <code>false</code> until you're absolutely, positively, bet-your-house ready. And even then, start small."</td></tr></table>

- **`false`:** Simulation mode — logs decisions but doesn't trade
- **`true`:** Live trading — real money at risk
- 📺 **In the UI:** Settings → **System** → toggle **Live Trading**

### `max_concurrent_positions` (Default: `3`)
- **Safe:** 2-3 positions
- **Advanced:** 4-5 positions (requires more capital)
- 📺 **In the UI:** Settings → **Safety & Shields** → **Max Concurrent Positions**

---

## The "Time" Levers

### `candle_timeframe` (Default: `1h`)
- **5m:** Scalping. High noise, fast action.
- **15m:** Intraday, cleaner signals.
- **1h:** Swing trading (recommended).
- **4h:** Position trading.
- 📺 **In the UI:** Settings → **System** → **Candle Timeframe** dropdown

### `htf_timeframe` / `ltf_timeframe`
- **HTF:** Higher timeframe for trend direction (e.g., `4h`)
- **LTF:** Lower timeframe for entry precision (e.g., `15m`)
- 📺 Settings → **System** → **HTF/LTF Timeframe** dropdowns

### `sabbath_enabled` (Default: `true`)
- **What it does:** Blocks new entries Friday sunset to Saturday sunset
- 📺 Settings → **Hours & Sabbath** → toggle **Enable Sabbath**

---

## Broker Controls

All broker settings: Settings → **Broker Suite**.

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
| `CCXT_EXCHANGE` | Exchange ID (`gemini`, `coinbase`, `kraken`) |
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

> 📺 Settings → **Intelligence** — select provider, model, and commentary policy

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

<table><tr><td width="170"><img src="img/ninja.png" width="150"></td><td><b>NINJA</b>:<br><em>"Touch these without knowing what you're doing... and the market will make you pay tuition."</em></td></tr></table>

- `EXECUTE_TRADES` — Live trading toggle
- `IBKR_PORT` — Wrong port = wrong account
- `market_poll_interval_seconds` — Too low = API ban
- Lowering `icc_entry_score_threshold` below 35 — Nearly random trades

---

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"The best traders aren't the ones who touch every single button. They're the ones who know which buttons NOT to touch. The cockpit has 50 controls. A good pilot uses 6 of them 99% of the time. You are not Tom Cruise in Top Gun. Be a boring pilot."</td></tr></table>
