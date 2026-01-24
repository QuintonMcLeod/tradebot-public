# 09_TRADING_STRATEGIES: The Multi-Strategy Arsenal

> **"One strategy doesn't fit all markets. Choose your weapon wisely."**

Tradebot SCI now supports **9 distinct trading strategies**, each optimized for different market conditions. You can assign different strategies to different asset classes — using mean reversion for ranging crypto while running trend-following on forex.

---

## Strategy Overview

| Strategy | Style | Risk | Win Rate | Best For |
|----------|-------|------|----------|----------|
| **Rubberband Reaper** | Mean Reversion | Adaptive | ~39% | Ranging markets, volatile assets |
| **RoboCop** | Aggressive Scalping | High | ~25% | Trending markets, high volatility |
| **Robot Evolution** | Range Trading | Low-Medium | ~45% | Sideways markets, consolidation |
| **Quantum** | Trend Following | Medium | ~35% | Strong trending forex pairs |
| **Mean Reversion** | Mean Reversion | Medium | ~42% | Ranging crypto and forex |
| **HyperScalper** | Fast Scalping | High | ~30% | Liquid forex, fast markets |
| **London Breakout** | Breakout | Medium | ~38% | GBP pairs, European session |
| **Volatility Breakout** | Breakout | Medium-High | ~32% | Compressed markets |
| **Singularity Aggregator** | Multi-Strategy | Variable | ~35% | Maximum capital efficiency |

---

## 1. Rubberband Reaper (Default)

> **"Price is a rubber band — it always snaps back."**

**Verified Performance:** +7,036% with tiered anti-martingale risk management.

### How It Works
1. **Detection:** Watches for price to break outside Bollinger Bands (2.5 std)
2. **Confirmation:** RSI confirms oversold (<25) or overbought (>75)
3. **Entry:** Enters expecting reversion to the mean
4. **Target:** Opposite Bollinger Band for 3:1+ reward-to-risk

