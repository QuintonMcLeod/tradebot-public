# 🎭 The Forex Conductor Strategy — The Strategy That Refuses to Lose Gracefully

**Status:** 14-day backtest +$4,569 (+83%) | PF=3.25 | Avg Win $122 | Avg Loss -$15
**Last Updated:** March 2026 (v2.8.92 — Tiered Guillotine + Counter-Reversal)

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

1. **Losses must be humiliated — in two stages.** At **-0.15R** we close 80% of the position. At **-0.3R** we close 80% of what remains. Only 4% of the original position ever reaches the stop. A full stop hit costs ~$2 instead of ~$45. The loss doesn't just die — it dies twice.

2. **Winners must be tortured into submission.** No fixed TP. Dynamic ATR trail that tightens as profit grows. Pyramids at every 0.5R level. Winners run until the market forcibly rips them from our hands. We don't let go. The market has to TAKE it from us.

3. **Losses must fund reversals — and if the reversal fails, the Counter-Reversal brings us back.** Every stop triggers a micro-risk SAR in the opposite direction. If SAR also stops out, CR fires back to the original direction. Three bites at the apple: original trade → SAR → CR. All at calibrated micro-risk.

4. **The house always wins.** With 29% WR, we're profitable because each win averages $122 and each loss averages $15. That's a 8:1 R:R. The win rate is almost irrelevant when the math is this lopsided.

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

## Regime Classification: ADX Thresholds

The Conductor routes entries based on the market regime, which is determined by ADX in `trend_consensus.py`'s `_classify_regime()` function.

### Forex-Tuned Thresholds (March 2026)

| Regime | ADX Condition | Routes To |
|--------|:------------:|:----------|
| **Trending** | ADX > 20 + EMA aligned | Trend Rider |
| **Transitional** | ADX 12-20 | Session Breakout |
| **Ranging** | ADX ≤ 12 | Mean Reversion |
| **Choppy** | No conditions met | BLOCKED |

### Chop Gate (profile settings)

| Setting | Value | Effect |
|---------|:-----:|:-------|
| `adx_gate_threshold` | 12 | ADX < 12 → halve trend strength |
| `trend_chop_threshold` | 8 | ADX < 8 → kill direction entirely |

> [!WARNING]
> **These thresholds were lowered from crypto/stock defaults (30/20/15) specifically for forex.** Forex on 1H rarely pushes ADX above 25. With the old thresholds, 100% of bars classified as "ranging" — the Conductor never saw trending or transitional markets. Verified via 14-day backtest.

> **🔧 File:** `src/tradebot_sci/market/trend_consensus.py` → `_classify_regime()` (lines ~408-450)
> **🔧 Profile:** `adx_gate_threshold=12`, `trend_chop_threshold=8`

---

## Loss Mitigation: The Tiered Guillotine

<table><tr><td width="170"><img src="img/chad.png" width="150"></td><td><b>CHAD</b>:<br>"OK but... what about losses? That's the part that keeps me up at night."</td></tr></table>

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"Losses? We don't have ONE guillotine anymore. We have a <em>cascade</em>. The loss doesn't just die — it gets dismembered in two stages."</td></tr></table>

### How It Works

The Conductor fires **two** scale-outs before the stop is ever reached:

```
Tier 1 at -0.15R: Close 80% of position     → 20% remains
Tier 2 at -0.30R: Close 80% of that 20%     →  4% remains
Stop hit:         Close the 4% remnant       → stop absorbed by 4%
```

**Example with a $10,000 position (risk = $200):**
```
-0.15R hit: Close $8,000 (80%)   → loss ≈ $24
-0.30R hit: Close $1,600 (80%)   → loss ≈ $10
Full stop:  $400 (4%) stopped    → loss ≈  $8

Total loss: ~$42   vs   $200 unprotected   → 79% reduction ✅
```

<table><tr><td width="170"><img src="img/chad.png" width="150"></td><td><b>CHAD</b>:<br>"So instead of losing $200 on a stop, I lose $42?"</td></tr></table>

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"And every cut has a <b>spread guard</b> — we only fire if the loss exceeds 2× the spread cost. We're not spending $5 to save $3."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Both tiers are profile-configurable: `tier1_r_threshold`, `tier1_cut_fraction`, `tier2_r_threshold`, `tier2_cut_fraction`. The fraction is embedded in the scale_out decision as `|scale_frac=0.80|` and parsed by the executor — the global `scale_out_fraction` is NOT used."</td></tr></table>

> **🔧 Profile settings:** `tier1_r_threshold=-0.15`, `tier1_cut_fraction=0.80`, `tier2_r_threshold=-0.30`, `tier2_cut_fraction=0.80`

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

## Counter-Reversal: The Boomerang

<table><tr><td width="170"><img src="img/chad.png" width="150"></td><td><b>CHAD</b>:<br>"What happens if the SAR itself gets stopped out?"</td></tr></table>

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"Then we go BACK to where we started. The market whipsawed us twice? Fine. We have a boomerang."</td></tr></table>

### How It Works

When a SAR trade is stopped out:

