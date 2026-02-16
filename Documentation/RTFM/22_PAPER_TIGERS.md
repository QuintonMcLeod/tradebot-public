
# 22. Paper Tigers (Simulation & Paper Trading)
> *"Would you test a parachute by jumping off a cliff? Then don't test a trading strategy with real money."*

Before you connect your broker, enter your API keys, and let the bot loose on the live markets with your hard-earned cash — **stop.**

Run it in Paper Mode first.

---

## What is Paper Trading?

Paper trading is simulated trading. The bot does everything exactly the same as live trading — scans markets, analyzes charts, applies strategies, makes decisions — except at the moment of execution, instead of sending a real order to a real broker, it writes the trade on a piece of virtual paper.

*   **Market data?** Real. Live prices from real exchanges.
*   **Strategy logic?** Identical to live. Same code path. Same decisions.
*   **Orders?** Simulated. No real money moves. No real positions opened. No real fills.
*   **P&L?** Tracked virtually. You can see exactly how much you would have made (or lost).

---

## Why Paper Trading Matters

### 1. Strategy Validation
"Does Meta-SCI actually work on crypto?" Paper trade it for a week and find out. Zero risk.

### 2. Configuration Testing
"What happens if I set `structure_score_threshold` to 50 instead of 60?" Try it in paper mode. If the bot starts taking 47 trades a day, you know the threshold was too low.

### 3. Learning the System
If you've never used the bot before, Paper Mode is your training wheels. Watch how it scans, decides, and would have traded. Understand the rhythm before you put money on the line.

### 4. New Asset Testing
Want to add GBP/JPY to your universe? Paper trade it first. That currency pair is nicknamed "The Dragon" for a reason — it moves 200+ pips a day and will eat your stop-loss for breakfast.

---

## How to Enable Paper Mode

There are two ways:

### Method 1: The Simple Way
Set `execute_trades` to `false` in your settings:

> 📺 **In the UI:** Settings → **System** → toggle **Live Trading** OFF

```yaml
runtime:
  execute_trades: false
```

The bot runs normally but never sends orders. Simple. Clean. Safe.

### Method 2: The Paper Broker
The bot has a built-in `PaperBroker` that simulates order fills, tracks virtual positions, and calculates P&L as if the trades were real.

This is what Sabbath Mode uses internally — during Sabbath, the `PaperBroker` takes over from the real broker. But you can use it anytime by running in simulation mode.

---

## What the Paper Broker Tracks

| Metric | How It's Calculated |
|--------|-------------------|
| **Virtual Positions** | Tracks symbol, side, size, entry price — just like a real broker |
| **Unrealized P&L** | Calculated from current live market price vs. entry price |
| **Realized P&L** | Logged when a virtual position is closed |
| **Win Rate** | Percentage of paper trades that were profitable |
| **Trade Count** | How many trades the bot took in paper mode |

All of this is stored in `data/paper_trade_results.json` and `data/paper_ledger.json`.

---

## Paper Mode vs. Backtesting: What's the Difference?

| Feature | Paper Mode | Backtesting |
|---------|-----------|-------------|
| **Data** | Live, real-time market data | Historical data |
| **Speed** | Real-time (1 scan every X seconds) | Fast-forward (weeks in seconds) |
| **Fills** | Simulated at market price | Simulated at historical price |
| **Purpose** | "How does the bot behave right now?" | "How would the bot have performed last month?" |
| **Duration** | Days to weeks | Minutes to hours |

**Use backtesting** to quickly validate a strategy over historical data.
**Use paper mode** to see how the strategy handles live, never-before-seen market conditions.

Both are important. Backtesting tells you the past. Paper mode tells you the present.

---

## When to Graduate to Live

The checklist for going live:

- [ ] Paper traded for at least 1 week
- [ ] Win rate is reasonable (40%+ for trend strategies, 55%+ for mean reversion)
- [ ] Profit factor is above 1.0 (you made more than you lost)
- [ ] Max drawdown is within your tolerance
- [ ] You understand every decision the bot made
- [ ] You're not doing this because of FOMO
- [ ] You've read the risk management article (The Shield Wall, Article 18)
- [ ] You're starting with small position sizes (you can always scale up)

If you can't check every box, keep paper trading. There's no prize for going live early. The market will still be there next week.

---

## The Harsh Truth

Paper trading has one limitation: it doesn't simulate **your emotions.** In paper mode, watching a -$200 unrealized loss feels like nothing. In live mode, that same -$200 makes you want to close the trade early, override the bot, and "manage" the position.

Paper mode teaches you the system. Live mode teaches you yourself.

Start paper. Graduate to live with small sizes. Scale up only when you trust both the bot and yourself.
