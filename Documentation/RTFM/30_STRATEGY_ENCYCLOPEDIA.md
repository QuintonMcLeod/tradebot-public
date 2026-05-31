---
title: "30 Strategy Encyclopedia: The Complete Arsenal"
category: rtfm
icon: library_books
description: '"You asked for 28 strategies. You got 42. Now you have no excuses." The complete reference guide to every single strategy in the bot, with scoring formulas, entry conditions, risk parameters, and brutal honesty about what each one actually does.'
featured: true
---

# 30. Strategy Encyclopedia — The Complete Arsenal

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"I heard there are like 40+ strategies in here! That's amazing! I'm going to run ALL of them at once and become rich!"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"And that, ladies and gentlemen, is how you blow up an account in 3 business days. Quality over quantity, rookie. But since you asked so nicely, here's every single weapon in the arsenal. Use them wisely, or don't use them at all."</td></tr></table>

---

## Universal Strategies (Multi-Asset)

### **Meta-SCI Tournament** 
**Backend ID:** `meta_sci.py` | **Rating:** 9.8/10 ⭐⭐⭐⭐⭐

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"Finally, a strategy with actual intelligence. Meta-SCI doesn't just trade—it conducts a tournament. Every bar, 28 strategies compete. Only the champion gets to deploy capital."</td></tr></table>

**How It Works:**
- Runs a continuous tournament where all strategies submit scores
- Champion selection based on regime detection + historical win rates
- Dynamic weight adjustment based on 14-day battle hardening
- Session windows enforced per-strategy (London Breakout only trades London, etc.)

**Scoring Formula:** Delegated to sub-strategies (each has own formula)

**Entry Requirements:** Must win tournament + pass regime filter + be in session window

**Risk Parameters:** Inherited from profile settings

**Recent Fixes:** ✅ Session windows preserved for tournament logic (not hardcoded in strategies)

⚠️ **NOTE:** This is your CHAMPION strategy. Run this alone if you must choose one.

---

### **Evolution Strategy**
**Backend ID:** `evolution.py` | **Rating:** 9.5/10 ⭐⭐⭐⭐⭐

<table><tr><td width="170"><img src="img/ninja.png" width="150"></td><td><b>NINJA</b>:<br><em>"The market breathes. HTF inhales, LTF exhales. When they synchronize, violence follows."</em></td></tr></table>

**How It Works:**
- Multi-timeframe trend alignment (HTF + LTF must agree)
- Chandelier exit for aggressive profit protection
- Explicit neutral handling (no trades if HTF direction == "neutral")

**Scoring Formula:**
- HTF Strength (40 pts): Scaled 0-40 based on trend conviction
- LTF/HTF Alignment (30 pts): Full points only if both agree
- EMA Structure (20 pts): Price above/below EMA stack
- Volatility Adjustment (10 pts): Favors expanding volatility

**Entry Requirements:** Score ≥ 65 + HTF strength ≥ 0.2 + HTF/LTF agreement

**Risk Parameters:** Chandelier trail = 3 × ATR

**Recent Fixes:** ✅ Added explicit neutral HTF handling (was missing before)

---

### **Trend Rider**
**Backend ID:** `trend_rider.py` | **Rating:** 9.0/10 ⭐⭐⭐⭐

<table><tr><td width="170"><img src="img/bull.png" width="150"></td><td><b>BULL</b>:<br>"THE TREND IS YOUR FRIEND! BUY THE DIP! SELL THE RIP! IT'S THAT SIMPLE!"</td></tr></table>

**How It Works:**
- Pure EMA pullback strategy (8/21/50 EMA stack)
- Enters only when price pulls back to EMA(21) in strong trend
- No mean-reversion, no counter-trend nonsense

**Scoring Formula:**
- EMA Alignment (40 pts): All EMAs stacked correctly
- Pullback Depth (30 pts): Price within 0.3 × ATR of EMA(21)
- RSI Confirmation (20 pts): RSI between 40-60 (not oversold/overbought)
- Momentum (10 pts): Recent candle direction matches trend

**Entry Requirements:** Score ≥ 60 + HTF trend strength ≥ 0.3

**Risk Parameters:** Stop at swing low/high, min 1.5 × ATR

**Recent Fixes:** ✅ Clean pullback logic, no time filters

---

