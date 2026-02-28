# 21. The Dashboard — Reading the GUI Like a Fighter Pilot

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"Whoa, the dashboard looks amazing! What do all these panels do?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Let me give you the tour. You opened the app. There's a chart. Numbers. Colors. A sidebar with things that blink. You feel like you accidentally opened NASA Mission Control.<br><br>Relax. Every panel has a purpose. Let's break it down."</td></tr></table>

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

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"This is your command center — navigation, status, and instrumentation all in one panel."</td></tr></table>

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

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"That's the bot's inner monologue. Every scan, every decision, every guard check. You'll get used to it."</td></tr></table>

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

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"If any of those happen, check Chapter 6 — The Panic Button. That's literally why it exists."</td></tr></table>
