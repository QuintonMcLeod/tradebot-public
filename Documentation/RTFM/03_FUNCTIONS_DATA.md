
# 3. Functions & Datasets
> *"The devil is in the details. And the bugs."*

If you are debugging this thing, you need to know what the data actually looks like.

## The Core Data Objects
These are the data packets passed around like hot potatoes.

### 1. `MarketSnapshot` (`src/tradebot_sci/market/models.py`)
This is the "Source of Truth" for a symbol at a specific time.
```python
@dataclass
class MarketSnapshot:
    symbol: str             # e.g., "BTC/USD"
    timeframe: str          # e.g., "5m"
    candles: List[Candle]   # The raw OHLCV data
    trend_htf: TrendState   # Higher Timeframe Trend (Bullish/Bearish/Neutral)
    trend_ltf: TrendState   # Lower Timeframe Trend
```
*   **Philosophy:** Immutable. Once created, we don't mess with it. It represents "What Happened".

### 2. `AITradeDecision` (`src/tradebot_sci/strategy/decisions.py`)
This is the "Verdict".
```python
@dataclass
class AITradeDecision:
    symbol: str
    action: str              # "enter_long", "enter_short", "stand_aside", "hold"
    confidence: float        # 0.0 to 1.0 (How sure are we?)
    entry_price: float       # Proposed entry
    stop_loss: float         # Proposed stop ("The line in the sand")
    take_profit: float       # Proposed target ("The moon")
    reason: str              # "Because the stars aligned (and RSI < 30)"
```
*   **Philosophy:** Actionable. The Broker takes this and executes it blindly (after checking the wallet).

## Key Functions (The Heavy Hitters)

### `StrategyEngine.decide(...)`
*   **Location:** `src/tradebot_sci/strategy/engine.py`
*   **Purpose:** Takes a `MarketSnapshot` and returns an `AITradeDecision`.
*   **Flow:**
    1.  `build_market_context()`: Formats data for analysis.
    2.  `_check_entry_invalidation()`: Fast-fail if price already ran away.
    3.  `score_icc_grade()`: Calculates the A-F grade.
    4.  Returns a Decision.

### `CCXTExchangeBroker.execute_decision(...)`
*   **Location:** `src/tradebot_sci/broker/ccxt_broker.py`
*   **Purpose:** The muscle.
*   **Flow:**
    1.  **Affordability Check:** `if wallet < req_cash: return BLOCKED`.
    2.  **Order Sizing:** Calculates position size based on Risk %.
    3.  **API Call:** `exchange.create_order(...)`.
    4.  **Stop Loss:** Places the protective stop order immediately after entry.

### `run_bot(...)`
*   **Location:** `src/tradebot_sci/runtime/loop.py`
*   **Purpose:** The eternal loop.
*   **Flow:** `while True: scan -> decide -> execute -> sleep`.