### **Rubberband Reaper**
**Backend ID:** `rubberband_reaper.py` | **Rating:** 9.0/10 ⭐⭐⭐⭐ (was 4.5/10)

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"This used to be garbage. I fixed it. Now it's a precision mean-reversion scalpel. The rubber band snaps, we collect. Simple."</td></tr></table>

**How It Works:**
- Pure mean-reversion on extreme Bollinger Band pierces
- Requires BOTH BB pierce AND RSI extreme (no partial credit)
- Ultra-tight stops above/below wick extremes

**Scoring Formula:**
- BB Position (30 pts): Full points ONLY for true pierce (close outside band)
- RSI Extremity (30 pts): Full points ONLY for RSI < 20 or > 80
- BB Width (20 pts): Favors expanded bands (volatility present)
- Structure (20 pts): HTF/LTF divergence alignment

**Entry Requirements:** Score ≥ 65 + BB pierce confirmed + RSI extreme confirmed

**Risk Parameters:** Stop = wick extreme ± buffer, TP = middle band or opposite band

**Recent Fixes:** ✅ Removed 35 free scoring points, ✅ Fixed score/entry alignment, ✅ Removed "near" partial credit

⚠️ **WARNING:** This is MEAN-REVERSION ONLY. Do not run in trending markets without Meta-SCI filtering.

---

### **Forex Conductor**
**Backend ID:** `forex_conductor.py` | **Rating:** 9.0/10 ⭐⭐⭐⭐ (was 5.5/10)

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"Take profit? At 2.5R? My dear boy, we don't DO fixed take profits here."</td></tr></table>

**How It Works:**
- Regime-based router (trending → London Sweep, ranging → Mean Reversion)
- Aggressive pyramiding on winners (up to 50x entries)
- Stop-and-reverse on losses (Uno Reverse Card)
- Counter-reversal if SAR fails (Boomerang)

**Scoring Formula:** Delegated to sub-strategies

**Entry Requirements:** Correct regime + sub-strategy score threshold

**Risk Parameters:** 
- Original trades: Full structural stops
- SAR trades: 4.5% risk, 1R TP (cost-aware)
- CR trades: 0.225% risk, 1R TP

**Recent Fixes:** ✅ Fixed regime mapping (trending now uses trend-following, not mean-reversion), ✅ Removed module-level globals

⚠️ **WARNING:** This strategy is VICIOUS. It will stop you out, reverse, stop you out again, then reverse back. Your heart rate will increase.

---

### **Forex Hybrid Scalper**
**Backend ID:** `forex_hybrid_scalper.py` | **Rating:** 8.0/10 ⭐⭐⭐⭐ (was 3.0/10)

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"I fused HyperScalper trend logic with Rubberband kinetic triggers. It's a structural Frankenstein, but it WORKS now."</td></tr></table>

**How It Works:**
- Trend anchor: 200 EMA confirms direction
- Kinetic trap: BB pierce + RSI extreme for entry
- Multi-timeframe validation required

**Scoring Formula:**
- RSI Divergence (40 pts): Extreme readings only
- BB Setup (25 pts): Confirmed pierce, not "near"
- HTF Alignment (20 pts): 200 EMA direction match
- Session Quality (15 pts): London/NY overlap preferred

**Entry Requirements:** Score ≥ 65 + EMA direction + BB pierce + RSI extreme

**Risk Parameters:** ATR-based stops, position sizing from pivot distance

**Recent Fixes:** ✅ Complete rewrite (was allowing trades without BB/RSI conditions), ✅ Added HTF validation, ✅ Fixed timezone filtering

⚠️ **NOTE:** Session timing handled by Global Scheduler, not strategy.

---

## Session-Specific Strategies

### **London Breakout**
**Backend ID:** `london_breakout.py` | **Rating:** 8.5/10 ⭐⭐⭐⭐

<table><tr><td width="170"><img src="img/ninja.png" width="150"></td><td><b>NINJA</b>:<br><em>"The amateurs build their little box during Asia. London opens, smashes through, and we ride the momentum."</em></td></tr></table>

**How It Works:**
- Identifies Asian session range (high/low)
- Trades breakout at London open with momentum confirmation
- Box quality scoring (tighter = better breakout potential)

**Scoring Formula:**
- Box Quality (30 pts): Tighter Asian range = higher score
- Edge Proximity (25 pts): Price near box edge before breakout
- Breakout Setup (30 pts): Candle closes outside box with volume
- Momentum (15 pts): Follow-through candles confirm direction

