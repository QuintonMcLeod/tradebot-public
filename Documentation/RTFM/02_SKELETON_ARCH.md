# 2. Inside the Machine: The Complete Skeletal Architecture

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"If Chapter 1 was the soul — the <em>why</em> — this is the bones. The skeleton. The thing that holds the soul upright so it doesn't collapse into a pile of good intentions and Python exceptions.<br><br>Let me walk you through the anatomy of this machine, piece by piece, organ by organ."</td></tr></table>

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"Do I need to understand all of this to use the bot?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Look, do you need to know how a transmission works to drive to Wendy's? No. But when your car starts smoking on the highway at 3 AM and you don't know what a radiator is, you're gonna look real stupid on the side of the road. This is the manual so you don't look stupid."</td></tr></table>

---

## High-Level Architecture

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Here's the blueprint. And yes, it looks complicated, because it IS complicated! You think making money while you sleep is supposed to be easy? Every piece here has a job. Don't touch anything unless you know exactly what it does."</td></tr></table>

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

## The Loop — The Heartbeat (`runtime/loop.py`)

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"This is the heartbeat. The pulse. It wakes up every few seconds, looks at every single symbol you told it to watch, and asks 'Are we making money right now?' If no, it goes back to sleep. It's like a night watchman, except it doesn't complain about the hours, it doesn't need coffee, and it doesn't fall asleep on the job!"</td></tr></table>

Here's what happens each cycle:

1. **Pre-Flight Check:** Verifies at least one broker is configured. Refuses to start otherwise. No broker = no point.
2. **Wake Up:** Reads config (JSON or YAML), picks a profile (e.g., `forex_continuous`).
3. **Initialize Strategies:** Loads the per-asset strategy configuration and caches strategy instances.
4. **Cycle:** Every X seconds (defined in profile), it starts a new scan cycle.
5. **Scan:** Iterates through every symbol in your list:

<table><tr><td width="170"><img src="img/bot.png" width="150"></td><td><b>THE BOT</b>:<br><em>"Hey Symbol Classifier, what asset class is EUR/USD?" → forex<br>"Hey Strategy Cache, give me the strategy for forex" → meta_sci<br>"Hey Market, what's EUR/USD doing?" → candles, indicators, structure<br>"Hey Strategy, do I like this setup?" → Meta-SCI runs tournament<br>"Hey Safety Layer, is this trade allowed?" → Position Lock, Leverage Sentry check<br>"Hey Broker, execute if everything passed." → Order sent (or rejected)</em></td></tr></table>

6. **Sleep:** Naps until the next cycle. Dreams of nothing. Because it can't.

**Key Files:**
- `src/tradebot_sci/main.py`: The entry point. Where it all begins.
- `src/tradebot_sci/runtime/loop.py`: The infinite `while True` loop + preflight broker check.

---

## The Strategy Arsenal

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"Meta-SCI is the recommended default. Instead of committing to a single strategy like a person who orders the same thing at every restaurant, it runs a <b>tournament</b> every cycle. Twenty strategies walk in. Only one walks out with the trade."</td></tr></table>

The tournament flow:
1. **Detects market regime** (trending, ranging, choppy)
2. **Selects eligible strategies** for that regime
3. **Runs them all in parallel** — each generates a signal
4. **Picks the winner** — highest-scoring signal becomes the decision
5. **Falls back gracefully** — no qualifying signal = STAND ASIDE

See Chapter 9 (**20 Weapons of War**) for the full tournament flow.

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

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"When a symbol is evaluated, the system goes through a four-step process. It's very organized. Like a library. If libraries traded forex."</td></tr></table>

1. **Classifies** the symbol → `BTC/USD` → `crypto`
2. **Retrieves** the strategy for that class → `meta_sci`
3. **Caches** the strategy instance for performance
4. **Evaluates** using that strategy's logic (or Meta-SCI tournament)

**Key Files:**
- `src/tradebot_sci/strategy/engine.py`: Strategy loading + decision orchestration.
- `src/tradebot_sci/strategy/variants/`: Individual strategy implementations (20 files).
- `src/tradebot_sci/strategy/variants/meta_sci.py`: The Meta-SCI ensemble.
- `src/tradebot_sci/utils/symbol_classifier.py`: Asset class detection.

---

## The Brain (`strategy/engine.py`)

<table><tr><td width="170"><img src="img/ghost.png" width="150"></td><td><b>GHOST (The AI)</b>:<br><em>"This is where the magic — or the hallucination — happens. I take in raw market data, I process it through the strategy framework, and I produce a decision. Buy. Sell. Hold. Stand Aside.<br><br>Four possible answers. But the thinking behind each one? That's where the complexity lives."</em></td></tr></table>

