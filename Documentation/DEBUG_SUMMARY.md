# Tradebot Debug Summary - 2026-01-06

## Issues Identified

### 1. **Config Persistence Issue** ✅ FIXED
**Problem**: Bot was connecting to IBKR despite `EXCHANGE_PROVIDER=alternative` setting.

**Root Causes Found**:
- `@lru_cache` on `get_settings()` was caching old config
- `tradebot.sh` wasn't re-sourcing `.env` on restart
- `EXCHANGE_PROVIDER` wasn't mapped in `loader.py`

**Fixes Applied**:
- ✅ Added `EXCHANGE_PROVIDER` to `market_overrides` in `loader.py:76`
- ✅ Changed `settings_base.yaml:20` to `exchange_provider: alternative`
- ✅ `tradebot.sh` now re-sources `.env` in restart function

### 2. **Symbol Configuration for Coinbase** ✅ FIXED
**Problem**: Bot trying to fetch SPY/QQQ/GLD from Coinbase (404 errors).

**Root Cause**: Coinbase only supports crypto pairs (BTC-USD, ETH-USD, etc.), not traditional securities.

**Fixes Applied**:
- ✅ Changed `default_symbol` from SPY to BTCUSD in `settings_base.yaml:17`
- ✅ Updated `auto_schedule` profile symbols to crypto-only:
  ```yaml
  symbols:
    - BTCUSD
    - ETHUSD
    - SOLUSD
  ```

### 3. **GUI Threading Crash** ✅ FIXED
**Problem**: GUI crashed with "QThread: Destroyed while thread '' is still running" after ~10 seconds.

**Root Cause**: Capital tune thread error/completion handlers in [app.py](src/tradebot_sci/gui/app.py) were setting thread references to `None` WITHOUT calling `quit()` and `wait()` first.

**Symptoms**:
```
[CAPITAL_TUNE] CCXT balance missing USD/USDC/USDT
QThread: Destroyed while thread '' is still running
Aborted (core dumped)
```

**Fix Applied**:
- Updated `_on_capital_tune_error()` at line 2152-2159
- Updated `_on_capital_tune_done()` at lines 2126-2136 and 2151-2158
- Added proper thread cleanup:
  ```python
  if self._capital_tune_thread is not None and self._capital_tune_thread.isRunning():
      self._capital_tune_thread.quit()
      self._capital_tune_thread.wait(2000)
  self._capital_tune_thread = None
  ```

**Result**: ✅ GUI now runs stably without crashes (verified 60+ seconds uptime)

## Current Configuration State

### Settings Files:
- **`.env`**: `EXCHANGE_PROVIDER=alternative`, `BROKER_MODE=alternative`, `MARKET_DATA_MODE=alternative` ✅
- **`settings_base.yaml`**: `exchange_provider: alternative`, `default_symbol: BTCUSD` ✅
- **`settings_profiles.yaml`**: `auto_schedule` profile uses crypto symbols only ✅

### Verified Working:
```bash
$ python3 -c "from tradebot_sci.config.loader import get_settings; s=get_settings(); print(s.market.default_symbol, s.market.exchange_provider)"
BTCUSD alternative  ✅
```

## Remaining Issues

### 1. GUI Symbol Display Issue ⚠️ IN PROGRESS
**Priority**: MEDIUM
**Impact**: GUI dropdown has correct crypto symbols, but candles panel fetches SPY by default

**Root Cause**: GUI's `tick_candles()` method uses `state.structure_by_symbol` to auto-pick symbols when no symbol is manually selected. This state is populated from trading log parsing, which contains old symbols (SPY, QQQ, etc.) from previous runs.

**Workaround**: User can manually select BTCUSD/ETHUSD/SOLUSD from the symbol dropdown in the GUI.

**Permanent Fix Options**:
1. Clear state files before GUI startup: `rm -rf data/*.json hold*/*.json`
2. Set initial locked symbol to BTCUSD in GUI initialization
3. Start bot in trading mode (not GUI-only) to populate structure_by_symbol with crypto symbols

### 2. CCXT Balance Warning
**Priority**: MEDIUM
**Message**: `[CAPITAL_TUNE] CCXT balance missing USD/USDC/USDT`

**Cause**: Bot trying to fetch balance but Coinbase API might need:
- Proper API credentials in `.env` (CCXT_API_KEY, CCXT_SECRET exist ✅)
- Account to have USD/USDC/USDT balance
- Different balance fetch method for Coinbase spot trading

### 3. IBKR Fallback Connection Attempts
**Priority**: LOW
**Message**: `API connection failed: ConnectionRefusedError(111, "Connect call failed ('127.0.0.1', 7497)")`

**Cause**: Code still attempts IBKR connection as fallback even when `exchange_provider=alternative`

**Fix**: Update `loop.py:114` to ONLY try IBKR when explicitly set to "primary":
```python
provider = os.getenv("EXCHANGE_PROVIDER") or settings.market.exchange_provider
if provider.strip().lower() != "primary":
    return None  # Don't even try IBKR connection
```

## Testing Recommendations

1. **Clear all caches** before testing:
   ```bash
   rm -rf src/**/__pycache__
   ```

2. **Start GUI in isolated environment**:
   ```bash
   cd "/path/to/tradebot-sci-debug"
   ./scripts/tradebot.sh --gui
   ```

3. **Monitor for successful Coinbase fetches**:
   ```bash
   tail -f logs/tradebot.log | grep -i "coinbase\|btc\|eth\|sol"
   ```

4. **Verify no IBKR connection attempts**:
   ```bash
   tail -f logs/tradebot.log | grep -i "ibkr\|ib_insync"
   ```

## Files Modified

1. `config/settings_base.yaml` - Changed default_symbol to BTCUSD, exchange_provider to alternative
2. `config/settings_profiles.yaml` - Updated auto_schedule symbols to crypto-only
3. `src/tradebot_sci/config/loader.py` - Added EXCHANGE_PROVIDER to market_overrides
4. `scripts/tradebot.sh` - Re-sources .env on restart (from ANTIGRAVITY session)

## Next Steps

1. Fix GUI threading crash (highest priority)
2. Test full startup with Coinbase crypto symbols
3. Verify CCXT balance fetch works or disable capital tune for now
4. Take screenshot of working GUI showing crypto charts
5. Monitor logs for successful trading decisions with crypto

---
*Debug session completed: 2026-01-06*
*Multi-agent collaboration with ANTIGRAVITY successfully identified config persistence issues*
