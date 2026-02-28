# 🎭 The Forex Conductor Strategy — The Strategy That Refuses to Lose Gracefully

**Status:** 100% Hit Rate (6/6 windows) | +$653 Best Window | 9.3% Worst DD
**Last Updated:** February 2026

---

## 🎬 The Opening Scene

<table><tr><td width="170"><img src="img/chad.png" width="150"></td><td><b>CHAD</b>:<br>"Bro, my strategy just hit 2.5R. Time to take profit! Ring the register! 🔔"</td></tr></table>

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"Take profit? At 2.5R? That's adorable. My dear boy, we don't DO fixed take profits here. We removed those in the Great Decapping of February 2025. The trailing stop hasn't even warmed up yet. We are just getting STARTED."</td></tr></table>

<table><tr><td width="170"><img src="img/chad.png" width="150"></td><td><b>CHAD</b>:<br>"But what if it reverses?!"</td></tr></table>

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"Then the dynamic ATR trail catches it. And if it doesn't? We ride to 5R, 7R, 10R. Your 2.5R 'win' is frankly embarrassing. That's like leaving a restaurant after the appetizer because you were 'satisfied.' No. We're having the full course. Dessert included."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"The Conductor is my magnum opus. It is, without exaggeration, the single most <em>aggressively optimized</em> trading strategy I've ever built. It doesn't just manage trades — it tortures winners into submission and humiliates losers on the way out. Let me show you how."</td></tr></table>

---

## The Philosophy

<table><tr><td width="170"><img src="img/chad.png" width="150"></td><td><b>CHAD</b>:<br>"So what's the strategy in one sentence?"</td></tr></table>

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"We enter trend pullbacks, make our losses <em>microscopic</em>, double down on winners until they beg for mercy, and when we DO lose, we immediately flip and profit from the very move that stopped us out."</td></tr></table>

<table><tr><td width="170"><img src="img/chad.png" width="150"></td><td><b>CHAD</b>:<br>"That sounds illegal."</td></tr></table>

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"It's not illegal. It's just... <em>aggressively optimized.</em>"</td></tr></table>

### The Core Tenets

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Four rules. Non-negotiable. Break one and the whole thing falls apart like a Jenga tower at an earthquake:"</td></tr></table>

1. **Losses must be humiliated.** We don't just cut losers — we close 95% of the position at -0.3R, leaving only 5% to absorb the stop. A full stop hit costs ~$4 instead of ~$45. The loss doesn't just die — it dies embarrassed.

2. **Winners must be tortured into submission.** No fixed TP. Dynamic ATR trail that tightens as profit grows. Pyramids at every 0.5R level. Winners run until the market forcibly rips them from our hands. We don't let go. The market has to TAKE it from us.

3. **Losses must fund reversals.** Every stop triggers a 4.5% risk reversal trade in the opposite direction with a 1R target. If the market moved hard enough to stop us, it's probably still moving — so we ride it the other way. It's an Uno Reverse Card for your portfolio.

4. **The house always wins.** With 4 wins out of 12 trades (33% WR), we're profitable because each win averages $228 and each loss averages $28. That's an 8.2:1 R:R. The win rate is almost irrelevant when the math is this lopsided.

---

## Entry: The EMA Pullback

<table><tr><td width="170"><img src="img/chad.png" width="150"></td><td><b>CHAD</b>:<br>"OK so how do we get IN?"</td></tr></table>

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"Elementary, my dear Chad. We use the <b>Trend Rider</b> — an EMA pullback strategy. But we don't just buy blindly. There are LAYERS. Ten of them. Like a very paranoid layer cake."</td></tr></table>

### The Entry Checklist

```
✅ Market Regime = "trending" (Conductor checks)
✅ HTF Strength ≥ 0.30 (no weak signals)
✅ HTF/LTF Alignment (both timeframes agree on direction)
✅ ADX > 20 (standalone mode only)
✅ HTF Direction = "long" or "short" (with htf_strength ≥ 0.50)
✅ EMA(8) on correct side of EMA(21) (trend confirmed)
✅ RSI between 40-60 (pullback confirmed, not reversal)
✅ Price within 0.3 × ATR of EMA(21) (near the moving average)
✅ Price bouncing off EMA(21) (close > prev_close for longs)
✅ Price above EMA(21) for longs / below for shorts
```

