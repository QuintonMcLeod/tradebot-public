# Auditor Intake — Responses
**From:** Dev Team  
**Date:** February 18, 2026 · 18:34 EST  
**Re:** Answers to all 6 pre-audit questions

> [!CAUTION]
> **Several of your questions reference stale artifacts and pre-fix code.** The previous auditor's UI audit triggered a large batch of fixes that were completed today. Before proceeding, please be aware:
> 
> - **`CHANGELOG_LAST_24H.md`** and **`AI_HANDOFF_PROMPT.md`** — These documents describe the codebase state *before* today's UI audit fixes. The `TradingProfileSettings` import issue referenced in Q2 was resolved in a prior session. Do not treat these documents as current.
> - **`optimize_strategies.py`** (Q6) — This is a **legacy one-off script**, not the canonical backtester. It predates the cartridge-based `mega_backtester.py` system. The hardcoded `capital = 870.0` is a snapshot from an old optimization run, not a design choice.
> - **Line numbers** in the prior audit report (v4/v5) are now stale — today's fixes removed ~30 lines and restructured several sections of `settings_integrated.js`.
> 
> **Please re-pull the current `settings_integrated.js` and `models.py` before beginning your audit.** The previous auditor's v5 re-audit already made this mistake (checked old line numbers and marked fixed items as "UNFIXED").



## 1. Scope Confirmation

Yes — the next audit should cover **strategy engine, scoring/confluence, and broker execution**. Suggested order:

1. **Strategy Engine** (`strategy/engine.py`) — orchestrates variant loading, entry/exit priority, and the STRATEGY_REGISTRY
2. **Confluence & Scoring** (`strategy/variants/*.py`) — individual strategy `evaluate()` logic, ICC scoring weights
3. **Broker Execution** (`brokers/`) — CCXT, IBKR, OANDA order placement, fill handling, slippage/fee modeling
4. **Safety Guard** (`safety/safety_guard.py`) — the runtime gatekeeper that sits between engine and broker

If there's a preference to start with a narrower subsystem, strategy engine + safety guard is the highest-value pair.

---

## 2. Known Issues

- **`TradingProfileSettings` import deletion** — This was **resolved** in a prior session. The class definition was accidentally removed from `models.py` and has been restored. No other model classes were affected.
- **No other known broken classes or functions** at this time. The UI audit we just completed touched only `settings_integrated.js` (frontend) and one field removal in `models.py` (`trailing_stop_enabled` in `PositionExitConfig` — resolved split-brain with `PerformanceSettings`).
- **Position Lock** was recently implemented to prevent strategy whiplash (rapid long/short flipping on the same symbol).

---

## 3. Live vs. Backtest Discrepancies

The Friday live-trading-vs-0-backtest-trades discrepancy is **still outstanding**. The root cause is **data granularity**: the backtester uses local JSON files with potentially incomplete candle coverage (gaps during off-hours, missing ticks), while the live bot receives real-time streaming data from IBKR/CCXT. Specific known factors:

- Session Gate and Opening Range Sentry filters may not fire identically in backtest (time-zone edge cases)
- The backtester's `LocalJSONProvider` may lack data for the exact timeframe the live bot traded

This is a known limitation, not a bug in the engine itself.

---

## 4. Active Strategy Variants

There are **20 registered strategies** in `STRATEGY_REGISTRY` (`strategy/engine.py:68-89`):

| Strategy | Production Status |
|---|---|
| `icc_core` | ✅ **Primary** — default for most profiles |
| `robocop` | ✅ **Active** — AI-assisted entry/exit |
| `meta_sci` | ✅ **Active** — multi-strategy consensus |
| `rubberband_reaper` | ✅ **Active** — mean reversion |
| `supply_demand` | ✅ **Active** — S/D zone trading |
| `orb_breakout` | ✅ **Active** — Opening Range Breakout (NY) |
| `evolution` | ✅ **Active** — adaptive strategy |
| `aggregator` | ✅ **Active** — multi-strategy aggregation |
| `trend_rider` | 🟡 Experimental |
| `session_momentum` | 🟡 Experimental |
| `bearish_engulfing` | 🟡 Experimental |
| `london_breakout` | 🟡 Experimental |
| `hyper_scalper` | 🟡 Experimental |
| `quantum` | 🟡 Experimental |
| `mean_reversion` | 🟡 Experimental |
| `volatility_breakout` | 🟡 Experimental |
| `crypto_rsi_macd` | 🟡 Crypto-specific |
| `crypto_vwap_reversion` | 🟡 Crypto-specific |
| `crypto_double_macd` | 🟡 Crypto-specific |
| `crypto_grid` | 🟡 Crypto-specific |

The first 8 are **production-active** and should be the audit focus. The remaining 12 are experimental or crypto-specific variants that see limited use.

---

## 5. Test Health

There are **46 test files** in `tests/`. Test suite status:

- Tests were last validated during the `TradingProfileSettings` restoration work. 
- The import fix that restored `TradingProfileSettings` unblocked the entire test suite.
- **Recommendation:** Run `pytest tests/ -x --tb=short` as part of this audit to get a fresh baseline. If you'd like, we can run it right now before you begin.

---

## 6. Backtester Canonical Status

`tools/optimize_strategies.py` is **NOT the canonical backtester**. It's a narrow one-off script with hardcoded values (`capital = 870.0`, `RubberbandReaperStrategy` only).

The **canonical backtester** is:

### `tools/mega_backtester.py`
- **Cartridge-based architecture** — uses pluggable "cartridges" from `tools/cartridges/` 
- Supports any strategy via `--strategy` override flag
- Configurable capital, symbols, and date ranges per cartridge
- Shared simulation engine: `src/tradebot_sci/simulation/backtester.py`

Available cartridges include:
- `marathon_jan_2026` — full January 2026 replay
- `meta_sci_marathon` — Meta-SCI multi-strategy
- `clash_marathon_jan_2026` — strategy head-to-head comparison

**Usage:** `python -m tools.mega_backtester <cartridge_name> [--strategy override] [--symbol override]`

The `optimize_strategies.py` and `verify_jan_backtest.py` (now in `tools/archive/`) are legacy scripts that predate the cartridge system.
