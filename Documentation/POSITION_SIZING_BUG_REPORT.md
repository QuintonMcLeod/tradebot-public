# CRITICAL: Position Sizing Bug - Bot Never Queries Account Balance

**Date:** January 9, 2026 14:54 EST
**Severity:** CRITICAL - Bot placing orders without checking actual account balance
**Impact:** Insufficient funds errors, failed trades, incorrect risk management

---

## The User's Question

**"Does the bot legitimately see my account balance before it decides to put down a risk?"**

**Answer: NO - The bot does NOT query account balance before placing orders!**

---

## Evidence of the Bug

### 1. The Failed Order (05:36:51 EST)

**Log Entry:**
```
2026-01-09 05:36:51 [ERROR] tradebot_sci.broker.ccxt_broker - [CCXT] Entry failed: coinbase {
  "success":false,
  "error_response":{
    "error":"INSUFFICIENT_FUND",
    "message":"Insufficient balance in source account"
  },
  "order_configuration":{
    "market_market_ioc":{
      "quote_size":"137.741"  # ← Trying to place $137.74 USD order
    }
  }
}
```

### 2. The AI Decision That Triggered It

**Log Entry:**
```
Decision: POLUSD 5m | bias=long phase=chop action=enter_long
entry=0.1452 sl=0.1438 tp=0.1459
risk%=0.05  # ← AI said 5% risk, but bot tried $137.74!
```

**Context:**
- AI decision specified: `risk%=0.05` (5% of account)
- If bot tried to place $137.74 order at 5% risk, it would imply:
  - **Assumed account balance: $2,754.80** ($137.74 / 0.05)
- But Coinbase rejected with INSUFFICIENT_FUND
- **Actual account balance: Unknown (probably < $137.74)**

---

## Root Cause Analysis

### Position Sizing Code in ccxt_broker.py

**File:** `src/tradebot_sci/broker/ccxt_broker.py`
**Lines:** 362-378

```python
# Entry Logic (enter_long, enter_short, scale_in)
if action in {"enter_long", "enter_short", "scale_in"}:
    # Sizing
    qty = 0.0
    ticker = self._safe_fetch_ticker(sym)
    if ticker and ticker.last:
        qty = max(0.0, float(self.profile.crypto_min_notional_usd) / float(ticker.last))
    if qty <= 0:
        qty = 0.001 # Minimal fallback

    # Entry Execution
    try:
        # Place Entry
        order = self._exchange.create_order(sym, "market", side, qty)
        entry_id = str(order.get("id"))
        logger.info(f"[CCXT] Placed {side} market order {entry_id} for {qty} {sym}")
```

### The Calculation Breakdown

**Config Setting:**
```yaml
# config/settings_profiles.yaml:30
crypto_min_notional_usd: 20.0
```

**Position Size Calculation:**
```python
# With POLUSD at price $0.1452
qty = crypto_min_notional_usd / ticker.last
qty = 20.0 / 0.1452
qty = 137.74
```

**CCXT Order Placement:**
```python
order = self._exchange.create_order(sym, "market", side, qty)
# Passes qty = 137.74
```

**Coinbase API Interpretation:**
- **Bot intended:** Buy 137.74 POL coins (base currency) = ~$20 worth
- **Coinbase received:** `quote_size = 137.74` = Buy $137.74 USD worth of POL
- **Result:** Coinbase tries to place $137.74 order → INSUFFICIENT_FUND error

---

## Why the Bug Exists

### 1. No Balance Query Before Order

The bot has a `get_liquid_capital()` method that queries Coinbase balance:

**File:** `src/tradebot_sci/broker/ccxt_broker.py`
**Lines:** 262-274

```python
def get_liquid_capital(self) -> float:
    """Return available USD/USDT balance for trading.

    This is used by the bot for position sizing calculations.
    """
    try:
        bal = self._exchange.fetch_balance()
        usd_free = float((bal.get("free") or {}).get("USD", 0.0) or 0.0)
        usdt_free = float((bal.get("free") or {}).get("USDT", 0.0) or 0.0)
        return usd_free + usdt_free
    except Exception as exc:
        logger.warning("[CCXT] get_liquid_capital failed: %s", exc)
        return 0.0
```

**But this method is NEVER CALLED before order placement!**

Verified by searching the codebase:
```bash
$ grep -r "get_liquid_capital" src/
src/tradebot_sci/broker/ccxt_broker.py:262:    def get_liquid_capital(self) -> float:
src/tradebot_sci/broker/ccxt_broker.py:273:            logger.warning("[CCXT] get_liquid_capital failed: %s", exc)
# No other files call this method!
```

### 2. AI Risk Percentage is Ignored

