# Trading Bot Settings Analysis Report

## Executive Summary

This report catalogs all settings/options in the trading bot GUI, identifies redundancies and conflicts, and recommends missing settings that should be exposed.

**Key Findings:**
- **CRITICAL BUG**: Duplicate field definitions in `TradingProfileSettings` (lines 242-277 and 401-437 in models.py)
- **Max Positions vs Pyramiding**: These are COMPLEMENTARY, not redundant (see detailed analysis below)
- **Missing Settings**: 31 profile settings and 15 runtime settings not exposed in GUI
- **Current Settings**: 100+ settings across 13 tabs

---

## 1. CRITICAL: Code Duplication Bug

### Issue
The `TradingProfileSettings` class in `/media/qchan/Steam Games/Scripts/Trade by SCI/tradebot-sci-enterprise/src/tradebot_sci/config/models.py` has **duplicate field definitions** (lines 242-277 duplicated at lines 401-437):

**Duplicated Fields:**
- `cooldown_enabled`
- `cooldown_cycles_after_block`
- `cooldown_cycles_after_success`
- `cooldown_scope`
- `stick_to_active_symbol_until`
- `crypto_fractional_enabled`
- `crypto_min_notional_usd`
- `crypto_max_notional_usd`
- `crypto_qty_steps`

### Recommendation
**REMOVE** lines 401-437 in `models.py` - they are exact duplicates of lines 242-277.

---

## 2. Max Positions vs Pyramiding Analysis

### User's Concern
> "Some of them appear to maybe step on the toes of other options (I.E. Max positions vs Pyramiding)"

### Analysis: These are COMPLEMENTARY, NOT Redundant

**Max Concurrent Positions** (`MULTI_POSITION_ENABLED` + `MAX_CONCURRENT_POSITIONS`)
- **Scope**: ACROSS different symbols
- **Purpose**: How many DIFFERENT symbols can be traded at once
- **Example**: Trade SPY AND QQQ AND BTCUSD simultaneously
- **Location**: Runtime tab

**Max Pyramid Entries** (`PROFILE_MAX_PYRAMID_ENTRIES`)
- **Scope**: WITHIN a single position on ONE symbol
- **Purpose**: How many times to add to a WINNING position
- **Example**: Enter SPY at $500, add at $505, add again at $510 (3 entries total on SPY)
- **Location**: Strategy tab

### Real-World Example
```
Settings:
- MULTI_POSITION_ENABLED = true
- MAX_CONCURRENT_POSITIONS = 3
- PROFILE_MAX_PYRAMID_ENTRIES = 3

Result:
✓ Can hold SPY + QQQ + BTCUSD at the same time (3 different symbols)
✓ Can pyramid into SPY up to 3 times (initial + 2 adds)
✓ Can pyramid into QQQ up to 3 times (initial + 2 adds)
✓ Can pyramid into BTCUSD up to 3 times (initial + 2 adds)

Maximum theoretical risk: 3 symbols × 3 entries × risk per entry
```

### Recommendation
**KEEP BOTH** - They control different dimensions of position management. Consider renaming for clarity:
- `MAX_CONCURRENT_POSITIONS` → `Max concurrent SYMBOLS`
- `PROFILE_MAX_PYRAMID_ENTRIES` → `Max pyramid entries PER SYMBOL`

---

## 3. Complete Settings Catalog

### 3.1 Bot Tab (13 settings)
| Setting | Type | Config Source |
|---------|------|---------------|
| `APP_ENVIRONMENT` | Text | AppSettings |
| `PROFILE_NAME` | Dropdown | AppSettings |
| `BOT_MODE` | Dropdown | Runtime mode |
| `BOT_ITERATIONS` | Number | Runtime mode |
| `EXECUTE_TRADES` | Checkbox | Runtime master switch |
| `BOT_SABBATH` | Dropdown | Runtime override |
| `LOG_LEVEL` | Dropdown | LoggingSettings |
| `SESSION_NAME` | Text | tmux session |
| `TRADEBOT_LOG` | File path | LoggingSettings.file |
| `GUI_AUTOSTART_BOT` | Checkbox | GUI QSettings |
| `GUI_KEEP_BOT_RUNNING` | Checkbox | GUI QSettings |
| `AUTO_RESTART_ON_ERROR` | Checkbox | RuntimeSettings |
| `BUG_BYPASS_SCHEDULE` | Checkbox | Debug override |

