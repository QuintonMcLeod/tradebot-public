# AI Handoff — Guillotine & SAR Emergency Fix Session

> [!CAUTION]
> **READ THIS ENTIRE DOCUMENT** before touching any code. This session fixed 8 critical bugs that were causing catastrophic losses. The bot lost $750+ in a single day due to these compounding failures. Every fix listed below is load-bearing — reverting any one of them will re-break the system.

---

## 1. Your Mission

**Monitor the live trading bot and recover NAV to $7,500+.**

Current NAV: **$5,751** (down from $6,442 at session start due to 8 compounding bugs).
Target: **$7,500** — ~$1,750 to recover.

The bot is running **v2.8.92** with tiered Guillotine (T1 -0.15R/80% + T2 -0.3R/80%) and Counter-Reversal (CR) active. Restarted at ~4:05 AM ET on March 6, 2026.

### Conversation ID
`008b5307-8281-4f9a-aa22-d19060855a8a`

### Conversation Artifacts
Located at: `/home/qchan/.gemini/antigravity/brain/008b5307-8281-4f9a-aa22-d19060855a8a/`

---

## 2. What Was Done This Session (8 Bug Fixes)

> [!IMPORTANT]
> **The Guillotine and SAR were COMPLETELY NON-FUNCTIONAL in live trading.** These are the two core features of the Forex Conductor strategy — without them, losses are uncapped and unreversed. All 8 bugs compounded: the Guillotine threshold was wrong, then the datetime import crashed the engine, then the broker couldn't execute partial closes, then SAR trades were killed by regime flip and EMA exits 5 minutes after entry.

### The 8 Fixes (v2.8.74 → v2.8.79)

| # | Bug | File | Impact | Fix |
|---|---|---|---|---|
| 1 | **Guillotine at -0.6R instead of -0.3R** | `forex_conductor.py` L612 | RTFM says 95% close at -0.3R. Was -0.6R — losses 2× too large before cutoff | Changed threshold to `-0.3` |
| 2 | **SAR stored as plain string** | `engine.py` L564-570 | `_reversal_pending[sym] = "long"` (string). Conductor's stale cleanup expected `(dir, timestamp)` tuple. Strings had `rev_time=None → age=9999s → stale → cleared immediately` | Changed to `("long", _dt.datetime.now(_dt.timezone.utc))` |
| 3 | **`datetime` import crashed every cycle** | `engine.py` L566 | `from datetime import datetime` inside a conditional shadowed the function-level `datetime` reference at L433, causing `UnboundLocalError` on EVERY cycle. **No exit signals fired at all.** | Changed to `import datetime as _dt` |
| 4 | **Broker `scale_out` used non-existent API** | `oanda_broker.py` L764 | `self.client.order.market()` doesn't exist in oandapyV20. **Guillotine scale_out always crashed.** | Rewrote to use `PositionClose` endpoint (same as `flatten_symbol`) |
| 5 | **Close fraction 80% instead of 95%** | `oanda_broker.py` L750 | Hardcoded `close_fraction = 0.80` instead of RTFM-specified 0.95 | Changed to `0.95` |
| 6 | **SAR killed by regime flip exits** | `safety_guard.py` L530 | SAR trades OPPOSE the HTF trend by design, but regime flip closed them in ~5 min | Added `is_sar_trade` exemption — SAR skips regime flip |
| 7 | **SAR killed by EMA cross exits** | `trend_rider.py` L303 | SAR entries inherently oppose EMA direction, triggering immediate EMA cross exit | Added `is_sar_trade` check — returns `None` for SAR trades |
| 8 | **SAR entered at F+ market scores** | `forex_conductor.py` L399 | FORCED SAR had **zero score gate** — entered with strat_score=40 (F+) | Added minimum B- (60) score requirement |

### Live Test Results

Test trade #2 (EURUSD 500 units long) confirmed:
- **Guillotine threshold fires at -0.3R** ✅ (synthetic test passed)
- **SAR reversal entry triggers after SL hit** ✅ (live FORCED SAR SHORT fired)
- **No more `Fatal error` crashes** ✅ (datetime fix confirmed)
- **Broker can execute scale_out** ✅ (PositionClose endpoint works)

---

## 3. Current Bot State (as of 2026-03-05 19:55 ET)

