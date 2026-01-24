
# 2. The Skeleton (Architecture)
> *"It's alive! ...mostly."*

This document explains the **anatomy** of the application. If `01_PHILOSOPHY.md` was the soul, this is the bones.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Tradebot SCI Architecture                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌─────────────┐     ┌─────────────────────────────────────────────┐  │
│   │   Profile   │────▶│              Strategy Arsenal               │  │
│   │   Loader    │     │  ┌─────────┬─────────┬─────────┬─────────┐  │  │
│   └─────────────┘     │  │ Crypto  │ Forex   │ Stocks  │ Futures │  │  │
│                       │  │ Strategy│ Strategy│ Strategy│ Strategy│  │  │
│                       │  └────┬────┴────┬────┴────┬────┴────┬────┘  │  │
│                       └───────┼─────────┼─────────┼─────────┼───────┘  │
│                               │         │         │         │          │
│   ┌─────────────┐     ┌───────▼─────────▼─────────▼─────────▼───────┐  │
│   │   Market    │────▶│            Strategy Engine                  │  │
│   │   Snapshot  │     │         (Symbol Classification)             │  │
│   └─────────────┘     └──────────────────┬──────────────────────────┘  │
│                                          │                             │
│                                          ▼                             │
│                              ┌───────────────────────┐                 │
│                              │   Trade Decision      │                 │
│                              │   (Buy/Sell/Hold)     │                 │
│                              └───────────┬───────────┘                 │
│                                          │                             │
│   ┌──────────────────────────────────────┼─────────────────────────┐  │
│   │                   Broker Layer        ▼                        │  │
│   │  ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐        │  │
│   │  │  IBKR   │   │  OANDA  │   │  CCXT   │   │  Hybrid │        │  │
│   │  │ Broker  │   │ Broker  │   │ Broker  │   │  Mode   │        │  │
│   │  └─────────┘   └─────────┘   └─────────┘   └─────────┘        │  │
│   └────────────────────────────────────────────────────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## The Loop (`runtime/loop.py`)
This is the heartbeat.
1.  **Wake Up:** Reads `settings_profiles.yaml`, picks a profile (e.g., `forex_continuous`).
2.  **Initialize Strategies:** Loads the per-asset strategy configuration and caches strategy instances.
3.  **Cycle:** Every X seconds (defined in profile), it screams "NEXT CYCLE!"
4.  **Scan:** Iterates through every symbol in your list:
    *   "Hey Symbol Classifier, what asset class is EUR/USD?" → `forex`
    *   "Hey Strategy Cache, give me the strategy for `forex`" → `rubberband_reaper`
    *   "Hey Market, what's EUR/USD doing?"
    *   "Hey Strategy, do we like this setup?"
    *   "Hey Broker, execute if Strategy said yes."
5.  **Sleep:** Naps until the next cycle.

**Key Files:**
*   `src/tradebot_sci/main.py`: The entry point.
*   `src/tradebot_sci/runtime/loop.py`: The infinite `while True` loop.

---

## The Strategy Arsenal

### Multi-Strategy Architecture

The bot supports **9 distinct trading strategies**, each optimized for different market conditions:

| Strategy | Key | Style |
|----------|-----|-------|
| Rubberband Reaper | `rubberband_reaper` | Mean reversion with anti-martingale |
| RoboCop | `robocop` | Ultra-aggressive trending |
| Robot Evolution | `evolution` | No-Trade-Zone scalping |
| Quantum | `quantum` | Trend following with SMA |
| Mean Reversion | `mean_reversion` | Classic Bollinger Band reversion |
| HyperScalper | `hyper_scalper` | Fast EMA crossover |
| London Breakout | `london_breakout` | Session-based breakout |
| Volatility Breakout | `volatility_breakout` | Range compression breakout |
| Singularity Aggregator | `aggregator` | Multi-strategy parallel |

### Per-Asset Strategy Selection

Instead of one strategy for everything, different strategies run for different asset classes:

```yaml
strategies:
  crypto: rubberband_reaper    # BTC, ETH, altcoins
  forex: rubberband_reaper     # EUR/USD, GBP/JPY
  stocks: quantum              # Individual equities
  etf: quantum                 # SPY, QQQ
  metals: mean_reversion       # Gold, Silver
  futures: volatility_breakout # ES, NQ
```

### Symbol Classification

When a symbol is evaluated, the system:
1. **Classifies** the symbol → `BTC/USD` → `crypto`
2. **Retrieves** the strategy for that class → `rubberband_reaper`
3. **Caches** the strategy instance for performance
4. **Evaluates** using that strategy's logic

**Key Files:**
*   `src/tradebot_sci/strategy/factory.py`: Strategy instantiation.
*   `src/tradebot_sci/strategy/variants/`: Individual strategy implementations.
*   `src/tradebot_sci/utils/symbol_classifier.py`: Asset class detection.

---

## The Brain (`strategy/engine.py`)
This is where the magic (or hallucination) happens.
*   **Inputs:** A `MarketSnapshot` (Candles + Trend) + Strategy Variant.
*   **Logic:**
    1.  **Select Strategy:** Get the correct strategy for this symbol's asset class.
    2.  **Filter:** Is the trend right? Is volatility acceptable?
    3.  **Gate:** Did we sweep liquidity? Did we break structure?
    4.  **Score:** Assign an ICC score (0-100). If Score > Threshold, it's a "Go".
*   **Output:** An `AITradeDecision` (Buy/Sell/Hold/StandAside).

