---
title: Am I Winning? How to Read Your Performance Metrics
category: rtfm
icon: monitoring
description: "\"If you can't measure it, you can't improve it.\" So the bot is running.\
  \ Trades are happening. Numbers are flying across your screen. But what do they\
  \ actually mean? This guide teaches you the Big Five metrics \u2014 Profit Factor,\
  \ Win Rate, Max Drawdown, R:R, and Expectancy \u2014 how to read the dashboard,\
  \ and when to worry versus when to be patient."
---

# 14. Reading the Scoreboard — Performance Metrics Decoded

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"Numbers don't lie. But they can mislead if you read them wrong. A 70% win rate sounds great until you realize the losses are 3× bigger than the wins. Let me teach you what each metric REALLY means — and more importantly, which ones to ignore."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Look at you. Staring at the screen like you're reading the Matrix. The bot is running, trades are happening, and you're sitting there with your mouth open looking at the Profit Factor wondering if 1.2 is a grade point average or a temperature.<br><br>Listen to me. If you can't read your own P&L, you are going to lose all your money, and you're going to deserve it. This chapter teaches you how to read performance like an adult. Pay attention."</td></tr></table>

---

## The Big Five: Metrics That Actually Matter

### 1. Profit Factor

**What it is:** Total gross profit ÷ Total gross loss.

| Profit Factor | What It Means |
|---------------|--------------|
| **< 1.0** | You're losing money. Every dollar risked returns less than a dollar. |
| **1.0 - 1.5** | Marginal. Barely breaking even after fees. |
| **1.5 - 2.5** | Solid edge. This is where most profitable systems live. |
| **2.5+** | Excellent — but verify it's not curve-fit or a small sample. |

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"If your profit factor is 1.5 after a hundred trades, you have a real edge. If you have a profit factor of 6.0 after THREE trades, you don't have an edge, you have luck and a gambling problem. That's statistical noise. Stop acting like a genius after two lucky guesses."</td></tr></table>

---

### 2. Win Rate

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"I want at least 80% win rate!"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"EIGHTY PERCENT?! You sound like a child asking Santa for a pet dinosaur! EIGHTY PERCENT?! Do you know who has an 80% win rate? Nobody who makes real money! Here's why that's a trap for stupid people:"</td></tr></table>

A 30% win rate with 4:1 reward-to-risk is FAR more profitable than a 70% win rate with 1:1. The math:

| Win Rate | R:R Needed to Profit |
|----------|---------------------|
| 25% | 3:1 minimum |
| 33% | 2:1 minimum |
| 50% | 1:1 minimum |
| 66% | 0.5:1 minimum |

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"Win rate is meaningless without Reward-to-Risk ratio. Always look at them together. One without the other is like knowing your speed but not your direction."</td></tr></table>

---

### 3. Maximum Drawdown

**What it is:** Largest peak-to-trough decline in your equity.

| Drawdown | Severity |
|----------|---------|
| **< 10%** | Normal. Part of any system. |
| **10-20%** | Uncomfortable but manageable. Review if it persists. |
| **20-30%** | Warning zone. Check if strategy still matches market. |
| **30%+** | Critical. Reduce risk or pause. |

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Here is the math that keeps me awake at night, because I know none of you understand it:"</td></tr></table>

| Drawdown | Gain Needed to Recover |
|----------|----------------------|
| 10% | 11.1% |
| 20% | 25.0% |
| 30% | 42.9% |
| 50% | 100.0% |
| 75% | 300.0% |

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"If you lose 50% of your money, you don't need 50% to get it back. YOU NEED A HUNDRED PERCENT! You have to double your account just to get back to zero! That's not a comeback story, that's a miracle! This is why capital preservation beats your greedy little attempts at aggressive growth. The math does not negotiate with your ego."</td></tr></table>

---

### 4. Average R:R (Reward-to-Risk Ratio)

| Avg R:R | Quality |
|---------|---------|
| **< 1.0** | Winners smaller than losers. Dangerous. |
| **1.0 - 2.0** | Acceptable with decent win rate. |
| **2.0 - 3.0** | Good. The system is letting winners run. |
| **3.0+** | Excellent. The bot is catching real moves. |

---

### 5. Expectancy (Per-Trade Edge)

```
Expectancy = (Win Rate × Avg Win) - (Loss Rate × Avg Loss)
```

