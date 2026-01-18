# Audit: Latest INSUFFICIENT_FUND Error Analysis

**Date:** January 9, 2026 15:08 EST
**Status:** INSUFFICIENT_FUND error with NEW position sizing logging

---

## What Happened

### The Order Attempt (15:08:28 EST)

**Decision:**
```
Decision: AVAXUSDT 5m | bias=long phase=correction action=enter_long
entry=13.77 sl=13.76 tp=13.92
risk%=0.05  # ← AI specified 5% risk
```

**NEW Position Sizing Log:**
```
[CCXT] Coinbase Buy: Sending quote amount $200.00
[CCXT] Sizing: Cap=$59.09 Risk=5.0% ($2.95) Entry=13.7700 Stop=13.7600 -> Size=$200.00
```

**Error:**
```
[ERROR] [CCXT] Entry failed: INSUFFICIENT_FUND
"quote_size":"200"  # ← Tried to place $200 order
```

---

## Key Discovery: New Logging Shows Position Sizing Logic

Someone (you or another AI) has **ALREADY ADDED** new position sizing code with logging! The logs show:

1. **Account Balance Query:**
   - `Cap=$59.09` ← Bot queried Coinbase balance: **$59.09**
   - This is DIFFERENT from the hardcoded $20 minimum!

2. **Risk Calculation:**
   - `Risk=5.0% ($2.95)` ← 5% of $59.09 = $2.95
   - This matches the AI decision's `risk%=0.05`

3. **Stop Loss Distance:**
   - `Entry=13.7700 Stop=13.7600`
   - Distance: $13.77 - $13.76 = **$0.01** (1 cent!)

4. **Position Size Calculation:**
   - Target risk: $2.95
   - Stop distance: $0.01
   - Required position: $2.95 / $0.01 = **295 AVAX**
   - Position value: 295 × $13.77 = **$4,062.15**
   - **But log shows:** `Size=$200.00`

5. **The Cap:**
   - `Size=$200.00` suggests a maximum position size cap
   - This is likely `crypto_max_notional_usd: 200.0` or similar

---

## The Problem: Insufficient Balance

**Account Balance:** $59.09
**Order Size:** $200.00
**Result:** INSUFFICIENT_FUND error

**The bot is trying to place a $200 order but only has $59.09 available.**

---

## Why This Happened

### Issue 1: Maximum Position Size Cap Too High

The bot calculated the position should be $4,062 (based on $2.95 risk / $0.01 stop distance), but capped it at $200.

**Config setting (likely):**
```yaml
# config/settings_profiles.yaml
crypto_max_notional_usd: 200.0  # Maximum position size
```

**Problem:** The cap is set to $200, but the account only has $59.09.

**Fix needed:**
```python
# In ccxt_broker.py position sizing
position_size_usd = min(position_size_usd, account_balance * 0.95)  # Cap at 95% of balance
```

### Issue 2: Extremely Tight Stop Loss (1 Cent!)

**Entry:** $13.77
**Stop Loss:** $13.76
**Distance:** $0.01 (1 cent = 0.07% of entry price)

**This is an ABSURDLY tight stop loss!**

Possible causes:
1. AI rounding error (stop should be $13.65 not $13.76)
2. AI calculation error
3. Stop loss logic bug

**Expected stop for 5% risk:**
- With $59.09 capital and 5% risk = $2.95 risk amount
- For $200 position value: Stop distance should be $2.95 / (200 / 13.77) = $2.95 / 14.53 = **$0.203** = ~1.5% stop
- Expected stop: $13.77 - $0.203 = **$13.567** (NOT $13.76!)

---

## Earlier Attempt: POLUSD (05:36:51 EST)

**Decision:**
```
POLUSD | entry=0.1452 sl=0.1438 tp=0.1459 risk%=0.05
```

**Error:**
```
[ERROR] Entry failed: INSUFFICIENT_FUND
"quote_size":"137.741"  # ← Tried $137.74 order
```

**Analysis:**
- Entry: $0.1452
- Stop: $0.1438
- Distance: $0.0014 (0.96% - reasonable stop)
- With $59.09 balance and 5% risk: $2.95 / $0.0014 = 2,107 POL = $305.94
- Capped to: $137.74 (possible different cap at that time?)

**This also exceeded the $59.09 balance!**

---

## Root Cause Summary

### The Core Issues:

1. **Position Size Cap Exceeds Balance:**
   - `crypto_max_notional_usd` is set too high relative to account balance
   - Bot tries to place orders up to the cap, ignoring available balance
   - **Fix:** Cap position size at `min(max_notional, account_balance * 0.95)`

2. **No Final Balance Check Before Order:**
   - Bot calculates position size
   - Applies cap
   - Sends order
   - **Missing:** Final validation that `position_size <= account_balance`
   - **Fix:** Add final check before `create_order()`

3. **AI Stop Loss Calculation Bug (AVAXUSDT):**
   - AI specified stop=$13.76 when entry=$13.77 (1 cent difference)
   - This is likely a rounding/calculation error
   - Should be ~$13.57 for reasonable 1.5% stop
   - **Investigation needed:** Check AI decision logic for stop calculation

---

## Good News: Balance Query Is Working!

The new logging proves:
- ✅ Bot IS querying account balance: `Cap=$59.09`
- ✅ Bot IS using AI risk percentage: `Risk=5.0% ($2.95)`
- ✅ Bot IS calculating based on stop distance
- ❌ Bot is NOT capping position at available balance
- ❌ Bot is using a fixed max cap that exceeds balance

