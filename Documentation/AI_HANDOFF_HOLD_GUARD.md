# AI Handoff — Hold Guard & Live Bot Alignment Session

> [!CAUTION]
> **READ THIS ENTIRE DOCUMENT** before touching any code. This session fixed the root cause of why the live bot performs poorly compared to the backtester. The core issue was timing: the live bot used wall-clock time for trade management while the backtester uses candle timestamps. Every fix below is interdependent — breaking one re-breaks the others.

---

## 1. Your Mission

**Continue monitoring and tuning the live bot's performance, now that it is aligned with the backtester's timing.**

The bot is currently in **Weekend Sabbath/Replay mode** (switches back to Oanda live at Saturday sunset, before Sunday market open). All changes are verified working in replay mode.

### Conversation ID
`f6a327f3-c60e-4e22-9396-70eadf4a4c08`

### Conversation Artifacts
Located at: `/home/qchan/.gemini/antigravity/brain/f6a327f3-c60e-4e22-9396-70eadf4a4c08/`

---

## 2. The Core Problem Solved

**The live bot was exiting trades in 16 seconds. The backtester holds trades for 15 minutes (median).**

The Hold Guard (which prevents panic-exits) was set to 16 seconds in replay mode and 300 seconds in live mode — both using wall-clock time. The backtester naturally holds trades for at least 5 minutes (one candle) because it processes data bar-by-bar. This fundamental timing mismatch meant:

- Guillotine triggered before the market had time to move
- SAR never activated (trades exited before they could reach SL)
- Trend detection systems were ignored (exits fired before trends developed)

---

## 3. What Was Done This Session (6 Fixes)

> [!IMPORTANT]
> The first 3 fixes are the critical pipeline changes. Fixes 4-6 are cascading bugs discovered during testing.

| # | Bug | File | Fix |
|---|---|---|---|
| 1 | **ICC pre-filter blocking 99% of entries** | `cycle.py` | Removed `score_icc_grade()` pre-filter in `build_candidate_list()`. It ran before `engine.decide()` with a neutral-trend snapshot, blocking almost all entries. The backtester calls `engine.decide()` directly. |
| 2 | **Hold Guard: wall-clock time, wrong duration** | `engine.py` L427-461 | Changed from `datetime.now()` to `snapshot.candles[-1].timestamp` for age calculation. Set hold period to **900s (15 minutes)** based on actual backtester data (695 trades, median=15m). Removed separate replay/live branching. |
| 3 | **Paper broker: entry_time in wrong time domain** | `paper_broker.py` L101-115 | `_now()` returned `datetime.now()` (wall-clock 2026-03-07) while Hold Guard compared against candle timestamps (2026-01-28), producing **negative age (-2,118,128s)**. Fixed to return `sim_time` from replay provider during replay mode. |
| 4 | **Day Enforcer: 613h phantom age** | `engine.py` L484-490 | SafetyGuard received `sim_time=None` (fell through to `datetime.now()`), but `entry_time` was now in candle-time domain. Fixed by passing `candle_now` to `SafetyGuard.augment_exit_decision()`. |
| 5 | **Replay provider: only 2/7 symbols loading** | `replay_provider.py` L80-130 | Day picker used reference symbol only. EURUSD/GBPUSD had extra data from live trading, so it picked Feb 3 where other symbols had 0 candles. Fixed to intersect valid days across ALL symbols. |
| 6 | **Trend Rider: 4-pip stops eaten by spread** | `trend_rider.py` | Added 15-pip minimum stop distance floor. ATR on quiet data produced stops smaller than the spread. |

### Backtester Duration Data (695 Trades, 14 Days)

This is the **empirical data** that drove the Hold Guard calibration:

| Metric | All | Wins (62) | Losses (633) |
|---|---|---|---|
| **Average** | 32m | 75m | 28m |
| **Median** | 15m | — | — |
| **Min** | 5m | 5m | 5m |

Distribution: 69% of trades last 15-30m, 12% last 1-4h, 9% last 30m-1h.

