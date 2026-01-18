
# 7. The Cockpit Controls (Configuration)
> *"What does this button do?" — Last words of a former trader.*

The `config/settings_profiles.yaml` file is the control panel. It determines if the bot is a scalping maniac (not recommended) or a patient sniper (recommended).

Here is the translation guide for the most important levers.

## The "Aggression" Levers

### `icc_entry_score_threshold` (Default: `60.0`)
*   **What it does:** Sets the standard for identifying a trade. 0 is trash, 100 is perfection.
*   **Higher (e.g., 70.0):** The bot only trades A+ setups. You might wait days for a trade.
*   **Lower (e.g., 50.0):** The bot trades B- setups. More action, more risk.
*   **Danger Zone:** Anything below 40.0 is basically randomly guessing.

### `market_poll_interval_seconds` (Default: `15`)
*   **What it does:** How often the bot asks "What's the price?"
*   **Lower (e.g., 5):** Faster reaction. Higher API usage.
*   **Higher (e.g., 60):** Lower stress. Good for 1H timeframes.

## The "Safety" Levers

### `max_daily_loss` (in `.env`)
*   **What it does:** If you lose this much money in 24 hours, the bot quits.
*   **Default:** Usually 6% of equity.
*   **Advice:** Keep this on. It saves you from "tilt" (emotional spiraling).

### `cooldown_cycles_after_block` (Default: `3`)
*   **What it does:** If a trade gets rejected (too risky, too poor), the bot pauses on that symbol for 3 cycles (~45 seconds).
*   **Why:** To prevent it from spamming the broker with the same bad order 100 times a second.

## The "Time" Levers

### `candle_timeframe` (Default: `5m`)
*   **What it does:** The chart resolution the bot looks at.
*   **5m:** Standard Intraday.
*   **1h:** Swing Trading. Slower, calmer.
*   **1m:** Scalping. High noise, high caffeine.

### `sabbath_enabled` (Default: `Auto`)
*   **What it does:** Respects the weekend (Friday sunset to Saturday sunset).
*   **Why:** Because markets are choppy on weekends, and humans need sleep.
*   **Override:** You can force this OFF with `--no-sabbath` if you hate rest.

## The "Crypto" Levers

### `crypto_min_notional_usd` (Default: `$20.00`)
*   **What it does:** The smallest trade allowed.
*   **Why:** Many brokers (like Coinbase) reject orders smaller than ~$1.00 used. We set it higher to ensure fees don't eat the profit.

### `crypto_routing` (in `settings_base.yaml`)
*   **What it does:** Tells IBKR (and some institutional CCXT setups) which backend to use (PAXOS vs ZEROHASH).
*   **Advice:** Don't touch this unless you get "Unsupported Instrument" errors.

## Summary
*   **Green Levers (Safe to Touch):** `icc_entry_score_threshold`, `sabbath_enabled`, `candle_timeframe`.
*   **Red Levers (Danger):** `crypto_routing`, `market_poll_interval_seconds` (too low = ban).
