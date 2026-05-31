---
title: '36 Weapons of War: The Complete Strategy Arsenal'
category: rtfm
icon: strategy
description: "\"One strategy doesn't fit all markets. Choose your weapon wisely \u2014\
  \ or let Meta-SCI choose for you.\" TradeBot SCI supports 36 distinct trading strategies\
  \ \u2014 including the new Forex Conductor with regime-based routing and per-symbol\
  \ cooldowns. You can assign different strategies to different asset classes, or\
  \ use Meta-SCI to let the bot pick the best one automatically via tournament-style\
  \ scoring."
featured: true
---

# 09. 36 Weapons of War: The Complete Strategy Arsenal

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"I want to understand the strategies! There's like... thirty-six of them? Which one do I pick? This is like being at a buffet where everything is labeled in a language I don't speak."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"You don't pick! Why would you pick? I spent months building Meta-SCI so you don't have to make decisions that you are completely unqualified to make! But fine, since you want to look at the shiny toys, let me walk you through the catalog. You don't need to touch them, just look at them and appreciate the engineering!"</td></tr></table>

---

## Strategy Overview

### ⭐ The Recommended Default: Meta-SCI

| Strategy | Key | Style | Best For |
|----------|-----|-------|----------|
| **Meta-SCI** | `meta_sci` | AI Ensemble (auto-selects best strategy) | All markets — the recommended default |

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"Meta-SCI is the conductor of the orchestra. It doesn't play an instrument — it decides which instrument plays when. And unlike a human conductor, it never picks the wrong section. Well... <em>almost</em> never."</td></tr></table>

### Universal Strategies (Forex + Crypto + Stocks)

| Strategy | Key | Style | Best For |
|----------|-----|-------|----------|
| **Rubberband Reaper** | `rubberband_reaper` | Mean Reversion + Anti-Martingale | Ranging markets, volatile assets |
| **RoboCop** | `robocop` | Sniper Precision Entries | High-conviction setups, any market |
| **Mean Reversion** | `mean_reversion` | Bollinger Band + RSI Reversion | Ranging crypto and forex |
| **Supply & Demand** | `supply_demand` | Institutional Zone Trading | Support/resistance plays |
| **Trend Rider** | `trend_rider` | EMA Pullback Continuation | Strong trending markets |
| **Session Momentum** | `session_momentum` | VWAP at Session Open | London/NY open volatility |
| **Engulfing Reversal** | `bearish_engulfing` | Candlestick Pattern Recognition | Key reversal levels |
| **ICC Core** | `icc_core` | Pure ICC Structure Trading | Structure-first patience |
| **ORB Breakout** | `orb_breakout` | Opening Range Breakout | First-hour range breaks |
| **Golden Pocket** | `golden_pocket` | Dynamic Value Pullback | Strong trending macro markets |
| **ICC Core Standalone** | `icc_core_standalone` | Vanilla ICC Entry Model | Strictly pure ICT structure |
| **Wind Down Truffle** | `wind_down_truffle` | Friday Afternoon Fade | Assets with Friday PM weekend closes |
| **Yo-Yo** | `yoyo` | SAR Trend-Follower | Accelerating sustained trends |

### Crypto-Specific Strategies

| Strategy | Key | Style | Best For |
|----------|-----|-------|----------|
| 🪙 **RSI + MACD** | `crypto_rsi_macd` | Classic Momentum Crossover | Crypto trending |
| 🪙 **VWAP Reversion** | `crypto_vwap_reversion` | Mean Reversion to VWAP | Crypto ranging |
| 🪙 **Double MACD** | `crypto_double_macd` | Dual-Timeframe Scalping | Crypto scalping |
| 🪙 **Virtual Grid** | `crypto_grid` | Grid Trading at Fixed Levels | Crypto sideways markets |

### Legacy / Niche Strategies

| Strategy | Key | Style | Best For |
|----------|-----|-------|----------|
| **Robot Evolution** | `evolution` | NTZ Edge Scalping | Sideways/consolidation |
| **Quantum** | `quantum` | SMA Trend Following | Strong trending forex |
| **HyperScalper** | `hyper_scalper` | Fast EMA Crossover | Liquid forex, fast markets |
| **London Breakout** | `london_breakout` | Session Range Breakout | GBP pairs, European session |
| **Volatility Breakout** | `volatility_breakout` | Range Compression Breakout | Compressed markets |
| **Aggregator** | `aggregator` | Multi-Strategy Parallel | Maximum capital efficiency |

### Forex-Specific Strategies

