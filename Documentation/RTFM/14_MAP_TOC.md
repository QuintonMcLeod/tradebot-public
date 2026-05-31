---
title: 14 Lost in the Codebase? The Complete Navigation Map
category: rtfm
icon: map
description: "\"Where is main.py again?\" The project structure is classic Python\
  \ with an Electron GUI layer on top. This is the complete navigational map of the\
  \ entire repository \u2014 every directory, every module, every source file \u2014\
  \ organized as a tree with annotations explaining what each piece does and how it\
  \ relates to the whole."
---

# 14. The Map — Complete Project Navigation

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"Lost? Good. That means you're looking for the map. This IS the map. The complete directory structure, every file's purpose, and quick navigation to wherever you need to go.<br><br>Think of this as the airport terminal map. You don't need to visit every gate — just find the one that gets you where you're going."</td></tr></table>

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"Where is main.py again?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Are you blind? It's right there. Look down!"</td></tr></table>

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
│       │   └── variants/       # 36 Individual strategy implementations
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
│       │       ├── aggregator.py           # Multi-Strategy Parallel
│       │       ├── qs_sma_filter.py        # 📈 QS 200-SMA Filter
│       │       ├── qs_golden_cross.py      # 📈 QS Golden Cross
│       │       ├── qs_rsi_mean_reversion.py# 📈 QS RSI-2 Mean Reversion
│       │       ├── qs_3_10_trend.py        # 📈 QS 3/10 Trend Follower
│       │       ├── qs_tqqq_btal.py         # 📈 QS TQQQ/BTAL Rebalancer
│       │       ├── qs_choppiness.py        # 📈 QS Choppiness Index
│       │       └── qs_first_day_month.py   # 📈 QS Seasonal First DOM
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
│       ├── 09_FEET_WET_STRATEGY.md # All 36 Strategies Explained
│       ├── 10_THE_ANCIENT_OATHS.md # AI Guidelines
│       ├── 11_GHOST_IN_MACHINE.md  # AI & Strategy Logic
│       ├── 12_TIME_MACHINE.md      # Backtesting Methods
│       ├── 13_ENV_VARS.md          # Environment Variables Reference
│       ├── 45_QUANTITATIVE_STRATEGIES.md # 📈 7 Advanced Algorithms Explained
│       ├── 51_MINOVSKY_PARITY.md   # Temporal Parity & Minovsky Engine
│       ├── 52_EXIT_ROUTER.md       # Universal Exit Router & Shields
│       └── 53_ACCOUNTING_PHYSICS.md # PnL Integrity & Cost Basis Physics
│
├── logs/                       # Where the bot screams into the void
│   └── tradebot.log            # The main log file
│
└── .env.secrets                # YOUR SECRETS (API Keys). Not in git.
```

---

## Quick Navigation

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Stop whining and wandering around the codebase like a lost tourist. Tell me what you want to do, and I'll tell you which file to break:"</td></tr></table>

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

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"If the directory tree above is the map, this is the legend. Organized by function, not by folder."</td></tr></table>

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

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"If you read this whole page and you're still lost, you shouldn't be operating a computer. Seriously. This map is foolproof. Stop skimming and actually read the words I wrote for you!"</td></tr></table>

---

## 📖 Continue Reading

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"Wow, okay I think I get it now. What's next?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Turn the page. We are going to talk about <b>Cockpit Controls</b>. Try to keep up."</td></tr></table>
