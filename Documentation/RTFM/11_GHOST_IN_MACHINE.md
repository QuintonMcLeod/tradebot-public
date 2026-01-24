
# 11. The Ghost in the Machine (AI & Strategy)
> *"I think, therefore I trade."*

You know the bot trades. But *how* does it decide?
This document explains the **Brain** (`strategy/engine.py`), the **Strategy Arsenal** (9 strategies), and the **Soul** (The AI Backup).

---

## The Multi-Strategy Arsenal

The bot isn't locked to one strategy. It has **9 distinct trading strategies**, each optimized for different market conditions. You can assign different strategies to different asset classes.

| Strategy | Style | Best For |
|----------|-------|----------|
| **Rubberband Reaper** | Mean reversion + anti-martingale | Ranging markets, volatile crypto |
| **RoboCop** | Ultra-aggressive trending | Strong trends, high volatility |
| **Evolution** | NTZ scalping | Sideways/consolidation |
| **Quantum** | Trend following with SMA | Strong trending forex/stocks |
| **Mean Reversion** | Classic Bollinger + RSI | Ranging crypto and forex |
| **HyperScalper** | Fast EMA crossover | Liquid forex, fast markets |
| **London Breakout** | Session breakout | GBP pairs, European session |
| **Volatility Breakout** | Range compression breakout | Compressed markets |
| **Aggregator** | Multi-strategy parallel | Maximum capital efficiency |

See `09_TRADING_STRATEGIES.md` for detailed explanations of each strategy.

---

## The Theory: ICC (Indication, Correction, Continuation)

The core logic (used by several strategies) follows the ICC model. The bot does not guess tops or bottoms. It waits for the market to show its hand.

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

---

## Per-Asset Strategy Selection

Different assets behave differently. That's why you can assign different strategies per asset class:

```yaml
strategies:
  crypto: rubberband_reaper    # Mean reversion for volatile crypto
  forex: rubberband_reaper     # Proven +7,036% on forex
  stocks: quantum              # Trend-following for equities
  etf: quantum                 # Works on SPY, QQQ
  metals: mean_reversion       # Gold/Silver tend to range
  futures: volatility_breakout # Catch breakouts on ES, NQ
```

When the bot evaluates a symbol:
1. **Classify** → `EUR/USD` is `forex`
2. **Select** → Use `rubberband_reaper` strategy
3. **Evaluate** → Apply that strategy's logic

---

## The AI Backup
The hard-coded algorithm handles 90% of the work. But sometimes, the chart is messy.

### When the AI Steps In
If the Algorithm is unsure (Score between 40-59), it packages the chart data into a prompt and sends it to the LLM (Large Language Model).

**The Prompt:**
> "Here is the chart for BTC. Trend is Bullish. We just swept the lows. But volume is low. Would you take this trade? Y/N."

**The Response:**
The AI analyzes the context—Time of Day, recent volatility, vibes—and returns a verdict.
*   *"Yes, because we are in the London Session and the sweep is clean."* -> **Trade Approved.**
*   *"No, volume is dying and it looks like a trap."* -> **Stand Aside.**

This "Second Opinion" is designed to catch profitable setups that rigorous code might miss, or save you from "technically correct but stupid" trades.

### Supported AI Providers
| Provider | Notes |
|----------|-------|
| **Gemini** | Recommended. Good balance of quality & cost. |
| **OpenAI** | GPT-4, GPT-4 Turbo |
| **Claude** | Anthropic's Claude 3 |
| **DeepSeek** | Cost-effective alternative |
| **OpenRouter** | Access multiple models |

---

## Why This Works (The Guarantee)
This system guarantees **process**, not outcome.
*   It *guarantees* you won't buy the top (because it waits for Correction).
*   It *guarantees* you won't sell the bottom (because it waits for Indication).
*   It *guarantees* you won't trade blindly (because the AI double-checks).
*   It *guarantees* the right strategy for the right asset class.

In a chaotic market, a solid process is the closest thing to a money printer you will find.