- **Version**: v2.8.79
- **NAV**: $5,751.43
- **Open Positions**: NONE (all closed during emergency stop)
- **Profile**: `forex_continuous`
- **Strategy**: Forex Conductor (regime-based router)
- **Bot PID**: 702145

### Key Settings
| Setting | Value | Notes |
|---|---|---|
| **Guillotine** | -0.3R, 95% close | Per RTFM — cuts losers fast |
| **SAR** | Enabled, 2.7% risk, 1R TP | Score gate ≥ 60 (B-) |
| **SAR max concurrent** | 1 | Prevents cascading losses |
| **SAR exemptions** | Regime flip + EMA cross | Only exits via SL or TP |
| **ATR trail** | 0.5R+ (tiered tightening) | Moves broker SL |
| **Trend Rider proximity** | 2.0× ATR | Widened from 1.0× this session |

### Today's Performance (the disaster)
```
Trades: 3W / 19L
PnL: -$711
Key winners: +$252 (USDJPY SL/TP), +$140 (USDCAD ranging TP), +$67 (USDJPY ranging TP)
Key losers: -$286 (EURUSD — no Guillotine, no SAR), -$164 (GBPJPY SL), -$123 (USDCHF regime flip)
```

---

## 4. Files Modified This Session

| File | Changes |
|---|---|
| `src/tradebot_sci/strategy/variants/forex_conductor.py` | Guillotine -0.6→-0.3R; stale SAR cleanup before entry loop; SAR score gate ≥60; ranging quick TP at 0.7R |
| `src/tradebot_sci/strategy/engine.py` | SAR reversal as tuple `(dir, timestamp)` using `import datetime as _dt` |
| `src/tradebot_sci/broker/oanda_broker.py` | scale_out: `PositionClose` instead of `client.order.market()`; close_fraction 80%→95% |
| `src/tradebot_sci/strategy/safety_guard.py` | SAR exemption from regime flip exits |
| `src/tradebot_sci/strategy/variants/trend_rider.py` | SAR exemption from EMA cross exits; proximity 1.0→2.0× ATR |

---

## 5. DO NOT TOUCH

> [!CAUTION]
> Every item below was the root cause of a bug in this session. Reverting ANY of them will re-break the system.

- **Guillotine threshold `-0.3`** in `forex_conductor.py` L614 — do NOT change to -0.6R or anything else. RTFM is explicit.
- **`import datetime as _dt`** in `engine.py` L566 — do NOT change to `from datetime import datetime`. It shadows the function-level reference and crashes every cycle.
- **`PositionClose` in `oanda_broker.py`** L760-770 — do NOT use `self.client.order.market()`. It doesn't exist in oandapyV20.
- **`close_fraction = 0.95`** in `oanda_broker.py` L750 — do NOT reduce. RTFM says 95%.
- **SAR exemptions** in `safety_guard.py` L530 and `trend_rider.py` L303 — SAR trades MUST skip regime flip and EMA cross exits. They exit only via SL or TP.
- **SAR score gate ≥ 60** in `forex_conductor.py` L407 — do NOT remove. Bot was entering at F+ scores without it.
- **SAR tuple format** in `engine.py` L565-570 — must be `(direction, timestamp)` tuple, NOT a plain string.

Also read `Documentation/PASSING_THE_BATON.md` Section 4 and `Documentation/AI_HANDOFF_MONITORING.md` Section 7 for do-not-touch lists from previous sessions.

---

## 6. How to Monitor

### Quick Health Check
```bash
# Current positions
cat /home/qchan/.config/tradebot-sci/data/oanda_tracked_positions.json | python3 -c "
import json,sys
d=json.load(sys.stdin)
if not d: print('NO POSITIONS')
for s,p in d.items():
    entry=float(p['entry_price']); sl=float(p.get('stop_loss',0))
    risk=abs(entry-sl); pnl=float(p['unrealized_pnl'])
    r=(pnl/(risk*abs(float(p['size']))/entry)) if risk>0 and float(p['size'])!=0 else 0
    print(f'{s} {p[\"direction\"]} pnl=\${pnl:+.2f} R={r:.2f} size={p[\"size\"]}')
"
```