**Entry Requirements:** Score ≥ 60 + London session (via scheduler)

**Risk Parameters:** Stop at opposite side of box, TP = 1.5-2 × box height

**Recent Fixes:** ✅ Removed time filters (now scheduler-managed), ✅ Removed free scoring points

---

### **London Sweep**
**Backend ID:** `london_sweep.py` | **Rating:** 8.5/10 ⭐⭐⭐⭐

<table><tr><td width="170"><img src="img/ninja.png" width="150"></td><td><b>NINJA</b>:<br><em>"Wait for the amateurs to get trapped. The trick isn't just buying oversold RSI... it's buying oversold RSI when the liquidity sweep completes."</em></td></tr></table>

**How It Works:**
- Identifies Asian session high/low
- Waits for price to SWEEP (wick beyond) these levels
- Enters reversal when price closes back inside range

**Scoring Formula:** N/A (binary signal: sweep detected or not)

**Entry Requirements:** 
- Long: Sweeps Asian low, closes back above
- Short: Sweeps Asian high, closes back below

**Risk Parameters:** Ultra-tight stop above/below sweep wick

**Recent Fixes:** ✅ Clarified session timing comment (scheduler handles when, strategy detects sweeps)

---

### **New York Drive**
**Backend ID:** `new_york_drive.py` | **Rating:** 8.5/10 ⭐⭐⭐⭐

<table><tr><td width="170"><img src="img/bull.png" width="150"></td><td><b>BULL</b>:<br>"NY SESSION! MOMENTUM! BREAKOUTS! LET'S GOOOO!"</td></tr></table>

**How It Works:**
- Identifies London session range
- Trades violent breach of London extremes during NY open
- Momentum continuation play

**Scoring Formula:** N/A (binary signal: London range breached)

**Entry Requirements:**
- Long: NY candle closes above London high
- Short: NY candle closes below London low

**Risk Parameters:** 1.5 × ATR stop (wider to let momentum breathe)

**Recent Fixes:** ✅ Clarified session timing comment (scheduler handles when, strategy detects breakouts)

---

## Crypto-Specific Strategies

### **Crypto RSI+MACD**
**Backend ID:** `crypto_rsi_macd.py` | **Rating:** 8.0/10 ⭐⭐⭐⭐

<table><tr><td width="170"><img src="img/pirate.png" width="150"></td><td><b>PIRATE</b>:<br>"RSI says we're oversold! MACD says momentum's shifting! That's enough for me! 🏴‍☠️"</td></tr></table>

**How It Works:**
- RSI detects oversold/overbought extremes
- MACD crossover confirms momentum shift
- Pyramiding enabled for strong trends

**Scoring Formula:**
- RSI Extremity (50 pts): < 25 for longs, > 75 for shorts
- MACD Crossover (40 pts): Bullish/bearish cross confirmed
- Trend Alignment (20 pts): Higher timeframe agreement

**Entry Requirements:** Score ≥ 60 + RSI extreme + MACD cross

**Risk Parameters:** ATR-based stops, pyramid every 6 bars

**Recent Fixes:** ✅ Added structured scoring (was ad-hoc), ✅ Fixed score/entry alignment

---

### **Crypto VWAP Reversion**
**Backend ID:** `crypto_vwap_reversion.py` | **Rating:** 8.0/10 ⭐⭐⭐⭐

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"Price deviates from VWAP like a drunk leaving a bar. Eventually, gravity wins. We short the drunk."</td></tr></table>

**How It Works:**
- Measures deviation from VWAP
- Enters when deviation exceeds threshold
- Bets on reversion to mean (VWAP)

**Scoring Formula:**
- VWAP Deviation (40 pts): Larger deviation = higher score
- EMA Trend (30 pts): Confirms overall direction
- RSI Confirmation (30 pts): Extreme reading supports reversal

**Entry Requirements:** Score ≥ 60 + deviation > threshold + trend confirmation

**Risk Parameters:** Stop beyond recent swing, TP at VWAP

**Recent Fixes:** ✅ Added proper scoring components, ✅ Fixed score/entry alignment

---

### **Crypto Double MACD**
**Backend ID:** `crypto_double_macd.py` | **Rating:** 8.0/10 ⭐⭐⭐⭐

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"One MACD is good. Two MACDs (fast + slow) are better. It's not rocket science, it's just more confirmation."</td></tr></table>

