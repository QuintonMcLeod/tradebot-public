
# 14. Reading the Scoreboard
> *"If you can't measure it, you can't improve it."*

So the bot is running. Trades are happening. Numbers are flying across your screen. But what do they actually mean? This guide teaches you how to read your trading performance like a professional — and more importantly, when to worry and when to be patient.

---

## The Big Five: Metrics That Actually Matter

### 1. Profit Factor

**What it is:** Total gross profit ÷ Total gross loss.

| Profit Factor | What It Means |
|---------------|--------------|
| **< 1.0** | You're losing money. Every dollar risked returns less than a dollar. |
| **1.0 - 1.5** | Marginal. You're barely breaking even after fees. |
| **1.5 - 2.5** | Solid edge. This is where most profitable systems live. |
| **2.5+** | Excellent — but verify it's not curve-fit or a small sample. |

**The Rule:** A profit factor of 1.5+ over 100+ trades means the system has a real edge. Under 50 trades, it's statistical noise.

---

### 2. Win Rate

**What it is:** Percentage of trades that were profitable.

**The Trap:** Most people obsess over win rate. Don't. A 30% win rate with 4:1 reward-to-risk is far more profitable than a 70% win rate with 1:1.

| Win Rate | R:R Needed to Profit |
|----------|---------------------|
| 25% | 3:1 minimum |
| 33% | 2:1 minimum |
| 50% | 1:1 minimum |
| 66% | 0.5:1 minimum |

**The Rule:** Win rate is meaningless without knowing the Reward-to-Risk ratio. Always look at them together.

---

### 3. Maximum Drawdown

**What it is:** The largest peak-to-trough decline in your equity.

| Drawdown | Severity |
|----------|---------|
| **< 10%** | Normal. Part of any system. |
| **10-20%** | Uncomfortable but manageable. Review if it persists. |
| **20-30%** | Warning zone. Check if strategy still matches market conditions. |
| **30%+** | Critical. Consider reducing risk or pausing. |

**The Math Problem:** A 50% drawdown requires a 100% gain to recover. A 25% drawdown only needs 33%. This is why capital preservation always beats aggressive growth.

| Drawdown | Gain Needed to Recover |
|----------|----------------------|
| 10% | 11.1% |
| 20% | 25.0% |
| 30% | 42.9% |
| 50% | 100.0% |
| 75% | 300.0% |

**The Rule:** If max drawdown exceeds 25%, something needs to change — either the risk per trade or the strategy assignment.

---

### 4. Average R:R (Reward-to-Risk Ratio)

**What it is:** Average winning trade size ÷ Average losing trade size.

| Avg R:R | Quality |
|---------|---------|
| **< 1.0** | Your winners are smaller than your losers. Dangerous. |
| **1.0 - 2.0** | Acceptable with a decent win rate. |
| **2.0 - 3.0** | Good. The system is letting winners run. |
| **3.0+** | Excellent. The bot is catching real moves. |

**The Rule:** If your R:R drops below 1.5 consistently, check your exit logic. You might be cutting winners too early or holding losers too long.

---

### 5. Expectancy (Per-Trade Edge)

**What it is:** How much you expect to make per trade, on average.

```
Expectancy = (Win Rate × Avg Win) - (Loss Rate × Avg Loss)
```

**Example:**
- Win Rate: 35%, Avg Win: $150
- Loss Rate: 65%, Avg Loss: $50
- Expectancy: (0.35 × $150) - (0.65 × $50) = $52.50 - $32.50 = **+$20.00 per trade**

If expectancy is positive, you have an edge. If it's negative, you're bleeding.

**The Rule:** Positive expectancy + enough trades = profit is mathematically inevitable.

---

## Reading the Dashboard

### The Holdings Panel

| Column | What It Tells You |
|--------|------------------|
| **Symbol** | Which asset the bot is trading |
| **Direction** | LONG (betting price goes up) or SHORT (betting it goes down) |
| **Size** | How many units the bot bought/sold |
| **Entry Price** | Where the bot entered the trade |
| **Current Price** | Where the market is right now |
| **PnL** | Unrealized profit/loss on this position |
| **Strategy** | Which strategy generated this trade |

**Green PnL** = in profit. **Red PnL** = underwater. Don't panic at red — every trade goes underwater at some point.

### The Decisions Panel

This shows you what the bot is *thinking* each scan cycle:

| Decision | Meaning |
|----------|---------|
| **ENTER_LONG** | Bot wants to buy (expects price to rise) |
| **ENTER_SHORT** | Bot wants to sell (expects price to fall) |
| **HOLD** | Bot is watching but not acting yet |
| **STAND_ASIDE** | No qualifying setup found — this is healthy |
| **EXIT** | Bot is closing a position |

**A day full of STAND_ASIDE is not a bad day.** It means the bot is protecting you from bad setups.

---

## The Performance Report

After running for a while, these are the numbers to check:

### Daily Check (Glance)
- **Open positions** — How many trades are active?
- **PnL today** — Are you green or red?
- **Any blocked trades?** — Check if safety guards are firing (Position Lock, Leverage Sentry, etc.)

### Weekly Check (Review)
- **Win rate this week** — Is it roughly in line with expectations?
- **Largest win vs. largest loss** — Are wins bigger than losses?
- **Number of trades** — Is the bot trading the expected frequency?

### Monthly Check (Analysis)
- **Profit factor** — Is it above 1.5?
- **Max drawdown** — Has it exceeded your comfort zone?
- **Expectancy** — Is the per-trade edge still positive?
- **Strategy attribution** — Which strategies are generating the best trades?

---

## When to Worry (And When NOT To)

### 🟢 Don't Worry
- **3 losses in a row** — Normal. Even great systems lose 5-7 in a row regularly.
- **No trades today** — The bot is being selective. That's the point.
- **Small PnL day** — Not every day is a home run. Consistency beats fireworks.
- **One bad week** — Zoom out. Look at the 30-day picture.

### 🟡 Keep an Eye On
- **10+ losses in a row** — Possible regime shift. Check if the market condition matches your strategy.
- **Win rate dropping below 20%** — Over 50+ trades, this suggests the edge may be fading.
- **Drawdown approaching 20%** — Consider reducing `risk_per_trade_pct` temporarily.

### 🔴 Take Action
- **Drawdown exceeds 30%** — Reduce risk immediately. Switch to paper trading to diagnose.
- **Profit factor below 1.0 over 100+ trades** — The system is losing money. Review strategy assignment.
- **Bot not trading for 48+ hours in active markets** — Check for errors, API disconnects, or expired credentials.
- **Capital approaching zero** — Kill switch. Stop trading. Diagnose.

---

## The Patience Tax

The hardest part of systematic trading isn't the math — it's the waiting.

The bot will have losing days. It will have losing weeks. The question isn't "did I win today?" but "is my edge still intact over the last 100 trades?"

> *Think of it like a casino. The house doesn't win every hand — but over 10,000 hands, the math always wins. You are the house.*

If your profit factor is above 1.5, your expectancy is positive, and your drawdown is manageable — **the only thing you need to do is not interfere.**

The bot's worst enemy isn't the market. It's the person who turns it off after 3 red days.

---

## Quick Reference Card

| Metric | Healthy Range | Red Flag |
|--------|-------------|----------|
| Profit Factor | > 1.5 | < 1.0 |
| Win Rate | 25-50% (with good R:R) | < 15% over 100+ trades |
| Max Drawdown | < 20% | > 30% |
| Avg R:R | > 2.0 | < 1.0 |
| Expectancy | Positive | Negative over 100+ trades |
| Trades/Week | 5-30 (varies by config) | 0 for 48+ hours |