**Example:**
- Win Rate: 35%, Avg Win: $150
- Loss Rate: 65%, Avg Loss: $50
- Expectancy: (0.35 × $150) - (0.65 × $50) = $52.50 - $32.50 = **+$20.00 per trade**

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"Positive expectancy + enough trades = profit is mathematically inevitable. That's not hope. That's math. The same math that powers every casino on Earth."</td></tr></table>

---

## Reading the Dashboard

### The Holdings Panel

| Column | What It Tells You |
|--------|------------------|
| **Symbol** | Which asset the bot is trading |
| **Direction** | LONG or SHORT |
| **Size** | How many units |
| **Entry Price** | Where the bot entered |
| **Current Price** | Where the market is now |
| **PnL** | Unrealized profit/loss |
| **Strategy** | Which strategy generated this trade |

**Green PnL** = in profit. **Red PnL** = underwater. Don't panic at red — every trade goes underwater at some point.

### The Decisions Panel

| Decision | Meaning |
|----------|---------|
| **ENTER_LONG** | Bot wants to buy (expects rise) |
| **ENTER_SHORT** | Bot wants to sell (expects fall) |
| **HOLD** | Watching but not acting yet |
| **STAND_ASIDE** | No qualifying setup — this is healthy |
| **EXIT** | Closing a position |

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"A day full of STAND_ASIDE is NOT a bad day! It means the bot looked at the garbage market conditions and said, 'I'm not risking my boss's money on this crap.' That's discipline! You should be thanking it! Instead, you're sitting there tapping your watch like 'Come on, do a trick!' Stop it."</td></tr></table>

---

## The Performance Report

### Daily Check (Glance)
- Open positions healthy? SL/TP set?
- PnL today — green or red?
- Any blocked trades? (Position Lock, Leverage Sentry)

### Weekly Check (Review)
- Win rate in line with expectations?
- Largest win vs. largest loss — winners bigger?
- Number of trades — expected frequency?

### Monthly Check (Analysis)
- Profit factor above 1.5?
- Max drawdown within comfort zone?
- Expectancy still positive?
- Which strategies generating best trades?

---

## When to Worry (And When NOT To)

### 🟢 Don't Worry
- **3 losses in a row** — Normal. Great systems lose 5-7 in a row regularly.
- **No trades today** — The bot is being selective. That's the point.
- **Small PnL day** — Consistency beats fireworks.
- **One bad week** — Zoom out. Look at the 30-day picture.

### 🟡 Keep an Eye On
- **10+ losses in a row** — Possible regime shift.
- **Win rate below 20%** — Over 50+ trades, the edge may be fading.
- **Drawdown approaching 20%** — Consider reducing risk temporarily.

### 🔴 Take Action
- **Drawdown exceeds 30%** — Reduce risk immediately. Switch to paper.
- **Profit factor below 1.0 over 100+ trades** — System is losing money.
- **Bot not trading for 48+ hours** — Check for errors, API disconnects.
- **Capital approaching zero** — Kill switch. Stop. Diagnose.

---

## The Patience Tax

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"The hardest part of algorithmic trading isn't the math. It's YOU. It's your complete inability to sit still and wait. The bot is going to have losing days. It's going to have losing weeks. You know what you do during a losing week? YOU SHUT UP AND LET IT WORK. <br><br>The house in Vegas doesn't win every hand of blackjack, but over ten thousand hands, they own the entire strip! You are the house! Start acting like it! Stop panicking because a machine lost $12 on a Tuesday!"</td></tr></table>

If profit factor is above 1.5, expectancy is positive, and drawdown is manageable — **the only thing you need to do is not interfere.**

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
| Trades/Week | 5-30 (varies) | 0 for 48+ hours |


> [!NOTE]
> **APRIL 2026 UI & VITALS UPDATE:**  
> Listen up, you degenerates. We just dropped a massive update to the UI and Nurse's Station. The tooltips now trigger when you hover over the *entire goddamn card*, so your fat thumbs can't miss them anymore. The Exit Logic tab is now a clean, idiot-proof single column. We also fixed the Nurse's Station connection tracker—no more lying to you that the bot is dead when it's actively retrying to connect. Read **47_UI_OVERHAUL_AND_VITALS.md** for the full breakdown before you touch the controls and blow your account.
