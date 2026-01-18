# Configuration Conflicts & Permutation Analysis

## Summary
Deep analysis of all potential configuration conflicts in the tradebot, examining how different settings can trip over each other similar to the Crypto+PDT+24h hold issue.

## ✅ IMPLEMENTATION STATUS (Updated: 2026-01-07)

**All HIGH and MEDIUM priority conflicts have been addressed in [loader.py](/home/qchan/Scripts/Trade by SCI/tradebot-sci-debug/src/tradebot_sci/config/loader.py).**

### Conflicts Resolved:
- **10 HIGH/MEDIUM conflicts**: Now have auto-resolution or informational warnings
- **10 LOW/INFO conflicts**: Marked as design choices or user configuration decisions
- **Total: 20 conflicts** identified and categorized

### Implementation Details:
All audit checks are in `_enforce_profile_guardrails()` function (lines 306-451):
1. ✅ Crypto + PDT (auto-disabled)
2. ✅ Crypto + Min Hold (auto-cleared)
3. ✅ PDT + Auto Flatten (auto-disabled)
4. ✅ Intraday + CCXT (warning issued)
5. ✅ Continuous + Sessions (info check)
6. ✅ Intraday Flatten + Continuous (auto-disabled)
7. ✅ Fractional + Stocks (warning issued)
8. ✅ Day Trades + Hold Seconds (info check)
9. ✅ Local Stops + CCXT (info about synthetic stops)
10. ✅ Continuous + Sabbath (intentional check)

---

## ✅ ALREADY HANDLED (Implemented in loader.py:306-350)

### 1. **Crypto + PDT Guard**
- **Conflict**: PDT guard on crypto (24/7 market)
- **Status**: ✅ Auto-resolved at line 336-338
- **Fix**: `pdt_guard_enabled = False` when crypto detected

### 2. **Crypto + Min Hold Hours**
- **Conflict**: 24h hold requirement on crypto (no market close)
- **Status**: ✅ Auto-resolved at line 340-343
- **Fix**: `min_hold_hours = 0.0` when crypto detected

### 3. **PDT Guard + Auto Flatten on Close**
- **Conflict**: Can't flatten at close if PDT limits day trades
- **Status**: ✅ Auto-resolved at line 311-316
- **Fix**: `auto_flatten_on_close = False` when PDT enabled

---

## ⚠️ POTENTIAL UNHANDLED CONFLICTS

### 4. **Intraday Profile + CCXT/Crypto Symbols**
- **Location**: Profile `intraday` (lines 6-35 in settings_profiles.yaml)
- **Conflict**:
  - `intraday` has NO `continuous_mode` flag (defaults to False)
  - If user sets `EXCHANGE_PROVIDER=alternative` (CCXT/crypto)
  - Intraday profile expects market sessions (9:25-11:45, 13:30-16:05)
  - Crypto markets are 24/7 with no sessions
- **Impact**: Bot may pause trading during "off hours" even though crypto never closes
- **Detection**: Check if `profile=intraday` AND `exchange_provider=alternative`
- **Permutation Scenarios**:
  1. User picks intraday profile but switches to CCXT → trading pauses at 4:05pm
  2. User has crypto symbols (BTCUSD) in intraday profile → confusion about when to trade
  3. `auto_flatten_on_close` conflicts with 24/7 operation

### 5. **Continuous Mode + Schedule Sessions**
- **Location**: `crypto_247`, `all_247`, `auto_schedule` profiles
- **Conflict**:
  - Profiles have `continuous_mode: true` (24/7)
  - Base settings have `schedule.sessions` with morning/afternoon times
  - If a profile doesn't explicitly set `auto_schedule_enabled: false`, it might inherit session logic
- **Impact**: 24/7 crypto bot might unexpectedly pause during "off hours"
- **Detection**: Check if `continuous_mode=True` AND `schedule.sessions` exists AND `auto_schedule_enabled != False`
- **Current State**:
  - `crypto_247` has `continuous_mode: true` but NO `auto_schedule_enabled` field → might inherit
  - `auto_schedule` profile sets `auto_schedule_enabled: true` + `continuous_mode: true` → potential conflict

### 6. **Auto Schedule + Sabbath Mode**
- **Location**: `auto_schedule` profile (line 176-259)
- **Conflict**:
  - `auto_schedule_enabled: true` (use market sessions)
  - `sabbath_enabled: true` (pause Friday 6pm - Saturday 6pm)
  - If crypto trading (`continuous_mode: true`), sabbath creates artificial pause
