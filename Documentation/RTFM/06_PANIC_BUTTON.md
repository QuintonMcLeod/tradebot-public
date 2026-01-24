
# 6. The Panic Button (Troubleshooting)
> *"Something is wrong. Make it stop."*

So, the bot is screaming in red text, or worse—it's doing nothing at all.
Don't panic. Read this.

---

## 1. "Kill Switch Activated"
**Symptom:** The logs say `[KILL SWITCH] Too many consecutive errors. Shutting down.`
**Cause:** The bot tried to do something 5 times in a row and failed every time. It shut itself down to save your API quota and your sanity.
**Fix:**
1.  **Read the error above the Kill Switch.**
    *   `Insufficient Funds`? You are broke. (See section 2).
    *   `Permission Denied`? Your API key assumes you can trade Futures, but the Exchange disagrees.
    *   `Timeout`? The internet is bad.
2.  **Reset:** Run `./scripts/tradebot.sh --restart`.

---

## 2. "Insufficient Funds" / "Affordability Block"
**Symptom:** `[CCXT] AFFORDABILITY BLOCK: Required $50 > Free $3.50`
**Cause:**
*   **Futures:** Some brokers (notably Coinbase) require USDC/USD in the **Spot Wallet** to collateralize futures, ignoring the Futures wallet balance.
*   **Spot:** You ran out of money.
*   **Rounding:** The contract size is 1.0, but you only have money for 0.8. The bot cannot buy 0.8 of a Future.
**Fix:**
*   Add funds.
*   Move funds to Spot.
*   Trade a cheaper asset (DOGE instead of BTC).

---

## 3. "Risk Suppressed"
**Symptom:** `[GUARD] Risk Suppressed: buying power $100 < required $150`
**Cause:** The bot *could* afford it, but the **Risk Manager** said "No."
*   Maybe you hit your `max_daily_loss`?
*   Maybe you have too many open positions?
**Fix:**
*   Check `config/settings_profiles.yaml`. Raise `max_exposure_pct` if you feel lucky.

---

## 4. "It's Not Trading!" (The Silent Treatment)
**Symptom:** The bot is running, scanning, but never entering.
**Cause:**
*   **The Market Sucks:** If the `selection_score` is 45.0 and your threshold is 60.0, the bot is doing its job. It is saving you from losing money in chop.
*   **Sabbath Mode:** Is it Friday night? The bot might be resting.
*   **Balance:** See "Insufficient Funds".
*   **Wrong Strategy:** The assigned strategy for that asset class might not be firing in current conditions.
**Fix:**
*   Check the logs for `[SELECT]`. If it sees candidates but scores them low, be patient.
*   If it sees *nothing*, check your `symbols` list.
*   Check `[STRATEGY]` logs to confirm the right strategy is being used.

---

## 5. IBKR-Specific Issues

### "Connection Refused"
**Symptom:** `[IBKR] Connection Refused: 127.0.0.1:7497`
**Cause:** TWS or IB Gateway isn't running, or wrong port.
**Fix:**
*   Start TWS or IB Gateway.
*   Check port: 7497 = Paper, 7496 = Live.
*   Verify API is enabled in TWS settings.

### "Client ID in Use"
**Symptom:** `[IBKR] Client ID 1 already in use`
**Cause:** Another instance or script is connected with the same ID.
**Fix:** Change `IBKR_CLIENT_ID` to a different number (2, 3, etc.).

---

## 6. OANDA-Specific Issues

### "Invalid Account ID"
**Symptom:** `[OANDA] Invalid Account ID`
**Cause:** Account ID format is wrong.
**Fix:** Use format `101-001-1234567-001` (with dashes).

### "Unauthorized"
**Symptom:** `[OANDA] 401 Unauthorized`
**Cause:** API token is wrong, expired, or revoked.
**Fix:**
1.  Go to [OANDA Hub](https://hub.oanda.com)
2.  Navigate to Manage API Access
3.  Generate a new token
4.  Update `OANDA_API_KEY` in settings

### "Market Halted"
**Symptom:** `[OANDA] Market is halted for EUR_USD`
**Cause:** Forex markets are closed (weekend or holiday).
**Fix:** Wait for markets to reopen. Forex trades Sunday 5 PM ET to Friday 5 PM ET.

### "Insufficient Margin"
**Symptom:** `[OANDA] Insufficient margin for 10000 EUR_USD`
**Cause:** Not enough funds for the position size + margin requirement.
**Fix:** Add funds or reduce position size via `risk_per_trade_pct`.

---

## 7. CCXT/Crypto-Specific Issues

### "Rate Limit Exceeded"
**Symptom:** `[CCXT] Rate limit exceeded`
**Cause:** Too many API calls too fast.
**Fix:** Increase `market_poll_interval_seconds` in your profile.

### "Symbol Not Found"
**Symptom:** `[CCXT] Symbol BTCUSD not found`
**Cause:** Wrong symbol format for the exchange.
**Fix:** Check `CCXT_SYMBOL_MAP`. Use format like `BTC/USD` or `BTC/USDT`.

---

## 8. EMERGENCY STOP (How to Kill It)
If the bot goes rogue (Skynet scenario):
1.  **Ctrl+C** in the terminal.
2.  **`./scripts/tradebot.sh --exit-all`** (The Nuclear Option).
3.  **Log into your Broker (Coinbase, Kraken, IBKR, OANDA, etc.)** and manually close positions.
    *   *Note:* Killing the bot does **not** automatically sell your bags. It just stops the bot from buying more.

---

## Quick Diagnostic Checklist

| Issue | Check |
|-------|-------|
| No trades | Logs for `[SELECT]` score, strategy assigned |
| Connection error | Broker running? Port correct? API enabled? |
| Insufficient funds | Balance in correct wallet? Margin requirements? |
| Wrong strategy | Profile has `strategies:` block with correct assignments? |
| API errors | Key/secret correct? Not expired? Has trade permissions? |
