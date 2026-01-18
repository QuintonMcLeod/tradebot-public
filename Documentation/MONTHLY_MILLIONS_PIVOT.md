# TradeBot SCI: "Monthly Millions" Architecture (Coinbase Futures Pivot)

## Overview
This document outlines the architectural pivot from Spot Scalping to **Coinbase Nano Futures (Derivatives)** to enable the user's "Monthly Millions" growth strategy.

**Objective**: Turn small capital ($68 starting) into $1M+ via aggressive compounding.
**Constraint**: USER is US-based (No Binance/Bybit).
**Solution**: **Coinbase Derivatives (Nano Futures)** via Advanced Trade API.

---

## 1. Technical Configuration

### Venue & Broker
- **Exchange**: Coinbase Advanced Trade (via `ccxt` + `coinbase-advanced-py` logic).
- **Broker Mode**: `CCXTExchangeBroker` (Primary).
- **API Key Type**: **Cloud API Key** (CDP Portal).
  - *Critical Fix*: The `.env` loader and `ccxt_broker.py` have been patched to auto-normalize escaped newlines (`\\n` -> `\n`) in PEM-formatted private keys.

### Instrument: Nano Futures
We utilize "Nano" contracts which are 1/10th or 1/100th size, allowing granular sizing for small accounts.
- **Nano Ether**: `ETP-20DEC30-CDE` (1/10th ETH).
- **Nano Bitcoin**: `BIP-20DEC30-CDE` (1/100th BTC).
- **Why 2030 Expiration?**: We chose long-dated contracts (Dec 2030) to simulate "Perpetual" behavior and avoid monthly rollover friction.

### Strategy Profile: `coinbase_futures`
Located in `config/settings_profiles.yaml`.
- **Timeframes**: 5m (Primary), 1h (Confirmation).
- **Execution**: `MARKET` orders (Liquidity on Nanos is sufficient; urgency is priority).
- **Risk Management**:
  - **Risk Per Trade**: 1.5% of Equity.
  - **"3 Bullets" Logic**: With ~$85 margin and minimal capital, the account can survive ~3 consecutive full stop-outs before hitting margin limits.
  - **Max Positions**: 1 (Focus on A+ setups only).

---

## 2. Key Code Modifications

### `src/tradebot_sci/broker/ccxt_broker.py`
- **Secret Normalization**: Added logic in `_build_exchange` to detect and replace `\\n` with `\n` in API secrets. This enables support for Coinbase Cloud PEM keys loaded from `.env`.
- **Symbol Mapping**: `symbol_map` logic isn't strictly needed for `ETP` as we use the raw Product ID, but the broker handles the pass-through.

### `tools/` Scripts
- **`find_nano_with_sdk.py`**: Official SDK script to list available futures products. Used to discover the `20DEC30` product IDs.
- **`simple_portfolio_check.py`**: Diagnostic tool to verify API Key permissions and visibility of the "Futures" portfolio balance.

---

## 3. Operations Manual

### Launching the Bot
```bash
# Ensure .env has CCXT_API_KEY (Cloud) and PROFILE_NAME=coinbase_futures
python3 src/tradebot_sci/main.py
```

### Monitoring
- **Logs**: Check `logs/tradebot.log` for `[CCXT] Broker Connected`.
- **First Trade**: Verify that `amount` is correct (should be integer 1 for Nano contracts).

---

## 4. Future Roadmap
- **Margin Management**: As account grows > $1000, consider switching to `ETH-PERP` (International) if regulatory landscape changes, or scale up Nano contracts.
- **Algo Tuning**: Monitor `icc_entry_score` efficiency on 5m timeframe. Current threshold `60.0` might need adjustment for the higher volatility of Futures.
