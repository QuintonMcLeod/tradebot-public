# Additional Configuration Conflicts - ChatGPT Analysis
## Date: 2026-01-07

This document contains additional conflicts identified by ChatGPT that were not in the original analysis.

---

## 🔴 CRITICAL CONFLICTS (Need Immediate Attention)

### 1. **crypto_only_profile Field Name Mismatch**
- **Status**: ✅ ALREADY HANDLED (Line 319 checks both names)
- **Issue**: YAML uses `crypto_only_profile`, but Pydantic model has `crypto_only`
- **Current Fix**: loader.py:319 checks both: `getattr(profile, "crypto_only", False) or getattr(profile, "crypto_only_profile", False)`
- **Validation**: This conflict is already resolved with fallback logic

### 2. **Deprecated exchange_provider vs New Mode Settings**
- **Location**: provider_factory.py, models.py
- **Conflict**: `exchange_provider` (legacy) can override newer `market_data_mode` / `broker_mode`
- **Impact**: User sets `market_data_mode=primary` but `exchange_provider=alternative` wins
- **Detection**: Check if both legacy and new modes are set with conflicting values
- **Severity**: MEDIUM
- **Status**: ⚠️ NEEDS AUDIT CHECK

### 3. **Profile Symbols vs Base Symbols Only Logged**
- **Status**: ✅ ALREADY HANDLED (loader.py:366-374)
- **Current**: Logs info when symbols differ
- **Impact**: Silent universe change when switching profiles

### 4. **CCXT + Intraday Profile Only Warned**
- **Status**: ✅ ALREADY HANDLED (loader.py:354-359)
- **Current**: Logs warning for intraday + crypto provider
- **Impact**: User can keep PDT/equity logic with crypto

---

## 🟡 MEDIUM SEVERITY CONFLICTS

### 5. **Runtime Hold Rules vs Profile Hold Rules Inconsistent**
- **Location**: ibkr_executor.py vs backtester.py
- **Conflict**:
  - Live trading uses `runtime.min_hold_seconds`
  - Backtester uses profile `min_hold_hours` / `max_hold_hours`
- **Impact**: Different behavior between live and backtest
- **Detection**: Compare runtime.min_hold_seconds with profile min_hold_hours
- **Severity**: MEDIUM
- **Status**: ⚠️ DESIGN INCONSISTENCY

### 6. **Allow Day Trades vs Min Hold Seconds Ambiguity**
- **Status**: ✅ ALREADY HANDLED (loader.py:410-419)
- **Current**: Logs ambiguous intent when `allow_day_trades=false` but `min_hold_seconds < 3600`

### 7. **Auto-Schedule + Scheduled Sessions Conflict**
- **Status**: ✅ ALREADY HANDLED (loader.py:433-443)
- **Current**: Logs info when continuous_mode=true but sessions exist

### 8. **Sabbath + Continuous Mode**
- **Status**: ✅ ALREADY HANDLED (loader.py:445-451)
- **Current**: Logs info about intentional pause

---

## 🟢 LOW SEVERITY / INFORMATIONAL

### 9. **Coinbase Granularity Remaps 4h → 6h**
- **Location**: coinbase.py
- **Issue**: HTF timeframe `4h` is silently remapped to `6h`
- **Impact**: Strategy behavior changes without config error
- **Detection**: Check if profile uses 4h with Coinbase provider
- **Severity**: LOW (Coinbase limitation)
- **Status**: ⚠️ PROVIDER LIMITATION

### 10. **CCXT Symbol Map vs Profile Symbols**
- **Location**: ccxt_broker.py
- **Issue**: Profile symbols might not be in CCXT symbol map
- **Impact**: Orders/quotes silently fail or skip
- **Detection**: Validate profile symbols against CCXT map at startup
- **Severity**: LOW
- **Status**: ⚠️ NEEDS VALIDATION

### 11. **Auto-Schedule Symbol Selection Drops Unknown Symbols**
- **Location**: auto_schedule.py, symbols.py
- **Issue**: `select_auto_schedule_symbols()` skips symbols not in SYMBOL_METADATA
- **Impact**: Mis-typed symbols become invisible
- **Detection**: Check profile symbols against SYMBOL_METADATA
- **Severity**: LOW
- **Status**: ⚠️ NEEDS VALIDATION

---

## 📊 CONFLICT SUMMARY

| Conflict | Severity | Status |
|----------|----------|--------|
| crypto_only_profile field mismatch | CRITICAL | ✅ HANDLED |
| exchange_provider vs new modes | MEDIUM | ⚠️ NEEDS AUDIT |
| Profile vs base symbols | MEDIUM | ✅ HANDLED |
| CCXT + intraday profile | HIGH | ✅ HANDLED |
| Runtime vs profile hold rules | MEDIUM | ⚠️ DESIGN ISSUE |
| Day trades vs hold seconds | LOW | ✅ HANDLED |
| Auto-schedule + sessions | MEDIUM | ✅ HANDLED |
| Sabbath + continuous | LOW | ✅ HANDLED |
| Coinbase 4h → 6h remap | LOW | ⚠️ PROVIDER LIMIT |
| CCXT symbol map validation | LOW | ⚠️ NEEDS CHECK |
| Auto-schedule unknown symbols | LOW | ⚠️ NEEDS CHECK |

---

## 🎯 RECOMMENDED ACTIONS

### High Priority

1. **Add audit for exchange_provider vs mode conflict**:
```python
# In loader.py _enforce_profile_guardrails()
legacy = (getattr(settings.market, "exchange_provider", "") or "").lower()
broker_mode = (getattr(settings.market, "broker_mode", "") or "").lower()
market_mode = (getattr(settings.market, "market_data_mode", "") or "").lower()

if legacy and (broker_mode or market_mode):
    if legacy != broker_mode or legacy != market_mode:
        logger.warning(
            "Audit: exchange_provider='%s' conflicts with broker_mode='%s' / market_data_mode='%s'. "
            "Legacy exchange_provider may override newer mode settings.",
            legacy, broker_mode, market_mode
        )
```

### Medium Priority

2. **Validate symbols against provider capabilities at startup**
3. **Document runtime vs profile hold rule differences**
4. **Add validation for Coinbase timeframe remapping**

### Low Priority

5. **Add symbol metadata validation for auto-schedule**
6. **Consider unifying hold time settings between runtime and profiles**