**Auto-Restart Settings:**
- `AUTO_RESTART_STALE_SECONDS` (Number, default: 300)
- `AUTO_RESTART_MIN_UPTIME_SECONDS` (Number, default: 120)
- `AUTO_RESTART_COOLDOWN_SECONDS` (Number, default: 600)

### 3.2 Time Tab (7 settings)
| Setting | Type | Config Source |
|---------|------|---------------|
| `SABBATH_ENABLED` | Dropdown | TradingProfileSettings override |
| `SABBATH_ASTRONOMICAL` | Checkbox | TradingProfileSettings |
| `SABBATH_CITY` | Text | Helper for lat/lon resolution |
| `SABBATH_TIMEZONE` | Text | TradingProfileSettings |
| `SABBATH_START_LOCAL` | Text (HH:MM) | TradingProfileSettings |
| `SABBATH_END_LOCAL` | Text (HH:MM) | TradingProfileSettings |
| `SABBATH_LAT` | Number | TradingProfileSettings |
| `SABBATH_LON` | Number | TradingProfileSettings |

**Note:** These settings are shared/synced with:
- `COMMENTARY_LLM_TZ`
- `PROFILE_SESSION_OVERLAP_TIMEZONE`

### 3.3 Market Tab (8 settings)
| Setting | Type | Config Source |
|---------|------|---------------|
| `EXCHANGE_PROVIDER` | Dropdown | MarketSettings.exchange_provider |
| `ALTERNATIVE_MARKET_DATA` | Dropdown | MarketSettings.alternative_market_data |
| `ALTERNATIVE_BROKER` | Dropdown | MarketSettings.alternative_broker |
| `MARKET_DEFAULT_SYMBOL` | Text | MarketSettings.default_symbol |
| `MARKET_DEFAULT_TIMEFRAME` | Dropdown | MarketSettings.default_timeframe |
| GUI Candle Size | Dropdown | GUI display only |
| `MARKET_MAX_CANDLES` | Number | MarketSettings.max_candles |
| `MARKET_SYMBOLS` | Textarea | MarketSettings.symbols (comma-separated) |

### 3.4 Runtime Tab (13 settings)
| Setting | Type | Config Source |
|---------|------|---------------|
| `CANCEL_ORDERS_ON_START` | Checkbox | RuntimeSettings |
| `FLATTEN_ON_EXIT` | Checkbox | RuntimeSettings |
| `INTRADAY_FLATTEN` | Checkbox | RuntimeSettings |
| `ALLOW_INHERITED_POSITION` | Checkbox | RuntimeSettings |
| `MULTI_POSITION_ENABLED` | Checkbox | RuntimeSettings |
| `MAX_CONCURRENT_POSITIONS` | Number | RuntimeSettings |
| `STARTUP_CRYPTO_UNPROTECTED_POLICY` | Dropdown | TradingProfileSettings |
| `SCALE_OUT_FRACTION` | Decimal | RuntimeSettings |
| `MIN_POSITION_SIZE_TO_SCALE` | Decimal | RuntimeSettings |
| `EMERGENCY_STOP_PCT` | Decimal | RuntimeSettings |
| `MAX_SCALE_INS_PER_LEG` | Number | RuntimeSettings |
| `SYNTH_STOP_STORE_PATH` | File path | TradingProfileSettings |
| `POSITION_HOLD_STORE_PATH` | File path | RuntimeSettings |

### 3.5 Risk Tab (9 settings)
| Setting | Type | Config Source |
|---------|------|---------------|
| `FRICTION_FAIL_SAFE` | Checkbox | Risk model toggle |
| `FRICTION_RISK_CAP` | Decimal | Risk model threshold |
| `VIX_FAIL_SAFE` | Checkbox | Risk model toggle |
| `VIX_RISK_CAP` | Decimal | Risk model threshold |
| `PROFILE_ICC_AGGRESSIVE_MODE` | Dropdown | TradingProfileSettings |
| `PROFILE_AGGRESSIVE_RISK_PER_TRADE_PCT` | Decimal | TradingProfileSettings |
| `PROFILE_MAX_DAILY_LOSS_PCT` | Decimal | TradingProfileSettings |
| `PROFILE_MAX_EXPOSURE_PCT` | Decimal | TradingProfileSettings |
| `PROFILE_MAX_CONSECUTIVE_LOSSES` | Number | TradingProfileSettings |

