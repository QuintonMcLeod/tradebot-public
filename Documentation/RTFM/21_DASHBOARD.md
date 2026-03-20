# 21. The Dashboard — Reading the GUI Like a Fighter Pilot

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"Whoa, the dashboard looks amazing! What do all these panels do?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Look at you. You open the app, you see a chart, some blinking lights, and suddenly you think you're launching a space shuttle. Calm down, Commander. It's a dashboard. It's designed so that even a guy who has to sound out the words on a Denny's menu can figure out if he is making money or losing money.<br><br>Let me give you the tour before you hurt yourself."</td></tr></table>

---

## The Layout

```
┌──────────────────────────────────────────────────┐
│  Title Bar: App name, window controls            │
├────────┬─────────────────────────────────────────┤
│        │                                         │
│ Side-  │        The Chart (Big Center Area)       │
│ bar:   │      Candlesticks, indicators, lines     │
│ Nav,   │                                         │
│ Status,├─────────────────────────────────────────┤
│ Update │  Log Panel (Bottom): Scrolling text      │
└────────┴─────────────────────────────────────────┘
```

---

## Zone 1: The Title Bar

| Element | What It Means |
|---------|--------------|
| **TRADEBOT SCI** | App name and logo. |
| **Window Controls** | Close (✕), minimize (—), maximize (☐). |

---

## Zone 2: The Chart

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"The chart is the main event. Everything else is supporting cast."</td></tr></table>

### Candlesticks
Standard OHLC. Green = up. Red = down. Height shows the range.

### Price Lines
- 🔴 **Stop-Loss Line** — Your downside protection
- 🟢 **Take-Profit Line** — Your target
- 🔵 **Entry Price Line** — Where you got in

### Indicators
Depending on active strategy:
- **EMA / SMA lines** — Trend direction
- **Bollinger Bands** — Volatility envelope
- **VWAP** — Volume-weighted average price

### Trade Markers
- 🟢 **▲ BUY** — Where the bot entered long
- 🔴 **▼ SELL** — Where the bot entered short
- ⚪ **EXIT** — Where the bot closed a position

---

## Zone 3: The Sidebar

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"This is the adult table. This is where the decisions happen. If you can't read what's in this sidebar, you shouldn't be trading. You should be putting your money in a savings account that yields 0.01%."</td></tr></table>

### Navigation & Status
- **Tab Navigation** — Dashboard, Graph, Settings, Profile, Help
- **Bot Running / Bot Stopped** — Green = running. Gray = stopped.
- **Start / Stop Button** — Controls the bot engine.
- **Update Available** — New version notification.

### Holdings Panel
Every open position:
- **Symbol** — What you're holding
- **Side** — LONG or SHORT
- **Size** — How many units
- **Entry Price** — Where you got in
- **Current Price** — Where it is now
- **P&L** — Winning or losing
- **SL / TP** — Where your stops are set

### Decisions Panel

| Decision | Meaning |
|----------|---------|
| **STAND_ASIDE** | Bot looked and decided not to trade. Most common. Often smartest. |
| **ENTER_LONG** | Buy setup detected |
| **ENTER_SHORT** | Sell setup detected |
| **EXIT** | Closing a position |

Each decision includes the **strategy name** and **score**.

### P&L Summary
- **Today's P&L** — How much made/lost today
- **Session P&L** — Current session performance
- **Unrealized P&L** — Open positions (not yet cashed)
- **Realized P&L** — Closed positions (real money)

---

## Zone 4: The Log Panel

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"That scrolling text at the bottom is intimidating."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Intimidating?! It's TEXT. Are you intimidated by a book?! That's the bot's inner monologue. Every scan, every decision, every time it looks at the market and says 'Wow, this is terrible,' it writes it down for you. Read it. Become one with it."</td></tr></table>

| What You'll See | What It Means |
|----------------|--------------|
| Green text | INFO — normal operation |
| Yellow text | WARNING — something blocked or unusual |
| Red text | ERROR — something broke (usually self-heals) |
| JSON blobs | Machine-readable data for the sidebar panels |

See Chapter 16 (**The War Room**) for the full log-reading guide.

---

## The Controls

- **Start / Stop Button** — Controls the bot engine
- **Settings Gear Icon** — Opens the settings panel
- **Symbol Selector** — Switches which chart is displayed (doesn't change what the bot scans)

---

## What "Healthy" Looks Like

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"When everything is working correctly:"</td></tr></table>

- Sidebar shows **Bot Running** in green
- Chart showing live candles with steady updates
- Log panel scrolling with `[SCAN]` and `[STATE]` entries
- Holdings panel shows positions with P&L numbers
- Decisions panel shows recent STAND_ASIDE / ENTRY decisions

**When to worry:**
- Bot status is **gray** and you didn't stop it
- Continuous `[ERROR]` lines in red
- No new log entries for 5+ minutes
- Holdings show positions with no SL/TP values

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"If the bot is gray, or spewing red errors, or just completely frozen like it's reconsidering its life choices... check Chapter 6. The Panic Button. Don't call me. Read the book."</td></tr></table>
