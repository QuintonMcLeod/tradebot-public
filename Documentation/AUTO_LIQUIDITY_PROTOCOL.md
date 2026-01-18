# Auto-Liquidity Protocol: Autonomous Capital Reserve Management

**Version:** 1.0.0 (Implemented Jan 2026)
**Component:** `CCXTExchangeBroker` (`src/tradebot_sci/broker/ccxt_broker.py`)

## 1. Problem Statement
The trading bot uses **USD** as the primary quote currency for all trades (e.g., `BTC-USD`) to leverage the deepest liquidity pools on Coinbase Advanced Trade.

However, trading is blocked if:
*   **USD Balance** drops below the exchange minimum order size (~$1.00).
*   **Capital is Fragmented**: The user holds significant value in **USDT** (Tether), but the bot cannot access it because it is configured for USD-only execution.

This results in a state where the account is "Under-Funded" despite having assets, causing `PREVIEW_INVALID_QUOTE_SIZE_TOO_SMALL` errors.

## 2. Solution: Auto-Liquidity Injection
We implemented a self-healing mechanism that detects capital exhaustion and automatically converts reserve stablecoins (USDT) into primary trading capital (USD).

### Logic Flow (`execute_decision`)
1.  **Guard Check**: Before placing an order, the system calculates the position size based on available USD.
2.  **Detection**: If `calculated_size_usd < MIN_ORDER_VAL` ($1.10), the **Auto-Liquidity Trigger** fires.
3.  **Reserve Check**: The trigger checks `fetch_balance()` for `USDT`.
    *   *Threshold*: Must have > $5.00 USDT to justify conversion.
4.  **Execution**:
    *   Bot places a **Market Sell** order for the `USDT/USD` pair on Coinbase Advanced Trade.
    *   *Note*: This uses the liquid spot market (0.001% fee), not the "Convert" feature (spread fee).
5.  **Recursion**: Upon successful conversion, the bot **immediately recurses** calling `execute_decision()`.
    *   The second attempt finds fresh USD capital and executes the original alpha signal successfully.

## 3. Benefits
*   **Zero-Touch Funding**: The user can deposit USDT, and the bot will "eat" it as needed to fund trades.
*   **Capital Efficiency**: Consolidates fragmented stablecoins into a single deep-liquidity pool (USD).
*   **Crash Prevention**: Prevents API errors by resolving the low-balance condition locally.

## 4. Code Reference
```python
# src/tradebot_sci/broker/ccxt_broker.py

def _attempt_auto_liquidation_usdt(self, required_usd: float) -> bool:
    """Attempts to sell USDT for USD if capital is critical."""
    # ... logic to fetch balance and create market sell order ...
```