### Strategy Variants

Each strategy implements its own logic:

| Strategy | Entry Logic |
|----------|-------------|
| Rubberband Reaper | Bollinger Band break + RSI confirmation |
| RoboCop | 1-bar confirmation, any micro-signal |
| Evolution | NTZ edge sweep + reversal |
| Quantum | SMA pullback + HTF/LTF alignment |
| Mean Reversion | BB + RSI with pyramiding |
| HyperScalper | EMA 9/21 crossover + 200 EMA filter |
| London Breakout | Session range break (08:00-09:00 GMT) |
| Volatility Breakout | Range compression + RSI momentum |
| Aggregator | Mean Reversion + HyperScalper parallel |

**Key Files:**
*   `src/tradebot_sci/strategy/engine.py`: The decision orchestrator.
*   `src/tradebot_sci/strategy/profiles.py`: Profile-specific overrides.
*   `src/tradebot_sci/strategy/variants/*.py`: Individual strategy implementations.

---

## The Hands (Broker Layer)
The executioner. Talks to exchanges/brokers via API.

### Supported Brokers

| Broker | Module | Markets |
|--------|--------|---------|
| **IBKR** | `ibkr_broker.py` | Stocks, Options, Futures, Forex |
| **OANDA** | `oanda_broker.py` | Forex, CFDs |
| **CCXT** | `ccxt_broker.py` | Crypto (Coinbase, Kraken, Binance, etc.) |

### Broker Responsibilities
*   **Translation:** Converts "Buy EUR/USD" to broker-specific API calls.
*   **Protection:** Affordability checks, position limits, risk validation.
*   **Feedback:** Order confirmations or failure handling.
*   **Kill Switch:** Auto-disable after too many consecutive errors.

### Hybrid Mode

The bot can use different brokers for different purposes:
*   **Data from IBKR** + **Execution via OANDA**
*   **Data from CCXT** + **Execution via IBKR**

Configure via `MARKET_DATA_MODE` and `BROKER_MODE` environment variables.

**Key Files:**
*   `src/tradebot_sci/broker/ibkr_broker.py`: Interactive Brokers.
*   `src/tradebot_sci/broker/oanda_broker.py`: OANDA forex.
*   `src/tradebot_sci/broker/ccxt_broker.py`: CCXT crypto exchanges.
*   `src/tradebot_sci/broker/broker_factory.py`: Broker instantiation.

---

## The Eyes (`market/providers.py`)
The humble observer.
*   **Responsibilities:**
    *   Fetches current Price, Bid/Ask, and Historical Candles.
    *   Packages them into a nice, immutable `MarketSnapshot`.
    *   Doesn't judge. Just reports.

### Data Sources

| Provider | Source | Best For |
|----------|--------|----------|
| IBKR | Interactive Brokers API | Stocks, Futures |
| OANDA | OANDA v20 API | Forex |
| CCXT | Exchange APIs | Crypto |

**Key Files:**
*   `src/tradebot_sci/market/providers.py`: Connects to Data APIs.
*   `src/tradebot_sci/market/models.py`: Definitions of `Candle`, `Ticker`, etc.

---

## The Interface (Electron GUI)

A high-fidelity dashboard for monitoring and configuration.

### Components

| Window | Purpose |
|--------|---------|
| **Dashboard** | Real-time P&L, positions, trade log |
| **Settings** | Profile selection, strategy config, broker setup |
| **Charts** | Candlestick visualization with indicators |

### Settings GUI Tabs

| Tab | Purpose |
|-----|---------|
| System | Profile, execution mode, timeframes |
| Strategy Workshop | Per-asset strategies, risk, pyramiding |
| Broker Suite | IBKR, OANDA, CCXT configuration |
| Intelligence | AI provider, commentary policy |
| Hours & Sabbath | Session gates, timezone |
| Advanced | Raw environment editor |

**Key Files:**
*   `src/tradebot_sci/electron_gui/main.js`: Electron main process.
*   `src/tradebot_sci/electron_gui/settings.html`: Settings window.
*   `src/tradebot_sci/electron_gui/renderer.js`: Dashboard logic.

---

## Configuration Flow

```
settings_profiles.yaml
        │
        ▼
┌─────────────────┐
│  Profile Loader │  ← Reads profile (e.g., forex_continuous)
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│                  Profile Config                      │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐    │
│  │ strategies │  │ risk_mgmt  │  │  pyramiding │    │
│  │  per-asset │  │  settings  │  │   config    │    │
│  └────────────┘  └────────────┘  └────────────┘    │
└─────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│ Strategy Cache  │  ← Instantiates strategies per asset class
└────────┬────────┘
         │
         ▼
    Runtime Loop
```

---

## Key Architectural Decisions

### Why Per-Asset Strategies?
Different asset classes behave differently:
- **Crypto:** High volatility, 24/7 → Mean reversion works well
- **Forex:** Session-based, trending → Trend following or session breakouts
- **Stocks:** News-driven, gappy → Safer trend following
- **Metals:** Range-bound → Mean reversion

### Why Multiple Brokers?
- **IBKR:** Best for stocks/options/futures, professional-grade
- **OANDA:** Best for forex, great API, competitive spreads
- **CCXT:** Best for crypto, supports 100+ exchanges

### Why Electron GUI?
- Cross-platform (Windows, Mac, Linux)
- Real-time updates via WebSocket
- Native OS integration
- Familiar web technologies (HTML/CSS/JS)
