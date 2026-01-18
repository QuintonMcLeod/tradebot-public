# Timeframe Configuration Analysis
**Date:** January 9, 2026
**User Request:** "Does the bot use the 4h to determine trends? I don't want it to anymore. I want it to identify trends using the 15m, but look for continuations in the 5m"

---

## Current Configuration

### Active Profile: `intraday` (from settings_profiles.yaml:6-35)

```yaml
intraday:
  candle_timeframe: 5m          # ← Base candles for decisions
  htf_timeframe: 4h             # ← Higher TimeFrame (HTF) for trend identification
  ltf_timeframe: 15m            # ← Lower TimeFrame (LTF) for structure/continuations
```

### How Timeframes Are Currently Used

**From engine.py analysis:**

#### 1. Trend Identification (HTF = 4h)
- **Line 662-663:** `htf_strength = float(snapshot.trend_htf.strength or 0.0)`
- **Line 664:** `htf_candles = snapshot.htf_candles or snapshot.candles`
- **Line 670:** `swing_progress(htf_candles, swing_lookback=2, min_swings=3)`
- **Used for:**
  - HTF trend direction and strength
  - HTF alignment checks
  - Structure invalidation detection (line 504-508)
  - Indication detection (line 916-917)

#### 2. Continuation/Structure Detection (LTF = 15m)
- **Line 663:** `ltf_strength = float(snapshot.trend_ltf.strength or 0.0)`
- **Line 665:** `ltf_candles = snapshot.ltf_candles or snapshot.candles`
- **Line 675:** `swing_progress(ltf_candles, swing_lookback=2, min_swings=3)`
- **Used for:**
  - LTF trend strength
  - Structure levels for stop loss (line 544)
  - Liquidity sweep detection (line 873-874)
  - Correction detection (line 924-925)
  - Continuation trigger detection (line 898-900)

#### 3. Entry Trigger Timing (Base = 5m)
- **Line 7:** `candle_timeframe: 5m`
- **Used for:**
  - Poll interval (every 10 seconds)
  - Decision timing (every 60 seconds)
  - Entry trigger precision

---

## What You Want vs What You Have

| Aspect | Current (WRONG) | Desired (CORRECT) |
|--------|----------------|-------------------|
| **Trend identification** | 4h (HTF) | 15m (HTF) |
| **Continuation detection** | 15m (LTF) | 5m (LTF) |
| **Entry trigger timing** | 5m (base) | 5m (base) ✅ |

---

## The Problem

### Current Setup:
```
4h (HTF) → Identifies trend direction
  ↓
15m (LTF) → Looks for continuations (sweeps, corrections, HL/LH)
  ↓
5m (base) → Entry timing only
```

**Issue:** The 15m is being used for **continuations**, but you want it for **trends**.

### What You Want:
```
15m (HTF) → Identifies trend direction
  ↓
5m (LTF) → Looks for continuations (sweeps, corrections, HL/LH)
  ↓
5m (base) → Entry timing (same as LTF, which is fine)
```

---

## Required Configuration Changes

### File: `config/settings_profiles.yaml`

**Current intraday profile (lines 6-35):**
```yaml
intraday:
  candle_timeframe: 5m
  htf_timeframe: 4h      # ← Change this to 15m
  ltf_timeframe: 15m     # ← Change this to 5m
```

**Should become:**
```yaml
intraday:
  candle_timeframe: 5m
  htf_timeframe: 15m     # ← Trend identification
  ltf_timeframe: 5m      # ← Continuation detection
```

### Impact of This Change

#### Positive Impacts:
1. ✅ **Faster trend detection** - 15m trends develop faster than 4h trends
2. ✅ **Earlier entries** - 5m continuations trigger sooner than 15m continuations
3. ✅ **More trading opportunities** - Catches intraday trends that 4h misses
4. ✅ **Better for crypto 24/7** - 15m more responsive to crypto volatility

#### Trade-offs:
1. ⚠️ **More false signals** - 15m trends less stable than 4h trends
2. ⚠️ **More whipsaw risk** - 5m continuations more prone to fakeouts
3. ⚠️ **Requires tighter risk management** - Stop losses need to be tighter
4. ⚠️ **More trades** - Higher frequency = more commissions/slippage

