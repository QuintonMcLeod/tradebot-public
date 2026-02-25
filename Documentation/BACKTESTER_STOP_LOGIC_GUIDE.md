# Backtester Stop Logic & Loss Mitigation Guide

> **CRITICAL**: Read this document before modifying ANY exit logic in the backtester,
> StrategyEngine, SafetyGuard, or strategy variants. Every parameter described here
> was arrived at through extensive testing and represents the difference between
> +$710 profit and -$1000 loss.

## The Golden Configuration (Verified Feb 25, 2026)

**Verified PnL**: +$710 on $3,290 capital (14-day backtest, 5 symbols)

| Setting | Value | Location | WHY |
|---------|-------|----------|-----|
| ICC Core StructInval ATR mult | **0.5** | `icc_core.py:290` | Cuts losers at $7-$50 before full SL hit |
| ICC Core StructInval emergency_exit | **True** | `icc_core.py:301` | Bypasses 1h hold guard — acts immediately |
| Safety Guard StructInval | **DISABLED** | `safety_guard.py:504` | ICC Core handles its own; SG version was duplicate |
| Hold guard (engine.py) | **3600s hardcoded** | `engine.py:414` | Only `emergency_exit=True` bypasses this |
| ICC Core stop distance | **2.5x ATR** | `icc_core.py:232` | With 25-pip floor. NOT 4x ATR! |
| ICC Core structure stop buffer | **0.5x ATR** | `icc_core.py:236` | NOT 1.5x. Keep tight. |
| London Breakout | **9% WR, -$416** | — | Consider disabling. |
| risk_per_trade_pct | **0.045** (4.5%) | Profile setting | — |
| min_hold_hours | **1.0** | Profile setting | — |

## Exit Flow Architecture

```
ENTRY → SafetyGuard Churn Guard (2min) → Strategy check_exit_signal() → Hold Guard → Safety Guard

                                           ↓                              ↓             ↓
                                  ICC Core StructInval          Blocks close exits  ATR Armor, Greedy Exit,
                                  at 0.5x ATR                  for 1 hour UNLESS   Trailing, Regime Flip
                                  emergency_exit=True           emergency_exit=True
                                  → BYPASSES hold guard
```

### How Losses Get Mitigated to ~$7

1. **Trade enters** with 2.5x ATR stop (insurance, rarely hit)
2. **Within 15-60 minutes**: If price breaks swing structure by 0.5x ATR → ICC Core's
   `check_exit_signal()` fires `Structure Invalidation` with `emergency_exit=True`
3. **Emergency exit bypasses the 1-hour hold guard** → trade closes at candle close
4. **Loss is tiny** ($7-$15 = entry fees + small adverse movement) instead of full SL ($50-$100)
5. **Winners survive** because structure remains intact → reach TP at 2R ($80-$200)

### The R:R Math

- Average winner: **$109-$137** (reaches 2R target or gets trailing stop at profit)
- Average loser: **$7-$65** (cut by StructInval or SL)
- At 40-49% WR and 1.5:1 R:R → **profitable system**

## CRITICAL BUGS FOUND & FIXED (Feb 24-25, 2026)

### Bug 1: `emergency_exit` Changed from True to False

**When**: Between commit `4d1ee52d` (the $550 code) and a later deploy.
**Where**: `icc_core.py:301`
**Impact**: StructInval was blocked by the hold guard for 1 hour. Losers that
should have been cut at $7 grew to $50+ before the hold guard expired.
**Fix**: Set `emergency_exit=True` in ICC Core's `close_position_decision()`.

### Bug 2: Duplicate StructInval in Safety Guard

**When**: During centralization of exit logic into Safety Guard.
**Where**: `safety_guard.py:504-517`
**Impact**: StructInval fired twice — once from ICC Core (strategy path) and once
from Safety Guard (safety path). SG version used 1.5x ATR (later 3.0x) instead
of 0.5x, and had `emergency_exit=False`. This could cause conflicting exits.
**Fix**: Disabled Safety Guard StructInval (`if False and ...`). ICC Core owns it.

### Bug 3: Stop Widening (Wrong Direction)

**When**: Feb 24, this conversation.
**Where**: `icc_core.py` (4x ATR), `london_breakout.py` (2.5x ATR buffer), `orb_breakout.py` (2.5x ATR)
**Impact**: Wider stops = bigger losses when SL hit. The system was designed for
stops to be insurance (rarely hit) with StructInval cutting losers early.
**Fix**: Reverted to committed values (2.5x ATR, 0.5x buffer).

## Key Principle: "Wide Stops, Tight Invalidation"

The system works because:
- **Stops are far away** (2.5x ATR) = rarely hit = insurance only
- **Structure Invalidation is tight** (0.5x ATR) = fires on small breaks
- **StructInval bypasses hold guard** (`emergency_exit=True`) = acts immediately
- **Most exits are StructInval** at $7-$15 loss, NOT SL at $50-$100

**DO NOT**:
- ❌ Widen stops "to prevent SL hits" — they're already insurance
- ❌ Widen StructInval buffer — it must be tight (0.5x) to cut losers early
- ❌ Set StructInval `emergency_exit=False` — it MUST bypass the hold guard
- ❌ Move StructInval to Safety Guard — it belongs in ICC Core's `check_exit_signal()`
- ❌ Add `is_management` passthrough to hold guard — only `emergency_exit` should bypass

## Performance by Configuration (Feb 25, 2026, $3,290 capital)

| Config | WR | R:R | PnL | Notes |
|--------|-----|-----|-----|-------|
| **Original (pre-changes)** | 29% | 1.0:1 | **-$846** | Baseline, broken config |
| StructInval 3.0x + no emergency | 21% | 1.7:1 | -$680 | Better R:R but WR too low |
| StructInval 0.5x + emergency=True (SG) | 23% | 0.8:1 | -$931 | SG version fires for all strategies |
| **StructInval 0.5x + emergency=True (ICC Core only)** 2 sym | 32% | 1.5:1 | **-$408** | Correct placement |
| **Same + 5 symbols** | 40% | 1.7:1 | **+$176** | Diversification helps |
| **Same + 5 sym + no London** | **49%** | 1.5:1 | **+$710** | London is a drag |

## London Breakout Analysis

London Breakout is consistently the worst performer (9% WR, -$416 on 11 trades).
The "Failed Breakout" exit fires when price returns inside the London range,
but it closes at market price (full loss). Consider:
1. Disabling it entirely (saves $400+)
2. Adding breakeven-at-1R to London Breakout's `check_exit_signal()` (before the failed breakout check)
3. Adding tighter stops specifically for London Breakout

## Files Modified (Summary)

| File | Change | Status |
|------|--------|--------|
| `icc_core.py:301` | `emergency_exit=False` → `True` | ✅ Applied |
| `safety_guard.py:504` | StructInval disabled (duplicate) | ✅ Applied |
| `engine.py` | Reverted to committed (original hold guard) | ✅ Applied |
| `icc_core.py:232-246` | Stops reverted to 2.5x ATR | ✅ Applied |
| `london_breakout.py` | Reverted to committed (no stop buffer) | ✅ Applied |
| `orb_breakout.py` | Reverted to committed (no stop buffer) | ✅ Applied |
