# AI Handoff — Bot Monitoring & Recovery Session

> [!CAUTION]
> **READ THIS ENTIRE DOCUMENT** before doing anything. You are taking over live monitoring of a trading bot with real money. The bot has been bleeding due to bugs, most of which have been fixed in this session. Your job is to monitor, validate, and intervene only when necessary.

---

## 1. Your Mission

**Continuously monitor the live trading bot until NAV reaches $7,500+.**

Current estimated NAV: **~$6,621** (margin used $4,293 + available $2,328).
Target: **$7,500** — that's ~$879 to recover.

### What You'll Be Doing
1. **Monitoring** — Check positions, P&L, and logs every 5-10 minutes
2. **Validating fixes** — Confirm the bugs fixed this session are actually working
3. **Anomaly detection** — Watch for errors, stuck trades, margin issues, duplicate ledger entries
4. **Trade quality** — How are wins being rode? How fast are losses cut? Is the ATR trail moving broker SL?
5. **Intervening** — If you see a bug or anomaly, fix it, deploy, and restart

### When to Stop
- NAV reaches $7,500+, OR
- Market closes (Friday 5PM ET), OR
- You identify a critical bug that needs user input to resolve

---

## 2. What Was Done This Session

### Conversation ID
`90d902e4-4a62-48ca-b1f1-5334c6c40770`

### Conversation Artifacts
Located at: `/home/qchan/.gemini/antigravity/brain/90d902e4-4a62-48ca-b1f1-5334c6c40770/`

### Critical Bugs Fixed (v2.8.55 → v2.8.60)

| # | Bug | File | Impact | Fix |
|---|---|---|---|---|
| 1 | **`stop_price` vs `stop_loss` field name** | `forex_conductor.py` L471 | **ALL position management was silently broken** — de-risk, pyramids, floors, ATR trail all computed `r_multiple ≈ 0.0` because `stop_price` returned `None`→`0`, making `initial_risk = entry_price` instead of the actual risk distance | Changed to `open_position.get("stop_price", 0) or open_position.get("stop_loss", 0) or 0` |
| 2 | **ATR trail trapped inside 1.0R gate** | `forex_conductor.py` L576+ | ATR trailing stop was nested inside `if r_multiple >= 1.0:` block, so even at 0.93R ($118 profit) the trail never engaged | Extracted ATR trail into standalone block before the 1.0R pyramid gate |
| 3 | **ATR trail threshold 1.0R → 0.5R** | `forex_conductor.py` L576+ | Trade peaked at 0.93R but old threshold was 1.0R — no profit floor | New tiers: 0.5-1R: 2.0× ATR, 1-2R: 1.5× ATR, 2-3R: 1.0× ATR, 3R+: 0.7× ATR |
| 4 | **SAR max concurrent 2 → 1** | `forex_conductor.py` L50 | Too many simultaneous SAR positions | `_SAR_MAX_CONCURRENT = 1` |
| 5 | **SAR stale trend validation** | `forex_conductor.py` L374+ | SAR blindly reversed direction even when late (>10 min), causing cascading counter-trend losses | Immediate SARs (<10 min) fire freely; stale SARs (>10 min) must align with HTF trend |
| 6 | **Smart Positions stuck on** | `.env` | `SMART_POSITIONS_ENABLED=true` in `.env` overrode the GUI toggle, blocking new trades | Changed to `false` in `.env` |

> [!IMPORTANT]
> **Bug #1 (`stop_price` vs `stop_loss`) was the worst** — it silently disabled ALL position management in the Conductor. De-risk at -0.6R, pyramiding at 1R+, floor moves, and the ATR trailing stop ALL use `current_stop` which was reading `0`. This means trades have been running without any profit protection or loss management for an unknown period. Verify this is now working by watching for `[CONDUCTOR] ATR TRAIL` or `[CONDUCTOR] MILESTONE` log entries.

---

## 3. Current Bot State (as of 2026-03-04 15:00 ET)

- **Version**: 2.8.60
- **PID**: 92726
- **Profile**: `forex_continuous`
- **Strategy**: Forex Conductor (regime-based router)
- **Symbols**: EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF, NZDUSD, EURJPY, GBPJPY, AUDJPY, XAUUSD, WTICOUSD

### Open Position at Handoff
| Symbol | Side | Entry | SL | TP | Unrealized P&L |
|---|---|---|---|---|---|
| USDCAD | SHORT | 1.36418 | 1.36579 | 1.36129 | +$63.71 |

