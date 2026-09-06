---
title: "57 Grandma's Kitchen Clock, Racing Ghosts, and the Scout Who Crowned a King (The Patch Notes, Explained)"
category: rtfm
icon: new_releases
description: 'A grandma-safe tour of the latest fixes: the bot no longer uses the kitchen clock during time travel, the strategy scout stops crowning kings who never fought, and same history now replays the same way twice.'
featured: true
---

# 57. Grandma's Kitchen Clock, Racing Ghosts, and the Scout Who Crowned a King

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"So... I heard we 'fixed some bugs.' Which bugs? And more importantly, do I have to learn anything new, or can I keep pressing the shiny button?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Keep pressing the shiny button. These fixes are the boring kind — the kind where nothing explodes and grandma can finally understand why the bot did what it did. Let's walk through them one at a time."</td></tr></table>

---

## Fix #1: The Kitchen Clock During Time Travel

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"When the bot *practices* on old charts — what we call *backtesting* — it used to peek at the real-world kitchen clock for its safety timers."</td></tr></table>

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"Oh, sweetie, that's like baking a cake 'in the past' but timing it with the oven that's sitting in *today's* kitchen. You'd pull it out four days early and call it done."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Exactly. The safety timers — 'don't trade again for 4 hours,' 'sit out 24 hours' — were being measured against the *real* clock. In a backtest over last month's charts, a 24-hour punishment would never expire, because last month never catches up to today. Grandma's timer, set in the wrong kitchen, would just... never ding.<br><br>Now the bot uses the **clock that's on the chart it's replaying.** Timer set at 2 PM on February 12th expires at 2 PM on February 13th — like it should. Practice now behaves like real life, except nobody loses real money."</td></tr></table>

---

## Fix #2: The Scout Who Crowned a King Who Never Fought

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"The strategy tuner — our little scout that tries hundreds of settings and reports the winner — had a flaw: if a setting never placed *a single trade*, it still reported a score of negative-a-million and could still get picked as 'best.'"</td></tr></table>

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"So it was crowning a king who never left the castle? Baby, you don't get a medal for staying in bed all day."</td></tr></table>

<table><tr><td width="170"><img src="img/pirate.png" width="150"></td><td><b>PIRATE</b>:<br>"Arrr, and the worst part: all them other settings that *did* fight and *did* lose real money looked *better* than the lazy one, because negative-a-million looks scary. So the scout kept pickin' the lazy king."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Now the rules are simple: **no trades = no trophy.** The scout skips any setting that doesn't actually trade, and it shows you the real numbers — trades, win rate, drawdown — next to the profit. If *nothing* trades, it says so out loud instead of pretending a ghost won. Also, the scout used to go looking for its tools on a hard drive that wasn't plugged in; it now looks in its own pocket."</td></tr></table>

---

## Fix #3: Same Movie, Same Ending (Deterministic Replays)

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"Backtests used to be a little bit like live TV — replay the same week twice and you might get a slightly different story, because of how the computer shuffled its deck."</td></tr></table>

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"Wait, so our backtest results were... different every time? How were we supposed to know if a fix helped?!"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Exactly why we fixed it. Now replays are like grandma's VHS: press play twice, you get the same movie twice. Same trades, same profit, same ending. If a change moves the number, we know it was the *change* — not the ghost in the machine."</td></tr></table>

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"And if the movie changes, you know somebody rewound it wrong. Good. I like knowing whether I actually burned the roast or just imagined it."</td></tr></table>

---

## Fix #4: When the Big Boss Changes Her Mind

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"One more: when the big trend 'regime flips' — the market's boss changes her mind — the bot used to keep trading as if nothing happened. Our own experiments showed that habit cost about ten times more than it saved."</td></tr></table>

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"If my favorite soap opera switches to a different show at 2 o'clock, you don't keep watching expecting the old characters to come back. You change the channel, sweetie."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Now the bot gets out of the way by default when the boss flips. You can still turn that off if you fancy the old chaos, but the safe setting is on."</td></tr></table>

---

## Fix #5: The Little Notebook (Optional)

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"And finally, the bot can now keep a little notebook: every time it closes a trade, it writes down why and how much — to a file *you* point it at. Grandma's ledger, but legible."</td></tr></table>

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"Oh, I do love a good notebook. Then when the bot loses money, we can see *which* rule did it, instead of blaming the weather."</td></tr></table>

---

## TL;DR for Grandma

- The bot now uses the **chart's own clock** when practicing, so its "sit out" penalties actually end.
- The strategy scout **won't crown a winner that never traded**, and it finds its own tools.
- Practice replays are now **the same movie every time** — you can trust the numbers.
- When the market's boss changes her mind, the bot **steps aside by default**.
- There's an optional **notebook** that writes down every trade.

No new buttons to learn. The shiny button still works. Grandma is safe.

<sub>Written in the spirit of the other RTFM entries — read the actual diffs for the boring details.</sub>
