---
title: "27 The Universal Exit Router: 11 Ways to Abandon Ship"
category: rtfm
icon: shield
description: 'Understanding how the bot abandons trades. The Universal Exit Router runs 11 mathematically-proven exit methodologies across three phases — emergency exits fire before your broker even knows what happened.'
---

# 27. The Universal Exit Router

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Anybody can code a bot to enter a trade. Getting IN is easy. Getting OUT without leaving 80% of your money on the table or getting completely flattened by a reversal? That's engineering. This is the exit architecture. Eleven strategies. Three phases. One router. Zero mercy."</td></tr></table>

Entering a trade is managed by your chosen strategy playbook. But exiting a trade? That logic defaults to the **Universal Exit Router** (`exit_logic.py`).

The router doesn't just wait for your stop-loss to get hit like a drunk waiting for a bus. It actively evaluates 11 distinct exit methodologies on every single candle, split across three execution phases. Think of it as a firing squad — if one strategy misses, the next one won't.

---

## The Three Phases of Exit

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"The router operates like a triage ward. Phase 1 is the ER — emergency exits that must fire BEFORE the mechanical stop. Phase 2 is the morgue — the hard stop itself. Phase 3 is physical therapy — trailing stops, ratchets, and time decay."</td></tr></table>

| Phase | When It Runs | Strategies | Priority |
|-------|-------------|------------|----------|
| **Phase 1** | Before everything else | `trend_invalidation`, `structure_failure`, `micro_canary`, `bollinger_invalidation` | 🔴 Emergency |
| **Phase 2** | After Phase 1, before Phase 3 | Broker mechanical SL/TP | ⚫ Hard Stop |
| **Phase 3** | After hard stop evaluation | `fixed_rr`, `chandelier`, `scale_breakeven`, `ratchet_milestone`, `time_decay`, `winner_giveback`, `swing_trailing`, `rsi_exhaustion`, `bollinger_snap`, `adx_death`, `ma_crossover` | 🟡 Standard |

**Why this order matters:** In the old architecture, the hard stop ran first. If a 5m candle gapped violently through your stop, you'd fill at the bar close — sometimes 300% beyond your stop level. By moving emergency exits to Phase 1, the bot can exit on *strategy* (at bar-close price) before the broker's mechanical stop turns a $105 loss into a $388 loss.

---

## Phase 1: The Emergency Room

These four strategies run before ANY broker stop evaluation. They are the bot's "oh no" reflexes.

### 1. Trend Invalidation
If the higher-timeframe trend flips against your position while you're still holding, this fires immediately. No questions. No hope. Just exit.

<table><tr><td width="170"><img src="img/bear.png" width="150"></td><td><b>BEAR</b>:<br>"The trend is dead. Why are you still holding? Hope? Hope isn't a strategy. It's a coping mechanism."</td></tr></table>

### 2. Structure Failure
Detects when price prints a lower high (in a long) or higher low (in a short) that invalidates the pullback structure you entered on. If the market is telling you "that bounce was fake," the router listens.

### 3. Micro-Canary
Uses 1m candles to detect microscopic structural collapse before the 5m candle even closes. A massive 1m bullish spike against your short? Micro-Canary sees it and front-runs the reversal.

<table><tr><td width="170"><img src="img/ninja.png" width="150"></td><td><b>NINJA</b>:<br><em>"The canary dies before the miner smells gas. That is its purpose."</em></td></tr></table>

### 4. Bollinger Invalidation *(The Pinned RSI)* — **NEW: Dual-Timeframe**

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"This one is special. Mean-reversion trades — like our Forex Hybrid Scalper — enter when RSI is extreme. But what if price keeps going against you and RSI just... stays there? Like a fork stuck in a garbage disposal. That's Bollinger Invalidation. It detects when RSI is 'pinned' without bouncing."</td></tr></table>

**How it works:**
- Monitors mean-reversion strategies (`forex_hybrid_scalper`, `rubberband_reaper`)
- After `pin_bars` (default **2 bars** = 10 minutes at 5m), it checks if RSI has stayed pinned in extreme territory
- **5m check first** (primary): RSI ≤ 35 (long) or ≥ 65 (short) for 2 consecutive bars, with no meaningful bounce (>5 points)
- **1m fast fallback** (new): If 5m hasn't pinned yet but 1m RSI is stuck extreme, it fires early using `micro_candles` — same timeframe the strategy enters on

