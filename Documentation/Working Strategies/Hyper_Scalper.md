# Hyper Scalper Strategy — Crypto Only (2026-02-28)

## Status: ❌ FOREX | 🔬 CRYPTO-ONLY

## Decision: Removed from Forex

Hyper Scalper is an EMA scalper designed for crypto's volatility profile.
On forex, it produced:

| Metric | Value |
|---|---|
| Trades | 173 |
| Win Rate | 47.4% |
| Avg Win | $18.25 |
| Avg Loss | $20.81 |
| R:R | **0.9:1** (inverted) |
| Net PnL | **-$397** |

**With 47% WR and losses bigger than wins, it's mathematically impossible to profit.**

### Stop Analysis
- 90 stops = -$1,878 (100% of losses)
- 34 targets = +$1,122 (only wins from targets)
- Stop distance wider than target distance = inverted R:R

## Action Taken

Added to `CRYPTO_STRATEGIES` set in Meta-SCI.
Removed from: `bearish_trending`, `bullish_trending`, `ranging` regime groups,
`FOREX_WEIGHTS`, `FOREX_PROVEN_WINNERS`, `ALL_AROUND_HITTERS`.

## Files Modified

- `src/tradebot_sci/strategy/variants/meta_sci.py`