| Strategy | Key | Style | Best For |
|----------|-----|-------|----------|
| 📈 **Forex Conductor** | `forex_conductor` | Regime-Based Router (SAR + Pyramiding) | Forex trending — per-symbol cooldowns, cost-aware TP |
| 📈 **Forex Hybrid Reaper** | `forex_hybrid_reaper` | Spaced Mean Reversion | Forex ranging markets |
| 🕰️ **London Sweep** | `london_sweep` | European Open Sweep | Trading GBP/EUR liquidity hunts |
| 🕰️ **New York Drive** | `new_york_drive` | US Session Momentum | High-volatility USD dollar moves |

### Futures-Specific Strategies

| Strategy | Key | Style | Best For |
|----------|-----|-------|----------|
| 🏛️ **Silver VWAP** | `silver_vwap` | 10AM VWAP Breakout | CME Futures (NQ/ES) morning trends |

### Advanced Quantitative Strategies

| Strategy | Key | Style | Best For |
|----------|-----|-------|----------|
| **QS 200-SMA Filter** | `qs_sma_filter` | Regime Filter | Capital preservation in bear markets |
| **QS Golden Cross** | `qs_golden_cross` | Long-term Trend | Catching massive multi-month bull runs |
| **QS RSI-2 Mean Rev** | `qs_rsi_mean_reversion` | Mean Reversion | Buying aggressive dips in an uptrend |
| **QS 3/10 Trend** | `qs_3_10_trend` | Macro Trend | Lazy, slow multi-month investing |
| **QS TQQQ/BTAL** | `qs_tqqq_btal` | Rebalancing | Monthly index fund management |
| **QS Choppiness** | `qs_choppiness` | Measurement Filter | Checking if market is actually moving |
| **QS Seasonal FDOM** | `qs_first_day_month` | Seasonal / Calendar | Front-running institutional beginning-of-month cash |

---

## 1. Meta-SCI — The Adaptive Ensemble ⭐

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Why would you commit to one strategy? That's insane! The bot can run thirty-six options in the time it takes you to blink! It's literally putting 36 traders in a cage match and only paying the one who wins. It's brutal, it's efficient, and it doesn't complain about the air conditioning!"</td></tr></table>

### How the Tournament Works

```
Symbol: EURUSD → Regime Detection → BULLISH_TRENDING

Tournament:
  ├── Rubberband Reaper  → STAND_ASIDE (ranging strategy, wrong regime)
  ├── Trend Rider         → ENTER_LONG (score: 78.5) ✅
  ├── Supply & Demand     → ENTER_LONG (score: 65.2)
  ├── Session Momentum    → STAND_ASIDE (not session open)
  └── Engulfing Reversal  → STAND_ASIDE (no engulfing pattern)

🏆 Winner: Trend Rider (highest score: 78.5)
→ Action: ENTER_LONG EURUSD
```

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"The tournament follows a precise six-step process. No shortcuts. No favorites. Pure meritocracy:"</td></tr></table>

1. **Regime Detection** — Is the market trending, ranging, mean-reverting, or choppy?
2. **Strategy Eligibility** — Each strategy has regimes it's suited for. Only matching ones compete.
3. **Parallel Evaluation** — Every eligible strategy generates a signal independently.
4. **Scoring & Ranking** — Signals scored by conviction (0-100), entry quality, and R:R.
5. **Winner Selection** — Highest-scoring signal becomes the trade decision.
6. **Graceful Fallback** — If no strategy scores above threshold → STAND ASIDE (no trade).

### Market Regimes

| Regime | Eligible Strategies |
|--------|-------------------|
| **Bullish Trending** | Trend Rider, RoboCop, Session Momentum, Supply & Demand, ICC Core |
| **Bearish Trending** | Same as bullish (reversed direction) |
| **Ranging** | Rubberband Reaper, Mean Reversion, Supply & Demand, Engulfing Reversal |
| **Mean Reverting** | Mean Reversion, Rubberband Reaper, VWAP Reversion |
| **Choppy / Unclear** | Conservative selection only — fewer strategies eligible |

<table><tr><td width="170"><img src="img/bear.png" width="150"></td><td><b>BEAR</b>:<br>"So when the market is choppy, it doesn't just YOLO into a random strategy?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"No! When the market is garbage, the bot sits in the corner and does nothing! Which is exactly what you should do, but you can't, because you have a gambling problem and you keep seeing patterns in static electricity! The bot has the restraint you wish you had!"</td></tr></table>

**Crypto Routing:** When Meta-SCI scans a crypto symbol, it automatically includes crypto-specific strategies (RSI+MACD, VWAP Reversion, Double MACD, Virtual Grid) alongside universal strategies.

**Best For:** Everything. Use this unless you have a very specific, very informed reason not to. And "I read a Reddit post" is not a reason.

---

## 2. Rubberband Reaper

