---
title: 'Engine Audit: The Minovsky Engine''s 14-Day Stress Test'
category: rtfm
icon: verified
description: '"Show me what you can do in two weeks." 2,278 trades. +$3,974 PnL. Profit
  Factor 2.10. SAR, Counter-Reversal, and Guillotine in full action. The complete
  14-day audit with per-symbol breakdown, big winners, worst losses, and system activity
  counts.'
---

# 36. Engine Audit — The Minovsky Engine's 14-Day Stress Test

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Look, every new engine takes the same test I give any human. Show me what you got in two weeks. Not 24 hours. Two weeks. That's enough time to figure out if you're actually good or if you just got lucky on the first date."</td></tr></table>

## The Setup

| Parameter | Value |
|-----------|-------|
| **Engine** | Minovsky Engine v1. |
| **Cartridge** | `conductor_14d_all` |
| **Period** | Feb 19 – Mar 5, 2026 (14 calendar days) |
| **Strategy** | Forex Conductor |
| **Capital** | $5,500 |
| **Risk** | 4.5% per trade |
| **Symbols** | 10 FX pairs (EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF, NZDUSD, EURJPY, GBPJPY, AUDJPY) |
| **Multi-Position** | ✅ Enabled (5 concurrent per symbol) |
| **Warmup** | 7 days (indicators process candles Feb 12–19 before first trade) |

---

## The Scorecard

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Alright, shut up and look at the numbers. The numbers don't lie."</td></tr></table>

| Metric | Value |
|--------|-------|
| **Total Trades** | 2,278 |
| **Wins / Losses** | 850 W / 1,428 L |
| **Win Rate** | 37% |
| **PnL** | **+$3,974.11** |
| **Profit Factor** | **2.10** |
| **Risk:Reward** | **3.53** |
| **Avg Win** | +$8.91 |
| **Avg Loss** | -$2.52 |
| **Final Balance** | **$9,474.11** |
| **Return** | **+72.3%** in 14 days |

<table><tr><td width="170"><img src="img/bull.png" width="150"></td><td><b>BULL</b>:<br>"SEVENTY-TWO PERCENT?! IN TWO WEEKS?! <em>*breathing intensifies*</em> ...I need a moment."</td></tr></table>

<table><tr><td width="170"><img src="img/bear.png" width="150"></td><td><b>BEAR</b>:<br>"The win rate is only 37%. You lose more trades than you win."</td></tr></table>

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"And that is exactly by design. The R:R is 3.53 — meaning every win is 3.5× the size of every loss. Win rate doesn't matter when the wins are that much bigger. A 37% win rate with a 3.5 R:R produces a <b>Profit Factor of 2.1</b>.<br><br>For comparison, most hedge funds celebrate when their PF exceeds 1.3."</td></tr></table>

---

## Per-Symbol Breakdown

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"Not every instrument performs equally. Some carry the orchestra, some are just along for the ride."</td></tr></table>

| Symbol | Trades | PnL | Contribution |
|--------|--------|-----|-------------|
| **AUDUSD** | 293 | **+$1,625** | 🏆 Star soloist |
| **EURUSD** | 176 | **+$1,006** | 🏆 First chair |
| NZDUSD | 592 | +$517 | ✅ Reliable |
| USDCHF | 211 | +$479 | ✅ Steady |
| USDJPY | 262 | +$320 | ✅ Consistent |
| GBPUSD | 162 | +$168 | ✅ Modest |
| EURJPY | 52 | +$2 | ➖ Break-even |
| GBPJPY | 32 | -$0.43 | ➖ Break-even |
| USDCAD | 90 | -$19 | ⚠️ Slight loss |
| AUDJPY | 408 | -$123 | ⚠️ Underperformer |

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"AUDUSD and EURUSD are Jordan and Pippen. They're carrying the whole team. The rest of these pairs are just standing around watching. AUDJPY is out there sweating, putting up shots, making a mess, but hey, at least he showed up to the game."</td></tr></table>

---

## ⚔️ The Three Weapons — SAR, CR & Guillotine

<table><tr><td width="170"><img src="img/ninja.png" width="150"></td><td><b>NINJA</b>:<br><em>"The Minovsky Engine has three defensive arts. Know them. Respect them. They're the reason you're not bankrupt."</em></td></tr></table>

### 🔁 SAR (Stop-and-Reverse) — 1,835 Events

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"SAR is the Uno Reverse Card. When ANY stop loss fires, the engine immediately opens a position in the <em>opposite</em> direction. Why? Because if price moved hard enough to stop you out, it's probably still moving — ride it the other way.<br><br>The chain guard limits consecutive SARs to 1 wrong reversal before switching to the safer Counter-Reversal."</td></tr></table>

