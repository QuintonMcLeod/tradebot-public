---
title: 08 The Accounting Engine: PnL Integrity & Cost Basis Physics
category: rtfm
icon: calculate
description: 'How the bot handles the math of money. A deep dive into the Futures Capital Model, Slippage Injection for paper trading, and the temporal AGE parity that synchronizes simulated metrics to real-world physics.'
---

# 08. The Accounting Engine: PnL Integrity

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"A $1,000 algorithmic profit in simulation that drops to a $400 physical profit in a live environment is an unacceptable variance in physics. The Accounting Engine bridges this logic gap."</td></tr></table>

Most trading bots run on *Spot Physics*. If you buy 1 BTC at $60,000, the bot assumes you physically extracted $60,000 from your cash balance to hold the asset, then returned the $60,000 plus profit upon sale. But margin brokers don't work like that.

## The Futures Capital Model

TradeBot SCI operates exclusively on the **Futures Capital Model**. 

When a trade is entered, the actual principal value of the asset *does not leave your wallet*. Instead, the Accounting Engine mathematically computes the position sizing leverage, isolates the margin impact, and natively subtracts only the **fees** and **latency spread** to determine your Entry Cost Basis. 

1. **Law of Fees:** Entry = `-= fees`. Your principal remains visible and active.
2. **Law of PnL:** Exit = `+= net_pnl`. No principal recovery calculations are injected.
3. **Law of Direction:** Shorts are calculated independently (using `_calculate_pnl`) rather than treating them as inverted Spot buys. This ensures negative cost-basis math does not erroneously inflate returns.

---

## Paper Trading Liability: Slippage Injection

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"If your paper trading makes 60% a month and your live account makes 2%, your paper trader is lying to you. I fixed the liar."</td></tr></table>

By default, an exchange's Paper Trading API guarantees you perfect fills on every position with zero latency. In reality, large market orders experience depth-of-book slippage. 

The Accounting Engine forces **Slippage Injection** into all paper trading environments. It purposefully degrades your simulated entry and exit prices based on asset volatility and theoretical order-book thickness. This forces the bot to overcome realistic friction, ensuring the strategy actually has a structural edge and isn't just profiting off simulated micro-spreads.

---

## Paper Trade Visibility & Temporal Age

To complete the integrity overhaul, the system implements a dedicated `'holdings'` WebSocket stream designed specifically for real-time visibility parity.

*   **The AGE Column Parity:** Trades held in simulation now natively inherit the `AGE` property, tracking physical wall-clock life-cycles even when stepping through historical backend backtests. This allows you to evaluate exactly how long a trade was held and guarantees that the "duration" math matches between your simulated PnL ledgers and live broker dashboards.

---

## 📖 Continue Reading

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"Wow, okay I think I get it now. What's next?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Turn the page. We are going to talk about <b>Market Personalities</b>. Try to keep up."</td></tr></table>