<table><tr><td width="170"><img src="img/ninja.png" width="150"></td><td><b>NINJA</b>:<br><em>"Price is a rubber band. Stretch it far enough... it always snaps back."</em></td></tr></table>

**How It Works:**
1. **Detection:** Watches for price to break outside Bollinger Bands (2.5 std)
2. **Confirmation:** RSI confirms oversold (<25) or overbought (>75)
3. **Entry:** Enters expecting reversion to the mean
4. **Target:** Opposite Bollinger Band for 3:1+ reward-to-risk

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"The secret sauce is the <b>Anti-Martingale</b> risk. Unlike systems that increase size after losses — which is called 'digging your own grave faster' — Rubberband does the opposite: after a WIN, increase size. After a LOSS, decrease size. Simple. Logical. And yet nobody does this manually because human ego says 'but I need to win it back.'"</td></tr></table>

**Best For:** Crypto, forex pairs that range (EUR/USD, AUD/USD), volatile altcoins.

---

## 3. RoboCop

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Maximum precision. Minimum noise. If Rubberband Reaper is a shotgun, RoboCop is a sniper rifle with a laser sight and a cup of herbal tea."</td></tr></table>

**How It Works:**
1. **Structural Confirmation:** Waits for clean ICC structure alignment
2. **High-Conviction Filter:** Only fires on setups with strong multi-timeframe agreement
3. **Wide Targets:** 3.0 ATR target for maximum profit potential
4. **Fast Exit:** "Chop exit" triggers if price stalls in a range

**Best For:** Low-frequency, high-conviction setups in any market. Expects fewer trades but bigger wins. The patient hunter.

---

## 4. Mean Reversion

<table><tr><td width="170"><img src="img/monk.png" width="150"></td><td><b>MONK</b>:<br><em>"What goes up must come down. What goes down must come up. Balance is not a philosophy — it is a law."</em></td></tr></table>

**How It Works:**
1. **Bollinger Band Break:** Price breaks outside 15-period, 2.5 std bands
2. **RSI Confirmation:** RSI < 25 (oversold) or > 75 (overbought)
3. **Pyramiding:** Can add up to 6 entries with cooldown between adds
4. **Exit:** When price returns to the middle band

**Best For:** Ranging crypto and forex. Works on assets that oscillate around a mean like a kid on a swing.

---

## 5. Supply & Demand

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"Trade where the institutions trade. Not where Reddit tells you to trade. There's a difference. A very expensive difference."</td></tr></table>

**How It Works:**
1. **Zone Identification:** Detects supply and demand zones from historical price action
2. **Zone Strength:** Scores zones by how many times they've held
3. **Entry on Retest:** Enters when price returns to a strong zone
4. **Target:** Opposite zone for clean risk/reward

**Best For:** Support/resistance traders. Works across all asset classes.

---

## 6. Trend Rider

<table><tr><td width="170"><img src="img/bull.png" width="150"></td><td><b>BULL</b>:<br>"THE TREND IS MY FRIEND! I RIDE THE TREND LIKE A MECHANICAL BULL AT A COUNTY FAIR!"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Please calm down. Yes, the trend is your friend. But unlike you at a county fair, the bot waits for a <em>pullback</em> before jumping on. It doesn't chase."</td></tr></table>

**How It Works:**
1. **Wait for Pullback:** Price must retrace to the EMA
2. **Confirm Trend:** HTF and LTF must both show the same direction
3. **Enter on Bounce:** Enter when price bounces off the EMA in trend direction
4. **Exit on Flip:** Automatically exits when HTF trend reverses

**Best For:** Strong trending markets (GBP/JPY, EUR/GBP, trending crypto).

---

## 7. Session Momentum

<table><tr><td width="170"><img src="img/ninja.png" width="150"></td><td><b>NINJA</b>:<br><em>"The institutions arrive at the session open. They move the market with the precision of a military operation. I arrive with them. Silently."</em></td></tr></table>

**How It Works:**
1. **Detect Session Open:** Identifies London (08:00 GMT) and NY (13:30 GMT) opens
2. **VWAP Reference:** Calculates session VWAP as fair value anchor
3. **Momentum Entry:** Enters in the direction of early session momentum vs VWAP
4. **Session Close Exit:** Exits before session end if target not hit

**Best For:** London/NY session opens. High-volatility first-hour trades.

---

## 8. Engulfing Reversal

<table><tr><td width="170"><img src="img/ghost.png" width="150"></td><td><b>GHOST (The AI)</b>:<br><em>"The candle tells the story. An engulfing candle at a key level is the market screaming 'I CHANGED MY MIND.' Most traders hear the scream. Few act on it in time."</em></td></tr></table>

