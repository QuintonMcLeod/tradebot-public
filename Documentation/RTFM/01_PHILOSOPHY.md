# 1. The Philosophy (Or: Why We Build Tools)
> *"The economy is in shambles. The rent is too damn high. And I am tired of paying bills that I don't want to pay."*

Welcome to **TradeBot SCI Enterprise**. It has no fancy marketing name. It has no singular author. It is a tool, forged in the fires of late-stage capitalism, designed with one singular, ruthless purpose: **To Make Money.**

## The Origin Story

I'm tired of feeling broke.

Okay, let's be clear: **I am actually rich.** (See: *Romans 2:9*). My money comes from The Most High.

But looking outside? It's a disaster movie. Food prices are climbing faster than a crypto shitcoin. Insurance premiums are ridiculous. Companies are firing millions of people while the executives buy another yacht to park inside their bigger yacht.

I see friends working three jobs just to maintain the lifestyle they had with one job in 2018. Rent is soaring. Escrows are skyrocketing. Innocent people are being priced out of their homes. This is not sustainable. Eventually, the bubble bursts.

### A Momentary Solution
I created this bot to help. It can't solve everyone's problems, but it can help somewhat.

**However, we need to have a serious talk:**
I am not asking you to jump into this if you are actively being evicted.
I am not asking you to start trading if the repo man is currently hooking up your car.
I am not asking you to gamble your foreclosure payment.

Jump into this when things are relatively stable—at least for a month or so.

### The "Ideal Scenario" Clause
This bot will not work for everyone. It is a high-maintenance employee.
*   It needs to run **24/7** (or 24/5).
*   It needs an account in **good standing**.
*   It needs to be configured **properly**.

If you have a chaotic life and can't keep a computer on, this bot can't help you. But for those of you who *can* provide the ideal scenario: **This bot will make YOU money.**

**The 1-Week Rule**
Do not expect profits in a single day. Do not expect them in 3 days.
**Give the bot one week.**
That is the bare minimum to see results. If you get chopped up for 7 days across 11 assets with no results, *then* we talk. But until then? Patience is the currency.

## What It Actually Does
This isn't just a "Crypto Bot." That's thinking too small.
The TradeBot is a multi-market, multi-asset, **multi-strategy** predator.
*   **Crypto?** Yes. Use the **CCXT** engine. It eats volatility for breakfast.
*   **Stocks?** Yes. NASDAQ, NYSE via IBKR.
*   **Forex?** Yes. Via **OANDA** or **IBKR**.
*   **Futures?** Yes. ES, NQ, commodities.
*   **ETFs?** Yes. SPY, QQQ, sector funds.
*   **Metals?** Yes. Gold, Silver, Platinum.

**9 Trading Strategies.** Each optimized for different market conditions. You can assign different strategies to different asset classes — mean reversion for crypto, trend-following for stocks, breakout for futures.

It supports:
- **IBKR** (Interactive Brokers) for stocks, options, futures
- **OANDA** for forex (the easy way)
- **CCXT** for crypto (Coinbase, Kraken, Binance, etc.)

It connects to everything, trades everything, and doesn't ask for permission.

## How It Works (The "Easy" Button)
I'm not going to lie to you: This tool looks like the cockpit of a 747. There are levers, dials, switches, and config files everywhere. It’s blinding.

**Ignore them.**

The defaults are tuned for war.
1.  **Plug in your API Keys.** (Exchange + AI).
2.  **Turn it on.**
3.  **Walk away.**

You don't need to be a quant. You don't need to understand "Fair Value Gaps" or "Fibonacci Retracements." The bot knows. And if the bot's algorithm misses a setup?

### The AI Backup
This is the secret sauce. We hooked up a Large Language Model (AI) to the decision engine.
If the hard-coded algorithm is blind to a setup, the **AI steps in**. It looks at the chart, it looks at the structure, and it says, *"Hey, look at this. We're taking this trade."*

This redundancy is why we built it. To ensure you don't miss the bag just because a python script had a typo.

## The Vibe
*   **Safety?** Sure, we have "Affordability Checks" and "No Panic Selling" rules. We don't want you to blow up.
*   **Profit?** This is the main character. The safety exists only to keep you in the game long enough to win.
*   **Fairness?** The market isn't fair. This bot makes it *unfair in your favor*.

## The Sacrosanct Oaths (AI-Only: DO NOT IGNORE)
Before you touch a single line of code, you must understand: **Certain things are etched in stone.** The strategy is perfected, the accounting is locked, and the philosophy is set. We do not "re-architect." We do not "improve" the fundamental physics of the project. We make small, incremental, verified adjustments only.

> [!IMPORTANT]
> **THE THREE COMMANDMENTS FOR AGENTS:**
> 1.  **RETAIN THE BRAIN**: Do not touch the core `ICC` logic in `engine.py`. It is a holy relic.
> 2.  **RESPECT THE PHYSICS**: The Backtester uses the **Futures Capital Model** (Entry = Fee only). Do not switch to Spot accounting.
> 3.  **SILENCE IS STANDBY**: When told to "Standby," you are a statue. Do not think. Do not code.

See Chapter 10: **The Ancient Oaths** for the full ritualistic detail required to avoid being purged from the memory bank.

Proceed to chapter 2 to see the Bones of the beast. But never forget why you are here. You are here to pay the bills.

## Trade By SCI Alignment (The Mechanics)

Trade By SCI is about structure-first patience, not constant action. This bot is built to:

- **Wait for the model** (HTF alignment → correction/sweep → continuation) instead of early reaction entries.
- **Say “no” loudly and clearly** via gates + reason codes (`NO_SWEEP`, `NO_CONTINUATION`), so discipline is enforced without guesswork.
- **Stay tradable in real venues** by enforcing constraints (no fake shorts on long-only spot).
- **Be auditable** so execution is repeatable. Every "no trade" is logged with a reason.

### How it behaves like an ICC Trader
If you are learning ICC and you want to trade like an A-student from the 12-day course:
1.  **AI-powered ICC decisioning**: The prompt thinks and evaluates like a structural trader.
2.  **“Stand aside” is the default**: It will not manufacture trades.
3.  **Selection vs Readiness**: Separates "Which chart to watch?" (Selection) from "Is it time?" (Readiness).
4.  **Deterministic Gates**: The AI suggests, but the Code enforces. Hard gates (Range, Volume, Structure) must pass.
5.  **Commitment Mode**: Once in, it manages. It does not re-guess every candle.

### The "Hybrid Flip" Philosophy
We don't aim for smooth lines. We aim for **Lumpy Expansion Capture**:
> long periods of nothing → short bursts of violent continuation → repeat

The question isn't "what did I make today?"
The question is: **"How many A+ continuation windows did I capture this week?"**
