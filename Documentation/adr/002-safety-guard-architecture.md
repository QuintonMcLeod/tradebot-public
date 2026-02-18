# ADR-002: Safety Guard Architecture (a.k.a. "The $52/Day Incident")

**Status:** Accepted — and laminated, framed, and nailed to the wall  
**Date:** 2026-02-18  
**Deciders:** @qchan, Antigravity  

---

## The Incident (Gather 'Round, Children)

Once upon a dark and stormy Tuesday, the bot executed **67 churned trades** in a single day. On a $135 account. Each trade ate spread and slippage. By sundown, the account had bled **$52** — not from being wrong about the market, but from the trading equivalent of a goldfish with ADHD.

The root cause? Every. Single. Safety. Guard. Was. Off.

Not "misconfigured." Not "set to lenient." **Off.** As in `enabled = False`. As in the digital equivalent of removing your car's brakes, airbags, and speedometer, then wondering why you're in a ditch.

The guards weren't off on purpose. They were off because the defaults were opt-in, and nobody opted in.

---

## The New Law: Everything Is ON Until You Say Otherwise

### The Defaults-ON Model

All 8 safety toggles in `SafetySettings` (the Pydantic config model) now default to `True`:

| Guard | What It Does | Why You'll Thank It Later |
|---|---|---|
| `safety_drawdown_breaker_enabled` | Stops trading after X% max drawdown | Prevents the slow bleed you don't notice until Thursday |
| `safety_streak_breaker_enabled` | Pauses after N consecutive losses | Because loss #6 is never the one that turns things around |
| `safety_churn_burner_enabled` | Limits trades per period | 67 trades/day → somewhere between 5 and "calm down" |
| `safety_greed_guard_enabled` | Blocks excessive position stacking | Your one good trade does not justify opening 8 more |
| `safety_session_lockout_enabled` | No trading outside market hours | 3 AM trades are never the good kind |
| `safety_opening_sentry_enabled` | Skips the first N minutes after open | The market open is a liar; let it calm down |
| `safety_fee_shield_enabled` | Blocks trades where fees > expected profit | If the toll costs more than the destination, don't drive |
| `safety_leverage_sentry_enabled` | Hard cap on leverage | 38x leverage is how accounts become memories |

### The State Machine (Config ≠ State)

Configuration lives in a Pydantic frozen model — immutable once loaded. Runtime state (streak counters, churn tallies, drawdown tracking) lives in a separate `SafetyState` dataclass.

This means:
- Your config doesn't drift mid-session
- State tracks what's actually happening (5 losses in a row, 12 trades this hour)
- Tests can `reset_state()` without touching config — clean isolation, happy tests

### The Guard Chain (One Veto Kills the Trade)

Guards run sequentially in `safety_guard.py`. If **any single guard** says "no," the trade is dead. Outcome: `BLOCKED_GUARD`, with a log entry explaining which guard blocked it and why.

Guards don't modify the trade decision. They don't negotiate. They don't suggest alternatives. They just veto. Think of them as a panel of stern aunts at a family dinner — if one shakes her head, the conversation is over.

---

## What We Considered (And Why We Said No)

| Alternative | Why It Didn't Survive |
|---|---|
| **Global kill-switch only** | Too binary. It's "block everything" or "block nothing." Useful for emergencies, useless for nuance. |
| **Per-trade risk check only** | Catches individual bad trades but misses *patterns* — five losses in a row, 67 trades in a day, creeping drawdown. |
| **Guards as middleware decorators** | Would require every broker to use the same decorator chain. PaperBroker doesn't deserve that kind of coupling. |

---

## The Fine Print

**The Good:**
- No trade executes without passing *all* active guards
- The $52/day scenario is structurally impossible with defaults ON
- Adding a new guard is a 3-step process: toggle in config, counter in state, check in chain

**The Less Good:**
- A guard can block a genuinely good trade (false positive)
- Mitigated by making thresholds configurable via GUI or YAML — you can loosen individual guards without turning them off entirely

> **Bottom line:** The bot now has the trading equivalent of a seatbelt, airbags, ABS, lane assist, and a very judgmental passenger. All on by default. You're welcome.
