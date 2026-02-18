# ADR-004: Position Hold Lock (a.k.a. "Stop Flipping Like a Pancake")

**Status:** Accepted — the whiplash era is over  
**Date:** 2026-02-18  
**Implemented:** February 2026, after one memorably expensive Sunday  

---

## The Problem (A Story in Three Flips)

Picture this. It's 2:01 PM on a Tuesday. The bot opens a long position on BTCUSD because Meta-SCI is feeling bullish:

```
14:01  ENTER_LONG   BTCUSD  → Meta-SCI says "go long, my child"
```

Five minutes later, RoboCop (a different strategy) looks at the same chart and disagrees:

```
14:06  CLOSE + ENTER_SHORT  → RoboCop says "actually, short"
```

Five minutes after *that*, Meta-SCI runs again and says:

```
14:11  CLOSE + ENTER_LONG   → Meta-SCI says "no wait, I changed my mind"
```

**Result:** 3 round-trips. ~$45 in spread and fees. Net PnL: **-$52.**

The market didn't move against us. No black swan. No flash crash. The bot simply could not commit to a direction for more than 5 minutes. It was trading like a weather vane in a hurricane — technically responsive, financially devastating.

This is called **strategy whiplash**, and it's the trading equivalent of opening the fridge, closing the fridge, opening the fridge, closing the fridge, and then ordering DoorDash.

---

## The Solution (Pick a Lane)

### The Rule

**Once a position is opened, all new entry signals for that symbol are rejected until the existing position closes naturally.**

That's it. That's the whole rule.

### How It Works

1. `execute_decision()` checks **"do I already have a position on this symbol?"**
2. If yes → return `STAND_ASIDE` with a log: *"Position already open, ignoring conflicting signal"*
3. Only exit actions (stop-loss, take-profit, structural exit) can close the position
4. After a position closes, a **300-second re-entry cooldown** prevents immediate re-entry (so the bot doesn't immediately flip back)

### What This Looks Like In Practice

```
14:01  ENTER_LONG   BTCUSD  → Position opened ✅
14:06  ENTER_SHORT  BTCUSD  → BLOCKED: "Position already open" ❌
14:11  ENTER_LONG   BTCUSD  → BLOCKED: "Position already open" ❌
14:32  TP HIT       BTCUSD  → Position closed ✅
14:32  COOLDOWN     BTCUSD  → 5-minute cooldown started ⏳
14:37  ENTER_SHORT  BTCUSD  → Cooldown expired, free to trade ✅
```

**Result:** 1 trade, 1 take-profit, 0 churn. The bot held its conviction, took its profit, and moved on like an adult.

---

## What We Considered (And Why We Said No)

| Alternative | Why It Lost |
|---|---|
| **Allow flips if the new signal is "stronger"** | "Stronger" is subjective. AI confidence scores are noisy. A 0.72 vs 0.68 difference is NOT a reason to close a position and reverse. |
| **Time-based minimum hold (e.g., 30 min)** | Too rigid. A genuine structural invalidation at 5 minutes should still trigger an exit. You don't want a minimum hold preventing a valid stop-loss from firing. |
| **Per-strategy lock (different strategies can coexist)** | Two opposing positions on the same symbol = net zero exposure with double the fees. You're paying the spread to hold nothing. Congratulations, you've invented a fee donation machine. |

---

## The Fine Print

**The Good:**
- Churn-based capital bleed is structurally eliminated
- Strategies are forced to commit to their conviction
- Position tracking is simplified — max 1 position per symbol
- The 300-second cooldown prevents "revenge trading" after a close

**The Less Good:**
- If a genuinely superior signal arrives while a position is open, it's ignored
- But exits still run independently — if the position is structurally invalid, the stop-loss or structural exit will close it regardless
- After the close, the bot is free to enter in any direction

> **Bottom line:** The bot now picks a direction and sticks with it until there's a *real reason* to exit — not because another strategy had a different opinion. The fridge stays closed until you're actually hungry.
