# POSITION AUDIT - Bot State at 13:08

**Date**: 2026-01-11 13:08
**Status**: Bot broken with position tracking errors

---

## SUMMARY

The bot is in a **CONFUSED STATE** with critical discrepancies:

- **Tracked Positions**: 4 (shown in holdings snapshot)
- **Guard System Sees**: 8 open positions
- **Discrepancy**: 4 PHANTOM POSITIONS the bot can't manage
- **New Bug**: `_get_base_currency` crashes preventing stop loss placement
- **Available Capital**: $0.18 USD (99.7% capital locked)

---

## POSITIONS THE BOT CAN TRACK (from 13:01:33 snapshot)

### Position 1: SOLUSD
- **Size**: 0.31261662 SOL
- **Entry Price**: $139.34
- **Current Value**: ~$43.55
- **Unrealized P&L**: -$0.00313 (-0.007%)
- **Stop Loss**: NONE ❌
- **Status**: Partial fill from 12:51 crash

### Position 2: ATOMUSD
- **Size**: 7.6 ATOM
- **Entry Price**: $2.60652179
- **Current Value**: ~$19.81
- **Unrealized P&L**: +$0.0492 (+0.25%)
- **Stop Loss**: NONE ❌
- **Status**: From 12:37 entry, SL placement failed

### Position 3: BTCUSD
- **Size**: 0.00002388 BTC
- **Entry Price**: $90,850.03
- **Current Value**: ~$2.17
- **Unrealized P&L**: -$0.00096 (-0.04%)
- **Stop Loss**: NONE ❌
- **Is Dust**: TRUE (worthless position)

### Position 4: DOGEUSD
- **Size**: 0.06361181 DOGE
- **Entry Price**: $0.13993
- **Current Value**: ~$0.009
- **Unrealized P&L**: -$0.0001 (-1.15%)
- **Stop Loss**: NONE ❌
- **Is Dust**: TRUE (below minimum tradeable size)

**Total Tracked Value**: ~$65.53
**Total Unrealized P&L**: +$0.045 (+0.07%)

---

## THE 4 PHANTOM POSITIONS

The guard system sees **8 open positions** but only 4 are tracked. This means there are **4 additional positions** created that the bot can't manage.

### Likely Sources of Phantom Positions

Based on recent crashes, these are probably:

1. **ATOMUSD #2**: From 13:05:40 crash
   - Order ID: 2c7b0c64-32e8-4ea7-b5e0-c1ec82618ce2
   - Intended: $62.33 worth (~24 ATOM)
   - Status: UNKNOWN (crashed after order placed)

2. **SOLUSD #2**: From 13:05:47 crash
   - Order ID: 304d11af-c8e8-4e1e-9fe7-bc44f5ff380f
   - Intended: $3.13 worth (~0.02 SOL)
   - Status: UNKNOWN (crashed after order placed)

3. **BTCUSD #2**: From 13:00:47 crash
   - Status: UNKNOWN

4. **Unknown Position**: Possibly from earlier crash or API inconsistency

**Problem**: These positions exist in the exchange but the bot's tracking system doesn't know about them because it crashed during creation.

---

## RECENT FAILED ENTRY ATTEMPTS (Last 10 Minutes)

### 13:05:40 - ATOMUSD Entry
```
Placed buy market order 2c7b0c64-32e8-4ea7-b5e0-c1ec82618ce2 for 62.329499999999996 ATOM/USD
Waiting for ATOM/USD settlement (up to 10s)...
Entry failed: 'CCXTExchangeBroker' object has no attribute '_get_base_currency'
```
**Result**: Order placed, bot crashed, no stop loss, position orphaned

### 13:05:47 - SOLUSD Entry
```
Placed buy market order 304d11af-c8e8-4e1e-9fe7-bc44f5ff380f for 3.135 SOL/USD
Waiting for SOL/USD settlement (up to 10s)...
Entry failed: 'CCXTExchangeBroker' object has no attribute '_get_base_currency'
```
**Result**: Order placed, bot crashed, no stop loss, position orphaned

### 13:06:02 - POLUSD Blocked
```
Capping position size at safe balance limit: $20.00 -> $0.17 (Cap=$0.18)
Skipping entry for POLUSD: Calculated size $0.17 < Min $1.1 (Capital=$0.18)
```
**Result**: No capital available for new trades

### 13:06:09 - NEARUSD Blocked
```
Skipping entry for NEARUSD: Calculated size $0.17 < Min $1.1 (Capital=$0.18)
```
**Result**: No capital available

### 13:06:17 - DOTUSD Blocked
```
Skipping entry for DOTUSD: Calculated size $0.17 < Min $1.1 (Capital=$0.18)
```
**Result**: No capital available

---

## CAPITAL STATUS

**Total Portfolio Value**: Estimated ~$130-150 (if all phantom positions filled)
**Available USD**: $0.18
**Locked in Positions**: ~$130-150
**Utilization**: 99.9%

