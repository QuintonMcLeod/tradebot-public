# Backtester Architecture & Rules for AI Assistants

**IMPORTANT**: This document explains how the backtester works and what you MUST NOT change. Read this before touching any backtester code.

---

## Core Principle: Futures-Style Capital Model

The backtester simulates **leveraged futures/margin trading**, NOT spot trading. This is critical to understand:

### Spot Trading (NOT what we do)
- You buy 1 BTC for $100,000 → You have $100,000 less in your account
- You sell 1 BTC for $105,000 → You get $105,000 back
- Net: +$5,000 profit

### Futures/Margin Trading (WHAT WE DO)
- You open a LONG position for 1 BTC at $100,000 → You only pay the **fee** (not $100,000)
- You close the position at $105,000 → You receive the **PnL** (+$5,000) minus exit fee
- Your capital was never tied up in the full notional value

This is why the backtester uses:
```python
# ENTRY: Only deduct fees
capital -= entry_fee  # NOT (cost_basis + entry_fee)

# EXIT: Add net PnL
capital += net_pnl    # NOT (pnl + entry_price * size)
```

---

## The `_calculate_pnl()` Function

This helper calculates PnL correctly for BOTH long and short positions:

```python
def _calculate_pnl(direction: str, entry_price: float, exit_price: float, size: float) -> float:
    if direction == "short":
        return (entry_price - exit_price) * size  # Profit when price DROPS
    else:  # long
        return (exit_price - entry_price) * size  # Profit when price RISES
```

### DO NOT:
- Remove or modify this function
- Use inline PnL calculations that don't account for direction
- Assume all positions are long

### Examples:
| Direction | Entry | Exit | Size | PnL |
|-----------|-------|------|------|-----|
| LONG | $100 | $110 | 1 | +$10 (price went UP = profit) |
| LONG | $100 | $90 | 1 | -$10 (price went DOWN = loss) |
| SHORT | $100 | $90 | 1 | +$10 (price went DOWN = profit) |
| SHORT | $100 | $110 | 1 | -$10 (price went UP = loss) |

---

## Capital Bookkeeping Rules

### On ENTRY:
```python
cost_basis = size * entry_price
entry_fee = cost_basis * self.taker_fee_pct

# CORRECT: Only deduct the fee
capital -= entry_fee

# WRONG: Don't deduct full position value
# capital -= (cost_basis + entry_fee)  # THIS IS SPOT TRADING
```

### On EXIT:
```python
gross_pnl = _calculate_pnl(direction, entry_price, exit_price, size)
total_fees = entry_fee + exit_fee
net_pnl = gross_pnl - total_fees

# CORRECT: Add net PnL
capital += net_pnl

# WRONG: Don't add back principal
# capital += (net_pnl + (entry_price * size))  # THIS ASSUMES SPOT TRADING
```

---

## Stop Loss & Take Profit Direction Handling

### Stop Loss Triggers:
```python
# LONG position: Stop triggers when price drops TO or BELOW stop
if pos.direction == "long" and current_bar.low <= pos.stop_price:
    stop_triggered = True

# SHORT position: Stop triggers when price rises TO or ABOVE stop
elif pos.direction == "short" and current_bar.high >= pos.stop_price:
    stop_triggered = True
```

### Take Profit Triggers:
```python
# LONG position: Target triggers when price rises TO or ABOVE target
if pos.direction == "long" and current_bar.high >= pos.target_price:
    target_triggered = True

# SHORT position: Target triggers when price drops TO or BELOW target
elif pos.direction == "short" and current_bar.low <= pos.target_price:
    target_triggered = True
```

---

## What You CAN Modify

1. **Strategy logic** - How signals are generated, confidence thresholds, etc.
2. **Fee percentages** - `taker_fee_pct`, `maker_fee_pct`, `slippage_pct`
3. **Risk parameters** - Position sizing, max leverage caps
4. **Logging** - Add debug output, but don't remove existing logs
5. **New exit conditions** - Add new exit types (e.g., trailing stop), following the same capital model

---

## What You MUST NOT Modify

1. **The `_calculate_pnl()` function** - It's correct, leave it alone
2. **Capital bookkeeping pattern** - Entry: `-= fee`, Exit: `+= net_pnl`
3. **Direction-aware stop/target triggers** - They correctly handle long vs short
4. **The fundamental assumption** - This is futures trading, not spot trading

---

## Common Mistakes to Avoid

### Mistake 1: Mixing Spot and Futures Accounting
```python
# WRONG - This mixes both models and causes double-counting
capital -= (cost_basis + entry_fee)  # Spot-style entry
capital += (net_pnl + (entry_price * size))  # Trying to restore principal
```

### Mistake 2: Forgetting Direction on PnL
```python
# WRONG - This only works for LONG positions
gross_pnl = (exit_price - entry_price) * size

# CORRECT - Use the helper
gross_pnl = _calculate_pnl(pos.direction, pos.entry_price, exit_price, pos.size)
```

### Mistake 3: Wrong Stop/Target Direction
```python
# WRONG - Same logic for both directions
if current_bar.low <= pos.stop_price:  # Only correct for LONG
    stop_triggered = True

# CORRECT - Check direction
if pos.direction == "long" and current_bar.low <= pos.stop_price:
    stop_triggered = True
elif pos.direction == "short" and current_bar.high >= pos.stop_price:
    stop_triggered = True
```

---

## Testing Your Changes

After ANY modification to the backtester, verify:

1. **Short positions profit when price drops**
   - Enter SHORT at $100, exit at $90 → Should show POSITIVE PnL

2. **Max drawdown is reasonable**
   - Should NOT exceed 100% unless using extreme leverage
   - 99%+ drawdown usually indicates broken capital accounting

3. **Capital doesn't go negative unexpectedly**
   - Negative capital should only happen with extreme losses, not accounting bugs

4. **Fees are being deducted correctly**
   - `net_pnl = gross_pnl - total_fees` should always be less than gross_pnl

---

## Summary

| Action | Correct Pattern |
|--------|-----------------|
| Entry | `capital -= entry_fee` |
| Exit | `capital += net_pnl` |
| PnL Calculation | Use `_calculate_pnl(direction, entry, exit, size)` |
| Long Stop | Triggers when `bar.low <= stop_price` |
| Short Stop | Triggers when `bar.high >= stop_price` |
| Long Target | Triggers when `bar.high >= target_price` |
| Short Target | Triggers when `bar.low <= target_price` |

**When in doubt, don't touch the capital accounting. Ask first.**
