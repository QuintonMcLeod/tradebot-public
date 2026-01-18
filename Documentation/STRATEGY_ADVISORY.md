
# Strategy Advisory: Optimizing ICC for Expectancy

## Executive Summary
You reported **20% Win Rate** and **Negative MFE** (Entries immediately underwater) on a recent 7-day BTC backtest.
This indicates the bot is entering **too early** (catching falling knives) and/or exiting **too late** (round-tripping profits).

Here is my analysis and concrete recommendations for the `TradeBySCI` bot.

## 1. Should Continuation Require Indication?
**Verdict:** **YES.**

*   **Logic:** The "ICC" acronym stands for *Indication* -> *Correction* -> *Continuation*.
*   **Why:** A "Continuation" without a prior "Indication" implies we never saw the initial impulse. We are likely buying a random breakout in a chop zone.
*   **Recommendation:** Enforce `require_indication=True` in the continuation detection logic.
*   **Implementation:**
    *   **File:** `src/tradebot_sci/strategy/icc_signals.py`
    *   **Function:** `detect_continuation`
    *   **Change:** Ensure `indication` argument is mandatory and not `None`.

## 2. Should `sweep+indication` Remain?
**Verdict:** **RESTRICT IT.** (Do not delete, but disable for Auto-Entry).

*   **Logic:** A `sweep+indication` entry buys the *first* sign of reversal.
    *   **Pros:** Gets the absolute bottom (Sniper entry).
    *   **Cons:** Extremely low win rate. Most "Indications" fail and become lower lows (Trend Continuation against you).
*   **Why:** Your "Negative MFE" is almost certainly caused by these entries. You buy the bounce, and it dumps again.
*   **Recommendation:**
    *   **Auto-Trading:** **DISABLE** `sweep+indication`. Force the bot to wait for the confirmed `continuation` (the Higher Low).
    *   **Manual/AI:** Allow it only if `score > 8.5` (A+ setups).
*   **Implementation:**
    *   **File:** `src/tradebot_sci/strategy/engine.py`
    *   **Function:** `_check_icc_entry_signal` or `_build_auto_entry_decision`
    *   **Change:** `if indication and not continuation: return None` (or reduce size).

## 3. How Should Take Profit (TP) Be Set?
**Verdict:** **USE SPLIT TARGETS (Scale Out).**

*   **Current Issue:** "Too tight exits" vs "Negative MFE". You are getting stopped out before the move, or holding too long and round-tripping.
*   **Why:** A fixed `2.5R` target is hard to hit in choppy conditions.
*   **Recommendation: The "Bank & Ride" Approach**
    *   **TP1 (Bank):** Set a partial exit (50%) at **1.5R - 2.0R**. This pays for the risk and "free rolls" the rest.
    *   **TP2 (Ride):** Leave the remaining 50% with a **Structure Trailing Stop** (don't set a hard target price, looking for "Moon").
*   **Implementation:**
    *   **File:** `src/tradebot_sci/strategy/engine.py`
    *   **Function:** `_apply_icc_post_checks`
    *   **Change:** Logic to submit a bracket order with Scale Out or managing `scale_out_decision`.

## Concrete Action Plan
If you agree with this assessment, I can implement the following **non-destructive** changes:

1.  **Refine Filters:** Modify `engine.py` to downgrade `sweep+indication` setups (require higher score) instead of deleting them.
2.  **Split TP:** Adjust `ccxt_broker.py` or `engine.py` to support `take_profit_1` and `take_profit_2` logic.
3.  **Strict Continuation:** Verify `icc_signals.py` ensures the sequence holds.
