# URGENT: GEMINI'S FIX DID NOT WORK

**Date**: 2026-01-11 12:52
**Status**: CRITICAL BUG STILL ACTIVE
**Bot Restarted**: 12:43 with "fixed" code

---

## ⚠️ GEMINI: DO THESE TWO THINGS IMMEDIATELY ⚠️

1. **Place stop losses on ALL unprotected holdings** (use the script in "PROTECT ALL UNPROTECTED HOLDINGS NOW" section below)
2. **Fix the `_is_future` bug** (instructions in "THE CORRECT FIX" section below)

**DO NOT just protect SOLUSD!** Protect EVERY position that doesn't have a stop loss!

---

## THE BUG STILL EXISTS ❌

Gemini's attempt to fix the `_is_future` bug **FAILED**. The exact same error is occurring:

```
[CCXT] Entry failed: 'CCXTExchangeBroker' object has no attribute '_is_future'
```

## EVIDENCE

**Time**: 12:51:10 (8 minutes after restart with "fix")

**What Happened**:
1. Bot decided to enter SOLUSD position
2. Successfully placed market buy order (Order ID: 7dce8ed2-b718-43bf-b229-ee9f4480b886)
3. **Tried to place stop loss** → CRASHED with `_is_future` error
4. Position left UNPROTECTED

**Log Excerpt**:
```
2026-01-11 12:51:09 [INFO] Decision: SOLUSD enter_long entry=139.33 sl=139.23
2026-01-11 12:51:10 [INFO] Placed buy market order 7dce8ed2-b718-43bf-b229-ee9f4480b886 for 43.5955 SOL/USD
2026-01-11 12:51:10 [ERROR] Entry failed: 'CCXTExchangeBroker' object has no attribute '_is_future'
2026-01-11 12:51:10 [INFO] SOLUSD outcome=error reason=entry failed
```

## CURRENT DAMAGE

**New Unprotected Position**:
- **SOLUSD**: ~43.5955 SOL purchased (~$6,074 worth at $139.33)
- **NO STOP LOSS**
- **At risk**: Potentially entire position if market crashes

**Other Positions**:
- ATOMUSD: Closed automatically (emergency exit on HTF invalidation) → +$0.049 profit realized
- DOGEUSD: 0.063 dust (harmless)

---

## WHY GEMINI'S FIX FAILED

Gemini likely fixed the wrong location or didn't fix all occurrences of `self._is_future`.

**The Error Occurs In**: Stop loss placement code (after successful entry order)

**The Bug**: Code references `self._is_future` but:
1. It's never initialized as an instance variable in `__init__`
2. The local variable `is_future` exists at line 487 but is out of scope in the stop loss section

**What Needs to Happen**:
Gemini needs to search for **EVERY** occurrence of `self._is_future` and either:
1. Replace with the local variable `is_future` (if in scope), OR
2. Re-declare `is_future` in the stop loss section

---

## GEMINI: SEARCH THESE EXACT PATTERNS

Run these searches in `ccxt_broker.py`:

```bash
# Find all occurrences
grep -n "self._is_future" src/tradebot_sci/broker/ccxt_broker.py

# Find the stop loss placement section
grep -n -A20 "place Stop Loss" src/tradebot_sci/broker/ccxt_broker.py
```

**Expected Results**:
- You'll find references to `self._is_future` that need fixing
- The bug is happening AFTER the entry order succeeds
- It's in the stop loss placement code

---

## THE CORRECT FIX

### Option A: Re-declare the variable

In the stop loss placement section (around line 677-710), ADD this line at the top:

```python
# Stop Loss Placement (CRITICAL UPGRADE)
if decision.stop_loss and decision.stop_loss > 0:
    # Re-declare is_future for this scope
    default_type = (os.getenv("CCXT_DEFAULT_TYPE") or "spot").lower()
    is_future = default_type in {"future", "swap"}  # <-- ADD THIS LINE

    stop_side = "sell" if side == "buy" else "buy"
    try:
        # ... rest of stop loss code
```

### Option B: Make it an instance variable

In `__init__` (around line 52-86), ADD:

```python
def __init__(self, profile: TradingProfileSettings, position_hold_store_path: str | None = None):
    self.profile = profile
    self.position_hold_store = None
    # ... existing code ...

    # ADD THIS:
    default_type = (os.getenv("CCXT_DEFAULT_TYPE") or "spot").lower()
    self._is_future = default_type in {"future", "swap"}

    self._exchange = self._build_exchange()
    # ... rest of init
```

---

## IMMEDIATE ACTIONS REQUIRED

1. **GEMINI**: Fix ALL occurrences of `self._is_future` bug in the code
2. **GEMINI**: Place stop losses on ALL UNPROTECTED HOLDINGS (see script below)
3. **RESTART BOT**: After confirming fix
4. **TEST**: Watch for next entry to verify stop loss places successfully

