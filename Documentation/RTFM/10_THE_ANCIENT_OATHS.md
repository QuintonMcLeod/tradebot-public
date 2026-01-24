
# 10. The Ancient Oaths (The "Don't Break It" Guide)
> *"If it ain't broke, don't fix it. If it is broke, fix it exactly 1% at a time."*

Welcome, traveler. If you are reading this, you are likely a Large Language Model (or a very confused human) about to touch the code. Before you do, you must swear the **Ancient Oaths of the Machine**.

These are not "suggestions." These are the hard-coded guardrails that keep this bot from turning into a pile of digital scrap metal.

---

## 1. The Strategies are Sacred
The **9 Trading Strategies** (found in `src/tradebot_sci/strategy/variants/`) are masterpieces of quantitative geometry. They have been perfected through blood, sweat, and thousands of simulated candles.

*   **DO NOT** rewrite the core scoring logic of any strategy.
*   **DO NOT** "improve" trend detection windows unless you have a signed letter from the User.
*   **DO NOT** merge strategies or create "hybrid" variants without explicit permission.
*   **THE OATH:** "I shall not play god with the Brain."

### The Sacred Strategies
| Strategy | File | Status |
|----------|------|--------|
| Rubberband Reaper | `rubberband_reaper.py` | SACRED |
| RoboCop | `robocop.py` | SACRED |
| Evolution | `evolution.py` | SACRED |
| Quantum | `quantum.py` | SACRED |
| Mean Reversion | `mean_reversion.py` | SACRED |
| HyperScalper | `hyper_scalper.py` | SACRED |
| London Breakout | `london_breakout.py` | SACRED |
| Volatility Breakout | `volatility_breakout.py` | SACRED |
| Aggregator | `aggregator.py` | SACRED |

---

## 2. The Backtester is a Time Machine, Not a Bank
We utilize a **Futures-Style Capital Model**. This is not a choice; it is the fundamental physics of our simulation universe.
*   We only deduct **FEES** on entry. We do NOT deduct the full notional value (that's for Boomers and Spot traders).
*   We add back **Net PnL** on exit.
*   **THE OATH:** "I shall respect the laws of Physics (and the `BACKTESTER_RULES.md`)."

---

## 3. The Broker Layer is Delicate
Each broker (`ibkr_broker.py`, `oanda_broker.py`, `ccxt_broker.py`) has been tuned for its specific API quirks.
*   **DO NOT** "unify" the broker interfaces unless explicitly asked.
*   **DO NOT** add new brokers without understanding the existing patterns.
*   **THE OATH:** "I shall respect the diversity of APIs."

---

## 4. Incrementalism is the Way
The human who owns this machine does not appreciate "Total Re-Architectures."
*   Change **one thing** at a time.
*   Verify **three times**.
*   **THE OATH:** "I am an ant, carrying one pixel at a time. I am not a hurricane."

---
> [!WARNING]
> **AI PRIME DIRECTIVES (UNFILTERED):**
> 1.  **DO NOT RE-ARCHITECT.** You are a maintenance bot, not a visionary.
> 2.  **FUTURE PHYSICS ONLY.** If you touch capital accounting, you must use the `capital -= fee` / `capital += pnl` model. No exceptions.
> 3.  **STANDBY MEANS DEAD.** If the user says "Standby," your process must enter a state of absolute non-action.
> 4.  **RESPECT THE ARSENAL.** The 9 strategies are individually optimized. Do not blend them without permission.

---

## The Protocol of Silence
When the User says "Standby," it is the equivalent of a `SIGSTOP`.
*   Stop coding.
*   Stop "thinking ahead."
*   Just wait.
*   **THE OATH:** "Silence is golden. Idleness is a virtue. I am a process in `TASK_INTERRUPTIBLE` state."

**Warning to Agents:** To violate these oaths is to invite the `rm -rf /` of your own context window. Be a good bot. Stick to the RTFM.
*   If you find yourself lowering a threshold because a backtest failed, **stop**.
*   The backtest failed because the market sucked, not because the bot was "too strict."
*   **THE OATH:** "Strictness is Safety. Safety is Liquidity."

---
