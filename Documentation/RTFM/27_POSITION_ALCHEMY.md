---
title: 'Position Alchemy: The Art and Science of SL, TP, and Trailing Stops'
category: rtfm
icon: auto_graph
description: '"The entry is science. The exit is art. The stop-loss is religion."
  Deep dive into every exit mechanism: ATR-based stop-losses, risk/reward take-profits,
  trailing stops with activation thresholds, breakeven trails, and the exit priority
  stack. With actual formulas, examples, and the philosophy of why exits matter more
  than entries.'
---

# 27. Position Alchemy — SL, TP, Trailing Stops & Breakeven Mechanics

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"The entry is science. The exit is art. The stop-loss is religion."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Everyone loves the entry. 'I called the bottom!' 'I bought the dip, bro!' Nobody talks about exits. But exits are where the money actually changes hands. You people love entering trades and then you just stare at the screen hoping God takes the wheel.<br><br>You can have a 90% win rate and still go broke if your losers are ten times bigger than your winners! This article is about the exit side — the math that physically forces you to keep the money you made."</td></tr></table>

---

## The Holy Trinity: SL, TP, and You

| Level | What It Is | What It Does |
|-------|-----------|-------------|
| **Entry Price** | Where you got in | The starting line. Your cost basis. |
| **Stop-Loss (SL)** | The worst-case exit | Limits max loss to a predetermined amount. |
| **Take-Profit (TP)** | The best-case exit | Automatically takes profit at target. |

---

## Stop-Loss: The Guardian Angel

```
Stop-Loss = Entry Price - (ATR × Multiplier)
```

**Example (Long Trade):**
- Entry: 1.0850
- ATR(14): 0.0035 (35 pips)
- Multiplier: 1.5
- Stop-Loss: 1.0850 - (0.0035 × 1.5) = **1.08025**

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"A 30-pip static stop on GBP/JPY (which moves 200 pips/day) gets hit by normal noise. ATR adjusts to the symbol's actual behavior. And the stop is server-side — even if your computer explodes, the stop fires."</td></tr></table>

---

## Take-Profit: The Discipline Machine

```
Take-Profit = Entry Price + (SL Distance × R:R Ratio)
```

**Example (Long Trade, 2:1 R:R):**
- SL Distance: 52.5 pips
- Take-Profit: 1.0850 + (52.5 × 2.0) = **1.0955**

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Without a take-profit, you're going to watch the price hit your target, get greedy, think 'let it run, I'm a genius,' and then watch it reverse all the way back to zero and cry. The Take-Profit cures your greed by taking the money while you're still hallucinating about buying a boat."</td></tr></table>

---

## Trailing Stop: The Best of Both Worlds

A trailing stop follows price as it moves in your favor, locking in profit progressively:

```
Initial Entry: 1.0850 | SL: 1.08025

Price → 1.0900:
  → Trailing stop moves to 1.0860 (locking in 10 pips)

Price → 1.0950:
  → Trailing stop moves to 1.0910 (locking in 60 pips)

Price reverses to 1.0910:
  → Trailing stop FIRES at 1.0910
  → Captured 60 pips instead of full 100
  → But NEVER gave back profit
```

### Configuration
```yaml
trailing_stop:
  enabled: true
  activation_atr: 1.0    # Trail starts after 1x ATR in your favor
  trail_distance_atr: 0.5 # Follows at 0.5x ATR behind price
```

> 📺 Settings → **Strategy Workshop** → **Exit Logic** → **"Greedy Exit"** toggle

---

## Breakeven Trail: The "House Money" Move

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"Once price moves a certain distance in your favor, the stop moves to your ENTRY price. Zero-loss guaranteed from that point."</td></tr></table>

```
Entry: 1.0850 | SL: 1.08025

Price → 1.0890 (40 pips profit):
  → Breakeven activates
  → SL moves from 1.08025 → 1.0850

Now playing with house money:
  → Price continues up → Profit
  → Price reverses → Exit at break-even (no loss)
```

```yaml
breakeven_trail:
  enabled: true
  activation_pips: 30
  offset_pips: 2           # Slight offset for spread coverage
```

> 📺 Settings → **Safety & Shields** → **"Lock-In"** field

---

## Exit Priority: What Fires First?

```
1. Stop-Loss (Hard floor, always active)
2. Take-Profit (Hard ceiling, always active)
3. Trailing Stop (Dynamic, activates after threshold)
4. Breakeven Trail (Locks in zero-loss floor)
5. Strategy Exit Signal (Structural exit from engine)
6. Chop Detection (Position going nowhere → exit)
7. Session Close (If intraday_flatten is enabled)
```

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Whichever one hits first, wins! If the trailing stop fires at +60 pips, the TP at +100 never gets a chance. But you still made 60! Be happy! That's more than the zero you would have made trying to manage it yourself!"</td></tr></table>

---

## The Exit Philosophy

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Most of you spend 90% of your energy trying to find the perfect entry and 10% on your exits. It's completely backwards. A mediocre entry with a ruthless exit system completely destroys a brilliant entry with sloppy exits. Every single time.<br><br>Losses are small. Wins are meaningful. Capital is protected. <br><br><em>You don't need to be right all the time. You just need to stop bleeding like a stuck pig when you're wrong!</em>"</td></tr></table>


> [!NOTE]
> **APRIL 2026 UI & VITALS UPDATE:**  
> Listen up, you degenerates. We just dropped a massive update to the UI and Nurse's Station. The tooltips now trigger when you hover over the *entire goddamn card*, so your fat thumbs can't miss them anymore. The Exit Logic tab is now a clean, idiot-proof single column. We also fixed the Nurse's Station connection tracker—no more lying to you that the bot is dead when it's actively retrying to connect. Read **47_UI_OVERHAUL_AND_VITALS.md** for the full breakdown before you touch the controls and blow your account.