- **Impact**: Crypto bot honors Jewish Sabbath but still tries to run 24/7
- **Detection**: `sabbath_enabled=True` AND `continuous_mode=True`
- **Question**: Is this intentional (religious observance) or accidental?

### 7. **Intraday Flatten + Continuous Mode**
- **Location**: Multiple profiles
- **Conflict**:
  - `intraday_flatten` in base settings (line 36): `false`
  - Profile `runtime_overrides.intraday_flatten: false` (crypto_247, all_247, auto_schedule)
  - But if user enables `intraday_flatten=True` via ENV while using crypto profile
  - Crypto positions flatten at market "close" that doesn't exist
- **Impact**: 24/7 crypto positions unexpectedly flatten at 4:05pm
- **Detection**: `intraday_flatten=True` AND (`continuous_mode=True` OR `exchange_provider=alternative`)

### 8. **Allow Day Trades + Min Hold Seconds**
- **Location**: Base settings runtime (lines 37-38)
- **Conflict**:
  - `allow_day_trades: false` (must hold positions)
  - `min_hold_seconds: 300` (5 minutes minimum)
  - If PDT guard enabled, "allow_day_trades" is contradictory
- **Impact**: Unclear which takes precedence
- **Detection**: `allow_day_trades=False` AND `min_hold_seconds < 3600` → ambiguous intent
- **Note**: `allow_day_trades=False` typically means "must hold overnight", but `min_hold_seconds=300` suggests intraday is allowed

### 9. **Crypto Fractional + Traditional Symbols**
- **Location**: Profile settings
- **Conflict**:
  - `crypto_fractional_enabled: true` (allows 0.001 BTC orders)
  - But profile has mixed symbols (SPY, QQQ, BTCUSD)
  - IBKR doesn't allow fractional shares of stocks
- **Impact**: Bot tries to buy 0.5 shares of SPY → order rejected
- **Detection**: `crypto_fractional_enabled=True` AND symbols contain non-crypto (SPY, QQQ, GLD)
- **Current Risk**: `intraday` profile has `crypto_fractional_enabled: false` which is correct, but if user overrides via ENV...

### 10. **Local Stops + CCXT (No Stop Support)**
- **Location**: Base settings runtime (lines 50-53)
- **Conflict**:
  - `allow_local_stops: true`
  - `local_stop_symbols: [SOLUSD, BTCUSD]` (crypto)
  - But CCXT exchanges don't support native stop orders
  - Bot must use synthetic stops (polling)
- **Impact**: User expects native stop orders but gets synthetic (slower, depends on bot uptime)
- **Detection**: `allow_local_stops=True` AND `exchange_provider=alternative` AND symbol is crypto
- **Mitigation**: Already uses synthetic stops for crypto, but no warning to user

### 11. **PDT Guard + Max Equity Roundtrips**
- **Location**: Profile settings
- **Conflict**:
  - `pdt_guard_enabled: true` (limit to 3 day trades per 5 days)
  - `max_equity_roundtrips_per_day: 99` (very high limit)
- **Impact**: PDT guard will block at 3 trades, making the 99 limit meaningless
- **Detection**: `pdt_guard_enabled=True` AND `max_equity_roundtrips_per_day > 3`
- **Current State**: `intraday` has this conflict (PDT=True, max_roundtrips not set → might default high)

### 12. **Maker-First + Market Orders (Fast Execution Needed)**
- **Location**: Crypto profiles
- **Conflict**:
  - `maker_first_enabled: true` (post limit orders to save fees)
  - But ICC methodology requires fast entries on trigger
  - Maker orders might miss the trade if price moves
- **Impact**: Entry delayed waiting for limit fill → missed opportunity
- **Detection**: `maker_first_enabled=True` AND `icc_auto_entry_enabled=True` with tight timeframes
- **Question**: Does user want fee savings or speed?

### 13. **Pyramid + Cooldown After Success**
- **Location**: Profiles with pyramid trading
- **Conflict**:
  - `max_pyramid_entries: 5` (scale into position)
  - `cooldown_cycles_after_success: 1` (pause after winning trade)
  - If first pyramid entry succeeds, cooldown prevents adding more
- **Impact**: Can't build full 5-entry pyramid
- **Detection**: `max_pyramid_entries > 1` AND `cooldown_cycles_after_success > 0`
- **Current State**: `auto_schedule` has `cooldown_cycles_after_success: 0` (correct)

