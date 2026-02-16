
# 11. The Ghost in the Machine (AI & Strategy)
> *"I think, therefore I trade."*

You know the bot trades. But *how* does it decide?
This document explains the **Brain** (`strategy/engine.py`), the **Strategy Arsenal**, and the **Soul** (The AI Backup).

---

## The Theory: ICC (Indication, Correction, Continuation)

The core logic follows the ICC model. The bot does not guess tops or bottoms. It waits for the market to show its hand.

### Step 1: Indication (The "Hint")
The price moves aggressively in one direction.
*   **The Bot Sees:** A "Clean Close" above a swing high.
*   **The Bot Thinks:** "Hmm. The bulls are awake."
*   **Action:** Nothing yet. I don't chase pumps.

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

## The Execution: Meta-SCI ⭐

> *"Why pick one strategy when the bot can hold tryouts every cycle?"*

Instead of committing to one strategy, Meta-SCI runs ALL eligible strategies in parallel and picks the best signal. It's like a talent show where the judges are math.

### Step 1: Regime Detection (The "What Kind of Day Is It?")
*   **The Bot Sees:** Market data flowing in — candles, volume, volatility.
*   **The Bot Thinks:** "Is this market trending, ranging, mean-reverting, or just pure chaos?"
*   **Action:** Classifies the current regime.

### Step 2: The Tournament (The "Hunger Games")
*   **The Bot Sees:** 10+ strategies all raising their hands.
*   **The Bot Thinks:** "Trend Rider, you only work in trends. Sit down. Rubberband Reaper, this isn't ranging. You too. Session Momentum... is it even session open? No? OUT."
*   **Action:** Disqualifies strategies that don't match the regime.

### Step 3: Winner Selection (The "And the Oscar Goes To...")
*   **The Bot Sees:** 3-4 surviving strategies, each with a score.
*   **The Bot Thinks:** "Trend Rider scored 78.5. Supply & Demand scored 65.2. We have a winner."
*   **Action:** **Executes the highest-scoring signal.** If nobody scores above threshold → STAND ASIDE.

---

## The Sniper: Rubberband Reaper

> *"Price is a rubber band. Stretch it far enough and it WILL snap back."*

Mean Reversion + Anti-Martingale. Best for ranging markets and volatile crypto.

### Step 1: The Stretch (The "That's Too Far")
Price flies way outside Bollinger Bands — 2.5 standard deviations from the mean.
*   **The Bot Sees:** Price shooting through the upper or lower Bollinger Band like it's trying to leave the chart.
*   **The Bot Thinks:** "Okay you're being dramatic. Nobody goes up 2.5 standard deviations and stays there."
*   **Action:** Starts watching closely.

### Step 2: RSI Confirmation (The "Are You Sure?")
*   **The Bot Sees:** RSI below 25 (oversold) or above 75 (overbought).
*   **The Bot Thinks:** "RSI agrees. This thing is exhausted. The rubber band is fully stretched."
*   **Action:** Prepares to enter the snap-back trade.

### Step 3: The Snap (The "I Told You So")
*   **The Bot Sees:** Price starting to reverse toward the mean.
*   **The Bot Thinks:** "Physics is physics. ENTRY. Target: the opposite Bollinger Band. That's a 3:1 minimum."
*   **Action:** **ENTRY.** And if I won the last trade, I'm sizing UP. If I lost? Sizing DOWN. That's anti-Martingale, baby.

---

## The Enforcer: RoboCop

> *"Dead or alive, you're coming with me."*

Sniper precision. Best for high-conviction setups only.

### Step 1: Structural Scan (The "Nothing Gets Past Me")
*   **The Bot Sees:** Multi-timeframe structure aligning — HTF trend, LTF confirmation, ICC gate scores.
*   **The Bot Thinks:** "I don't care about your 'gut feeling.' Show me the structure. Show me confluence. Show me MATH."
*   **Action:** Waiting. RoboCop does not chase. RoboCop waits for the setup to come to him.