**How It Works:**
- Fast MACD (8/21/5) for quick signals
- Slow MACD (12/26/9) for trend confirmation
- Both must align for entry

**Scoring Formula:**
- MACD Trend (40 pts): Slow MACD direction
- Fast Crossover (30 pts): Fast MACD signal cross
- RSI Pullback (30 pts): RSI confirms entry timing

**Entry Requirements:** Score ≥ 60 + both MACDs aligned

**Risk Parameters:** ATR-based stops

**Recent Fixes:** ✅ Removed free scoring points, ✅ Added proper scoring structure

---

### **Crypto Grid**
**Backend ID:** `crypto_grid.py` | **Rating:** 7.5/10 ⭐⭐⭐

<table><tr><td width="170"><img src="img/robot.png" width="150"></td><td><b>ROBOT</b>:<br>"BEEP BOOP. GRID STRATEGY ENGAGED. BUY LOW. SELL HIGH. REPEAT INFINITE TIMES."</td></tr></table>

**How It Works:**
- Places buy/sell orders at fixed intervals
- Profits from range-bound crypto markets
- Virtual grid (no actual limit orders)

**Scoring Formula:** Range-bound detection + grid level proximity

**Entry Requirements:** Market in defined range + price at grid level

**Risk Parameters:** Grid spacing based on ATR

---

## ICT-Inspired Strategies

### **ICC Core**
**Backend ID:** `icc_core.py` | **Rating:** 8.5/10 ⭐⭐⭐⭐

<table><tr><td width="170"><img src="img/ninja.png" width="150"></td><td><b>NINJA</b>:<br><em>"Institutional order flow leaves footprints. We follow the footprints. Simple."</em></td></tr></table>

**How It Works:**
- Fair Value Gaps (FVGs) detection
- Order block identification
- Liquidity sweep confirmation

**Scoring Formula:** FVG quality + order block strength + sweep confirmation

**Entry Requirements:** All three ICT elements align

**Risk Parameters:** Stop beyond order block, TP at next liquidity pool

---

### **Golden Pocket**
**Backend ID:** `golden_pocket.py` | **Rating:** 8.0/10 ⭐⭐⭐⭐

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"Fibonacci retracements work because millions of traders believe they work. Self-fulfilling prophecy, but profitable."</td></tr></table>

**How It Works:**
- Identifies major swings
- Waits for 0.618-0.786 Fibonacci retracement ("Golden Pocket")
- Enters with tight stop

**Scoring Formula:** Swing quality + Fib level precision + confirmation candle

**Entry Requirements:** Price in Golden Pocket + bullish/bearish confirmation

**Risk Parameters:** Stop beyond 0.786 Fib, TP at swing high/low

---

## Mean Reversion Strategies

### **Mean Reversion**
**Backend ID:** `mean_reversion.py` | **Rating:** 8.5/10 ⭐⭐⭐⭐

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"What goes up must come down, baby. What goes down must come up. That's just physics."</td></tr></table>

**How It Works:**
- Bollinger Bands for extreme detection
- RSI for overbought/oversold confirmation
- Bets on return to mean (middle band)

**Scoring Formula:** BB position + RSI extremity + band width

**Entry Requirements:** BB pierce + RSI < 20 or > 80

**Risk Parameters:** Stop beyond wick, TP at middle band

---

### **Silver VWAP**
**Backend ID:** `silver_vwap.py` | **Rating:** 8.0/10 ⭐⭐⭐⭐

Similar to Crypto VWAP but optimized for silver's unique volatility patterns.

---

### **Supply Demand**
**Backend ID:** `supply_demand.py` | **Rating:** 8.0/10 ⭐⭐⭐⭐

<table><tr><td width="170"><img src="img/ninja.png" width="150"></td><td><b>NINJA</b>:<br><em>"Imbalance creates opportunity. Massive buying leaves unfilled orders. We wait for price to return and fill them."</em></td></tr></table>

**How It Works:**
- Identifies supply/demand zones
- Waits for price to revisit zone
- Enters with zone as support/resistance

---

## Breakout Strategies

### **ORB Breakout**
**Backend ID:** `orb_breakout.py` | **Rating:** 8.0/10 ⭐⭐⭐⭐

**How It Works:**
- Opening Range Breakout (first 30 min of session)
- Trades break of OR high/low
- Momentum continuation

---

### **Hyper Scalper**
**Backend ID:** `hyper_scalper.py` | **Rating:** 7.5/10 ⭐⭐⭐