### 14. **Auto Flatten on Close + Max Hold Hours**
- **Location**: Various profiles
- **Conflict**:
  - `auto_flatten_on_close: false` (hold overnight)
  - `max_hold_hours: 120.0` (5 days max)
  - If market is closed 16 hours/day, 120 hours spans multiple days
  - Position exits at max_hold during market hours
- **Impact**: Ambiguous when position actually closes
- **Detection**: `auto_flatten_on_close=False` AND `max_hold_hours > 24` → clarify intent

### 15. **Symbols List Conflicts (Profile vs Base vs ENV)**
- **Location**: Multiple levels
- **Conflict**:
  - Base settings: `symbols: [BTCUSD, ETHUSD, SOLUSD]`
  - Profile (auto_schedule): `symbols: [BTCUSDT, ETHUSDT, SOLUSDT]` (different exchange)
  - ENV override: `MARKET_SYMBOLS=SPY,QQQ`
- **Impact**: Which symbol list wins? Mixing Binance (USDT) and Coinbase (USD) pairs
- **Detection**: Profile symbols != base symbols != ENV symbols
- **Current Risk**: User confusion about which symbols are actually trading

### 16. **Pair Selector + Fixed Symbols List**
- **Location**: crypto_247, all_247, auto_schedule
- **Conflict**:
  - `pair_selector_enabled: true` (dynamically pick best crypto pairs)
  - `symbols: [BTCUSDT, ETHUSDT, SOLUSDT]` (fixed list)
- **Impact**: Pair selector might pick different symbols, ignore fixed list
- **Detection**: `pair_selector_enabled=True` AND profile has `symbols` field
- **Question**: Does pair selector use fixed list as candidates, or ignore it?

### 17. **Crypto Routing + Wrong Exchange Provider**
- **Location**: Base settings (lines 27-32)
- **Conflict**:
  - `crypto_routing.overrides` sets BTCUSD → ZEROHASH
  - But `exchange_provider: alternative` (CCXT/Coinbase)
  - ZEROHASH is IBKR's crypto endpoint
- **Impact**: Routing ignored when using CCXT
- **Detection**: `crypto_routing` defined AND `exchange_provider != primary`

### 18. **Emergency Stop + Synthetic Stops**
- **Location**: Base settings + profile settings
- **Conflict**:
  - `emergency_stop_pct: 0.01` (1% portfolio loss = stop)
  - `synthetic_stop_persistence_enabled: true` (per-position stops)
  - If portfolio hits emergency stop, but position stop is further away
- **Impact**: Which stop fires first? Both?
- **Detection**: Both emergency stop and synthetic stops enabled

### 19. **Guard Block Threshold + Continuous Trading**
- **Location**: Base settings (lines 48-49)
- **Conflict**:
  - `guard_block_threshold: 6` (block symbol after 6 failures)
  - `continuous_mode: true` (24/7 trading)
  - If symbol blocked during US hours, stays blocked during Asia hours
- **Impact**: Missing trading opportunities in different time zones
- **Detection**: `guard_block_threshold > 0` AND `continuous_mode=True`
- **Suggestion**: Maybe reset guard blocks at daily boundaries for 24/7?

### 20. **Sabbath Timezone + Crypto Trading**
- **Location**: auto_schedule profile
- **Conflict**:
  - `sabbath_timezone: America/New_York`
  - Crypto trades globally 24/7
  - Sabbath pause in NY time affects global market
- **Impact**: If user is in Asia, sabbath pauses at wrong local time
- **Detection**: `sabbath_enabled=True` AND `continuous_mode=True` AND user timezone != sabbath timezone

---

## 📊 CONFLICT MATRIX

