
# 15. The Night Watch (Overnight & Weekend Positions)
> *"The market never sleeps. Neither does your anxiety."*

So you've got an open position and the clock says 11 PM. Your spouse is already asleep. Your dog is judging you. And you're sitting there, watching a 5-minute chart in your underwear, wondering if EUR/USD is going to gap against you overnight.

Stop it.

**That's the bot's job now.**

---

## The Problem: Humans Need Sleep, Markets Don't

Here's the ugly truth about trading:
*   **Forex** trades 24 hours a day, 5 days a week. It takes breaks only for weekends and the occasional existential crisis.
*   **Crypto** doesn't even get weekends. It runs 24/7/365. Christmas? Trading. Your birthday? Trading. The heat death of the universe? Probably still trading.
*   **You**, on the other hand, need 7-8 hours of sleep, food, bathroom breaks, and the occasional human interaction.

This mismatch is why most retail traders lose money. They open a trade at 2 PM, go to bed at 10 PM, and wake up at 6 AM to discover that Tokyo decided to ruin their week.

---

## How the Bot Handles the Night Shift

### The Stop-Loss is Your Nightlight
Every trade the bot places has a **stop-loss**. Not a "mental" stop-loss. Not a "I'll close it if it gets bad" stop-loss. An actual, server-side, "I don't care if the internet goes down" stop-loss.

*   **The Bot Sets:** An ATR-based stop-loss at the moment of entry.
*   **While You Sleep:** If Tokyo decides to send EUR/USD to the shadow realm, the stop-loss catches it.
*   **What You Wake Up To:** Either the trade is still running (great) or it was stopped out for a controlled loss (survivable). Never a margin call.

### The Take-Profit is Your Alarm Clock
Similarly, every trade has a **take-profit**. If the London session rips in your favor at 3 AM while you're dreaming about being a professional dog walker, the bot takes the profit. No alarm needed. No "just 5 more pips" greed.

---

## Weekend Risk: The Gap Monster

Friday at 5 PM EST, the forex market closes. Sunday at 5 PM EST, it reopens. In between? **Nobody is trading.** But the world keeps spinning. Geopolitical events, natural disasters, surprise central bank announcements — all of this happens while you can't do anything about it.

When the market reopens, price can **gap** — meaning it opens at a completely different level than where it closed.

### The Bot's Weekend Protocol

| Setting | What It Does |
|---------|-------------|
| **Flatten on Exit** | Closes all forex positions before the weekend gap zone |
| **Crypto Exception** | Crypto never closes, so crypto positions are never auto-flattened |
| **Intraday Flatten** | Optional: close all positions at session end every day |

The default behavior: **If you're running a forex profile, positions flatten before the weekend.** If you're running crypto, they stay open because crypto doesn't have gaps (it has 48-hour crashes instead, which is somehow worse).

---

## The 3 AM Rule

Professional traders have a saying: "Nothing good happens after midnight in the markets."

This is statistically true. Liquidity drops, spreads widen, and the only people trading at 3 AM EST are:
1. Algorithms (like this one)
2. Insomniac retail traders making revenge trades
3. A guy in Tokyo who just had his third Red Bull

The bot doesn't care what time it is. It evaluates structure, not clocks. But it does factor in **session awareness** — if the relevant session isn't active, some strategies (like Session Momentum) simply won't fire. The bot won't take a "London Breakout" trade at 3 AM EST because London is asleep. Common sense, coded.

---

## What You Should Actually Do Before Bed

1. **Check the dashboard.** Open positions look healthy? SL/TP set? Good.
2. **Check your leverage.** Under your cap? Good.
3. **Close the laptop.**
4. **Go to sleep.**
5. **Trust the process.** The bot has guards. The stop-loss is set. The world will not end overnight. (Probably.)

If you find yourself waking up at 3 AM to check your phone, you are either:
- Over-leveraged (fix your position size), or
- Not trusting the system (fix your psychology)

Both are fixable. Neither requires you to lose sleep.

---

## The Guarantee

The Night Watch guarantees one thing: **you will never wake up to an uncontrolled loss.** Every position has a stop. Every stop is server-side. Every exit is calculated. The bot doesn't panic at 3 AM. It doesn't revenge trade. It doesn't "hold and hope."

It either wins while you sleep, or it loses a controlled amount while you sleep. Either way, you slept. And that's worth more than any trade.
