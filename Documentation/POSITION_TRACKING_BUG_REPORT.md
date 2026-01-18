# CRITICAL: Position Tracking Bug - Bot Ignoring Real Positions

**Date:** January 9, 2026 15:27 EST
**Severity:** CRITICAL - Bot not tracking existing positions
**Impact:** Risk management broken, positions not managed, no exit strategy

---

## The Discovery

**Your Actual Holdings:**
- **XRP:** 4.52 XRP (~$9.43)
- **DOGE:** 0.022 DOGE (~$0.00)
- **USDT:** $39.47
- **USD:** $19.62

**Bot Says:**
```
[HOLDINGS] {"count": 0, "positions": [], "reason": "heartbeat"}
[STATE] XRPUSDT open_position: none
[GUARD] Pruned phantom positions: {'XRPUSDT', 'DOGEUSDT'} -> set()
```

**Bot thinks you have ZERO positions!**

---

## Root Cause Analysis

### Step 1: Position Detection (WORKING)

**Code:** `list_open_position_symbols()` ([ccxt_broker.py:143-194](/home/qchan/Scripts/Trade by SCI/tradebot-sci-debug/src/tradebot_sci/broker/ccxt_broker.py#L143-L194))

```python
def list_open_position_symbols(self) -> set[str]:
    balance = self._exchange.fetch_balance()
    total = balance.get("total", {})
    ignored_currencies = {"USD", "USDT", "USDC", "DAI", "FDUSD"}

    for currency, amount in total.items():
        if currency in ignored_currencies:
            continue  # Skip cash/stablecoins

        # Found: XRP = 4.524525, DOGE = 0.02220808
        # Returns: {'XRPUSDT', 'DOGEUSDT'}
```

**Result:** ✅ Correctly detects XRP and DOGE positions

---

### Step 2: Position Verification (FAILING)

**Code:** Guard logic in [runtime/loop.py:895-922](/home/qchan/Scripts/Trade by SCI/tradebot-sci-debug/src/tradebot_sci/runtime/loop.py#L895-L922)

```python
verified_symbols = set()
for sym in open_position_symbols:  # sym = "XRPUSDT"
    state = executor._fetch_symbol_state(sym)
    if state and abs(state.get("position_shares", 0)) > 0:
        verified_symbols.add(sym)
    # XRP not added to verified_symbols!

# Logs: "Pruned phantom positions: {'XRPUSDT', 'DOGEUSDT'} -> set()"
open_position_symbols = verified_symbols  # Now empty!
```

**Result:** ❌ Verification fails, positions marked as "phantom"

---

### Step 3: The Bug in get_open_position_snapshot()

**Code:** [ccxt_broker.py:224-237](/home/qchan/Scripts/Trade by SCI/tradebot-sci-debug/src/tradebot_sci/broker/ccxt_broker.py#L224-L237)

```python
def get_open_position_snapshot(self, symbol: str) -> dict | None:
    # symbol = "XRPUSDT"
    sym = self._map_symbol(symbol)  # sym = "XRP/USDT"
    base, _ = sym.split("/")  # base = "XRP"

    # Spot: fetch_balance
    bal = self._exchange.fetch_balance()
    total = bal.get("total", {})
    size = float(total.get(base, 0.0))  # size = 4.524525 XRP

    # [BUG] Check if below minimum amount
    # min_amount is undefined here! (Should be from markets[sym]['limits']['amount']['min'])
    if min_amount > 0 and abs(size) > 0 and abs(size) < min_amount:
        logger.debug(f"Ignoring dust position for {sym}: size={size} < min={min_amount}")
        size = 0.0  # ← SETS SIZE TO ZERO!

    if abs(size) == 0:
        return None  # ← Returns None, verification fails!
```

**The Problem:**
1. Bot queries XRP balance: **4.52 XRP**
2. Checks if `size < min_amount` (minimum trade size from Coinbase)
3. **If below minimum, treats as "dust" and sets `size = 0`**
4. Returns `None` because size is now 0
5. Verification fails, position marked as "phantom"
6. Position is pruned from tracking

---

## Why This Is Critical

### 1. No Position Management
- You have 4.52 XRP ($9.43) in an open position
- Bot doesn't know it exists
- **No stop loss protection**
- **No profit target management**
- **No exit strategy**

### 2. Risk Management Broken
- Bot calculates available capital incorrectly
- Thinks it has $59.09 available (USD + USDT)
- **Actually has XRP position worth $9.43**
- Could open overleveraged positions

### 3. No Exit Decisions
- AI should be making decisions for XRP:
  - Should we hold?
  - Should we take profit?
  - Should we cut losses?
- **None of this is happening**

### 4. Silent Position Decay
- XRP position exists but isn't tracked
- If XRP drops, you lose money silently
- Bot never alerts you or takes action

---

## The Fix Required

### Fix 1: Don't Treat Small Positions as Dust

**Current Bug** (lines 235-237):
```python
if min_amount > 0 and abs(size) > 0 and abs(size) < min_amount:
    size = 0.0  # ← BUG: Ignores position
```

**Fixed Code:**
```python
# [FIX] Don't ignore existing positions just because they're small
# Only ignore dust when OPENING new positions, not when checking existing ones
# If we have it, we need to track it!

# Remove the dust check entirely from get_open_position_snapshot()
# Or at minimum, still return the position but mark it as "below_minimum":

if min_amount > 0 and abs(size) > 0 and abs(size) < min_amount:
    logger.warning(f"[CCXT] Position {sym} below minimum tradeable size: {size} < {min_amount} (cannot add to it)")
    # Still return the position, but flag it
    is_below_minimum = True
else:
    is_below_minimum = False

# Always return the position if it exists
return {
    "symbol": symbol.upper(),
    "side": "long" if size > 0 else "short",
    "size": size,
    "below_minimum": is_below_minimum,  # Flag for UI/alerts
    ...
}
```

### Fix 2: Log Position Tracking Clearly

Add logging to show why positions are pruned:

```python
# In runtime/loop.py verification loop
for sym in open_position_symbols:
    state = executor._fetch_symbol_state(sym)
    position_shares = abs(state.get("position_shares", 0)) if state else 0

    if position_shares > 0:
        verified_symbols.add(sym)
        logger.debug(f"[GUARD] Verified position {sym}: {position_shares} shares")
    else:
        logger.warning(f"[GUARD] Position {sym} failed verification (shares={position_shares}, state={state})")
```

### Fix 3: Show Positions in GUI

The "Orders" panel should show:
- **Active Positions:** XRP (4.52 @ $2.08, current P&L: -$0.50)
- **Position Status:** Below minimum trade size (cannot scale in)
- **AI Recommendation:** Hold / Exit / Scale Out

---

## Impact Assessment

### Current State
- **Positions Held:** XRP (4.52), DOGE (0.022)
- **Bot Awareness:** ZERO (thinks no positions exist)
- **Risk Exposure:** Unmanaged ($9.43 at risk)
- **Exit Strategy:** None

### After Fix
- **Positions Tracked:** XRP, DOGE
- **Bot Awareness:** Full visibility
- **Risk Management:** Active monitoring
- **Exit Strategy:** AI makes hold/exit decisions every cycle

---

## Testing After Fix

### Test 1: Position Detection
```bash
# Check logs for position tracking
grep -E "HOLDINGS|open_position" logs/tradebot.log | tail -20

# Expected:
[HOLDINGS] {"count": 2, "positions": [{"symbol": "XRPUSDT", "size": 4.52}, {"symbol": "DOGEUSDT", "size": 0.022}]}
[STATE] XRPUSDT open_position: {"size": 4.524525, "side": "long", "below_minimum": false}
```

### Test 2: AI Decision for Existing Position
```bash
# Bot should make decisions for XRP position
grep "XRPUSDT.*action=" logs/tradebot.log

# Expected:
Decision: XRPUSDT 5m | bias=long phase=correction action=hold
  (or action=close_position, or action=scale_out, depending on market)
```

### Test 3: GUI Display
- Orders panel should show XRP position
- Should show current P&L
- Should show AI recommendation (hold/exit)

---

## Additional Issues Discovered

### Issue 1: No `min_amount` Variable

Line 230 references `min_amount` but it's never defined in this scope!

```python
# Line 230 (undefined variable!)
if min_amount is None:
    qty_steps = getattr(self.profile, "crypto_qty_steps", {})
    min_amount = float(qty_steps.get(symbol, 0.0) or 0.0)
```

This should be defined earlier:
```python
# Get minimum tradeable amount from market info
min_amount = None
if sym in self._exchange.markets:
    market = self._exchange.markets[sym]
    limits = market.get("limits", {})
    amount_limits = limits.get("amount", {})
    min_amount = float(amount_limits.get("min", 0.0) or 0.0)
```

### Issue 2: No Position Entry Tracking

When the bot bought XRP (05:35:50), there's no record of:
- Entry price ($2.08?)
- Entry time
- Stop loss level
- Take profit target

**Without this data, the bot can't make informed hold/exit decisions!**

Possible solutions:
1. Store position metadata in a file (JSON)
2. Query Coinbase order history to reconstruct entry
3. Use current price as entry (not ideal but better than nothing)

---

## Summary

**The Critical Bug:**
Bot detects positions (XRP, DOGE) but then prunes them as "phantom" because `get_open_position_snapshot()` returns `None` when position size is below minimum tradeable amount.

**Why This Happens:**
1. XRP balance: 4.52 XRP
2. Check: `if size < min_amount` → sets `size = 0`
3. Return: `None` (because size is 0)
4. Verification fails → Position pruned as "phantom"

**The Fix:**
- Don't treat existing positions as dust
- Always return position data if balance > 0
- Flag positions as "below_minimum" if they can't be scaled
- Log verification failures clearly
- Show positions in GUI

**Impact:**
- **Before:** $9.43 XRP position unmanaged, at risk
- **After:** Full tracking, AI makes hold/exit decisions, risk managed

---

**Prepared By:** Claude (AI Assistant)
**Date:** January 9, 2026 15:27 EST
**Status:** ❌ **CRITICAL BUG** - Existing positions not tracked
**Priority:** IMMEDIATE - Risk management completely broken for existing positions
