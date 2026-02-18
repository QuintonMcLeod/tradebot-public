# What Does "S+ Grade" Mean?

*A plain-English guide for humans who trade, not humans who type-check.*

---

## The Short Version

Tradebot SCI went through **8 rounds of independent code audits** — the kind where a grader uses sentences like *"the workers delivered"* and scores the codebase like it's failing gym class. It started at **C+** (yikes) and ended at **S+** (the grade they give when they run out of letters).

Here's what that actually means for anyone watching the money go up and down.

---

## 💰 Safety Guards That Are Actually ON

### The Problem They Solved

Early in development, the bot once bled **$52/day** — not because the strategy was wrong, but because **every single safety guard was silently set to OFF.**

Imagine a pilot flying without instruments, seatbelts, engine warnings, or a fuel gauge — and the plane is on fire — but the cockpit lights all say ✅ GREEN.

The bot was also churning trades at an absurd rate. Each flip costs spread fees, and those fees add up fast when nobody's watching.

### What's There Now

All 8 safety guards are **ON by default** and **cannot be silently disabled**:

| Guard | What It Protects Against |
|---|---|
| **Drawdown Breaker** | "The market moved 3% against the position. Let's NOT buy more." |
| **Streak Breaker** | "5 losses in a row. Time to sit out a round." |
| **Churn Burner** | "67 trades/day is not a strategy, it's a panic attack." |
| **Greed Guard** | "The trade is up 400%. Opening 3 more of these is not wise." |
| **Session Lockout** | "The market is closed. No phantom trades." |
| **Opening Sentry** | "First 5 minutes of session. All data is unreliable." |
| **Fee Shield** | "This trade would cost more in fees than it could possibly make." |
| **Leverage Sentry** | "Leverage at 38x. This is not the way." |

Each guard is backed by a **property-based test** — a testing framework (Hypothesis) throws 200 random scenarios at each guard to try to break it. If the guard survives 200 attempts to kill it, it ships. If it doesn't, it gets fixed until it does.

---

## 🛡️ Graceful Degradation (Things WILL Break)

The internet goes down. A broker returns a 500 error. The hard drive fills up. The AI returns something that looks like it was written by a confused parrot.

These things happen. The question is: *what does the bot do?*

### Before S+

When something broke, the bot would either:
- **Crash entirely** (the polite option)
- **Continue trading with garbage data** (the expensive option)
- **Silently hold a position forever** because the exit code threw an exception nobody caught

### After S+

There are **12 degradation contract tests** — tests that *deliberately inject failures* and verify correct handling:

| What Breaks | What The Bot Does | What It Doesn't Do |
|---|---|---|
| **Broker API is down** | Logs a warning, pauses trading, retries with backoff | Panic-sell positions at 3 AM |
| **AI returns nonsense** | Rejects the decision, logs the garbage, moves on | Execute a "BUY 9999 ELONMUSK/USD" order |
| **Disk is full** | Keeps trading, logs write failures separately | Crash because it can't write a log line |
| **Config is corrupted** | Refuses to start with a clear error message | Start trading with `risk_per_trade = NaN` |

Every failure mode has a *planned response*, and every planned response is tested.

---

## 🚦 The CI Pipeline (Bad Code Can't Sneak In)

Every code change passes through 3 automated gates before it goes live:

### Gate 1: The Linter (Grammar Police)
```
ruff check — "That variable is named 'x2'. Try harder."
ruff format — "Indentation is wrong on line 47. No hiding."
```

### Gate 2: The Type Checker (Pedantic Accountant)
```
mypy --strict — "This function says it returns a number, but on line 93
it returns the string 'oops'. No merge for you."
```

This is a **hard gate** — if it fails, the code literally cannot be merged. Not "fix it later." Cannot. Merge.

### Gate 3: The Test Suite (Crash Test Dummies)
```
184 tests — Every critical path verified automatically
80% coverage minimum — At least 80% of the code is tested
```

If all 3 gates pass, the code ships. If any one fails, it's blocked. Same pattern used by Google, Stripe, and every company that takes "don't break production" seriously.

---

## 📊 Structured Logging

### What Logs Used To Look Like
```
2026-02-18 03:15:00 [INFO] something happened somewhere maybe
2026-02-18 03:15:01 [INFO] doing a thing
```

### What They Look Like Now
```json
{
  "timestamp": "2026-02-18T03:15:00",
  "level": "INFO",
  "event": "order_fill",
  "symbol": "EURUSD",
  "side": "BUY",
  "qty": 1000,
  "price": 1.0845,
  "broker": "oanda",
  "strategy": "MetaSCI"
}
```

Machine-readable, searchable, filterable. "Why did the bot stand aside at 3:47 PM?" is now a 5-second query instead of a 20-minute log file adventure.

---

## 📝 Architecture Decision Records (ADRs)

Every major design decision is documented with **what**, **why**, **alternatives considered**, and **consequences**. This prevents the classic disaster:

> New developer sees a position lock. Thinks "that seems limiting." Removes it. Bot starts whiplashing between long and short 67 times a day. Capital bleeds. Nobody knows why because the *reason* for the lock was only in one person's head.

There are 4 ADRs in the system:

- **ADR-001**: Strategy Registry — why strategies load from a dictionary, not a giant if/elif chain
- **ADR-002**: Safety Guard Architecture — why all guards are ON by default (the $52/day story)
- **ADR-003**: Broker Abstraction — why OANDA, Gemini, and IBKR aren't hard-wired into the brain
- **ADR-004**: Position Hold Lock — why positions are locked until they close naturally

These live in `Documentation/adr/` and are accessible from the Help tab.

---

## 🧹 Clean Workspace

| Before | After |
|---|---|
| 32 random `.txt` files in root directory | 7 essential files |
| 3 documentation directories | 1 documentation directory |
| `tools/` with 200+ scripts, 40% debate transcripts | 127 active tools, 76 archived |
| `.gitignore` that ignored almost nothing | 77 rules, comprehensive |

A clean workspace means new collaborators don't get confused by `nuclear_full_log.txt` sitting next to `README.md`.

---

## The Bottom Line

Tradebot SCI went from *"hope it works"* to *"proven to work, and proven to fail safely when it can't."*

Every safety guard is tested. Every failure mode is handled. Every code change is gated. Every decision is documented.

Is it perfect? No — there's still a growth path (more modules to type-check, more integration tests, coverage to expand). But the foundation is solid, the guardrails are real, and the $52/day bleeding story is an artifact of a version that no longer exists.

*— SCI Engineering, Feb 2026*