| Conflict | Profiles Affected | Severity | Auto-Resolved? |
|----------|------------------|----------|----------------|
| Crypto + PDT | all crypto profiles | HIGH | ✅ YES (loader.py:336-352) |
| Crypto + Min Hold | all crypto profiles | HIGH | ✅ YES (loader.py:336-352) |
| PDT + Auto Flatten | intraday | MEDIUM | ✅ YES (loader.py:311-316) |
| Intraday + CCXT | intraday (if CCXT used) | HIGH | ✅ YES (loader.py:354-359) |
| Continuous + Sessions | crypto_247, all_247 | MEDIUM | ✅ YES (loader.py:433-443) |
| Auto Schedule + Sabbath | auto_schedule | LOW | ✅ INFO (loader.py:445-451) |
| Intraday Flatten + Continuous | all crypto if ENV override | HIGH | ✅ YES (loader.py:361-364) |
| Day Trades + Hold Seconds | all profiles | LOW | ✅ INFO (loader.py:410-419) |
| Fractional + Stocks | intraday (if crypto enabled) | MEDIUM | ✅ YES (loader.py:393-408) |
| Local Stops + CCXT | crypto profiles | INFO | ✅ INFO (loader.py:421-431) |
| PDT + High Roundtrips | intraday | LOW | ✅ INFO (loader.py:376-384) |
| Maker-First + Fast Entry | crypto profiles | MEDIUM | ⚠️ DESIGN CHOICE |
| Pyramid + Cooldown | most profiles | LOW | ✅ AVOIDED (cooldown=0) |
| Flatten + Max Hold | swing, auto_schedule | LOW | ⚠️ DESIGN CHOICE |
| Symbol List Conflicts | all profiles | MEDIUM | ✅ INFO (loader.py:366-374) |
| Pair Selector + Fixed Symbols | crypto_247, auto_schedule | MEDIUM | ✅ INFO (loader.py:386-391) |
| Crypto Routing + CCXT | base + CCXT | INFO | ⚠️ BENIGN (routing ignored) |
| Emergency + Synthetic Stops | all profiles | LOW | ⚠️ DESIGN CHOICE |
| Guard Block + 24/7 | continuous profiles | LOW | ⚠️ DESIGN CHOICE |
| Sabbath TZ + Global Crypto | auto_schedule | LOW | ⚠️ USER CONFIG |

---

## 🎯 RECOMMENDED ADDITIONS TO AUDIT

### High Priority (Add to loader.py)

1. **Intraday + CCXT Check**:
```python
if profile_name == "intraday" and provider.lower() in {"ccxt", "alternative", "coinbase"}:
    logger.warning("Audit: Intraday profile with CCXT/crypto detected. "
                   "Consider using crypto_247 or auto_schedule for 24/7 markets.")
```

2. **Intraday Flatten + Continuous Mode**:
```python
if settings.runtime.intraday_flatten and getattr(profile, "continuous_mode", False):
    settings.runtime.intraday_flatten = False
    logger.warning("Audit: intraday_flatten disabled for continuous_mode profile")
```

3. **Symbol List Mismatch**:
```python
profile_symbols = set(getattr(profile, "symbols", []) or [])
base_symbols = set(settings.market.symbols or [])
if profile_symbols and base_symbols and profile_symbols != base_symbols:
    logger.warning("Audit: Profile symbols %s differ from base symbols %s",
                   profile_symbols, base_symbols)
```

### Medium Priority

4. **PDT + High Roundtrip Limit**:
```python
if getattr(profile, "pdt_guard_enabled", False):
    max_rt = getattr(profile, "max_equity_roundtrips_per_day", 99)
    if max_rt > 3:
        logger.info("Audit: PDT guard will limit to 3 day trades, "
                    f"max_equity_roundtrips_per_day={max_rt} is ineffective")
```

5. **Pair Selector + Fixed Symbols**:
```python
if getattr(profile, "pair_selector_enabled", False) and getattr(profile, "symbols", []):
    logger.info("Audit: pair_selector_enabled with fixed symbols list. "
                "Selector will use symbols as candidates.")
```

---

## 💡 DESIGN QUESTIONS FOR USER

1. **Sabbath on Crypto**: Is `sabbath_enabled` on `auto_schedule` (crypto profile) intentional for religious observance?
2. **Maker-First**: Does user want fee savings (limit orders) or fast execution (market orders) for ICC entries?
3. **Intraday Flatten**: Should intraday_flatten be forcibly disabled for all continuous_mode profiles?
4. **Symbol Lists**: Should profile symbols REPLACE base symbols or MERGE with them?
5. **Crypto Routing**: Should we warn when crypto_routing is defined but CCXT is active (routing won't be used)?

---

## ✅ VALIDATION CHECKLIST

To prevent conflicts, every time user:
- Switches exchange provider (primary ↔ alternative)
- Changes profile (intraday → crypto_247)
- Enables crypto symbols in non-crypto profile
- Sets environment overrides

Run audit checks for:
- [ ] Crypto detection vs PDT/hold settings
- [ ] Continuous mode vs session schedule
- [ ] Fractional trading vs symbol types
- [ ] Intraday flatten vs 24/7 operation
- [ ] Symbol list consistency across layers
