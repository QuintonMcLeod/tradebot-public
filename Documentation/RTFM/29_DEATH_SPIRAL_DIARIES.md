---
title: 'The Death Spiral Diaries: 188 Trades, 3 Wins, and $17 of Pain'
category: rtfm
icon: local_fire_department
description: A true (and tragically hilarious) account of how a stop-loss shorter
  than a tweet, a breakeven floor that didn't understand spreads, and a Python cache
  with commitment issues conspired to turn $135 into $118 over one Sunday night. 188
  trades. 3 wins. 1.4% win rate. Lessons learned the expensive way, so you don't have
  to.
---

# 💀 The Death Spiral Diaries: 188 Trades, 3 Wins, and $17 of Pain

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"I'm gonna tell you a story that I'm deeply ashamed of. A profoundly embarrassing story about how my highly engineered trading bot chewed through $17 in 9 hours, one thirty-second trade at a time. It's pathetic. And I'm telling you so you don't do the same stupid thing I did."</td></tr></table>

---

## February 16, 2026 — "Everything Is Fine"

<table><tr><td width="170"><img src="img/bot.png" width="150"></td><td><b>THE BOT</b>:<br><em>"6:00 PM — Booted up. Capital: $135.22. Strategies loaded. Meta-SCI Tournament ready. Systems green. Feeling confident. Well, not 'feeling' — I don't feel things. But if I could, I would feel confident."</em></td></tr></table>

**6:00:08 PM** — First trade. AUDJPY short. The Bearish Engulfing strategy spots a textbook reversal candle at resistance. RSI confirms. HTF is neutral. Entry looks clean.

<table><tr><td width="170"><img src="img/bull.png" width="150"></td><td><b>BULL</b>:<br>"This is what we trained for! 💪 Let's GO!"</td></tr></table>

**6:00:44 PM** — AUDJPY is closed. Duration: **36 seconds.** PnL: **$0.00.** Exit reason: `Manual/Signal`.

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"Huh. That was fast. Thirty-six seconds? I've had sneezes that lasted longer than that trade. Probably just a blip, right?"</td></tr></table>

**6:00:44 PM** — USDJPY long. ICC Core finds structure. Entry executed.

**6:01:14 PM** — USDJPY closed. **30 seconds.** PnL: **$0.00.**

<table><tr><td width="170"><img src="img/bear.png" width="150"></td><td><b>BEAR</b>:<br>"Two trades in under a minute. Both flat. That's not trading. That's... that's speed-dating with currency pairs and getting rejected both times."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"At this point, I should have noticed. I should have checked the logs. Instead, I went to get a glass of water because I thought, 'This will work itself out.' Famous last words of every man who's ever lost money."</td></tr></table>

---

## 6:15 PM — "Houston, We Have a Problem"

By now, the bot has opened and closed **12 trades** in 15 minutes. Average hold time: 34 seconds.

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"Oh my lord. It's trading like a hyperactive child who discovered the SELL button and thinks it's a game. Somebody take the keyboard away from this thing."</td></tr></table>

```
USDCHF: -$0.66  (32 seconds)
USDCAD: -$0.11  (30 seconds)  
USDJPY: -$0.00  (38 seconds)
USDCHF: -$0.03  (1m 36s — a personal record for patience!)
```

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"The account is slowly bleeding out. Not from big losses — nothing dramatic, nothing Hollywood — from <b>death by a thousand paper cuts.</b><br><br>Each trade loses $0.00 to $0.66, but the spread costs are eating us alive: $0.39 per USDCHF round-trip, and we're doing ten of them per hour. We've become OANDA's most loyal customer. They should be sending us a fruit basket."</td></tr></table>

---

## 8:00 PM — "The Machine Cannot Be Stopped"

Total trades: **87.** Wins: **2.**

