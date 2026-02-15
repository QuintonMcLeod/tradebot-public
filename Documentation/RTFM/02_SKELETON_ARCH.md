
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
│   │   Profile   │────▶│         Multi-Strategy Arsenal              │  │
│   │   Loader    │     │  ┌───────────────────────────────────────┐  │  │
│   └─────────────┘     │  │         Meta-SCI Ensemble ⭐          │  │  │
│                       │  │  ┌─────────┬─────────┬─────────────┐  │  │  │
│   ┌─────────────┐     │  │  │ Regime  │ Tourna- │  Winner     │  │  │  │
│   │   Safety    │     │  │  │ Detect  │   ment  │ Selection   │  │  │  │
│   │   Layer     │     │  │  └─────────┴─────────┴─────────────┘  │  │  │
│   │ ┌─────────┐ │     │  ├───────────────────────────────────────┤  │  │
│   │ │Position │ │     │  │  20 Individual Strategy Variants      │  │  │
│   │ │  Lock   │ │     │  │  Universal + Crypto-Specific + Legacy │  │  │
│   │ ├─────────┤ │     │  └───────────┬───────────────────────────┘  │  │
│   │ │Leverage │ │     └──────────────┼──────────────────────────────┘  │
│   │ │ Sentry  │ │                    │                                 │
│   │ ├─────────┤ │     ┌──────────────▼──────────────────────────────┐  │
│   │ │ Daily   │ │     │             Strategy Engine                 │  │
│   │ │ Loss    │ │     │  (Symbol Classification + ICC Scoring)      │  │
│   │ │ Limit   │ │     └──────────────┬──────────────────────────────┘  │
│   │ ├─────────┤ │                    │                                 │
│   │ │Breakeven│ │                    ▼                                 │
│   │ │ Trail   │ │     ┌───────────────────────┐                       │
│   │ └─────────┘ │     │   Trade Decision      │                       │
│   └──────┬──────┘     │   (Buy/Sell/Hold)     │                       │
│          │            └───────────┬───────────┘                       │
│          │                       │                                     │
│          └──────────────────────►│ (guards applied before execution)   │
│                                  │                                     │
│   ┌──────────────────────────────┼─────────────────────────────────┐  │
│   │                  Broker Layer │                                 │  │
│   │  ┌─────────┐  ┌─────────┐  ┌▼────────┐  ┌─────────┐          │  │
│   │  │  IBKR   │  │  OANDA  │  │  CCXT   │  │  Paxos  │          │  │
│   │  │ Broker  │  │ Broker  │  │ Broker  │  │ Broker  │          │  │
│   │  └─────────┘  └─────────┘  └─────────┘  └─────────┘          │  │
│   └────────────────────────────────────────────────────────────────┘  │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

---

## The Loop (`runtime/loop.py`)
This is the heartbeat.
1.  **Pre-Flight Check:** Verifies at least one broker is configured. Refuses to start otherwise.
2.  **Wake Up:** Reads config (JSON or YAML), picks a profile (e.g., `forex_continuous`).
3.  **Initialize Strategies:** Loads the per-asset strategy configuration and caches strategy instances.
4.  **Cycle:** Every X seconds (defined in profile), it starts a new scan cycle.
5.  **Scan:** Iterates through every symbol in your list:
    *   "Hey Symbol Classifier, what asset class is EUR/USD?" → `forex`
    *   "Hey Strategy Cache, give me the strategy for `forex`" → `meta_sci`
    *   "Hey Market, what's EUR/USD doing?"
    *   "Hey Strategy, do I like this setup?" → Meta-SCI runs tournament
    *   "Hey Safety Layer, is this trade allowed?" → Position Lock, Leverage Sentry check
    *   "Hey Broker, execute if everything passed."
6.  **Sleep:** Naps until the next cycle.

**Key Files:**
*   `src/tradebot_sci/main.py`: The entry point.
*   `src/tradebot_sci/runtime/loop.py`: The infinite `while True` loop + preflight broker check.

---

## The Strategy Arsenal

### Meta-SCI: The Adaptive Ensemble ⭐

