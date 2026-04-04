---
title: 'The Sabbath Protocol: When the Bot Takes a Day Off'
category: rtfm
icon: synagogue
description: "\"Even God rested on the seventh day. The bot just switches to paper\
  \ trading.\" Some of us observe the Sabbath. The markets don't. This guide explains\
  \ how the bot automatically swaps to the Paper Broker during Sabbath, keeps scanning\
  \ and analyzing in paper mode, and seamlessly resumes live trading when Sabbath\
  \ ends \u2014 all calculated astronomically based on your location."
---

# 17. The Sabbath Protocol — When the Bot Takes a Day Off

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"The Sabbath Protocol is not optional! Rest is not a weakness, it's a strategy. Even the Most High took a day off. You think you're better than Him? You think your little forex account is more important than the literal creation of the universe? Sit down!"</td></tr></table>

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"But the market is still moving! What about my trades?!"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Your trades have server-side stops! They're protected! The bot doesn't actually go to sleep — it just switches to paper money so you don't violate the holy day trying to scalp two pips. It watches, it takes notes, and when the sun goes down on Saturday, it goes back to work. Breathe."</td></tr></table>

---

## The Dilemma

Two conflicting requirements:
1. **No real trading during Sabbath.** No buying. No selling. No profit-seeking.
2. **The markets are still moving.** Missing 25 hours of data means missing setups, missing exits, and coming back Saturday night to discover your position went sideways.

The answer: **Sabbath Mode.**

---

## How It Works

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"When candle-lighting time arrives — calculated astronomically based on your GPS coordinates — the bot does three things:"</td></tr></table>

### 1. The Swap
The bot swaps from the **real broker** to the **Paper Broker**. All new signals go to paper. Real money stops moving. The bot continues scanning, analyzing, making decisions — it just writes them on paper instead of sending them to the exchange.

### 2. The Heartbeat Goes Silent
The execution heartbeat goes quiet. No new orders. No modifications. No cancellations. Existing positions stay as they are, protected by server-side stop-losses and take-profits (already at the broker, don't require the bot).

### 3. The Paper Ledger
A separate paper trading ledger tracks what the bot *would have* done during Sabbath:
- Review paper trades Saturday night
- Bot's strategy engine stays calibrated (no 25-hour context gap)
- Live positions remain untouched and protected

---

## When Does It Start and End?

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"The bot uses astronomical calculations. Not a fixed time — because sunset changes throughout the year:"</td></tr></table>

- **Sabbath Start:** Candle-lighting time (18 minutes before sunset, Friday)
- **Sabbath End:** Three stars visible (approximately 42-72 minutes after sunset, Saturday)

> 📺 **In the UI:** Settings → **Hours & Sabbath** → use the **Location Resolver** (enter your city and click Resolve), or manually enter **Latitude**, **Longitude**, and **Timezone**

```yaml
sabbath_lat: 33.764     # Your latitude
sabbath_lon: -84.386    # Your longitude
sabbath_timezone: "America/New_York"
```

In June, Sabbath starts at 8:30 PM. In December, it starts at 5:15 PM. The bot handles this automatically. Every week.

---

## What Happens to Live Positions?

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"Live positions are NOT touched during Sabbath. Here's why that's safe:"</td></tr></table>

| Protection | Status During Sabbath |
|-----------|---------------------|
| **Stop-Loss** | Server-side. Active 24/7 regardless of bot state. |
| **Take-Profit** | Server-side. Active 24/7 regardless of bot state. |
| **Position Lock** | Still active — no new positions on the same symbol. |
| **Daily Loss Limit** | Still tracked. Kill switch still fires if positions stop out. |

Your live positions are as protected during Sabbath as they are at any other time. The only change: new trades go to paper.

---

## The Saturday Night Review

When Sabbath ends (three stars), the bot automatically:
1. **Switches back** to the real broker
2. **Logs the transition:** `[SABBATH] Sabbath ended. Resuming live execution.`
3. **Resumes normal operation**

Review the paper ledger (`data/paper_ledger.json`) to see:
- How many paper trades it took
- What the paper P&L would have been
- Whether you "missed" a big move

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Spoiler: you didn't miss anything. You observed Sabbath. That's the whole point."</td></tr></table>

---

## The Philosophy

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Trading is a tool! It serves you, you don't serve it! If your religion says 'take a day off,' the bot is going to respect it. It's not going to text you like a toxic ex saying 'omg look at this candle you missed.'<br><br>It handles the business, you handle your soul. We reconvene on Saturday night."</td></tr></table>


> [!NOTE]
> **APRIL 2026 UI & VITALS UPDATE:**  
> Listen up, you degenerates. We just dropped a massive update to the UI and Nurse's Station. The tooltips now trigger when you hover over the *entire goddamn card*, so your fat thumbs can't miss them anymore. The Exit Logic tab is now a clean, idiot-proof single column. We also fixed the Nurse's Station connection tracker—no more lying to you that the bot is dead when it's actively retrying to connect. Read **47_UI_OVERHAUL_AND_VITALS.md** for the full breakdown before you touch the controls and blow your account.
