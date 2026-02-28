# 5. The Cookbook — Step-by-Step Recipes

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Give a man a fish, he trades for a day. Teach a man to configure the bot, he loses money <em>automatically.</em><br><br>I'm kidding. These are the most common tasks, laid out step by step, so you can't screw them up. And if you DO screw them up after reading these recipes? That's on you. I gave you the cookbook."</td></tr></table>

---

## Recipe 1: Adding a New Symbol

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"I want to trade DOGE! How do I add it?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Of course you want to trade DOGE. Everyone wants to trade DOGE. Fine. Two ways:"</td></tr></table>

**Via GUI (Recommended):**
1. Open Profile Editor → Select your profile → **Symbols** tab.
2. Add `DOGEUSD` to the symbol list.
3. Click **Save**. The bot picks it up on the next cycle.

**Via config.json:**
```json
"crypto_247": {
  "symbols": ["BTCUSD", "ETHUSD", "DOGEUSD"]
}
```
Then restart: `./scripts/tradebot.sh --restart`.

<table><tr><td width="170"><img src="img/bear.png" width="150"></td><td><b>BEAR</b>:<br>"Just because you CAN trade DOGE doesn't mean you SHOULD."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Leave the man alone, Bear. Let Meta-SCI worry about whether DOGE is tradeable. That's literally its job."</td></tr></table>

---

## Recipe 2: Switching to Meta-SCI (Recommended)

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"Want the bot to auto-select the best strategy for each market condition? Meta-SCI is the recommended default. It runs a tournament of all eligible strategies and picks the best signal."</td></tr></table>

**Via GUI:**
1. Profile Editor → Select profile → **General** tab.
2. Set **Strategy** to `Meta-SCI`.
3. Save. Done.

**Via config.json:**
```json
"my_profile": {
  "strategy": "meta_sci"
}
```

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"If you're not using Meta-SCI, I need you to have a very good reason. 'I read a blog post' is not a reason. 'I backtested 500 trades and Rubberband outperformed on my specific symbols' — that's a reason."</td></tr></table>

---

## Recipe 3: Assigning Different Strategies per Asset Class

<table><tr><td width="170"><img src="img/ninja.png" width="150"></td><td><b>NINJA</b>:<br><em>"Different weapons for different battlefields."</em></td></tr></table>

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

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"I heard OANDA is good for forex. How do I set it up?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"OANDA is excellent for forex. Competitive spreads. Solid API. Here's how to connect it in under 5 minutes:"</td></tr></table>