**How It Works:**
- Ultra-fast scalping on 1-minute charts
- EMA200 trend filter
- Quick in/out with small profits

---

## Quantitative Strategies (See Doc 45 for details)

- **QS SMA Filter** (`qs_sma_filter.py`) - Market weather thermometer
- **QS Golden Cross** (`qs_golden_cross.py`) - Big picture momentum
- **QS RSI Mean Reversion** (`qs_rsi_mean_reversion.py`) - Panic buying engine
- **QS 3/10 Trend** (`qs_3_10_trend.py`) - Smooth monthly trend rider
- **QS TQQQ/BTAL** (`qs_tqqq_btal.py`) - Monthly portfolio guard
- **QS Choppiness** (`qs_choppiness.py`) - Sideways market detector
- **QS First Day Month** (`qs_first_day_month.py`) - Payday anomaly

---

## Specialty Strategies

### **Quantum**
**Backend ID:** `quantum.py` | **Rating:** 7.5/10 ⭐⭐⭐

**How It Works:**
- Multi-factor model combining momentum, value, volatility
- Quantum-inspired optimization (named for marketing, not actual quantum computing)

---

### **Robocop**
**Backend ID:** `robocop.py` | **Rating:** 7.5/10 ⭐⭐⭐

**How It Works:**
- Enforcement strategy (blocks trades violating rules)
- Risk management overlay

---

### **Wind Down Truffle**
**Backend ID:** `wind_down_truffle.py` | **Rating:** 7.0/10 ⭐⭐⭐

**How It Works:**
- Closes positions Friday 5PM ET
- Weekend risk avoidance

**Recent Note:** Time-based exit logic may be moved to Global Scheduler for consistency.

---

### **Yoyo**
**Backend ID:** `yoyo.py` | **Rating:** 7.0/10 ⭐⭐⭐

**How It Works:**
- Oscillating market specialist
- Captures rapid reversals

---

### **Bearish Engulfing**
**Backend ID:** `bearish_engulfing.py` | **Rating:** 7.5/10 ⭐⭐⭐

**How It Works:**
- Candlestick pattern recognition
- Bearish engulfing = short signal
- Bullish engulfing = long signal

---

### **Breakout**
**Backend ID:** `breakout.py` | **Rating:** 7.5/10 ⭐⭐⭐

**How It Works:**
- Generic breakout detection
- Support/resistance breach

---

### **Aggregator**
**Backend ID:** `aggregator.py` | **Rating:** 8.0/10 ⭐⭐⭐⭐

**How It Works:**
- Combines signals from multiple strategies
- Weighted voting system

---

### **ICC Core Standalone**
**Backend ID:** `icc_core_standalone.py` | **Rating:** 8.5/10 ⭐⭐⭐⭐

Same as ICC Core but operates independently (not in Meta-SCI tournament).

---

## Strategy Selection Guide

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Stop trying to run all 42 strategies. Pick based on your market and personality:"</td></tr></table>

| Market Condition | Recommended Strategies |
|-----------------|----------------------|
| **Strong Trends** | Evolution, Trend Rider, Forex Conductor (trending regime) |
| **Ranging/Choppy** | Rubberband Reaper, Mean Reversion, London Sweep |
| **High Volatility** | New York Drive, London Breakout, ORB Breakout |
| **Crypto 24/7** | Crypto RSI+MACD, Crypto VWAP, Double MACD |
| **Conservative** | Meta-SCI (lets tournament decide), QS strategies |
| **Aggressive** | Forex Conductor (full vicious mode), Hyper Scalper |

---

## Final Words of Wisdom

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Three rules:<br><br>1. **Quality > Quantity** - Run 3 good strategies, not 28 mediocre ones<br>2. **Trust the Tournament** - Meta-SCI exists to pick winners for you<br>3. **Session Timing** - Configure the Global Scheduler, don't hardcode times in strategies<br><br>Follow these, and maybe—just maybe—you'll survive long enough to make money."</td></tr></table>

---

**Last Updated:** March 2026 (Post-Refactoring Edition)

**Total Strategies Documented:** 42

**Strategies Rated 8.0+:** 24

**Strategies to Avoid:** None (all refactored to minimum 7.0/10)

---

## 📖 Continue Reading

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"Wow, okay I think I get it now. What's next?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Turn the page. We are going to talk about <b>Quantitative Strategies</b>. Try to keep up."</td></tr></table>