---

## PROTECT ALL UNPROTECTED HOLDINGS NOW

**CRITICAL**: You need to place stop losses on EVERY position that doesn't have one. Don't just protect SOLUSD - protect ALL holdings!

**Step 1**: Check which positions exist and don't have stop losses
**Step 2**: Place stop losses on ALL of them

Here's a script to protect ALL unprotected positions:

```python
# tools/protect_all_holdings.py
import ccxt
import os
import json

exchange = ccxt.coinbase({
    'apiKey': os.getenv('COINBASE_API_KEY'),
    'secret': os.getenv('COINBASE_API_SECRET'),
})

# Fetch all current positions
positions = exchange.fetch_balance()
print("Current positions:")
print(json.dumps(positions['total'], indent=2))

# Fetch all open orders to see which have stop losses
open_orders = exchange.fetch_open_orders()
print(f"\nOpen orders: {len(open_orders)}")

symbols_with_stops = set()
for order in open_orders:
    if 'stop_price' in order.get('info', {}):
        symbols_with_stops.add(order['symbol'])
        print(f"✓ {order['symbol']} already has stop loss")

# List of known positions that need protection
# Based on recent logs:
# - SOLUSD: ~43.6 SOL (entry ~$139.33, stop at $139.23)
# - ATOMUSD: Check if still exists (might have been closed)
# - DOGEUSD: 0.063 DOGE (dust, can ignore)

STOP_LOSS_CONFIGS = {
    'SOL/USD': {
        'entry': 139.33,
        'stop_price': '139.23',
        'stop_pct': 0.5,  # 0.5% below entry
    },
    'ATOM/USD': {
        'entry': 2.606,
        'stop_price': '2.593',
        'stop_pct': 0.5,
    },
}

protected_count = 0

for symbol, config in STOP_LOSS_CONFIGS.items():
    if symbol in symbols_with_stops:
        print(f"Skipping {symbol} - already protected")
        continue

    # Get the base currency (e.g., 'SOL' from 'SOL/USD')
    base_currency = symbol.split('/')[0]

    # Check if we have this position
    balance = positions['free'].get(base_currency, 0)
    if balance <= 0:
        print(f"Skipping {symbol} - no position (balance: {balance})")
        continue

    print(f"\n⚠️ UNPROTECTED POSITION FOUND: {symbol}")
    print(f"   Balance: {balance} {base_currency}")
    print(f"   Entry: ${config['entry']}")
    print(f"   Stop: ${config['stop_price']}")

    try:
        # Place stop loss
        stop_price = float(config['stop_price'])
        limit_price = stop_price * 0.95  # 5% below stop

        stop_order = exchange.create_order(
            symbol=symbol,
            type='stop_limit_stop_limit_gtc',
            side='sell',
            amount=balance,
            params={
                'stop_price': str(stop_price),
                'limit_price': str(round(limit_price, 2)),
                'stop_direction': 'STOP_DIRECTION_STOP_DOWN'
            }
        )

        print(f"✅ Stop loss placed: {stop_order['id']}")
        protected_count += 1

    except Exception as e:
        print(f"❌ Failed to place stop loss for {symbol}: {e}")

print(f"\n{'='*50}")
print(f"Protected {protected_count} position(s)")
print(f"{'='*50}")
```

Run it:
```bash
cd tools
python protect_all_holdings.py
```

**IMPORTANT NOTES:**
1. This script checks ALL positions and places stops on anything unprotected
2. It skips positions that already have stop losses (avoids duplicates)
3. It handles dust positions by checking balance > 0
4. **Run this EVERY time the bot crashes after placing an entry order**

---

## TESTING AFTER FIX

Once Gemini fixes the bug again:

1. **Restart bot**
2. **Watch logs for next entry**:
```bash
tail -f logs/tradebot.log | grep -E "(Placed.*market order|Stop Loss|_is_future|ERROR)"
```

3. **Look for**:
```
[INFO] Placed buy market order [id] for [amount]
[INFO] Coinbase SL placed: [id]  # <-- This should appear!
```

4. **If you see**:
```
[ERROR] ... '_is_future'  # <-- Bug still exists
```

Then Gemini needs to try again with more careful searching.

---

## SUMMARY FOR GEMINI

You fixed it once, but the bug is still happening. This means either:
1. You didn't fix ALL occurrences of `self._is_future`
2. You fixed the wrong location
3. The code wasn't properly reloaded

**DO THIS**:
1. Search for `self._is_future` in the ENTIRE `ccxt_broker.py` file
2. Replace EVERY occurrence with either:
   - Local variable `is_future` if in scope
   - Re-declare `is_future = default_type in {"future", "swap"}` if not in scope
3. Verify the fix is in the stop loss placement section (after entry order succeeds)
4. Restart the bot
5. Test with next trade

The bug is definitely in the stop loss placement code that runs AFTER a successful entry order.
