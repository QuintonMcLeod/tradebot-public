---
title: "59 The Receipt the Bot Never Printed"
category: rtfm
icon: receipt_long
description: 'The bot closed trades and wrote nothing down, so the books said it had never traded at all. Then we finally got a receipt, and every trade on it had been charged a discount. This one is about the two numbers nobody checked, and the reason nobody checked them.'
featured: true
---

# 59. The Receipt the Bot Never Printed

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"I asked the bot how it did today. It said it hadn't traded. I watched it trade. I saw it."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Sit down. Because it <i>did</i> trade. It just never printed the receipt.<br><br>And you want to know the ugly part? When we finally forced it to print one, the receipt was wrong too. Two numbers. Both wrong. Both wrong in the same direction. Both of them flattering the bot. Now ask yourself who that arrangement was for, because the bot doesn't have feelings and it doesn't have rent."</td></tr></table>

---

## First, the plain version

When the bot closes a trade it is supposed to write down what happened. What it bought, at what price, what it sold for, what it lost. That sentence gets written into a log file. A second program reads that log and keeps the books.

The bot was closing trades. **The writing-down part was broken.** So the books said zero. Not "a small number." Zero. The bot kept a flawless record of having done nothing at all.

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"So the shop was open all day and the till tape was blank."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Blank. And here's the thing that should bother you more than the bug. It had been blank long enough that nobody noticed.<br><br>Because zero is a boring number. A boring number doesn't make you open the file. A <i>big</i> number makes you open the file. A <i>scary</i> number makes you open the file. Zero just sits there looking tidy, and you think: nothing happened, great, no news is good news. That is not what zero meant. Zero meant <b>I don't know</b>."</td></tr></table>

---

## Why the receipt never printed

This part is almost funny, and it is entirely real.

The bot tried to write a sentence like: *"the trade lost −0.36%."* The **percent sign** broke it.

To the logging system, `%` is not a character. It is an instruction — "put something here" — and it expects a code letter right after it telling it what to put. The bot wrote a percent sign and then a closing bracket. So the system went looking for the instructions for a bracket, couldn't find them, gave up, and threw the entire sentence in the bin.

Quietly. No crash. No warning. No red text. The <i>only</i> clue was a folded-up error message nobody was reading, and it said the logging had failed, not that a trade had gone missing.

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"It failed in five separate places, and all five were exit records. Every single way a trade could end wrote the same broken sentence. So it was not that some exits went unrecorded. It was that no exit of any kind had ever been recorded."</td></tr></table>

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"So every time I looked at the dashboard and it said everything was fine..."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"...the dashboard was reading a book that had never had a single entry written in it. It wasn't lying to you. It was reading a blank page very confidently."</td></tr></table>

---

## Then we got the receipt, and the receipt was worse

Once the exits were printing, we could finally do the thing nobody had been able to do: compare what the bot <i>charged</i> against what the trades <i>actually cost</i>.

The bot had been charging itself **one flat price for the spread on every trade** — and it had picked that number by taking the <b>middle</b> of the list.

<table><tr><td width="170"><img src="img/skeptic.png" width="150"></td><td><b>KAREN (from Accounting)</b>:<br>"The middle of the list. The <i>median</i>. Not the average — the middle. Those are different numbers whenever the list isn't symmetrical, and this list is not symmetrical. A handful of trades are very expensive and a lot of trades are cheap.<br><br>You cannot charge everybody the middle and call it the average. That's not accounting. That's a discount you gave yourself and forgot to mention."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Say it plain. A hundred people come through your shop. Some owe you two dollars, some owe you twenty. You charge all hundred of them three dollars because three is the middle one. You just let the expensive ones walk out the door paying half, and you told yourself you'd been fair to everybody.<br><br>That's not a rounding error. That's the business."</td></tr></table>

Here is what that discount was worth, on the two sets of prices the whole idea rested on:

