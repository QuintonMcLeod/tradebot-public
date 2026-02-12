
# 5. The Cookbook (How-To)
> *"Give a man a fish, he trades for a day. Teach a man to configure the bot, he loses money automatically."*

Here are the common tasks you might want to perform.

---

## Recipe 1: Adding a New Symbol
You want to trade `DOGE`? Sure, why not.

**Via GUI (Recommended):**
1. Open Profile Editor → Select your profile → **Symbols** tab.
2. Add `DOGEUSD` to the symbol list.
3. Click **Save**. The bot picks it up on the next cycle.

**Via config.json:**
1. Open `config.json`.
2. Find your profile under `"profiles"`.
3. Add the symbol to the list:
   ```json
   "crypto_247": {
     "symbols": ["BTCUSD", "ETHUSD", "DOGEUSD"]
   }
   ```
4. **Restart the bot.** (`./scripts/tradebot.sh --restart`).

---

## Recipe 2: Switching to Meta-SCI (Recommended)
Want the bot to auto-select the best strategy for each market condition?

**Via GUI:**
1. Open Profile Editor → Select profile → **General** tab.
2. Set **Strategy** to `Meta-SCI`.
3. Save.

**Via config.json:**
```json
"my_profile": {
  "strategy": "meta_sci"
}
```

That's it. Meta-SCI now runs a tournament of all eligible strategies and picks the best signal for each symbol.

---

## Recipe 3: Assigning Different Strategies per Asset Class
Want mean reversion for crypto but trend-following for forex?

**Via GUI:**
1. Profile Editor → Select profile → **General** tab.
2. Set the per-asset strategy dropdowns.

**Via config.json:**
```json
"my_profile": {
  "strategies": {
    "crypto": "crypto_rsi_macd",
    "forex": "rubberband_reaper",
    "stocks": "trend_rider",
    "metals": "mean_reversion"
  }
}
```

**Available strategies:**
- `meta_sci` ⭐ — Auto-selects best (recommended)
- `rubberband_reaper` — Mean reversion + anti-martingale
- `robocop` — Sniper precision
- `mean_reversion` — Classic Bollinger + RSI
- `supply_demand` — Institutional zones
- `trend_rider` — EMA pullback
- `session_momentum` — VWAP at session open
- `bearish_engulfing` — Candlestick reversals
- `icc_core` — Pure ICC structure
- `orb_breakout` — Opening range breakout
- `crypto_rsi_macd` — 🪙 Crypto momentum
- `crypto_vwap_reversion` — 🪙 Crypto mean reversion
- `crypto_double_macd` — 🪙 Crypto scalping
- `crypto_grid` — 🪙 Crypto grid trading
- `evolution`, `quantum`, `hyper_scalper`, `london_breakout`, `volatility_breakout`, `aggregator` — Legacy strategies

---

## Recipe 4: Setting Up OANDA for Forex
Want to trade forex with OANDA? Here's how:

1.  **Get API credentials:**
    - Log into [OANDA Hub](https://hub.oanda.com)
    - Go to **Manage API Access**
    - Generate a new token and copy it immediately
2.  **Configure via GUI:**
    - Open Settings → **Brokers** → **OANDA** tab
    - Enter Account ID: `101-001-1234567-001`
    - Paste API Key
    - Set Environment: `practice` (demo) or `live`
3.  **Or via .env.secrets:**
    ```bash
    OANDA_ACCOUNT_ID=101-001-1234567-001
    OANDA_API_KEY=your-token-here
    OANDA_ENVIRONMENT=practice
    ```
4.  **Restart the bot.**

---

## Recipe 5: Making the Bot More Aggressive
The bot is too timid? You can lower its standards.

1.  Open Settings → **System** tab (or edit `config.json`).
2.  Find `icc_entry_score_threshold`.
3.  Lower it.
    *   `65.0`: Conservative. Only A-grade setups.
    *   `55.0`: The recommended default. B-grade setups.
    *   `40.0`: Will trade C-grade setups (riskier).
    *   `30.0`: Will trade almost anything that moves (DANGER).
4.  **Save** (bot picks up changes on next cycle).

---

## Recipe 6: The "Kill Switch" Reset
The bot screamed "Kill Switch Activated!" and stopped. Now what?

1.  **Check the logs:** `tail -n 50 logs/tradebot.log`.
    *   Ideally, fix the root cause (e.g., add funds, fix API key).
2.  **Wait:** It has a cooldown (usually 3 cycles). It might reset itself.
3.  **Hard Reset:** If it's stuck:
    *   `./scripts/tradebot.sh --restart`
    *   This clears the `_consecutive_errors` counter immediately.

---

## Recipe 7: Debugging "Why didn't it trade?"
1.  **Check Position Lock:** Is there already an open position for that symbol?
    *   Look for `[POSITION LOCK]` in logs.
2.  **Check Leverage Sentry:** Are you over-leveraged?
    *   Look for `[SAFETY] Entry Blocked: Leverage Sentry` in logs.
3.  **Check ICC Score:** Did the setup score high enough?
    *   `[ICC] EURUSD Score 42.1 below threshold 55.0 — rejected`
4.  **Check Affordability:** Do you have enough capital?
    *   `[AFFORDABILITY BLOCK] Required $50 > Free $3.50`
5.  **Check Meta-SCI Tournament:**
    *   `[META-SCI] Tournament: No qualifying signals found` → Bot is being selective (good)
    *   `[META-SCI] 🏆 Winner: trend_rider (score: 78.5)` → Signal found, check guards

---

## Recipe 8: Running a Backtest
Want to test a strategy before risking real money?

```bash
# Quick forex backtest (7 days)
poetry run python tools/run_forex_backtest.py

# Quick crypto backtest (3 days)
poetry run python tools/run_crypto_backtest.py

# 30-day head-to-head strategy comparison
poetry run python tools/cartridges/forex_30day_h2h.py
```

---

## Recipe 9: Switching Between Brokers
Trading multiple asset classes? Use different brokers:

1.  **IBKR for Stocks/Futures:**
    - Settings → Brokers → IBKR
2.  **OANDA for Forex:**
    - Settings → Brokers → OANDA
3.  **CCXT for Crypto (Gemini, Coinbase, Kraken):**
    - Settings → Brokers → CCXT
4.  **Hybrid Mode:** Use one broker for data and another for execution
    - Set `MARKET_DATA_MODE` and `BROKER_MODE` in environment

---

## Recipe 10: Enabling Paper Trading (Simulation Mode)
Not ready to trade real money yet?

1.  **Via GUI:**
    - Settings → System → **Execution Mode**
    - Toggle OFF "Execute Real Trades"
2.  **Via .env.secrets:**
    ```bash
    EXECUTE_TRADES=false
    ```
3.  The bot will log decisions but won't place actual orders.

---

## Recipe 11: Understanding Position Lock
The bot opened a trade but now it's "ignoring" new signals for that symbol? That's **Position Lock** working correctly.

*   **What happened:** The bot entered a trade. Position Lock now blocks ALL new entry signals for that symbol until the trade closes naturally.
*   **Why:** Prevents whipsaw flipping (long→short→long) which destroys accounts.
*   **When it clears:** Automatically when the position is closed by SL, TP, or exit logic.
*   **Important:** If you manually close the trade outside the bot, Position Lock won't know. Restart the bot to clear it.
