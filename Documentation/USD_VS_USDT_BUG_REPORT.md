# CRITICAL: USD vs USDT Balance Bug

**Date:** January 9, 2026 15:23 EST
**Severity:** CRITICAL - Bot combining USD + USDT for all trades
**Impact:** Orders fail with INSUFFICIENT_FUND despite having enough in correct currency

---

## The Discovery

**Your Actual Coinbase Balance:**
- **USD:** $19.62
- **USDT:** $39.47
- **XRP:** 4.52 XRP (~$9.43 value)
- **DOGE:** 0.022 DOGE (~$0.00 value)

**Total Portfolio:** ~$68.52 (but only $59.09 is USD/USDT)

---

## The Bug

**Current Code** ([ccxt_broker.py:262-271](/home/qchan/Scripts/Trade by SCI/tradebot-sci-debug/src/tradebot_sci/broker/ccxt_broker.py#L262-L271)):

```python
def get_liquid_capital(self) -> float:
    """Return available USD/USDT balance for trading."""
    try:
        bal = self._exchange.fetch_balance()
        usd_free = float((bal.get("free") or {}).get("USD", 0.0) or 0.0)
        usdt_free = float((bal.get("free") or {}).get("USDT", 0.0) or 0.0)
        return usd_free + usdt_free  # ← BUG: Adds both!
    except Exception as exc:
        logger.warning("[CCXT] get_liquid_capital failed: %s", exc)
        return 0.0
```

**The Problem:**
1. Bot queries balance → Gets $19.62 USD + $39.47 USDT = **$59.09 total**
2. Bot tries to buy **LINK/USDT** (needs USDT as quote currency)
3. Bot calculates order: $56.13 (95% of $59.09)
4. **But USDT balance is only $39.47!**
5. Coinbase rejects: INSUFFICIENT_FUND

**Why It Fails:**
- **LINK/USDT pair** requires **USDT** (not USD)
- Bot only has $39.47 USDT available
- Order of $56.13 exceeds $39.47 → Rejected

---

## The Fix Required

### Fix 1: Get Quote Currency from Symbol

Add method to determine quote currency:

```python
def _get_quote_currency(self, symbol: str) -> str:
    """
    Determine the quote currency for a trading pair.

    Args:
        symbol: Trading symbol (e.g., "LINKUSDT", "POLUSD")

    Returns:
        Quote currency code ("USD", "USDT", "USDC", etc.)
    """
    # Map symbol to CCXT market symbol
    ccxt_symbol = self._map_symbol(symbol)

    # Get market info
    if ccxt_symbol in self._exchange.markets:
        market = self._exchange.markets[ccxt_symbol]
        quote = market.get("quote", "")
        if quote:
            return quote

    # Fallback: parse from symbol string
    symbol_upper = symbol.upper()
    if "USDT" in symbol_upper:
        return "USDT"
    elif "USD" in symbol_upper:
        return "USD"
    elif "USDC" in symbol_upper:
        return "USDC"
    else:
        # Default to USDT for crypto pairs
        return "USDT"
```

### Fix 2: Update get_liquid_capital() to Accept Symbol

```python
def get_liquid_capital(self, symbol: str | None = None) -> float:
    """
    Return available balance for trading in the appropriate quote currency.

    Args:
        symbol: Trading symbol to determine quote currency.
                If None, returns USD + USDT (legacy behavior).

    Returns:
        Available balance in the quote currency
    """
    try:
        bal = self._exchange.fetch_balance()
        free = bal.get("free", {})

        # [FIX] If symbol provided, only return balance for that quote currency
        if symbol:
            quote_currency = self._get_quote_currency(symbol)
            balance = float(free.get(quote_currency, 0.0) or 0.0)
            logger.debug(f"[CCXT] Liquid capital for {symbol} ({quote_currency}): ${balance:.2f}")
            return balance

        # Legacy: sum all quote currencies
        usd_free = float(free.get("USD", 0.0) or 0.0)
        usdt_free = float(free.get("USDT", 0.0) or 0.0)
        usdc_free = float(free.get("USDC", 0.0) or 0.0)
        total = usd_free + usdt_free + usdc_free

        logger.debug(f"[CCXT] Total liquid capital: USD=${usd_free:.2f} + USDT=${usdt_free:.2f} + USDC=${usdc_free:.2f} = ${total:.2f}")
        return total

    except Exception as exc:
        logger.warning("[CCXT] get_liquid_capital failed: %s", exc)
        return 0.0
```

### Fix 3: Update execute_decision() to Pass Symbol

In the position sizing section (around line 400-450):

```python
# [FIX] Query balance for the specific symbol's quote currency
account_balance = self.get_liquid_capital(decision.symbol)

if account_balance <= 0:
    logger.error(f"[CCXT] No available balance for {decision.symbol}")
    return (
        ExecutionResult(ExecutionStatus.RISK_SUPPRESSED, decision.symbol, "no balance available"),
        ExecutionOutcome(ExecutionOutcomeType.BLOCKED_GUARD, decision.symbol, "no balance"),
    )
```

---

## Expected Behavior After Fix

### Scenario: LINK/USDT Trade

**Before Fix:**
- Symbol: LINK/USDT
- Bot queries: USD + USDT = $59.09
- Calculates order: $56.13 (95% of $59.09)
- **Coinbase rejects:** INSUFFICIENT_FUND (only $39.47 USDT available)

**After Fix:**
- Symbol: LINK/USDT
- Bot detects quote currency: **USDT**
- Bot queries: USDT only = $39.47
- Calculates order: $37.50 (95% of $39.47)
- **Coinbase accepts:** $37.50 < $39.47 USDT ✅

### Scenario: POL/USD Trade

**Before Fix:**
- Symbol: POL-USD
- Bot queries: USD + USDT = $59.09
- Calculates order: $56.13
- **Coinbase rejects:** INSUFFICIENT_FUND (only $19.62 USD available)

**After Fix:**
- Symbol: POL-USD
- Bot detects quote currency: **USD**
- Bot queries: USD only = $19.62
- Calculates order: $18.64 (95% of $19.62)
- **Coinbase accepts:** $18.64 < $19.62 USD ✅

---

## Why This Happened

**Root Cause:**
The original `get_liquid_capital()` method was designed for a single fiat currency (USD only). When USDT pairs were added, the method was updated to sum USD + USDT, assuming they're interchangeable.

**But they're NOT interchangeable:**
- **USD pairs** (POL-USD) require USD
- **USDT pairs** (LINK-USDT) require USDT
- You can't spend USD to buy USDT pairs (or vice versa) without conversion

**Coinbase doesn't auto-convert:**
- Unlike some brokers, Coinbase doesn't automatically convert USD → USDT for you
- You must have the exact quote currency available

---

## Testing After Fix

### Test 1: USDT Pair (LINK/USDT)
```
Expected Balance Query: $39.47 (USDT only)
Expected Order: ~$37.50 (95% of $39.47)
Expected Result: ✅ Order placed successfully
```

### Test 2: USD Pair (POL-USD)
```
Expected Balance Query: $19.62 (USD only)
Expected Order: ~$18.64 (95% of $19.62)
Expected Result: ✅ Order placed successfully
```

### Test 3: Mixed Portfolio
```
After successful trades:
- USD: $0.98 remaining (5% buffer)
- USDT: $1.97 remaining (5% buffer)
- LINK: Position opened with $37.50 USDT
- POL: Position opened with $18.64 USD
Total deployed: $56.14 / $59.09 (95%) ✅
```

---

## Summary

**The Bug:**
- Bot adds USD + USDT = $59.09
- Tries to spend $56.13 on USDT pair
- But only has $39.47 USDT
- Order fails: INSUFFICIENT_FUND

**The Fix:**
- Detect symbol's quote currency (USD vs USDT)
- Query only that currency's balance
- Calculate order size based on available balance
- Order succeeds within available funds

**Impact:**
- **Before:** Zero trades (all orders rejected)
- **After:** Bot can trade successfully with correct balance per currency

---

**Prepared By:** Claude (AI Assistant)
**Date:** January 9, 2026 15:23 EST
**Status:** ❌ **CRITICAL BUG** - USD + USDT mixed incorrectly
**Priority:** IMMEDIATE - Without this fix, NO trades can execute