### 3.6 Strategy Tab (24 settings)
| Setting | Type | Config Source |
|---------|------|---------------|
| `CONFLUENCE_EXTERNAL` | Checkbox | Strategy toggle |
| `COMMITMENT_MODE` | Checkbox | Strategy toggle |

**ICC Structure:**
- `PROFILE_HTF_TIMEFRAME` (Dropdown)
- `PROFILE_LTF_TIMEFRAME` (Dropdown)
- `PROFILE_TREND_WINDOW` (Number)
- `PROFILE_TREND_SWING_LOOKBACK` (Number)
- `PROFILE_TREND_MIN_SWINGS` (Number)
- `PROFILE_TREND_STRENGTH_FLOOR` (Decimal)
- `PROFILE_STRUCTURE_SCORE_THRESHOLD` (Decimal)

**Session Bias (A+ Gate):**
- `PROFILE_SESSION_GATE_ENABLED` (Dropdown)
- `PROFILE_SESSION_GATE_MIN_CANDLES` (Number)
- `PROFILE_SESSION_RANGE_MULTIPLIER` (Decimal)
- `PROFILE_SESSION_VOLUME_MULTIPLIER` (Decimal)
- `PROFILE_SESSION_OVERLAP_START_HOUR` (Number)
- `PROFILE_SESSION_OVERLAP_END_HOUR` (Number)

**Risk/Flips:**
- `PROFILE_PDT_GUARD_ENABLED` (Dropdown)
- `PROFILE_MAX_EQUITY_ROUNDTRIPS_PER_DAY` (Number)
- `PROFILE_FLIP_ACTIONS_ENABLED` (Dropdown)
- `PROFILE_FLIP_COOLDOWN_SECONDS` (Number)
- `PROFILE_COOLDOWN_ENABLED` (Dropdown)
- `PROFILE_COOLDOWN_CYCLES_AFTER_BLOCK` (Number)
- `PROFILE_COOLDOWN_CYCLES_AFTER_SUCCESS` (Number)
- `PROFILE_COOLDOWN_SCOPE` (Dropdown)
- `PROFILE_STICK_TO_ACTIVE_SYMBOL_UNTIL` (Dropdown)
- `PROFILE_MAX_PYRAMID_ENTRIES` (Number)
- `PROFILE_HTF_NEUTRAL_EXIT_BARS` (Number)

### 3.7 Scoring Tab (8 settings)
| Setting | Type | Config Source |
|---------|------|---------------|
| `PROFILE_ICC_ENTRY_SCORE_THRESHOLD` | Decimal | TradingProfileSettings |
| `PROFILE_PYRAMID_SCORE_THRESHOLD` | Decimal | TradingProfileSettings |
| `PROFILE_ICC_SCORE_HTF_LTF_ALIGN_POINTS` | Decimal | TradingProfileSettings |
| `PROFILE_ICC_SCORE_SWEEP_POINTS` | Decimal | TradingProfileSettings |
| `PROFILE_ICC_SCORE_CONTINUATION_POINTS` | Decimal | TradingProfileSettings |
| `PROFILE_ICC_SCORE_STRONG_HTF_POINTS` | Decimal | TradingProfileSettings |
| `PROFILE_ICC_SCORE_PHASE_POINTS` | Decimal | TradingProfileSettings |
| `PROFILE_ICC_SCORE_HTF_STRENGTH_THRESHOLD` | Decimal | TradingProfileSettings |

### 3.8 Commentary Tab (6 settings)
| Setting | Type | Config Source |
|---------|------|---------------|
| `COMMENTARY_LLM` | Dropdown | Commentary mode |
| `COMMENTARY_LLM_POLICY` | Dropdown | Commentary policy |
| `COMMENTARY_LLM_DAILY_SLOTS` | Text | Commentary daily slots |
| `COMMENTARY_LLM_MIN_SECONDS` | Number | Commentary refresh rate |
| `COMMENTARY_LLM_MAX_CALLS_PER_DAY` | Number | Commentary budget |
| `COMMENTARY_LLM_BUDGET_PATH` | File path | Commentary budget file |

