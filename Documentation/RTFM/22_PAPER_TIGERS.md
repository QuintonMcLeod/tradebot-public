# 22. Paper Tigers — Simulation & Paper Trading

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br><em>"Would you test a parachute by jumping off a cliff? Then don't test a trading strategy with real money."</em></td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Before you connect your broker, enter your API keys, and let the bot loose on the live markets with your hard-earned cash... STOP. Drop your mouse.<br><br>Run it in Paper Mode first! I do not care how confident you are. I do not care if the backtest looked like a staircase to heaven. Paper trade it! The market has a very funny way of humbling people who think they're smarter than the process."</td></tr></table>

---

## What is Paper Trading?

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"Paper trading is simulated trading. The bot does everything exactly the same as live — scans markets, analyzes charts, applies strategies, makes decisions — except at the moment of execution, instead of sending a real order, it writes the trade on virtual paper."</td></tr></table>

- **Market data?** Real. Live prices from real exchanges.
- **Strategy logic?** Identical to live. Same code path.
- **Orders?** Simulated. No real money moves.
- **P&L?** Tracked virtually.

---

## Why Paper Trading Matters

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"Do I really need to paper trade? Can't I just go live?"</td></tr></table>

<table><tr><td width="170"><img src="img/bear.png" width="150"></td><td><b>BEAR</b>:<br>"Famous last words."</td></tr></table>

### 1. Strategy Validation
"Does Meta-SCI work on crypto?" Paper trade it for a week. Zero risk.

### 2. Configuration Testing
"What happens if I lower `structure_score_threshold` to 50?" Try it in paper. If 47 trades fire in one day, that threshold was too low.

### 3. Learning the System
Paper Mode is your training wheels. Watch how the bot scans, decides, and would have traded.

### 4. New Asset Testing

<table><tr><td width="170"><img src="img/ninja.png" width="150"></td><td><b>NINJA</b>:<br><em>"Want to add GBP/JPY to your universe? Paper trade it first. That pair is nicknamed 'The Dragon' — 200+ pips a day. It will eat your stop-loss for breakfast."</em></td></tr></table>

---

## How to Enable Paper Mode

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"Just toggle Live Trading OFF, sweetie."</td></tr></table>

> 📺 Settings → **System** → toggle **Live Trading** OFF

```yaml
runtime:
  execute_trades: false
```

The bot runs normally but never sends orders. The built-in `PaperBroker` simulates fills, tracks positions, and calculates P&L as if trades were real.

---

## What the Paper Broker Tracks

| Metric | How It's Calculated |
|--------|-------------------|
| **Virtual Positions** | Symbol, side, size, entry price — just like a real broker |
| **Unrealized P&L** | Current price vs. entry price |
| **Realized P&L** | Logged when virtual position closes |
| **Win Rate** | Percentage of profitable paper trades |
| **Trade Count** | Total paper trades taken |

Stored in `data/paper_trade_results.json` and `data/paper_ledger.json`.

---

## Paper Mode vs. Backtesting

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"Both are important. Here's the distinction:"</td></tr></table>

| Feature | Paper Mode | Backtesting |
|---------|-----------|-------------|
| **Data** | Live, real-time | Historical |
| **Speed** | Real-time | Fast-forward |
| **Fills** | Simulated at market price | Simulated at historical price |
| **Purpose** | "How does the bot behave NOW?" | "How would it have performed THEN?" |
| **Duration** | Days to weeks | Minutes to hours |

---

## When to Graduate to Live

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"The checklist:"</td></tr></table>

- [ ] Paper traded for at least 1 week
- [ ] Win rate is reasonable (40%+ trend, 55%+ mean reversion)
- [ ] Profit factor above 1.0
- [ ] Max drawdown within tolerance
- [ ] You understand every decision the bot made
- [ ] You're NOT doing this because of FOMO
- [ ] You've read The Shield Wall (Article 18)
- [ ] Starting with small position sizes

<table><tr><td width="170"><img src="img/monk.png" width="150"></td><td><b>MONK</b>:<br><em>"If you can't check every box, keep paper trading. There's no prize for going live early. The market will still be there next week."</em></td></tr></table>

---

## The Harsh Truth

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Paper trading has exactly one limitation: it doesn't simulate <b>your fragile emotional state.</b> In paper mode, watching a trade go into the red by $200 feels like nothing. In live mode, that same -$200 makes you sweat, makes you want to close early, override the bot, and 'manage' the position like a moron.<br><br>Paper mode teaches you the system. Live mode teaches you how weak your discipline actually is.<br><br>Start on paper. Graduate to live with small sizes. Scale up only when you figure out how to stop hyperventilating."</td></tr></table>
