# AI Handoff — Strategy Optimization Session

> [!CAUTION]
> **READ THIS ENTIRE DOCUMENT** before touching any code. Previous AI sessions have broken working configurations by not reading the documentation first.

---

## 1. What Was Done This Session

### Conversation ID
`458fe30c-fa89-4a37-b6b1-cab5f3e32de0`

### Conversation Artifacts
Located at: `/home/qchan/.gemini/antigravity/brain/458fe30c-fa89-4a37-b6b1-cab5f3e32de0/`
- `walkthrough.md` — Results summary
- `implementation_plan.md` — Research-based strategy plan
- `task.md` — Task checklist

### What The User and I Discussed

1. **Strategy presets** — The user wanted strategies to be "presets" that auto-configure other bot settings (risk, pyramids, trends). When a user picks a strategy, the toggles change everywhere. The core entry/exit logic differs per strategy, but risk management settings are preset per strategy.

2. **Asset class pages** — The user wants per-asset-class settings (forex, crypto, stocks, etc.) in the sidebar UI. One profile should be able to run different strategies per asset class. This was discussed but **NOT yet implemented** — it requires a config remodel.

3. **Strategy optimization via SAR and pyramiding** — We identified ICC Core + SAR at 1.6% risk as the sweet spot (+$3,564). Applied to all strategies but only ICC Core and Yo-Yo benefit from SAR.

4. **Research-based strategy fixes** — User told me to stop experimenting with my own ideas and instead Google proven strategies and borrow their techniques. This produced:
   - **Yo-Yo v3 SAR**: -$2,224 → **+$1,220** using proven PSAR + 50 SMA trend filter + directional candle confirmation
   - **RoboCop**: -$1,085 → **-$697** using ICT swing-based stops
   - **Supply Demand**: -$706 → **-$599** using tight zone-edge stops
   - **Session Momentum**: -$435 → **-$375** using ORB VWAP stops

5. **ATR trailing stops (in-progress)** — Applied proven ATR trailing stops (trail behind price after 1R) to all remaining losers. This is still being tested when the session ended. The latest code has:
   - Evolution: 0.75× ATR trail
   - Quantum: 1.0× ATR trail (had import bug — **fixed**: `hold_decision` added to imports)
   - Supply Demand: 0.5× ATR trail  
   - RoboCop: 0.75× ATR trail + Guillotine
   - Session Momentum: 0.5× ATR trail

### Current Strategy Scoreboard (14-day, 10 forex pairs, $7,500 capital)

| Strategy | Config | Trades | WR% | PnL | Status |
|---|---|---|---|---|---|
| **ICC Core** | SAR + 1.6% risk | 217 | 68% | **+$3,564** | ✅ Deployed |
| **Yo-Yo v3** | SAR | 12 | 83% | **+$1,220** | ✅ Deployed |
| **Mean Reversion** | 2.0% risk | 12 | 67% | **+$881** | ✅ Deployed |
| **Bearish Engulfing** | 2.5% risk | 33 | 61% | **+$11** | ✅ Deployed |
| London Breakout | 0.5% risk | 12 | 42% | -$55 | 🟡 Near breakeven |
| Session Momentum | VWAP stop + trail | 9 | 33% | -$344 | ❌ In progress |
| Evolution | 1.0× ATR + trail | 174 | 70% | -$626 | ❌ In progress |
| Supply Demand | Zone-edge + trail | 171 | 57% | -$460 | ❌ In progress |
| RoboCop | Swing + trail | 123 | 59% | -$697 | ❌ In progress |
| Quantum | 2× ATR + trail | 171 | 57% | -$1,515 | ❌ In progress |
| **Forex Conductor** | SAR + Guillotine + fixed ADX | 30 | 30% | **+$603** | ✅ Deployed |

### ADX Threshold Fix (Session 2ca3c3ed)

> [!IMPORTANT]
> The ADX thresholds in `trend_consensus.py` were tuned down for forex. The old thresholds (trending=30, ranging=20) were designed for crypto/stocks where ADX routinely exceeds 30. Forex on 1H barely reaches 20, so the Conductor was stuck classifying 100% of bars as "ranging".