**Problem**: Capital is completely fragmented across 8+ positions, most of which are dust or partial fills. Bot can't consolidate or make new trades.

---

## WHY THE BOT CAN'T SEE ALL POSITIONS

The bot's position tracking system relies on:
1. Successful order placement
2. Settlement confirmation
3. Recording position data

When the bot crashes AFTER placing an order but BEFORE confirming settlement:
- Exchange fills the order (partially or fully)
- Bot never records the position
- Position becomes "orphaned" - exists but isn't tracked
- Guard system sees it (via exchange API) but trading logic doesn't

**This is why**:
- Holdings snapshot shows 4 positions
- Guard system blocks trades citing 8 positions

---

## GUARD SYSTEM BLOCKING TRADES

Recent blocking messages:
```
13:05:54 [GUARD] Blocked new entry on ADAUSD: max_concurrent_positions=5 reached (open=8 pending=0)
13:06:30 [GUARD] Blocked new entry on DOGEUSD: max_concurrent_positions=5 reached (open=8 pending=0)
```

The guard system queries the exchange directly and sees all 8 positions, while the bot's internal tracking only knows about 4.

**Config Setting**: `max_concurrent_positions=5`
**Actual Positions**: 8
**Result**: All new trades blocked

---

## EMERGENCY RECOVERY NEEDED

### Option 1: Flatten ALL Positions (Recommended)

Create a script that queries the exchange directly and closes EVERYTHING:

```python
# tools/emergency_flatten_everything.py
import ccxt
import os

exchange = ccxt.coinbase({
    'apiKey': os.getenv('COINBASE_API_KEY'),
    'secret': os.getenv('COINBASE_API_SECRET'),
})

# Get ALL balances directly from exchange
balance = exchange.fetch_balance()

print("=== FLATTENING ALL POSITIONS ===\n")

# List of all possible crypto holdings
for currency in balance['total'].keys():
    if currency == 'USD':
        continue

    amount = balance['total'].get(currency, 0)

    if amount <= 0:
        continue

    symbol = f"{currency}/USD"

    try:
        print(f"Closing {symbol}: {amount} units...")
        order = exchange.create_market_sell_order(symbol, amount)
        print(f"  ✅ Order placed: {order['id']}")
    except Exception as e:
        print(f"  ❌ Failed: {e}")

# Check final balance
final = exchange.fetch_balance()
print(f"\n=== FINAL STATE ===")
print(f"USD Balance: ${final['total'].get('USD', 0):.2f}")

# Show any remaining positions
print("\nRemaining positions:")
for currency, amount in final['total'].items():
    if currency != 'USD' and amount > 0:
        print(f"  {currency}: {amount}")
```

### Option 2: Manually Check and Close Positions

User can log into Coinbase Advanced Trade and manually close all positions to start fresh.

---

## ROOT CAUSE CHAIN

1. **Original Bug**: `_is_future` attribute missing
2. **Gemini's Fix**: Added settlement wait logic
3. **New Bug**: Called non-existent `_get_base_currency()` method
4. **Result**: Bot crashes after placing orders
5. **Effect**: Orders partially fill, positions orphaned
6. **Cascade**: Capital fragments, bot paralyzed

---

## NEXT STEPS FOR GEMINI

1. **STOP THE BOT** - It's creating more broken positions every cycle
2. **Flatten all positions** - Use emergency script or manual close
3. **Fix `_get_base_currency` bug** - Add the method definition
4. **Test the fix** - Verify settlement logic works
5. **Restart with clean slate** - Fresh capital, no positions
6. **Monitor FIRST trade** - Ensure complete cycle works (entry + SL)

---

## COMPARISON: Expected vs Actual State

### Expected (Healthy Bot):
- 1-2 positions at a time
- Each position has stop loss
- Capital cycles through trades
- Positions close and free capital
- Clean tracking

### Actual (Current State):
- 8 positions (4 tracked + 4 phantom)
- ZERO stop losses
- Capital 99.9% locked
- Can't make new trades
- Confused tracking

---

## TESTING REQUIREMENTS AFTER FIX

1. Flatten ALL positions
2. Verify $65-150 USD available
3. Fix `_get_base_currency` bug
4. Restart bot
5. Watch for FIRST trade:
   - Entry order placed ✅
   - Settlement wait ✅
   - Base currency detected ✅
   - Stop loss placed ✅
   - Position tracked correctly ✅

If ANY step fails → STOP and debug that specific step.

---

## FILES REFERENCED

- Bot logs: `logs/tradebot.log`
- Broker code: `src/tradebot_sci/broker/ccxt_broker.py` (contains bug)
- Emergency flatten script: `tools/emergency_flatten_everything.py` (create this)

---

## BOTTOM LINE

The bot is **completely non-functional** due to:
1. New `_get_base_currency` bug crashing all entries
2. 8 positions (4 tracked + 4 phantom) locking up capital
3. Guard system blocking new trades
4. No stop losses on ANY position

**Gemini needs to flatten everything and start over with a proper fix.**