### 3.9 AI Tab (7 settings)
| Setting | Type | Config Source |
|---------|------|---------------|
| `TRADE_SCI_PROVIDER` | Dropdown | AISettings.provider |
| `TRADE_SCI_API_BASE_URL` | Text | AISettings.base_url |
| `TRADE_SCI_API_KEY` | Password | AISettings.api_key |
| `CHATGPT_KEY` | Password | Legacy fallback |
| `TRADE_SCI_MODEL_NAME` | Text | AISettings.model_name |
| `TRADE_SCI_TEMPERATURE` | Decimal | AISettings.temperature |
| `TRADE_SCI_MAX_TOKENS` | Number | AISettings.max_tokens |

### 3.10 IBKR Tab (15 settings)
| Setting | Type | Config Source |
|---------|------|---------------|
| `IBKR_HOST` | Text | BrokerSettings |
| `IBKR_PORT` | Number | BrokerSettings |
| `IBKR_CRYPTO_EXCHANGE` | Text | BrokerSettings |
| `IBKR_ZEROHASH_CRYPTO_TIF` | Dropdown | BrokerSettings |
| `IBKR_CLIENT_ID` | Text | BrokerSettings |
| `IBKR_ACCOUNT_ID` | Text | BrokerSettings |
| `IBKR_DEFAULT_CCY` | Text | BrokerSettings |
| `IBKR_PAPER` | Checkbox | BrokerSettings |
| `IBKR_READ_ONLY` | Checkbox | BrokerSettings |

**Risk Caps (with Override checkboxes):**
- `IBKR_MAX_SHARES_PER_SYMBOL` (Number + Override)
- `IBKR_MAX_DOLLAR_RISK_PER_SYMBOL` (Decimal + Override)
- `IBKR_MAX_DOLLAR_RISK_PER_ACCOUNT` (Decimal + Override)
- `IBKR_AUTO_RISK_FRACTION_OF_BUYING_POWER` (Decimal + Override)

### 3.11 CCXT Tab (10 settings)
| Setting | Type | Config Source |
|---------|------|---------------|
| `CCXT_EXCHANGE` | Text | Alternative broker config |
| `CCXT_DEFAULT_TYPE` | Dropdown | Alternative broker config |
| `CCXT_ENABLE_RATE_LIMIT` | Checkbox | Alternative broker config |
| `CCXT_SANDBOX` | Checkbox | Alternative broker config |
| `CCXT_SYMBOL_MAP` | Textarea | Alternative broker config |
| `CCXT_API_KEY` | Password | Alternative broker config |
| `CCXT_SECRET` | Password | Alternative broker config |
| `CCXT_PASSWORD` | Password | Alternative broker config |

### 3.12 Benchmark Tab
- Capital input for position sizing calculations

### 3.13 Advanced (env) Tab
- Raw environment variable table with filtering

---

## 4. Missing Settings (Should be Added to GUI)

### 4.1 Critical Profile Settings (NOT in GUI)

**Basic Profile Settings:**
1. `candle_timeframe` - **CRITICAL**: Base timeframe for the profile (e.g., "5m", "15m")
2. `market_poll_interval_seconds` - How often to fetch market data
3. `ai_decision_interval_seconds` - How often to run AI decision logic

**Auto-Schedule:**
4. `PROFILE_AUTO_SCHEDULE_ENABLED` - Equities in-hours, crypto off-hours
5. `PROFILE_CONTINUOUS_MODE` - Keep runtime alive indefinitely
6. `PROFILE_CRYPTO_ONLY` - Treat profile as crypto-only
7. `PROFILE_AUTO_FLATTEN_ON_CLOSE` - Auto-flatten at session end

**ICC Auto-Entry:**
8. `PROFILE_ICC_AUTO_ENTRY_ENABLED` - Auto-enter on ICC sweep+continuation
9. `PROFILE_ICC_AUTO_ENTRY_COOLDOWN_MINUTES` - Min minutes between auto-entries
10. `PROFILE_ICC_AUTO_ENTRY_MIN_HTF_STRENGTH` - Min HTF strength for auto-entry
11. `PROFILE_ICC_AUTO_ENTRY_REQUIRE_SWEEP` - Require sweep before auto-entry