**Changes in `trend_consensus.py` `_classify_regime()`:**
| Parameter | Old | New | Why |
|---|---|---|---|
| Trending regime | ADX > 30 | ADX > 20 | Forex rarely hits 30 on 1H |
| Ranging regime | ADX ≤ 20 | ADX ≤ 12 | Forex with ADX 12-20 is transitional, not ranging |
| Transitional regime | ADX 20-30 | ADX 12-20 | Opens up transitional for Session Breakout |
| Chop threshold (profile) | 15 | 8 | ADX < 8 is real chop |
| ADX gate (profile) | 20 | 12 | Let forex trends through |

**Guillotine fix in `models.py` `RuntimeSettings`:**
- `scale_out_fraction` default: **0.5 → 0.95** (was closing only 50% instead of 95%)
- This is the Conductor's core loss-cutting mechanism: close 95% at -0.3R, leave 5% for SAR
- Impact: Avg loss dropped from $93 → $45, R:R jumped from 1.53 → 3.81

---

## 2. Project Structure

### Root Directory
`/home/qchan/Scripts/Trade by SCI/tradebot-sci-debug/`

### Key Directories
| Path | Purpose |
|---|---|
| `src/tradebot_sci/strategy/variants/` | All 25 strategy implementations |
| `src/tradebot_sci/strategy/engine.py` | Strategy engine (Exit > Entry priority) |
| `src/tradebot_sci/strategy/safety_guard.py` | SafetyGuard (ATR Armor, Regime Flip, Stale Sniper) |
| `src/tradebot_sci/strategy/decisions.py` | Trade decision factories (`hold_decision`, `close_position_decision`, etc.) |
| `src/tradebot_sci/strategy/icc_signals.py` | ICC Core signals (sweep, BOS, FVG, NTZ, indication detection) |
| `src/tradebot_sci/simulation/backtester.py` | The backtester (~2000 lines) |
| `src/tradebot_sci/config/models.py` | Pydantic config models (Settings, ProfileSettings) |
| `src/tradebot_sci/electron_gui/` | Electron GUI (`settings_integrated.js` has strategy presets) |
| `data/oanda_14day/` | 14-day OANDA forex data for backtesting |
| `Documentation/` | All RTFM documentation |
| `scripts/deploy.sh` | Deploy script (`bash scripts/deploy.sh master`) |

### Deploy Process
```bash
cd "/home/qchan/Scripts/Trade by SCI/tradebot-sci-debug"
git add -A && git commit -m "message"
bash scripts/deploy.sh master
```

---

## 3. RTFM Documentation — READ THESE FIRST

> [!IMPORTANT]
> The user's #1 rule: **RTFM** (Read The Manual). Read ALL of these before making any changes.

| Document | Path | What It Covers |
|---|---|---|
| **AGENTS.md** | `AGENTS.md` | No watermarks, no attribution tags, clean comments only |
| **Backtester Rules** | `Documentation/BACKTESTER_RULES.md` | Futures-style capital model, PnL calculation, stop/TP direction handling. **DO NOT** modify `_calculate_pnl()` or capital bookkeeping |
| **Stop Logic Guide** | `Documentation/BACKTESTER_STOP_LOGIC_GUIDE.md` | ICC Core's "Wide Stops, Tight Invalidation" architecture. StructInval at 0.5× ATR with `emergency_exit=True`. **DO NOT** widen StructInval or set emergency_exit=False |

### Critical Rules from Documentation
1. **Entry: `capital -= entry_fee`** (NOT full position value — this is futures, not spot)
2. **Exit: `capital += net_pnl`** (NOT pnl + principal)
3. **Use `_calculate_pnl(direction, entry, exit, size)`** — handles long AND short
4. **Long stops trigger on `bar.low <= stop_price`**, Short on `bar.high >= stop_price`
5. **ICC Core StructInval** at 0.5× ATR with `emergency_exit=True` — this is the core loss mitigation system. **DO NOT CHANGE IT.**

