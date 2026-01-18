
# 2. The Skeleton (Architecture)
> *"It's alive! mostly."*

This document explains the **anatomy** of the application. If `01_PHILOSOPHY.md` was the soul, this is the bones.

## The Loop (`runtime/loop.py`)
This is the heartbeat.
1.  **Wake Up:** It starts, reads the `settings_profiles.yaml`, and picks a profile (e.g., `crypto_247`).
2.  **Cycle:** Every X seconds (defined in profile), it screams "NEXT CYCLE!"
3.  **Scan:** It iterates through every symbol in your list.
    *   "Hey Market, what's BTC doing?"
    *   "Hey Strategy, do we like BTC?"
    *   "Hey Broker, buy BTC is Strategy said yes."
4.  **Sleep:** It naps until the next cycle.

**Key Files:**
*   `src/tradebot_sci/main.py`: The entry point.
*   `src/tradebot_sci/runtime/loop.py`: The infinite `while True` loop.

## The Brain (`strategy/engine.py`)
This is where the magic (or hallucination) happens.
*   **Inputs:** A `MarketSnapshot` (Candles + Trend).
*   **Logic:**
    1.  **Filter:** Is the trend up? Is volatility okay?
    2.  **Gate:** Did we sweep liquidity? (`_detect_sweep`). Did we break structure? (`_detect_continuation`).
    3.  **Score:** Assign a GPA (0.0 to 1.0). If Score > Threshold (e.g. 0.6), it's a "Go".
*   **Output:** An `AITradeDecision` (Buy/Sell/Hold/StandAside).

**Key Files:**
*   `src/tradebot_sci/strategy/engine.py`: The decision logic.
*   `src/tradebot_sci/strategy/profiles.py`: Different personalities (Scalper vs Swinger).

## The Hands (`broker/ccxt_broker.py`)
The executioner. It talks to the Exchange via API.
*   **responsibilities:**
    *   **Translation:** Converts "Buy BTC" to "limit order side=buy amount=0.1".
    *   **Protection:** "Wait, do we have money?" (The `Affordability Check`).
    *   **Feedback:** "Order filled. ID: 12345." OR "Order failed. Access Denied."
*   **The Kill Switch:** The Hands keep a tally of failures (`_consecutive_errors`). If it gets too high, it effectively handcuffs itself and refuses to trade until a human restarts it.

**Key Files:**
*   `src/tradebot_sci/broker/ccxt_broker.py`: The CCXT (Crypto) implementation. Supports Coinbase, Kraken, Gemini, Binance, etc.
*   `src/tradebot_sci/broker/ibkr_broker.py`: The Interactive Brokers implementation (if you're fancy).

## The Eyes (`market/providers.py`)
The humble observer.
*   **Responsibilities:**
    *   Fetches current Price, Bid/Ask, and Historical Candles.
    *   Packages them into a nice, immutable `MarketSnapshot`.
    *   Doesn't judge. Just reports.

**Key Files:**
*   `src/tradebot_sci/market/providers.py`: Connects to Data APIs.
*   `src/tradebot_sci/market/models.py`: Definitions of `Candle`, `Ticker`, etc.