**LTF Trend Settings:**
12. `PROFILE_LTF_TREND_WINDOW` - Candles for LTF trend detection

**Crypto Settings:**
13. `PROFILE_CRYPTO_FRACTIONAL_ENABLED` - Allow fractional crypto sizing
14. `PROFILE_CRYPTO_MIN_NOTIONAL_USD` - Min notional for crypto trades
15. `PROFILE_CRYPTO_MAX_NOTIONAL_USD` - Max notional for crypto trades
16. `PROFILE_CRYPTO_QTY_STEPS` - Per-symbol quantity steps (JSON)

**Crypto Pair Selection:**
17. `PROFILE_PAIR_SELECTOR_ENABLED` - Dynamic crypto basket selection
18. `PROFILE_PAIR_SELECTOR_REFRESH_SECONDS` - How often to refresh pairs
19. `PROFILE_PAIR_SELECTOR_MIN_VOLUME_USD_24H` - Min 24h volume
20. `PROFILE_PAIR_SELECTOR_MAX_SPREAD_BPS` - Max spread in bps
21. `PROFILE_PAIR_SELECTOR_MIN_DEPTH_USD` - Min order book depth
22. `PROFILE_PAIR_SELECTOR_MAX_PAIRS` - Max pairs to select

**Maker/Taker Preferences:**
23. `PROFILE_MAKER_FIRST_ENABLED` - Prefer maker (post-only) entries
24. `PROFILE_MAKER_FIRST_OFFSET_BPS` - Price offset for maker orders
25. `PROFILE_TAKER_MAX_SLIPPAGE_BPS` - Max slippage for taker orders
26. `PROFILE_ORDER_TIMEOUT_SECONDS` - Timeout for resting orders

**Synthetic Stop Settings:**
27. `PROFILE_SYNTHETIC_STOP_PERSISTENCE_ENABLED` - Persist stops to disk
28. `PROFILE_REARM_STOP_DISTANCE_PCT` - Distance for rearmed stops
29. `PROFILE_SYNTHETIC_STOP_INTEGRITY_INTERVAL` - Cycles between integrity checks

**Profile Overrides:**
30. `PROFILE_SYMBOLS` - Optional symbol universe override
31. `PROFILE_RUNTIME_OVERRIDES` - Dict of runtime setting overrides

### 4.2 Missing Runtime Settings (NOT in GUI)

**Day Trading Guards:**
1. `ALLOW_DAY_TRADES` - Allow exits before min hold duration
2. `MIN_HOLD_SECONDS` - Min seconds to hold position

**Margin Requirements:**
3. `MIN_EQUITY_FOR_MARGIN` - Min equity for margin/short/FX

**Position Age Inference:**
4. `INFER_POSITION_HOLD_FROM_EXECUTIONS` - Infer position age from broker history
5. `INFER_POSITION_HOLD_LOOKBACK_DAYS` - Lookback window for inference

**IBKR Keep-Alive:**
6. `KEEP_ALIVE_INTERVAL_SECONDS` - Ping interval for IBKR

**Strike System:**
7. `STRIKE_MAX_CONSECUTIVE` - Max consecutive risk suppressions
8. `STRIKE_COOLDOWN_CYCLES` - Cycles to skip after strike limit

**Guard Block System:**
9. `GUARD_BLOCK_THRESHOLD` - Guard block streak before cooldown
10. `GUARD_BLOCK_COOLDOWN_CYCLES` - Cycles to skip after guard block

**Local Stops:**
11. `ALLOW_LOCAL_STOPS` - Allow client-side stops
12. `LOCAL_STOP_SYMBOLS` - Symbols requiring local stops (list)

### 4.3 Missing Crypto Routing Settings

**Crypto Exchange Routing:**
1. `CRYPTO_ROUTING_DEFAULT_EXCHANGE` - Default exchange (PAXOS/ZEROHASH)
2. `CRYPTO_ROUTING_OVERRIDES` - Per-symbol exchange override (dict)

---

## 5. Redundancy Analysis

### 5.1 TRUE Redundancies (Consider Removing)

**NONE FOUND** - All settings serve distinct purposes.