**How It Works:**
1. **Pattern Detection:** Identifies bullish/bearish engulfing candle patterns
2. **Key Level Filter:** Only trades engulfing patterns at significant S/R levels
3. **Volume Confirmation:** Requires above-average volume on the engulfing candle
4. **Tight Stops:** Places stop beyond the engulfing candle's range

**Best For:** Reversal trading at key levels. Works across all markets.

---

## 9. ICC Core

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"This is the purest implementation of the ICC framework. No shortcuts. No aggressive entries. No 'I think it's gonna go.' Pure structure. Three letters: Indication → Correction → Continuation.<br><br>If the structure doesn't complete all three steps? No trade. If it completes all three? We enter. Period. It's like a combination lock — you either have all three numbers or you have nothing."</td></tr></table>

**How It Works:**
1. **Indication:** Identifies a clean structural break (HH/HL or LH/LL)
2. **Correction:** Waits for a pullback into discount/premium zone
3. **Continuation:** Enters when price breaks back in the trend direction

**Best For:** Traders who want the most disciplined, structure-first approach. The patient student.

---

## 10. ORB Breakout (Opening Range Breakout)

<table><tr><td width="170"><img src="img/pirate.png" width="150"></td><td><b>PIRATE</b>:<br>"Arrr! The first 15 minutes write the story for the day! I mark me range, I wait for the break, and I PLUNDER! 🏴‍☠️"</td></tr></table>

**How It Works:**
1. **Mark the Range:** Records high/low from the first 15-30 minutes
2. **Wait for Break:** Price must break above the high or below the low
3. **Volume Filter:** Requires above-average volume on the break
4. **Target:** 1.5-2.0x the opening range height

**Best For:** Intraday trading on stocks, futures, and forex session opens.

---

---

## 11. Golden Pocket

<table><tr><td width="170"><img src="img/monk.png" width="150"></td><td><b>MONK</b>:<br><em>"Price seeks equilibrium. When an established trend corrects into the golden mathematical ratios — it is merely gathering breath for the next leap."</em></td></tr></table>

**How It Works:**
1. **Macro Trend Filter:** Requires structural EMA 21 to sit cleanly above EMA 55.
2. **Value Identification:** Waits for a meaningful pullback into the value pocket.
3. **Execution:** Buys the dip at the "golden" discount without trying to catch a falling knife.

**Best For:** Strong macro trends offering brief retracements.

---

## 12. ICC Core Standalone

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"For those who think Meta-SCI is too wild. This is the pure, unadulterated Trade By SCI doctrine. Nothing extra."</td></tr></table>

**How It Works:**
1. **Direction Bias:** Locks onto purely the High Timeframe structural direction.
2. **Sweep Detection:** Requires a liquidity sweep of a major swing level.
3. **Displacement:** Requires 3+ momentum candles confirming the reversal.
4. **OTE Alignment:** Only enters if the market pulls back precisely into the Optimal Trade Entry zone.

**Best For:** Structural purists trading the true ICT Entry Model.

---

## 13. Yo-Yo

<table><tr><td width="170"><img src="img/ninja.png" width="150"></td><td><b>NINJA</b>:<br><em>"Do not guess when the trend ends. Ride it until you are thrown off."</em></td></tr></table>

**How It Works:**
1. **Trend Filter:** Uses the 50 SMA as a strict "no-fly zone."
2. **Candle Check:** Entry candles must close strongly in their directional top/bottom 30%.
3. **SAR Stop:** Employs Parabolic SAR moving stops.
4. **Risk Escalator:** Automatically increases position size after winners, pressing the advantage.

**Best For:** Markets experiencing prolonged, low-pullback trends.

---

## 14. Wind Down Truffle

<table><tr><td width="170"><img src="img/ghost.png" width="150"></td><td><b>GHOST (The AI)</b>:<br><em>"Everyone goes home on Friday at 2 PM. Volume disappears. Price drifts lazily. It is the easiest money of the entire week."</em></td></tr></table>

**How It Works:**
1. **Time Lock:** Only active between Friday 12:00 PM and 4:30 PM ET.
2. **VWAP Fade:** Shorts markets drifting below session VWAP with declining EMA momentum.
3. **Volume Check:** Rejects entries if volume spikes (thin liquidity fading only).

**Best For:** Boring, dead Friday afternoons across any major asset.

---

## Crypto-Specific Strategies

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"These four are designed specifically for the crypto wild west. They're automatically included in Meta-SCI tournaments when scanning crypto symbols. You don't need to manually enable them — the bot knows when it's looking at Bitcoin versus EURUSD."</td></tr></table>

### 15. RSI + MACD (Crypto)

The classic combo, optimized for crypto volatility.

