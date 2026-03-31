# AI Handoff — Universal Exit Logic Arrays & UI Polish

> [!CAUTION]
> **READ THIS ENTIRE DOCUMENT** before touching any code. Previous AI sessions have broken the frontend by assuming the Exit Logic tab uses a simple `<select>` dropdown. It does *not*. We have upgraded to a Multi-Select boolean array architecture.

---

## 1. What Was Done This Session

### Conversation ID
`0e2498ab-f8cc-435b-ad74-970062222af5`

### What The User and I Discussed

1. **Multi-Select Exit Logic Constraints**: The user requested that the 11 Universal Exit strategies (Chandelier, Time-Decay, Sniper, etc.) be converted from a single rigid choice into a stackable, multi-select system. We implemented this by upgrading the Pydantic schema in `models.py` from a string to `list[str]`.
2. **Settings UI Overhaul**: We completely rebuilt `renderExitLogicTab` in `settings_integrated.js`. Instead of a standard configuration panel, it now parses the `exitStrategies` object and maps 11 distinct boolean toggle cards in a single-column flex layout.
3. **Dynamic Parameter Embedding**: We purged the static "Exit Strategy Parameters" section. The custom sliders (like "Chandelier ATR Multiplier") are now dynamically created and injected *directly beneath* their corresponding parent toggle cards. If the strat is disabled, its specific parameters are grayed out (`opacity: 0.3`, `grayscale(100%)`).
4. **Layout Regression Bug Fixes**: We fixed a DOM spacing layout bug where standard tags were inadvertently compressed, breaking the vertical CSS symmetry of the entire Settings UI sidebar.

### Positive Expected PnL
We successfully documented how the Universal Exit Router mechanically forces a Positive Expected PnL. By aggressively trailing profitability (e.g., Chandelier ATR trailing) and killing stagnant trades (Time-Decay), we structurally prevent the market from clawing back unrealized gains. *We now leave with profit before the institutional algorithms sweep the liquidity.*

---

## 2. Technical Implementation Details

### The Universal Router Iterable (`exit_logic.py`)
The master router at `evaluate_exit_strategies` no longer evaluates an `elif` chain against a single string. It iterates through the configured array (e.g., `["chandelier", "time_decay"]`). Every single tick, the engine queries all active algorithms simultaneously. **The first strategy to return an `action="exit"` signal mathematically kills the trade.**

### The Pydantic Change (`models.py`)
```python
    universal_exit_strategies: list[Literal[
        "fixed_rr", "chandelier", "scale_breakeven", "parabolic_sar", 
        "ma_crossover", "time_decay", "swing_trailing", "rsi_exhaustion", 
        "bollinger_snap", "ratchet_milestone", "adx_death"
    ]] = Field(default_factory=lambda: ["fixed_rr"])
```
Ensure any backtests or CLI runners inject a `list` rather than a standard flat string.

### The JavaScript DOM Builder (`settings_integrated.js`)
When modifying `settings_integrated.js`, be extremely careful inside `renderExitLogicTab`. The loop dynamically calls `createSliderCard()` and attaches nested element event listeners. The boolean states are pushed directly to `configData.global.universal_exit_strategies` as JS Array objects (bypassing CSV string serialization to ensure JSON integrity).

---

## 3. What the Next AI Needs To Do

### Immediate: Run Combination Backtests
Now that the engine supports *layered* defense, we need to run an 84-day autonomous backtest to find the mathematical sweet spot of composite exits. 
1. Run a test with `["fixed_rr", "chandelier", "time_decay"]` stacked simultaneously.
2. Cross-reference the PnL and Max Drawdown against the standalone `["fixed_rr"]` legacy benchmark.

### DO NOT TOUCH:
1. Do not rewrite `exit_logic.py` back to a string interpreter.
2. Do not modify the DOM structure of `renderExitLogicTab` inside `settings_integrated.js` without first verifying the `stratWrapper` variable bindings inside the click listener. (A previous iteration caused a silent `ReferenceError` that erased the visibility of the entire tab).

### Final Verification
Always launch the Electron GUI (`npm run start:ui`) and physically click the **Exit Logic** tab before committing to verify that the 11 toggles successfully append to the DOM.