1. **Get API credentials:**
    - Log into [OANDA Hub](https://hub.oanda.com)
    - Go to **Manage API Access**
    - Generate a new token and copy it immediately (you can't see it again)
2. **Configure via GUI:**
    - Settings → **Brokers** → **OANDA** tab
    - Enter Account ID: `101-001-1234567-001`
    - Paste API Key
    - Set Environment: `practice` (demo) or `live`
3. **Or via .env.secrets:**
    ```bash
    OANDA_ACCOUNT_ID=101-001-1234567-001
    OANDA_API_KEY=your-token-here
    OANDA_ENVIRONMENT=practice
    ```
4. **Restart the bot.**

---

## Recipe 5: Making the Bot More Aggressive

<table><tr><td width="170"><img src="img/pirate.png" width="150"></td><td><b>PIRATE</b>:<br>"The bot is too timid! I want MORE TRADES! MORE TREASURE! 🏴‍☠️"</td></tr></table>

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"Now calm down, honey. Be careful lowering those thresholds. The bot is being selective for a reason."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Fine, you want more action? Lower the entry score threshold. But understand what you're doing — you're telling the bot to accept lower-quality setups. That's not 'more aggressive.' That's 'less picky.' There's a difference."</td></tr></table>

1. Settings → **System** tab (or edit `config.json`).
2. Find `icc_entry_score_threshold`.
3. Lower it:
    - `65.0`: Conservative. Only A-grade setups.
    - `55.0`: The recommended default. B-grade setups.
    - `40.0`: Will trade C-grade setups (riskier).
    - `30.0`: Will trade almost anything that moves (DANGER).
4. **Save** (bot picks up changes on next cycle).

<table><tr><td width="170"><img src="img/bear.png" width="150"></td><td><b>BEAR</b>:<br>"30.0? You might as well hand your money to a stranger on the street. At least the stranger would say thank you."</td></tr></table>

---

## Recipe 6: The "Kill Switch" Reset

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"The bot just screamed 'Kill Switch Activated!' and stopped! What do I do?!"</td></tr></table>

<table><tr><td width="170"><img src="img/bot.png" width="150"></td><td><b>THE BOT</b>:<br><em>"I detected critical errors and shut myself down to protect your capital. Five failures in a row. Something is wrong and I'm not going to keep trying the same thing expecting different results. You're welcome."</em></td></tr></table>

1. **Check the logs:** `tail -n 50 logs/tradebot.log`
    - `Insufficient Funds`? You are broke. (See Recipe 2 in Panic Button.)
    - `Permission Denied`? API key doesn't have trade permissions.
    - `Timeout`? Internet issue.
2. **Wait:** It has a cooldown (usually 3 cycles). It might reset itself.
3. **Hard Reset:** `./scripts/tradebot.sh --restart` — clears the error counter immediately.

---

## Recipe 7: Debugging "Why didn't it trade?"

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"A very common question. Possibly the MOST common question. Here's your diagnostic checklist:"</td></tr></table>

1. **Check Position Lock:** Already an open position for that symbol?
    - Look for `[POSITION LOCK]` in logs.
2. **Check Leverage Sentry:** Over-leveraged?
    - Look for `[SAFETY] Entry Blocked: Leverage Sentry` in logs.
3. **Check ICC Score:** Setup score too low?
    - `[ICC] EURUSD Score 42.1 below threshold 55.0 — rejected`
4. **Check Affordability:** Enough capital?
    - `[AFFORDABILITY BLOCK] Required $50 > Free $3.50`
5. **Check Meta-SCI Tournament:**
    - `[META-SCI] Tournament: No qualifying signals found` → Bot is being selective (good)
    - `[META-SCI] 🏆 Winner: trend_rider (score: 78.5)` → Signal found, check guards

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Nine times out of ten, the bot not trading is the bot doing its job. The tenth time, you forgot to add symbols to your profile. Check the simple things first before assuming something is broken."</td></tr></table>

---

## Recipe 8: Running a Backtest

<table><tr><td width="170"><img src="img/monk.png" width="150"></td><td><b>MONK</b>:<br><em>"Test in silence before trading in the storm."</em></td></tr></table>

```bash
# Quick forex backtest (7 days)
poetry run python tools/run_forex_backtest.py

# Quick crypto backtest (3 days)
poetry run python tools/run_crypto_backtest.py

# 30-day head-to-head strategy comparison
poetry run python tools/cartridges/forex_30day_h2h.py
```

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Run the backtest BEFORE you go live. Not after. Not 'I'll do it later.' NOW. Backtesting is free. Losses are not."</td></tr></table>

---

## Recipe 9: Switching Between Brokers

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Trading multiple asset classes? Use different brokers. Each one is a specialist:"</td></tr></table>

1. **IBKR for Stocks/Futures:** Settings → Brokers → IBKR
2. **OANDA for Forex:** Settings → Brokers → OANDA
3. **CCXT for Crypto (Gemini, Coinbase, Kraken):** Settings → Brokers → CCXT
4. **Hybrid Mode:** Use one broker for data, another for execution
    - Set `MARKET_DATA_MODE` and `BROKER_MODE` in environment

---

## Recipe 10: Enabling Paper Trading (Simulation Mode)

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"Not ready to trade real money yet, sweetie? That's smart. That's the smartest thing you've done since you started reading this manual. Start with paper trading."</td></tr></table>

1. **Via GUI:** Settings → System → **Execution Mode** → Toggle OFF "Execute Real Trades"
2. **Via .env.secrets:**
    ```bash
    EXECUTE_TRADES=false
    ```
3. The bot will log decisions but won't place actual orders. All the analysis, none of the risk.

---

## Recipe 11: Understanding Position Lock

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"The bot opened a trade but now it's ignoring new signals for that symbol. Is it broken?"</td></tr></table>

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"That's <b>Position Lock</b> working correctly. It entered a trade. Now it blocks ALL new entry signals for that symbol until the trade closes naturally. Why? Prevents whipsaw flipping — long, short, long, short — which is how accounts get destroyed faster than a piñata at a birthday party."</td></tr></table>

- **When it clears:** Automatically when the position closes (SL, TP, or exit logic).
- **Important:** If you manually close the trade outside the bot, Position Lock won't know. Restart the bot to clear it.
