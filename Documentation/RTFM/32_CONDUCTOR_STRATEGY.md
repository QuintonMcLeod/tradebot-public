# 🎭 The Forex Conductor Strategy — RTFM

> *A.K.A. "The Strategy That Refuses to Lose Gracefully"*

---

**Last Updated:** February 2025  
**Status:** 100% Hit Rate (6/6 windows) | +$653 Best Window | 9.3% Worst DD  
**Authors:** A very tired human and an AI who now understands spreads *and* fees

---

## 🎬 The Opening Scene

**CHAD** *(aggressive trader, sunglasses indoors)*: "Bro, my strategy just hit 2.5R. Time to take profit!"

**CONDUCTOR** *(adjusts monocle)*: "Take profit? At 2.5R? My dear boy, we don't DO fixed take profits here. We removed those back in Act I. The trailing stop hasn't even warmed up yet."

**CHAD**: "But what if it reverses?!"

**CONDUCTOR**: "Then the dynamic ATR trail catches it. And if it doesn't? We ride to 5R, 7R, 10R. Your 2.5R 'win' is frankly embarrassing."

---

## 📖 Table of Contents

1. [The Philosophy](#the-philosophy)
2. [Entry: The EMA Pullback](#entry-the-ema-pullback)
3. [Loss Mitigation: The 95% Guillotine](#loss-mitigation-the-95-guillotine)
4. [Stop-and-Reverse: The Uno Reverse Card](#stop-and-reverse-the-uno-reverse-card)
5. [R-Milestone Management: The Infinite Pyramid](#r-milestone-management-the-infinite-pyramid)
6. [Momentum Acceleration: The Displacement Detector](#momentum-acceleration-the-displacement-detector)
7. [Pullback Re-Pyramiding: The Bounce Tracker](#pullback-re-pyramiding-the-bounce-tracker)
8. [Dynamic ATR Trailing: The Tightening Noose](#dynamic-atr-trailing-the-tightening-noose)
9. [Bot/UI Setting Mappings](#bot-ui-setting-mappings)
10. [The Numbers](#the-numbers)

---

## The Philosophy

**CHAD**: "So what's the strategy in one sentence?"

**CONDUCTOR**: "We enter trend pullbacks, make our losses microscopic, double down on winners until they beg for mercy, and when we DO lose, we immediately flip and profit from the very move that stopped us out."

**CHAD**: "That sounds illegal."

**CONDUCTOR**: "It's not illegal. It's just... *aggressively optimized*."

### The Core Tenets

1. **Losses must be humiliated.** We don't just cut losers — we close 95% of the position at -0.3R, leaving only 5% to absorb the stop. A full stop hit costs ~$4 instead of ~$45.

2. **Winners must be tortured into submission.** No fixed TP. Dynamic ATR trail that tightens as profit grows. Pyramids at every 0.5R level. Winners run until the market forcibly rips them from our hands.

3. **Losses must fund reversals.** Every stop triggers a 4.5% risk reversal trade in the opposite direction with a 1R target. If the market moved hard enough to stop us, it's probably still moving — so we ride it the other way.

4. **The house always wins.** With 4 wins out of 12 trades (33% WR), we're profitable because each win averages $228 and each loss averages $28. That's an 8.2:1 R:R.

---

## Entry: The EMA Pullback

**CHAD**: "OK so how do we get IN?"

**CONDUCTOR**: "Elementary, my dear Chad. We use the **Trend Rider** — an EMA pullback strategy. But we don't just buy blindly. There are LAYERS."

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

**CHAD**: "That's like ten filters!"

**CONDUCTOR**: "Precisely. We don't enter often. But when we do, the odds are stacked."

### The Stop Placement

- **Long:** Stop at swing low of last 10 candles, minimum 1.5 × ATR below entry
- **Short:** Stop at swing high of last 10 candles, minimum 1.5 × ATR above entry

### The Take Profit (or lack thereof)

```python
take_profit = None  # Let Conductor's dynamic trail manage exits
```

**CHAD**: "No take profit?! You're insane!"

**CONDUCTOR**: "The take profit was removed in the Great Decapping of February 2025. We learned that a 2.5R ceiling was COSTING us money. Our best trades run 4R, 5R, even 7R. Capping them at 2.5R was like telling Usain Bolt to stop at the 60m mark."

> **🔧 Bot Setting:** `take_profit` on entry decisions → Set to `None`
> This is the default Trend Rider behavior when routed through the Conductor.

---

## Loss Mitigation: The 95% Guillotine

**CHAD**: "OK but... what about losses?"

**CONDUCTOR**: "Ah, losses. My favorite topic. Allow me to demonstrate."

### How It Works

When a trade hits **-0.3R**, the Conductor fires a `scale_out` decision that closes **95%** of the position immediately.

```
Entry: $10,000 position
At -0.3R: Close $9,500 (95%)
Remaining: $500 position (5% of original)
If full stop hits: Loss on remaining = ~$4
Total loss: partial close cost + $4 ≈ $8-22
```

**CHAD**: "So instead of losing $75 on a stop, I lose $8?"

**CONDUCTOR**: "Now you're getting it. The 95% guillotine turns a $75 loss into an $8 loss. But here's the beautiful part — there's a **spread guard**. We only fire the guillotine if the loss exceeds 2× the spread cost. Otherwise the close itself would cost more than the loss."

> **🔧 Bot Setting:** `SCALE_OUT_FRACTION` in Exit Logic → **0.95** (95% partial close)  
> Now fully configurable via the UI — slider from 0.25 to 1.0.  
> **🔧 Bot Setting:** `de_risk_threshold` → **-0.3R** (fires at -0.3R)  
> **🔧 Bot Setting:** Already exists in Conductor milestones, inherits from Pyramiding config

---

## Stop-and-Reverse: The Uno Reverse Card

**CHAD**: "This is the one that blew my mind."

**CONDUCTOR**: *(smirking)* "When life gives you stop losses, you make lemonade. At gunpoint."

### How It Works

When **ANY** stop loss fires in the backtester:

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

**CHAD**: "So the market stops you out, and you literally flip and ride the same move?"

**CONDUCTOR**: "The logic is simple: if price moved with enough force to stop us, it's probably still moving. Why fight it? Join it. Take a quick 1R and walk away."

**CHAD**: "Why only 1R? Why not let it run?"

**CONDUCTOR**: "We tried that. It was worse. Reversals catch **bounces**, not trends. Bounces are quick — they surge 1R then fade. By the time the trailing stop activates, the bounce is already dying. The 1R TP grabs the meat and gets out."

### Cost-Aware TP: The Oanda Tax Dodger

**CHAD**: "Wait, but the 1R TP doesn't actually net 1R after spreads, does it?"

**CONDUCTOR**: "Ah, you've been paying attention! Correct. On OANDA, every trade eats 1.5 pips of spread. For a 15-pip stop, that's 10% of your risk evaporating into thin air. So we add the spread cost TO the TP target."

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

**CHAD**: "So you're literally padding the TP to eat the spread?"

**CONDUCTOR**: "The IRS calls it *tax optimization*. We call it *not being a chump*."

> **🔧 Bot Setting:** `STOP_AND_REVERSE_ENABLED` in Exit Logic → **True**  
> **🔧 Bot Setting:** `REVERSAL_RISK_PER_TRADE` in Exit Logic → **0.045** (4.5% of capital)  
> **🔧 Bot Setting:** `REVERSAL_TP_R` in Exit Logic → **1.0** (1R quick exit)  
> **🔧 Bot Setting:** `REVERSAL_COST_AWARE_TP` in Exit Logic → **True** (pads TP for spread)  
> ✅ **FULLY PORTED** — Live bot, backtester, and UI all support this. No longer backtester-only.

---

## R-Milestone Management: The Infinite Pyramid

**CHAD**: "OK this part is nuts. You have INFINITE pyramids?!"

**CONDUCTOR**: "Up to 50, technically. But in practice you see 3-5 per trade. Here's the system:"

### The Milestone Table

| R-Level | Floor Moves To | Pyramid Risk | What Happens |
|---------|:--------------:|:------------:|:-------------|
| **1.0R** | Breakeven (0R) | **30%** | Big first add — hammer the win |
| **1.5R** | 0.5R | 4% | Smaller add, lock 0.5R profit |
| **2.0R** | 1.0R | 4% | Another add, lock 1.0R |
| **2.5R** | 1.5R | 4% | Keep stacking |
| **3.0R** | 2.0R | 4% | And stacking |
| **...** | ... | 4% | Every 0.5R, forever |

**CHAD**: "Wait, the FIRST pyramid is 30% risk?!"

**CONDUCTOR**: "Yes. Because at 1R, the floor moves to breakeven. The original trade has ZERO risk. So we slam the gas with a 30% add. Every subsequent add is 4% — smaller but consistent. Death by a thousand pyramids."

> **🔧 Bot Setting:** `pyramid_levels` in Pyramiding config
> The 30% initial add is the `initial_pyramid_risk_pct` setting.
> The 4% subsequent is `subsequent_pyramid_risk_pct`.
> Floor management uses the existing `breakeven_at_r` and `floor_levels` settings.

---

## Momentum Acceleration: The Displacement Detector

**CONDUCTOR**: "This one is subtle but powerful. If a single candle moves ≥ 0.3R in our direction, we pyramid immediately — don't wait for the next 0.5R milestone."

### The Logic

```python
candle_move = candle.close - candle.open  # (for longs)
if candle_move >= initial_risk * 0.3:
    # BIG candle! Pyramid immediately at 4% risk
    fire_momentum_pyramid()
```

**CHAD**: "So you detect displacement and pile on?"

**CONDUCTOR**: "Exactly. A 0.3R candle is a sign of institutional flow. The market isn't pullback-bouncing anymore — it's RUNNING. We want maximum exposure when that happens."

> **🔧 Bot Setting:** `momentum_accel_threshold` → **0.3R** per candle
> Fires only once per position (`momentum_accel` milestone key).
> Maps to the pyramid system — uses `risk_per_trade_pct = 0.04`.

---

## Pullback Re-Pyramiding: The Bounce Tracker

**CONDUCTOR**: "This is the sneakiest feature. It tracks the peak R-level, detects pullbacks, and when price re-breaks the level... resets the pyramid milestone."

### How It Works

1. Price reaches 2.0R → pyramid fires, milestone `pyr_2.0r` marked as fired
2. Price pulls back to 1.5R (0.5R pullback)
3. Price climbs BACK to 2.0R → milestone `pyr_2.0r` RESET
4. Fresh pyramid fires at 2.0R again!

**CHAD**: "You're re-pyramiding on the SAME level?!"

**CONDUCTOR**: "Only if the pullback proves the trend is still alive. If price pulled back 0.5R and came roaring back, that's a CONFIRMED bounce — stronger trend signal than the original. We'd be fools not to add."

> **🔧 Bot Setting:** This uses the existing pyramid infrastructure.
> Add `re_pyramid_on_bounce` flag to Pyramiding config (default True).
> Pullback threshold: `re_pyramid_pullback_r` → **0.5R**.

---

## Dynamic ATR Trailing: The Tightening Noose

**CONDUCTOR**: "The pièce de résistance. As profit grows, the trailing stop TIGHTENS."

### The Trail Multipliers

| R-Level | Trail Distance | Logic |
|---------|:--------------:|:------|
| **1.0R - 1.9R** | 1.5 × ATR | Give room — trend is young |
| **2.0R - 2.9R** | 1.0 × ATR | Getting serious — tighten up |
| **3.0R+** | 0.7 × ATR | Lock it DOWN — don't give back profit |

**CHAD**: "Why tighten as profit grows?"

**CONDUCTOR**: "At 1R, the trend is unproven — we need room for noise. At 3R+, we're sitting on serious profit. Every pip of pullback threatens real money. The 0.7× ATR trail at 3R+ means: 'You can breathe, market, but if you cough I'm OUT with my money.'"

### How It Interacts With Floors

The ATR trail and R-level floors work TOGETHER:
- **Floors** provide discrete jumps (0R → 0.5R → 1.0R → etc.)
- **ATR trail** provides continuous tightening between floors
- The stop is always the HIGHER of the two (floor vs trail)

**CHAD**: "So the floor is the minimum and the trail can be even tighter?"

**CONDUCTOR**: "Precisely. The floor says 'no matter what, you keep 1.0R.' The ATR trail says 'actually, you keep 2.3R because the trail is tighter right now.' Best of both worlds."

> **🔧 Bot Setting:** `atr_trail_multiplier` in Safety & Shields → Dynamic
> Mapped to the existing `breakeven_trail` infrastructure.
> Trail tightening ratios: `atr_trail_at_1r`, `atr_trail_at_2r`, `atr_trail_at_3r`.

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

---

## The Numbers

**CONDUCTOR**: "Let's end with the cold, hard math."

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

**CHAD**: "So it's profitable in every single window?"

**CONDUCTOR**: "Six for six. Even with 20% win rate in the worst window, the math still works because the wins average 10× the losses. That's the beauty of uncapped winners with the guillotine on losers."

---

## ⚠️ DO NOT MODIFY

> [!CAUTION]
> **These parameters were tuned over multiple sessions through iterative backtesting.**
> Every number in this document exists for a reason.
> If you change one thing, you WILL break the delicate balance.
> 
> Specifically:
> - **Do NOT add a fixed TP.** It was removed intentionally. The ATR trail handles exits.
> - **Do NOT reduce the 95% partial close.** 75% was tested and was $18/loss worse.
> - **Do NOT let reversals ride.** 1R TP was tested vs uncapped. Uncapped was -$132 worse.
> - **Do NOT reduce reversal risk below 4.5%.** 1% was tested (+$64/reversal), 2% (+$127), 4.5% (+$292). Each step up improved results.
> - **Do NOT cap pyramids at less than 50.** In trending markets, pyramids 4-8 are where the real money is.
> - **Do NOT disable cost-aware TP.** Without it, every reversal nets 0.92R instead of 1.0R — that's $25/trade leaked to the broker.

**CHAD**: "What if I just tweak ONE thi—"

**CONDUCTOR**: "**NO.**"

---

*fin* 🎭
