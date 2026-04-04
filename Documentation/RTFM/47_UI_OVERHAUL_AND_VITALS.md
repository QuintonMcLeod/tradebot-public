---
title: UI Overhauls & Nurse's Station Vitals
category: rtfm
icon: medical_services
description: Listen to me, you dumb motherfuckers. We just spent the last two weeks
  overhauling the UI and the Nurse's Station. A complete guide on reading the vitals,
  the universal exit router, and why your bot says Retrying.
---

# 47. UI OVERHAULS & NURSE'S STATION VITALS

Listen to me, you dumb motherfuckers. I'm gonna break this down real slow so even the slowest guy in the room can understand it. We just spent the last two weeks overhauling the UI and the Nurse's Station because you idiots kept crying about "where do I click?" and "why is my bot dead?" 

## THE UNIVERSAL EXIT ROUTER (EXIT LOGIC TAB)

First of all, the **Exit Logic** tab used to look like a goddamn jigsaw puzzle. We ripped all that shit out. It's now a single-column, grandma-safe list. 
If you want to use the Chandelier Exit? Boom, toggle it. If you don't? Boom, toggle it off. 
And the sub-settings (like the ATR multiplier) only show up if the main toggle is ON. We made it idiot-proof. If you can't use it now, you shouldn't be trading.

Oh, and those tooltips? You remember how you had to hover your fat fucking mouse exactly over the tiny little `ⓘ` icon just to read what a setting does? We fixed that too. Now, you hover over the **ENTIRE FUCKING CARD**. The whole toggle! The whole slider! If you hover over the box, the tooltip pops up. You literally cannot miss it unless you're legally blind.

## THE NURSE'S STATION (VITALS TAB)

Let’s talk about the **Nurse's Station**. This is your bot's heartbeat. We added tooltips to every single vital card (the little squares). Hover over the "Heartbeat," "Data Feed," or "Broker Link" card, and the bot will tell you exactly what the fuck it's doing. 

We also fixed the biggest lie the bot was telling you. You know when you restarted the bot and the UI immediately screamed, `Cannot connect to the bot! Please start it!`? Yeah, that was bullshit. The bot was just rebooting, and the UI was secretly retrying every 5 seconds without telling you. We changed that. 
Now, if the connection drops or you hit restart, the Nurse's Station will say:
`Connection Lost — Retrying (Attempt 1... 2...)`
It’s gonna pulse, and it's gonna keep counting until the Python brain wakes the fuck up. Stop panicking. Let it reconnect.

We also fixed the `Data Feed` vital so it doesn't scream `CRITICAL` on a Sunday when the Forex markets are literally closed. It knows it's the goddamn weekend now.

## BACKTESTER TREND INVALIDATION (UNDER THE HOOD)

We also fixed a massive bug in the backtester where the `trend_invalidation` exit was starving for 1H candles and shitting the bed. We taught the backtester workers to fetch native 1H candles straight from Oanda so it has 60+ candles of history to actually know what the trend is. It prevents you from getting violently stopped out when the market flips. 

Read the rest of the manuals, don't touch buttons if you don't know what they do, and let the 20-Year AI Autopilot make you money.
