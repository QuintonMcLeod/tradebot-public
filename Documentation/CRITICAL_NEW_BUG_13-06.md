# CRITICAL: GEMINI INTRODUCED NEW BUG

**Date**: 2026-01-11 13:06
**Status**: BOT BROKEN AGAIN
**Severity**: P0 - BLOCKING ALL TRADES

---

## EXECUTIVE SUMMARY

Gemini attempted to fix the `_is_future` bug and **introduced a DIFFERENT critical bug**:

```
'CCXTExchangeBroker' object has no attribute '_get_base_currency'
```

**Impact**:
- ATOMUSD order placed ($62.33) → **CRASHED** → Position unknown state
- SOLUSD order placed ($3.13) → **CRASHED** → Position unknown state
- Bot showing **8 open positions** but only tracking 3
- $0.18 available capital (virtually all capital locked)
- Bot completely non-functional

**Root Cause**: Gemini added code calling `self._get_base_currency()` but never defined this method.

---

## NEW BUG DETAILS

### Error Message
```
[CCXT] Entry failed: 'CCXTExchangeBroker' object has no attribute '_get_base_currency'
```

### When It Occurs
After successfully placing entry order, during the settlement wait phase:
1. Bot places market entry order ✅
2. Log shows "Waiting for [SYMBOL] settlement (up to 10s)..." ✅
3. Code calls `self._get_base_currency()` ❌ **CRASHES**
4. Order partially fills, no stop loss placed
5. Position left in unknown state

### Evidence from Logs

**13:05:40 - ATOMUSD**:
```
[CCXT] Placed buy market order 2c7b0c64-32e8-4ea7-b5e0-c1ec82618ce2 for 62.329499999999996 ATOM/USD
[CCXT] Waiting for ATOM/USD settlement (up to 10s)...
[ERROR] Entry failed: 'CCXTExchangeBroker' object has no attribute '_get_base_currency'
```

**13:05:47 - SOLUSD**:
```
[CCXT] Placed buy market order 304d11af-c8e8-4e1e-9fe7-bc44f5ff380f for 3.135 SOL/USD
[CCXT] Waiting for SOL/USD settlement (up to 10s)...
[ERROR] Entry failed: 'CCXTExchangeBroker' object has no attribute '_get_base_currency'
```

**13:00:47 - BTCUSD** (earlier):
```
[EXEC] BTCUSD outcome=error reason=entry failed: 'CCXTExchangeBroker' object has no attribute '_get_base_currency'
```

---

## CURRENT BOT STATE: DISASTER

### Position Count Discrepancy

**Bot Claims**: Managing 3 open positions (SOLUSD, BTCUSD, ATOMUSD)

**Reality**: Bot is blocking new trades because it sees **8 open positions**:
```
[GUARD] Blocked new entry on ADAUSD: max_concurrent_positions=5 reached (open=8 pending=0)
```

This means there are **5 PHANTOM POSITIONS** the bot can't track properly!

### Capital Status

**Available**: $0.18 USD
**Status**: Virtually all capital locked in unknown positions

Recent attempts blocked:
```
[CCXT] Capping position size at safe balance limit: $20.00 -> $0.17 (Cap=$0.18)
[CCXT] Skipping entry for POLUSD: Calculated size $0.17 < Min $1.1 (Capital=$0.18)
[EXEC] POLUSD outcome=blocked_guard reason=capital exhausted
```

---

## WHAT GEMINI DID WRONG

### The Fix Attempt

Gemini tried to add settlement wait logic after placing entry orders. This is GOOD in concept - it addresses the settlement race condition.

**New Code Added**:
```python
# After placing entry order:
logger.info(f"Waiting for {symbol} settlement (up to 10s)...")
# Then tries to call:
base_currency = self._get_base_currency(symbol)  # <-- THIS DOESN'T EXIST!
```

### The Problem

`_get_base_currency()` is **NOT A METHOD** in `CCXTExchangeBroker`. Gemini referenced a method that doesn't exist.

**What Should Have Been Done**:
```python
# Extract base currency from symbol
base_currency = symbol.split('/')[0]  # e.g., 'SOL/USD' -> 'SOL'
```

OR create the helper method:
```python
def _get_base_currency(self, symbol: str) -> str:
    """Extract base currency from trading pair symbol."""
    return symbol.split('/')[0]
```

---

## IMMEDIATE DAMAGE ASSESSMENT

### Unprotected Positions Created

1. **ATOMUSD**: $62.33 order placed at 13:05:40
   - Order ID: 2c7b0c64-32e8-4ea7-b5e0-c1ec82618ce2
   - Intended size: 62.33 ATOM
   - **Status: UNKNOWN** (crashed before confirmation)
   - **Stop Loss: NONE**

2. **SOLUSD**: $3.13 order placed at 13:05:47
   - Order ID: 304d11af-c8e8-4e1e-9fe7-bc44f5ff380f
   - Intended size: 3.135 SOL
   - **Status: UNKNOWN** (crashed before confirmation)
   - **Stop Loss: NONE**

3. **BTCUSD**: Earlier crash (13:00:47)
   - **Status: UNKNOWN**
   - **Stop Loss: NONE**

### Plus Previous Unprotected Positions

From earlier monitoring:
- **SOLUSD**: 0.31 SOL (~$43.56) - partial fill from 12:51
- **ATOMUSD**: 7.6 ATOM (~$19.81) - from 12:37
- **BTCUSD**: 0.00002388 BTC (~$2.17) - dust
- **DOGEUSD**: 0.063 DOGE (~$0.009) - dust