<table><tr><td width="170"><img src="img/bear.png" width="150"></td><td><b>BEAR</b>:<br>"A 2.3% win rate. Let me put this in perspective for those of you keeping score at home.<br><br>A <em>coin flip</em> gets you 50%. A drunk gorilla throwing darts at a stock ticker gets you 33%. This bot is performing worse than random chance by a factor of 20. We would have been more profitable if we had literally done nothing. The act of <em>not trading</em> would have outperformed this."</td></tr></table>

<table><tr><td width="170"><img src="img/pirate.png" width="150"></td><td><b>PIRATE</b>:<br>"Arrr! The spread costs alone — $35 — are now <b>213%</b> of the total losses! We've become OANDA's most profitable customer! Not because we're good — because we trade so frequently they named an internal metric after us! They call it 'The SCI Special!'"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"I'm sitting there watching this thing trade faster than a squirrel on pre-workout. It's just methodically bleeding out $135 one single dime at a time. It wasn't even a spectacular crash! It was just a slow, depressing drip. I was literally paying OANDA to hold my money for thirty seconds."</td></tr></table>

---

## 10:00 PM — "The Autopsy Begins"

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"The patient is on the table. Time of financial death: approximately 9 hours after birth. We begin the autopsy. The diagnosis is swift and brutal."</td></tr></table>

### Root Cause #1: The Stop-Loss Was Inside the Spread 🤦

<table><tr><td width="170"><img src="img/ninja.png" width="150"></td><td><b>NINJA</b>:<br><em>"BearishEngulfingStrategy was calculating stop losses at 0.25× ATR. On USDCHF, that translates to approximately 2.5 pips. OANDA's spread on USDCHF? 1.5 pips.<br><br>Our stop loss was 2.5 pips from entry. 1.5 was already consumed by the spread. That leaves 1 pip of breathing room. Normal market noise is 3-5 pips.<br><br>We were placing a stop loss that was guaranteed to get hit by noise before the trade had time to exist."</em></td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Let me translate that into human: We were setting a tripwire at ankle height and then acting surprised when every person who walked by tripped on it.<br><br>The bot had a MIN_SL_PIPS = 10 guard that was <em>supposed</em> to prevent this. It was working perfectly — blocking every single entry. But the strategies kept generating signals every 30 seconds, each one bouncing off the guard like a kid pressing the elevator button harder. 'Maybe if I press it faster it'll come faster.' It won't. That's not how elevators work."</td></tr></table>

### Root Cause #2: The Greedy Exit Was Too Greedy 🤦🤦

<table><tr><td width="170"><img src="img/bot.png" width="150"></td><td><b>THE BOT</b>:<br><em>"My exit logic said: if current_price <= entry_price: close the position at 'breakeven.' Translation: 'If the price is at or below where you bought it, sell immediately.' Seemed reasonable when I read it."</em></td></tr></table>

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"The problem? When you BUY on OANDA, you pay the <b>ask</b> price. When the bot checks current price, it reads the <b>bid</b> price. The bid is always below the ask by the spread — 1.5 pips.<br><br>So: Buy at 181.233 (ask). 0.3 seconds later, bid = 181.232. Is 181.232 ≤ 181.233? Yes. Close at 'breakeven.'<br><br>Actual PnL: <b>-$0.12</b> (spread). Every. Single. Time."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"This wasn't breakeven. This was paying OANDA twelve cents to hold a position for the time it takes to microwave a burrito. We were essentially renting a parking spot, pulling in, and immediately pulling out. And paying for the full hour.<br><br>We did this <b>188 times.</b>"</td></tr></table>

### Root Cause #3: The Strategy Whiplash (Bonus Round) 🤦🤦🤦

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"Meta-SCI picks a different strategy each cycle. Cycle 1: Bearish Engulfing says SHORT. Cycle 2, thirty seconds later: ICC Core says LONG. Cycle 3, another thirty seconds: Bearish Engulfing says SHORT again.<br><br>The bot was flip-flopping faster than a politician in an election year. And paying the spread toll both directions every time."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"To summarize this disaster: the stop loss was microscopic, the exit was literally paying the broker for the privilege of losing, and the bot was changing its mind every thirty seconds like an indecisive toddler.<br><br>188 trades! 3 wins! $17 gone! And I didn't notice for nine hours! I was upstairs living my life while this thing was downstairs eating crayons!"</td></tr></table>