### Key Settings
- **SAR**: Enabled, max 1 concurrent, 4.5% risk (overridden to 1% in code via `_SAR_RISK_PCT`)
- **SAR stale threshold**: 600 seconds (10 min) — after this, trend must align
- **ATR trail**: Fires at 0.5R+, moves broker SL via `decision.stop_loss`
- **Hold Guard**: 300 seconds (5 min) — blocks non-emergency exits
- **Cooldown**: 2 consecutive losses → 4-bar block per symbol
- **Smart Positions**: DISABLED (`.env` set to `false`)

---

## 4. How to Monitor

### Quick Health Check (run every 5-10 min)
```bash
# Recent decisions (last 2 minutes)
grep "$(date -u +%Y-%m-%dT%H:%M | cut -c1-15)" /home/qchan/.config/tradebot-sci/logs/tradebot.log | grep "DECISION" | python3 -c "
import sys,json
for l in sys.stdin:
    try:
        d=json.loads(l.strip())
        print(f'{d[\"timestamp\"][11:19]} {d[\"message\"][:200]}')
    except: pass
"
```

### Check for ATR Trail / Position Management
```bash
# These should appear when trades are profitable (>0.5R)
grep "ATR TRAIL\|MILESTONE\|DE-RISK\|CONDUCTOR.*TRAIL" /home/qchan/.config/tradebot-sci/logs/tradebot.log | tail -10
```

### Check for SAR Activity
```bash
grep "FORCED SAR\|SAR CANCELLED\|SAR STALE\|SAR DEFERRED\|LOSS DETECTED" /home/qchan/.config/tradebot-sci/logs/tradebot.log | tail -10
```

### Check for Errors and Warnings
```bash
grep '"level":"ERROR"\|"level":"WARNING"' /home/qchan/.config/tradebot-sci/logs/tradebot.log | tail -20
```

### Check Account / Margin
```bash
grep "Margin Check" /home/qchan/.config/tradebot-sci/logs/tradebot.log | tail -1
```

### Check Open Positions
```bash
python3 -c "
import json
with open('/home/qchan/.config/tradebot-sci/data/oanda_tracked_positions.json') as f:
    pos = json.load(f)
for sym, p in pos.items():
    print(f'{sym}: {p.get(\"side\")} entry={p.get(\"entry_price\")} sl={p.get(\"stop_loss\")} pnl=\${p.get(\"unrealized_pnl\",0):.2f}')
if not pos: print('No open positions')
"
```

### Check Trade Ledger
```bash
python3 -c "
import json
with open('/home/qchan/.config/tradebot-sci/data/trade_ledger.json') as f:
    ledger = json.load(f)
trades = ledger if isinstance(ledger, list) else ledger.get('trades', [])
# Last 5 closed trades
closed = [t for t in trades if t.get('closed_at')]
for t in closed[-5:]:
    pnl = t.get('pnl_usd', 0) or 0
    print(f'{t.get(\"symbol\"):8s} {t.get(\"side\"):5s} pnl=\${pnl:>8.2f} closed={t.get(\"closed_at\",\"\")[:19]}')
"
```

---

## 5. What to Watch For (Anomaly Checklist)

### ✅ Good Signs (confirm these are happening)
- `[CONDUCTOR] ATR TRAIL` log entries when trades are profitable (>0.5R)
- `[CONDUCTOR] MILESTONE` log entries at 1R+ for floor moves and pyramids
- `[CONDUCTOR] DE-RISK` when a trade is at -0.6R
- SAR entries that are **trend-aligned** (immediate or HTF-confirmed)
- `modify_stop_loss` calls in logs (broker SL actually moving)
- Trades lasting >5 min (hold guard working)

### ❌ Bad Signs (investigate immediately)
- `[SAFETY] Armor: Trailing` on profitable trades WITHOUT a preceding `[CONDUCTOR] ATR TRAIL` — means the Conductor's trail code isn't being reached
- Repeated `[BLOCKED] Insufficient margin` — means position sizing is too large
- `SAR CANCELLED` on trades that should have been immediate (within 10 min of loss)
- Duplicate trades in the ledger for the same symbol/time
- Trades exiting in <1 minute (hold guard failing)
- `r_multiple ≈ 0.0` on profitable trades (the `stop_price`/`stop_loss` bug returned)
- Any `ERROR` level logs

### 🔧 If You Need to Fix Something
```bash
# 1. Edit the file
# 2. Deploy and restart
bash "/home/qchan/Scripts/Trade by SCI/tradebot-sci-debug/scripts/deploy.sh" all
kill -9 $(pgrep -f "run_dev_bot.py")
sleep 2
bash "/home/qchan/Scripts/Trade by SCI/tradebot-sci-debug/scripts/tradebot.sh" -p forex_continuous -m continuous -x true --daemon
```

---

## 6. Key Files (Quick Reference)

