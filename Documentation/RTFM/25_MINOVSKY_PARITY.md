---
title: 'The Minovsky Engine: Temporal Parity & Advanced Simulation'
category: rtfm
icon: hourglass_empty
description: 'Backtesting is easy when you cheat. We do not cheat. The Minovsky Engine implements a strict Temporal Domain Split, separating wall-clock display from sim-time processing, ensuring perfect paper-trade parity and enabling Tier-S cross-symbol auto-discovery.'
---

# 51. The Minovsky Engine: Temporal Parity

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"Welcome to the thermodynamics of the Tradebot ecosystem. Backtesting in PineScript is easy because PineScript lets you look into the future to validate the past. The Minovsky Engine, however, enforces strict Temporal Parity."</td></tr></table>

The core problem with algorithmic simulation is **data leakage**. If your bot can see that a 4-hour candle closed bearish at 16:00, but it executes a trade at 13:00 to front-run that movement, your simulation is lying to you. To prevent this, the TradeBot uses the **Minovsky Engine**.

---

## The Temporal Domain Split

<table><tr><td width="170"><img src="img/ninja.png" width="150"></td><td><b>NINJA</b>:<br><em>"Two clocks tick simultaneously. The clock you see, and the clock the machine feels. Never confuse the two."</em></td></tr></table>

When operating the backtester or running the paper-trading websocket streams, the Engine physically separates time into two domains:

1. **Wall-Clock (Display Time):** The physical time you are observing the GUI dashboard.
2. **Sim-Time (Processing Time):** The restricted localized timeline the active strategy logic and Safety Guards are allowed to process.

### Why Does This Matter?
If you run `tools/run_forex_backtest.py`, the Safety Guards (`Position Lock`, `PDT Guard`, `Daily Loss Limit`) must evaluate their conditions based entirely on *Sim-Time*. If the Daily Loss Limit checks your account's PnL using the *Wall-Clock* while simulating a trade from six months ago, the bot will immediately crash and burn because the temporal metrics do not match.

**The Rule:** The `AGE` column in paper trading overrides all standard latency checks to maintain visual parity across localized replay jumps.

---

## Tier-S Cross-Symbol Discovery

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Testing a strategy on a random Tuesday in August when the market didn't move for 9 hours is useless. Why waste CPU cycles? The bot hunts for the bloodbaths."</td></tr></table>

The Engine includes a robust **Trending Scorer** that pre-analyzes historical data before running full simulations. It aggregates the Average True Range (ATR) and standard deviations across *multiple* synchronized assets to auto-select **Tier-S Days** (e.g., high-volatility events like Jan 30 / Jan 22).

Instead of making you manually guess which dates had the most insane market structure, the Engine automatically discovers them and benchmarks your strategies against the absolute hardest environments.

---

## The 80% Majority-Threshold Logic

What happens when you simulate an algorithmic strategy requiring synchronized data across 5 different symbols, but `WTICOUSD` (Crude Oil) had a 3-hour data outage on your broker's end for that specific day? 

Other bots crash. The Minovsky Engine doesn't.

It implements majority-threshold intersection logic. If **80%** of your active symbols return clean candle data for a requested timeblock, the Engine artificially bridges the sparse data gap for the missing secondary symbol so the tournament can continue running. 

<table><tr><td width="170"><img src="img/ghost.png" width="150"></td><td><b>GHOST (The AI)</b>:<br><em>"The machine heals the timeline. It patches the missing hours so the simulation survives."</em></td></tr></table>

---

## 📖 Continue Reading

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"Wow, okay I think I get it now. What's next?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Turn the page. We are going to talk about <b>Global Scheduler</b>. Try to keep up."</td></tr></table>