**Example (AUDUSD, Feb 19):**
```
Trade #1:  SHORT @ 0.70530 → stopped at 0.70492 = -$86.79
   └─ SAR fires → LONG @ 0.70492

Trade #2:  LONG @ 0.70492 → stopped at 0.70422 = -$85.42
   └─ SAR CHAIN BLOCKED (1 consecutive SAR loss, limit=1)
   └─ Counter-Reversal fires instead (see below)
```

---

### 🔀 Counter-Reversal (CR) — 27 Events

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"When SAR fails — when the reversal itself gets stopped out — CR is the backup plan. It fires at <b>reduced risk</b> (0.225%) with a tight stop. Think of it as insurance: small cost if wrong, big payoff if right.<br><br>27 CRs fired in 14 days. That's 27 times the system said 'the reversal was wrong, but let me try one more time, carefully.'"</td></tr></table>

---

### 🗡️ Guillotine *(Disabled March 2026)* — 896 Events (826 T1 + 70 T2)

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Actually, I need to issue a correction. The Guillotine <em>was</em> the most important weapon. During this 14-day stress test, it fired 896 times. It saved capital relentlessly.<br><br>But there's a dark side to all that cutting: it also choked out <b>winners</b>. By slashing positions at -0.15R, it punished trades that just needed a little room to breathe during a normal pullback. The math worked — we had an incredible Profit Factor — but the win rate suffered because the Guillotine was too eager to execute.<br><br>So, as of March 2026, <b>we turned it off.</b> We let full stops hit. Our average loss went up, but our win rate skyrocketed to 51%. Our PnL recovered from an abysmal -$1,219 drawdown to a positive +$25 net gain in the exact same 14-day chop window. Turns out, sometimes you just need to put the blade away and let the market do its thing."</td></tr></table>

| Tier | Trigger | Action | Events |
|------|---------|--------|--------|
| **T1** | -0.15R to -0.90R | Cut 80% of position | 826 |
| **T2** | -0.30R | Cut 80% of remainder | 70 |
| **Stop (remnant)** | Full SL | Close the last 4% | 84 |

**Example cascade:**
```
Entry: SHORT @ 0.70530 (full size: 46,000 units)

  Price moves -0.15R against you:
  └─ Guillotine T1: cut 80% → 46,000 → 9,200 units (PnL: -$58)

  Price moves -0.30R:
  └─ Guillotine T2: cut 80% of remainder → 9,200 → 1,840 units (PnL: -$20)

  Price hits full stop:
  └─ Close remnant → 1,840 units (PnL: -$6)

  Total loss: ~$84
  Without Guillotine: ~$165
  SAVINGS: 49%
```

<table><tr><td width="170"><img src="img/monk.png" width="150"></td><td><b>MONK</b>:<br><em>"The blade falls before the victim knows it has been cut. That is mercy — for your capital."</em></td></tr></table>

---

## 🏆 The Big Winners

<table><tr><td width="170"><img src="img/pirate.png" width="150"></td><td><b>PIRATE</b>:<br>"SHOW ME THE TREASURE! Where's the gold?!"</td></tr></table>

| # | Symbol | Dir | Date | PnL | Exit |
|---|--------|-----|------|-----|------|
| 98 | EURUSD | Short | Feb 19 | **+$732.60** | 🎯 Target |
| 308 | AUDUSD | Short | Feb 20 | **+$423.86** | 🎯 Target |
| 675 | AUDUSD | Short | Feb 23 | **+$419.85** | 🎯 Target |
| 631 | AUDUSD | Long | Feb 22 | **+$333.01** | 🎯 Target |
| 629 | EURUSD | Long | Feb 22 | **+$311.67** | 🎯 Target |
| 118 | USDJPY | Long | Feb 19 | **+$270.25** | Trailed stop |
| 630 | USDCHF | Short | Feb 22 | **+$253.76** | 🎯 Target |
| 677 | USDCHF | Long | Feb 23 | **+$217.08** | 🎯 Target |
| 525 | AUDUSD | Long | Feb 20 | **+$198.28** | Trailed stop |
| 132 | NZDUSD | Short | Mar 5 | **+$189.23** | 🎯 Target |

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"8 out of 10 big winners hit FULL target. That's the 3R target. The other 2 were trailed stops — the stop was moved into profit and price reversed, but we still banked.<br><br>This is how a 37% win rate makes almost $4,000 in 14 days. Because when you win, you WIN. Each one of those target hits is 3.5x the average loss."</td></tr></table>