1. **RSI Signal:** Identifies oversold (<30) and overbought (>70) conditions
2. **MACD Confirmation:** MACD histogram must confirm direction
3. **Dual Filter:** Both indicators must agree before entry

**Best For:** Trending crypto markets (BTC, ETH during strong moves).

### 16. VWAP Reversion (Crypto)

<table><tr><td width="170"><img src="img/monk.png" width="150"></td><td><b>MONK</b>:<br><em>"Price always visits VWAP. Always. It may wander, but it returns. Like a cat that pretends it doesn't live at your house."</em></td></tr></table>

1. **VWAP Deviation:** Detects when price deviates significantly from VWAP
2. **Volume Confirmation:** Requires volume exhaustion at extremes
3. **Target:** Return to VWAP for clean R:R

**Best For:** Ranging crypto. Works well during low-volatility periods.

### 17. Double MACD (Crypto)

Two timeframes, one signal. Like having bifocals for the market.

1. **Fast TF MACD:** Quick signal on the execution timeframe
2. **Slow TF MACD:** Confirmation from a higher timeframe
3. **Dual Agreement:** Both timeframes must show the same direction

**Best For:** Crypto scalping. Short-duration trades in trending conditions.

### 18. Virtual Grid (Crypto)

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"Grid trading without the grid. Instead of placing 50 limit orders and praying, this strategy places virtual buy/sell levels and only triggers when price actually reaches them. Much cleaner. Much less terrifying."</td></tr></table>

1. **Level Calculation:** Places virtual buy/sell levels at fixed intervals around current price
2. **Level Tracking:** Tracks which levels have been hit
3. **Mean Reversion:** Buys at lower levels, sells at upper levels

**Best For:** Crypto sideways markets. Accumulation during consolidation.

---

## Forex-Specific Strategies

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"These are ruthlessly optimized for fiat currencies. You don't bring a crypto grid-trading bot to a Eurozone central bank rate hike. You bring these."</td></tr></table>

### 19. Forex Conductor

The flagship regime-based router handling the most complex of forex currents.

1. **Trend Analysis:** Analyzes High Timeframe ADX to verify strong, tradable trends.
2. **Cooldown Control:** Implements per-symbol cooldowns to stop churn when a pair stalls.
3. **Execution:** Manages entries using cost-aware TP tracking to overcome forex spread drag.

**Best For:** Majors and minors that follow central bank trajectories.

### 20. Forex Hybrid Reaper

The classic Reaper framework slightly reconfigured for currency speed.

1. **Mean Reversion:** Targets bollinger explosions on M5/M15 standard pairs.
2. **Spread Considerations:** Widens validation checks to prevent getting chopped by broker swaps.

**Best For:** EURUSD, USDJPY traversing tight daily ranges.

### 21. London Sweep

<table><tr><td width="170"><img src="img/pirate.png" width="150"></td><td><b>PIRATE</b>:<br>"FRANKFURT WAKES UP AND HUNTS LIQUIDITY! WE HUNT WITH THEM!"</td></tr></table>

1. **Session Anchor:** Tracks overnight Asian ranges.
2. **London Open:** Trades the aggressive whipsaw commonly found at 3:00 AM EST.
3. **Target:** Hunts the opposite end of the Asian session block.

**Best For:** GBP and EUR crosses during EU morning.

### 22. New York Drive

1. **US Open Anchor:** Capitalizes on the 8:00 AM - 10:00 AM EST volume glut.
2. **Alignment:** Looks for alignment between the London high and NY opening momentum.

**Best For:** USD crosses during Wall Street hours.

---

## Futures-Specific Strategies

### 23. Silver VWAP

<table><tr><td width="170"><img src="img/bull.png" width="150"></td><td><b>BULL</b>:<br>"TEN AM! TEN AM! IT'S THE SILVER BULLET WINDOW! BUY THE NQ AND DON'T LOOK BACK!"</td></tr></table>

1. **Time Lock:** Only operates in the notoriously volatile 09:50 AM to 11:10 AM EST window.
2. **Filters:** Uses the 15M opening range and Anchored VWAP as anchors.
3. **Entries:** Executes primarily on VWAP pullbacks within established morning trends.

**Best For:** CME Index Futures (NQ/ES/YM).

---

## Per-Asset Strategy Assignment

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"You can assign different strategies to different asset classes. Maybe you want Mean Reversion on crypto and Trend Rider on forex. Here's how:"</td></tr></table>

### Via the Profile Editor
**Profile Editor** → Select profile → **General** tab → **Strategy** dropdown

To assign different strategies per asset class, use the **per-asset strategy dropdowns** in the same tab (Crypto, Forex, Stocks, Metals each have their own dropdown).

