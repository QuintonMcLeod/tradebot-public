---
title: "57 Grandma's Kitchen Timer, the Lazy King, and the DVD That Never Changes"
category: rtfm
icon: new_releases
description: 'The bot got some under-the-hood fixes. This one explains them the way grandma would: with a kitchen timer, a king who never left his castle, and a DVD that plays the same movie every time.'
featured: true
---

# 57. Grandma's Kitchen Timer, the Lazy King, and the DVD That Never Changes

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"So... I heard we fixed some stuff. Do I need to learn new buttons, or can I keep pressing the shiny one?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Same shiny button. These are the boring, good kind of fixes — the kind grandma can understand. Let's walk through them like normal people."</td></tr></table>

---

## Fix #1: The Kitchen Timer Problem

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"Sometimes we let the bot *practice* on old prices — like rehearsing with last week's newspaper before it ever touches real money. We call that a practice run."</td></tr></table>

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"Oh, sweetie, so it's like baking a cake in *the past* but setting the timer on the oven that's sitting in *today's* kitchen. You'd pull it out four days early and call it done."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Exactly that. The bot has little rules like 'if I lose, sit out for a while.' But during practice runs, it was checking the *real-world* clock instead of the clock on the old chart it was practicing on. So a one-day timeout on last month's chart never ended — because last month never catches up to today. Grandma's timer, set in the wrong kitchen, would just... never ding.<br><br>Now it uses the clock that's printed on the chart itself. Timeout starts at 2 PM on the practice day, ends at 2 PM the next practice day — like it should. Practice behaves like real life, minus the part where you lose real money."</td></tr></table>

---

## Fix #2: The Lazy King Who Never Left His Castle

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"We have a little helper that tries lots of different settings and tells us which one did best. It had a bad habit: a setting that never placed even one trade would still get a gigantic 'minus a million' score — and sometimes that was still chosen as the winner."</td></tr></table>

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"So it crowned a king who never fought a single battle? Baby, you don't get a medal for staying in bed all day."</td></tr></table>

<table><tr><td width="170"><img src="img/pirate.png" width="150"></td><td><b>PIRATE</b>:<br>"Arrr, and here's the nasty part — the settings that *did* fight and *did* lose real money looked *better* than the lazy one, because losing real money is a smaller number than minus-a-million. So the helper kept pickin' the lazy king."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"New rule, plain as day: **no trades = no trophy.** If a setting never actually trades, it gets skipped and it can't win. And if *nothing* trades at all, the helper says so out loud instead of pretending a ghost won. Bonus fix: the helper used to go looking for its toolbox on a shelf that wasn't plugged in; it now grabs the toolbox from its own pocket."</td></tr></table>

---

## Fix #3: The DVD That Plays the Same Movie

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"Practice runs used to be a little bit like live TV. Run the same old week twice and you might get a slightly different story, because the computer shuffled its cards differently each time."</td></tr></table>

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"Wait — so our practice results were different every time? Then how were we supposed to know if a fix actually helped?!"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"That's exactly why we fixed it. Practice runs are now grandma's DVD: press play twice, you get the same movie twice. Same trades, same ending, same number at the bottom. So if a change moves that number, we know the *change* did it — not a ghost in the machine."</td></tr></table>

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"And if the movie changes, somebody rewound it wrong. Good. I like knowing whether I actually burned the roast or just dreamed I did."</td></tr></table>

---

## Fix #4: When the Boss Changes the Channel

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"One more: when the market's big boss suddenly changes her mind about which way things are going, the bot used to keep trading as if nothing happened. Our own practice results showed that habit cost about ten times more than it saved."</td></tr></table>

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"If my favorite soap opera gets replaced by a different show at 2 o'clock, you don't keep watching hoping the old characters come back. You change the channel, sweetie."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Now the bot steps aside by default when the boss flips the channel. You can still turn that off if you enjoy chaos, but the safe setting is on."</td></tr></table>

---

## Fix #5: The Little Notebook (Optional)

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"And finally, the bot can now keep a little notebook. Every time it closes a trade, it writes down *why* and *how much*, into a file you point it at. Grandma's ledger, but legible."</td></tr></table>

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"Oh, I do love a good notebook. Then when the bot loses money, we can see *which rule* did it — instead of blaming the weather."</td></tr></table>

---

## The Short Version, for Grandma

- When the bot practices, its little timeouts now tick by the **chart's own clock**, so they actually end.
- The helper **won't crown a winner that never traded**, and it finds its own tools.
- Practice runs now play back **the same movie every time** — you can trust the number.
- When the market's boss changes her mind, the bot **steps aside by default**.
- There's an optional **notebook** that writes down every trade.

No new buttons. The shiny button still works. Grandma is safe.
