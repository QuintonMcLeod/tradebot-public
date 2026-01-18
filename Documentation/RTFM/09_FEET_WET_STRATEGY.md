# 09_FEET_WET_STRATEGY: The Safety First Approach

> **"Don't dive into the deep end until you know the water isn't boiling."**

The "Feet Wet" strategy isn't just a config file; it's a **philosophy of survival** combined with aggressive opportunity.

## Executive Summary: What to Expect
**"Probe, Verify, Pyramid."**

Behind the scenes, this strategy uses a "High Risk / High Reward" math model, but it applies it with **Micro-Sizing**.

### The Reality: You Will Lose Often
You must be prepared for this: **The bot has a Win Rate of ~27%.**
That means out of 10 trades, **7 will likely be losses.** You will see a string of small red numbers in your logs. **This is normal.** The bot is "feeling around" for a trend.

### The Payoff: Pyramiding Wins
When the bot finally catches one of those 3 winning trades, it doesn't just sit there. It uses **Pyramiding**.
- It detects the trend is real.
- It adds more money to the winning position (using the house's money).
- It moves the Stop Loss to Breakeven.

**The Result:** One big win can pay for 10 small losses and still leave you in profit.

### The Safety: The "Cup of Coffee" Rule
Because we start with tiny sizing (1% of capital), the cost of being wrong is negligible.
- If you have a **$100 account**, a loss is only **$1 or $2**.
- That's the price of a cheap cup of coffee, not your rent.

This allows you to survive the "chop" (the 7 losses) until you hit the "home run" (the 1 pyramided win).


---

## 1. What is "Feet Wet"?

It is a **Day 1 Configuration** designed to verify:
1.  **Connectivity:** Can the bot talk to IBKR?
2.  **Data Flow:** Are prices arriving?
3.  **Execution:** Can orders be placed and canceled without rejection?
4.  **Logic:** Is the ICC model making sense?

It does all of this **without blowing up your account**.

---

## 2. The Configuration (Why it's Safe)

The `feet_wet` profile (which is effectively the default `intraday` profile with conservative overrides) enforces these rules:

### A. Tiny Risk Per Trade (1%)
- **Standard:** 10% per entry (Aggressive).
- **Feet Wet:** **1% per entry**.
- **Result:** If you lose a trade, you lose a cup of coffee, not your rent.

### B. Continuous Operation
- **Rule:** The bot runs 24/7 (or 24/5 for Forex).
- **Behavior:** No forced exits at end-of-day. Positions are held until the strategy dictates an exit.
- **Why:** Crypto never sleeps, and Forex trends often span multiple days.
- **Note:** Ensure your machine/VPS stays online.

### C. Works for All Assets
- **Scope:** Forex, Crypto, Stocks, Futures.
- **Logic:** The "Feet Wet" safety checks apply universally.
- **Live Trading Disabled (Initially):**
- **Default:** `EXECUTE_TRADES=false` (Simulation Mode).
- **Behavior:** The bot makes decisions, "places" fake orders in the log, and tracks PnL.
- **Goal:** Verify the strategy works on *your* data feed before risking a cent.

### D. Single Position Only
- **Rule:** `MULTI_POSITION_ENABLED=false`.
- **Why:** Manage one thing at a time. Watching 5 flashing positions on Day 1 is how mistakes happen.

---

## 3. How to Graduate

You stay on "Feet Wet" until you can answer **YES** to these three questions:

1.  **"Did I see the bot execute a trade exactly as I expected?"** (Entry, Stop, Take Profit).
2.  **"Did the PnL tracking match my broker statement (or Simulation log)?"**
3.  **"Do I trust the bot to run for 1 hour without me staring at it?"**

Once you answer YES, you graduate:
1.  **Bump Risk:** Increase from 1% to 2%, then 5%.
2.  **Enable Mult-Position:** Trade 2-3 pairs at once.
3.  **Explore Strategies:** Switch to `swing` or `crypto_247`.

**But for today: Keep your feet wet.**
The market will be there tomorrow.
