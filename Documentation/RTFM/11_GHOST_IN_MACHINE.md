
# 8. The Ghost in the Machine (AI & Strategy)
> *"I think, therefore I trade."*

You know the bot trades. But *how* does it decide?
This document explains the **Brain** (`strategy/engine.py`) and the **Soul** (The AI Backup).

## The Theory: ICC (Indication, Correction, Continuation)
The bot does not guess tops or bottoms. It waits for the market to show its hand.

### Step 1: Indication (The "Hint")
The price moves aggressively in one direction.
*   **The Bot Sees:** A "Clean Close" above a swing high.
*   **The Bot Thinks:** "Hmm. The bulls are awake."
*   **Action:** Nothing yet. We don't chase pumps.

### Step 2: Correction (The "Pullback")
The price comes back down to test the waters.
*   **The Bot Sees:** Price dipping into a "Discount Zone" or sweeping a "Liquidity Pool" (fancy words for "lots of stop losses").
*   **The Bot Thinks:** "Are they trapping the bears? Let's see if it holds."
*   **Action:** Still waiting.

### Step 3: Continuation (The "Go Signal")
The price rips back up, breaking local structure.
*   **The Bot Sees:** A candle closing above the correction range.
*   **The Bot Thinks:** "Okay, the Correction is over. The Trend is resuming. SEND IT."
*   **Action:** **ENTRY.**

## The AI Backup
The hard-coded algorithm above handles 90% of the work. But sometimes, the chart is messy.

### When the AI Steps In
If the Algorithm is unsure (Score between 40-59), it packages the chart data into a prompt and sends it to the LLM (Large Language Model).

**The Prompt:**
> "Here is the chart for BTC. Trend is Bullish. We just swept the lows. But volume is low. Would you take this trade? Y/N."

**The Response:**
The AI analyzes the context—Time of Day, recent volatility, vibes—and returns a verdict.
*   *"Yes, because we are in the London Session and the sweep is clean."* -> **Trade Approved.**
*   *"No, volume is dying and it looks like a trap."* -> **Stand Aside.**

This "Second Opinion" is designed to catch profitable setups that rigorous code might miss, or save you from "technically correct but stupid" trades.

## Why This Works (The Guarantee)
This system guarantees **process**, not outcome.
*   It *guarantees* you won't buy the top (because it waits for Correction).
*   It *guarantees* you won't sell the bottom (because it waits for Indication).
*   It *guarantees* you won't trade blindly (because the AI double-checks).

In a chaotic market, a solid process is the closest thing to a money printer you will find.