<table><tr><td width="170"><img src="img/chad.png" width="150"></td><td><b>CHAD</b>:<br>"That's like ten filters!"</td></tr></table>

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"Precisely. We don't enter often. But when we do, the odds are so stacked that the trade practically owes us money before it even starts."</td></tr></table>

### The Stop Placement

- **Long:** Stop at swing low of last 10 candles, minimum 1.5 × ATR below entry
- **Short:** Stop at swing high of last 10 candles, minimum 1.5 × ATR above entry

### The Take Profit (or lack thereof)

```python
take_profit = None  # Let Conductor's dynamic trail manage exits
```

<table><tr><td width="170"><img src="img/chad.png" width="150"></td><td><b>CHAD</b>:<br>"No take profit?! You're INSANE!"</td></tr></table>

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"The take profit was removed in the Great Decapping of February 2025. We learned that a 2.5R ceiling was COSTING us money. Our best trades run 4R, 5R, even 7R. Capping them at 2.5R was like telling Usain Bolt to stop at the 60-meter mark.<br><br>'Hey Usain, you're fast enough. That'll do.' No. Let the man RUN."</td></tr></table>

> **🔧 Bot Setting:** `take_profit` on entry decisions → Set to `None`

---

## Loss Mitigation: The 95% Guillotine

<table><tr><td width="170"><img src="img/chad.png" width="150"></td><td><b>CHAD</b>:<br>"OK but... what about losses? That's the part that keeps me up at night."</td></tr></table>

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"Ah, losses. My favorite topic. Most traders treat losses like a family death. We treat them like a mosquito bite. Allow me to demonstrate."</td></tr></table>

### How It Works

When a trade hits **-0.3R**, the Conductor fires a `scale_out` decision that closes **95%** of the position immediately.

```
Entry: $10,000 position
At -0.3R: Close $9,500 (95%)
Remaining: $500 position (5% of original)
If full stop hits: Loss on remaining = ~$4
Total loss: partial close cost + $4 ≈ $8-22
```

<table><tr><td width="170"><img src="img/chad.png" width="150"></td><td><b>CHAD</b>:<br>"So instead of losing $75 on a stop, I lose $8?"</td></tr></table>

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"Now you're getting it. The 95% guillotine turns a $75 loss into an $8 loss. That's a 90% discount on pain.<br><br>But here's the beautiful part — there's a <b>spread guard.</b> We only fire the guillotine if the loss exceeds 2× the spread cost. Otherwise the close itself would cost more than the loss. We're not going to spend $5 to save $3. That's not optimization. That's insanity."</td></tr></table>

> **🔧 Bot Setting:** `SCALE_OUT_FRACTION` in Exit Logic → **0.95** (95% partial close)
> **🔧 Bot Setting:** `de_risk_threshold` → **-0.3R** (fires at -0.3R)

---

## Stop-and-Reverse: The Uno Reverse Card

<table><tr><td width="170"><img src="img/chad.png" width="150"></td><td><b>CHAD</b>:<br>"This is the one that blew my mind. This is the one that made me spit out my coffee."</td></tr></table>

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"When life gives you stop losses, you make lemonade. At gunpoint."</td></tr></table>

### How It Works

When **ANY** stop loss fires:

