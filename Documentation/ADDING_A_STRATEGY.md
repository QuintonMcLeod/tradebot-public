---
title: "Adding or Changing a Strategy"
category: procedure
icon: extension
description: "The single authoritative checklist. Two Python files minimum, four UI
  registrations, one test command. Written against the code as it actually is, not as
  the older checklists describe it."
---

# Adding or Changing a Strategy

**This is the authoritative procedure.** Several older checklists exist inside the
source (`engine.py`, `meta_sci.py`, the GUI comments). They have drifted from the
code and disagreed with each other. Where they conflict with this document, **this
document is right** — it was verified against the code on 2026-09-13. If you find a
discrepancy, fix this file rather than trusting the older comments.

Read this before touching anything. If you are an AI agent, read it before you start
editing, not after a test failure tells you that you missed a file.

---

## The short version

| # | What | Where |
|---|---|---|
| 1 | Write the strategy class | `src/tradebot_sci/strategy/variants/<name>.py` |
| 2 | Register it in the engine | `src/tradebot_sci/strategy/engine.py` → `STRATEGY_REGISTRY` |
| 3 | Add to the Meta-SCI ensemble *(only if it belongs there)* | `src/tradebot_sci/strategy/variants/meta_sci.py` |
| 4 | Register it in the GUI — **four separate places** | see step 4 below |
| 5 | **Validate** | `python3 -m pytest tests/test_strategy_engine.py tests/test_integration.py -q` |

Skipping step 4 leaves a strategy that runs but cannot be selected — the bot will be
trading something the UI has never heard of, which is exactly the bug that prompted
this document.

---

## Step 1 — Write the strategy class

Create `src/tradebot_sci/strategy/variants/<your_strategy>.py`.

Extend `BaseStrategy` and implement the methods below. **The correct interface is
`check_entry_signal` and `check_exit_signal`.** Older checklists tell you to
implement `evaluate()` and `get_signal()` — neither method exists anywhere in this
codebase, so do not go looking for them.

```python
class MyStrategy(BaseStrategy):
    # None means "selected by config, not gated to a named session".
    SESSION_PROFILE = None

    def __init__(self, **kwargs):
        super().__init__("MyStrategy")
        # Every parameter must be reachable from the profile config, because that
        # is where per-profile strategy settings are stored and passed in as kwargs.
        self.target_pips = float(kwargs.get("my_target_pips", 15.0))

    def score_signal(self, snapshot, gates):
        """Optional but expected: (score, grade, reason)."""

    def check_entry_signal(self, snapshot, gates, open_position=None,
                           current_capital=None, trade_history=None):
        """Return an AITradeDecision, or None to stand aside."""

    def check_exit_signal(self, snapshot, open_position, gates,
                          current_capital=None, trade_history=None):
        """Return a close decision, or None to keep holding."""
```

Signatures must match `strategy/variants/base.py` exactly. The base class raises
`NotImplementedError`, so a mismatched signature fails at runtime, not at import.

Module conventions, all of which the existing variants follow:

- A module docstring that states the rule, **why each parameter is what it is**, and
  the measured result. Include the research document that produced it.
- Parameter defaults read via `kwargs.get(...)`, never hardcoded at the call site.
- `logger.info` lines tagged `[YOUR_TAG]`, matching the house log-tag style
  (`[PAPER]`, `[GUARD]`, `[SCRAPE]`). No agent names or attribution tags anywhere —
  see `AGENTS.md`.

## Step 2 — Register in the engine

One line in `STRATEGY_REGISTRY` in `src/tradebot_sci/strategy/engine.py`:

```python
"my_strategy": ("tradebot_sci.strategy.variants.my_strategy", "MyStrategy"),
```

Nothing is imported at the top of `engine.py`; the module path is resolved lazily at
runtime, so a typo here does not fail until something selects the strategy. Step 5
is what catches it.

## Step 3 — Meta-SCI ensemble (conditional)

**Only if the strategy belongs in the per-bar ensemble.** Most do not. A strategy
with a fixed time window, or one that is selected deliberately by a profile, should
**not** be added: `meta_sci` picks among regime-matched strategies on every bar and
would fire it outside its measured conditions.

If it does belong, follow the checklist at the top of `meta_sci.py`:
`_ensure_strategies_loaded()` → `self.strategies` → `self.REGIME_GROUPS` → optionally
`self.CRYPTO_STRATEGIES` and `self.STRATEGY_WEIGHTS`.

## Step 4 — Register in the GUI (four places)

The GUI keeps its own hardcoded catalogs. It does not read the Python registry, so
all four of these are required. Edit files under
**`src/tradebot_sci/electron_gui/`** — see the warning about `gui/` below.

