
# 11. The Ghost in the Machine (AI & Strategy)
> *"I think, therefore I trade."*

You know the bot trades. But *how* does it decide?
This document explains the **Brain** (`strategy/engine.py`), the **Strategy Arsenal** (20 strategies), and the **Soul** (The AI Backup).

---

## The Multi-Strategy Arsenal

The bot isn't locked to one strategy. It has **20 distinct trading strategies**, each optimized for different market conditions. You can assign different strategies per asset class — or use **Meta-SCI** to let the bot choose automatically.

### Recommended: Meta-SCI Ensemble

| Strategy | Style | Best For |
|----------|-------|----------|
| **Meta-SCI** ⭐ | AI Ensemble (auto-selects best strategy) | All markets — the default |

Meta-SCI runs a **tournament** every scan cycle:
1. **Detects market regime** — Trending? Ranging? Choppy?
2. **Selects eligible strategies** — Only strategies that match the current regime compete
3. **Runs them all** — Each generates a signal independently (milliseconds)
4. **Picks the winner** — Highest-scoring signal becomes the trade decision
5. **Falls back gracefully** — No qualifying signal = STAND ASIDE

### Universal Strategies

| Strategy | Style | Best For |
|----------|-------|----------|
| **Rubberband Reaper** | Mean Reversion + Anti-Martingale | Ranging markets, volatile crypto |
| **RoboCop** | Sniper Precision | High-conviction setups |
| **Mean Reversion** | Bollinger + RSI | Ranging crypto and forex |
| **Supply & Demand** | Institutional Zones | Support/resistance plays |
| **Trend Rider** | EMA Pullback | Strong trending markets |
| **Session Momentum** | VWAP at Session Open | London/NY session opens |
| **Engulfing Reversal** | Candlestick Patterns | Key reversal levels |
| **ICC Core** | Pure ICC Structure | Structure-first patience |
| **ORB Breakout** | Opening Range Breakout | First-hour range breaks |

### Crypto-Specific Strategies

| Strategy | Style | Best For |
|----------|-------|----------|
| 🪙 **RSI + MACD** | Momentum Crossover | Crypto trending |
| 🪙 **VWAP Reversion** | Mean Reversion to VWAP | Crypto ranging |
| 🪙 **Double MACD** | Dual-TF Scalping | Crypto scalping |
| 🪙 **Virtual Grid** | Grid Trading | Crypto sideways |

See `09_FEET_WET_STRATEGY.md` for full details on all 20 strategies.

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

```json
{
  "profiles": {
    "my_profile": {
      "strategy": "meta_sci",
      "strategies": {
        "crypto": "meta_sci",
        "forex": "rubberband_reaper",
        "stocks": "trend_rider",
        "metals": "mean_reversion"
      }
    }
  }
}
```

When the bot evaluates a symbol:
1. **Classify** → `EUR/USD` is `forex`
2. **Select** → Use `rubberband_reaper` for forex
3. **Evaluate** → Apply that strategy's logic

With `meta_sci`: Step 2 becomes "run a tournament of all eligible strategies."

---

## The AI Backup
The hard-coded algorithm handles 90% of the work. But sometimes, the chart needs a second opinion.

### When the AI Steps In
The AI provides market commentary and decision validation. It doesn't replace the strategy — it augments it.

**The Flow:**
> Strategy signals ENTER_LONG on EURUSD → AI reviews the context → "Market structure is clean, volume supports the move. Confirmed." → Trade executes.

### Supported AI Providers
| Provider | Notes |
|----------|-------|
| **Gemini** | Recommended. Fast, cheap, good quality. |
| **OpenAI** | GPT-4, GPT-4 Turbo — premium analysis |
| **Claude** | Anthropic's Claude 3.5 — nuanced reasoning |
| **DeepSeek** | Cost-effective alternative |
| **OpenRouter** | Access multiple models via one API key |
| **Local (Ollama)** | Free, private, runs on your machine |

---

## The Safety Layer

Between the strategy's decision and execution, an entire safety layer validates the trade:

| Guard | What It Checks |
|-------|---------------|
| **Position Lock** | Is there already an open position on this symbol? → Block |
| **Leverage Sentry** | Would this trade exceed the leverage cap? → Block |
| **Daily Loss Limit** | Have daily losses hit the circuit breaker? → Block all trading |
| **ICC Gatekeeper** | Is the ICC score above the minimum threshold? → Block if too low |
| **Affordability** | Is there enough capital for the position size? → Block if insufficient |

These guards fire in sequence. If any one fails, the trade is blocked and logged with a clear reason.

---

## Why This Works (The Guarantee)
This system guarantees **process**, not outcome.
*   It *guarantees* you won't buy the top (because it waits for Correction).
*   It *guarantees* you won't sell the bottom (because it waits for Indication).
*   It *guarantees* you won't flip positions recklessly (Position Lock).
*   It *guarantees* the right strategy for the right market (Meta-SCI).
*   It *guarantees* you won't over-leverage (Leverage Sentry).
*   It *guarantees* you won't blow up in one day (Daily Loss Limit).

In a chaotic market, a solid process is the closest thing to a money printer you will find.
