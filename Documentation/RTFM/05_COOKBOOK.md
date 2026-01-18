
# 5. The Cookbook (How-To)
> *"Give a man a fish, he trades for a day. Teach a man to configure the bot, he loses money automatically."*

Here are the common tasks you might want to perform.

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

## Recipe 2: Making the Bot More Aggressive
The bot is too timid? You can lower its standards.

1.  Open `config/settings_profiles.yaml`.
2.  Find `icc_entry_score_threshold`.
3.  Lower it.
    *   `60.0`: The default. Needs a B- grade or better.
    *   `50.0`: Will trade "C" setups (riskier).
    *   `30.0`: Will trade almost anything that moves (DANGER).
4.  **Restart the bot.**

## Recipe 3: The "Kill Switch" Reset
The bot screamed "Kill Switch Activated!" and stopped. Now what?

1.  **Check the logs:** `tail -n 50 logs/tradebot.log`.
    *   Ideally, fix the root cause (e.g., add funds, fix API key).
2.  **Wait:** It has a cooldown (usually 3 cycles). It might reset itself.
3.  **Hard Reset:** If it's stuck or you are impatient:
    *   `./scripts/tradebot.sh --restart`
    *   This clears the `_consecutive_errors` counter immediately.

## Recipe 4: Debugging "Why didn't it trade?"
1.  **Check Affordability:** Did you have enough cash in the **Spot** wallet? (Many brokers, like Coinbase Futures, require collateral in the Spot wallet).
2.  **Check Score:** Look at the logs.
    *   `[STRUCTURE] BTC selection_score=45.0`
    *   If your threshold is 60.0, it failed the exam.
3.  **Check Gates:**
    *   `last_gate=sweep`: It saw a sweep. Good.
    *   `last_gate=None`: It hasn't seen a sweep or continuation. It's waiting.

## Recipe 5: Running a Backtest (Simulation)
Want to test a strategy without real money?
1.  Run the bot in `iterations` mode.
    ```bash
    ./scripts/tradebot.sh -m iterations -i 500 -x false
    ```
2.  This runs 500 cycles using live data (or mock if configured) but **skips execution**.
3.  Check `logs/tradebot.log` to see what it *would* have done.
