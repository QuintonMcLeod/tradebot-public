
# 25. The Crypto Frontier (The Wild West of 24/7 Markets)
> *"Crypto: where 'stability' means it only moved 8% today."*

Welcome to the asset class that never sleeps, rarely makes sense, and occasionally drops 40% because someone tweeted a meme.

Trading crypto is fundamentally different from trading forex or stocks. The rules change. The hours change. The volatility changes. And the bot adapts to all of it.

---

## The Big Differences

### 1. No Closing Bell
Forex takes weekends off. The NYSE closes at 4 PM. Crypto? **24 hours a day, 7 days a week, 365 days a year.** Christmas Eve? Trading. Your wedding? Trading. The sun exploding? Still trading until the servers melt.

**What this means for the bot:**
*   **No weekend flattening** for crypto positions. The `flatten_on_exit` logic skips crypto symbols.
*   **No session detection** unless you're overlaying session awareness for volatility purposes.
*   Crypto symbols run in the `crypto_247` profile with no time restrictions.

### 2. Volatility on Steroids
EUR/USD moves about 0.5-1.0% per day. That's considered normal. BTC/USD can move 5-10% in a day and that's **also** considered normal. On spicy days, 15-20% swings happen.

**What this means for the bot:**
*   **ATR-based stops are wider.** The bot automatically adjusts stop-loss distance based on the symbol's volatility. BTC gets a wider stop than EUR/USD because its "normal" movement is bigger.
*   **Position sizes are smaller.** More volatility = smaller positions to keep risk constant.

### 3. Spreads and Slippage
Forex pairs on OANDA have 1-2 pip spreads. Some crypto pairs on smaller exchanges can have spreads measured in percentages. Even major pairs like BTC/USD can have 0.1-0.3% effective spreads when you factor in the exchange's fees.

**What this means for the bot:**
*   The **Friction Model** calculates expected transaction costs before each trade. If the cost eats too much of the expected profit, the trade is downgraded.
*   **Fee-aware position sizing** ensures the trade's risk/reward accounts for the round-trip cost of entering and exiting.

### 4. Liquidity Varies Wildly
BTC and ETH are highly liquid. You can move millions without moving the price. But SOL at 3 AM on a Sunday? XRP during a regulatory announcement? Liquidity can evaporate faster than a puddle in the Sahara.

**What this means for the bot:**
*   **Volume confirmation** is baked into several strategies. No volume = no conviction = no trade.
*   The bot prefers **high-volume symbols** configured in the crypto profile for exactly this reason.

---

## Crypto-Optimized Strategies

The bot includes strategies specifically designed for crypto's unique behavior:

| Strategy | Why It Works for Crypto |
|----------|----------------------|
| **RSI + MACD** | Crypto trends hard, and these momentum indicators catch the beginning of a move |
| **VWAP Reversion** | Crypto drifts from VWAP constantly, creating mean reversion opportunities |
| **Double MACD** | Dual timeframe confirmation catches crypto scalps during ranging periods |
| **Virtual Grid** | Crypto ranges are predictable during consolidation — perfect for grid accumulation |
| **Rubberband Reaper** | Crypto's extreme BB extensions create high-probability snap-back trades |

When running Meta-SCI on crypto symbols, these strategies autom atically enter the tournament alongside the universal strategies.

---

## Crypto Quantity Steps

Crypto uses different position sizing than forex. You can't buy "10,000 units of Bitcoin" — you buy fractions. The bot uses **quantity steps** to size positions correctly:

```yaml
crypto_qty_steps:
  BTCUSD: 0.001    # Minimum 0.001 BTC per trade
  ETHUSD: 0.01     # Minimum 0.01 ETH per trade
  SOLUSD: 0.1      # Minimum 0.1 SOL per trade
```

These are configured per-symbol because each crypto has different minimum trade sizes on the exchange.

---

## The Whales and the Plankton

Here's the brutal truth about crypto markets: **they're heavily manipulated.**

*   **Whales** (wallets holding massive amounts) can move the market by sneezing.
*   **Wash trading** inflates volume on some exchanges, making it look like there's more activity than there is.
*   **Twitter influencers** can pump a coin 30% with a single post and dump it an hour later.

The bot's defense:
*   **Structure over narrative.** The bot doesn't read Twitter. It reads candles.
*   **Volume confirmation.** Fake volume often doesn't create real structure.
*   **Stop-losses respect volatility.** Even if a whale dumps BTC 5%, the ATR-based stop accounts for that kind of movement.

---

## Crypto-Specific Risks

| Risk | Mitigation |
|------|-----------|
| Exchange downtime | Paper mode catches the gap. Stop-losses at the exchange won't lapse. |
| Flash crashes | Wide ATR stops absorb flash movements. Daily Loss Limit caps total damage. |
| Regulatory news | Structure-based trading ignores news. The bot trades what the chart shows, not what CNN says. |
| Rug pulls / delistings | Only trade established coins (BTC, ETH, SOL, XRP). Leave the memecoins to Reddit. |

---

## The Bottom Line

Crypto is the most exciting and the most dangerous asset class you can trade. The rewards are larger, the risks are larger, and the variance is enough to make a casino blush.

The bot treats crypto with respect — wider stops, smaller sizes, dedicated strategies. It doesn't fear crypto. It just sizes its bets appropriately.

*"Fortune favors the bold. But position sizing favors the alive."*