- **Inputs:** A `MarketSnapshot` (Candles + Trend) + Strategy Variant.
- **Logic:**
    1. **Select Strategy:** Get the correct strategy for this symbol's asset class.
    2. **Filter:** Is the trend right? Is volatility acceptable?
    3. **Gate:** Did I sweep liquidity? Did I break structure?
    4. **Score:** Assign an ICC score (0-100). If Score > Threshold, it's a "Go."
- **Output:** An `AITradeDecision` (Buy/Sell/Hold/StandAside).

**Key Files:**
- `src/tradebot_sci/strategy/engine.py`: The decision orchestrator.
- `src/tradebot_sci/strategy/profiles.py`: Profile-specific overrides.
- `src/tradebot_sci/strategy/variants/*.py`: Individual strategy implementations.

---

## The Safety Layer — The Bodyguard

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"The Safety Layer is the bouncer. The big guy at the door who doesn't care who you know. The Brain goes, 'Hey, I wanna trade!' and the Safety Layer goes, 'Show me some ID, empty your pockets, and explain your entire life story, and MAYBE I'll let you in.' Most of the time it just throws you back on the street. And it's doing you a favor!"</td></tr></table>

| Guard | What It Prevents | When It Acts |
|-------|--------------------|--------------|
| **Position Lock** | Whipsaw flipping (long→short→long) | Before entry — blocks if position already open |
| **Leverage Sentry** | Over-leveraging | Before entry — blocks if leverage exceeds cap |
| **Daily Loss Limit** | Tilt spirals | Before entry — stops all trading if daily loss hits breaker |
| **Breakeven Trail** | Giving back profits | After entry — moves SL to breakeven after configurable profit |
| **Trailing Stop** | Letting winners become losers | After entry — ratchets SL up as price advances |
| **ICC Gatekeeper** | Low-quality trades | Before entry — rejects setups below ICC score threshold |
| **Preflight Broker Check** | Running without a broker | On startup — refuses to start if no broker configured |

<table><tr><td width="170"><img src="img/bear.png" width="150"></td><td><b>BEAR</b>:<br>"So the safety layer can override the brain?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Every single time. The brain proposes, the safety layer disposes. It's like having a really smart friend who also has a really cautious parent. The friend has great ideas. The parent makes sure none of them kill you."</td></tr></table>

**Key Files:**
- `src/tradebot_sci/runtime/safety.py`: Decision validation.
- `src/tradebot_sci/runtime/loop.py`: Preflight check + position lock logic.

---

## The Hands — The Broker Layer

<table><tr><td width="170"><img src="img/ninja.png" width="150"></td><td><b>NINJA</b>:<br><em>"The executioner. Once the brain decides and the safety layer approves, the hands reach out to the exchange and place the order. Silently. Precisely. Without hesitation."</em></td></tr></table>

### Supported Brokers

| Broker | Module | Markets |
|--------|--------|---------|
| **IBKR** | `ibkr_broker.py` | Stocks, Options, Futures, Forex |
| **OANDA** | `oanda_broker.py` | Forex, CFDs |
| **CCXT** | `ccxt_broker.py` | Crypto (Gemini, Coinbase, Kraken, etc.) |
| **Paxos** | `paxos_broker.py` | Crypto (Paxos/itBit) |
| **Kraken** | `kraken_broker.py` | Crypto (Kraken direct) |

### Broker Responsibilities

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"Each broker does four things. No more, no less:"</td></tr></table>

- **Translation:** Converts "Buy EUR/USD" to broker-specific API calls. Because IBKR speaks a completely different language than OANDA. It's like translating between English and Japanese — the meaning is the same but the grammar is wildly different.
- **Protection:** Affordability checks, position limits, risk validation.
- **Feedback:** Order confirmations or failure handling.
- **Kill Switch:** Auto-disable after too many consecutive errors. If the broker keeps failing, the bot stops trying. Because insanity is doing the same thing over and over expecting different results.

### Hybrid Mode

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"The bot can use different brokers for different purposes. Data from IBKR, execution via OANDA. Data from CCXT, execution via IBKR. Mix and match like a DJ with two turntables. Configure via MARKET_DATA_MODE and BROKER_MODE environment variables."</td></tr></table>

