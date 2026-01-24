
# 5. The Cookbook (How-To)
> *"Give a man a fish, he trades for a day. Teach a man to configure the bot, he loses money automatically."*

Here are the common tasks you might want to perform.

---

## Recipe 1: Adding a New Symbol
You want to trade `DOGE`? Sure, why not.

1.  Open `config/settings_profiles.yaml`.
2.  Find the profile you are running (likely `crypto_247` or a custom profile).
3.  Add the symbol to the list:
    ```yaml
    crypto_247:
      # ...
      symbols:
        - BTCUSD
        - ETHUSD
        - DOGEUSD  # <--- Add this!
    ```
4.  **Restart the bot.** (`./scripts/tradebot.sh --restart`).
    *   *Note:* The bot scans the config on startup. It won't pick up changes dynamically.

---

## Recipe 2: Changing Strategy per Asset Class
Want to use mean reversion for crypto but trend-following for stocks?

1.  Open `config/settings_profiles.yaml`.
2.  Find your profile and locate the `strategies:` block.
3.  Assign strategies to asset classes:
    ```yaml
    forex_continuous:
      strategies:
        crypto: rubberband_reaper    # Mean reversion for volatile crypto
        forex: rubberband_reaper     # Proven +7,036% on forex
        stocks: quantum              # Trend-following for equities
        etf: quantum                 # Works on SPY, QQQ
        metals: mean_reversion       # Gold/Silver tend to range
        futures: volatility_breakout # Catch breakouts on ES, NQ
    ```
4.  **Available strategies:**
    - `rubberband_reaper` - Mean reversion + anti-martingale
    - `robocop` - Ultra-aggressive trending
    - `evolution` - NTZ scalping
    - `quantum` - Trend following with SMA
    - `mean_reversion` - Classic Bollinger + RSI
    - `hyper_scalper` - Fast EMA crossover
    - `london_breakout` - European session breakout
    - `volatility_breakout` - Range compression breakout
    - `aggregator` - Multi-strategy parallel
5.  **Restart the bot.**

---

## Recipe 3: Setting Up OANDA for Forex
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
3.  **Or via .env:**
    ```bash
    OANDA_ACCOUNT_ID=101-001-1234567-001
    OANDA_API_KEY=your-token-here
    OANDA_ENVIRONMENT=practice
    ```
4.  **Restart the bot.**

---

## Recipe 4: Making the Bot More Aggressive
The bot is too timid? You can lower its standards.

1.  Open `config/settings_profiles.yaml`.
2.  Find `icc_entry_score_threshold`.
3.  Lower it.
    *   `60.0`: The default. Needs a B- grade or better.
    *   `50.0`: Will trade "C" setups (riskier).
    *   `30.0`: Will trade almost anything that moves (DANGER).
4.  **Restart the bot.**

---

## Recipe 5: The "Kill Switch" Reset
The bot screamed "Kill Switch Activated!" and stopped. Now what?

1.  **Check the logs:** `tail -n 50 logs/tradebot.log`.
    *   Ideally, fix the root cause (e.g., add funds, fix API key).
2.  **Wait:** It has a cooldown (usually 3 cycles). It might reset itself.
3.  **Hard Reset:** If it's stuck or you are impatient:
    *   `./scripts/tradebot.sh --restart`
    *   This clears the `_consecutive_errors` counter immediately.

---

## Recipe 6: Debugging "Why didn't it trade?"
1.  **Check Affordability:** Did you have enough cash in the **Spot** wallet? (Many brokers, like Coinbase Futures, require collateral in the Spot wallet).
2.  **Check Score:** Look at the logs.
    *   `[STRUCTURE] BTC selection_score=45.0`
    *   If your threshold is 60.0, it failed the exam.
3.  **Check Gates:**
    *   `last_gate=sweep`: It saw a sweep. Good.
    *   `last_gate=None`: It hasn't seen a sweep or continuation. It's waiting.
4.  **Check Strategy:**
    *   Make sure the correct strategy is assigned to that asset class.
    *   Check logs for `[STRATEGY] Using rubberband_reaper for BTC`.

---

## Recipe 7: Running a Backtest (Simulation)
Want to test a strategy without real money?
1.  Run the bot in `iterations` mode.
    ```bash
    ./scripts/tradebot.sh -m iterations -i 500 -x false
    ```
2.  This runs 500 cycles using live data (or mock if configured) but **skips execution**.
3.  Check `logs/tradebot.log` to see what it *would* have done.

---

## Recipe 8: Switching Between Brokers
Trading multiple asset classes? Use different brokers:

1.  **IBKR for Stocks/Futures:**
    - Settings → Brokers → IBKR
    - Set `BROKER_MODE=primary`
2.  **OANDA for Forex:**
    - Settings → Brokers → OANDA
    - Set `BROKER_MODE=oanda`
3.  **CCXT for Crypto:**
    - Settings → Brokers → CCXT
    - Set `BROKER_MODE=alternative`

---

## Recipe 9: Opening the Settings GUI
Forgot where all the buttons are?

```bash
./scripts/tradebot.sh --settings
```

Or from within the dashboard, click the **Settings** button.

---

## Recipe 10: Enabling Paper Trading (Simulation Mode)
Not ready to trade real money yet?

1.  **Via GUI:**
    - Settings → System → **Execution Mode**
    - Toggle OFF "Execute Real Trades"
2.  **Via .env:**
    ```bash
    EXECUTE_TRADES=false
    ```
3.  The bot will log decisions but won't place actual orders.