**Total Unprotected Capital**: ~$65+ potentially at risk

---

## THE FIX GEMINI NEEDS TO DO

### Step 1: Define the Helper Method

Add to `CCXTExchangeBroker` class:

```python
def _get_base_currency(self, symbol: str) -> str:
    """
    Extract base currency from trading pair symbol.
    Example: 'SOL/USD' -> 'SOL'
    """
    return symbol.split('/')[0]
```

### Step 2: Verify Settlement Logic Works

After adding the method, the settlement wait should:
1. Wait for order to fill
2. Check balance of base currency
3. Confirm tokens settled
4. THEN place stop loss

### Step 3: Test With Debug Logging

Add print statements to verify:
```python
logger.info(f"Waiting for {symbol} settlement (up to 10s)...")
base_currency = self._get_base_currency(symbol)
logger.info(f"Base currency: {base_currency}")
# ... rest of settlement check ...
logger.info(f"Settlement confirmed, placing stop loss...")
```

---

## ALTERNATIVE: SIMPLER FIX

If Gemini wants to avoid the complexity, just do this:

```python
# After placing entry order:
import time
logger.info(f"Waiting 3s for settlement...")
time.sleep(3)  # Simple delay
# Then place stop loss
```

This is less elegant but WILL WORK and won't crash.

---

## TESTING REQUIREMENTS

Once fixed, Gemini MUST:

1. **Restart bot**
2. **Watch for FIRST trade entry**
3. **Verify these log lines appear**:
   ```
   [CCXT] Placed buy market order [id] for [amount]
   [CCXT] Waiting for [SYMBOL] settlement (up to 10s)...
   [CCXT] Base currency: [CURRENCY]  # <-- NEW LINE SHOULD APPEAR
   [CCXT] Coinbase SL placed: [id]   # <-- STOP LOSS PLACED!
   ```

4. **If ANY error appears**: STOP and report exact line numbers

---

## PATTERN OBSERVED

Every time Gemini "fixes" the code, a NEW bug appears:

1. **First bug**: `_is_future` doesn't exist
2. **Gemini's fix**: Added settlement wait
3. **Second bug**: `_get_base_currency()` doesn't exist
4. **Next fix**: ???

**GEMINI**: You need to TEST your code changes locally or add EXTENSIVE debug logging before running on live bot!

---

## RECOMMENDED IMMEDIATE ACTIONS

### Action 1: Stop the Bot (User Decision)

The bot is creating more broken positions with every cycle. Consider stopping until fix is complete.

### Action 2: Emergency Position Audit

Run this script to see ALL positions:
```python
# tools/emergency_audit_all_positions.py
import ccxt
import os

exchange = ccxt.coinbase({
    'apiKey': os.getenv('COINBASE_API_KEY'),
    'secret': os.getenv('COINBASE_API_SECRET'),
})

balance = exchange.fetch_balance()
print("=== ALL NON-ZERO POSITIONS ===")
for currency, amount in balance['total'].items():
    if amount > 0 and currency != 'USD':
        print(f"{currency}: {amount}")

print("\n=== USD BALANCE ===")
print(f"Total: ${balance['total'].get('USD', 0):.2f}")
print(f"Free: ${balance['free'].get('USD', 0):.2f}")

print("\n=== OPEN ORDERS ===")
orders = exchange.fetch_open_orders()
print(f"Total open orders: {len(orders)}")
for order in orders:
    print(f"  {order['symbol']}: {order['side']} {order['type']} {order.get('amount', 'N/A')}")
```

### Action 3: Place Manual Stop Losses

For any confirmed positions without stop losses, place them manually using the `protect_all_holdings.py` script from previous documentation.

---

## WHY THIS KEEPS HAPPENING

**Root Cause**: Gemini is making changes without having:
1. Full context of the codebase structure
2. Ability to test changes before deployment
3. Clear understanding of what methods exist

**Solution**: Gemini should:
1. Search for existing helper methods before creating calls to new ones
2. Add debug logging extensively
3. Make minimal changes (don't refactor while fixing)
4. Test each change in isolation

---

## COMPARISON: Expected vs Actual

### Expected Behavior After Fix:
1. Place entry order ✅
2. Wait for settlement ✅
3. Detect base currency ✅
4. Place stop loss ✅
5. Position protected ✅

### Actual Behavior Now:
1. Place entry order ✅
2. Wait for settlement ✅
3. Call non-existent method ❌ **CRASH**
4. No stop loss ❌
5. Position unprotected ❌
6. Capital locked ❌

---

## BOTTOM LINE

**GEMINI**: You traded one bug for another bug. The `_is_future` bug is gone, but now you have `_get_base_currency` bug.

**THE FIX IS SIMPLE**:
- Add the method definition OR
- Use `symbol.split('/')[0]` directly

**STOP TRYING TO FIX WITHOUT TESTING!**

Every "fix" is creating MORE broken positions and locking up MORE capital!

---

## FILES AFFECTED

- `src/tradebot_sci/broker/ccxt_broker.py` - Contains the bug
- Bot logs show 3+ failed entries with this error

---

## NEXT MONITORING

I'll continue watching logs to see:
- If Gemini fixes this new bug
- How many more positions get created
- If capital becomes completely exhausted

**Current Status**: Bot running but COMPLETELY NON-FUNCTIONAL
