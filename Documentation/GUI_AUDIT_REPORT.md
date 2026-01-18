# GUI Orders Pane Audit Report
**Date:** January 8, 2026 (19:20 EST)
**Scope:** Verify AI's implementation of Orders pane revamp

---

## User Requirements

### Requirement #1: Multi-Line Status Bar for Holdings
**User Request:** "Each crypto needs to be on a separate line. You don't understand that?"

**Expected:**
```
BTC - 0.45000000
DOGE - 100.00000000
Orders: 2
```

**NOT:**
```
BTC - 0.45000000, DOGE - 100.00000000 | Orders: 2
```

### Requirement #2: Holdings Table (CCXT Mode)
**User Request:** "In CCXT mode, you need to change the columns too. Make them sortable and expandable"

**Expected:**
- Columns should be **CHANGED** for CCXT mode (different columns than IBKR)
- Columns should be **sortable** (click header to sort)
- Columns should be **resizable** (drag dividers to expand/shrink)

### Requirement #3: NO Orders Count Display
**User Request:** "You don't need to even say how many orders"

**Expected:**
- Status bar should NOT display "Orders: 2" or any order count

---

## Audit Findings

### ✅ PASS: Multi-Line Status Bar Implementation

**Code Location:** `app.py:1860-1863` (Initialization)
```python
# [ANTIGRAVITY FIX] Add permanent multi-line widget for holdings status
self._status_holdings_label = QtWidgets.QLabel("")
self._status_holdings_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
self._status_holdings_label.setStyleSheet("QLabel { color: #cccccc; font-weight: bold; margin-right: 10px; }")
self.statusBar().addPermanentWidget(self._status_holdings_label)
```

**Code Location:** `app.py:6301-6308` (Update Logic)
```python
# [ANTIGRAVITY FIX] Update permanent status label with holdings
# We use newlines to separate each holding as requested
if self._ibkr_last_status:
     # Replace " | " with "\n" if it came from our formatted string
     # But our previous edit used " | ". We can just split and rejoin.
     parts = self._ibkr_last_status.split(" | ")
     txt = "\n".join(parts)
     self._status_holdings_label.setText(txt)
else:
     self._status_holdings_label.setText("")
```

**Data Source:** `app.py:1452-1466` (IbkrAccountFetcher - CCXT Mode)
```python
# Build minimal status string
# "BTC - 0.45..., | DOGE - 100... | Orders: 2"
parts = []
if pos_summary_parts:
    parts.extend(pos_summary_parts) # Each holding is a part

if ccxt_orders:
    parts.append(f"Orders: {len(ccxt_orders)}")

self._last_status = " | ".join(parts)
```

**Analysis:**
- ✅ Creates separate status label widget
- ✅ Uses `" | "` as separator in data source
- ✅ Splits by `" | "` and joins with `"\n"` for display
- ✅ Result: Each crypto on separate line as requested

**Example Output:**
```
BTC - 0.45000000
DOGE - 100.00000000
Orders: 2
```

---

### ❌ FAIL: Holdings Table Columns NOT Changed for CCXT Mode

**User Request:** "In CCXT mode, you need to change the columns too. Make them sortable and expandable"

**Code Location:** `orders_panel.py:92-95` (Orders Table Columns)
```python
table = QtWidgets.QTableWidget(0, 10, self)
table.setHorizontalHeaderLabels(
    ["Time", "Symbol", "ID", "Side", "Qty", "Type", "TIF", "Status", "Filled", "Avg"]
)  # ← These are IBKR columns, NOT changed for CCXT mode
```

**Analysis:**
- ❌ **COLUMNS NOT CHANGED** - Still shows IBKR columns: `["Time", "Symbol", "ID", "Side", "Qty", "Type", "TIF", "Status", "Filled", "Avg"]`
- ❌ User explicitly said: "I also asked it to change the columns! Not just make them sortable and draggable!"
- ❌ AI only made columns sortable/resizable but did NOT change the columns themselves for CCXT mode

**What the AI Did:**
- ✅ Made columns sortable (`setSortingEnabled(True)`)
- ✅ Made columns resizable (`Interactive` resize mode)
- ❌ **Did NOT change the column headers** for CCXT mode

**Code Location:** `app.py:1826-1836` (Holdings Table - Sortable/Resizable)
```python
self._holdings_table.setSortingEnabled(True)
hhdr = self._holdings_table.horizontalHeader()
hhdr.setStretchLastSection(True) # Stretch last section to fill
hhdr.setSectionResizeMode(QtWidgets.QHeaderView.Interactive) # Allow user resize
```

**Verdict:** ❌ **FAILED** - AI misunderstood requirement. User wanted:
1. CHANGE the columns (different column headers for CCXT)
2. Make them sortable
3. Make them resizable

AI only did #2 and #3, NOT #1.

---

### ❌ PARTIAL FAIL: Decimal Precision Display

**User Request:** "Just SHOW the crypto and SHOW how much we're holding. Easy!"

**Code Location:** `app.py:1454-1455`
```python
# User requested full decimals ("Show them all")
s_qty = f"{qty:.8f}".rstrip("0").rstrip(".")
pos_summary_parts.append(f"{sym.replace('USD','')} - {s_qty}")
```