The recommended default. Instead of committing to a single strategy, Meta-SCI runs a **tournament** every cycle:

1. **Detects market regime** (trending, ranging, choppy)
2. **Selects eligible strategies** for that regime
3. **Runs them all in parallel** — each generates a signal
4. **Picks the winner** — highest-scoring signal becomes the decision
5. **Falls back gracefully** — no qualifying signal = STAND ASIDE

See `09_FEET_WET_STRATEGY.md` for the full tournament flow.

### The 20-Strategy Arsenal

| Strategy | Key | Style |
|----------|-----|-------|
| **Meta-SCI** ⭐ | `meta_sci` | AI Ensemble (auto-selects best) |
| **Rubberband Reaper** | `rubberband_reaper` | Mean Reversion + Anti-Martingale |
| **RoboCop** | `robocop` | Sniper Precision |
| **Mean Reversion** | `mean_reversion` | Bollinger + RSI |
| **Supply & Demand** | `supply_demand` | Institutional Zones |
| **Trend Rider** | `trend_rider` | EMA Pullback |
| **Session Momentum** | `session_momentum` | VWAP at Session Open |
| **Engulfing Reversal** | `bearish_engulfing` | Candlestick Patterns |
| **ICC Core** | `icc_core` | Pure Structure Trading |
| **ORB Breakout** | `orb_breakout` | Opening Range Breakout |
| **Robot Evolution** | `evolution` | NTZ Scalping |
| **Quantum** | `quantum` | SMA Trend Following |
| **HyperScalper** | `hyper_scalper` | Fast EMA Crossover |
| **London Breakout** | `london_breakout` | Session Breakout |
| **Volatility Breakout** | `volatility_breakout` | Range Compression |
| **Aggregator** | `aggregator` | Multi-Strategy Parallel |
| 🪙 **RSI + MACD** | `crypto_rsi_macd` | Crypto Momentum |
| 🪙 **VWAP Reversion** | `crypto_vwap_reversion` | Crypto Mean Reversion |
| 🪙 **Double MACD** | `crypto_double_macd` | Crypto Scalping |
| 🪙 **Virtual Grid** | `crypto_grid` | Crypto Grid Trading |

### Per-Asset Strategy Selection

When a symbol is evaluated, the system:
1. **Classifies** the symbol → `BTC/USD` → `crypto`
2. **Retrieves** the strategy for that class → `meta_sci`
3. **Caches** the strategy instance for performance
4. **Evaluates** using that strategy's logic (or Meta-SCI tournament)

**Key Files:**
*   `src/tradebot_sci/strategy/engine.py`: Strategy loading + decision orchestration.
*   `src/tradebot_sci/strategy/variants/`: Individual strategy implementations (20 files).
*   `src/tradebot_sci/strategy/variants/meta_sci.py`: The Meta-SCI ensemble.
*   `src/tradebot_sci/utils/symbol_classifier.py`: Asset class detection.

---

## The Brain (`strategy/engine.py`)
This is where the magic (or hallucination) happens.
*   **Inputs:** A `MarketSnapshot` (Candles + Trend) + Strategy Variant.
*   **Logic:**
    1.  **Select Strategy:** Get the correct strategy for this symbol's asset class.
    2.  **Filter:** Is the trend right? Is volatility acceptable?
    3.  **Gate:** Did I sweep liquidity? Did I break structure?
    4.  **Score:** Assign an ICC score (0-100). If Score > Threshold, it's a "Go".
*   **Output:** An `AITradeDecision` (Buy/Sell/Hold/StandAside).

**Key Files:**
*   `src/tradebot_sci/strategy/engine.py`: The decision orchestrator.
*   `src/tradebot_sci/strategy/profiles.py`: Profile-specific overrides.
*   `src/tradebot_sci/strategy/variants/*.py`: Individual strategy implementations.

---

## The Safety Layer (`runtime/safety.py` + `runtime/loop.py`)

The guardrail system that protects you from bad trades and from yourself.