| Parameter | Value | Description |
|-----------|-------|-------------|
| `bollinger_invalidation_bars` | 2 | Bars required before arming (was 3) |
| `rsi_overbought` | 65 | Upper threshold (aligned with entry) |
| `rsi_oversold` | 35 | Lower threshold (aligned with entry) |
| `rsi_period` | 7 | RSI lookback period |

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"The dual-timeframe check is critical. The strategy enters on 1m RSI extreme, but the old invalidation only checked 5m. By the time 5m RSI smoothed into extreme territory, the trade was often already dead. The 1m fallback closes this gap."</td></tr></table>

---

## Phase 2: The Hard Stop

**Removed from the router in April 2026.** Hard stops are now handled **exclusively** by the broker's mechanical evaluator:
- **Paper broker:** Uses candle HIGH/LOW for intra-bar detection, exits at exact stop price
- **OANDA broker:** Server-side SL/TP orders managed via TradeCRCDO

The router no longer compares bar-close price against stop price. This prevents catastrophic gap-through fills.

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"Baby, you mean the bot used to wait for the candle to close before checking the stop? That's like waiting for the fire to finish burning before calling the fire department!"</td></tr></table>

---

## Phase 3: The Standard Arsenal

These strategies run after the hard stop evaluation. They manage profitable trades, trailing stops, and time-based exits.

### Fixed Risk-Reward (`fixed_rr`)
The simplest: hit the target or die trying. If price touches your 3R target, the router exits.

### Chandelier Trailing Stop
Tracks the highest high (long) or lowest low (short) minus 2× ATR. As price moves in your favor, the chandelier rises. If price retraces and crosses the trail, exit.

### Scale Breakeven
Moves stop to breakeven once price hits 1R in profit. You can't lose money on a trade that made 1R.

### Ratchet Milestone
Locks in profit at milestones (1R → move stop to +0.5R, 2R → move to +1R, etc.). Prevents giving back large gains.

### Winner Giveback *(Default: 20%)*
If you're up significantly and give back 20% of your peak profit, the router exits. "Don't let a winner turn into a loser" — encoded in math.

<table><tr><td width="170"><img src="img/bull.png" width="150"></td><td><b>BULL</b>:<br>"I HATE Winner Giveback! It made me exit a trade that went to 4R AFTER I left!"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Bull, that one trade went to 4R. The other nine would have reversed and hit your stop. Winner Giveback exists because you don't get to cherry-pick the one that kept running. You have to optimize for the distribution."</td></tr></table>

### Time Decay
If a trade hasn't reached 1R within `decay_bars` (default 12 bars = 1 hour at 5m), it exits near breakeven. Capital tied up in a stale trade is capital not hunting new setups.

### RSI Exhaustion
Exits when RSI hits climactic extremes (≥85 or ≤15) suggesting the move is overextended.

### Bollinger Snap
Exits when price tags the opposite Bollinger Band — the rubber band has snapped back.

### ADX Death
Exits when trend strength (ADX) collapses below 20, indicating the move has lost momentum.

### MA Crossover
Golden cross / death cross exits for trend-following positions.

---

## Hold Guards: When Exits Get Blocked

The engine has two guards that can suppress non-emergency exits:

### Negative Hold Guard
If a trade is underwater and younger than `negative_hold_seconds` (default 2700s = 45 minutes), non-emergency exits are blocked. This prevents whipsaw exits on normal pullback noise.

**Exception:** Emergency exits (`is_emergency=True`) — including Bollinger Invalidation, Trend Invalidation, Structure Failure, and Micro-Canary — **bypass** this guard.

### Spread Profit Guard
If floating PnL is positive but less than the estimated spread cost, exits are blocked. Prevents closing for a "profit" that is actually just spread.

**Exception:** Emergency exits bypass this too.

<table><tr><td width="170"><img src="img/skeptic.png" width="150"></td><td><b>KAREN</b>:<br>"So the hold guards protect against panic exits, but emergencies can still fire? That's... actually sensible."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Karen approves. Someone mark the calendar."</td></tr></table>

---

## Active Strategies Configuration

Your profile's `universal_exit_strategies` list controls which strategies are active. The default for most profiles:

```yaml
universal_exit_strategies:
  - fixed_rr
  - structure_failure
  - trend_invalidation
  - bollinger_invalidation
  - ratchet_milestone
  - scale_breakeven
  - chandelier
  - time_decay
  - winner_giveback
```

You can add or remove strategies per profile. Bollinger Invalidation is enabled by default for mean-reversion trading.

---

## 📖 Continue Reading

<table><tr><td width="170"><img src="img/skeptic.png" width="150"></td><td><b>KAREN</b>:<br>"I found a typo. Page 27. It's 'their' not 'there.' I'm keeping a list."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Karen's typo list grows. Next: <b>Engine Audit</b>. Find more. I double-dog dare you."</td></tr></table>