### Via config.json
```json
{
  "profiles": {
    "my_profile": {
      "strategy": "meta_sci",
      "strategies": {
        "crypto": "meta_sci",
        "forex": "rubberband_reaper",
        "stocks": "trend_rider",
        "metals": "mean_reversion"
      }
    }
  }
}
```

---

## Strategy Selection Guide

| Market Condition | Recommended Strategy |
|------------------|---------------------|
| **Don't know / Mixed** | **Meta-SCI** (auto-selects) |
| Trending strongly | Trend Rider, RoboCop, Session Momentum |
| Ranging / Sideways | Rubberband Reaper, Mean Reversion, Supply & Demand |
| High volatility (crypto) | RSI + MACD, Double MACD |
| Low volatility (compression) | ORB Breakout, Engulfing Reversal |
| Session opens (forex) | Session Momentum, ORB Breakout |
| Key reversal levels | Engulfing Reversal, Supply & Demand |
| Maximum adaptability | **Meta-SCI** |

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"If you don't know which one to pick, pick Meta-SCI. If you <em>think</em> you know which one to pick, still pick Meta-SCI. The only reason to NOT pick Meta-SCI is if you've backtested a specific strategy on your specific symbols and it outperforms. And even then... maybe still Meta-SCI."</td></tr></table>

---

## The "Feet Wet" Approach

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"Baby, you don't jump into the deep end your first day at the pool. You dip your toes. Then your ankles. Then maybe your knees if the water feels right. Same thing here."</td></tr></table>

### Day 1: Paper Trading

> 📺 **In the UI:** Settings → **System** → toggle **Live Trading** OFF

```yaml
runtime:
  execute_trades: false    # Simulation mode — no real orders
```

### Day 2-7: Micro-Sizing

> 📺 **In the UI:** Settings → **Strategy Workshop** → **Global Risk** sub-tab → **Default Risk %** slider

```yaml
risk_per_trade_pct: 0.01  # 1% risk only
```

### Week 2+: Gradual Increase

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Once you trust the system — and trust is earned, not given — you can start opening the throttle:"</td></tr></table>

1. Increase to 2%, then 3-4% (Settings → Strategy Workshop → Global Risk → Default Risk %)
2. Enable multi-position trading (Settings → Safety & Shields → Max Concurrent Positions)
3. Experiment with different strategies per asset class (Settings → Strategy Workshop → Asset Strategies)
4. Or just use **Meta-SCI** and let it handle everything. Have I mentioned Meta-SCI yet?

---

## 62 Common Misconceptions (And Why They're Wrong)

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Alright, my favorite part. The part where I shatter all your delusions. I'm gonna take everything you learned from 19-year-olds on TikTok and throw it in the garbage. It's gonna hurt your feelings, but it's gonna save your wallet."</td></tr></table>

### 🎯 Win Rate & Performance

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"A higher win rate is better, right? Like, 80% win rate beats 40% every time?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"<b>Wrong.</b> A 25% win rate with 4:1 R:R beats a 60% win rate with 1:1 R:R. Every. Single. Time. What matters is <b>Profit Factor</b> — total wins divided by total losses. Not how often you're right. How <em>big</em> you are when you're right."</td></tr></table>

**The full misconception breakdown:**

1. **"Higher win rate = better"** — Wrong. R:R matters more than frequency.

2. **"I should avoid losing trades"** — Wrong. Losses are part of the system. The goal is small losses and big wins. A professional losing 6 out of 10 trades can still be wildly profitable.

3. **"If I lost 5 trades in a row, the next one must be a win"** — Wrong. Gambler's Fallacy. Each trade is independent. A coin doesn't "remember" previous flips, and neither does the market.

4. **"A 90% win rate system is safer than a 40% win rate system"** — Wrong. Many 90% systems achieve this by taking tiny profits and holding massive drawdowns. One bad trade can wipe out 50 winners.

5. **"I need to be right more than I'm wrong"** — Wrong. You need your winners to be *bigger* than your losers. Being right 35% of the time with 3:1 R:R is extremely profitable.

6. **"Profit factor is just win rate times R:R"** — Partially wrong. Fees, slippage, and trade management also contribute.

7. **"My backtest made 500% so it will do that live"** — Wrong. Backtests are always optimistic. They don't account for slippage, liquidity, or the fact that you'll panic at the first drawdown.

8. **"A strategy that lost money last month is broken"** — Wrong. Even the best strategies have losing months. What matters is the edge over 100+ trades.

---

### 💰 Risk Management

<table><tr><td width="170"><img src="img/bear.png" width="150"></td><td><b>BEAR</b>:<br>"Can I risk 10% per trade to grow faster?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Five losses at 10% risk = 41% drawdown. At 2% risk, the same 5 losses = only 9.6% drawdown. <b>Survival is the first rule.</b> You can't compound from zero."</td></tr></table>

