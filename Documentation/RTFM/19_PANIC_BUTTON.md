---
title: "Something Is Wrong \u2014 The Emergency Panic Protocol"
category: rtfm
icon: emergency
description: "\"Something is wrong. Make it stop.\" So the bot is screaming in red\
  \ text, or worse \u2014 it's doing nothing at all. Don't panic. Read this. Covers\
  \ every emergency scenario: Kill Switch activation, insufficient funds, broker disconnects,\
  \ stuck positions, API rate limits, and the nuclear option \u2014 how to flatten\
  \ everything and shut down safely."
size: md
---

# 6. The Panic Button — Troubleshooting Guide

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"Something is wrong. Make it stop. MAKE IT STOP."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Look at you. You're a grown adult, hyperventilating because a computer program printed some red text. Pull yourself together! The bot is either screaming at you, or worse, doing absolutely nothing and making you sit with your own thoughts. Both are terrifying when you don't know what you're doing. But don't panic. That's why I wrote this chapter.<br><br>Every error in here? I've seen it. I've stared at it at 2 AM looking like a complete idiot before I figured it out. So shut up, sit down, and read."</td></tr></table>

---

## 1. "Kill Switch Activated"

**Symptom:** `[KILL SWITCH] Too many consecutive errors. Shutting down.`

<table><tr><td width="170"><img src="img/bot.png" width="150"></td><td><b>THE BOT</b>:<br><em>"I tried 5 times in a row and failed every time. I shut myself down to save your API quota and your sanity. I am not going to keep banging my head against a wall. That's YOUR job."</em></td></tr></table>

**Fix:**
1. **Read the error above the Kill Switch.** The Kill Switch is the symptom. The cause is always the line before it.
    - `Insufficient Funds`? You are broke. (See section 2.)
    - `Permission Denied`? Your API key doesn't have the permissions it needs.
    - `Timeout`? The internet is bad. Or the broker's API is having a moment.
2. **Reset:** `./scripts/tradebot.sh --restart`.

---

## 2. "Insufficient Funds" / "Affordability Block"

**Symptom:** `[CCXT] AFFORDABILITY BLOCK: Required $50 > Free $3.50`

<table><tr><td width="170"><img src="img/bear.png" width="150"></td><td><b>BEAR</b>:<br>"You. Ran. Out. Of. Money. <em>Shocking.</em>"</td></tr></table>

**Cause:**
- **Futures:** Some brokers (notably Coinbase) require USDC/USD in the **Spot Wallet** to collateralize futures, ignoring the Futures wallet balance.
- **Spot:** You ran out of money. There's no polite way to say it.
- **Rounding:** Contract size is 1.0 but you only have money for 0.8. The bot can't buy 80% of a future.

**Fix:**
- Add funds.
- Move funds to Spot wallet.
- Trade a cheaper asset (DOGE instead of BTC).

---

## 3. "Risk Suppressed"

**Symptom:** `[GUARD] Risk Suppressed: buying power $100 < required $150`

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"The bot <em>could</em> technically afford it, but the Risk Manager said 'No.' You may have hit your max_daily_loss, or you have too many open positions already. The bot is protecting you from over-committing. This is a feature, not a bug."</td></tr></table>

**Fix:**
- Check your profile settings. Raise `max_exposure_pct` if you feel comfortable.
- Review the Leverage Sentry cap in Settings → Safety & Shields.

---

## 4. "It's Not Trading!" (The Silent Treatment)

**Symptom:** The bot is running, scanning, but never entering.

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"WHY WON'T IT DO SOMETHING?! It's just sitting there! Looking at charts! DOING NOTHING!"</td></tr></table>

<table><tr><td width="170"><img src="img/monk.png" width="150"></td><td><b>MONK</b>:<br><em>"Patience. Silence is not failure — it is discipline. The absence of a trade IS a decision. And often the best one."</em></td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Monk is right, but since you don't speak incense and yoga mats, let me translate: THE MARKET IS TRASH TODAY. Would you walk into a hurricane just to say you went outside? No! So why are you mad the bot isn't trading in garbage conditions? <br><br>But fine. If you absolutely MUST know why it's not trading, go through this checklist. IN ORDER. Before you come crying to me that it's broken."</td></tr></table>

**Cause Checklist:**
- **Position Lock:** Already an open position for that symbol? Lock blocks ALL new entries.
- **Leverage Sentry:** Total leverage over the cap? Check for `[SAFETY] Entry Blocked: Leverage Sentry`.
- **The Market Sucks:** If score is 45.0 and threshold is 55.0, the bot is protecting you from chop. That's its JOB.
- **Meta-SCI Tournament:** Check for `[META-SCI] Tournament: No qualifying signals found`. This means every strategy looked at the market and said "nah."
- **Sabbath Mode:** Is it Friday evening? The bot might be resting. As it should be.
- **Balance:** See "Insufficient Funds" above.
- **Wrong Strategy:** The assigned strategy might not fire in current conditions.

**Fix:**
- Check logs for `[POSITION LOCK]` — if locked, wait for position to close or restart.
- Check for `[SAFETY]` entries — these show exactly which guard blocked the trade.
- Check `[SELECT]` logs — if it sees candidates but scores them low, be patient.
- Check `[META-SCI]` logs to see tournament results.
- If it sees *nothing*, check your `symbols` list. You probably forgot to add symbols.

