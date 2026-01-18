# GUI Position Display Analysis

**Date:** January 9, 2026 16:13 EST
**Issue:** User reports positions not showing in GUI

---

## How GUI Position Display Works

### Holdings Tab (Separate from Orders)

The GUI has a **separate Holdings tab** (not the Orders panel) that displays positions.

**Code:** [app.py:1840-1853](/home/qchan/Scripts/Trade by SCI/tradebot-sci-debug/src/tradebot_sci/gui/app.py#L1840-L1853)
```python
self._main_tabs.addTab(holdings_inner, "Holdings")
```

**Columns displayed:**
- Symbol
- Side (long/short)
- Size
- Avg Price
- Current Price
- P&L $
- P&L %
- Stop Loss
- Take Profit
- Working Orders
- Hold Age
- Status

---

## How Holdings Get Updated

### Step 1: Bot Logs [HOLDINGS] Line

**Backend:** Bot writes holdings to log every cycle
**Example:**
```
[HOLDINGS] {"count": 3, "positions": [
    {"symbol": "XRPUSDT", "size": 4.524525, "side": "long", ...},
    {"symbol": "DOGEUSDT", "size": 0.02220808, "side": "long", ...},
    {"symbol": "ADAUSDT", "size": 100.75, "side": "long", ...}
]}
```

### Step 2: GUI Parses Log Line

**Code:** [app.py:6006-6014](/home/qchan/Scripts/Trade by SCI/tradebot-sci-debug/src/tradebot_sci/gui/app.py#L6006-L6014)
```python
def _on_log_line(self, line: str, state: UiState) -> None:
    if "[HOLDINGS]" in line:
        try:
            payload = line.split("[HOLDINGS]", 1)[1].strip()
            data = json.loads(payload) if payload else {}
            positions = list(data.get("positions") or [])
            out: list[dict[str, Any]] = []
            for p in positions:
                if isinstance(p, dict):
                    out.append(p)
            self._holdings = out  # ← Updates internal holdings list
            self._holdings_updated_ts = _now_epoch()
```

### Step 3: GUI Renders Holdings Table

**Code:** [app.py:6054-6312](/home/qchan/Scripts/Trade by SCI/tradebot-sci-debug/src/tradebot_sci/gui/app.py#L6054-L6312)
```python
def _render_holdings(self) -> None:
    # Uses self._holdings to populate the Holdings table
    # Called from _render_right() -> statusBar update
```

---

## Expected Behavior

When bot has positions:
1. ✅ Bot logs: `[HOLDINGS] {"count": 3, "positions": [...]}`
2. ✅ GUI parses holdings from log
3. ✅ GUI updates `self._holdings` list
4. ✅ GUI calls `_render_holdings()`
5. ✅ Holdings table displays all positions

---

## Current Status

### Backend (Bot) - ✅ WORKING
- ✅ Position tracking fixed (min_amount bug resolved)
- ✅ Logs show: `[HOLDINGS] {"count": 3, "positions": [...]}`
- ✅ XRP, DOGE, ADA positions all tracked

### Frontend (GUI) - Need to Verify

**Question for user:** Are you looking at the **Holdings tab** or the **Orders tab**?

- **Holdings tab** = Shows open positions (XRP, DOGE, ADA)
- **Orders tab** = Shows recent orders (buy/sell executions)

**Positions should appear in the Holdings tab, not Orders tab.**

---

## Testing GUI Display

### Test 1: Check if Holdings Tab Exists
Look for tabs at top of GUI:
- Candles
- Decisions
- Structure
- Log
- **Holdings** ← This tab should show positions
- Orders
- Commentary

### Test 2: Verify [HOLDINGS] in Log
```bash
tail -20 logs/tradebot.log | grep HOLDINGS
```

Expected:
```
[HOLDINGS] {"count": 1, "positions": [{"symbol": "DOGEUSDT", "size": 0.022, ...}]}
```

### Test 3: Check Holdings Tab Content
1. Open GUI
2. Click "Holdings" tab (not "Orders")
3. Should see table with DOGE position (0.022 DOGE)

---

## Possible Issues

### Issue 1: User Looking at Wrong Tab
- **Symptoms:** "Orders pane doesn't show positions"
- **Cause:** Positions are in Holdings tab, not Orders tab
- **Fix:** Click Holdings tab instead of Orders tab

### Issue 2: GUI Not Parsing [HOLDINGS]
- **Symptoms:** Holdings tab empty despite log showing positions
- **Cause:** Parse error or exception in _on_log_line
- **Debug:** Check if exception is being silently caught

### Issue 3: _render_holdings() Not Being Called
- **Symptoms:** _holdings list updated but table not refreshing
- **Cause:** Render not triggered
- **Debug:** Add logging to _render_holdings()

---

## Next Steps

**User needs to clarify:**
1. Are you checking the **Holdings** tab or **Orders** tab?
2. Does the Holdings tab exist in your GUI?
3. Is the Holdings tab empty or does it show something?

**If Holdings tab is empty despite [HOLDINGS] logs:**
- Need to debug _on_log_line() parsing
- Check for exceptions in log
- Verify _render_holdings() is being called

---

**Prepared By:** Claude (AI Assistant)
**Date:** January 9, 2026 16:13 EST
**Status:** ⚠️ Need user clarification on which tab they're checking
