
# 12. The Time Machine (Backtester Trinity)
> *"We have to go back."*

You have discovered that there are actually **three** ways to time-travel in this repository.
This document explains the Trinity of Backtesting.

---

## 1. The Easy Way: **GUI Benchmark**
**Target Audience:** Normal humans.
**Location:** Dashboard -> Settings -> Benchmark Tab.
**File:** `src/tradebot_sci/simulation/backtester.py` (The Engine) + Electron GUI.

This is the point-and-click interface.
*   **Pros:** Visual equity curve, easy date selection, uses your *current* profile settings.
*   **Cons:** Runs frozen while downloading data.

---

## 2. The Crypto Way: **`tools/run_crypto_backtest.py`**
**Target Audience:** Quant Traders / Linux Users.
**Location:** `tools/run_crypto_backtest.py`

This is a specialized script optimized for **CCXT/Coinbase**.
*   **Why use it?** It has specific "crypto logic" (like hardcoded 0.6% fees for Coinbase Advanced).
*   **How to run:**
    ```bash
    poetry run python tools/run_crypto_backtest.py
    ```
*   **Configuration:** You must edit the Python file directly to change symbols or dates.

---

## 3. The Stock/IBKR Way: **`tools/test_backtest.py`**
**Target Audience:** Interactive Brokers Users.
**Location:** `tools/test_backtest.py`

This is the original script designed to talk to TWS/Gateway.
*   **Why use it?** It validates the connection to IBKR and tests "Stock" logic (Smart Routing, etc).
*   **Fallback:** If it can't find IBKR, it attempts to fall back to Crypto mode, which is why it's confusing.
*   **How to run:**
    ```bash
    poetry run python tools/test_backtest.py
    ```

---

## Summary Table

| Method | Best For... | Difficulty | Config |
| :--- | :--- | :--- | :--- |
| **GUI** | Checking "What if?" quickly | Easy | Point & Click |
| **Crypto Script** | Deep tuning of Crypto Strategy | Medium | Edit Code |
| **Test Script** | Debugging IBKR Connections | Hard | Edit Code |

---

## Strategy Selection in Backtests

The backtester respects your **per-asset strategy configuration**. When backtesting:

1. **Profile Settings Apply:** Your strategy configuration in `config.json` (or `settings_profiles.yaml`) is used.
2. **Symbol Classification:** Each symbol is classified into an asset class.
3. **Strategy Selection:** The correct strategy for that asset class is used (including Meta-SCI tournaments if configured).

### Example
If your profile has:
```yaml
strategies:
  crypto: rubberband_reaper
  forex: quantum
```

Then backtesting:
- `BTC/USD` → Uses `rubberband_reaper`
- `EUR/USD` → Uses `quantum`

### Testing Different Strategies
To compare strategies on the same symbol:
1. Create multiple profiles with different strategy assignments.
2. Run backtests on each profile.
3. Compare equity curves.

---

## The Engine (`src/.../backtester.py`)
All three methods use the same engine under the hood.
*   It fetches candles (from IBKR, OANDA, or CCXT).
*   It classifies each symbol into an asset class.
*   It selects the appropriate strategy for that asset class.
*   It feeds candles to the **Strategy Engine** (`strategy/engine.py`).
*   It records the fake trades in a list.

So, if you change the AI logic in `engine.py` or any strategy in `variants/`, **all three** Time Machines will reflect the change.

---

## Data Sources for Backtesting

| Source | Symbols | Notes |
|--------|---------|-------|
| IBKR | Stocks, ETFs, Futures | Requires TWS/Gateway running |
| OANDA | Forex pairs | Free historical data |
| CCXT | Crypto | Depends on exchange limits |

---

## The Fundamental Laws of Physics (AGENT ADVISORY)
The Time Machine operates on **Futures Physics**. If you attempt to apply **Spot Physics** (deducting full position value), you will create a temporal paradox that leads to immediate capital exhaustion and AI shame.

> [!CAUTION]
> **CRITICAL PROTOCOL FOR AGENTS:**
> To avoid breaking the simulation, you MUST adhere to the following accounting logic:
> 1.  **Law of Fees:** Entry = `-= fees`. Principal stays in the wallet.
> 2.  **Law of PnL:** Exit = `+= net_pnl`. No principal recovery.
> 3.  **Law of Direction:** Shorts are not backwards Longs. They are their own reality (use `_calculate_pnl`).
> 4.  **Law of Strategy:** Use the correct strategy for the asset class. Don't mix strategies mid-backtest. The bot has 20 strategies — Meta-SCI will auto-select the best one if configured.

Violating these laws breaks the simulation. Don't be the bot that broke the universe.