### Step 2: High-Conviction Filter (The "Is This A+ or Not?")
*   **The Bot Sees:** Score above threshold. Multiple timeframes agree. The chart is clean.
*   **The Bot Thinks:** "This is the shot. Wide target — 3.0 ATR. I don't take trades to make pocket change."
*   **Action:** **ENTRY.** Fewer trades, bigger wins. Precision over frequency.

### Step 3: Chop Detection (The "I'm Not Sitting Here All Day")
*   **The Bot Sees:** Price going sideways. No conviction. Range-bound nonsense.
*   **The Bot Thinks:** "This isn't a trade anymore, it's a hostage situation. I'm getting OUT."
*   **Action:** **Chop exit.** Close the trade, free the capital, move on.

---

## The Mathematician: Mean Reversion

> *"What goes up must come down. What goes down must come up. Repeat forever."*

Bollinger + RSI. Best for ranging crypto and forex.

### Step 1: The Overshoot (The "That Was Excessive")
*   **The Bot Sees:** Price breaking outside 15-period, 2.5 std Bollinger Bands.
*   **The Bot Thinks:** "You went too far. The mean is calling. She wants you back."
*   **Action:** Marks the extreme. First entry loaded.

### Step 2: Pyramiding (The "Oh You're Still Going? Fine, I'll Add More")
*   **The Bot Sees:** Price continuing to push away from the mean.
*   **The Bot Thinks:** "Every step further is a bigger rubber band. I'll add up to 6 entries with cooldown between each. You CAN'T stay out here forever."
*   **Action:** Adds entries as price extends. Up to 6 layers deep.

### Step 3: The Return (The "Welcome Home")
*   **The Bot Sees:** Price crawling back to the middle Bollinger Band.
*   **The Bot Thinks:** "There she is. The mean. Like gravity — patient and inevitable."
*   **Action:** **EXIT.** All layers close. Profit collected across the entire pyramid.

---

## The Tracker: Supply & Demand

> *"I don't trade at random prices. I trade where the institutions left their footprints."*

Institutional zones. Best for support/resistance plays.

### Step 1: Zone Mapping (The "Who Was Here Before Me?")
*   **The Bot Sees:** Historical price action. Areas where price exploded away from a level.
*   **The Bot Thinks:** "Someone with serious money was buying here. They'll probably be back. Institutions don't just buy once — they accumulate."
*   **Action:** Maps supply zones (sell walls) and demand zones (buy floors).

### Step 2: Zone Strength Scoring (The "Has This Floor Been Tested?")
*   **The Bot Sees:** A zone that's held 3+ times. Each bounce makes it stronger.
*   **The Bot Thinks:** "Three bounces. This zone is LEGIT. The big players keep defending it."
*   **Action:** Marks the zone as high-priority for entry.

### Step 3: The Retest (The "Right on Schedule")
*   **The Bot Sees:** Price drifting back into a strong demand zone.
*   **The Bot Thinks:** "Welcome back to the zone. The institutions are loading up again. I'll ride with them."
*   **Action:** **ENTRY.** Target: the nearest supply zone. Clean, institutional-grade risk/reward.

---

## The Surfer: Trend Rider

> *"The trend is your friend. I wait for it to come pick me up."*

EMA pullback. Best for strong trending markets.

### Step 1: The Pullback (The "Come Back Down Here")
*   **The Bot Sees:** Price in a strong uptrend, pulling back toward the EMA.
*   **The Bot Thinks:** "Good. You raced ahead too fast. Come back to the EMA and I'll hop on."
*   **Action:** Waiting for price to touch the moving average.

### Step 2: Trend Confirmation (The "Everyone Agrees")
*   **The Bot Sees:** HTF trend is bullish. LTF trend is bullish. Both timeframes pointing the same direction.
*   **The Bot Thinks:** "Two timeframes agree. This isn't a fake rally. This is the real deal."
*   **Action:** Ready to enter.

### Step 3: The Bounce (The "Get On the Horse")
*   **The Bot Sees:** Price bouncing off the EMA in the trend direction. The pullback is over.
*   **The Bot Thinks:** "The trend just picked me up. Riding this wave until the higher timeframe flips."
*   **Action:** **ENTRY.** Exit when HTF trend reverses — not a moment sooner.

