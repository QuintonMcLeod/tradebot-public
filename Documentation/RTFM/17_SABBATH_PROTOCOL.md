
# 17. The Sabbath Protocol (When the Bot Takes a Day Off)
> *"Even God rested on the seventh day. The bot just switches to paper trading."*

Some of us observe the Sabbath. The sun goes down Friday evening, and for approximately 25 hours, you're supposed to rest, reflect, and absolutely NOT be glued to a trading terminal watching candles like a degenerate.

But the market doesn't observe your Sabbath. EUR/USD doesn't care about your spiritual practices. Bitcoin has never heard of Shabbat.

So we built a solution.

---

## The Dilemma

You have two conflicting requirements:
1. **No real trading during Sabbath.** No buying. No selling. No profit-seeking. The commandments are pretty clear on this one.
2. **The markets are still moving.** Missing 25 hours of market data means missing potential setups, missing exit signals, and coming back on Saturday night to discover your position went sideways while you were eating challah.

The answer: **Sabbath Mode.**

---

## How It Works

When the Sabbath candle-lighting time arrives (calculated astronomically based on your GPS coordinates), the bot does three things:

### 1. The Swap
The bot swaps from the **real broker** to the **Paper Broker**. All new signals get routed to the paper engine. Real money stops moving. The bot continues to scan, analyze, and make decisions — it just writes them on paper instead of sending them to the exchange.

### 2. The Heartbeat Goes Silent
The execution heartbeat — the part that actually sends orders — goes quiet. No new orders. No modifications. No cancellations. Existing positions stay as they are, protected by their server-side stop-losses and take-profits (which are already placed at the broker and don't require the bot to be active).

### 3. The Paper Ledger
A separate paper trading ledger tracks what the bot *would have* done during Sabbath. This means:
*   You can review the paper trades Saturday night and see if you "missed" anything
*   The bot's strategy engine stays calibrated (it doesn't lose context from a 25-hour gap)
*   Your live positions remain untouched and protected

---

## When Does It Start and End?

The bot uses **astronomical calculations** to determine:
*   **Sabbath Start:** Candle-lighting time (18 minutes before sunset, Friday)
*   **Sabbath End:** Three stars visible (approximately 42-72 minutes after sunset, Saturday)

You configure your location:

> 📺 **In the UI:** Settings → **Hours & Sabbath** → use the **Location Resolver** (enter your city and click Resolve), or manually enter **Latitude**, **Longitude**, and **Timezone**

```yaml
sabbath_lat: 33.764     # Your latitude
sabbath_lon: -84.386    # Your longitude
sabbath_timezone: "America/New_York"
```

The bot calculates the exact sunset time for your location, every single week. It doesn't use a fixed time because sunset changes throughout the year. In June, Sabbath starts at 8:30 PM. In December, it starts at 5:15 PM. The bot handles this automatically.

---

## What Happens to Live Positions?

Live positions are **not touched** during Sabbath. Here's why that's safe:

| Protection | Status During Sabbath |
|-----------|---------------------|
| **Stop-Loss** | Server-side. Active 24/7 regardless of bot state. |
| **Take-Profit** | Server-side. Active 24/7 regardless of bot state. |
| **Position Lock** | Still active — no new positions on the same symbol. |
| **Daily Loss Limit** | Still tracked. If positions stop out, the kill switch still fires. |

Your live positions are as protected during Sabbath as they are at any other time. The only thing that changes is that new trades go to paper.

---

## The Saturday Night Review

When Sabbath ends (three stars), the bot automatically:
1. **Switches back** to the real broker
2. **Logs the transition** — `[SABBATH] Sabbath ended. Resuming live execution.`
3. **Resumes normal operation**

You can then review the paper ledger (`data/paper_ledger.json`) to see what the bot did during Sabbath:
*   How many paper trades it took
*   What the paper P&L would have been
*   Whether you "missed" a big move (spoiler: you didn't miss anything. You observed Sabbath. That's the whole point.)

---

## The Philosophy

Trading is a tool. It serves you — you don't serve it. If your faith requires rest, the bot respects that. It doesn't guilt-trip you for taking a day off. It doesn't FOMO you with "look what you missed!" notifications.

It simply says: "I've got this. Go rest. I'll keep watching and take notes. We'll compare notes Saturday night."

That's the Sabbath Protocol.