| Guard | What It Prevents | When It Acts |
|-------|-----------------|--------------|
| **Position Lock** | Whipsaw flipping (long→short→long) | Before entry — blocks if position already open for symbol |
| **Leverage Sentry** | Over-leveraging | Before entry — blocks if leverage exceeds cap |
| **Daily Loss Limit** | Tilt spirals | Before entry — stops all trading if daily loss hits circuit breaker |
| **Breakeven Trail** | Giving back profits | After entry — moves SL to breakeven after configurable profit |
| **Trailing Stop** | Letting winners become losers | After entry — ratchets SL up as price advances |
| **ICC Gatekeeper** | Low-quality trades | Before entry — rejects setups below ICC score threshold |
| **Preflight Broker Check** | Running without a broker | On startup — refuses to start if no broker configured |

**Key Files:**
*   `src/tradebot_sci/runtime/safety.py`: Decision validation.
*   `src/tradebot_sci/runtime/loop.py`: Preflight check + position lock logic.

---

## The Hands (Broker Layer)
The executioner. Talks to exchanges/brokers via API.

### Supported Brokers

| Broker | Module | Markets |
|--------|--------|---------|
| **IBKR** | `ibkr_broker.py` | Stocks, Options, Futures, Forex |
| **OANDA** | `oanda_broker.py` | Forex, CFDs |
| **CCXT** | `ccxt_broker.py` | Crypto (Gemini, Coinbase, Kraken, etc.) |
| **Paxos** | `paxos_broker.py` | Crypto (Paxos/itBit) |
| **Kraken** | `kraken_broker.py` | Crypto (Kraken direct) |

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
*   `src/tradebot_sci/broker/paxos_broker.py`: Paxos/itBit crypto.
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
| **Dashboard** | Real-time chart, positions, live P&L, trade decisions, logs |
| **Profile Editor** | Profile selection, symbol lists, strategy assignment |
| **Strategy Toolbox** | Browse all 20 strategies with descriptions and stats |
| **Settings** | Broker config, AI setup, risk management, safety controls |

### Settings GUI Tabs

| Tab | Purpose |
|-----|---------|
| System | Profile, execution mode, timeframes, trend detection |
| Strategy Workshop | Browse strategies, per-asset assignment, ICC scoring |
| Broker Suite | IBKR, OANDA, CCXT, Paxos, Kraken configuration |
| Intelligence | AI provider, model settings, commentary policy |
| Safety & Shields | Position Lock, Leverage Sentry, Breakeven Trail, Daily Loss |
| Hours & Sabbath | Session gates, Sabbath blocking, timezone |
| Advanced | Raw environment editor |

**Key Files:**
*   `src/tradebot_sci/electron_gui/main.js`: Electron main process.
*   `src/tradebot_sci/electron_gui/index.html`: Dashboard + Profile Editor.
*   `src/tradebot_sci/electron_gui/renderer.js`: Dashboard logic.
*   `src/tradebot_sci/electron_gui/settings_integrated.js`: Settings logic.

---

## Configuration Flow

```
config.json (primary)  ←or→  settings_profiles.yaml (legacy)
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
│  │ strategies │  │ risk_mgmt  │  │   safety   │    │
│  │  per-asset │  │  settings  │  │   guards   │    │
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
- **Crypto:** High volatility, 24/7 → Mean reversion and momentum work well
- **Forex:** Session-based, trending → Trend following or session strategies
- **Stocks:** News-driven, gappy → Safer trend following
- **Metals:** Range-bound → Mean reversion

### Why Meta-SCI as Default?
Users don't need to know which strategy is best for which market. Meta-SCI detects the regime and selects the best strategy automatically. It adapts as market conditions change.

### Why Multiple Brokers?
- **IBKR:** Best for stocks/options/futures, professional-grade
- **OANDA:** Best for forex, great API, competitive spreads
- **CCXT:** Best for crypto, supports 100+ exchanges
- **Paxos:** Specialized crypto (itBit)

### Why Electron GUI?
- Cross-platform (Windows, Mac, Linux)
- Real-time updates via WebSocket
- Native OS integration
- Familiar web technologies (HTML/CSS/JS)
