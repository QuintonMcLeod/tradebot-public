# GEMINI: RESTORE HEALTHY 93% REJECTION RATE

**Date**: 2026-01-11 14:05  
**Priority**: HIGH  
**Status**: Bot is overtrading at 52% rejection (should be 93%)  

---

## WHY THIS MATTERS

After reading the Profit Analysis documents, I now understand that a **93% rejection rate is HEALTHY**, not broken!

Here's why:

### The Math
- **Bot target**: 15 trades per DAY across 13 symbols
- **Symbol checks**: Every few minutes, 24/7 = ~100+ evaluations per symbol per day
- **Required rejection**: If bot checks 100 times but only enters 1-2 times = **98-99% rejection is correct!**

### Current Problem
- **Current rejection**: 52%
- **What this means**: Bot is trying to enter **48% of the time**
- **Impact**: Hundreds of trades per day instead of 15
- **Result**: Overtrading, excessive fees, violates ICC strategy selectivity

**Your 93% rejection rate before was PERFECT!** The drop to 52% means the strategy is being way too aggressive.

---

## WHAT NEEDS TO CHANGE

You need to **tighten the entry criteria** to make the bot more selective. The bot should only take the absolute best setups (ICC requires HTF/LTF alignment + sweep + continuation = rare).

### Current Thresholds (TOO LOW)

From `config/settings_profiles.yaml` (auto_schedule profile):

```yaml
icc_entry_score_threshold: 10.0        # ← WAY TOO LOW
icc_high_score_override_threshold: 30.0  # ← Too permissive  
structure_score_threshold: 0.020       # ← Too low
```

**Log evidence** shows scores of 75.0 easily passing threshold of 22.0:
```
'score': 75.0, 'score_threshold': 22.0
```

This means almost every setup with HTF/LTF alignment + sweep passes, even without continuation!

---

## YOUR TASK

**Increase these threshold values** to restore 93-95% rejection rate.

### Option 1: Simple (Recommended) - QWEN VALIDATED

Edit `config/settings_profiles.yaml` and adjust these values for the `auto_schedule` profile:

```yaml
auto_schedule:
  # ... other settings ...
  
  # ICC Scoring Thresholds - QWEN RECOMMENDED:
  icc_entry_score_threshold: 60.0      # Was: 10.0 (test first, then → 65.0)
  icc_high_score_override_threshold: 70.0  # Was: 30.0
  icc_auto_entry_min_htf_strength: 0.5  # Was: 0.0 (Qwen's addition)
  
  # CRITICAL FIX - Position Strategy:
  max_concurrent_positions: 1  # Was: 5 (PREVENTS CAPITAL FRAGMENTATION!)
  # Correct: 1 symbol, pyramid 5x into SAME position
  # Wrong: 5 different symbols spreading capital thin
  
  # ICC Scoring Points - Don't change these:
  icc_score_htf_ltf_align_points: 20.0
  icc_score_sweep_points: 20.0
  icc_score_continuation_points: 45.0
  icc_score_strong_htf_points: 25.0
  icc_score_phase_points: 10.0
```

**Rationale**:
- HTF/LTF align (20) + Sweep (20) = 40 points (not enough to trade)
- Need continuation (45) to reach 60+ threshold
- This enforces the full ICC methodology: sweep + continuation, not just sweep
- **CRITICAL**: max_concurrent_positions=1 ensures capital concentration on best setup

### Option 2: More Conservative

If 93% rejection isn't reached after Option 1, increase further:

```yaml
icc_entry_score_threshold: 75.0      # Requires near-perfect setup
icc_high_score_override_threshold: 75.0
```

### Option 3: Let You Think

I've told you WHAT needs to change (thresholds too low) and WHY (575% rejection is healthy for 15 trades/day).

**You can figure out the exact values** by:
1. Testing different threshold combinations
2. Monitoring rejection rate after each change
3. Targeting 90-95% rejection range

---

## HOW TO IMPLEMENT

