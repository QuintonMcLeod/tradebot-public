# 25. The Crypto Frontier — The Wild West of 24/7 Markets

<table><tr><td width="170"><img src="img/pirate.png" width="150"></td><td><b>PIRATE</b>:<br>"Crypto! The wild seas! 24/7 markets, no rules, maximum chaos! 🏴‍☠️"</td></tr></table>

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"Please be careful out there, sweetie. Crypto is volatile."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Welcome to Crypto! The only place on Earth where a billionaire tweets a picture of his dog and you lose your life savings! It never sleeps, it doesn't make any sense, and it's governed by absolute lunatics on the internet. The bot adapts to all of this chaos so you don't have to stay awake for 48 hours staring at candles."</td></tr></table>

---

## The Big Differences

### 1. No Closing Bell

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"24/7/365. Your wedding? Trading. The sun exploding? Still trading until the servers melt."</td></tr></table>

- No weekend flattening for crypto positions
- No session detection unless overlaying for volatility
- Runs in `crypto_247` profile with no time restrictions

### 2. Volatility on Steroids

EUR/USD moves 0.5-1.0% per day (normal). BTC/USD can move 5-10% per day (also "normal"). On spicy days: 15-20% swings.

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Look, EUR/USD moves like a reasonable adult. Bitcoin moves like a teenager who just drank four energy drinks. The bot knows this. It widens the stops and shrinks the position size so you don't get obliterated on a random Tuesday sneeze."</td></tr></table>

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

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Let me break your heart real quick: this entire market is manipulated by about twelve guys in Dubai. Whales move the market by blinking. Influencers pump and dump while you're still reading their tweet. The bot doesn't care. It ignores their nonsense and literally just reads the structure."</td></tr></table>

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

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Crypto is dangerous, man. It'll make a casino look like a savings account. The bot doesn't fear it, though. It just puts on a helmet, widens the stops, and goes to work. Fortune favors the bold, but proper position sizing favors the guy who actually wants to keep his money."</td></tr></table>