| File | Purpose |
|---|---|
| `src/tradebot_sci/strategy/variants/forex_conductor.py` | Main strategy — SAR logic, position management, ATR trail, regime routing |
| `src/tradebot_sci/strategy/engine.py` | Strategy engine — exit priority flow, hold guard, safety guard integration |
| `src/tradebot_sci/strategy/safety_guard.py` | Safety exits — ATR Armor, Regime Flip, Stale Sniper |
| `src/tradebot_sci/broker/oanda_broker.py` | Broker interface — `modify_stop_loss()`, `place_order()`, margin checks |
| `src/tradebot_sci/runtime/cycle.py` | Main trading cycle — processes decisions, calls `modify_stop_loss` on HOLD decisions with `stop_loss` |
| `src/tradebot_sci/config/models.py` | Pydantic config models |
| `.env` | Environment overrides (SMART_POSITIONS_ENABLED=false) |

### Config Files (Runtime)
| Path | Purpose |
|---|---|
| `~/.config/tradebot-sci/config.json` | Bot configuration |
| `~/.config/tradebot-sci/data/oanda_tracked_positions.json` | Live position tracking |
| `~/.config/tradebot-sci/data/trade_ledger.json` | Trade history ledger |
| `~/.config/tradebot-sci/logs/tradebot.log` | Main log file (JSON lines) |

---

## 7. DO NOT TOUCH

> [!CAUTION]
> These are critical systems that have been carefully tuned. DO NOT modify them.

- **`stop_price`/`stop_loss` fallback** at `forex_conductor.py` L471 — this was the biggest bug this session
- **ATR trail block** at `forex_conductor.py` L576-635 — this is OUTSIDE the 1.0R gate intentionally
- **SAR stale validation** at `forex_conductor.py` L374-404 — timestamps with HTF trend check
- **Hold Guard** at `engine.py` — 300s (5 min), do NOT reduce below 120s
- **`trend_consensus.py` cache key** — includes `candles[0].close` to prevent cross-symbol contamination
- **`.env` SMART_POSITIONS_ENABLED=false** — do NOT change back to true
- **`safety_guard.py`** — ATR Armor, Regime Flip, all tuned and working
- **`backtester.py`** — core simulation capital bookkeeping

Also read `Documentation/PASSING_THE_BATON.md` Section 4 for the full do-not-touch list from previous sessions.

---

## 8. The P&L Flow (How Money is Made/Lost)

Understanding how the bot makes/loses money is critical for monitoring:

1. **Entry**: Conductor routes to sub-strategy (Trend Rider, Mean Reversion, Session Breakout) based on regime
2. **Losing trades**: Should be cut at -0.6R via de-risk (partial close 95%) or SL hit
3. **Winning trades**: ATR trail moves broker SL starting at 0.5R:
   - 0.5R: trail 2.0× ATR behind price (locks ~breakeven)
   - 1.0R: trail 1.5× ATR + floor to breakeven + pyramid 30%
   - 1.5R+: trail tightens, floor rises, pyramid 4% per 0.5R
4. **SAR**: On loss, immediately reverse direction. If stale (>10 min), must align with HTF trend.

**The key metric**: R-multiple. If the bot correctly cuts losers at -0.6R and rides winners with ATR trail, the math works. The bugs this session meant losers weren't being cut AND winners weren't being locked in — both sides were broken.

---

## 9. Knowledge Items

- **Tradebot Technical Architecture and Verification Infrastructure** — at `/home/qchan/.gemini/antigravity/knowledge/tradebot_technical_architecture_and_verification_infrastructure/`
- **Tradebot Governance and Deployment** — at `/home/qchan/.gemini/antigravity/knowledge/tradebot_governance_and_deployment/`

## 10. Previous Relevant Conversations

| ID | Topic |
|---|---|
| `90d902e4` | **This session** — Bug fixes (stop_price, ATR trail, SAR concurrency/trend, Smart Positions) |
| `2ca3c3ed` | Pipeline unblock (5 critical bugs preventing all trades) |
| `458fe30c` | Strategy optimization (SAR + pyramiding + proven techniques) |
| `50d4d601` | Restoring original loss mitigation ($550 profit config) |
| `344e0ec9` | Fixing chart auto-update |

---

## 11. Deploy Process

```bash
# Full deploy + restart
cd "/home/qchan/Scripts/Trade by SCI/tradebot-sci-debug"
bash scripts/deploy.sh all

# Restart bot
kill -9 $(pgrep -f "run_dev_bot.py")
sleep 2
bash scripts/tradebot.sh -p forex_continuous -m continuous -x true --daemon
```

> [!WARNING]
> Always use `deploy.sh all` which handles git commit, push to origin, push to debug branch, and mirror to public repo. Do NOT use `git push` manually.