**Key Files:**
- `src/tradebot_sci/broker/ibkr_broker.py`: Interactive Brokers.
- `src/tradebot_sci/broker/oanda_broker.py`: OANDA forex.
- `src/tradebot_sci/broker/ccxt_broker.py`: CCXT crypto exchanges.
- `src/tradebot_sci/broker/paxos_broker.py`: Paxos/itBit crypto.
- `src/tradebot_sci/broker/broker_factory.py`: Broker instantiation.

---

## The Eyes — Market Data (`market/providers.py`)

<table><tr><td width="170"><img src="img/monk.png" width="150"></td><td><b>MONK</b>:<br><em>"The humble observer. It watches. It records. It does not judge. It fetches the price, the bid/ask, the candle history — and packages them into an immutable MarketSnapshot. Then it sits quietly and waits to be asked again."</em></td></tr></table>

| Provider | Source | Best For |
|----------|--------|----------|
| IBKR | Interactive Brokers API | Stocks, Futures |
| OANDA | OANDA v20 API | Forex |
| CCXT | Exchange APIs | Crypto |

**Key Files:**
- `src/tradebot_sci/market/providers.py`: Connects to Data APIs.
- `src/tradebot_sci/market/models.py`: Definitions of `Candle`, `Ticker`, etc.

---

## The Interface — Electron GUI

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"The GUI is your cockpit. It's where you see everything — the chart, the trades, the P&L, the logs. It looks like the control panel of a spacecraft, and that's intentional. Because trading without visibility is flying blind."</td></tr></table>

| Window | Purpose |
|--------|---------|
| **Dashboard** | Real-time chart, positions, live P&L, trade decisions, logs |
| **Profile Editor** | Profile selection, symbol lists, strategy assignment |
| **Strategy Toolbox** | Browse all 21 strategies with descriptions and stats |
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
- `src/tradebot_sci/electron_gui/main.js`: Electron main process.
- `src/tradebot_sci/electron_gui/index.html`: Dashboard + Profile Editor.
- `src/tradebot_sci/electron_gui/renderer.js`: Dashboard logic.
- `src/tradebot_sci/electron_gui/settings_integrated.js`: Settings logic.

---

## Configuration Flow

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"Config flows downward like a waterfall. Profile → Strategies → Cache → Runtime. Here's the visual:"</td></tr></table>

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

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Nothing in this architecture is accidental. Every decision was made for a reason. Some of those reasons were learned the hard way — which means they cost me time, money, or both."</td></tr></table>

<table><tr><td width="170"><img src="img/skeptic.png" width="150"></td><td><b>SKEPTIC</b>:<br>"Why per-asset strategies?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Because different asset classes behave completely differently. Crypto is a 24/7 rollercoaster with no seatbelts. Forex is session-based and trending. Stocks are news-driven and gappy. Metals range-bound. You wouldn't wear the same outfit to a beach and a funeral. Same energy."</td></tr></table>

<table><tr><td width="170"><img src="img/skeptic.png" width="150"></td><td><b>SKEPTIC</b>:<br>"Why Meta-SCI as default?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Because users don't need to know which strategy is best for which market. Meta-SCI detects the regime and selects the best strategy automatically. It adapts as conditions change. It's like having a personal shopper who actually knows your taste instead of just guessing."</td></tr></table>

<table><tr><td width="170"><img src="img/skeptic.png" width="150"></td><td><b>SKEPTIC</b>:<br>"Why multiple brokers?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"IBKR is best for stocks and futures — professional grade. OANDA is best for forex — great API, competitive spreads. CCXT for crypto — supports 100+ exchanges. Paxos for specialized crypto. Each broker is a specialist. You don't go to an eye doctor for a broken leg."</td></tr></table>

<table><tr><td width="170"><img src="img/skeptic.png" width="150"></td><td><b>SKEPTIC</b>:<br>"Why Electron for the GUI?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Cross-platform — works on Windows, Mac, Linux. Real-time updates via WebSocket. Native OS integration. Built with web technologies that every developer on the planet knows. And because I wasn't about to learn Swift AND Qt AND GTK just to make some buttons and a chart. I've got a bot to build."</td></tr></table>


> [!NOTE]
> **APRIL 2026 UI & VITALS UPDATE:**  
> Listen up, you degenerates. We just dropped a massive update to the UI and Nurse's Station. The tooltips now trigger when you hover over the *entire goddamn card*, so your fat thumbs can't miss them anymore. The Exit Logic tab is now a clean, idiot-proof single column. We also fixed the Nurse's Station connection tracker—no more lying to you that the bot is dead when it's actively retrying to connect. Read **47_UI_OVERHAUL_AND_VITALS.md** for the full breakdown before you touch the controls and blow your account.