### 5.2 Settings That SEEM Redundant But AREN'T

1. **`SABBATH_ENABLED` vs `BOT_SABBATH`**
   - `BOT_SABBATH`: Runtime override (Auto/Force ON/Force OFF)
   - `SABBATH_ENABLED`: Profile default
   - **Verdict**: KEEP BOTH (runtime override pattern)

2. **`EXECUTE_TRADES` vs `IBKR_READ_ONLY`**
   - `EXECUTE_TRADES`: Master switch for ALL trading
   - `IBKR_READ_ONLY`: IBKR-specific safety (even if EXECUTE_TRADES=true)
   - **Verdict**: KEEP BOTH (defense in depth)

3. **`MAX_SCALE_INS_PER_LEG` vs `PROFILE_MAX_PYRAMID_ENTRIES`**
   - `MAX_SCALE_INS_PER_LEG`: Runtime global limit
   - `PROFILE_MAX_PYRAMID_ENTRIES`: Profile-specific ICC pyramiding
   - **Verdict**: KEEP BOTH (could consolidate, but serves different use cases)

4. **`FLATTEN_ON_EXIT` vs `INTRADAY_FLATTEN` vs `PROFILE_AUTO_FLATTEN_ON_CLOSE`**
   - `FLATTEN_ON_EXIT`: Flatten when bot EXITS/shuts down
   - `INTRADAY_FLATTEN`: Flatten at end of trading session
   - `PROFILE_AUTO_FLATTEN_ON_CLOSE`: Profile setting for auto-flatten at schedule windows
   - **Verdict**: KEEP ALL (different trigger conditions)

5. **`EMERGENCY_STOP_PCT` vs stop settings in profile**
   - `EMERGENCY_STOP_PCT`: Fallback/safety net for unprotected positions
   - Profile stops: ICC-based invalidation stops
   - **Verdict**: KEEP BOTH (safety net vs strategy stops)

### 5.3 Settings With Overlapping Names (Clarify)

1. **`PROFILE_COOLDOWN_*` appears in multiple places**
   - These are profile-level settings with env override capability
   - **Recommendation**: No change needed, pattern is consistent

2. **`COMMENTARY_LLM_TZ` vs `SABBATH_TIMEZONE` vs `PROFILE_SESSION_OVERLAP_TIMEZONE`**
   - These are intentionally synced in the GUI (shared timezone)
   - **Recommendation**: Document that changing one changes all three

---

## 6. Naming Improvements for Clarity

### Recommended Renames

1. **Current**: `MULTI_POSITION_ENABLED` + `MAX_CONCURRENT_POSITIONS`
   **Better**: `MULTI_SYMBOL_ENABLED` + `MAX_CONCURRENT_SYMBOLS`
   **Reason**: Clarifies it's about DIFFERENT symbols, not pyramid entries

2. **Current**: `PROFILE_MAX_PYRAMID_ENTRIES`
   **Better**: `PROFILE_MAX_PYRAMID_ENTRIES_PER_SYMBOL`
   **Reason**: Clarifies scope is per-symbol

3. **Current**: `MAX_SCALE_INS_PER_LEG`
   **Better**: `RUNTIME_MAX_SCALE_INS_PER_LEG` or `GLOBAL_MAX_SCALE_INS_PER_LEG`
   **Reason**: Clarifies it's a runtime/global limit

4. **Current**: `FLATTEN_ON_EXIT` / `INTRADAY_FLATTEN` / `AUTO_FLATTEN_ON_CLOSE`
   **Better**:
   - `FLATTEN_ON_BOT_EXIT` (when bot shuts down)
   - `FLATTEN_AT_SESSION_END` (intraday mode)
   - `PROFILE_AUTO_FLATTEN_AT_SCHEDULE_WINDOW` (profile setting)
   **Reason**: Clarifies when each triggers

---

## 7. Recommendations Summary

### High Priority Actions

1. **FIX CRITICAL BUG**: Remove duplicate field definitions in `models.py` (lines 401-437)

2. **Add Missing Profile Settings to GUI**:
   - Create new "Profile Advanced" tab for:
     - `candle_timeframe`, `market_poll_interval_seconds`, `ai_decision_interval_seconds`
     - Auto-schedule settings
     - ICC auto-entry settings
     - Crypto fractional/pair selector settings
     - Maker/taker preferences

