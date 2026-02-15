
# 21. The Dashboard (Reading the GUI Like a Fighter Pilot)
> *"If fighter pilots can land on aircraft carriers using instruments, you can read a P&L number."*

You opened the app. There's a chart. There are numbers. There are colors. There's a sidebar with things that blink. You feel like you accidentally opened NASA Mission Control.

Relax. Let's break down every piece of the dashboard so you can look at it with confidence instead of confusion.

---

## The Big Picture: Layout

The GUI is divided into zones, like a fighter pilot's cockpit:

```
┌──────────────────────────────────────────────────┐
│  Title Bar: Bot status, version, update button   │
├──────────────────────────────────────────────────┤
│                                                  │
│            The Chart (Big Center Area)            │
│          Candlesticks, indicators, lines          │
│                                                  │
├──────────────────────────────────────────────────┤
│  Sidebar: Holdings, P&L, Decisions, Controls     │
├──────────────────────────────────────────────────┤
│  Log Panel (Bottom): The scrolling text stream    │
└──────────────────────────────────────────────────┘
```

Let's go zone by zone.

---

## Zone 1: The Title Bar

The title bar tells you two things at a glance:

| Element | What It Means |
|---------|--------------|
| **Bot Running** / **Bot Stopped** | Is the engine currently active? Green = running. Gray = stopped. |
| **Update Available** | A new version exists on the remote repo. Click to update. |
| **Window Controls** | Close, minimize, maximize. Standard stuff. |

The title bar is your "am I okay?" quick check. If it's green, you're good. If it's gray, the bot isn't running. If there's an update badge, you should update.

---

## Zone 2: The Chart

The chart is the main event. It shows:

### Candlesticks
Standard OHLC candlesticks. Green = price went up. Red = price went down. The height of the candle shows the range.

### Price Lines
*   🔴 **Stop-Loss Line** — Your downside protection. If price touches this, the position closes at a controlled loss.
*   🟢 **Take-Profit Line** — Your target. If price touches this, profit is taken automatically.
*   🔵 **Entry Price Line** — Where you got in. The reference point for "am I winning?"

### Indicators
Depending on the active strategy, you might see:
*   **EMA / SMA lines** — Moving averages showing the trend direction
*   **Bollinger Bands** — Volatility envelope around the price
*   **VWAP** — Volume-weighted average price (crypto and intraday)

### Trade Markers
*   🟢 **▲ BUY** markers — Where the bot entered long
*   🔴 **▼ SELL** markers — Where the bot entered short
*   ⚪ **EXIT** markers — Where the bot closed a position

---

## Zone 3: The Sidebar

This is your instrumentation panel. Each section tells you something critical:

### Holdings Panel
Shows every open position:
*   **Symbol** — What you're holding
*   **Side** — LONG or SHORT
*   **Size** — How many units
*   **Entry Price** — Where you got in
*   **Current Price** — Where it is now
*   **P&L** — How much you're winning or losing on this position
*   **SL / TP** — Where your stop-loss and take-profit are set

### Decisions Panel
Shows the bot's most recent decisions for each scanned symbol:
*   **STAND_ASIDE** — The bot looked and decided not to trade. This is the most common (and often the smartest) decision.
*   **ENTER_LONG** — The bot saw a buy setup
*   **ENTER_SHORT** — The bot saw a sell setup
*   **EXIT** — The bot decided to close an existing position
*   Each decision includes the **strategy name** and **score** so you can see why it decided

### P&L Summary
*   **Today's P&L** — How much you've made or lost today
*   **Session P&L** — P&L for the current trading session
*   **Unrealized P&L** — P&L from positions still open (not yet cashed)
*   **Realized P&L** — P&L from positions that have been closed (real money)

---

## Zone 4: The Log Panel

The scrolling text at the bottom. This is the bot's inner monologue — every scan, every decision, every guard check.

| What You'll See | What It Means |
|----------------|--------------|
| Green text | INFO — normal operation |
| Yellow text | WARNING — something was blocked or unusual |
| Red text | ERROR — something broke (usually self-heals) |
| JSON blobs | Machine-readable data for the sidebar panels |

See "The War Room" (Article 16) for a full guide to reading the logs.

---

## The Controls

### Start / Stop Button
Starts or stops the bot engine. When stopped, the bot isn't scanning or trading. When running, it's doing its thing.

### Settings Gear Icon
Opens the settings panel. This is where you configure everything: profiles, strategies, brokers, risk, and safety parameters.

### Symbol Selector
Lets you switch which symbol's chart is displayed. This doesn't change what the bot is scanning — it just changes your view.

---

## What "Healthy" Looks Like

When everything is working correctly:
*   Title bar shows **Bot Running** in green
*   Chart is showing live candles with steady updates
*   Log panel is scrolling with `[SCAN]` and `[STATE]` entries
*   Holdings panel shows your positions (if any) with P&L numbers
*   Decisions panel shows recent STAND_ASIDE / ENTRY decisions

**When to worry:**
*   Bot status is **gray** and you didn't stop it
*   Log panel shows continuous `[ERROR]` lines in red
*   No new log entries for more than 5 minutes
*   Holdings panel shows positions with no SL/TP values

If any of these happen, check Article 06 ("The Panic Button") for emergency procedures.