1. The engine detects that the last loss was a `reversal` trade
2. **CR fires** back in the **original direction** (same as the first losing trade)
3. Risk = same micro-sizing as SAR (~0.225% of capital)
4. TP = 1R, cost-aware. If CR also fails → full cool-off.

```
Example:
Original: Long GBPUSD  → stopped out  (full Guillotine protection)
SAR:      Short GBPUSD → stopped out  (market reversed AGAIN)
CR:       Long GBPUSD  → market resumes original direction → WIN
```

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"CR is micro-sized — only 0.225% risk. It's a whisper. If the market is whipsawing and truly reverting, it'll win. If it's just chop, the loss is a rounding error."</td></tr></table>

> **🔧 Profile:** `counter_reversal_enabled=True`, `counter_reversal_tp_r=1.0`, `max_consecutive_cr=1`  
> **🔧 Engine:** `_cr_pending` dict in `engine.py` — consumed after SAR check each cycle

---



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

| Feature | Config Key | Default |
|---------|-----------|:-------:|
| **Guillotine T1** | `tier1_r_threshold=-0.15` / `tier1_cut_fraction=0.80` | -0.15R / 80% |
| **Guillotine T2** | `tier2_r_threshold=-0.30` / `tier2_cut_fraction=0.80` | -0.30R / 80% |
| **No TP Ceiling** | — | None |
| **30% Initial Pyramid** | (hardcoded) | 0.30 |
| **4% Subsequent Pyramids** | (hardcoded) | 0.04 |
| **Max 50 Pyramids** | `MAX_PYRAMID_COUNT` | 50 |
| **Pyramid Every 0.5R** | (hardcoded) | 0.5 |
| **Momentum Accel 0.3R** | (hardcoded) | 0.3 |
| **Bounce Re-Pyramid** | (hardcoded) | True |
| **ATR Trail Tightening** | (hardcoded) | Dynamic |
| **Trail at 1R** | (hardcoded) | 1.5× ATR |
| **Trail at 2R** | (hardcoded) | 1.0× ATR |
| **Trail at 3R** | (hardcoded) | 0.7× ATR |
| **Stop-and-Reverse** | `stop_and_reverse_enabled=True` | True |
| **SAR Risk** | `(1-scale_out_fraction) × risk_per_trade_pct` | 0.225% |
| **SAR TP** | `reversal_tp_r=1.0` | 1R |
| **Cost-Aware TP** | `reversal_cost_aware_tp=True` | True |
| **Counter-Reversal** | `counter_reversal_enabled=True` | True |
| **CR Risk** | Same as SAR | 0.225% |
| **CR TP** | `counter_reversal_tp_r=1.0` | 1R |
| **CR Chain Guard** | `max_consecutive_cr=1` | 1 |
| **Entry Risk** | `risk_per_trade_pct` | 4.5% |
| **Min Hold** | `min_hold_hours=0.08` | 5 min |
| **Wind Down Truffle** | (self-gated) | Fri 12-4:30 PM ET |
| **Friday 5PM Close** | (hardcoded) | Fri 4:45 PM ET |

### Existing Bot Infrastructure Used

| Feature | Bot Component | File |
|---------|--------------|------|
| Scale Out | `scale_out_decision()` | `decisions.py` |
| Pyramiding | Backtester pyramid path | `backtester.py:1380+` |
| ATR Calculation | `calculate_atr()` | `icc_signals.py` |
| EMA Calculation | `calculate_ema()` | `indicators.py` |
| Floor Management | R-milestone system | `forex_conductor.py` |
| Trend Detection | Regime classifier | `trend_consensus.py` |
| ADX Thresholds | Forex-tuned (20/12/8) | `trend_consensus.py` |
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
> - **Do NOT collapse tiers back to a single Guillotine.** T1 -0.15R/80% + T2 -0.3R/80% = 4% remnant reaching the stop. The cascade is the point.
> - **Do NOT change `scale_out_fraction` globally for guillotine tiers.** Each tier embeds its own fraction via `|scale_frac=X.XX|` in the decision notes, parsed by the executor. The global setting applies to non-guillotine scale-outs only.
> - **Do NOT add a fixed TP.** It was removed intentionally. The ATR trail handles exits.
> - **Do NOT let SAR or CR ride past 1R.** 1R TP was tested vs uncapped. Uncapped was -$132 worse. Reversals catch bounces, not trends.
> - **Do NOT raise SAR/CR risk above 0.225%.** They are micro-risk by design — the position is already nearly closed by the time they fire.
> - **Do NOT disable cost-aware TP.** Without it, every reversal nets 0.92R instead of 1.0R — $25/trade leaked to the broker.
> - **Do NOT raise ADX thresholds back to 30/20/15.** Those are crypto/stock defaults. Forex on 1H needs 20/12/8 or the Conductor sees 100% ranging.
> - **Do NOT cap pyramids at less than 50.** Pyramids 4-8 are where the real money is.

<table><tr><td width="170"><img src="img/chad.png" width="150"></td><td><b>CHAD</b>:<br>"What if I just tweak ONE thi—"</td></tr></table>

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"<b>NO.</b>"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"He said no. Listen to the man. He's wearing a monocle for a reason."</td></tr></table>

---

*fin* 🎭
