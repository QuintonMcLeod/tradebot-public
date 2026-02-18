# ADR-003: Broker Abstraction Layer (a.k.a. "Why We Don't Have 'if broker == OANDA' Everywhere")

**Status:** Accepted — the spaghetti has been composted  
**Date:** 2026-02-18  
**Deciders:** @qchan, Antigravity  

---

## The Problem (A.K.A. "Which Broker Am I Talking To?")

The bot supports **multiple brokers** with wildly different APIs:

- **OANDA** — forex, REST API, server-side stops, spreads are your fee
- **CCXT/Gemini** — crypto, exchange API, maker/taker fees, quantities in decimals
- **CCXT/Coinbase** — also crypto, different fee tiers, different market structure
- **IBKR** — stocks & futures, TWS gateway, commissions, margin rules
- **PaperBroker** — imaginary money, lives in memory, judges silently

Without an abstraction layer, the runtime loop would look like:

```python
if broker == "oanda":
    do_oanda_thing()
elif broker == "gemini":
    do_gemini_thing_but_different()
elif broker == "ibkr":
    do_ibkr_thing_with_three_workarounds()
elif broker == "paper":
    pretend_to_do_a_thing()
```

Multiply that by 10 methods, and you've got 40 `if/elif` branches scattered across the codebase like landmines. Step on one wrong, and EUR/USD gets submitted to Coinbase. **Don't ask how we know.**

---

## The Solution (A Protocol, Not an Inheritance Ceremony)

### IExchangeBroker — The Contract

A `typing.Protocol` class in `broker/interfaces.py` defines the **10 methods** every broker must implement:

```python
class IExchangeBroker(Protocol):
    def execute_decision(self, decision) -> tuple[ExecutionResult, ExecutionOutcome]: ...
    def get_open_position_snapshot(self, symbol) -> dict | None: ...
    def flatten_symbol(self, symbol) -> None: ...
    def get_liquid_capital(self, symbol) -> float: ...
    # ... 6 more methods
```

**Why Protocol instead of ABC?**

`Protocol` uses **structural subtyping** — which is a fancy way of saying "if it has the right methods, it's a broker." No inheritance required. No base class. No `super().__init__()` rituals.

This is critical because `PaperBroker` (the simulation engine) needs to implement the same interface without inheriting from any production code. It's a completely standalone class that happens to have the same method signatures. Like a stunt double who never met the actor.

### Per-Broker Fee Model

Each broker knows its own fee rate via `_get_fee_rate()`:

| Broker | Rate | Reality |
|---|---|---|
| OANDA | ~0.04% | Built into the spread; practically invisible |
| Gemini | ~0.80% | Visible and painful; your fee shield better be ON |
| IBKR | ~0.10% | Commission-based; varies by volume |
| PaperBroker | 0.04% | Simulated; close enough to bother testing |

The global default in `SafetySettings` is 0.04% (OANDA-calibrated), but profiles can override it. This prevents the Fee Shield from applying OANDA math to a Gemini trade, which would be like checking your grocery receipt using Costco prices.

### PaperBroker (The Imaginary Friend)

`PaperBroker` implements the same Protocol but executes trades against an in-memory balance with simulated fills. It's used for:

- **Sabbath Mode** — bot keeps scanning and analyzing, but all trades go to paper
- **Backtesting** — historical data replay without touching a real exchange
- **Integration testing** — verifiable trade lifecycle without API keys

---

## What We Considered (And Why We Said No)

| Alternative | Why It Didn't Make The Cut |
|---|---|
| **ABC with `@abstractmethod`** | Forces an inheritance hierarchy. PaperBroker would have to inherit from a production base class. That's like a crash-test dummy being legally classified as a person. |
| **Pure duck typing (no Protocol)** | Works until someone forgets `get_liquid_capital()` and doesn't find out until production. IDE can't help you. Mypy can't help you. Good luck. |
| **Adapter pattern per broker** | Each broker already speaks Python. Wrapping each one in an adapter is adding a middleman to a conversation that doesn't need one. |

---

## The Fine Print

**The Good:**
- The runtime loop doesn't know or care which broker is active
- Swapping brokers is a config change, not a code change
- PaperBroker enables risk-free testing of the entire pipeline
- No inheritance tax — each broker is self-contained and independent

**The Less Good:**
- Protocol doesn't enforce implementation at import time (only at type-check time)
- Mitigated by dedicated tests per broker: `test_ccxt_broker.py`, `test_oanda_broker.py`, `test_paper_broker.py`

> **Bottom line:** The runtime loop talks to a standardized interface. It doesn't know if it's talking to OANDA, Gemini, or a pretend broker made of JSON files. And that's exactly the point.
