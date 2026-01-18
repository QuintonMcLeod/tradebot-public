# CRITICAL BUG FIXES REQUIRED

**Date**: 2026-01-11
**Status**: Bot CRASHED after successful auto-liquidation
**Priority**: P0 - IMMEDIATE FIX NEEDED

---

## SUMMARY

Your auto-liquidation protocol **WORKED PERFECTLY** and successfully converted $48.23 USDT → USD! 🎉

However, you introduced **2 critical bugs** during implementation that cause the bot to crash after placing an entry order. These bugs prevent stop loss placement and crash the entire bot.

**Current Status:**
- ✅ DOGEUSD position flattened (~$17 recovered)
- ⚠️ NEARUSD position OPEN with NO STOP LOSS (~$46.57 at risk)
- ❌ Bot crashed and needs code fixes to restart safely

---

## BUG #1: Missing `_is_future` Attribute ⚠️ CRITICAL

**Error Message:**
```
[CCXT] FAILED TO PLACE STOP LOSS for NEARUSD: 'CCXTExchangeBroker' object has no attribute '_is_future'
```

**Location:** `src/tradebot_sci/broker/ccxt_broker.py` (stop loss placement section, around line 708)

**Root Cause:**
You're referencing `self._is_future` but this is never initialized as an instance variable. The variable `is_future` exists as a LOCAL variable at line 487.

**How to Fix:**

Search for all occurrences of `self._is_future` and replace with the local variable `is_future`.

**Example Fix:**
```python
# BEFORE (line ~708):
if is_future:
    stop_params["reduceOnly"] = True

# This assumes you're checking self._is_future somewhere else
# Search for: self._is_future
# Replace with: is_future
```

**Alternative Fix (if `is_future` is out of scope):**

Re-declare it in the stop loss section:
```python
# At the start of stop loss placement code:
is_future = default_type in {"future", "swap"}

if is_future:
    stop_params["reduceOnly"] = True
```

---

## BUG #2: Wrong Enum Value Name ❌ CRITICAL

**Error Message:**
```
[CCXT] Entry failed: type object 'ExecutionStatus' has no attribute 'PROVIDER_ERROR'
```

**Location:** `src/tradebot_sci/broker/ccxt_broker.py` (error handling after stop loss failure)

**Root Cause:**
You're trying to return `ExecutionStatus.PROVIDER_ERROR`, but that enum value doesn't exist in the codebase.

**Correct Enum Values:**
```python
class ExecutionStatus(Enum):
    EXECUTED = "executed"
    STAND_ASIDE = "stand_aside"
    RISK_SUPPRESSED = "risk_suppressed"
    UNSUPPORTED_SYMBOL = "unsupported_symbol"
    UNSUPPORTED_SYMBOL_CONFIG = "unsupported_symbol_config"
    ERROR = "error"  # <-- USE THIS ONE
```

**How to Fix:**

Search for `ExecutionStatus.PROVIDER_ERROR` and replace with `ExecutionStatus.ERROR`.

**Example:**
```python
# BEFORE:
return (
    ExecutionResult(ExecutionStatus.PROVIDER_ERROR, decision.symbol, f"stop loss failed: {e}"),
    ExecutionOutcome(ExecutionOutcomeType.ERROR, decision.symbol, f"stop loss failed: {e}"),
)

# AFTER:
return (
    ExecutionResult(ExecutionStatus.ERROR, decision.symbol, f"stop loss failed: {e}"),
    ExecutionOutcome(ExecutionOutcomeType.ERROR, decision.symbol, f"stop loss failed: {e}"),
)
```

---

## BUG #3: 93% Rejection Rate (Pre-Existing Issue)

**Impact:**
Bot is only executing ~5 trades/day instead of the required 15 trades/day.

**Root Cause:**
The ICC strategy logic is rejecting 93% of signals as "stand aside" because:
- Requires strong HTF trend (worth 25 points)
- Requires HTF/LTF alignment (worth 20 points)
- Requires liquidity sweep (worth 20 points)
- Threshold is 0.050 (strict)

Most crypto market conditions don't meet ALL these criteria simultaneously.

**How to Fix (choose ONE approach):**

