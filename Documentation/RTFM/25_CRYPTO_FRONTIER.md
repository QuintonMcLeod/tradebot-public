# 25. The Crypto Frontier — The Wild West of 24/7 Markets

<table><tr><td width="170"><img src="img/pirate.png" width="150"></td><td><b>PIRATE</b>:<br>"Crypto! The wild seas! 24/7 markets, no rules, maximum chaos! 🏴‍☠️"</td></tr></table>

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"Please be careful out there, sweetie. Crypto is volatile."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Welcome to the asset class that never sleeps, rarely makes sense, and occasionally drops 40% because someone tweeted a meme. Trading crypto is fundamentally different from forex or stocks. The rules change. The hours change. The volatility changes. And the bot adapts to all of it."</td></tr></table>

---

## The Big Differences

### 1. No Closing Bell

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"24/7/365. Your wedding? Trading. The sun exploding? Still trading until the servers melt."</td></tr></table>

- No weekend flattening for crypto positions
- No session detection unless overlaying for volatility
- Runs in `crypto_247` profile with no time restrictions

### 2. Volatility on Steroids

EUR/USD moves 0.5-1.0% per day (normal). BTC/USD can move 5-10% per day (also "normal"). On spicy days: 15-20% swings.

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"ATR-based stops automatically widen for crypto. Position sizes automatically shrink. More volatility = smaller positions = same risk per trade. The math stays the same, the numbers just get bigger."</td></tr></table>

### 3. Spreads and Slippage

Forex: 1-2 pip spreads. Some crypto pairs: spreads measured in percentages.

The **Friction Model** calculates expected transaction costs before each trade. If the cost eats too much of the expected profit → trade downgraded.

### 4. Liquidity Varies Wildly

<table><tr><td width="170"><img src="img/ninja.png" width="150"></td><td><b>NINJA</b>:<br><em>"BTC and ETH are highly liquid. SOL at 3 AM on a Sunday? Liquidity can evaporate faster than a puddle in the Sahara."</em></td></tr></table>

Volume confirmation is baked into strategies. No volume = no conviction = no trade.

---

## Crypto-Optimized Strategies

| Strategy | Why It Works for Crypto |
|----------|----------------------|
| **RSI + MACD** | Catches the beginning of momentum moves |
| **VWAP Reversion** | Crypto drifts from VWAP constantly |
| **Double MACD** | Dual timeframe scalps during ranging periods |
| **Virtual Grid** | Predictable ranges during consolidation |
| **Rubberband Reaper** | Extreme BB extensions create high-probability snap-backs |

When running Meta-SCI on crypto symbols, these strategies automatically enter the tournament alongside universal strategies.

---

## Crypto Quantity Steps

> ⚙️ Config only: `config.json` under your profile

```yaml
crypto_qty_steps:
  BTCUSD: 0.001    # Minimum 0.001 BTC per trade
  ETHUSD: 0.01     # Minimum 0.01 ETH per trade
  SOLUSD: 0.1      # Minimum 0.1 SOL per trade
```

---

## The Whales and the Plankton

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Here's the brutal truth: crypto markets are heavily manipulated. Whales move the market by sneezing. Wash trading inflates volume. Influencers pump and dump in the same hour."</td></tr></table>

The bot's defense:
- **Structure over narrative.** Doesn't read Twitter. Reads candles.
- **Volume confirmation.** Fake volume often doesn't create real structure.
- **Stop-losses respect volatility.** ATR accounts for whale-sized moves.

---

## Crypto-Specific Risks

| Risk | Mitigation |
|------|-----------|
| Exchange downtime | Paper mode catches gaps. Server-side stops hold. |
| Flash crashes | Wide ATR stops absorb flash movements. Daily Loss Limit caps damage. |
| Regulatory news | Structure-based trading ignores news. |
| Rug pulls / delistings | Only trade established coins (BTC, ETH, SOL, XRP). |

---

## The Bottom Line

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Crypto is the most exciting and the most dangerous asset class you can trade. The rewards are larger, the risks are larger, and the variance is enough to make a casino blush.<br><br>The bot treats crypto with respect — wider stops, smaller sizes, dedicated strategies. It doesn't fear crypto. It just sizes its bets appropriately.<br><br><em>Fortune favors the bold. But position sizing favors the alive.</em>"</td></tr></table>
