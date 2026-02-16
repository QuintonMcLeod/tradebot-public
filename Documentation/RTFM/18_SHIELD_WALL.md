
# 18. The Shield Wall (Risk Management Deep Dive)
> *"The fastest way to go broke is to be right 90% of the time and blow up on the other 10%."*

You can have the greatest strategy in the world. You can be right 80% of the time. You can predict market moves with the accuracy of a caffeinated fortune teller.

And **still lose all your money.**

How? Bad risk management. One over-leveraged trade. One "I'll just hold through it" disaster. One time you turned off the stop-loss because you were "sure" it would come back.

This section is about making sure that never happens.

---

## Layer 1: Position Sizing (The "How Much" Problem)

The bot doesn't just buy a random number of shares. It calculates position size based on:

1. **Account Balance** — How much total capital you have
2. **Risk Per Trade** — The percentage of capital you're willing to lose on ONE trade (default: 1-2%)
3. **Stop-Loss Distance** — How far away the stop is (in ATR or pips)

The formula is beautiful in its simplicity:

```
Position Size = (Account Balance × Risk %) ÷ Stop-Loss Distance
```

**Example:**
*   Account: $10,000
*   Risk per trade: 1% ($100)
*   Stop-loss: 30 pips
*   Position size: $100 ÷ 30 pips = 3,333 units

That means if you're wrong and the stop hits, you lose exactly $100. Not $500. Not $2,000. **Exactly $100.** That's 1% of your account. You can be wrong 20 times in a row and still have 80% of your capital left.

> 📺 **In the UI:** Settings → **Strategy Workshop** → **Global Risk** sub-tab → **Default Risk %** slider

---

## Layer 2: Leverage Sentry (The "Don't Be a Hero" Guard)

Leverage is the most dangerous tool in trading. It multiplies your gains AND your losses. 10x leverage means a 5% move against you wipes out half your account.

The Leverage Sentry enforces a **hard cap** on total leverage:

| Setting | Default | What It Does |
|---------|---------|-------------|
| `max_leverage` | 10.0 | Maximum total leverage across all positions |
| `leverage_per_position` | 3.0 | Maximum leverage for any single position |

If adding a new trade would push you over the cap, the trade is **blocked.** No exceptions. No "just this once." No override button. (Okay, there's an override in the config, but if you use it, you deserve what happens.)

> 📺 **In the UI:** Settings → **Safety & Shields** → **Max Concurrent Positions** (controls how many positions can be open at once)

---

## Layer 3: Daily Loss Limit (The "Circuit Breaker")

This is the nuclear option. If your losses for the day exceed a threshold, **all trading stops.** Every strategy is muted. Every entry signal is blocked. The bot sits on its hands until the next trading session.

```yaml
daily_loss_limit: 3.0    # Percent of account balance
```

> 📺 **In the UI:** Settings → **Strategy Workshop** → **Global Risk** sub-tab → **Daily Loss Limit** slider
>
> Also: Settings → **Safety & Shields** → **Drawdown Breaker** toggle (5% daily cap circuit breaker)

If you started today with $10,000 and lost $300, that's 3%. The kill switch fires. You're done for the day.

**Why this matters:**
*   Bad days happen. The market gaps against you. Your strategy catches a choppy stretch. Three stops in a row.
*   Without a daily loss limit, the temptation is to "trade your way back." This is called **revenge trading** and it's how 90% of retail accounts blow up.
*   The bot removes the temptation entirely. Loss limit hit? Go outside. Touch grass. Come back tomorrow.

---

## Layer 4: ICC Gatekeeper (The "Prove It" Guard)

Every trade must pass the ICC structure score threshold. This is the bot's version of "show me the money" — except it's "show me the structure."

*   **Score below threshold?** STAND ASIDE. The setup isn't clean enough.
*   **Score above threshold?** ENTRY is allowed. The structure supports the trade.

This prevents the bot from taking garbage setups in choppy markets. Even if the strategy says "go," the ICC Gatekeeper can say "not clean enough."

---

## Layer 5: Position Lock (The "One at a Time" Rule)

You cannot have two positions on the same symbol. Period.

*   **Long on EURUSD?** No more EURUSD trades until the long is closed.
*   **Strategy says go short?** Blocked. Close the long first.
*   **But what about hedging?** This bot doesn't hedge. Hedging against yourself is just paying the spread twice for the privilege of confusion.

Position Lock prevents the single most destructive behavior in retail trading: **position whiplash.** Open long, close long, open short, close short, open long again — each time paying spreads and fees. Death by a thousand cuts.

---

## Layer 6: ATR Armor (The "Smart Stops" System)

Stop-losses aren't placed at random levels. They're calculated using **Average True Range (ATR)** — a measure of how much a symbol typically moves in one period.

| Setting | What It Does |
|---------|-------------|
| `atr_multiplier` | How many ATR units away to place the stop (default: 1.5-2.0) |
| `atr_period` | How many candles to look back for ATR calculation (default: 14) |

> 📺 **In the UI:** Settings → **Safety & Shields** → **ATR Armor** toggle + **Stop ATR Multiplier** field

**Why ATR?**
*   A 30-pip stop on EUR/USD (which moves ~80 pips/day) makes sense.
*   A 30-pip stop on GBP/JPY (which moves ~200 pips/day) is suicide.
*   ATR automatically adjusts. Volatile symbol? Wider stop. Calm symbol? Tighter stop.

---

## The Shield Wall in Action

Here's what happens when a strategy wants to trade:

```
Strategy: "I want to BUY EURUSD"
   ↓
Position Lock: "Any existing position?" → No → PASS
   ↓
Leverage Sentry: "Current leverage 2.1x, cap 10x?" → Under cap → PASS
   ↓
ICC Gatekeeper: "Structure score 78.2, threshold 60?" → Above → PASS
   ↓
Affordability: "Can we afford 10,000 units?" → Yes → PASS
   ↓
Daily Loss Limit: "Today's loss 0.8%, limit 3%?" → Under limit → PASS
   ↓
✅ TRADE EXECUTES
```

**Every single guard** must pass. If ANY one fails, the trade is blocked and the exact reason is logged. No ambiguity. No "the bot just didn't trade and I don't know why." The logs tell you exactly which guard said no and why.

---

## The Golden Rule

Risk management isn't about avoiding losses. **Losses are inevitable.** Risk management is about making sure no single loss — or even a bad string of losses — can knock you out of the game.

The goal is to still be trading next month. And the month after that. And the year after that. Compound interest doesn't work if you're wiped out by February.

*Survive first. Profit second.*