---

## The Clock Watcher: Session Momentum

> *"When London wakes up, the money starts moving. I'll be waiting at the door."*

VWAP at session open. Best for London/NY session opens.

### Step 1: Session Detection (The "The Bell Just Rang")
*   **The Bot Sees:** Clock hits 08:00 GMT (London) or 13:30 GMT (New York).
*   **The Bot Thinks:** "The big boys just sat down at their desks with their overpriced coffee. Volatility incoming in 3... 2... 1..."
*   **Action:** Calculates VWAP as the fair value anchor for the session.

### Step 2: Momentum Read (The "Which Way Are They Pushing?")
*   **The Bot Sees:** Early session price action relative to VWAP.
*   **The Bot Thinks:** "Price is above VWAP and pushing. The institutional flow is bullish. I'll go with the smart money, not against it."
*   **Action:** **ENTRY** in the direction of early session momentum.

### Step 3: Session Clock (The "Closing Time")
*   **The Bot Sees:** Session nearing its end. Target not hit.
*   **The Bot Thinks:** "The party's over. Liquidity is about to dry up. I'm not holding through the dead zone."
*   **Action:** **EXIT** before session close if target isn't reached.

---

## The Pattern Reader: Engulfing Reversal

> *"One candle to rule them all."*

Candlestick patterns. Best for key reversal levels.

### Step 1: Pattern Detection (The "Did You See That?!")
*   **The Bot Sees:** A massive candle that completely engulfs the previous one. The bulls ate the bears alive (or vice versa).
*   **The Bot Thinks:** "That's not a normal candle. That's a statement. Someone just said 'we're going THIS way now.'"
*   **Action:** Flags the engulfing pattern.

### Step 2: Key Level Filter (The "But WHERE Did It Happen?")
*   **The Bot Sees:** The engulfing candle formed at a significant support/resistance level.
*   **The Bot Thinks:** "An engulfing candle in the middle of nowhere? Boring. An engulfing candle AT a key level? That's a reversal signal."
*   **Action:** Confirms location is significant. Checks volume — above average? Yes? Good.

### Step 3: The Reversal (The "New Sheriff in Town")
*   **The Bot Sees:** Confirmation bar following the engulfing pattern.
*   **The Bot Thinks:** "The engulfing happened at a key level, with volume. This trend is done. New direction confirmed."
*   **Action:** **ENTRY.** Stop beyond the engulfing candle's range. Tight risk, clean setup.

---

## The Purist: ICC Core

> *"Pure structure. No shortcuts. No feelings. Just textbook."*

The purest implementation of the Indication-Correction-Continuation framework. Zero shortcuts. Zero aggressive entries. This is the strategy for people who believe in discipline the way monks believe in silence. It follows the exact same three steps as "The Theory" above — but applies them with maximum patience and zero deviation.

### Step 1: Indication — Wait for proof.
### Step 2: Correction — Wait for the pullback.
### Step 3: Continuation — Wait for the market to resume. Then execute.

---

## The Early Bird: ORB Breakout

> *"The first 15 minutes write the story for the day."*

Opening range breakout. Best for first-hour range breaks.

### Step 1: Mark the Range (The "Draw the Lines")
*   **The Bot Sees:** The first 15-30 minutes of the session forming a high and a low.
*   **The Bot Thinks:** "The opening range is set. This is the battlefield. Everything above is bull territory. Everything below is bear territory."
*   **Action:** Records the Opening Range — high and low.

### Step 2: The Break (The "Someone Kicked the Door In")
*   **The Bot Sees:** Price smashing through the top or bottom of the opening range.
*   **The Bot Thinks:** "BREAK! And the volume is strong — this isn't a fake-out. The market has chosen a direction."
*   **Action:** **ENTRY** on the breakout side.