3. **Add Missing Runtime Settings to GUI**:
   - Add to Runtime tab:
     - Day trading guards (`ALLOW_DAY_TRADES`, `MIN_HOLD_SECONDS`)
     - Position age inference
     - Strike/guard block system
     - Local stops configuration

4. **Clarify Max Positions vs Pyramiding**:
   - Update tooltip for `MAX_CONCURRENT_POSITIONS`: "Maximum number of DIFFERENT SYMBOLS that can be traded simultaneously"
   - Update tooltip for `PROFILE_MAX_PYRAMID_ENTRIES`: "Maximum pyramid entries PER SYMBOL (adds to winning positions)"

### Medium Priority Actions

5. **Consider Renaming** (but not required):
   - `MAX_CONCURRENT_POSITIONS` → `MAX_CONCURRENT_SYMBOLS`
   - Add "(per symbol)" suffix to pyramid settings

6. **Documentation**:
   - Add to settings help: "Max concurrent positions = across different symbols; Pyramid entries = within one symbol"
   - Document that Time tab settings sync across Sabbath/Commentary/Session

### Low Priority Actions

7. **Organize Settings Better**:
   - Consider splitting Strategy tab (too many settings)
   - Group related settings visually

8. **Add Validation**:
   - Warn if `MAX_PYRAMID_ENTRIES > MAX_SCALE_INS_PER_LEG`
   - Warn if `MULTI_POSITION_ENABLED=true` but no account risk cap set

---

## 8. Tab Organization Recommendations

### Current Tabs (13)
1. Bot - General bot settings
2. Time - Timezone/Sabbath/Astral
3. Market - Market data/symbols
4. Runtime - Runtime safeguards
5. Risk - Risk models + aggressive mode
6. Strategy - ICC structure + session + PDT
7. Scoring - ICC point-based scoring
8. Commentary - AI commentary settings
9. AI - AI provider settings
10. IBKR - IBKR broker settings
11. CCXT - CCXT broker settings
12. Benchmark - Position sizing calculator
13. Advanced (env) - Raw env var table

### Proposed New Tabs

**Option A: Add 2 New Tabs**
- **Profile Advanced** - Missing profile settings (auto-schedule, ICC auto-entry, crypto, pair selector, maker/taker)
- **Runtime Advanced** - Missing runtime settings (day trade guards, strikes, guard blocks, local stops)

**Option B: Reorganize Existing**
- Split **Strategy** into:
  - **Strategy: Structure** (ICC HTF/LTF/trend settings)
  - **Strategy: Sessions** (Session gate, overlap, auto-schedule)
  - **Strategy: Safety** (PDT, flips, cooldowns, pyramiding)

---

## 9. Settings Count Summary

| Category | Settings Exposed in GUI | Settings in Config | Missing from GUI |
|----------|------------------------|-------------------|------------------|
| **Profile Settings** | ~55 | ~86 | ~31 |
| **Runtime Settings** | 13 | ~28 | ~15 |
| **AI Settings** | 7 | 7 | 0 |
| **Market Settings** | 8 | 11 | 3 |
| **Broker Settings** | 15 (IBKR) + 8 (CCXT) | ~25 | ~2 |
| **Commentary** | 6 | 6 | 0 |
| **Total** | **~112** | **~163** | **~51** |

---

## 10. Conclusion

The trading bot has a comprehensive settings system with **NO truly redundant settings**. The user's concern about "Max positions vs Pyramiding" is based on naming confusion - these settings control orthogonal dimensions:

- **Max Concurrent Positions**: How many DIFFERENT symbols to trade
- **Max Pyramid Entries**: How many times to ADD to a SINGLE symbol

The main issues are:
1. **Critical code duplication bug** in models.py (must fix)
2. **51 settings not exposed in GUI** (31 profile + 15 runtime + 3 market + 2 broker)
3. **Naming could be clearer** to prevent confusion

All current GUI settings serve distinct purposes and should be kept. The focus should be on:
- Fixing the duplication bug
- Adding missing settings to the GUI
- Improving tooltips/naming for clarity
- Better visual organization of the Strategy tab (currently has 24 settings)