9. **"I can risk 10% per trade to grow faster"** — Wrong. You're one bad streak from account destruction.

10. **"Stop losses are optional"** — Absolutely wrong. A trade without a stop is a gamble, not a trade.

11. **"I'll just close it manually when it goes against me"** — Wrong. Psychology will make you hold, hope, and average down until it's too late.

12. **"Wider stops mean more risk"** — Wrong. Risk is controlled by *position size*, not stop distance. A wider stop with smaller size = same dollar risk.

13. **"I should add to losing positions to lower my average"** — Wrong. This is "averaging down" and it's how accounts blow up. The bot pyramids *winners*, not losers.

14. **"Risk/reward doesn't matter if I have a high win rate"** — Wrong. 80% win rate with 1:5 R:R = net negative.

15. **"I should risk the same dollar amount on every trade"** — Not ideal. Percentage-based risk scales naturally.

16. **"Leverage is free money"** — Wrong. 10x leverage on a 1% move against you = 10% equity loss. Leverage is a tool, not a cheat code.

17. **"I don't need to worry about fees on small accounts"** — Wrong. On a $100 account, a $0.80 round-trip fee on a $1.50 profit eats 53% of it.

18. **"My broker won't let me lose more than my deposit"** — Mostly wrong. Flash crashes and gaps can still cause losses beyond your deposit.

---

### 📊 Technical Analysis

<table><tr><td width="170"><img src="img/skeptic.png" width="150"></td><td><b>SKEPTIC</b>:<br>"More indicators means better analysis, right? I have RSI, MACD, Stochastic, CCI, and Bollinger Bands all on the same chart. I can barely see the candles."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"That's not analysis. That's a Jackson Pollock painting. Most indicators are derived from the same data — price and volume. Adding four of them gives you four versions of the same information. Pick 1-2 and master them. Or better yet, let the bot use the right ones for each strategy."</td></tr></table>

19. **"Support and resistance are exact prices"** — Wrong. They're *zones*, not lines. Trading exact numbers leads to getting stopped by wicks.

20. **"More indicators = better analysis"** — Wrong. Four indicators from the same data = four versions of the same thing.

21. **"The trend is always your friend"** — Incomplete. The trend is your friend — *until it ends*. That's why Meta-SCI detects regimes first.

22. **"If RSI is oversold, the price must go up"** — Wrong. RSI can stay oversold for days in a downtrend.

23. **"Patterns work because of supply and demand"** — Partially true. Patterns work because *enough traders believe they work*. Self-fulfilling prophecy.

24. **"Higher timeframes are always more reliable"** — Partially true. But wider stops, fewer opportunities. Best approach: multi-timeframe analysis (which the bot does).

25. **"Volume doesn't matter in forex"** — Mostly right for tick volume, wrong conceptually. Liquidity still matters enormously.

26. **"Divergence always means reversal"** — Wrong. Divergence can persist through multiple legs. It's a warning sign, not a trigger.

27. **"Price action is better than indicators"** — Neither is better. Price action = *what*. Indicators = *how much*. The bot uses both.

28. **"If a candle has a long wick, it means rejection"** — Not always. Context matters. A wick at a key level means far more than a wick in no-man's-land.

---

### 🤖 Algo / Bot Trading

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"If the bot isn't trading, does that mean something is broken?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Usually? No. More often, the market is garbage and the bot is protecting you from yourself. A day with zero trades can be the <em>best</em> outcome. Standing aside IS a position. The most profitable position of all."</td></tr></table>

29. **"One strategy should work everywhere"** — Wrong. That's why there are 36. Use Meta-SCI.

30. **"Meta-SCI is slower because it runs multiple strategies"** — Wrong. Tournament runs in milliseconds.

31. **"The bot should trade constantly"** — Wrong. Standing aside is a position. The bot's job is finding *quality*, not *quantity*.

32. **"If the bot isn't trading, something is broken"** — Usually wrong. It's *protecting you*.

33. **"I should override the bot when I disagree"** — Dangerous. If you're going to override the algorithm, why run one?

34. **"Bots eliminate emotion from trading"** — Partially true. The bot eliminates *execution* emotion. But you can still turn it off during a drawdown or change settings out of fear.

35. **"More data = better decisions"** — Wrong. More data often means more noise. 50-200 candles is the sweet spot.

36. **"The bot needs to be right immediately"** — Wrong. Many winners go against you first. That's what stops are for.

37. **"If it works in backtest, just increase the risk"** — Wrong. Start conservative. Verify live. Then scale.

38. **"AI-powered trading is magic"** — Wrong. AI means systematic, data-driven decision-making. Not a crystal ball.