### Verify Guillotine + SAR Working
```bash
# Guillotine: should see DE-RISK logs when trades hit -0.3R
grep 'DE-RISK\|SCALE OUT\|GUILLOTINE' /home/qchan/.config/tradebot-sci/logs/tradebot.log | tail -5

# SAR: should see FORCED SAR after SL hits
grep 'FORCED SAR\|SAR BLOCKED\|LOSS DETECTED' /home/qchan/.config/tradebot-sci/logs/tradebot.log | tail -5

# SAR exemptions: should see these when SAR trades are open
grep 'Regime-Flip SKIPPED.*SAR\|EMA cross skipped.*SAR' /home/qchan/.config/tradebot-sci/logs/tradebot.log | tail -5

# Fatal errors: should be NONE
grep 'Fatal error' /home/qchan/.config/tradebot-sci/logs/tradebot.log | tail -3
```

### Check NAV
```bash
grep "Account Summary" /home/qchan/.config/tradebot-sci/logs/tradebot.log | grep OANDA | tail -1
```

### What to Watch For
- ✅ `[CONDUCTOR] DE-RISK`: Guillotine firing at -0.3R
- ✅ `[CONDUCTOR] FORCED SAR`: Reversal entries after losses
- ✅ `[OANDA] SCALE OUT`: Broker successfully executing partial closes
- ✅ `SAR BLOCKED — market score X < 60`: Score gate preventing bad entries
- ❌ `Fatal error processing`: Engine crash (should be gone)
- ❌ `scale_out failed`: Broker can't execute partial close (should be gone)
- ❌ Trades entering with strat_score < 50: Score gate not working

---

## 7. RTFM Reference

> [!IMPORTANT]
> Read `Documentation/RTFM/32_CONDUCTOR_STRATEGY.md` for the full Conductor design. Key points:

1. **Guillotine**: 95% close at -0.3R. Turns $75 loss into $8 loss.
2. **SAR**: Immediate reversal on SL hit. 4.5% risk, 1R TP, cost-aware TP.
3. **Pyramids**: 30% at 1R, 4% every 0.5R after.
4. **ATR Trail**: 1.5× at 1R, 1.0× at 2R, 0.7× at 3R+.
5. **No fixed TP** — ATR trail handles exits.

---

## 8. Deploy Process

```bash
# Deploy + restart
cd "/home/qchan/Scripts/Trade by SCI/tradebot-sci-debug"
bash scripts/deploy.sh all
kill -9 $(pgrep -f "run_dev_bot.py"); sleep 2
nohup .venv/bin/python scripts/run_dev_bot.py --continuous > /dev/null 2>&1 &
```

### OANDA API (for emergency position management)
```bash
# API key location: ~/.config/tradebot-sci/.env.secrets (OANDA_API_KEY)
# Account ID: 001-001-20452563-002
# Environment: live (api-fxtrade.oanda.com)
```

---

## 9. What the Next AI Needs To Do

### Immediate: Monitor Recovery
1. Watch for entries — bot should only enter at B- (60+) scores
2. Verify Guillotine fires at -0.3R on any losing trade
3. Verify SAR fires after any SL hit (and stays open — not killed by regime flip/EMA)
4. Monitor NAV towards $7,500

### Investigation Needed
5. **Position sizing audit** — Earlier EURUSD trade was 4.2× oversized (lost $286 instead of ~$67). The 1% risk cap may not be enforced correctly. Check `risk_per_trade_pct` calculation in engine.py.
6. **Trade frequency** — 22 trades in one day is excessive. Consider adding a daily max trade limit or a daily loss circuit breaker.
7. **SAR TP** — RTFM says 1R TP. Verify `tp_dist = stop_dist * 2.0` at `forex_conductor.py` L450 is correct (this is 2R, not 1R — may need to be changed to `stop_dist * 1.0`).

### Previous Relevant Conversations
| ID | Topic |
|---|---|
| `008b5307` | **This session** — 8-bug Guillotine/SAR fix, NAV $6,442→$5,751 |
| `90d902e4` | Bot monitoring (stop_price bug, ATR trail fix, SAR stale) |
| `2ca3c3ed` | Pipeline unblock (5 critical bugs preventing all trades) |
| `458fe30c` | Strategy optimization (SAR + pyramiding + proven techniques) |
| `50d4d601` | Restoring original loss mitigation |

### Knowledge Items
- **Tradebot Technical Architecture** — `/home/qchan/.gemini/antigravity/knowledge/tradebot_technical_architecture_and_verification_infrastructure/`
- **Tradebot Governance and Deployment** — `/home/qchan/.gemini/antigravity/knowledge/tradebot_governance_and_deployment/`