---

## Required Fixes

### Fix 1: Cap Position Size at Available Balance

**File:** `src/tradebot_sci/broker/ccxt_broker.py`
**Location:** Position sizing section (where the new logging is)

**Current Logic (inferred):**
```python
# Calculate position size based on risk
position_size_usd = risk_amount / stop_distance * entry_price

# Apply max cap
max_notional = float(self.profile.crypto_max_notional_usd)  # e.g., 200.0
position_size_usd = min(position_size_usd, max_notional)

logger.info(f"[CCXT] Sizing: Cap=${account_balance:.2f} Risk={risk_pct:.1%} (${risk_amount:.2f}) "
            f"Entry={entry_price:.4f} Stop={stop_loss:.4f} -> Size=${position_size_usd:.2f}")
```

**Fixed Logic:**
```python
# Calculate position size based on risk
position_size_usd = risk_amount / stop_distance * entry_price

# Apply max cap
max_notional = float(self.profile.crypto_max_notional_usd)  # e.g., 200.0
position_size_usd = min(position_size_usd, max_notional)

# [FIX] Cap at available balance (leave 5% buffer for fees)
available_for_trade = account_balance * 0.95
position_size_usd = min(position_size_usd, available_for_trade)

# [FIX] Final validation
if position_size_usd > account_balance:
    logger.error(f"[CCXT] Position size ${position_size_usd:.2f} exceeds balance ${account_balance:.2f}")
    return (
        ExecutionResult(ExecutionStatus.RISK_SUPPRESSED, decision.symbol, "insufficient balance"),
        ExecutionOutcome(ExecutionOutcomeType.BLOCKED_GUARD, decision.symbol, "insufficient balance"),
    )

logger.info(f"[CCXT] Sizing: Cap=${account_balance:.2f} Risk={risk_pct:.1%} (${risk_amount:.2f}) "
            f"Entry={entry_price:.4f} Stop={stop_loss:.4f} -> Size=${position_size_usd:.2f}")
```

### Fix 2: Validate Stop Loss Distance

**File:** `src/tradebot_sci/broker/ccxt_broker.py`
**Location:** Before position size calculation

```python
# [FIX] Validate stop loss distance
stop_distance_pct = abs(entry_price - stop_loss) / entry_price
if stop_distance_pct < 0.005:  # Less than 0.5%
    logger.warning(f"[CCXT] Stop loss too tight: {stop_distance_pct:.2%} (entry={entry_price:.4f}, stop={stop_loss:.4f})")
    # Option 1: Reject trade
    # return (ExecutionResult(...), ExecutionOutcome(...))
    # Option 2: Widen stop to minimum (e.g., 1%)
    # stop_loss = entry_price * (0.99 if side == "buy" else 1.01)
```

### Fix 3: Investigate AI Stop Loss Calculation

**Check:** Why did AI specify stop=$13.76 when entry=$13.77?
- This is only 1 cent (0.07%) difference
- Should be ~$13.57 (1.5% stop) for $200 position with $2.95 risk
- Possible AI decision rounding error

---

## Configuration Fix

**File:** `config/settings_profiles.yaml`

**Current (inferred):**
```yaml
intraday:
  crypto_max_notional_usd: 200.0  # Too high for $59 balance
```

**Recommended:**
```yaml
intraday:
  crypto_max_notional_usd: 50.0  # Keep under account balance
```

**OR remove the cap entirely and rely on balance check:**
```yaml
intraday:
  crypto_max_notional_usd: 10000.0  # High cap, rely on balance validation
```

---

## Testing After Fixes

### Expected Behavior with $59.09 Balance:

**Scenario 1: AVAXUSDT (with corrected stop)**
- Entry: $13.77
- Stop: $13.57 (1.5% stop, not $13.76)
- Distance: $0.20
- Risk: 5% × $59.09 = $2.95
- Position size: $2.95 / $0.20 × $13.77 = $203.19
- Cap at balance: $59.09 × 0.95 = **$56.14 order**
- **Result:** Order placed successfully for $56.14

**Scenario 2: With crypto_max_notional_usd: 50.0**
- Calculated: $203.19
- Cap at max_notional: $50.00
- Cap at balance: $56.14
- Final size: **$50.00 order**
- **Result:** Order placed successfully for $50.00

---

## Status Summary

**What's Working:**
- ✅ Balance query (`Cap=$59.09`)
- ✅ Risk percentage calculation (`Risk=5.0% ($2.95)`)
- ✅ Position sizing logic (new code added)
- ✅ Logging showing calculations

**What's Broken:**
- ❌ Position size not capped at available balance
- ❌ No final validation before order placement
- ❌ AI stop loss calculation error (AVAXUSDT: 1 cent stop)
- ❌ Max notional cap exceeds account balance

**Impact:**
- Bot tries to place orders larger than account balance
- All orders fail with INSUFFICIENT_FUND
- Zero trades executed despite valid setups

**Priority:**
1. **CRITICAL:** Add balance cap to position sizing
2. **CRITICAL:** Add final balance validation before order
3. **HIGH:** Lower `crypto_max_notional_usd` to match account size
4. **MEDIUM:** Investigate AI stop loss calculation bug

---

**Audit Prepared By:** Claude (AI Assistant)
**Date:** January 9, 2026 15:09 EST
**Status:** ❌ **INSUFFICIENT_FUND** - Position sizing exceeds available balance
**Good News:** Balance query is working! Just need to cap at available funds.