---

## 4. DO NOT TOUCH: Conductor Strategy & Friends

> [!CAUTION]
> **The Forex Conductor strategy (`forex_conductor.py`, 30KB, 606 lines) and all strategies it depends on MUST NOT be modified.** It is a regime-based router that is separate from the strategy optimization work.

### What the Conductor Does
`forex_conductor.py` routes to different strategies based on market regime:
- `trending` → EMA Trend Rider
- `ranging` → Mean Reversion  
- `transitional` → Session Breakout
- `choppy` → No entry

It has its own sophisticated exit logic (rising floor, early reversal, sub-strategy exits) and cooldown system.

### Files NOT to Modify
| File | Reason |
|---|---|
| `forex_conductor.py` | The conductor router itself (606 lines, complex regime routing) |
| `trend_rider.py` | Used by Conductor for trending regimes |
| `meta_sci.py` | Meta-SCI tournament judge (33KB, independent system) |
| `icc_core.py` | ICC Core with StructInval (already tuned, +$710 proven config) |
| `icc_core_standalone.py` | ICC Core SAR variant (already +$3,564 profitable) |
| `safety_guard.py` | SafetyGuard exit logic (Regime Flip, ATR Armor, Stale Sniper — all tuned) |
| `engine.py` | Strategy engine hold guard (emergency_exit bypass is critical) |
| `backtester.py` | Core simulation — capital bookkeeping must not change |

### Why
These strategies are either already profitable or are complex systems with many interdependencies. Changing them risks breaking working configurations — which has happened multiple times in past sessions.

> [!WARNING]
> **Exception: `trend_consensus.py` ADX thresholds were intentionally lowered (session 2ca3c3ed).** The old values (30/20/15) were too high for forex. If reverting code, do NOT revert the ADX threshold changes in `_classify_regime()`. The Conductor depends on these forex-tuned values.

---

## 5. How to Program Strategy Variants

### Strategy Interface
Every strategy extends `BaseStrategy` and implements:
```python
class MyStrategy(BaseStrategy):
    def __init__(self):
        super().__init__("My Strategy")
    
    def check_entry_signal(self, snapshot, gates, open_position=None, **kwargs):
        """Return AITradeDecision or None"""
        ...
    
    def check_exit_signal(self, snapshot, open_position, gates, **kwargs):
        """Return AITradeDecision (hold/close/scale_out) or None"""
        ...
```

### Key Decision Types (from `decisions.py`)
```python
# Stand aside (don't enter)
stand_aside_decision(symbol, timeframe, reason)

# Enter a trade
AITradeDecision(symbol, timeframe, bias, phase, action="enter_long"/"enter_short",
    entry_price, stop_loss, take_profit, risk_per_trade_pct, ...)

# Hold with stop adjustment (trailing stop)
hold_decision(symbol, timeframe, reason, stop_loss=new_stop)

# Close position
close_position_decision(symbol, timeframe, reason, emergency_exit=True/False)

# Scale out (partial close)
AITradeDecision(..., action="scale_out", notes="reason")
```

### Available Indicators (from `icc_signals.py`)
```python
from tradebot_sci.strategy.icc_signals import (
    calculate_atr,          # ATR(14)
    detect_ntz,             # No Trade Zone (consolidation range)
    detect_indication,      # BOS/CHoCH detection  
    detect_liquidity_sweep, # Sweep detection
    detect_fair_value_gap,  # FVG detection
)
from tradebot_sci.market.indicators import calculate_sma  # SMA
```

### The Exit Flow (Priority Order)
```
SafetyGuard Churn Guard (2min) → Strategy check_exit_signal() → Hold Guard (1h) → SafetyGuard
```
- `emergency_exit=True` on close_position_decision **bypasses the 1h hold guard**
- `hold_decision(stop_loss=...)` moves the stop — the backtester respects this
- `action="scale_out"` triggers partial close at `scale_out_fraction` (default 0.95)

