
# 27. Position Alchemy (SL, TP, Trailing Stops & Breakeven Mechanics)
> *"The entry is science. The exit is art. The stop-loss is religion."*

Entry gets all the glory. "I called the bottom!" "I bought the dip!" "I went long right before the moon mission!"

Nobody talks about exits. And exits are where the money is actually made or lost. You can have a 90% win rate and still lose money if your losing trades are 10x bigger than your winners.

This article is about the exit side of every trade — the mechanics that turn a good entry into actual profit.

---

## The Holy Trinity: SL, TP, and You

Every trade the bot places has three price levels:

| Level | What It Is | What It Does |
|-------|-----------|-------------|
| **Entry Price** | Where you got in | The starting line. Your cost basis. |
| **Stop-Loss (SL)** | The worst-case exit | Limits your maximum loss to a predetermined amount. |
| **Take-Profit (TP)** | The best-case exit | Automatically takes profit at your target level. |

**The entry** is calculated by the strategy. **The SL and TP** are calculated by the risk management system.

---

## Stop-Loss: The Guardian Angel

A stop-loss is a standing order that says: "If price hits this level, close the position immediately."

### How It's Calculated

The bot uses **ATR (Average True Range)** to set stops dynamically:

```
Stop-Loss = Entry Price - (ATR × Multiplier)
```

**Example (Long Trade):**
*   Entry: 1.0850
*   ATR(14): 0.0035 (35 pips)
*   Multiplier: 1.5
*   Stop-Loss: 1.0850 - (0.0035 × 1.5) = 1.08025

The stop is placed 52.5 pips below entry. If price drops that far, the trade is closed for a controlled loss.

### Why ATR?
Because a static stop (e.g., "always 30 pips") doesn't account for volatility. A 30-pip stop on GBP/JPY (which moves 200 pips/day) will get hit by normal noise. ATR adjusts the stop to the symbol's actual behavior.

### Where It Lives
The stop-loss is placed **at the broker** (server-side). Even if your computer explodes, even if your internet dies, even if aliens invade — the stop-loss will fire. It doesn't need the bot to be running.

---

## Take-Profit: The Discipline Machine

A take-profit is the opposite: "If price hits this level, close the position and take the money."

### How It's Calculated

Take-profit uses the risk/reward ratio:

```
Take-Profit = Entry Price + (SL Distance × R:R Ratio)
```

**Example (Long Trade, 2:1 R:R):**
*   Entry: 1.0850
*   SL Distance: 52.5 pips
*   R:R: 2.0
*   Take-Profit: 1.0850 + (52.5 × 2.0) = 1.0955

You risk 52.5 pips to make 105 pips. If you win 40% of the time with 2:1 R:R, you're profitable.

### Why Fixed TP?
Because greed. Without a take-profit, you'll watch price hit your target, think "let it run," and then watch it reverse all the way back to your entry. The TP removes the temptation.

---

## Trailing Stop: The Best of Both Worlds

A trailing stop follows price as it moves in your favor. It locks in profit progressively, but if price reverses, the stop catches it.

### How It Works

```
Initial Entry: 1.0850 | SL: 1.08025

Price moves to 1.0900:
  → Trailing stop moves UP to 1.0860 (locking in 10 pips of profit)

Price moves to 1.0950:
  → Trailing stop moves UP to 1.0910 (locking in 60 pips of profit)

Price reverses from 1.0950 back to 1.0910:
  → Trailing stop FIRES at 1.0910
  → You captured 60 pips instead of the full 100-pip move
  → But you NEVER gave back your profit
```

### The Configuration

```yaml
trailing_stop:
  enabled: true
  activation_atr: 1.0    # Trail starts after price moves 1x ATR in your favor
  trail_distance_atr: 0.5 # Trail follows at 0.5x ATR behind price
```

The trailing stop doesn't activate immediately — it waits until price has moved in your favor by at least `activation_atr`. Until then, the original stop-loss holds.

---

## Breakeven Trail: The "House Money" Move

The breakeven trail is the most conservative exit strategy. Once price moves a certain distance in your favor, the stop-loss moves to your **entry price** — guaranteeing a zero-loss trade at minimum.

### How It Works

```
Entry: 1.0850 | SL: 1.08025

Price moves to 1.0890 (40 pips in profit):
  → Breakeven activates
  → SL moves from 1.08025 → 1.0850 (your entry price)

Now you're playing with house money:
  → If price continues up → Profit
  → If price reverses → You exit at break-even (no loss)
```

### The Configuration

```yaml
breakeven_trail:
  enabled: true
  activation_pips: 30      # Move SL to breakeven after 30 pips of profit
  offset_pips: 2           # Offset slightly above entry for spread coverage
```

The offset ensures you don't get stopped out exactly at entry due to spread — you exit with a tiny profit instead of exact zero.

---

## Exit Priority: What Fires First?

When multiple exit conditions are active, this is the priority:

```
1. Stop-Loss (Hard floor, always active)
2. Take-Profit (Hard ceiling, always active)
3. Trailing Stop (Dynamic, activates after threshold)
4. Breakeven Trail (Locks in zero-loss floor)
5. Strategy Exit Signal (Structural exit from the strategy engine)
6. Chop Detection (Position going nowhere → exit)
7. Session Close (If intraday_flatten is enabled)
```

The first condition to trigger wins. If the trailing stop fires at +60 pips, the TP at +100 pips never gets a chance. But you still made 60 pips. That's more than zero.

---

## The Exit Philosophy

Most traders spend 90% of their energy on entries and 10% on exits. It should be the opposite.

A mediocre entry with a great exit system will outperform a brilliant entry with sloppy exits every time. The bot's exit architecture — layered stops, trailing mechanisms, and structural exits — is designed to ensure that:

*   **Losses are small** (ATR-based SL)
*   **Wins are meaningful** (R:R-based TP)
*   **Trends are ridden** (trailing stop)
*   **Capital is protected** (breakeven trail)

*"You don't need to be right. You just need to lose less when you're wrong than you make when you're right."*