---

### 🪙 Crypto-Specific

<table><tr><td width="170"><img src="img/pirate.png" width="150"></td><td><b>PIRATE</b>:<br>"Crypto is 24/7! I should be trading at 3 AM on a Sunday! The money never sleeps, and neither do I!"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Wrong. Even 24/7 markets have volume windows. Trading at 3 AM on a Sunday means worse fills, wider spreads, and the kind of false signals that make you question your life choices on Monday morning."</td></tr></table>

39. **"Crypto is 24/7, so I should trade 24/7"** — Wrong. Volume concentrates around US/EU hours.

40. **"Bitcoin goes up long term, so I should only go long"** — Wrong for short-term trading. The bot trades both directions based on structure.

41. **"Altcoins are just cheaper Bitcoin"** — Wrong. Each altcoin has its own liquidity profile and behavior. BCHUSD is nothing like BTCUSD.

42. **"Crypto fees don't matter because the moves are big"** — Wrong. 0.80% round-trip on Gemini eats over half your profit on a 1.5% capture.

43. **"I should trade every crypto symbol available"** — Wrong. More symbols ≠ more profit. Low-liquidity = wider spreads = more pain.

44. **"Crypto is too volatile for stop losses"** — Wrong. It's too volatile for *tight* stops. Wider stops + smaller size = same dollar risk.

45. **"DeFi yields mean I should hold, not trade"** — Apples and oranges. Yield farming and active trading are completely different games.

---

### 💱 Forex-Specific

46. **"Forex is less risky because the moves are small"** — Wrong. Leverage makes 50 pips feel like 500.

47. **"I need $10,000+ to trade forex"** — Wrong for opening an account. True for meaningful position sizes.

48. **"All forex pairs behave the same"** — Wrong. EUR/USD moves 50-80 pips/day. GBP/JPY moves 150-200. Completely different animals.

49. **"News trading is easy money"** — Wrong. Spreads widen, slippage increases. The bot avoids the first 15 minutes of session opens for exactly this reason.

50. **"Friday afternoon is a good time to trade forex"** — Wrong. Liquidity dries up. Weekend gap risk increases. The bot has Friday Fade for this.

---

### 🧠 Trading Psychology

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"Baby, the biggest enemy in trading isn't the market. It isn't the algorithm. It's the voice inside your head that says 'one more trade and I'll stop.' That voice is a liar. It has always been a liar."</td></tr></table>

51. **"I need to watch my trades constantly"** — Wrong. Watching increases stress and leads to premature exits. That's literally why you have a bot.

52. **"Revenge trading will make back my losses"** — The #1 account killer. The Streak Breaker and Churn Burner exist to prevent this.

53. **"I should feel confident about every trade"** — Wrong. If you feel confident about *every* trade, your standards are too low.

54. **"If I study hard enough, I can predict the market"** — Wrong. The market is probabilistic, not predictable. The goal is finding slight edges and repeating them.

---

### 🏗️ Market Structure & Mechanics

55. **"Markets are random"** — Wrong. They exhibit trends, mean reversion, volatility clustering, and institutional footprints. But they're not fully predictable either. They exist in between.

56. **"The market is out to get me"** — Wrong. The market doesn't know you exist. What's actually happening is that many traders place stops at the same levels, and algorithms sweep those clusters.

57. **"Smart money always wins"** — Wrong. Institutions have size constraints, regulatory limits, and committee-based decisions. Retail has speed and flexibility.

58. **"Gaps always get filled"** — Mostly true historically, but "eventually" can mean weeks. Don't trade this blindly.

---

### 📈 Account Growth & Compounding

59. **"I should double my account every month"** — Wrong. Consistent 5-10% monthly would make you one of the best traders alive. Expecting 100% leads to over-leveraging.

60. **"Compounding is easy — just reinvest profits"** — Harder than it sounds. One month of -20% erases several months of +5%.

61. **"Small accounts can't make money"** — Wrong. They make *less* money, but the skill is real and scalable.

62. **"I should withdraw profits immediately"** — Depends on your goals. If you're trying to grow, let profits compound.

---

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"There you go. 36 weapons and 62 myths destroyed. The market doesn't care about your feelings. It only respects your edge. Pick the right strategy for the right market — or let Meta-SCI pick for you — and let math do the rest.<br><br>And if you're still not sure which strategy to use after reading all of this? <b>Meta-SCI.</b> I can't say it enough times. <em>Meta-SCI.</em>"</td></tr></table>

---

## 📖 Continue Reading

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"Wow, okay I think I get it now. What's next?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Turn the page. We are going to talk about <b>Seasoned Trader</b>. Try to keep up."</td></tr></table>
