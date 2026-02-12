
# 4. Map & Table of Contents
> *"Where is `main.py` again?"*

The project structure is classic Python with an Electron GUI layer on top.

---

## The Map

```text
/
├── config/                     # User Settings (Legacy)
│   └── settings_profiles.yaml  # Legacy config (still supported)
│
├── config.json                 # THE MAIN CONFIG (Profiles, Strategies, Symbols)
├── .env.secrets                # API Keys (don't commit!)
│
├── scripts/                    # Entry points
│   ├── tradebot.sh             # <--- THE BIG RED BUTTON (Start Script)
│   ├── run_dev_bot.py          # Python Entry (runs the loop)
│   └── publish_mirror.sh       # Mirror script for public repo
│
├── tools/                      # Backtesting & Analysis
│   ├── run_crypto_backtest.py  # Crypto backtest
│   ├── run_forex_backtest.py   # Forex backtest
│   ├── optimize_strategies.py  # Strategy optimization
│   └── cartridges/             # Head-to-head comparison scripts
│       └── forex_30day_h2h.py  # 30-day forex strategy comparison
│
├── src/
│   └── tradebot_sci/
│       ├── main.py             # Startup logic
│       │
│       ├── runtime/            # The Loop + Safety
│       │   ├── loop.py         # The Heartbeat + Preflight Broker Check
│       │   ├── safety.py       # Decision validation, guards
│       │   └── rate_limit.py   # API retry logic
│       │
│       ├── strategy/           # The Brain (Multi-Strategy Arsenal)
│       │   ├── engine.py       # Strategy factory + decision orchestrator
│       │   ├── profiles.py     # Profile-specific overrides
│       │   ├── icc_signals.py  # ICC signal detection
│       │   ├── scoring.py      # ICC scoring system
│       │   └── variants/       # 20 Individual strategy implementations
│       │       ├── base.py                 # Base class for all strategies
│       │       ├── meta_sci.py             # ⭐ Meta-SCI Ensemble
│       │       ├── rubberband_reaper.py    # Mean Reversion + Anti-Martingale
│       │       ├── robocop.py              # Sniper Precision
│       │       ├── mean_reversion.py       # Classic Bollinger + RSI
│       │       ├── supply_demand.py        # Institutional Zones
│       │       ├── trend_rider.py          # EMA Pullback
│       │       ├── session_momentum.py     # VWAP at Session Open
│       │       ├── bearish_engulfing.py    # Engulfing Reversal
│       │       ├── icc_core.py             # Pure ICC Structure
│       │       ├── orb_breakout.py         # Opening Range Breakout
│       │       ├── crypto_rsi_macd.py      # 🪙 Crypto RSI + MACD
│       │       ├── crypto_vwap_reversion.py # 🪙 Crypto VWAP Reversion
│       │       ├── crypto_double_macd.py   # 🪙 Crypto Double MACD
│       │       ├── crypto_grid.py          # 🪙 Crypto Virtual Grid
│       │       ├── evolution.py            # Robot Evolution (NTZ)
│       │       ├── quantum.py              # Quantum (SMA Trend)
│       │       ├── hyper_scalper.py         # HyperScalper (EMA Crossover)
│       │       ├── london_breakout.py      # London Breakout
│       │       ├── breakout.py             # Volatility Breakout
│       │       └── aggregator.py           # Multi-Strategy Parallel
│       │
│       ├── ai/                 # The Soul (AI Commentary)
│       │   ├── client.py       # AI provider connections
│       │   ├── prompts.py      # Decision prompt templates
│       │   └── schemas.py      # AI response parsing
│       │
│       ├── broker/             # The Hands (Multi-Broker Support)
│       │   ├── broker_factory.py   # Broker instantiation
│       │   ├── ibkr_broker.py      # Interactive Brokers
│       │   ├── oanda_broker.py     # OANDA Forex
│       │   ├── ccxt_broker.py      # CCXT Crypto (Gemini, Coinbase, etc.)
│       │   ├── paxos_broker.py     # Paxos/itBit Crypto
│       │   ├── kraken_broker.py    # Kraken Crypto (direct)
│       │   └── trade_result_store.py # Trade history tracking
│       │
│       ├── market/             # The Eyes
│       │   ├── providers.py    # Data fetching
│       │   ├── oanda_provider.py   # OANDA market data
│       │   └── models.py       # Candle, Ticker definitions
│       │
│       ├── config/             # Configuration System
│       │   ├── loader.py       # Config loading + YAML→JSON migration
│       │   └── models.py       # Settings data models
│       │
│       ├── confluence/         # Market Context
│       │   └── context.py      # Build confluence data for AI
│       │
│       ├── server/             # WebSocket Server
│       │   └── ws_server.py    # GUI ↔ Bot communication
│       │
│       ├── logging/            # Logging System
│       │   └── setup.py        # Log configuration + WebSocket handler
│       │
│       ├── utils/              # Utilities
│       │   └── symbol_classifier.py  # Asset class detection
│       │
│       └── electron_gui/       # The Dashboard (Electron)
│           ├── main.js         # Electron main process
│           ├── index.html      # Dashboard + Profile Editor
│           ├── renderer.js     # Dashboard logic
│           ├── settings_integrated.js  # Settings logic (all tabs)
│           └── package.json    # Node dependencies
│
├── Documentation/
│   ├── HOW_TO_USE.md           # Quick Start Guide
│   └── RTFM/
│       ├── 01_PHILOSOPHY.md        # The Why (Start Here)
│       ├── 02_SKELETON_ARCH.md     # The Anatomy (Architecture)
│       ├── 03_FUNCTIONS_DATA.md    # The Technicals (Data Objects)
│       ├── 04_MAP_TOC.md           # The Map (You Are Here)
│       ├── 05_COOKBOOK.md           # The Recipes (How-To)
│       ├── 06_PANIC_BUTTON.md      # Troubleshooting
│       ├── 07_COCKPIT_CONTROLS.md  # Configuration Guide
│       ├── 08_API_SETUP.md         # API Connection Guide
│       ├── 09_FEET_WET_STRATEGY.md # All 20 Strategies Explained
│       ├── 10_THE_ANCIENT_OATHS.md # AI Guidelines
│       ├── 11_GHOST_IN_MACHINE.md  # AI & Strategy Logic
│       ├── 12_TIME_MACHINE.md      # Backtesting
│       └── 13_ENV_VARS.md          # Environment Variables Reference
│
├── logs/                       # Where the bot screams into the void
│   └── tradebot.log            # The main log file
│
└── .env.secrets                # YOUR SECRETS (API Keys). Not in git.
```