---

## Other Profiles Affected

### Profiles Currently Using 4h HTF:

1. **intraday** (line 10) - `htf_timeframe: 4h`
2. **crypto_247** (line 48) - `htf_timeframe: 4h`
3. **Profile at line 97** - `htf_timeframe: 4h`
4. **Profile at line 181** - `htf_timeframe: 4h`

**Question:** Should ALL profiles be changed to 15m/5m, or just `intraday`?

### Profiles Currently Using 1h HTF:

1. **swing** (line 40) - `htf_timeframe: 1h`, `ltf_timeframe: 15m`

**Note:** The `swing` profile is already using a lower HTF (1h instead of 4h), which is more conservative than your desired 15m.

---

## ICC Methodology Implications

### ICT (Inner Circle Trader) Timeframe Alignment

Traditional ICT teaches:
- **HTF:** Daily/4h for bias (trend direction)
- **LTF:** 15m/5m/1m for entries (continuations)

Your desired setup:
- **HTF:** 15m for bias (trend direction)
- **LTF:** 5m for entries (continuations)

**Analysis:**
- ✅ **Still maintains multi-timeframe confluence** (HTF trend + LTF structure)
- ✅ **Still requires sweep, indication, correction, continuation** (ICC intact)
- ✅ **Faster timeframes = more aggressive** (not necessarily wrong, just different risk profile)

### Continuation Detection on 5m

**Current Code:** Continuations detected on 15m
- Looks for Higher Low (HL) or Lower High (LH) structure
- Waits for 2-bar confirmation above/below swing
- Checks for sweep before continuation

**With 5m LTF:** Continuations detected on 5m
- ✅ Same logic applies (HL/LH structure, 2-bar confirmation, sweeps)
- ⚠️ **5m swings are smaller** - May trigger more often but with less conviction
- ⚠️ **5m sweep = weaker liquidity grab** - Not as significant as 15m sweep

---

## Recommended Configuration

### Option 1: Your Exact Request (Most Aggressive)
```yaml
intraday:
  candle_timeframe: 5m
  htf_timeframe: 15m     # Trend identification
  ltf_timeframe: 5m      # Continuation detection
```
**Best for:** High-frequency intraday trading, crypto scalping

### Option 2: Slightly More Conservative
```yaml
intraday:
  candle_timeframe: 5m
  htf_timeframe: 30m     # Trend identification (compromise)
  ltf_timeframe: 5m      # Continuation detection
```
**Best for:** Reducing false signals while staying intraday

### Option 3: Keep HTF 15m, Use 1m for Entries (Maximum Precision)
```yaml
intraday:
  candle_timeframe: 1m
  htf_timeframe: 15m     # Trend identification
  ltf_timeframe: 5m      # Continuation detection
```
**Best for:** Ultra-precise entries, scalping crypto volatility

---

## Summary

**Your Question:** "Does the bot use the 4h to determine trends?"
**Answer:** ✅ **YES**, currently uses 4h for trend identification (HTF)

**Your Request:** "I want it to identify trends using the 15m, but look for continuations in the 5m"
**Required Changes:**
```yaml
# In config/settings_profiles.yaml, change:
htf_timeframe: 4h   →  htf_timeframe: 15m
ltf_timeframe: 15m  →  ltf_timeframe: 5m
```

**Impact:**
- ✅ Faster trend identification (15m vs 4h)
- ✅ Earlier continuation entries (5m vs 15m)
- ⚠️ More aggressive trading (higher frequency, more false signals)
- ⚠️ Requires tighter risk management

**Profiles to Update:**
- `intraday` (line 10-11)
- `crypto_247` (line 48-49) - If you want consistency
- Other profiles (lines 97-98, 181-182) - Depending on your needs

---

**Analysis Prepared By:** Claude (AI Assistant)
**Date:** January 9, 2026
**Status:** ✅ **Configuration change identified - NO CODE CHANGES NEEDED**
**Action Required:** Update `htf_timeframe` and `ltf_timeframe` in settings_profiles.yaml