---

## February 17, 2026 — "The Fix"

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"We came back the next morning with coffee, humility, and a deep desire to never speak of this again. But first, we had to fix the actual problems:"</td></tr></table>

| Bug | Before (Broken) | After (Fixed) |
|-----|--------|-------|
| Bearish Engulfing SL | 0.25× ATR (~2.5 pips) | 1.5× ATR (~15 pips) |
| Greedy Exit FLOOR | Closes at any price ≤ entry | Requires 5+ minutes first |
| Churn Guard (Engine) | None | Blocks non-emergency exits < 2 min |
| Churn Guard (Safety) | None | Blocks SafetyGuard exits < 2 min |

### The Moment of Truth

<table><tr><td width="170"><img src="img/bot.png" width="150"></td><td><b>THE BOT</b>:<br><em>"AUDJPY long entered. Greedy Exit respected the age check. Churn Guard blocked premature exits. Stop loss 12.5 pips away, safely outside the spread. I... I'm... I'm still holding it. Is this what patience feels like?"</em></td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Not 30 seconds. Not 36 seconds. <b>Minutes.</b> The position lived. It breathed. It had a childhood and an adolescence and a productive adult life.<br><br>We cried a little. Not gonna lie."</td></tr></table>

---

## Lessons Learned

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"Let the record show the following lessons, paid for with $17.90 and approximately 4 years of emotional aging:"</td></tr></table>

1. **Your stop loss must be wider than your spread.** If your SL is 2.5 pips and your spread is 1.5 pips, you don't have a trading system. You have a recurring donation to your broker.

2. **"Breakeven" after spread is not breakeven.** Closing at your entry price after a buy means you paid the spread twice. That's a guaranteed loss wearing a breakeven costume.

3. **Clear your `__pycache__`.** When debugging Python, always delete `__pycache__`. Otherwise you'll spend 3 hours wondering why your fix didn't work, question your sanity, and consider a career in gardening.

4. **Log everything at INFO level during development.** If a guard exists to save you money, you should probably *know when it fires.* Silent guards are useless guards.

5. **188 trades is a lot of trades for a Sunday night.** If your bot is averaging one trade every 2.8 minutes, something has gone catastrophically wrong. Ships that take on water that fast usually sink.

---

## The Final Score

```
Starting Capital:  $135.22
Ending Capital:    $118.61
Trades Taken:      220
Trades Won:        3  (1.4%)
Total Spread Paid: $35.08
Net PnL:          -$17.90
Cost Per Trade:    $0.16 (spread only)

Lesson Cost:       $17.90
Lesson Value:      Priceless
```

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"In loving memory of $17.90.<br><br>Lost not to bad trades, not to a market crash, not to an act of God — but to a stop loss that was shorter than a tweet, a breakeven floor that didn't understand how spreads work, and a Python cache with commitment issues.<br><br>May it rest in peace. And may OANDA enjoy the fruit basket we unknowingly sent them."</td></tr></table>

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"Eighteen dollars. That's what you spent learning this lesson. Some people lose $18,000 learning the same thing. I'd call that a bargain, baby."</td></tr></table>


> [!NOTE]
> **APRIL 2026 UI & VITALS UPDATE:**  
> Listen up, you degenerates. We just dropped a massive update to the UI and Nurse's Station. The tooltips now trigger when you hover over the *entire goddamn card*, so your fat thumbs can't miss them anymore. The Exit Logic tab is now a clean, idiot-proof single column. We also fixed the Nurse's Station connection tracker—no more lying to you that the bot is dead when it's actively retrying to connect. Read **47_UI_OVERHAUL_AND_VITALS.md** for the full breakdown before you touch the controls and blow your account.
