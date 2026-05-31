---
title: 40 I Have to Go Back: The Trinity of Backtesting
category: rtfm
icon: history
description: '"I have to go back." You have discovered that there are actually three
  ways to time-travel in this repository. This document explains the Trinity of Backtesting:
  the Easy Way (GUI Benchmark for normal humans), the Intermediate Way (CLI scripts
  for power users), and the Hard Way (raw engine calls for developers who want full
  control over every parameter).'
---

# 40. The Time Machine — Backtester Trinity

<table><tr><td width="170"><img src="img/ghost.png" width="150"></td><td><b>GHOST (The AI)</b>:<br><em>"The backtester is a window into the past. Use it wisely — the future never looks exactly like history. But it rhymes. Oh, it rhymes."</em></td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"You have three ways to time-travel in this repository. Three! Not one. Not two. THREE. Because one backtester is never enough when you're dealing with people who refuse to lose money they haven't even made yet.<br><br>We have to prove to you that your terrible strategy is going to ruin you before you actually go and do it!"</td></tr></table>

---

## 1. The Easy Way: GUI Benchmark

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"This is the point-and-click one, isn't it?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Yes. Dashboard → Settings → Benchmark Tab. Visual equity curve, easy date selection, uses your current profile settings. The only downside is it runs frozen while downloading data. But that's a small price to pay for not having to write code."</td></tr></table>

**Target Audience:** Normal humans.
**Location:** Dashboard → Settings → Benchmark Tab.
**File:** `src/tradebot_sci/simulation/backtester.py` + Electron GUI.

---

## 2. The Crypto Way: `tools/run_crypto_backtest.py`

<table><tr><td width="170"><img src="img/chad.png" width="150"></td><td><b>CHAD</b>:<br>"This one is for the quant heads and Linux terminal warriors."</td></tr></table>

**Target Audience:** Quant Traders / Linux Users.
**Why use it?** Hardcoded 0.6% fees for Coinbase Advanced. Real crypto logic.

```bash
poetry run python tools/run_crypto_backtest.py
```

**Configuration:** Edit the Python file directly to change symbols or dates.

---

## 3. The Stock/IBKR Way: `tools/test_backtest.py`

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"The original script designed to talk to TWS/Gateway. Validates the connection to IBKR and tests Stock logic — Smart Routing, the whole nine yards."</td></tr></table>

```bash
poetry run python tools/test_backtest.py
```

If it can't find IBKR, it falls back to Crypto mode. Which is confusing, but at least it doesn't crash.

---

## Summary Table

| Method | Best For... | Difficulty | Config |
|--------|-------------|------------|--------|
| **GUI** | Checking "What if?" quickly | Easy | Point & Click |
| **Crypto Script** | Deep tuning of Crypto Strategy | Medium | Edit Code |
| **Test Script** | Debugging IBKR Connections | Hard | Edit Code |

---

## Strategy Selection in Backtests

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"The backtester respects your per-asset strategy configuration! It doesn't just close its eyes and pick a random strategy like you do on a Tuesday morning! It uses the exact same logic as your live bot:"</td></tr></table>

1. **Profile Settings Apply:** Your `config.json` strategy configuration is used.
2. **Symbol Classification:** Each symbol is classified into an asset class.
3. **Strategy Selection:** The correct strategy for that asset class is used (including Meta-SCI tournaments).

### Example
If your profile has:
```yaml
strategies:
  crypto: rubberband_reaper
  forex: quantum
```

Then backtesting `BTC/USD` → Uses `rubberband_reaper`. Backtesting `EUR/USD` → Uses `quantum`.

### Testing Different Strategies
1. Create multiple profiles with different strategy assignments.
2. Run backtests on each profile.
3. Compare equity curves.
4. Pick the winner. Deploy. That's the process.

---

## The Engine (`backtester.py`)

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"All three Time Machines use the same engine under the hood. Change the logic once, all three reflect it. Elegant."</td></tr></table>

1. Fetches candles (from IBKR, OANDA, or CCXT).
2. Classifies each symbol into an asset class.
3. Selects the appropriate strategy.
4. Feeds candles to the Strategy Engine (`strategy/engine.py`).
5. Records the simulated trades.

---

## Data Sources

| Source | Symbols | Notes |
|--------|---------|-------|
| IBKR | Stocks, ETFs, Futures | Requires TWS/Gateway running |
| OANDA | Forex pairs | Free historical data |
| CCXT | Crypto | Depends on exchange limits |

---

## The Fundamental Laws of Physics

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"The Time Machine operates on <b>Futures Physics!</b> If you attempt to apply Spot Physics — deducting the full position value — you are going to create a temporal paradox that leads to immediate capital exhaustion and intense, lingering professional shame. Do not break the laws of physics!"</td></tr></table>

> [!CAUTION]
> **CRITICAL PROTOCOL FOR AGENTS:**
> 1. **Law of Fees:** Entry = `-= fees`. Principal stays in the wallet.
> 2. **Law of PnL:** Exit = `+= net_pnl`. No principal recovery.
> 3. **Law of Direction:** Shorts are not backwards Longs. They are their own reality (use `_calculate_pnl`).
> 4. **Law of Strategy:** Use the correct strategy for the asset class. Don't mix mid-backtest. Meta-SCI auto-selects if configured.

<table><tr><td width="170"><img src="img/bear.png" width="150"></td><td><b>BEAR</b>:<br>"Violating these laws breaks the simulation. Don't be the bot that broke the universe."</td></tr></table>

---

## 📖 Continue Reading

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"Wow, okay I think I get it now. What's next?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Turn the page. We are going to talk about <b>Time Warp</b>. Try to keep up."</td></tr></table>