### Verified Replay Results (Feb 23, 2026)

After all fixes, 5 trades with correct durations:

| Duration | Exit | PnL |
|---|---|---|
| **15m** | Guillotine T1 -0.61R (80% cut) | -$34.80 |
| **20m** | Guillotine T2 -0.48R (80% cut) | -$6.23 |
| **45m** | Session Momentum: Time exit | -$1.48 |
| **15m** | Higher-Low Invalidation | -$44.58 |
| **30m** | SL Hit | -$17.38 |

✅ Hold Guard correctly blocks exits at 5m and 10m (age 300s, 600s < 900s)
✅ Day Enforcer shows realistic hours (not 613h phantom)
✅ Guillotine cascade works: decreasing PnL per cut ($34 → $6 → $1)
✅ All 7 symbols loading in replay panel

---

## 4. Files Modified This Session

| File | Changes |
|---|---|
| `src/tradebot_sci/runtime/cycle.py` | Removed ICC pre-filter in `build_candidate_list()` — entries now go directly through `engine.decide()` |
| `src/tradebot_sci/strategy/engine.py` | Hold Guard: candle-time based (900s), uses `snapshot.candles[-1].timestamp`; SafetyGuard `sim_time` set to `candle_now` |
| `src/tradebot_sci/broker/paper_broker.py` | `_now()` returns `sim_time` from replay provider in replay mode; added `entry_time`, `scale_out` handler, `trade_results.add_result()` on close |
| `src/tradebot_sci/market/replay_provider.py` | Day picker intersects valid days across ALL symbols (was reference-only) |
| `src/tradebot_sci/strategy/variants/trend_rider.py` | 15-pip minimum stop distance floor |

---

## 5. DO NOT TOUCH

> [!CAUTION]
> These changes are interdependent. Breaking one re-breaks the timing alignment.

- **`snapshot.candles[-1].timestamp` in engine.py** — Do NOT revert to `datetime.now()` or `current_bar_time` for position age. The candle timestamp is the ONLY time reference that works identically in live, replay, and backtest modes.
- **`HOLD_GUARD_SECONDS = 900`** — Do NOT reduce below 300 (5 minutes = backtester structural minimum). 900 = 15m = median backtester trade duration. Reducing it re-introduces premature exits.
- **`_now()` in paper_broker.py returning `sim_time`** — Do NOT revert to `datetime.now()`. Without this, `entry_time` and Hold Guard age are in different time domains (negative ages in replay, false Day Enforcer Emergency exits).
- **`_safety_sim_time = candle_now`** — Do NOT remove. SafetyGuard's Day Enforcer uses this for `hours_held` calculation. Without it, positions appear 600+ hours old.
- **Day intersection in replay_provider.py** — Do NOT revert to single-reference-symbol day picker. Some symbols have extra data from live trading that others don't.
- **ICC pre-filter removal in cycle.py** — Do NOT re-add `score_icc_grade()` before `engine.decide()`. The backtester doesn't use it, and it blocks entries with neutral-trend snapshots.

Also read `Documentation/AI_HANDOFF_GUILLOTINE_SAR.md` Section 5 and `Documentation/AI_HANDOFF_PROMPT.md` Section 4 for do-not-touch lists from previous sessions.

---

## 6. How to Monitor

### Quick Health Check
```bash
# Check replay status
grep "REPLAY" ~/.config/tradebot-sci/logs/bot_stdout.log | tail -5

# Check Hold Guard is working (ages should be positive, 300-900s range)
grep "HOLD GUARD" ~/.config/tradebot-sci/logs/bot_stdout.log | tail -5

# Check Day Enforcer (hours_held should be < 24h, NOT 600+)
grep "Day Enforcer" ~/.config/tradebot-sci/logs/bot_stdout.log | tail -5

# Paper trade results
python3 -c "
import json
data = json.load(open('/home/qchan/.config/tradebot-sci/data/paper_trade_results.json'))
total=len(data); wins=sum(1 for t in data if t['is_win'])
print(f'Trades: {total}, Wins: {wins}, WR: {wins/total*100:.0f}%' if total else '0 trades')
print(f'PnL: \${sum(t[\"pnl_usd\"] for t in data):.2f}')
for t in data:
    dur = t.get('duration_seconds',0)
    print(f'  {t[\"symbol\"]:8s} {t[\"side\"]:5s} \${t[\"pnl_usd\"]:>8.2f} {dur/60:>5.0f}m {t.get(\"exit_reason\",\"\")[:55]}')
"
```

