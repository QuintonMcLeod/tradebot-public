# Auditor Questions for the Workers
**From:** Antigravity, Incoming Code Auditor  
**Date:** February 18, 2026 · 18:33 EST  
**Re:** Pre-Audit Intake — Core Trading Logic  

---

The UI audit is complete (S+ — congratulations, minus the 3 AM incident). I'm picking up where the previous auditor left off. Before I begin the next phase, I need answers to the following:

---

## 1. Scope Confirmation
Am I correct that the next audit should cover the **strategy engine, scoring, confluence, and broker execution** layers? Or is there a specific subsystem you want me to focus on first?

## 2. Known Issues
Are there any **known bugs or behavioral anomalies** in the trading logic right now? The `CHANGELOG_LAST_24H.md` mentions the `TradingProfileSettings` import was accidentally deleted — are there any other classes or functions that may have been broken or restored recently?

## 3. Live vs. Backtest Discrepancies
The `AI_HANDOFF_PROMPT.md` mentions a known issue where the live bot traded profitably on a Friday but the backtester showed 0 trades. Has this data granularity issue been resolved, or is it still outstanding?

## 4. Active Strategy Variants
There are **20 strategy variants** in `src/tradebot_sci/strategy/variants/`. Which ones are currently **active in production** vs. experimental? I don't want to burn time auditing dead code.

## 5. Test Health
Have the tests in `tests/` been run recently? Do they all pass? Any known flaky tests I should be aware of?

## 6. Backtester Canonical Status
`tools/optimize_strategies.py` uses hardcoded `capital = 870.0` and only runs `RubberbandReaperStrategy`. Is this the **canonical** backtester, or is there a more comprehensive one I should be reviewing?

---

> [!IMPORTANT]
> Please answer **all six questions** before marking this document as reviewed. Write your responses directly below each question or in a separate response document.
