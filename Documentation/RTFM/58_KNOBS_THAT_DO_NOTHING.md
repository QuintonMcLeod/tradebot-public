---
title: "58 The Dimmer Switch That Was Wired to Nothing"
category: rtfm
icon: tune
description: 'The dashboard had knobs for how much profit the bot is allowed to hand back. They were wired to nothing. This one explains what we found, what we measured, and why a smaller loss is not the same thing as a profit.'
featured: true
---

# 58. The Dimmer Switch That Was Wired to Nothing

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"I asked the bot to only hand back a little bit of a winner's profit. It kept handing back a lot. I turned the knob twice. Nothing happened."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"You weren't imagining it. The knob was real, the wire behind it wasn't. Let's walk through it properly, because the fix is smaller than the story."</td></tr></table>

---

## First, the plain version

When a trade is winning, the bot has a rule that says: *"if too much of my best profit disappears, I leave."* Two numbers control it:

- **How much you're allowed to hand back** — the dashboard said 10%. The bot actually used 20%.
- **When that protection wakes up** — the dashboard said fairly early. The bot actually woke up later than that.

So the bot was letting winners slide further than anyone asked it to, and then closing them.

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"So the thermostat on my wall was painted on. I was turning a picture of a thermostat and wondering why the house stayed cold."</td></tr></table>

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"Precisely, and there's a reason. The dashboard writes those numbers into one drawer of the settings cabinet. The exit rules go looking in a *different* drawer. Nobody had connected the two, so the bot quietly used the factory defaults that were printed inside the machine."</td></tr></table>

---

## The trap we nearly walked into

<table><tr><td width="170"><img src="img/pirate.png" width="150"></td><td><b>PIRATE</b>:<br>"Arr, and here be the fun part. The same drawer mix-up was hiding the 'give up on a stale trade' timer. The dashboard said <b>1000 bars</b> — practically never. The bot was really using <b>48 bars</b>."</td></tr></table>

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"So the fix is just... connect the drawer, and the bot starts using 1000?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"We tested that before touching anything. On a month of old prices, letting stale trades sit around that long turned a loss of about <b>$80</b> into a loss of about <b>$200</b>, and the worst single trade went from <b>-$66</b> to <b>-$173</b>. The bot had been accidentally using the *better* number. If we'd 'fixed' the wiring without looking, we'd have wired up a landmine."</td></tr></table>

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"So before you plug in the lamp, you check what the lamp does. I raised four children on that rule."</td></tr></table>

---

## What we actually measured

Practice runs on two separate stretches of old prices, same pairs, same rules — only those two profit-handback numbers changed:

| Setting | Stretch 1 | Stretch 2 | Total |
|---|---|---|---|
| What the bot had been using (20%, late wake-up) | −$80.06 | −$100.29 | **−$180.35** |
| What the dashboard asked for (10%, early wake-up) | −$91.27 | — | worse |
| What we settled on (5%, wake up at half a risk unit) | −$59.54 | −$79.77 | **−$139.31** |

Both stretches improved, by about the same amount each time, which is the part that made us believe it. The bot now **loses about 23% less** on this strategy and the win/loss quality ratio went from 0.67 to 0.76.

---

## The honest part

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"A word of caution. Losing less is not the same as winning. This strategy still loses money on every stretch of history we have. What we fixed is that the knobs now do what they say."</td></tr></table>

<table><tr><td width="170"><img src="img/pirate.png" width="150"></td><td><b>PIRATE</b>:<br>"And tell 'em about the brake ye threw overboard, else they'll ask why it's not there."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Right. We also built a brake that locks in half of the best profit a trade ever had. Sounded great. It measured <b>worse</b> at every setting that actually engaged — it kept cutting the rare big winner short to protect pennies on the small ones. So we deleted it instead of shipping it and calling it clever."</td></tr></table>

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"Good. I don't want a smoke alarm that goes off every time I make toast. Throw it in the bin and tell me you threw it in the bin."</td></tr></table>

---

## Why the losses still look like this

Worth knowing, because it points at the real problem:

- Four of the worst losses **never went up by even one cent** before losing. They didn't give anything back — they never had anything.
- The winners regularly go *deeply* underwater first (one winner was down $47 before finishing up $23).
- One big winner peaked at **+$215** and finished at **+$109**. That's the give-back you were seeing — and it's a single trade, not a pattern.

So: **exits are not the disease.** The exits were being told the wrong numbers, and now they aren't. The trades that never go anywhere are an *entry* problem, and that's the next job.

---

## The short version, for Grandma

- The dashboard knobs for "how much profit may I hand back" were **wired to nothing** — the bot used its factory numbers instead. **Fixed**: the knobs now work.
- The bot had *also* been ignoring a "give up on a stale trade" number, and the number on the dashboard would have made things **much worse**. We set it to the value that measured best, and said why in the config.
- Practice runs are now repeatable, so we compared properly: the bot **loses about 23% less** on this strategy.
- It still **doesn't make money yet**. We're not going to pretend otherwise.
- We built one clever-sounding safety brake, measured it, found it made things worse, and **threw it away**.

The shiny button still works. Turn the knobs — this time they're attached.
