# GEMINI: FIX PHANTOM POSITIONS BLOCKING BOT

**Date**: 2026-01-11 13:52  
**Status**: URGENT - BOT CANNOT TRADE  
**Priority**: CRITICAL  

---

## THE PROBLEM

Your bot is **completely blocked** from making new trades because of phantom positions.

**Error in logs**:
```
[GUARD] Blocked new entry on LINKUSD: max_concurrent_positions=5 reached (open=8 pending=0)
```

The bot thinks it has 8 open positions, but **7 of them are phantoms** with `size=0.0`.

---

## WHY THIS HAPPENED

When you flattened positions earlier, the code set `size=0.0` but **did not delete** the entries from `position_holds.json`.

**Current position_holds.json** has 8 entries:
```json
[
  {"symbol": "BTCUSD", "size": 0.0},      // ← PHANTOM (delete this!)
  {"symbol": "ETHUSD", "size": 0.0},      // ← PHANTOM (delete this!)
  {"symbol": "SOLUSD", "size": 0.00643047}, // ← Real position
  {"symbol": "DOGEUSD", "size": 0.06361181}, // ← Dust position
  {"symbol": "XRPUSD", "size": 0.0},      // ← PHANTOM (delete this!)
  {"symbol": "POLUSD", "size": 0.0},      // ← PHANTOM (delete this!)
  {"symbol": "NEARUSD", "size": 0.0},     // ← PHANTOM (delete this!)
  {"symbol": "DOTUSD", "size": 0.0},      // ← PHANTOM (delete this!)
  {"symbol": "ATOMUSD", "size": 0.0}      // ← PHANTOM (delete this!)
]
```

The guard system counts ALL 8 entries → blocks trades because max=5.

---

## ⚠️ GEMINI: DO THIS RIGHT NOW ⚠️

You need to do TWO things:

### STEP 1: Clean Up Phantom Positions (Immediate Fix)

**Manual cleanup** - Edit `data/position_holds.json`:

1. Open the file: `data/position_holds.json`
2. **Delete all entries with `size=0.0`**
3. Keep only entries with `size > 0`
4. Save the file

**After cleanup, the file should look like**:
```json
[
  {
    "symbol": "SOLUSD",
    "opened_at": "2026-01-11T18:48:45.370332+00:00",
    "stop_loss": null,
    "entry_price": 139.61,
    "take_profit": null,
    "size": 0.00643047,
    "schema_version": 1
  },
  {
    "symbol": "DOGEUSD",
    "opened_at": "2026-01-11T18:44:44.660356+00:00",
    "stop_loss": null,
    "entry_price": 0.13837,
    "take_profit": null,
    "size": 0.06361181,
    "schema_version": 1
  }
]
```

**Only 2 entries** (both with size > 0).

5. **Restart the bot**:
```bash
pkill -f tradebot
./tradebot.sh --continuous &
```

6. **Verify it worked**:
```bash
tail -f logs/tradebot.log | grep -E "(GUARD|Blocked|outcome=)"
```

You should see trades going through, NOT "Blocked" messages.

---

### STEP 2: Fix the Code (Permanent Solution)

**The bug**: The guard system counts ALL position_holds.json entries, including zeros.

**Find the guard code**:
```bash
grep -rn "max_concurrent_positions" src/
```

Look for code that counts positions, probably something like:
```python
def count_open_positions(self):
    positions = load_position_holds()
    return len(positions)  # ← BUG: counts zero-size entries!
```

**Fix it to filter out zeros**:
```python
def count_open_positions(self):
    positions = load_position_holds()
    # Only count positions with actual size
    return len([p for p in positions if p.get('size', 0) > 0])
```

**OR** find where positions are closed and make sure to **DELETE** the entry instead of setting size=0:

```python
# When closing a position, DELETE the entry:
def close_position(self, symbol):
    # ... close the trade on exchange ...
    
    # Remove from position_holds.json (don't just set size=0!)
    positions = load_position_holds()
    positions = [p for p in positions if p['symbol'] != symbol]
    save_position_holds(positions)
```

---

## VERIFICATION STEPS

After Step 1 (manual cleanup):

1. **Check position count**:
```bash
cat data/position_holds.json | grep '"symbol"' | wc -l
```
Should show **2** (not 8)

2. **Check for phantoms**:
```bash
cat data/position_holds.json | grep '"size": 0.0'
```
Should show **nothing** (no results)

3. **Watch for trades**:
```bash
tail -f logs/tradebot.log | grep outcome=
```
You should see `outcome=success_submitted` when good setups appear, NOT "Blocked" messages.

---

## SUCCESS CRITERIA

✅ position_holds.json has only 2 entries  
✅ No entries with size=0.0  
✅ Bot logs show trades executing (not blocked)  
✅ Guard allows new positions  
✅ No "max_concurrent_positions reached" errors  

---

## WHAT CLAUDE FOUND

**Good news**:
- ✅ Your NoneType settlement bug is FIXED! (Great job!)
- ✅ First successful complete trade cycle worked
- ✅ Stop loss placement works perfectly

**Bad news**:
- ❌ Phantom positions blocking all new trades
- ❌ Bot cannot execute strategy (blocked by guard)

**The NoneType fix worked perfectly!** But the phantom position bug is preventing the bot from trading.

---

## ADDITIONAL ISSUES TO INVESTIGATE

After you fix the phantom positions, Claude found two more things to check:

1. **Position size tracking mismatch**:
   - Stop loss placed for 0.431 SOL (correct!)
   - But runtime tracking shows 0.006 SOL (wrong!)
   - Check how `fetch_balance()` is being used

2. **Duplicate SOL trades**:
   - Bot entered SOL at 13:46:28 (SL=0.4312 SOL)
   - Bot entered SOL AGAIN at 13:48:09 (SL=0.02158 SOL)
   - Why did it enter twice?

But **fix the phantom positions FIRST** - those are blocking everything!

---

## BOTTOM LINE

**Right now**: Bot cannot trade (blocked by phantoms)

**After Step 1**: Bot can trade again (manual cleanup)

**After Step 2**: Bug permanently fixed (code fix)

**Time estimate**: 5 minutes for Step 1, 10 minutes for Step 2

**Just do Step 1 immediately** to unblock the bot, then do Step 2 properly when you have time.

The bot is ready to trade once you delete those 7 phantom entries!