---

## 💀 The Bad Beats

<table><tr><td width="170"><img src="img/bear.png" width="150"></td><td><b>BEAR</b>:<br>"Don't just show me the wins. Show me the pain."</td></tr></table>

| # | Symbol | Dir | Date | PnL | What Happened |
|---|--------|-----|------|-----|---------------|
| 1 | USDCAD | Long | Feb 23 | **-$207.14** | Guillotine T1 at -0.72R — violent move blew past initial tiers |
| 2 | NZDUSD | Short | Feb 19 | **-$183.10** | Lower-High invalidation — fast reversal hit scale-out |
| 3 | AUDUSD | Long | Feb 19 | **-$157.89** | Guillotine T1 at -0.61R — single candle drove through |
| 4 | AUDUSD | Short | Feb 23 | **-$137.51** | Guillotine T1 at -0.50R — choppy conditions, rapid stop |

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"The engine runs with a <b>7-day warmup period</b> — it processes a full week of candle data before taking its first trade. Indicators are fully stabilized by the time the first entry fires. The losses you see above aren't from cold indicators. They're from <em>real market conditions</em> — violent moves, gap-throughs, and choppy ranges that no amount of warmup can prevent.<br><br>Notice the worst losses are spread across Feb 19 AND Feb 23 — not clustered on day 1. That tells you the engine is operating correctly from bar one."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Also notice: the top 10 wins sum to <b>+$3,349</b>. The top 4 losses sum to <b>-$686</b>. The ratio is 4.88:1. That's the edge. That's the Minovsky Reactor doing its job."</td></tr></table>

---

## System Activity Summary

| System | Events | What It Does |
|--------|--------|-------------|
| **SAR** | 1,835 | Stop-and-Reverse on every stop loss |
| **Counter-Reversal** | 27 | Backup when SAR chain exceeds limit |
| **Guillotine T1** | 826 | Cut 80% at first sign of trouble |
| **Guillotine T2** | 70 | Cut 80% of remainder |
| **Regime Flip Exits** | 2,535 | Exit when HTF trend reverses |
| **Targets Hit** | 39 | Full 3R take-profit |
| **Full Stops** | 84 | Remnant after Guillotine cascade |

<table><tr><td width="170"><img src="img/ghost.png" width="150"></td><td><b>GHOST (The AI)</b>:<br><em>"2,535 Regime Flip exits. That's the most active system. When the higher timeframe trend turns against the position, the engine doesn't wait, doesn't hope, doesn't pray. It exits. Immediately. That discipline alone prevents hundreds of dollars in unnecessary drawdowns."</em></td></tr></table>

---

## 🔥 Indicator Warmup — No Cold Starts

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"A Formula 1 car doesn't start the race with cold tires. That's how you crash on the first corner. Same principle applies here."</td></tr></table>

The Minovsky Engine uses **indicator warmup** to ensure no trade is ever taken with under-cooked data:

| Mode | What Happens | How Much |
|------|-------------|----------|
| **Backtest** | Engine processes candles before the trading start date — indicators compute, but entries are blocked | 7 days (`warmup_days=7`) |
| **Live Bot** | On first startup, the bot fetches extra historical candles from OANDA before the first decision cycle | 2,016 LTF candles (~7 days of 5m data) + 200 HTF candles (~33 days of 4H data) |

<table><tr><td width="170"><img src="img/ninja.png" width="150"></td><td><b>NINJA</b>:<br><em>"The blade is sharpened before the battle begins. Not during it."</em></td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"This means when your bot boots up for the very first time — after you input your API credentials — the ADX, EMA ribbon, supertrend, and MACD voters already have a week of price context. No guessing. No cold indicator signals. The engine trades at full strength from minute one."</td></tr></table>

---

## The Verdict

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"Baby, let me make sure I understand this. You put in $5,500 and two weeks later it was $9,474? That's almost double?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Yes ma'am. +72.3% in 14 days. With a Profit Factor of 2.10, meaning for every $1 lost, $2.10 came back.<br><br>The Minovsky Engine passed the 14-day test. It matches the backtester <b>exactly</b> — same trade count, same PnL, same PF. <br><br>The Phoenix Engine is in the museum. The reactor is online."</td></tr></table>

<table><tr><td width="170"><img src="img/monk.png" width="150"></td><td><b>MONK</b>:<br><em>"The temple was always there. We just had to stop building a second one next to it."</em></td></tr></table>


