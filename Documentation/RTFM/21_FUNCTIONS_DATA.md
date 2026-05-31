---
title: 'Under the Hood: Every Function, Every Data Packet'
category: rtfm
icon: data_object
description: "\"The devil is in the details. And the bugs.\" If you are debugging\
  \ this thing, you need to know what the data actually looks like. These are the\
  \ core data objects \u2014 MarketSnapshot, TradeDecision, PositionState \u2014 the\
  \ packets passed around like hot potatoes through every layer of the system. Every\
  \ field, every type, every edge case documented."
---

# 3. Functions & Datasets — The Technical Guts

<table><tr><td width="170"><img src="img/ghost.png" width="150"></td><td><b>GHOST (The AI)</b>:<br><em>"Every function has a purpose. Every data structure has a reason. If you are debugging this machine, you need to know what the data actually looks like. Let me catalog them for you — organ by organ, nerve by nerve."</em></td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Listen, if you're just here to push buttons, get out of this chapter. This is for the nerds. The people who actually want to know why the machine sneezed at 2 AM. Do not read this if you don't know what a JSON file is, you'll just hurt yourself. But you should bookmark it, because you're gonna break something eventually."</td></tr></table>

---

## The Core Data Objects

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"These are the data packets passed around the system like hot potatoes. Each one has a specific shape, a specific purpose, and touching them incorrectly will break things in ways that are surprisingly hard to diagnose."</td></tr></table>

### 1. `MarketSnapshot` (`src/tradebot_sci/market/models.py`)

The "Source of Truth" for a symbol at a specific time.

```python
@dataclass
class MarketSnapshot:
    symbol: str             # e.g., "BTC/USD"
    timeframe: str          # e.g., "5m"
    candles: List[Candle]   # The raw OHLCV data
    trend_htf: TrendState   # Higher Timeframe Trend (Bullish/Bearish/Neutral)
    trend_ltf: TrendState   # Lower Timeframe Trend
```

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"This thing is IMMUTABLE. Do you know what that means? It means you DO NOT TOUCH IT! It is cold, hard facts. It's history. You can't change the past! If I catch you trying to mutate a MarketSnapshot, I will personally come to your house and delete your hard drive."</td></tr></table>

### 2. `AITradeDecision` (`src/tradebot_sci/strategy/decisions.py`)

The "Verdict."

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
    strategy_used: str       # Which strategy made this decision
```

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"This is what the Brain outputs. Four possible actions: enter long, enter short, hold, or stand aside. The Broker takes this object and executes it — after checking the wallet, the leverage, and about six other safety guards, because we don't trust the Brain to have considered everything. Smart people do dumb things."</td></tr></table>

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
    crypto: str = "meta_sci"          # Meta-SCI auto-selects best
    forex: str = "meta_sci"           # Recommended default for all
    stocks: str = "meta_sci"
    etf: str = "meta_sci"
    metals: str = "meta_sci"
    futures: str = "meta_sci"

    def get_strategy_for_symbol(self, symbol: str) -> str:
        asset_class = classify_symbol(symbol)
        return getattr(self, asset_class.value)
```

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"You see how every default says meta_sci? That's not because I was lazy. It's because Meta-SCI is smarter than you! It picks the best strategy on its own. Unless you have a PhD in quantitative analysis and a binder full of backtests, leave it the hell alone!"</td></tr></table>

**Available strategies:** `meta_sci` ⭐, `rubberband_reaper`, `robocop`, `mean_reversion`, `supply_demand`, `trend_rider`, `session_momentum`, `bearish_engulfing`, `icc_core`, `orb_breakout`, `crypto_rsi_macd`, `crypto_vwap_reversion`, `crypto_double_macd`, `crypto_grid`, `evolution`, `quantum`, `hyper_scalper`, `london_breakout`, `volatility_breakout`, `aggregator`.

---

## Key Functions (The Heavy Hitters)

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"These are the functions that do the actual work. Everything else is plumbing. These are the pumps."</td></tr></table>

### `classify_symbol(symbol: str) → AssetClass`
- **Location:** `src/tradebot_sci/utils/symbol_classifier.py`
- **Purpose:** Determines which asset class a symbol belongs to.
- **Logic:**
    - `BTC/USD`, `ETH/USD` → `CRYPTO`
    - `EUR/USD`, `GBP_JPY` → `FOREX`
    - `AAPL`, `TSLA` → `STOCKS`
    - `SPY`, `QQQ` → `ETF`
    - `XAU/USD`, `XAUUSD` → `METALS`
    - `ES`, `NQ`, `MES` → `FUTURES`

### `StrategyEngine.decide(...)`
- **Location:** `src/tradebot_sci/strategy/engine.py`
- **Purpose:** Takes a `MarketSnapshot` and returns an `AITradeDecision`.
- **Flow:**
    1. `classify_symbol()`: Determine asset class.
    2. `get_strategy_for_asset()`: Get the correct strategy.
    3. `build_market_context()`: Format data for analysis.
    4. `strategy.evaluate()`: Run strategy-specific logic.
    5. Returns a Decision.

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Five steps. That's it. Clean, predictable, boring. When things explode in the middle of the night, you want boring. You don't want spaghetti code! You want to be able to point your finger exactly at the thing that failed and yell at it!"</td></tr></table>

### Broker Execution

Each broker has its own execution method:

| Broker | Method | Location |
|--------|--------|----------|
| **CCXT** | `execute_decision()` | `broker/ccxt_broker.py` |
| **IBKR** | `execute_decision()` | `broker/ibkr_broker.py` |
| **OANDA** | `execute_decision()` | `broker/oanda_broker.py` |
| **Paxos** | `execute_decision()` | `broker/paxos_broker.py` |

**Common Flow:**
1. **Affordability Check:** `if wallet < req_cash: return BLOCKED`.
2. **Order Sizing:** Calculates position size based on Risk %.
3. **API Call:** Broker-specific order placement.
4. **Stop Loss:** Places the protective stop order immediately after entry.

<table><tr><td width="170"><img src="img/ninja.png" width="150"></td><td><b>NINJA</b>:<br><em>"The stop goes on immediately. Not after coffee. Not after checking the chart. Immediately. A position without a stop is not a trade — it is a prayer."</em></td></tr></table>

### `run_bot(...)`
- **Location:** `src/tradebot_sci/runtime/loop.py`
- **Purpose:** The eternal loop.
- **Flow:**

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

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"That's the whole bot. Right there. Everything else is implementation detail. The loop wakes up, checks every symbol, asks the strategy what to do, checks the guards, and either executes or moves on. Simple. Elegant. Like a heartbeat — it just keeps going."</td></tr></table>

---

## 📖 Continue Reading

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"Wow, okay I think I get it now. What's next?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Turn the page. We are going to talk about <b>Ghost In Machine</b>. Try to keep up."</td></tr></table>
