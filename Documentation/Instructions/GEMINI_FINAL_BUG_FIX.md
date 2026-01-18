# GEMINI: FINAL BUG TO FIX - NoneType Error

**Date**: 2026-01-11 13:41
**Status**: ONE LAST BUG IN SETTLEMENT LOGIC

---

## GOOD NEWS ✅

1. **Positions flattened**: $64.71 USD available (clean slate achieved!)
2. **Bot restarted**: Running with PID 289289
3. **No phantom positions**: Guard system working correctly
4. **`_get_base_currency` fixed**: That bug is gone

---

## BAD NEWS ❌

**First trade attempt FAILED** with a new error:

```
[CCXT] Placed buy market order 2e97ddb9-4a38-43f4-838a-085abdc334d1 for 61.47 POL/USD
[CCXT] Waiting for POL/USD settlement (up to 10s)...
[ERROR] Entry failed: float() argument must be a string or a real number, not 'NoneType'
```

**What happened**:
1. Bot placed POL entry order ($61.47) ✅
2. Started waiting for settlement ✅
3. Crashed with NoneType error ❌
4. POL position orphaned (again!) ❌

---

## THE BUG LOCATION

**File**: `src/tradebot_sci/broker/ccxt_broker.py`
**Section**: Settlement wait logic (the code you added to fix the previous bug)

**The error occurs** right after the "Waiting for settlement" message.

**What's happening**: The code is trying to convert `None` to a `float`, which fails.

---

## LIKELY CAUSE

In the settlement wait code, you're probably doing something like:

```python
# After: logger.info(f"Waiting for {symbol} settlement (up to 10s)...")
base_currency = symbol.split('/')[0]

# Then checking balance
for attempt in range(20):
    balance = self._exchange.fetch_balance()
    filled_amount = balance['free'].get(base_currency, 0)

    # THIS LINE PROBABLY CRASHES:
    required_amount = float(order['filled'])  # <-- order['filled'] is None!

    if filled_amount >= required_amount:
        break
    time.sleep(0.5)
```

**Problem**: `order['filled']` might be `None` or missing if the order just placed.

---

## THE FIX

You need to handle the case where the order info might not have the filled amount yet.

**Option 1**: Use the amount you SENT, not what was filled:

```python
# You already know the amount from the order you placed
required_amount = float(amount)  # Use the original amount variable
```

**Option 2**: Wait and retry if filled is None:

```python
for attempt in range(20):
    balance = self._exchange.fetch_balance()
    filled_amount = balance['free'].get(base_currency, 0)

    # Fetch order status to get filled amount
    try:
        order_status = self._exchange.fetch_order(order_id, symbol)
        filled = order_status.get('filled', None)

        if filled is None:
            # Order not filled yet, keep waiting
            time.sleep(0.5)
            continue

        required_amount = float(filled)

        if filled_amount >= required_amount * 0.95:  # 95% threshold
            break
    except Exception as e:
        logger.warning(f"Could not fetch order status: {e}")

    time.sleep(0.5)
```

**Option 3**: Simplest - just wait a fixed time:

```python
# After placing order:
logger.info(f"Waiting 3s for {symbol} settlement...")
time.sleep(3)  # Simple fixed delay
# Then place stop loss
```

---

## WHAT YOU NEED TO DO NOW

### STEP 1: Find the Settlement Wait Code

**Search for this**:
```bash
grep -n "Waiting for.*settlement" src/tradebot_sci/broker/ccxt_broker.py
```

**You'll find the line number** where the settlement wait starts.

### STEP 2: Look at the Next Few Lines

After the "Waiting for settlement" log, there's code that's trying to:
1. Get base currency from symbol ✅ (this works now)
2. Check balance
3. Convert something to float that's None

**Find the line** that has `float(...)` and is getting None.

### STEP 3: Fix It

**Easiest fix** - Replace the complex settlement logic with simple delay:

```python
# After: Placed buy market order...
logger.info(f"Waiting 3s for settlement...")
time.sleep(3)

# Then continue to stop loss placement
```

**OR** use the original `amount` variable instead of `order['filled']`:

```python
# You already have 'amount' from earlier in the function
required_amount = float(amount)  # Don't use order['filled']!
```

### STEP 4: Restart Bot

**Stop**:
```bash
pkill -f tradebot
```

**Start**:
```bash
./tradebot.sh --continuous &
```

### STEP 5: Watch for First Trade

**Monitor logs**:
```bash
tail -f logs/tradebot.log | grep -E "(Placed.*order|Stop Loss|ERROR|Entry failed)"
```

**Expected output**:
```
[CCXT] Placed buy market order [ID] for [amount]
[CCXT] Waiting 3s for settlement...
[CCXT] Coinbase SL placed: [ID]  <-- THIS SHOULD APPEAR!
```

**If you see "Entry failed" again** → Show me the EXACT error message

---

## CURRENT BOT STATE

**Balance**: $64.71 USD
**Positions**: POL position from failed order (orphaned, no stop loss)

**Estimated POL amount**: ~364 POL tokens ($61.47 / $0.1688 = 364 POL)

**Risk**: This position has NO STOP LOSS. You need to:
1. Fix the bug
2. Restart bot
3. Let bot manage the POL position properly OR
4. Manually close POL first, then restart

---

## DECISION NEEDED

**Option A**: Close the orphaned POL position first
```bash
python tools/emergency_flatten_all.py
# Type: YES
# Then restart bot
```

**Option B**: Let the bot manage it after fixing the bug
- Fix the settlement bug
- Restart bot
- Bot will detect POL position and manage it

**I recommend Option A** - flatten POL, then restart with clean $64 USD.

---

## KILL-SWITCH ACTIVATED

The logs show:
```
[EXEC] AVAXUSD outcome=blocked_guard reason=kill-switch
[EXEC] DOTUSD outcome=blocked_guard reason=kill-switch
```

**What this means**: After the failed POL trade, the bot activated a "kill-switch" to prevent more failed trades.

**This is GOOD** - it prevents the bot from creating more orphaned positions.

**After you fix the bug** and restart, the kill-switch will reset.

---

## BOTTOM LINE

You're **99% there**! Just ONE more bug to fix in the settlement wait logic.

**The bug**: Trying to convert `None` to `float` when checking if order filled.

**The fix**: Either use simple `time.sleep(3)` OR use the original `amount` variable instead of `order['filled']`.

**Then**: Restart and watch for first COMPLETE trade cycle (entry + stop loss).

---

## SUCCESS CRITERIA

✅ Entry order places
✅ Settlement wait completes without error
✅ Stop loss places successfully
✅ Position tracked correctly
✅ No "Entry failed" errors
✅ Trade cycle completes (entry → monitor → exit)

**When ALL above are ✅, the bot is FULLY WORKING.**
