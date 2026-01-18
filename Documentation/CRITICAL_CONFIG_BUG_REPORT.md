# CRITICAL: Config Not Loading + Phantom Position Bug

**Date:** January 9, 2026 05:20 EST
**Severity:** CRITICAL - Blocking ALL trades despite correct YAML configuration

---

## Issue #9: Config Not Loading from Profile (CRITICAL)

### Evidence

**YAML Config (settings_profiles.yaml:37):**
```yaml
intraday:
  multi_position_enabled: true  # ← User set this to true
```

**Log Output (05:18:06-05:18:17 EST):**
```
[GUARD] Blocked new entry on POLUSD: existing position(s) on DOGEUSDT (multi_position_enabled=false)
[GUARD] Blocked new entry on SOLUSDT: existing position(s) on DOGEUSDT (multi_position_enabled=false)
[GUARD] Blocked new entry on XRPUSDT: existing position(s) on DOGEUSDT (multi_position_enabled=false)
```

**Code (models.py:532-533):**
```python
multi_position_enabled: bool = Field(
    default=False,  # ← Hardcoded default overrides YAML!
```

### Root Cause

The Python Pydantic model has `default=False` hardcoded. The config loader is not properly overriding this default with the YAML value `true` from the profile.

**Why This Happens:**
- Profile YAML says `multi_position_enabled: true`
- Python model has `default=False`
- Config loader fails to merge profile value into runtime config
- Bot uses hardcoded default instead of YAML value

**Impact:**
- Bot is in single-position mode despite user setting `multi_position_enabled: true`
- Limits to 1 position at a time (user wants 10+ trades/day across 13 symbols)
- Even after restarting bot, config still shows `false` in logs

### Where Config Is Read

**Line 879-880 in runtime/loop.py:**
```python
runtime = getattr(executor, "runtime", None) if executor else None
multi_enabled = bool(getattr(runtime, "multi_position_enabled", False))
```

**Problem:** `executor.runtime.multi_position_enabled` is returning `False` instead of `true`.

### Investigation Needed

1. **Check config loader** (config/loader.py):
   - How does it merge profile YAML into runtime object?
   - Is `multi_position_enabled` field being skipped?
   - Are profile settings properly overlaying base settings?

2. **Check runtime initialization**:
   - Where is `executor.runtime` object created?
   - Does it use the loaded profile config?
   - Is there a separate code path that bypasses profile loading?

3. **Verify profile loading**:
   - Add logging to show which profile is loaded
   - Add logging to show `multi_position_enabled` value after loading
   - Confirm profile merge is happening at all

### Fix Required

**Option 1: Fix config loader to properly merge profile values**
```python
# In config/loader.py (approximate location)
def load_profile(profile_name):
    base_config = load_base_config()
    profile_config = load_profile_yaml(profile_name)

    # Ensure profile values override base/model defaults
    merged_config = {**base_config, **profile_config}

    # IMPORTANT: Explicitly set fields from profile
    runtime.multi_position_enabled = merged_config.get("multi_position_enabled", False)
```

**Option 2: Change model default to True**
```python
# In config/models.py:532-533
multi_position_enabled: bool = Field(
    default=True,  # Change from False to True
```
**Note:** Option 2 is a workaround, not a real fix. Option 1 is correct solution.

---

## Issue #8: Phantom Position Bug (Still Active)

### Evidence (Same Timestamp!)

```
2026-01-09 05:18:09 [INFO] - [GUARD] Blocked new entry on XRPUSDT: existing position(s) on DOGEUSDT
2026-01-09 05:18:09 [INFO] - [STATE] DOGEUSDT open_position: none
```

### Root Cause

**Code (runtime/loop.py:889):**
```python
open_position_symbols = set(executor.list_open_position_symbols() or [])
```

`executor.list_open_position_symbols()` returns DOGEUSDT, but `executor._fetch_symbol_state("DOGEUSDT")` shows `open_position: none`.

**Why This Happens:**
- `list_open_position_symbols()` uses **cached** position list
- `_fetch_symbol_state()` queries **fresh** broker state
- Cache is stale - position was closed but cache not updated
- Guard uses cached list, state logging uses fresh query

### Fix Required

**Refresh position list before guard check:**
```python
# In runtime/loop.py around line 886-889
open_position_symbols: set[str] = set()
if executor and hasattr(executor, "list_open_position_symbols"):
    try:
        # [FIX] Refresh position cache before reading
        if hasattr(executor, "refresh_positions"):
            executor.refresh_positions()

        open_position_symbols = set(executor.list_open_position_symbols() or [])
    except Exception:
        open_position_symbols = set()
```

**OR verify each position individually:**
```python
# Alternative fix - verify positions are actually open
open_position_symbols: set[str] = set()
if executor and hasattr(executor, "list_open_position_symbols"):
    try:
        cached_symbols = executor.list_open_position_symbols() or []

        # [FIX] Verify each position actually exists
        for sym in cached_symbols:
            state = executor._fetch_symbol_state(sym)
            if state and abs(state.get("position_shares", 0)) > 0:
                open_position_symbols.add(sym)

    except Exception:
        open_position_symbols = set()
```

---

## Impact Summary

**With Both Bugs Active:**
- Config shows `multi_position_enabled=false` (should be `true`)
- Guard blocks all new entries citing "existing position on DOGEUSDT"
- DOGEUSDT has no actual position (`open_position: none`)
- **Result: ZERO trades possible**

**After Config Bug Fixed:**
- Bot would allow multi-position trading
- But phantom position bug would still block some entries
- **Estimated impact: 3-5 trades blocked per cycle**

**After Both Bugs Fixed:**
- Multi-position mode active
- No false position blocks
- **Estimated trades: 8-12/day** (still need to fix other gates)

---

## Action Items

1. **CRITICAL: Fix config loading bug**
   - Investigate config/loader.py
   - Ensure profile YAML values override model defaults
   - Add logging to confirm values loaded correctly

2. **CRITICAL: Fix phantom position bug**
   - Refresh position cache before guard check
   - OR verify each cached position individually
   - Add debug logging for position list vs state

3. **Add verification logging:**
   ```python
   logger.info(f"[CONFIG] multi_position_enabled={multi_enabled} (from runtime)")
   logger.info(f"[GUARD_DEBUG] Cached positions: {open_position_symbols}")
   for sym in open_position_symbols:
       state = executor._fetch_symbol_state(sym)
       shares = state.get("position_shares", 0) if state else 0
       logger.info(f"[GUARD_DEBUG] {sym} verified shares: {shares}")
   ```

4. **Test after fixes:**
   - Restart bot
   - Confirm logs show `multi_position_enabled=true`
   - Confirm no phantom DOGEUSDT blocks
   - Monitor for actual trades

---

**Prepared By:** Claude (AI Assistant)
**Date:** January 9, 2026 05:20 EST
**Status:** ❌ **2 CRITICAL BUGS** preventing all trades (config + phantom position)
**Priority:** IMMEDIATE - These bugs make bot completely non-functional