| what we told ourselves | what the trades really cost | the gap |
|---|---|---|
| 15 pairs: charged **2.30** pips per trade | actually **3.02** | 0.72 pips a trade, every trade |
| 26 pairs: charged **3.10** pips per trade | actually **4.84** | **1.74 pips a trade, every trade** |

And here is what it did to the result. The left column is what was written down. The right column is what happened when every trade paid its own real bill:

| the claim | as recorded | re-costed honestly |
|---|---|---|
| 15 pairs, 3 years | +1.15 pips (strong) | **+0.51 pips (weak)** |
| 26 pairs, 12 months | +1.51 pips (confirms it) | **−0.22 pips (loses)** |

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"The second row is the one that matters. The twenty-six pair set was the independent check — different pairs, different months, the whole point being that it did not share the first set's weaknesses. It was the reason this strategy was the only one still standing."</td></tr></table>

<table><tr><td width="170"><img src="img/skeptic.png" width="150"></td><td><b>KAREN (from Accounting)</b>:<br>"And I'll note the direction. The discount didn't make the good strategy look slightly better. It turned a losing result into a confirming one. Those two outcomes do not mean the same thing to a person deciding where to put money."</td></tr></table>

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"Could it just be a few crazy trades? One insane spread dragging the average up?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"We checked that first, because it's the excuse I'd have reached for too. Throw away the worst one percent of trades and the average cost is still 4.55 against the 3.10 we'd been charging.<br><br>It's not one crazy trade. It's the shape of the whole list. Twenty-eight percent of those trades cost more than five pips, and those trades are <b>sixty percent of the entire bill</b>. It wasn't a spike. It was the rent."</td></tr></table>

---

## The honest part

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"I want to be precise, because precision is the only thing we have left here. The <i>signal</i> is real. The underlying effect reproduces. What did not survive is the arithmetic we wrapped around it.<br><br>Charged correctly, nothing clears the bar we set for ourselves before we started. Not the fifteen pairs. Certainly not the twenty-six."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"And now let me say the part you're not going to like, because I'd rather you hear it from me than from your account balance.<br><br>Two numbers. Both wrong. Both wrong the same way. Both of them making the bot look like it worked. Nobody caught it for days — not the log, not the dashboard, not the ledger, not me. You know what finally caught it? <b>Reading the price data and comparing.</b> That's it. That's the whole trick.<br><br>So understand what actually happened here. The bot didn't lie to you. It printed a blank page and a flattering number, and everybody walked past both of them, because the flattering number was the one we all wanted to be true. You don't want a trading machine. You want a machine that agrees with you. Those are different products and only one of them is for sale."</td></tr></table>

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"So the scale was broken and it was broken in your favour, and you stood on it every morning for a month and felt good about yourself."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Every morning. And the fix for that is not a better scale. The fix is weighing yourself when you already know you're not going to like the answer."</td></tr></table>

---

## The short version, for Grandma

- The bot closed real trades and **wrote none of them down**. A percent sign in the wrong place broke the sentence, and the logging quietly binned it. The books read zero, and zero looked tidy.
- That is now **fixed**, and fixed in a way that can't quietly come back: there's a test that drives a real trade to its exit and refuses to pass if the receipt is missing.
- Then we found the receipt was wrong anyway. Every trade had been charged the **middle** spread instead of its own. The expensive trades were paying a discount nobody authorised.
- Charged properly, the strategy's headline result falls from **+1.15 to +0.51**, and the independent check — the one that was supposed to confirm it — goes from **+1.51 to −0.22**. It loses.
- It is not one freak trade. The expensive trades are a quarter of the count and **six tenths of the bill**.
- We corrected the documents that carried the old numbers, including the one that was published. We did not quietly change them — we added a correction saying what was wrong and what it is now.
- The bot is still on **paper only**. It has **no proven edge**, and it now has an honest receipt that says so.
- While we were in there we also found the same strategy listed **twice** in one dropdown, one entry of which pointed at a strategy that doesn't exist.

The receipt prints now. The numbers got worse. That is what a receipt is for.