---

## Quick Navigation

| Task | Go To |
|------|-------|
| Change **what symbols** to trade | `config.json` → `profiles` → `symbols` (or Profile Editor UI) |
| Change **which strategy** | `config.json` → `profiles` → `strategy` (or Profile Editor → General) |
| Change **how strategies work** | `src/tradebot_sci/strategy/variants/` |
| Fix a **broker API error** | `src/tradebot_sci/broker/` |
| Configure **IBKR connection** | Settings GUI → Brokers → IBKR |
| Configure **OANDA connection** | Settings GUI → Brokers → OANDA |
| Configure **crypto exchange** | Settings GUI → Brokers → CCXT |
| Configure **safety guards** | Settings GUI → Safety & Shields |
| View **logs** | `tail -f logs/tradebot.log` |
| Open **full GUI** | `./scripts/tradebot.sh --gui` |

---

## Key Files by Purpose

### Strategy Selection
| File | Purpose |
|------|---------|
| `config.json` | Per-asset strategy mapping (primary) |
| `config/settings_profiles.yaml` | Per-asset strategy mapping (legacy) |
| `strategy/engine.py` | Strategy factory + loading |
| `strategy/variants/meta_sci.py` | Meta-SCI ensemble tournament |
| `utils/symbol_classifier.py` | Detects asset class from symbol |

### Safety & Guards
| File | Purpose |
|------|---------|
| `runtime/loop.py` | Preflight broker check, Position Lock |
| `runtime/safety.py` | Decision validation, Leverage Sentry |

### Broker Connections
| File | Purpose |
|------|---------|
| `broker/ibkr_broker.py` | Stocks, Futures, Options |
| `broker/oanda_broker.py` | Forex pairs |
| `broker/ccxt_broker.py` | Crypto exchanges (Gemini, Coinbase, etc.) |
| `broker/paxos_broker.py` | Paxos/itBit crypto |

### GUI
| File | Purpose |
|------|---------|
| `electron_gui/main.js` | Electron main process |
| `electron_gui/index.html` | Dashboard + Profile Editor |
| `electron_gui/settings_integrated.js` | Settings window logic (all tabs) |
| `electron_gui/renderer.js` | Dashboard logic |