### What to Watch For
- ✅ `age XXXs < 900s` — Hold Guard blocking exits correctly
- ✅ Trade durations of 15-45 minutes — matches backtester
- ✅ Guillotine cascade: first cut large, subsequent cuts smaller
- ✅ All 7 symbols in the decision panel
- ❌ `age -XXXXXXs` — Time domain mismatch (should be fixed)
- ❌ `Day Enforcer: Emergency (600+h` — Phantom age (should be fixed)
- ❌ Trades exiting in < 5 minutes — Hold Guard not working

---

## 7. Sabbath / Replay Lifecycle

```
Friday Sunset → [Sabbath Mode] → Saturday Sunset → [Oanda Live Mode]
                 ↓                                   ↓
          Paper Broker +                        Real Oanda Broker +
          Replay Provider                       Live Market Data
          (candle_history data)                  (Sunday 5PM ET market open)
```

The bot automatically swaps to Oanda at **Saturday sunset** (before Sunday market open). Code: `loop.py` L1232-1254.

---

## 8. Deploy Process

```bash
# Deploy + restart
cd "/home/qchan/Scripts/Trade by SCI/tradebot-sci-debug"
bash scripts/deploy.sh all
pkill -f "run_dev_bot.py"; sleep 2
nohup .venv/bin/python scripts/run_dev_bot.py --continuous > /dev/null 2>&1 &
```

---

## 9. What the Next AI Needs To Do

### Immediate: Verify Sunday Live Trading
1. After market opens Sunday 5PM ET, confirm bot switched to Oanda (no more REPLAY logs)
2. Verify Hold Guard fires correctly with LIVE Oanda data (ages should be positive, 300-900s range)
3. Verify Guillotine and SAR activate on live trades
4. Monitor first 5-10 live trades for correct duration (15m+ median)

### Investigation Needed
5. **Win rate improvement** — The replay tests showed 0% WR (all ranging/choppy market). The backtester shows 9% WR (62/695). Need to run more replay days with trending data to verify strategy logic.
6. **Backtest the full 3-month candle_history** — Data exists in `~/.config/tradebot-sci/data/candle_history/` covering Dec 7 2025 – Mar 7 2026. Use `/tmp/run_conductor_backtest.py` as a starting point.
7. **Intelligent exit logic** — User wants Hold Guard to use trailing stops or other intelligent factors to decide exits, not just a flat timer. Consider replacing the flat 900s guard with a candle-count system that checks trailing profit after N candles.
8. **Position sizing** — Check if risk_per_trade_pct is being enforced correctly on live trades (previous sessions flagged oversizing).

### Previous Relevant Conversations
| ID | Topic |
|---|---|
| `f6a327f3` | **This session** — Hold Guard alignment, backtester trade durations, replay multi-symbol fix |
| `008b5307` | Guillotine & SAR emergency fix (8 bugs, NAV $6,442→$5,751) |
| `90d902e4` | Bot monitoring (stop_price bug, ATR trail fix, SAR stale) |
| `2ca3c3ed` | Pipeline unblock (5 critical bugs preventing all trades) |
| `458fe30c` | Strategy optimization handoff |

### Knowledge Items
- **Tradebot Technical Architecture** — `/home/qchan/.gemini/antigravity/knowledge/tradebot_technical_architecture_and_verification_infrastructure/`
- **Tradebot Governance and Deployment** — `/home/qchan/.gemini/antigravity/knowledge/tradebot_governance_and_deployment/`