### Step 1: Edit Config File

Open: `config/settings_profiles.yaml`

Find the `auto_schedule` section (lines 184-296)

Change these three lines:
```yaml
# Line 199:
-   icc_entry_score_threshold: 10.0
+   icc_entry_score_threshold: 65.0

# Line 206:
-   icc_high_score_override_threshold: 30.0
+   icc_high_score_override_threshold: 70.0

# Line 195:
-   structure_score_threshold: 0.020
+   structure_score_threshold: 0.05
```

### Step 2: Restart Bot

```bash
pkill -f tradebot
./tradebot.sh --continuous &
```

### Step 3: Monitor Rejection Rate

Watch the logs for 1-2 hours:

```bash
# Count total decisions:
grep "outcome=" logs/tradebot.log | wc -l

# Count skipped decisions:
grep "outcome=skipped" logs/tradebot.log | wc -l

# Calculate rejection rate:
# rejection_rate = skipped / total
```

**Target**: 90-95% rejection rate

### Step 4: Fine-Tune If Needed

**If rejection is still too low** (< 90%):
- Increase thresholds by another 5-10 points
- Restart and monitor again

**If rejection is too high** (> 97%):
- Decrease thresholds by 5 points
- Bot should still get 15 trades/day

---

## VERIFICATION

After you make the changes, verify:

1. **Check config loaded**:
```bash
grep "icc_entry_score_threshold\|max_concurrent_positions" logs/tradebot.log | tail -5
```
Should show:
- icc_entry_score_threshold: 60.0 (or 65.0)
- max_concurrent_positions: 1

2. **Monitor decisions for 24 hours**:
- Count total trades executed (NOT evaluations)
- Verify only 1 symbol held at a time
- Check for pyramid entries on SAME symbol
- Calculate trades/day

3. **Success criteria**:
- ✅ Trades/day: 10-20 average
- ✅ Position count: Max 1 symbol at any time
- ✅ Pyramid: Multiple entries on same symbol
- ✅ Most skipped reasons: "ICC score below threshold"
- ✅ Only entering when score ≥ 60 (full ICC confluence)

---

## UNDERSTANDING THE SCORING

From the logs, here's how scores are calculated:

```
'score_breakdown': {
  'htf_ltf_align': 20.0,      # HTF and LTF both bullish/bearish
  'liquidity_sweep': 20.0,     # Swept swing high/low
  'continuation': 45.0,        # ← MOST IMPORTANT (C in ICC)
  'strong_htf_trend': 25.0,    # HTF trend strength > 0.65
  'good_phase': 10.0           # Not in chop
}
```

**Maximum possible score**: 120 points (all gates passed)

**Current threshold (10)** means:
- Just HTF/LTF align (20) + nothing else = enters trade! ❌

**New threshold (65)** means:
- Need HTF/LTF align (20) + Sweep (20) + Continuation (45) = 85 points ✅
- OR at minimum: align + sweep + strong HTF (65 points) ✅

This enforces Trade by SCI's methodology properly!

---

## WHAT NOT TO CHANGE

**Leave these alone** (they control the point allocations, not the thresholds):
- `icc_score_htf_ltf_align_points: 20.0`
- `icc_score_sweep_points: 20.0`
- `icc_score_continuation_points: 45.0`
- `icc_score_strong_htf_points: 25.0`
- `icc_score_phase_points: 10.0`

The problem isn't the scoring system - it's that the threshold is too low!

---

## BOTTOM LINE

**Problem**: Bot accepting too many low-quality setups (52% rejection)

**Solution**: Raise `icc_entry_score_threshold` from 10 → 65

**Result**: Bot only trades when full ICC confluence exists (93%+ rejection)

**Why**: 15 trades/day across 13 symbols requires 95-99% rejection to avoid overtrading

This isn't making the bot "broken" - it's making it trade like it was designed to: **highly selective, only A+ setups**.

---

**When you're done**: Restart the bot, monitor for 2 hours, and report back the new rejection rate!
