# 27. Position Alchemy — SL, TP, Trailing Stops & Breakeven Mechanics

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"The entry is science. The exit is art. The stop-loss is religion."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Entry gets all the glory. 'I called the bottom!' 'I bought the dip!' Nobody talks about exits. And exits are where the money is actually made or lost.<br><br>You can have a 90% win rate and still lose money if your losers are 10× bigger than your winners. This article is about the exit side — the mechanics that turn a good entry into actual profit."</td></tr></table>

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

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Without a take-profit, you'll watch price hit your target, think 'let it run,' then watch it reverse all the way back. The TP removes the temptation."</td></tr></table>

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

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"First condition to trigger wins. If the trailing stop fires at +60 pips, the TP at +100 never gets a chance. But you still made 60. That's more than zero."</td></tr></table>

---

## The Exit Philosophy

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Most traders spend 90% of their energy on entries and 10% on exits. It should be the opposite. A mediocre entry with a great exit system outperforms a brilliant entry with sloppy exits. Every time.<br><br>Losses are small (ATR-based SL). Wins are meaningful (R:R-based TP). Trends are ridden (trailing stop). Capital is protected (breakeven trail).<br><br><em>You don't need to be right. You just need to lose less when you're wrong than you make when you're right.</em>"</td></tr></table>
