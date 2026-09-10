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

## Part 2: We went looking for the entry fix and came back empty-handed

The exits now tell the truth, and the bot still loses. So we went after the entries. Three ideas, three dead ends — recorded here so nobody spends a weekend rediscovering them.

### Dead end 1: "It's buying too late"

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"The scoring rule *pays* the bot extra points for entering after price has already run far past the level — 35 points for being more than one and a half ATR beyond it. That looked like the culprit: rewarding the chase."</td></tr></table>

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"So you fixed the scoring?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"We measured it first. Late entries were the *best* group — +$47.80 against −$29.84 for the fresh ones. The single biggest winner of the whole month was the **most** extended entry in the sample, 2.11 ATR past the level. Killing that rule would have destroyed the only trade that paid."</td></tr></table>

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"So the thing that looked like the mistake was the thing doing the work. That's why you check before you redecorate."</td></tr></table>

### Dead end 2: "The risk unit is too big"

The stops turn out to be **4–7 ATR wide (14–26 pips)**, because the stop sits at the opposite swing extreme *and then* adds an ATR buffer on top. The target was 2R — about $114 of follow-through — while the best ordinary winner in the sample only ever reached $44.79. That looked like the disease.

We tested every way of shrinking it:

| configuration | both windows combined | result |
|---|---|---|
| wide stop, 2R target (as shipped) | **−$139.31** | best |
| same stop, 1R target | −$196.31 | worse |
| same stop, 0.6R target | −$230.79 | worse |
| half-width stop, 1R target | −$244.51 | worse |
| quarter-width stop + cap, 1R | −$449.91 | much worse |
| tiny stop + cap, 1R | −$355.49 | much worse |

<table><tr><td width="170"><img src="img/pirate.png" width="150"></td><td><b>PIRATE</b>:<br>"Every single attempt to make the risk unit smaller made the bleedin' thing worse. Tighter stops mean bigger positions, and bigger positions pay more spread — the friction eats ye alive."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"This strategy is a lottery ticket: many small losses, paid for by a rare big winner. Capping the winner to protect the small ones is exactly the wrong move. We removed the stop-cap code we'd written for it, because it has no evidence behind it."</td></tr></table>

### The real find: the strategies were never actually listening

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"While testing, we discovered something worse than any of the above. The settings for a strategy — its trend filter, its volume requirement, its stop size — never actually reached the strategy. Every one of them silently used the number written inside its own source file."</td></tr></table>

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"So every time we tried a new setting and the result didn't change..."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"...it was because the setting was never delivered. **Fixed**, and provably: we can now hand a strategy the exact numbers a frozen variant was born with, and it reproduces that variant's results to the penny — 12 trades, −$59.54, both ways. Any knob in the app that claims to tune a strategy now genuinely does."</td></tr></table>

### So where is the actual fix?

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"Honestly: not found yet. And now we know why. Our entire recorded history is **35 calendar days — roughly 25 trading days, 12 to 19 trades per test.** That is not enough data to tell a real edge from a lucky coin toss. Tuning further on it is guaranteed overfitting, and we'd be lying to you about the result."</td></tr></table>

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"You can't judge a recipe from one bite, and you surely can't judge it after licking the spoon yourself. Get more dinners."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Right. The next move is data, not cleverness: pull months of history, pick the rules on one period, then judge them on a period we never looked at. Until then, the bot keeps running with the settings that measured best — which are the ones it already had."</td></tr></table>

---

## The short version, for Grandma

- The dashboard knobs for "how much profit may I hand back" were **wired to nothing** — the bot used its factory numbers instead. **Fixed**: the knobs now work.
- The bot had *also* been ignoring a "give up on a stale trade" number, and the number on the dashboard would have made things **much worse**. We set it to the value that measured best, and said why in the config.
- Practice runs are now repeatable, so we compared properly: the bot **loses about 23% less** on this strategy.
- It still **doesn't make money yet**. We're not going to pretend otherwise.
- We built one clever-sounding safety brake, measured it, found it made things worse, and **threw it away**.
- Then we went hunting for the entry fix and found **three more dead ends**, all written down above: buying late is *good* here, tighter stops are *worse*, and capping winners is *worse*.
- The real discovery: **the strategies were never receiving their settings at all.** Fixed, and proven by reproducing a known result exactly.
- We still have **no entry fix**, because 25 trading days of history cannot prove one. The next step is **more history**, not more knobs.

The shiny button still works. Turn the knobs — this time they're attached.
