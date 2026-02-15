
# 3. Functions & Datasets
> *"The devil is in the details. And the bugs."*

If you are debugging this thing, you need to know what the data actually looks like.

---

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
*   **Philosophy:** Immutable. Once created, I don't mess with it. It represents "What Happened".

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
    strategy_used: str       # Which strategy made the decision (e.g., "rubberband_reaper")
```
*   **Philosophy:** Actionable. The Broker takes this and executes it blindly (after checking the wallet).

### 3. `AssetClass` (Enum)
Used for per-asset strategy selection.
```python
class AssetClass(Enum):
    CRYPTO = "crypto"       # BTC, ETH, altcoins
    FOREX = "forex"         # EUR/USD, GBP/JPY
    STOCKS = "stocks"       # AAPL, TSLA
    ETF = "etf"             # SPY, QQQ
    METALS = "metals"       # XAU, XAG (Gold, Silver)
    FUTURES = "futures"     # ES, NQ, MES
```

### 4. `PerAssetStrategies` (`src/tradebot_sci/strategy/profiles.py`)
Maps asset classes to strategies.
```python
@dataclass
class PerAssetStrategies:
    crypto: str = "meta_sci"          # Meta-SCI auto-selects best strategy
    forex: str = "meta_sci"           # Recommended default for all classes
    stocks: str = "meta_sci"
    etf: str = "meta_sci"
    metals: str = "meta_sci"
    futures: str = "meta_sci"

    def get_strategy_for_symbol(self, symbol: str) -> str:
        asset_class = classify_symbol(symbol)
        return getattr(self, asset_class.value)
```

**Available strategies:** `meta_sci` ⭐, `rubberband_reaper`, `robocop`, `mean_reversion`, `supply_demand`, `trend_rider`, `session_momentum`, `bearish_engulfing`, `icc_core`, `orb_breakout`, `crypto_rsi_macd`, `crypto_vwap_reversion`, `crypto_double_macd`, `crypto_grid`, `evolution`, `quantum`, `hyper_scalper`, `london_breakout`, `volatility_breakout`, `aggregator`.

---

## Key Functions (The Heavy Hitters)

### `classify_symbol(symbol: str) -> AssetClass`
*   **Location:** `src/tradebot_sci/utils/symbol_classifier.py`
*   **Purpose:** Determines which asset class a symbol belongs to.
*   **Logic:**
    - `BTC/USD`, `ETH/USD` → `CRYPTO`
    - `EUR/USD`, `GBP_JPY` → `FOREX`
    - `AAPL`, `TSLA` → `STOCKS`
    - `SPY`, `QQQ` → `ETF`
    - `XAU/USD`, `XAUUSD` → `METALS`
    - `ES`, `NQ`, `MES` → `FUTURES`

### `StrategyEngine.decide(...)`
*   **Location:** `src/tradebot_sci/strategy/engine.py`
*   **Purpose:** Takes a `MarketSnapshot` and returns an `AITradeDecision`.
*   **Flow:**
    1.  `classify_symbol()`: Determine asset class.
    2.  `get_strategy_for_asset()`: Get the correct strategy for this asset class.
    3.  `build_market_context()`: Formats data for analysis.
    4.  `strategy.evaluate()`: Run the strategy-specific logic.
    5.  Returns a Decision.

### Broker Execution
Each broker has its own execution method:

| Broker | Method | Location |
|--------|--------|----------|
| **CCXT** | `execute_decision()` | `broker/ccxt_broker.py` |
| **IBKR** | `execute_decision()` | `broker/ibkr_broker.py` |
| **OANDA** | `execute_decision()` | `broker/oanda_broker.py` |
| **Paxos** | `execute_decision()` | `broker/paxos_broker.py` |

**Common Flow:**
1.  **Affordability Check:** `if wallet < req_cash: return BLOCKED`.
2.  **Order Sizing:** Calculates position size based on Risk %.
3.  **API Call:** Broker-specific order placement.
4.  **Stop Loss:** Places the protective stop order immediately after entry.

### `run_bot(...)`
*   **Location:** `src/tradebot_sci/runtime/loop.py`
*   **Purpose:** The eternal loop.
*   **Flow:**
    ```
    preflight_broker_check()           # Refuse to start without a broker
    while True:
        for symbol in symbols:
            if position_locked(symbol):     # Position Lock check
                continue
            asset_class = classify_symbol(symbol)
            strategy = get_strategy_for_asset(asset_class)
            snapshot = fetch_market_data(symbol)
            decision = strategy.evaluate(snapshot)
            if leverage_ok(decision):       # Leverage Sentry
                execute_decision(decision)
        sleep(interval)
    ```