---

## 5. IBKR-Specific Issues

### "Connection Refused"
**Symptom:** `[IBKR] Connection Refused: 127.0.0.1:7497`

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"TWS or IB Gateway isn't running. Or you're on the wrong port. 7497 is for Paper. 7496 is for Live. You didn't enable the API in the settings, did you? Be honest. You skipped that step because reading is hard. Go back and turn it on."</td></tr></table>

### "Client ID in Use"
**Symptom:** `[IBKR] Client ID 1 already in use`
**Fix:** Change `IBKR_CLIENT_ID` to a different number (2, 3, etc.). Another instance is hogging it.

---

## 6. OANDA-Specific Issues

### "Invalid Account ID"
**Symptom:** `[OANDA] Invalid Account ID`
**Fix:** Use format `101-001-1234567-001` (with dashes). People always forget the dashes.

### "Unauthorized"
**Symptom:** `[OANDA] 401 Unauthorized`

<table><tr><td width="170"><img src="img/ninja.png" width="150"></td><td><b>NINJA</b>:<br><em>"Your credentials are compromised or expired. Generate new ones. Immediately. Not tomorrow. Not after lunch. Now."</em></td></tr></table>

**Fix:**
1. Go to [OANDA Hub](https://hub.oanda.com)
2. Manage API Access → Generate new token
3. Update `OANDA_API_KEY` in settings

### "Market Halted"
**Symptom:** `[OANDA] Market is halted for EUR_USD`
**Fix:** Forex markets are closed (weekend or holiday). Sunday 5 PM ET to Friday 5 PM ET.

### "Insufficient Margin"
**Symptom:** `[OANDA] Insufficient margin for 10000 EUR_USD`
**Fix:** Add funds or reduce `risk_per_trade_pct`.

---

## 7. CCXT/Crypto-Specific Issues

### "Rate Limit Exceeded"
**Symptom:** `[CCXT] Rate limit exceeded`
**Fix:** Increase `market_poll_interval_seconds` in your profile. You're hitting the exchange too often.

### "Symbol Not Found"
**Symptom:** `[CCXT] Symbol BTCUSD not found`
**Fix:** Use `BTC/USD` or `BTC/USDT`. Check `CCXT_SYMBOL_MAP` for the exchange-specific format.

---

## 8. EMERGENCY STOP (How to Kill It)

<table><tr><td width="170"><img src="img/pirate.png" width="150"></td><td><b>PIRATE</b>:<br>"SKYNET SCENARIO! THE BOT'S GONE ROGUE! 🏴‍☠️"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Rogue? Are you out of your mind? It's a Python script, not the Terminator! It's doing EXACTLY what your goofy settings told it to do. If it's doing something stupid, it's because YOU gave it stupid instructions. <br><br>But if you absolutely need to rip the steering wheel off, here are your three options:"</td></tr></table>

1. **Ctrl+C** in the terminal.
2. **`./scripts/tradebot.sh --exit-all`** (The Nuclear Option).
3. **Log into your broker** (Coinbase, Kraken, IBKR, OANDA, etc.) and manually close positions.

> **Important:** Killing the bot does NOT automatically sell your positions. It just stops the bot from making NEW decisions. Your existing positions are still open on the exchange. Log into your broker to manage them.

> **Also important:** If you manually close a position, the bot's Position Lock won't know. Restart the bot to clear it.

---

## 9. "NO BROKER CONFIGURED" (Preflight Failure)

**Symptom:** Big error box: `❌ NO BROKER CONFIGURED — CANNOT START`

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"Honey, you forgot to set up your broker keys. You can't trade without an account. That's like trying to drive without a car."</td></tr></table>

**Fix:**
1. Open the GUI: `./scripts/tradebot.sh --gui`
2. Settings → **Brokers** tab
3. Enter API credentials for at least ONE broker
4. Save and restart

See Chapter 8 (**API Setup**) for step-by-step broker setup.

---

## Quick Diagnostic Checklist

| Issue | Check |
|-------|-------|
| No trades | Logs for `[SELECT]` score, `[POSITION LOCK]`, `[SAFETY]` |
| No trades (Meta-SCI) | Logs for `[META-SCI] Tournament` results |
| Position Lock blocking | Open position exists? Wait for SL/TP or restart bot |
| Leverage Sentry blocking | Total leverage over cap? Reduce positions or raise cap |
| Connection error | Broker running? Port correct? API enabled? |
| Insufficient funds | Balance in correct wallet? Margin requirements? |
| Wrong strategy | Profile has correct strategy assignment? |
| API errors | Key/secret correct? Not expired? Has trade permissions? |
| Won't start | No broker configured? See Preflight Check above |

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"If you've gone through this entire chapter and you're STILL confused, check the logs again. The answer is always in the logs. Always. I didn't write 500 different highly specific log messages just so you could ignore them and text me 'bot broke.' Read the damn screen. Stop playing with me."</td></tr></table>

---

## 📖 Continue Reading

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"Wow, okay I think I get it now. What's next?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Turn the page. We are going to talk about <b>Skeleton Arch</b>. Try to keep up."</td></tr></table>