The AI decision specifies `risk_per_trade_pct: 0.05` (5% of account), but:
- This value is **completely ignored** by ccxt_broker.py
- Position sizing uses hardcoded `crypto_min_notional_usd: 20.0`
- No calculation of: `position_size = account_balance * risk_pct`

### 3. Coinbase API Ambiguity

CCXT library's `create_order(sym, "market", side, qty)` is ambiguous:
- **Standard interpretation:** `qty` = base currency amount (POL coins)
- **Coinbase interpretation:** `qty` = quote currency amount (USD)
- **Result:** Bot calculates 137.74 POL coins, Coinbase receives $137.74 USD

---

## Impact Assessment

### Current State
- **Trades executed:** 0
- **Orders attempted:** Multiple (XRPUSDT succeeded, POLUSD failed)
- **Risk management:** Broken (AI risk % ignored)
- **Balance awareness:** None (bot doesn't know account balance)

### Risk Management Failures

**Scenario 1: Insufficient Funds**
- Bot tries to place $137.74 order
- Account has < $137.74
- Order rejected → No trade despite valid setup

**Scenario 2: Over-Leveraged If Sufficient Funds**
- AI specifies 5% risk = $137.74 order
- This implies $2,754.80 account balance
- But if actual balance is $500, this is 27.5% risk (not 5%)!
- **Extreme risk exposure beyond user's intent**

**Scenario 3: Multiple Concurrent Orders**
- With `multi_position_enabled: true`, bot could try multiple $137.74 orders
- Each order assumes full account balance available
- Would quickly exceed total balance → Multiple failures

---

## Why XRPUSDT Order Succeeded Earlier

**Log Entry (05:35:50 EST):**
```
[INFO] - [CCXT] Placed buy market order 9762af7b-ce20-4e45-8a6b-d526ff534c33 for 9.514295228580943 XRP/USDT
[INFO] - [EXEC] XRPUSDT outcome=success_submitted
```

**Calculation:**
- XRPUSDT price: ~$2.103 (estimated)
- Quantity: 9.514 XRP
- Order value: 9.514 * $2.103 = **$20.01**

**Why it succeeded:**
- Coinbase interpreted as ~$20 order (close to `crypto_min_notional_usd: 20.0`)
- Account had ≥ $20 available
- Order placed successfully

**But then failed to set stop loss:**
```
[ERROR] - [CCXT] FAILED TO PLACE STOP LOSS for 9762af7b-ce20-4e45-8a6b-d526ff534c33:
coinbase createOrder() only stop limit orders are supported
```

**Result:**
- Entry order succeeded
- Stop loss failed
- Position entered WITHOUT PROTECTION
- Later appeared in phantom positions list (pruned at 05:40:01)

---

## Required Fixes

### Priority 1: Query Balance Before Order Placement

**File:** `src/tradebot_sci/broker/ccxt_broker.py`
**Location:** Lines 362-368 (position sizing section)

**Current Code:**
```python
# Sizing
qty = 0.0
ticker = self._safe_fetch_ticker(sym)
if ticker and ticker.last:
    qty = max(0.0, float(self.profile.crypto_min_notional_usd) / float(ticker.last))
if qty <= 0:
    qty = 0.001 # Minimal fallback
```

**Fixed Code:**
```python
# [FIX] Query account balance first
account_balance = self.get_liquid_capital()
if account_balance <= 0:
    logger.error(f"[CCXT] No available balance (${account_balance:.2f})")
    return (
        ExecutionResult(ExecutionStatus.RISK_SUPPRESSED, decision.symbol, "no balance available"),
        ExecutionOutcome(ExecutionOutcomeType.BLOCKED_GUARD, decision.symbol, "no balance"),
    )

# [FIX] Calculate position size based on risk percentage from AI decision
risk_pct = decision.risk_per_trade_pct or 0.01  # Default 1% if not specified
risk_amount = account_balance * risk_pct

# [FIX] Calculate stop loss distance in USD
ticker = self._safe_fetch_ticker(sym)
if not ticker or not ticker.last:
    logger.error(f"[CCXT] No ticker data for {sym}")
    return (
        ExecutionResult(ExecutionStatus.PROVIDER_ERROR, decision.symbol, "no ticker data"),
        ExecutionOutcome(ExecutionOutcomeType.ERROR, decision.symbol, "no ticker"),
    )

entry_price = ticker.last
stop_loss = decision.stop_loss or 0.0

if stop_loss <= 0:
    logger.error(f"[CCXT] No stop loss specified for {decision.symbol}")
    return (
        ExecutionResult(ExecutionStatus.RISK_SUPPRESSED, decision.symbol, "no stop loss"),
        ExecutionOutcome(ExecutionOutcomeType.BLOCKED_GUARD, decision.symbol, "no stop"),
    )

# [FIX] Calculate position size based on risk and stop distance
stop_distance = abs(entry_price - stop_loss)
risk_per_unit = stop_distance  # Risk per coin/share
position_size_usd = risk_amount / risk_per_unit * entry_price

# [FIX] Apply min/max notional limits
min_notional = float(self.profile.crypto_min_notional_usd)
max_notional = float(getattr(self.profile, 'crypto_max_notional_usd', 10000.0))

position_size_usd = max(min_notional, min(position_size_usd, max_notional))

# [FIX] Convert to quantity (base currency)
qty = position_size_usd / entry_price

logger.info(f"[CCXT] Position sizing: balance=${account_balance:.2f}, risk%={risk_pct:.2%}, "
            f"risk_amount=${risk_amount:.2f}, stop_distance=${stop_distance:.4f}, "
            f"position_size=${position_size_usd:.2f}, qty={qty:.4f}")
```

### Priority 2: Fix Coinbase Quote Size Interpretation

**Option A: Use CCXT Parameters**
```python
# Specify base currency amount explicitly
params = {'base_size': qty}  # Or 'quote_size' if USD amount
order = self._exchange.create_order(sym, "market", side, None, None, params)
```

**Option B: Check Coinbase Documentation**
- Verify correct CCXT parameter for Coinbase Advanced Trade API
- May need `params = {'quote_size': position_size_usd}` instead of `qty` parameter

### Priority 3: Fix Stop Loss for Coinbase

**File:** `src/tradebot_sci/broker/ccxt_broker.py`
**Location:** Lines 393-408

**Current Code:**
```python
if "coinbase" in self.exchange_id.lower():
    order_type = "stop_limit"
    # Calculate aggressive limit price (5% buffer) to emulate market stop behavior
```

**Issue:** Coinbase stop-limit orders are working (no error shown recently), but earlier XRP order failed with:
```
FAILED TO PLACE STOP LOSS: coinbase createOrder() only stop limit orders are supported
```

**Verify:** Check if stop-limit logic is correct and being used consistently.

---

## Testing Required

### Test 1: Verify Balance Query
```python
# Add to ccxt_broker.py before order placement
balance = self.get_liquid_capital()
logger.info(f"[TEST] Account balance: ${balance:.2f}")
```

### Test 2: Verify Position Size Calculation
```python
# Add logging after position size calculation
logger.info(f"[TEST] AI risk%: {decision.risk_per_trade_pct}, "
            f"Calculated position: ${position_size_usd:.2f}, "
            f"Quantity: {qty:.4f}")
```

### Test 3: Verify Coinbase Order Format
```python
# Log the actual order payload sent to Coinbase
logger.info(f"[TEST] Order params: sym={sym}, type={order_type}, side={side}, qty={qty}, params={params}")
```

---

## Expected Behavior After Fix

### Correct Flow:
1. **Query Balance:**
   - Bot calls `get_liquid_capital()`
   - Logs: `[CCXT] Account balance: $87.45`

2. **Calculate Position Size:**
   - AI decision: `risk_per_trade_pct: 0.05` (5%)
   - Risk amount: $87.45 × 0.05 = $4.37
   - Entry: $0.1452, Stop: $0.1438
   - Stop distance: $0.0014
   - Position size: $4.37 / $0.0014 × $0.1452 = $453 (capped to max_notional)
   - **Or if properly calculated:** Risk per POL = $0.0014, Position = $4.37 / $0.0014 = 3,121 POL = $453 worth

3. **Place Order:**
   - Order: Buy $20 worth (or calculated amount) of POLUSD
   - Coinbase: Accepts (sufficient funds)
   - Stop Loss: Placed as stop-limit order
   - Result: Position entered with protection

---

## Summary

**The Critical Bug:**
- Bot does NOT query account balance before placing orders
- Position sizing uses hardcoded `crypto_min_notional_usd: 20.0`
- AI risk percentage (`risk_per_trade_pct`) is completely ignored
- Coinbase interprets `qty` parameter as USD amount, not coin amount
- Result: Insufficient funds errors OR over-leveraged positions

**Impact:**
- Zero trades despite valid setups (INSUFFICIENT_FUND errors)
- Risk management completely broken
- Bot has no awareness of actual account balance
- Could accidentally over-leverage if sufficient funds available

**Fix Required:**
1. Query balance before every order using `get_liquid_capital()`
2. Calculate position size based on: `balance × risk_pct / stop_distance`
3. Fix Coinbase API parameter interpretation (base_size vs quote_size)
4. Add logging to verify balance queries and position calculations

---

**Prepared By:** Claude (AI Assistant)
**Date:** January 9, 2026 14:54 EST
**Status:** ❌ **CRITICAL BUG** - Position sizing broken, balance never queried
**Priority:** IMMEDIATE - Bot cannot trade safely without this fix