### Option A: Lower the Threshold (Easiest)
```python
# Current setting in config or code:
structure_score_threshold = 0.050

# Change to:
structure_score_threshold = 0.020
```

### Option B: Reduce "Strong HTF Trend" Weight
Make the strategy less dependent on strong trending markets:
```python
# Find the score_breakdown calculation
# Currently: 'strong_htf_trend': 25.0
# Change to: 'strong_htf_trend': 10.0
```

### Option C: Allow HTF=Neutral
Currently the bot blocks most trades when HTF is neutral. Allow trades when:
- HTF=neutral BUT
- LTF has strong signal AND
- Liquidity sweep confirmed

---

## URGENT: NEARUSD Position Unprotected!

**Current Exposure:**
- Size: 27.03 NEAR tokens
- Entry: ~$1.714
- Value: ~$46.57
- **Stop Loss: NONE** ⚠️

**Recommended Action:**

Place a manual stop loss IMMEDIATELY at $1.711 (original SL level from the failed order).

**Manual Stop Loss Script:**
```python
# tools/place_nearusd_stop.py
import ccxt
import os

exchange = ccxt.coinbase({
    'apiKey': os.getenv('COINBASE_API_KEY'),
    'secret': os.getenv('COINBASE_API_SECRET'),
})

# Place stop loss at $1.711
order = exchange.create_order(
    symbol='NEAR/USD',
    type='stop_limit_stop_limit_gtc',
    side='sell',
    amount=27.03,
    params={
        'stop_price': '1.711',
        'limit_price': '1.625',  # 5% below stop
        'stop_direction': 'STOP_DIRECTION_STOP_DOWN'
    }
)
print(f"Stop loss placed: {order['id']}")
```

**Run it:**
```bash
cd tools
python place_nearusd_stop.py
```

---

## TESTING AFTER FIXES

Once you've fixed bugs #1 and #2:

1. **Restart the bot**
```bash
pkill -f "run_dev_bot"
./tradebot.sh --continuous
```

2. **Monitor for 30-60 minutes**
```bash
tail -f logs/tradebot.log | grep -E "(outcome=|Entry|Stop Loss|Auto-Liq|GUARD)"
```

3. **Verify stop losses are placing correctly**

Look for:
```
[CCXT] Placed buy market order [order_id] for [amount]
[CCXT] Using filled amount for SL: [amount]
[CCXT] Coinbase SL placed: [order_id]  # <-- Should see this!
```

4. **Check rejection rate**

After 30 minutes, count:
```bash
# Total decisions
grep "outcome=" logs/tradebot.log | grep "2026-01-11 12:" | wc -l

# Skipped decisions
grep "outcome=skipped" logs/tradebot.log | grep "2026-01-11 12:" | wc -l
```

**Target**: Less than 50% rejection rate

---

## SUCCESS CRITERIA

✅ Bot runs without crashing
✅ Stop losses place successfully on every entry
✅ No AttributeError or enum errors
✅ Rejection rate < 50%
✅ Bot achieving 10-15 decisions per hour

---

## ADDITIONAL NOTES

### Auto-Liquidation Works Great!

Your implementation successfully:
- Detected capital exhaustion ($0.82 < $1.10)
- Found USDT reserves ($48.23)
- Converted USDT → USD
- Recursively retried the trade
- Placed entry order successfully

The only issue was the stop loss placement that came AFTER the entry.

### Capital Status

After DOGEUSD flatten:
- Recovered: ~$17.00 from DOGE sale
- From USDT conversion: ~$48.23
- User top-up: ~$1.00
- **Total available: ~$66 USD**

This is sufficient for 3-4 positions at current sizing.

### File Locations

All bugs are in:
- `src/tradebot_sci/broker/ccxt_broker.py`

Search for:
1. `self._is_future` → Replace with `is_future`
2. `PROVIDER_ERROR` → Replace with `ERROR`

---

## QUESTIONS?

If you need me to pinpoint the EXACT line numbers for these bugs, I can search the file more thoroughly. The errors occurred around:
- Stop loss placement: Lines 700-750
- Error handling: After create_order() exception catch

Let me know if you need more specific guidance!