---

## 6. How to Run Backtests

Full batch test script pattern (run from project root):
```bash
cd "/home/qchan/Scripts/Trade by SCI/tradebot-sci-debug"
PYTHONPATH=src:. python3 -c "<see backtesting pattern in conversation artifacts>"
```

Key parameters in the profile:
- `strategy_variant` — strategy name (e.g., 'evolution', 'quantum', 'yoyo')
- `risk_per_trade_pct` — risk as decimal (0.01 = 1%)
- `stop_and_reverse_enabled` — SAR on/off
- `scale_out_fraction` — fraction to close on scale_out (0.95 = 95%)
- `icc_entry_score_threshold` — ICC Core entry quality gate (60.0)

Data: `data/oanda_14day/` contains 14-day OANDA forex data (Feb 13-26, 2026) for 10 pairs.

---

## 7. Strategy Presets (GUI)

Strategy presets are defined in two places in `settings_integrated.js`:

1. **Strategy descriptions**: `STRATEGY_DESCRIPTIONS` object (~line 840)
2. **Preset configs**: `STRATEGY_PRESETS` object (~line 910)

When a user selects a strategy, `applyStrategyPreset()` auto-applies the preset to the UI.

### Current Optimal Preset Configs
| Strategy | Risk | SAR | Key Setting |
|---|---|---|---|
| ICC Core Standalone | 1.6% | ✅ | SAR sweet spot |
| Mean Reversion | 2.0% | ❌ | Higher risk for fewer trades |
| Bearish Engulfing | 2.5% | ❌ | Highest risk for lowest trade count |
| London Breakout | 0.5% | ❌ | Low risk for protection |
| Yo-Yo | 1.0% | ✅ | SAR essential, SMA50 filter in code |

---

## 8. What the Next AI Needs To Do

### Immediate: Finish Testing ATR Trailing Stops
1. Run the batch test that was interrupted (Round 13b)
2. **Revert trailing stops that make things worse** — Evolution trailing made it worse (-$428 → -$626)
3. **Keep trailing stops that help** — S&D improved -$598 → -$460 with trailing
4. **Fix Yo-Yo SAR regression** — In Round 13, Yo-Yo SAR went from +$1,220 (12T) to -$542 (204T). This is likely because the trailing stop exit is interfering with SAR mechanics. The fix may be to disable trailing stop when SAR is enabled (let the SAR reversal handle exits).

### Medium Term
5. **Research more specific proven techniques** for each remaining loser. The key lesson: **Google proven strategies, borrow their techniques, apply and test.** Stop experimenting with theory.
6. **Per-asset-class settings UI** — Config remodel so one profile can run different strategies per asset class.

### Important Lessons From This Session
- **SMA trend filter is the #1 improvement** — filtering Yo-Yo trades against 50 SMA eliminated most losses
- **Swing-based stops** work for strategies with quality entries (Yo-Yo, RoboCop), but are too tight for weak entries (Evolution, Quantum)
- **SAR only works with ICC Core and Yo-Yo** — all others get worse
- **Regime Flip profit guard at `r < 1.0` is essential** — raising it to `r < 0.0` crashed ICC Core from +$3,564 to -$1,859!
- **ATR trailing stops** (trail behind price after 1R) show promise for S&D and Session Momentum
- **Don't invent** — Google what's proven to work, borrow those techniques

### Knowledge Items
- **Tradebot Core Infrastructure and Execution Safety** — at `/home/qchan/.gemini/antigravity/knowledge/tradebot_financials_and_execution_safety/`

### Previous Relevant Conversations
| ID | Topic |
|---|---|
| `50d4d601` | Restoring Original Loss Mitigation ($550 profit config) |
| `61d3017b` | Refining Meta-SCI Judge |
| `344e0ec9` | Fixing Chart Auto-Update |
| `927f2eba` | Fixing Missing Settings (CONFIG_MAP) |
| `2ca3c3ed` | ADX threshold fix, Guillotine fix, Forex Conductor +$603 |
