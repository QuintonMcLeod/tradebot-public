# MISSION: THE REAPER RESURRECTION
## Hand-off Briefing for Next Generation AI Assistant

### 1. The Context
You are taking over the development of `tradebot-sci`. We have conquered the "Gravity Well" of small accounts ($100).

**The Final Evolution**: We implemented the **Staircase Ratchet**.

### 2. The Current Architecture (Config 20)
-   **Logic**: **Staircase Floor** + **Strict Entry (BB 2.5 / RSI 25/75)**.
-   **Floor Milestones**: $100 -> $200 -> $500 -> $1,000 -> $2,000.
-   **Lock-in Logic**: The floor moves to the next level only when the account has a ~100% cushion (e.g., $100 floor until $500 reached).
-   **Result**: Survives the Jan 2026 Stress Test with capital intact.
-   **Philosophy**: Prioritize "Wiggle Room" so the bot isn't choked by its own safety net.

### 3. Engineering State
-   **Engine**: Backtester patched to allow **Loss-Exits** via signals (`allow_loss_exit_after_hold=True`).
-   **Strategy**: `rubberband_reaper.py` is locked to Config 20.
-   **Safety**: 5x Leverage Cap in the engine for production safety, but up to 200x for marathon runs.

### 4. Your Directives (Toward 1000%)
1.  **The Compounder**: Can you optimize the transition points? If we have $400, can we risk *more* to hit the $500 milestone faster?
2.  **Staircase Tuning**: I implemented **Cushion-Aware Scaling** to handle 5 symbols. Can you make it smarter? If only 1 symbol is trading, can we give it the *entire* cushion?
3.  **Dynamic Floor**: Instead of fixed milestones ($200, $500), can you use ATR-based volatility to decide how much "Wiggle Room" a floor needs?

**The Reaper is Resurrected. Protect the Steps.**
