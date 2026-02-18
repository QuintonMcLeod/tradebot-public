# ADR-001: The Strategy Registry (a.k.a. "Please Stop Adding Elif Branches")

**Status:** Accepted — and the `if/elif` chain has been given a dignified burial  
**Date:** 2026-02-18  
**Deciders:** @qchan, Antigravity  

---

## The Problem (It Was Getting Embarrassing)

The strategy engine used to pick trading strategies using a **factory function** with a growing chain of `if/elif` statements. Every time someone added a new strategy, they had to:

1. Write the strategy class (the fun part)
2. Find the factory function (the "where was it again?" part)
3. Add an `elif` branch (the "hope I don't break the 19 above me" part)
4. Pray they didn't forget to import anything (the "why is this None at runtime?" part)

By the time we had 20 strategies, the factory function looked like a choose-your-own-adventure book written by a committee.

---

## The Solution (A Dictionary. Seriously.)

We replaced the entire cascading `if/elif` monstrosity with a **class-level registry dictionary** called `STRATEGY_REGISTRY` inside `StrategyEngine`. Each entry is just:

```
"strategy_name" → (module_path, class_name)
```

Adding a new strategy is now a **2-file change**:

1. Create your class in `strategy/variants/my_new_strategy.py`
2. Add one line to `STRATEGY_REGISTRY`

That's it. The engine uses `importlib` to lazily load the module and instantiate the class at runtime. No imports at the top. No touching 47 other files. No prayers.

---

## What We Considered (And Why We Said No)

| Alternative | Why We Passed |
|---|---|
| **Plugin autodiscovery** (entry_points) | We have 20 strategies, not 200. This is a trading bot, not a WordPress installation. |
| **Decorator-based registration** | Sounds elegant until you realize every strategy module gets imported at startup whether needed or not. Your boot time says "no thanks." |
| **The original if/elif chain** | The original crime. Violated the Open-Closed Principle and made every PR a game of "spot the missing elif." |

---

## The Fine Print

**The Good:**
- Adding a variant is trivial — 2 files, no cascading changes
- `STRATEGY_REGISTRY` doubles as documentation — it's a table of contents for all strategies
- Lazy loading means unused strategies don't slow down startup

**The Less Good:**
- A typo in the module/class path will only blow up at runtime, not import time
- Mitigated by `test_strategy_engine.py`, which loops through every registry entry and tries to instantiate it. If you typo'd, the test catches it before you do.

> **Bottom line:** If you can copy-paste a dictionary entry and write a Python class, you can add a new strategy. The era of the 47-line elif chain is over.