### Step 3: The Target (The "How Far Can This Go?")
*   **The Bot Sees:** Price extending past the range.
*   **The Bot Thinks:** "Target is 1.5-2.0x the range height. Clean, mathematical, no guessing."
*   **Action:** Holds until target or stops out. No negotiation.

---

## The Crypto Specialists

These strategies are automatically included in Meta-SCI tournaments when scanning crypto symbols.

---

### The Duo: RSI + MACD 🪙

> *"Two indicators walk into a bar. They both agree. Now THAT's a signal."*

Momentum crossover. Best for crypto trending markets.

### Step 1: RSI reads the exhaustion.
*   **The Bot Sees:** RSI dropping below 30.
*   **The Bot Thinks:** "RSI says oversold."

### Step 2: MACD confirms the shift.
*   **The Bot Sees:** MACD histogram turning green.
*   **The Bot Thinks:** "MACD says momentum is shifting. When both agree, crypto tends to rip."

### Step 3: Both agree — or no deal.
*   **Action:** **ENTRY.** If either indicator disagrees — no trade. Both must confirm or I walk.

---

### The Gravity Well: VWAP Reversion 🪙

> *"Price always visits VWAP. It's like gravity for crypto."*

Mean reversion to VWAP. Best for ranging crypto.

### Step 1: Measure the drift.
*   **The Bot Sees:** Price drifting far from the session VWAP.

### Step 2: Watch the fuel gauge.
*   **The Bot Sees:** Volume is exhausting at the extreme.
*   **The Bot Thinks:** "You're 3% above VWAP with dying volume. You've got no fuel left. Come back home."

### Step 3: Trade the return.
*   **Action:** **ENTRY** toward VWAP. Target: VWAP itself. Simple. Effective. Repeatable.

---

### The Scalper: Double MACD 🪙

> *"Two timeframes, one verdict."*

Dual-timeframe scalping. Best for fast crypto scalps.

### Step 1: Fast chart signals entry.
*   **The Bot Sees:** Fast timeframe MACD crossing bullish.

### Step 2: Slow chart confirms the wind direction.
*   **The Bot Sees:** Slow timeframe MACD already bullish.
*   **The Bot Thinks:** "The fast chart says 'go.' The slow chart says 'we're already going.' Two timeframes confirm."

### Step 3: Quick in, quick out.
*   **Action:** **ENTRY.** Short-duration trade. Get in, get out, don't overstay the welcome.

---

### The Pinball Machine: Virtual Grid 🪙

> *"Grid trading without the grid. All the upside, none of the baggage."*

Virtual grid trading. Best for crypto sideways markets.

### Step 1: Identify the range.
*   **The Bot Sees:** Crypto moving sideways in a well-defined range. No trend. Just oscillation.

### Step 2: Set virtual zones.
*   **The Bot Thinks:** "You're bouncing between $95K and $97K like a pinball. I'll set virtual buy zones at the bottom and sell zones at the top. Every bounce is a trade."

### Step 3: Accumulate on every bounce.
*   **Action:** **Buys at low levels, sells at high levels.** No actual grid orders placed — all virtual. Accumulates during consolidation.

---

## The Reserves (Legacy & Niche)

| Strategy | Key | Style | Best For |
|----------|-----|-------|----------|
| **Robot Evolution** | `evolution` | NTZ Edge Scalping | Sideways/consolidation |
| **Quantum** | `quantum` | SMA Trend Following | Strong trending forex |
| **HyperScalper** | `hyper_scalper` | Fast EMA Crossover | Liquid forex, fast markets |
| **London Breakout** | `london_breakout` | Session Range Breakout | GBP pairs, European session |
| **Volatility Breakout** | `volatility_breakout` | Range Compression Breakout | Compressed markets |
| **Aggregator** | `aggregator` | Multi-Strategy Parallel | Maximum capital efficiency |

---

## Per-Asset Strategy Selection

Different assets behave differently. That's why you can assign different strategies per asset class:

> 📺 **In the UI:** Settings → **Strategy Workshop** → **Asset Strategies** sub-tab — choose a strategy per asset class (Crypto, Forex, Stocks, Metals)

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
