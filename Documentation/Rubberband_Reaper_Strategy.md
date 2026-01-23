# The Rubberband Reaper v2

*Anti-Martingale Tiered Risk Mean Reversion*

---

## Summary Metrics

| Metric | Fixed 10% Risk | Tiered Risk (20/10/1) |
|:--|--:|--:|
| **Starting Capital** | $100 | $100 |
| **Peak Capital** | $5,692 | **$8,088** |
| **Final Capital** | $965 | **$7,136** |
| **Preserved from Peak** | 17% | **88%** |
| **Total PnL** | +865% | **+7,036%** |
| **Win Rate** | 39% | 39% |
| **Avg R:R** | 3.7:1 | 3.7:1 |

---

## Tiered Risk Model

| Capital Level | Risk % | Rationale |
|:--|--:|:--|
| Below $1,000 | **20%** | Aggressive growth |
| $1,000 - $5,000 | **10%** | Growth phase |
| Above $5,000 | **1%** | Wealth protection |

---

## Timeline

| Metric | Value |
|:--|:--|
| Start Date | Jan 4, 2026 |
| End Date | Jan 21, 2026 |
| Duration | **17 days** |
| Total Trades | 41 |
| Wins | 16 |
| Losses | 25 |

---

## Complete Trade Log

| # | Symbol | Dir | Cap Before | Cap After | PnL | PnL% | Peak | Risk% | Exit |
|--:|:--|:--|--:|--:|--:|--:|--:|--:|:--|
| 1 | USDJPY | SHORT | $100.00 | $80.00 | -$20.00 | -20.0% | $100.00 | 20% | SL |
| 2 | EURUSD | LONG | $80.00 | $142.06 | +$62.06 | +77.6% | $142.06 | 20% | TP |
| 3 | EURUSD | SHORT | $142.06 | $113.65 | -$28.41 | -20.0% | $142.06 | 20% | SL |
| 4 | GBPUSD | SHORT | $142.06 | $85.24 | -$28.41 | -20.0% | $142.06 | 20% | SL |
| 5 | USDCAD | LONG | $85.24 | $151.63 | +$66.39 | +77.9% | $151.63 | 20% | TP |
| 6 | USDCAD | SHORT | $151.63 | $121.30 | -$30.33 | -20.0% | $151.63 | 20% | SL |
| 7 | NZDUSD | LONG | $121.30 | $97.04 | -$24.26 | -20.0% | $151.63 | 20% | SL |
| 8 | EURUSD | SHORT | $97.04 | $177.90 | +$80.86 | +83.3% | $177.90 | 20% | TP |
| 9 | GBPUSD | LONG | $97.04 | $158.49 | -$19.41 | -20.0% | $177.90 | 20% | SL |
| 10 | GBPUSD | SHORT | $158.49 | $242.65 | +$84.16 | +53.1% | $242.65 | 20% | TP |
| 11 | NZDUSD | SHORT | $158.49 | $350.78 | +$108.13 | +68.2% | $350.78 | 20% | TP |
| 12 | USDCHF | LONG | $350.78 | $280.63 | -$70.16 | -20.0% | $350.78 | 20% | SL |
| 13 | AUDUSD | SHORT | $158.49 | $248.93 | -$31.70 | -20.0% | $350.78 | 20% | SL |
| 14 | AUDUSD | SHORT | $248.93 | $420.46 | +$171.53 | +68.9% | $420.46 | 20% | TP |
| 15 | AUDUSD | SHORT | $420.46 | $798.84 | +$378.39 | +90.0% | $798.84 | 20% | TP |
| 16 | USDCHF | SHORT | $798.84 | $1,424.30 | +$625.46 | +78.3% | $1,424.30 | 20% | TP |
| 17 | USDCHF | LONG | $1,424.30 | $1,281.87 | -$142.43 | -10.0% | $1,424.30 | **10%** | SL |
| 18 | USDJPY | LONG | $1,281.87 | $1,937.48 | +$655.61 | +51.1% | $1,937.48 | 10% | TP |
| 19 | GBPUSD | LONG | $1,937.48 | $2,591.75 | +$654.27 | +33.8% | $2,591.75 | 10% | TP |
| 20 | EURUSD | LONG | $1,937.48 | $3,117.14 | +$525.39 | +27.1% | $3,117.14 | 10% | TP |
| 21 | USDJPY | LONG | $3,117.14 | $2,805.43 | -$311.71 | -10.0% | $3,117.14 | 10% | SL |
| 22 | USDCHF | SHORT | $1,937.48 | $3,348.58 | +$543.15 | +28.0% | $3,348.58 | 10% | TP |
| 23 | USDCHF | LONG | $3,348.58 | $3,013.72 | -$334.86 | -10.0% | $3,348.58 | 10% | SL |
| 24 | EURUSD | LONG | $3,348.58 | $4,993.40 | +$1,979.68 | +59.1% | $4,993.40 | 10% | TP |
| 25 | GBPUSD | LONG | $3,348.58 | $6,502.57 | +$1,509.17 | +45.1% | $6,502.57 | 10% | TP |
| 26 | AUDUSD | LONG | $3,348.58 | $8,087.98 | +$1,585.41 | +47.3% | $8,087.98 | 10% | **TP** |
| 27 | AUDUSD | SHORT | $8,087.98 | $8,007.10 | -$80.88 | -1.0% | $8,087.98 | **1%** | SL |
| 28 | EURUSD | SHORT | $8,007.10 | $7,927.03 | -$80.07 | -1.0% | $8,087.98 | 1% | SL |
| 29 | USDCHF | LONG | $8,007.10 | $7,846.96 | -$80.07 | -1.0% | $8,087.98 | 1% | SL |
| 30 | GBPUSD | SHORT | $8,007.10 | $7,766.89 | -$80.07 | -1.0% | $8,087.98 | 1% | SL |
| 31 | AUDUSD | SHORT | $7,766.89 | $7,689.22 | -$77.67 | -1.0% | $8,087.98 | 1% | SL |
| 32 | USDJPY | SHORT | $7,689.22 | $7,612.32 | -$76.89 | -1.0% | $8,087.98 | 1% | SL |
| 33 | GBPUSD | SHORT | $7,612.32 | $7,536.20 | -$76.12 | -1.0% | $8,087.98 | 1% | SL |
| 34 | EURUSD | SHORT | $7,612.32 | $7,460.08 | -$76.12 | -1.0% | $8,087.98 | 1% | SL |
| 35 | USDCHF | LONG | $7,536.20 | $7,384.72 | -$75.36 | -1.0% | $8,087.98 | 1% | SL |
| 36 | NZDUSD | LONG | $7,384.72 | $7,310.87 | -$73.85 | -1.0% | $8,087.98 | 1% | SL |
| 37 | AUDUSD | SHORT | $7,310.87 | $7,237.76 | -$73.11 | -1.0% | $8,087.98 | 1% | SL |
| 38 | USDCHF | SHORT | $7,310.87 | $7,164.65 | -$73.11 | -1.0% | $8,087.98 | 1% | SL |
| 39 | AUDUSD | SHORT | $7,164.65 | $7,093.00 | -$71.65 | -1.0% | $8,087.98 | 1% | SL |
| 40 | AUDUSD | SHORT | $7,093.00 | $7,208.48 | +$115.48 | +1.6% | $8,087.98 | 1% | TP |
| 41 | USDJPY | SHORT | $7,208.48 | $7,136.40 | -$72.08 | -1.0% | $8,087.98 | 1% | SL |

---

## Key Insight

**Trades 27-41 were 14 losses + 1 win** — but at 1% risk, total loss was only **$951**.

With fixed 10% risk, that same streak cost **$4,727** (from $5,692 to $965).

**Result: 88% preservation vs 17%.**

---

## Production Config

```python
# src/tradebot_sci/config/models.py
class UserConfig:
    STRATEGY_VARIANT = 'rubberband_reaper'
    BASE_RISK_PCT = 0.20  # Starting risk

# src/tradebot_sci/strategy/variants/rubberband_reaper.py
def get_tiered_risk(capital: float) -> float:
    if capital < 1000:   return 0.20  # Aggressive
    elif capital < 5000: return 0.10  # Growth
    else:                return 0.01  # Protection
```
