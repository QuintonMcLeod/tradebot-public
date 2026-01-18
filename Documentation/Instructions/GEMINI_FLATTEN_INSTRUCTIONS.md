# GEMINI: FLATTEN ALL POSITIONS NOW

**Date**: 2026-01-11 13:10
**For**: Gemini (you must do this EXACTLY as written)

---

## SITUATION

The bot has **8 open positions** (most are dust/broken). Capital is **99.7% locked**. The bot **CANNOT TRADE** in this state.

You need to **CLOSE ALL POSITIONS** and start over with a clean slate.

---

## STEP 1: STOP THE BOT

**EXACTLY THESE COMMANDS**:
```bash
cd "/media/qchan/Steam Games/Scripts/Trade by SCI/tradebot-sci-debug"
pkill -f tradebot
```

**Wait 5 seconds** to make sure it's stopped.

**Check it's stopped**:
```bash
ps aux | grep tradebot
```

If you see any processes, run `pkill -f tradebot` again.

---

## STEP 2: RUN THE FLATTEN SCRIPT

**EXACTLY THESE COMMANDS**:
```bash
cd "/media/qchan/Steam Games/Scripts/Trade by SCI/tradebot-sci-debug"
python tools/emergency_flatten_all.py
```

**What will happen**:
1. Script connects to Coinbase
2. Shows you all current positions
3. Asks you to type 'YES' to confirm
4. **Type exactly: YES** (all caps, no quotes)
5. Script closes all positions
6. Shows final USD balance

**Expected output**:
```
Final USD balance: $130-150
All positions successfully closed!
```

---

## STEP 3: VERIFY EVERYTHING IS CLOSED

**Run this command**:
```bash
python -c "
import ccxt
import os
exchange = ccxt.coinbase({
    'apiKey': os.getenv('COINBASE_API_KEY'),
    'secret': os.getenv('COINBASE_API_SECRET'),
})
balance = exchange.fetch_balance()
print('USD:', balance['total'].get('USD', 0))
for curr, amt in balance['total'].items():
    if curr != 'USD' and amt > 0:
        print(f'{curr}: {amt}')
"
```

**Expected output**:
```
USD: 130-150
```

**If you see ANY other currencies** (SOL, ATOM, BTC, etc.), those are dust. Ignore them if they're worth less than $0.10.

---

## STEP 4: FIX THE `_get_base_currency` BUG

**Location**: `src/tradebot_sci/broker/ccxt_broker.py`

**Search for this EXACT text**:
```python
base_currency = self._get_base_currency(symbol)
```

**Replace with**:
```python
base_currency = symbol.split('/')[0]
```

**DO THIS FOR EVERY OCCURRENCE** you find. There might be 1-3 occurrences.

**Save the file** after making changes.

---

## STEP 5: VERIFY THE FIX

**Run this command to check if you fixed it**:
```bash
grep -n "_get_base_currency" src/tradebot_sci/broker/ccxt_broker.py
```

**Expected output**: NOTHING (empty output means the bug is gone)

**If you see ANY output**, you missed one. Go back to Step 4.

---

## STEP 6: RESTART THE BOT

**EXACTLY THESE COMMANDS**:
```bash
cd "/media/qchan/Steam Games/Scripts/Trade by SCI/tradebot-sci-debug"
./tradebot.sh --continuous &
```

**Wait 10 seconds** for bot to start.

---

## STEP 7: WATCH FOR THE FIRST TRADE

**Open a new terminal and run**:
```bash
tail -f "/media/qchan/Steam Games/Scripts/Trade by SCI/tradebot-sci-debug/logs/tradebot.log" | grep -E "(Placed.*order|Stop Loss|ERROR|Entry failed)"
```

**Wait for the first trade entry.**

**WHAT SHOULD HAPPEN** (in order):
1. `Placed buy market order [ID] for [amount]` ← Entry order placed ✅
2. `Waiting for [SYMBOL] settlement` ← Settlement wait starts ✅
3. `Coinbase SL placed: [ID]` ← Stop loss placed ✅

**IF YOU SEE**:
- `ERROR` → Bug still exists, report the error to user
- `Entry failed` → Bug still exists, report the error to user
- No stop loss message → Bug still exists

**IF EVERYTHING WORKS**:
- Tell user: "First trade completed successfully with stop loss"
- Show the entry and stop loss order IDs

---

## STEP 8: MONITOR FOR 30 MINUTES

**Keep watching the logs** for 30 minutes.

**Count these**:
- Total decisions made
- Trades entered
- Trades that got stop losses
- Any errors

**After 30 minutes**, report to user:
- Number of trades entered
- Number of stop losses placed
- Any errors encountered
- Current position count
- Available USD balance

---

## WHAT NOT TO DO

❌ **DO NOT** restart the bot before flattening positions
❌ **DO NOT** skip the verification steps
❌ **DO NOT** claim you fixed the bug without testing
❌ **DO NOT** run the bot if the verification shows errors
❌ **DO NOT** ask the user to add more money
❌ **DO NOT** place stop losses manually (the bug fix should do it automatically)

---

## IF SOMETHING GOES WRONG

**If flatten script fails**:
1. Show user the error message
2. Ask user to manually close positions via Coinbase website

**If verification shows bug still exists**:
1. DO NOT restart bot
2. Show user the grep output
3. Ask user for help finding the bug

**If first trade fails**:
1. STOP the bot immediately: `pkill -f tradebot`
2. Show user the error from logs
3. DO NOT try to fix it yourself - wait for user guidance

---

## SUCCESS CRITERIA

✅ All positions closed (USD balance = $130-150)
✅ Bug verification shows no `_get_base_currency` references
✅ Bot restarts without errors
✅ First trade completes with entry + stop loss
✅ No error messages in logs
✅ Only 1 position open after first trade

**When all above are ✅, tell user: "Bot is working correctly now."**

---

## FINAL REMINDER

This is a **STEP-BY-STEP CHECKLIST**. Do **EVERY STEP** in **EXACT ORDER**. Do **NOT SKIP** any steps. Do **NOT** improvise. Follow the instructions **EXACTLY AS WRITTEN**.

**START NOW WITH STEP 1.**