**Analysis:**
- ✅ Shows 8 decimal places (appropriate for crypto)
- ✅ Strips trailing zeros (e.g., `0.45000000` → `0.45`)
- ⚠️ **ISSUE:** The comment says "Show them all" but code strips trailing zeros
- ⚠️ **CONFLICT:** User said "Show them all" vs code shows cleaned decimals

**Recommendation:**
If user truly wants ALL decimals (including trailing zeros), change to:
```python
s_qty = f"{qty:.8f}"  # Keep all 8 decimals
```

Current behavior: `BTC - 0.45` (cleaned)
User requested: `BTC - 0.45000000` (all decimals)?

**Needs Clarification:** Does user want trailing zeros or cleaned decimals?

---

### ✅ PASS: Symbol Cleanup

**Code Location:** `app.py:1455`
```python
pos_summary_parts.append(f"{sym.replace('USD','')} - {s_qty}")
```

**Example:**
- Input: `BTCUSD`
- Output: `BTC - 0.45`

**Analysis:**
- ✅ Removes "USD" suffix for cleaner display
- ✅ Matches user's example: "BTC - X" not "BTCUSD - X"

---

### ❌ FAIL: Orders Count Should NOT Be Displayed

**User Request:** "You don't need to even say how many orders"

**Code Location:** `app.py:1463-1464`
```python
if ccxt_orders:
    parts.append(f"Orders: {len(ccxt_orders)}")  # ← Should NOT be here
```

**Analysis:**
- ❌ **STILL DISPLAYS ORDER COUNT** - Shows "Orders: 2" in status bar
- ❌ User explicitly said: "Plus, I told it that we don't need it to display how many orders we have"
- ❌ AI ignored this requirement

**Verdict:** ❌ **FAILED** - AI added order count despite user explicitly saying not to

---

## Summary

### Requirements Met: 2/5 (40%)

| Requirement | Status | Notes |
|-------------|--------|-------|
| **Multi-line status bar** | ✅ PASS | Each crypto on separate line |
| **Change columns for CCXT** | ❌ FAIL | Columns NOT changed, only made sortable/resizable |
| **Sortable columns** | ✅ PASS | `setSortingEnabled(True)` |
| **Resizable columns** | ⚠️ PARTIAL | `Interactive` resize mode (but wrong columns) |
| **NO orders count** | ❌ FAIL | Still shows "Orders: 2" |
| **Show crypto + holdings** | ✅ PASS | Format: `BTC - 0.45` |
| **Decimal precision** | ⚠️ UNCLEAR | Strips trailing zeros vs "show all" |

### Overall Assessment: **FAIL**

The AI **misunderstood** your requirements and only completed 2 out of 5 major requirements.

**What the AI Did Right:**
1. ✅ Status bar shows each crypto on a SEPARATE LINE (not comma-separated)
2. ✅ Holdings table is SORTABLE (click headers)
3. ✅ Holdings table is RESIZABLE (drag column dividers)
4. ✅ Clean format: `BTC - 0.45` (not `BTCUSD - 0.45000000`)

**What the AI Did WRONG:**
1. ❌ **DID NOT CHANGE COLUMNS FOR CCXT MODE** - User explicitly asked to "change the columns" but AI only made them sortable/resizable. Columns still show IBKR headers: `["Time", "Symbol", "ID", "Side", "Qty", "Type", "TIF", "Status", "Filled", "Avg"]`
2. ❌ **STILL SHOWS ORDER COUNT** - User explicitly said "You don't need to even say how many orders" but code still displays "Orders: 2" at `app.py:1463-1464`

**Critical Misunderstandings:**
- AI interpreted "change the columns" as "make them sortable/resizable"
- AI ignored the explicit instruction to NOT display order count
- User's exact words: "I also asked it to change the columns! Not just make them sortable and draggable!"

---

## Required Fixes

### Fix #1: Remove Orders Count Display
**File:** [app.py:1463-1464](src/tradebot_sci/gui/app.py#L1463-L1464)
```python
# DELETE these lines:
if ccxt_orders:
    parts.append(f"Orders: {len(ccxt_orders)}")
```

**Expected Result:**
```
BTC - 0.45
DOGE - 100.00
```
NOT:
```
BTC - 0.45
DOGE - 100.00
Orders: 2
```

### Fix #2: Change Columns for CCXT Mode
**File:** [orders_panel.py:92-95](src/tradebot_sci/gui/orders_panel.py#L92-L95)

Current columns (IBKR-specific):
```python
["Time", "Symbol", "ID", "Side", "Qty", "Type", "TIF", "Status", "Filled", "Avg"]
```

**Question:** What should the CCXT columns be?
- Need to determine appropriate column headers for CCXT exchanges
- May need to check CCXT order structure vs IBKR order structure
- Columns should reflect CCXT-specific fields (e.g., exchange-specific order properties)

---

**Audit Prepared By:** Claude (AI Assistant)
**Date:** January 8, 2026 (19:20 EST) - **CORRECTED VERSION**
**Status:** ❌ **FAIL** - 2 critical requirements not met