### Anti-Martingale Risk (The Secret Sauce)
Unlike traditional systems that increase size after losses, Rubberband Reaper does the opposite:
- **After a WIN:** Increase position size (the trend is working)
- **After a LOSS:** Decrease position size (something's wrong)

### Tiered Risk by Account Size
| Account Size | Risk Per Trade |
|--------------|----------------|
| Below $1,000 | 20% (aggressive growth) |
| $1,000-$5,000 | 10% (growth phase) |
| Above $5,000 | 1-5% (capital preservation) |

**Best For:** Crypto, forex pairs that range (EUR/USD, AUD/USD), volatile altcoins.

---

## 2. RoboCop

> **"Maximum aggression. Minimum hesitation."**

### How It Works
1. **Ultra-Fast Confirmation:** Only 1 bar needed to confirm signal
2. **Any Valid Micro-Signal:** Reacts to ICC signals without waiting for full corrections
3. **Wide Targets:** 3.0 ATR target for maximum profit potential
4. **Fast Exit:** "Chop exit" triggers if price stalls in a range

### Key Parameters
```yaml
icc_confirmation_bars: 1
target_atr_multiplier: 3.0
chop_exit_enabled: true
```

**Best For:** Trending markets with clear direction. High volatility crypto. NOT for choppy/ranging markets.

**Warning:** High risk. Expect more losses but bigger wins. Requires strong trends to be profitable.

---

## 3. Robot Evolution (NTZ Scalper)

> **"Dance at the edges of the No-Trade-Zone."**

### How It Works
1. **Identify the NTZ:** Maps the range between recent swing high and swing low
2. **Wait for Sweep:** Price must sweep liquidity at the edge (break and reverse)
3. **Enter on Reversal:** Trade back toward the middle of the range
4. **Conservative Targets:** 2.0R with tight 1.5 ATR stops

### The "No-Trade-Zone" Concept
The NTZ is the middle of a range where:
- Neither bulls nor bears have control
- Entries have poor risk/reward
- The bot WAITS until price reaches the edges

**Best For:** Consolidation phases, ranging markets, sideways crypto.

---

## 4. Quantum (Trend Following)

> **"The trend is your friend — until it ends."**

### How It Works
1. **Wait for Pullback:** Price must retrace to the 20-period SMA
2. **Confirm Trend:** HTF and LTF must both show the same direction
3. **Enter on Bounce:** Enter when price bounces off the SMA in trend direction
4. **Exit on Flip:** Automatically exit when HTF trend reverses

### Key Parameters
```yaml
sma_period: 20
htf_ltf_alignment_required: true
exit_on_htf_flip: true
target_multiplier: 1.6
stop_atr_multiplier: 2.5
```

**Best For:** Strong trending forex (GBP/JPY, EUR/GBP), trending ETFs, clear directional moves.

---

## 5. Mean Reversion (Classic)

> **"What goes up must come down."**

### How It Works
1. **Bollinger Band Break:** Price breaks outside 15-period, 2.5 std bands
2. **RSI Confirmation:** RSI < 25 (oversold) or > 75 (overbought)
3. **Pyramiding:** Can add up to 6 entries with 6-bar cooldown between adds
4. **Exit:** When price returns to the middle band

### Key Parameters
```yaml
bb_period: 15
bb_std: 2.5
rsi_oversold: 25
rsi_overbought: 75
pyramid_cooldown_bars: 6
```

**Best For:** Ranging crypto and forex. Works well on assets that oscillate around a mean.

---

## 6. HyperScalper

> **"Speed is everything. Compound aggressively."**

### How It Works
1. **EMA Crossover:** 9 EMA crosses 21 EMA
2. **Trend Filter:** 200 EMA confirms overall direction
3. **RSI Filter:** RSI must agree with the crossover direction
4. **Fast Timeframe:** 5-minute candles for quick entries

### Risk Profile
- Default 1% risk per trade
- Targets 3.0 ATR for 100%+ weekly return potential
- Designed for aggressive compounding

### Key Parameters
```yaml
ema_fast: 9
ema_slow: 21
ema_trend: 200
timeframe: 5m
target_atr: 3.0
```

**Best For:** Liquid forex pairs (EUR/USD, GBP/USD), fast-moving markets. Requires active monitoring.

---

## 7. London Breakout

> **"Trade the institutional open."**

### How It Works
1. **Mark the Range:** Record high/low from 08:00-09:00 GMT (first hour of London session)
2. **Wait for Breakout:** Price must break above the high or below the low
3. **Deadline:** Entry must occur before 12:00 GMT (noon)
4. **Target:** 1.5R fixed risk/reward

### Why It Works
The London session open sees massive institutional order flow as European banks, funds, and traders come online. This creates predictable breakout patterns.

### Key Parameters
```yaml
range_start: "08:00"
range_end: "09:00"
entry_deadline: "12:00"
timezone: "GMT"
target_r: 1.5
```

**Best For:** GBP pairs (GBP/USD, GBP/JPY, EUR/GBP), European session only.

---

## 8. Volatility Breakout

> **"Catch the explosion when the range breaks."**

### How It Works
1. **Identify Compression:** Price consolidates in a 20-period range
2. **RSI Confirmation:** RSI > 60 for longs, < 40 for shorts
3. **Enter on Break:** Trade the breakout direction
4. **Momentum Exit:** Exit when RSI reverses (crosses back)

### Key Parameters
```yaml
range_period: 20
rsi_long_threshold: 60
rsi_short_threshold: 40
target_r: 2.0
```

**Best For:** Any market showing compression (low volatility → high volatility). Works on crypto, forex, futures.

---

## 9. Singularity Aggregator

> **"Never miss an opportunity. Always stay loaded."**

### How It Works
1. **Runs Two Strategies:** Mean Reversion + HyperScalper simultaneously
2. **Priority System:**
   - First: Scale into existing winners (pyramiding)
   - Second: New entries on fresh signals
3. **Capital Efficiency:** Keeps the bot "always loaded" with positions

### Why Use It
Traditional strategies have downtime waiting for setups. The Aggregator runs multiple strategies in parallel, maximizing capital utilization.

**Goal:** 400%+ returns by never having idle capital.

**Best For:** Accounts that can handle multiple positions. Maximum growth mode.

---

## Per-Asset Strategy Assignment

You don't have to use the same strategy for everything. Configure different strategies per asset class:

### In the GUI
**Settings → Strategy Workshop → Asset Strategies**

### In YAML
```yaml
strategies:
  crypto: rubberband_reaper    # Anti-martingale for volatile crypto
  forex: rubberband_reaper     # Proven +7,036% on forex
  stocks: quantum              # Trend-following for equities
  etf: quantum                 # Works on SPY, QQQ
  metals: mean_reversion       # Gold/Silver tend to range
  futures: volatility_breakout # Catch breakouts on ES, NQ
```

---

## The "Feet Wet" Approach

Regardless of which strategy you choose, start conservatively:

### Day 1: Paper Trading
```bash
EXECUTE_TRADES=false  # Simulation mode
```

### Day 2-7: Micro-Sizing
```yaml
risk_per_trade_pct: 0.01  # 1% risk only
```

### Week 2+: Gradual Increase
Once you trust the system:
1. Increase to 2%, then 5%
2. Enable multi-position trading
3. Experiment with different strategies per asset class

---

## Strategy Selection Guide

| Market Condition | Recommended Strategy |
|------------------|---------------------|
| Trending strongly | Quantum, RoboCop |
| Ranging/Sideways | Evolution, Mean Reversion |
| High volatility | Rubberband Reaper, RoboCop |
| Low volatility (compression) | Volatility Breakout |
| London session (GBP) | London Breakout |
| Fast markets | HyperScalper |
| Maximum capital use | Aggregator |

---

## Common Misconceptions

### "Higher win rate = better"
**Wrong.** A 25% win rate with 4:1 reward-to-risk beats a 60% win rate with 1:1.

### "I should avoid losing trades"
**Wrong.** Losses are part of the system. The goal is small losses and big wins.

### "One strategy should work everywhere"
**Wrong.** That's why we have 9 strategies. Match the strategy to the market condition.

---

> *"The market doesn't care about your feelings. It only respects your edge. Pick the right strategy for the right market, and let math do the rest."*
