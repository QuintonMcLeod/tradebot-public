---
title: 17 UI Overhauls & Nurse's Station Vitals
category: rtfm
icon: medical_services
description: Listen to me, you grown adults who refuse to read. We just spent the last two weeks
  overhauling the UI and the Nurse's Station. A complete guide on reading the vitals,
  the universal exit router, and why your bot says Retrying.
---

# 17. UI Overhauls & Nurse's Station Vitals

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Listen up, Rookie. I'm gonna break this down real slow so even you can understand it. We just spent the last two weeks overhauling the UI and the Nurse's Station because guys like you kept crying about 'Where do I click?' and 'Why is my bot dead?' Here is a complete guide to the new UI, the Exit Router, and the Vitals."</td></tr></table>

---

## THE UNIVERSAL EXIT ROUTER (EXIT LOGIC TAB)

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"Every time I opened the Exit Logic tab, my brain short-circuited. There were toggles everywhere. It looked like the cockpit of a 747 that was currently on fire."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Yeah, we knew you couldn't handle it. So we ripped all that garbage out. It's now a single-column, grandma-safe list. You want to use the Chandelier Exit? Boom, toggle it. If you don't? Boom, toggle it off.<br><br>And the sub-settings—like the ATR multiplier—only show up if the main toggle is ON. We made it idiot-proof. If you can't use it now, you shouldn't be trading."</td></tr></table>

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"I used to try reading what the settings did, but my arthritis flared up trying to hover over that tiny little 'i' icon. It was harder than threading a needle on a rollercoaster."</td></tr></table>

<table><tr><td width="170"><img src="img/chad.png" width="150"></td><td><b>CHAD</b>:<br>"Grandma's right. The hit-boxes on those tooltips were so small I felt like I was playing a sniper video game just to figure out what 'Time Decay' meant."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"We fixed that. Now, you hover over the <b>ENTIRE CARD</b>. The whole toggle! The whole slider! If you hover your fat mouse anywhere over the box, the tooltip pops up. You literally cannot miss it unless you're legally blind. And if you are, why on earth are you looking at charts?"</td></tr></table>

---

## THE NURSE'S STATION (VITALS TAB)

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"I hit the Restart Bot button, and immediately the Vitals tab screamed at me: <code>Cannot connect to the bot! Please start it!</code> I panicked and clicked it five more times."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"That's because the bot was rebooting, and the UI was secretly retrying every 5 seconds without telling you. It was basically lying to your face. We changed that. Now, if the connection drops or you hit restart, the Nurse's Station will say:<br><br><code>Connection Lost — Retrying (Attempt 1... 2...)</code><br><br>It’s gonna pulse, and it's gonna keep counting until the Python brain finally wakes up. Stop panicking. Let it reconnect. It takes a second to load all your garbage settings into memory."</td></tr></table>

<table><tr><td width="170"><img src="img/chad.png" width="150"></td><td><b>CHAD</b>:<br>"What about when the Forex market closes on Friday? Last weekend my Nurse's Station looked like a pinball machine. Everything was flashing CRITICAL RED saying 'No Data for 10+ minutes'."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Yeah, we taught the bot looking at the `Data Feed` vital to check a calendar. It knows it's the actual weekend now. It'll just politely tell you the market is closed instead of having a panic attack. You're welcome."</td></tr></table>

---

## BACKTESTER TREND INVALIDATION

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"I noticed the `trend_invalidation` exit was failing to trigger during backtests, leading to catastrophic drawdowns when the macroscopic 1H trend reversed against my 15-minute entries."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Yeah, your backtester was starving for 1-hour candles. It didn't have enough history to know if the trend was flipping. We taught the backtester workers to fetch native 1H candles straight from Oanda so it has 60+ periods of history. It actually knows what the macroscopic trend is now. It prevents you guys from getting violently stopped out when the market flips.<br><br>Now read the rest of the manuals, don't touch buttons if you don't know what they do, and let the Autopilot make you money before I lose my mind."</td></tr></table>

---

## 📖 Continue Reading

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"Wow, okay I think I get it now. What's next?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Turn the page. We are going to talk about <b>Reading The Scoreboard</b>. Try to keep up."</td></tr></table>
