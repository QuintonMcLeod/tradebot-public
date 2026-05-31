---
title: 'The Night Watch: Sleeping While Your Money Works'
category: rtfm
icon: bedtime
description: "\"The market never sleeps. Neither does your anxiety.\" So you've got\
  \ an open position and the clock says 11 PM. Your spouse is already asleep. Your\
  \ dog is judging you. This guide explains how the bot handles overnight and weekend\
  \ positions \u2014 server-side stops, weekend gap protection, and why checking your\
  \ phone at 3 AM is a sign you need to fix your position sizing, not your alarm."
---

# 15. The Night Watch — Overnight & Weekend Positions

<table><tr><td width="170"><img src="img/monk.png" width="150"></td><td><b>MONK</b>:<br><em>"While you sleep, the bot watches. The night shift runs in silence and discipline. No complaints. No overtime pay."</em></td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"It's 11 PM. Your spouse is asleep. Your dog is looking at you with disappointment. And you're sitting in the dark in your underwear, sweating bullets over a 5-minute chart, praying that the Bank of Japan doesn't ruin your life while you're unconscious.<br><br>Stop doing that! That is exactly what the bot is for! Go to sleep! You look ridiculous!"</td></tr></table>

---

## The Problem: Humans Need Sleep, Markets Don't

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"Here's the ugly truth about trading:"</td></tr></table>

- **Forex** trades 24 hours a day, 5 days a week. It only pauses for weekends and the occasional existential crisis.
- **Crypto** doesn't even get weekends. 24/7/365. Your birthday? Trading. The heat death of the universe? Probably still trading.
- **You**, on the other hand, need 7-8 hours of sleep, food, bathroom breaks, and the occasional human interaction.

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"This mismatch is why most retail traders lose money. They open a trade at 2 PM, go to bed at 10 PM, and wake up at 6 AM to discover that Tokyo decided to ruin their week. The bot doesn't have this problem because the bot doesn't sleep."</td></tr></table>

---

## How the Bot Handles the Night Shift

### The Stop-Loss is Your Nightlight

<table><tr><td width="170"><img src="img/ninja.png" width="150"></td><td><b>NINJA</b>:<br><em>"Every trade has a server-side stop-loss. Not a 'mental' stop-loss. Not a 'I'll close it if it gets bad' stop-loss. An actual, broker-held, 'I don't care if the internet goes down' stop-loss."</em></td></tr></table>

- **The Bot Sets:** An ATR-based stop-loss at the moment of entry.
- **While You Sleep:** If Tokyo sends EUR/USD to the shadow realm, the stop catches it.
- **What You Wake Up To:** Either still running (great) or stopped out for a controlled loss (survivable). Never a margin call.

### The Take-Profit is Your Alarm Clock

If London rips in your favor at 3 AM while you're dreaming about being a professional dog walker, the bot takes the profit. No alarm needed. No "just 5 more pips" greed.

---

## Weekend Risk: The Gap Monster

<table><tr><td width="170"><img src="img/bear.png" width="150"></td><td><b>BEAR</b>:<br>"Friday 5 PM EST: forex closes. Sunday 5 PM EST: it reopens. In between? Nobody is trading. But the world keeps spinning. Geopolitical events, surprise announcements — all happening while you can't do anything. When the market reopens, price can GAP. That gap can be ugly."</td></tr></table>

### The Bot's Weekend Protocol

| Setting | What It Does |
|---------|-------------|
| **Flatten on Exit** | Closes all forex positions before the weekend gap zone |
| **Crypto Exception** | Crypto never closes, so crypto positions are never auto-flattened |
| **Intraday Flatten** | Optional: close all positions at session end every day |

Default: forex positions flatten before the weekend. Crypto stays open because crypto doesn't have gaps — it has 48-hour crashes instead, which is somehow worse.

---

## The 3 AM Rule

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Professional traders have a saying: 'Nothing good happens after midnight in the markets.' This is statistically true. Liquidity drops, spreads widen, and the only people trading at 3 AM are:"</td></tr></table>

1. Algorithms (like this one)
2. Insomniac retail traders making revenge trades
3. A guy in Tokyo who just had his third Red Bull

The bot doesn't care what time it is — it evaluates structure, not clocks. But it factors in **session awareness**. It won't take a "London Breakout" trade at 3 AM EST because London is asleep. Common sense, coded.

---

## What You Should Actually Do Before Bed

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"Here's your bedtime checklist, sweetie:"</td></tr></table>

1. **Check the dashboard.** Open positions healthy? SL/TP set? Good.
2. **Check your leverage.** Under your cap? Good.
3. **Close the laptop.**
4. **Go to sleep.**
5. **Trust the process.** The bot has guards. The stop-loss is set. The world will not end overnight. (Probably.)

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"If you find yourself waking up at 3 AM to check your phone, you are either over-leveraged (fix your position size) or not trusting the system (fix your psychology). Both are fixable. Neither requires losing sleep."</td></tr></table>

---

## The Guarantee

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"The Night Watch guarantees one thing: <b>you will never wake up to an uncontrolled loss.</b> Every position has a stop. Every stop is server-side. Every exit is calculated. The bot doesn't panic at 3 AM. It doesn't revenge trade. It doesn't 'hold and hope.'<br><br>It either wins while you sleep, or it loses a controlled amount while you sleep. Either way — you slept. And that's worth more than any trade."</td></tr></table>

---

## 📖 Continue Reading

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"Wow, okay I think I get it now. What's next?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Turn the page. We are going to talk about <b>War Room</b>. Try to keep up."</td></tr></table>