**4a. Strategy descriptions** — `settings_integrated.js`, `const STRATEGIES = { ... }`

```js
my_strategy: {
    name: 'My Strategy',
    icon: 'trending_up',              // a Material Symbols name
    shortDesc: 'One line for the dropdown',
    assetClass: "forex",              // forex | crypto | universal | futures
    description: "What it actually does, in plain language.",
    style: "Mean Reversion",
    risk: "Medium",
    bestFor: "Forex: 20:00 UTC hour",
    stats: { target: "15 pips", stop: "20 pips" },
    sessionProfile: []                // [] when SESSION_PROFILE is None
},
```

`assetClass` must be one of the values above. The System Tab's per-asset strategy
dropdown is generated by iterating `Object.entries(STRATEGIES)` and grouping on this
field, **so this entry alone populates that dropdown** — there is no separate list to
maintain, despite what the older checklist says.

**4b. Strategy Toolbox grid** — `settings_integrated.js`, the `strategies` array
inside `renderStrategyToolbox()`:

```js
{ id: 'my_strategy', label: 'My Strategy', icon: 'compress', color: '#0ea5e9' },
```

**4c. Profile Editor dropdown** — `profiles_module.js`, the `STRATEGY_OPTIONS` array:

```js
{ value: 'my_strategy', label: 'My Strategy' },
```

**4d. Backtest dropdown** — `index.html`, an `<option>` inside
`<select id="bt-strategy-select">`:

```html
<option value="my_strategy">My Strategy</option>
```

> **Do not edit `gui/` at the repository root.** It is a stale duplicate of
> `electron_gui/` that nothing references, is not loaded by the app, and is not
> touched by `deploy.sh`. It lags behind by months. Editing it silently does nothing.
> See `gui/README.md`.

### Why the older checklists are wrong

They are not simply careless — they are **correct for a directory that no longer
exists**. The GUI used to live in `gui/` at the repository root, where `settings.js`
held the System Tab strategy dropdown and `renderer.js` was the Profile Editor. The
GUI then moved to `src/tradebot_sci/electron_gui/` and was refactored:

| Old checklist said | Reality now |
|---|---|
| `renderer.js` → `STRATEGY_OPTIONS` | `renderer.js` has **0** occurrences; the array moved to `profiles_module.js` |
| `settings.js` → `STRATEGY_VARIANT` dropdown | `settings.js` **does not exist** in `electron_gui/`; the dropdown is generated from `STRATEGIES` |
| "System Tab dropdown — separate list" | generated by iterating `Object.entries(STRATEGIES)`, so step 4a covers it |
| "implement `evaluate()` + `get_signal()`" | neither method exists in any of the ~43 variants; the contract is `check_entry_signal` / `check_exit_signal` |

The stale `gui/` directory still contains `settings.js` and still shows 3
`STRATEGY_VARIANT` hits, which is why the old checklist looks plausible if you go
looking in the wrong tree. Check which directory you are reading before you trust a
comment.

## Step 5 — Validate

```bash
cd "Trade by SCI/tradebot-sci-debug"
python3 -m pytest tests/test_strategy_engine.py tests/test_integration.py -q
```

`test_strategy_engine.py` walks every `STRATEGY_REGISTRY` entry and instantiates it,
which is the documented guard against a typo'd module or class path (see
`Documentation/adr/001-strategy-registry.md`). `test_integration.py` imports every
registered class. **Run this before claiming the registration works.**

Then run the wider suite and compare against a baseline:

```bash
python3 -m pytest tests/ -q
```

Note: `tests/test_property_invariants.py` needs the `hypothesis` package. If it is
missing the module now skips itself rather than aborting collection, so the rest of
the suite still runs.

## Step 6 — Changing an existing strategy

If you change a strategy's **defaults** or behaviour, the following all drift
silently and all must be updated in the same change:

- its module docstring (`strategy/variants/<name>.py`) — the rule, the parameters,
  and the measured result
- the `STRATEGIES` entry in `settings_integrated.js` — `stats`, `description`
- the GUI label, if the behaviour no longer matches the name
- the research document the docstring points at
- any inline comment that quotes the old numbers

A docstring that says "target 10 pips" while the code defaults to 15 is worse than no
docstring, because it is actively misleading to the next person and to any AI agent
reading it. Grep for the old value across the file before you finish.

---

## Worked example

`forex_scrape_fade` is the reference implementation of this procedure. It touches
exactly the files listed above and nothing else. When in doubt, diff your change
against it:

```bash
git log --oneline -- src/tradebot_sci/strategy/variants/forex_scrape_fade.py
```