1. Position closes at stop price (normal behavior)
2. **Immediately** open a new position in the **opposite direction**
3. Entry = the stop price that just hit
4. Stop = same risk distance as the original trade
5. Take Profit = **1R** (quick exit — bounces are short-lived)
6. Risk = **4.5%** of capital (aggressive — we're confident in the reversal momentum)

```
Original Trade: Short GBPUSD @ 1.34840, SL @ 1.34990
STOPPED OUT: -$95

REVERSAL FIRES:
→ Long GBPUSD @ 1.34990 (entry at the old stop)
→ SL @ 1.34840 (same 15-pip distance)
→ TP @ 1.35140 (1R = 15 pips)
→ Risk: 4.5% of $7,500 = $337.50

Result: +$292 WIN ✅
```

<table><tr><td width="170"><img src="img/chad.png" width="150"></td><td><b>CHAD</b>:<br>"So the market stops you out, and you literally flip and ride the same move?!"</td></tr></table>

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"The logic is simple: if price moved with enough force to stop us, it's probably still moving. Why fight it? Join it. Take a quick 1R and walk away smiling."</td></tr></table>

<table><tr><td width="170"><img src="img/chad.png" width="150"></td><td><b>CHAD</b>:<br>"Why only 1R? Why not let it run?"</td></tr></table>

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"We tried that. It was worse. Reversals catch <b>bounces</b>, not trends. Bounces are quick — they surge 1R then fade. By the time the trailing stop activates, the bounce is already dying. The 1R TP grabs the meat and gets out. In and out like a surgical strike."</td></tr></table>

### Cost-Aware TP: The Oanda Tax Dodger

<table><tr><td width="170"><img src="img/chad.png" width="150"></td><td><b>CHAD</b>:<br>"Wait, but the 1R TP doesn't actually net 1R after spreads, does it?"</td></tr></table>

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"Ah, you've been paying attention! On OANDA, every trade eats 1.5 pips of spread. For a 15-pip stop, that's 10% of your risk evaporating into thin air. So we add the spread cost TO the TP target."</td></tr></table>

```
Without cost-aware TP:
  TP = entry + 15 pips = 1.35140
  Gross PnL: +$337
  Spread:    -$27
  Net PnL:   +$310 (only 0.92R)

With cost-aware TP:  
  TP = entry + 15 pips + 1.5 pips = 1.35155
  Gross PnL: +$364
  Spread:    -$27
  Net PnL:   +$337 (true 1.0R) ✅
```

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"The IRS calls it 'tax optimization.' We call it 'not being a chump.' Without this feature, every reversal leaks $25 to the broker. Over 100 reversal trades, that's $2,500 of free money you just handed OANDA as a tip. For what? For the privilege of being their customer? No."</td></tr></table>

> **🔧 Bot Setting:** `STOP_AND_REVERSE_ENABLED` → **True**
> **🔧 Bot Setting:** `REVERSAL_RISK_PER_TRADE` → **0.045** (4.5% of capital)
> **🔧 Bot Setting:** `REVERSAL_TP_R` → **1.0** (1R quick exit)
> **🔧 Bot Setting:** `REVERSAL_COST_AWARE_TP` → **True** (pads TP for spread)

---

## R-Milestone Management: The Infinite Pyramid

<table><tr><td width="170"><img src="img/chad.png" width="150"></td><td><b>CHAD</b>:<br>"OK this part is NUTS. You have INFINITE pyramids?!"</td></tr></table>

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"Up to 50, technically. But in practice you see 3-5 per trade. Here's the system — and pay attention because this is where the real money is made:"</td></tr></table>

### The Milestone Table

| R-Level | Floor Moves To | Pyramid Risk | What Happens |
|---------|:--------------:|:------------:|:-------------|
| **1.0R** | Breakeven (0R) | **30%** | Big first add — hammer the win |
| **1.5R** | 0.5R | 4% | Smaller add, lock 0.5R profit |
| **2.0R** | 1.0R | 4% | Another add, lock 1.0R |
| **2.5R** | 1.5R | 4% | Keep stacking |
| **3.0R** | 2.0R | 4% | And stacking |
| **...** | ... | 4% | Every 0.5R, forever |

<table><tr><td width="170"><img src="img/chad.png" width="150"></td><td><b>CHAD</b>:<br>"Wait, the FIRST pyramid is 30% risk?! That's insane!"</td></tr></table>

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"At 1R, the floor moves to breakeven. The original trade has ZERO risk. So we slam the gas with a 30% add. It sounds aggressive because it IS aggressive. But the risk is zero on the original position. Every subsequent add is 4% — smaller but consistent. Death by a thousand pyramids."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Think of it like this: you found a slot machine that's paying out. Do you keep putting in quarters? YES. YES YOU DO. Except this isn't a slot machine — it's a confirmed trend with structural backing. And the quarters are calculated position sizes with defined risk. Same energy, better math."</td></tr></table>

---

## Momentum Acceleration: The Displacement Detector

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"This one is subtle but powerful. If a single candle moves ≥ 0.3R in our direction, we pyramid immediately — don't wait for the next 0.5R milestone."</td></tr></table>

```python
candle_move = candle.close - candle.open  # (for longs)
if candle_move >= initial_risk * 0.3:
    # BIG candle! Pyramid immediately at 4% risk
    fire_momentum_pyramid()
```

<table><tr><td width="170"><img src="img/chad.png" width="150"></td><td><b>CHAD</b>:<br>"So you detect displacement and just pile on?"</td></tr></table>

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"A 0.3R candle is a sign of institutional flow. The market isn't pullback-bouncing anymore — it's RUNNING. When an elephant starts sprinting, you don't stand in the way. You grab on and hold tight."</td></tr></table>

---

## Pullback Re-Pyramiding: The Bounce Tracker

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"This is the sneakiest feature. It tracks the peak R-level, detects pullbacks, and when price re-breaks the level... resets the pyramid milestone. Fresh pyramid. Same level. Free money."</td></tr></table>

### How It Works

1. Price reaches 2.0R → pyramid fires, milestone `pyr_2.0r` marked as fired
2. Price pulls back to 1.5R (0.5R pullback)
3. Price climbs BACK to 2.0R → milestone `pyr_2.0r` RESET
4. Fresh pyramid fires at 2.0R again!

<table><tr><td width="170"><img src="img/chad.png" width="150"></td><td><b>CHAD</b>:<br>"You're re-pyramiding on the SAME level?!"</td></tr></table>

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"Only if the pullback proves the trend is still alive. If price pulled back 0.5R and came roaring back, that's a CONFIRMED bounce — a stronger trend signal than the original break. We'd be fools not to add. And we are many things, but we are not fools."</td></tr></table>

---

## Dynamic ATR Trailing: The Tightening Noose

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"The pièce de résistance. The crown jewel. As profit grows, the trailing stop TIGHTENS. Like a noose made of mathematics."</td></tr></table>

### The Trail Multipliers

| R-Level | Trail Distance | Logic |
|---------|:--------------:|:------|
| **1.0R - 1.9R** | 1.5 × ATR | Give room — trend is young |
| **2.0R - 2.9R** | 1.0 × ATR | Getting serious — tighten up |
| **3.0R+** | 0.7 × ATR | Lock it DOWN — don't give back profit |

<table><tr><td width="170"><img src="img/chad.png" width="150"></td><td><b>CHAD</b>:<br>"Why tighten as profit grows?"</td></tr></table>

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"At 1R, the trend is unproven — we need room for noise. At 3R+, we're sitting on serious profit. Every pip of pullback threatens real money. The 0.7× ATR trail at 3R+ means: 'You can breathe, market, but if you cough I'm OUT with my money.'<br><br>The ATR trail and R-level floors work TOGETHER: floors provide discrete jumps (0R → 0.5R → 1.0R), the ATR trail provides continuous tightening between floors. The stop is always the HIGHER of the two."</td></tr></table>

<table><tr><td width="170"><img src="img/chad.png" width="150"></td><td><b>CHAD</b>:<br>"So the floor is the minimum and the trail can be even tighter?"</td></tr></table>

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"The floor says 'no matter what, you keep 1.0R.' The ATR trail says 'actually, you keep 2.3R because the trail is tighter right now.' Best of both worlds. Belt AND suspenders. Your pants aren't falling down."</td></tr></table>

---

## Wind Down Truffle: The Friday Fade

<table><tr><td width="170"><img src="img/chad.png" width="150"></td><td><b>CHAD</b>:<br>"Wait, what happens on Friday afternoons? The bot just... sits there?"</td></tr></table>

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"It <em>used</em> to sit there. Friday afternoons are dead air — Session Momentum's window is closed, Mean Reversion needs a BB extreme that rarely comes in thin liquidity. But the market has a tell: <b>it fades.</b><br><br>Enter the <b>Wind Down Truffle</b> — small, reliable, and you find one every Friday. Like a truffle. Except it's money."</td></tr></table>

**Active Window:** Friday 12:00 PM – 4:30 PM ET *(self-gates — won't fire any other time)*

**Entry Criteria:**
```
✅ Friday afternoon (weekday == 4, 12:00-16:30 ET)
✅ Price below VWAP (confirming the fade)
✅ EMA(8) < EMA(21) (short-term momentum declining)
✅ No volume surge (< 2.5× avg — thin liquidity = fade)
```

**Direction:** Short only. Always. No exceptions.

**Stop:** ATR × 1.2 + VWAP distance above entry
**TP:** 2:1 R:R *(trades typically exit at Friday 5PM close)*

### Backtest Results

```
Capital:        $7,500
Risk:           4.5%/trade
Fridays Tested: 3 (7 weeks of Oanda data)
Trades:         4
Win Rate:       100%
Profit:         +$100.86
Avg Per Trade:  ~$25
```

<table><tr><td width="170"><img src="img/chad.png" width="150"></td><td><b>CHAD</b>:<br>"$25 a trade? That's it?"</td></tr></table>

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"It's a <em>truffle</em>, not a gold bar. Small, consistent, zero losses. $50/Friday of free weekend money. And it's running in dead time when the bot would otherwise just be staring at charts doing nothing. That's like finding $50 in your jacket pocket every Friday. You're not gonna complain about that."</td></tr></table>

---

## Friday 5PM Close: The Weekly Shutdown

<table><tr><td width="170"><img src="img/chad.png" width="150"></td><td><b>CHAD</b>:<br>"What happens to open positions at the end of Friday?"</td></tr></table>

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"We close them. ALL of them. At 4:45 PM ET — the last candle before the forex weekly shutdown."</td></tr></table>

### Why 4:45 PM and Not 5 PM?

The forex market closes at 5 PM ET, but brokers stop providing data at 4:45 PM. The last actionable candle is the 4:45 bar.

```python
# In forex_conductor.py check_exit_signal:
if et.weekday() == 4 and (
    et.hour >= 17
    or (et.hour == 16 and et.minute >= 45)
):
    return close_position_decision(
        "Conductor: Friday 5PM Close"
    )
```

<table><tr><td width="170"><img src="img/chad.png" width="150"></td><td><b>CHAD</b>:<br>"What if I'm up 3R on a trade?"</td></tr></table>

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"You take the 3R and enjoy your weekend. Weekend gaps can erase 3R in a single tick. That's like going to bed with a full wallet and waking up broke because someone moved a decimal point in Tokyo while you were sleeping. The Friday close is a safety net, not a suggestion."</td></tr></table>

---

## Bot/UI Setting Mappings

### Complete Feature → Setting Map

| Feature | Config Key | UI Section | Default |
|---------|-----------|---------|:-------:|
| **95% Partial Close** | `SCALE_OUT_FRACTION` | Exit Logic | 0.95 |
| **De-risk at -0.3R** | (Conductor hardcoded) | — | -0.3 |
| **No TP Ceiling** | — | — | None |
| **30% Initial Pyramid** | (Conductor hardcoded) | — | 0.30 |
| **4% Subsequent Pyramids** | (Conductor hardcoded) | — | 0.04 |
| **Max 50 Pyramids** | `MAX_PYRAMID_COUNT` | Pyramiding | 50 |
| **Pyramid Every 0.5R** | (Conductor hardcoded) | — | 0.5 |
| **Momentum Accel 0.3R** | (Conductor hardcoded) | — | 0.3 |
| **Bounce Re-Pyramid** | (Conductor hardcoded) | — | True |
| **Bounce Pullback 0.5R** | (Conductor hardcoded) | — | 0.5 |
| **ATR Trail Tightening** | (Conductor hardcoded) | — | Dynamic |
| **Trail at 1R** | (Conductor hardcoded) | — | 1.5× |
| **Trail at 2R** | (Conductor hardcoded) | — | 1.0× |
| **Trail at 3R** | (Conductor hardcoded) | — | 0.7× |
| **Stop-and-Reverse** | `STOP_AND_REVERSE_ENABLED` | Exit Logic | True |
| **Reversal Risk** | `REVERSAL_RISK_PER_TRADE` | Exit Logic | 0.045 |
| **Reversal TP** | `REVERSAL_TP_R` | Exit Logic | 1.0 |
| **Cost-Aware TP** | `REVERSAL_COST_AWARE_TP` | Exit Logic | True |
| **Entry Risk** | `RISK_PER_TRADE_PCT` | Risk | 0.01 |
| **Entry Cooldown** | (Conductor hardcoded) | — | 8 bars (2h) |
| **Loss Streak Cooldown** | (Conductor hardcoded) | — | 3 losses |
| **Wind Down Truffle** | (self-gated) | — | Fri 12-4:30 PM ET |
| **Friday 5PM Close** | (Conductor hardcoded) | — | Fri 4:45 PM ET |
| **Min Hold** | `MIN_HOLD_HOURS` | Entry | 0.08 (5min) |

### Existing Bot Infrastructure Used

| Feature | Bot Component | File |
|---------|--------------|------|
| Scale Out | `scale_out_decision()` | `decisions.py` |
| Pyramiding | Backtester pyramid path | `backtester.py:1380+` |
| ATR Calculation | `calculate_atr()` | `icc_signals.py` |
| EMA Calculation | `calculate_ema()` | `indicators.py` |
| Floor Management | R-milestone system | `forex_conductor.py` |
| Trend Detection | Regime classifier | `safety_guard.py` |
| HTF/LTF Gates | Profile trend settings | `models.py` |
| Flywheel | Compound sizing | `backtester.py:1607+` |
| Regime Sync | 1.5× performance boost | `backtester.py:1620+` |
| Wind Down Truffle | Friday fade strategy | `wind_down_truffle.py` |
| Friday 5PM Close | Weekly shutdown | `forex_conductor.py` |

---

## The Numbers

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"Let's end with the cold, hard math. Because at the end of the day, opinions are worthless. Numbers are not."</td></tr></table>

### Hell Test Results (Feb 25, 2025)

```
Capital:        $7,500
Windows:        6 rolling 3-day periods
Hit Rate:       100% (6/6 windows profitable)
Best Window:    +$653.28 (12 trades, 33% WR)
Worst DD:       9.3%
Avg Per Window: +$462
```

### Scale Test Profitability

```
  Offset    Trade Sum  Trades     WR   MaxDD
  0d ago   $  +653.28      12    33%    9.3%  ✅
  3d ago   $  +513.33       7    29%    6.8%  ✅
  6d ago   $  +636.61       7    43%    6.8%  ✅
  9d ago   $  +381.12       7    29%    6.9%  ✅
  12d ago  $  +319.05       5    20%    6.9%  ✅
  15d ago  $  +271.63       6    33%    8.5%  ✅
```

<table><tr><td width="170"><img src="img/chad.png" width="150"></td><td><b>CHAD</b>:<br>"Six for six? It's profitable in EVERY SINGLE WINDOW?!"</td></tr></table>

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"Six for six. Even with 20% win rate in the worst window, the math still works because the wins average 10× the losses. That's the beauty of uncapped winners with the guillotine on losers.<br><br>You can be wrong 80% of the time and still walk away profitable. That is not normal. That is not common. That is the Conductor."</td></tr></table>

---

## ⚠️ DO NOT MODIFY

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"I'm going to say this once and I mean every syllable: <b>DO NOT touch these parameters.</b> They were tuned over multiple sessions through iterative backtesting. Every number exists for a reason. If you change one thing, you WILL break the delicate balance. It's like a house of cards except the cards are money."</td></tr></table>

> [!CAUTION]
> **These parameters were tuned through iterative backtesting. DO NOT MODIFY.**
>
> - **Do NOT add a fixed TP.** It was removed intentionally. The ATR trail handles exits.
> - **Do NOT reduce the 95% partial close.** 75% was tested and was $18/loss worse.
> - **Do NOT let reversals ride.** 1R TP was tested vs uncapped. Uncapped was -$132 worse.
> - **Do NOT reduce reversal risk below 4.5%.** 1% (+$64), 2% (+$127), 4.5% (+$292). Each step up improved results.
> - **Do NOT cap pyramids at less than 50.** Pyramids 4-8 are where the real money is.
> - **Do NOT disable cost-aware TP.** Without it, every reversal nets 0.92R instead of 1.0R — that's $25/trade leaked to the broker.

<table><tr><td width="170"><img src="img/chad.png" width="150"></td><td><b>CHAD</b>:<br>"What if I just tweak ONE thi—"</td></tr></table>

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"<b>NO.</b>"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"He said no. Listen to the man. He's wearing a monocle for a reason."</td></tr></table>

---

*fin* 🎭
