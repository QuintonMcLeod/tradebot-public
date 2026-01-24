
# 4. Map & Table of Contents
> *"Where is `main.py` again?"*

The project structure is classic Python with an Electron GUI layer on top.

---

## The Map

```text
/
├── config/                     # User Settings
│   ├── settings_profiles.yaml  # <--- THE MAIN CONFIG (Profiles, Strategies, Symbols)
│   └── settings_base.yaml      # API Key placeholders (don't commit secrets!)
│
├── scripts/                    # Entry points
│   ├── tradebot.sh             # <--- THE BIG RED BUTTON (Start Script)
│   ├── run_dev_bot.py          # Python Entry (runs the loop)
│   └── run_tmux_dashboard.sh   # The cool UI launcher
│
├── src/
│   └── tradebot_sci/
│       ├── main.py             # Startup logic
│       │
│       ├── runtime/            # The Loop
│       │   └── loop.py         # The Heartbeat
│       │
│       ├── strategy/           # The Brain (Multi-Strategy Arsenal)
│       │   ├── engine.py       # Decision orchestrator
│       │   ├── factory.py      # Strategy instantiation
│       │   ├── profiles.py     # Profile-specific overrides
│       │   └── variants/       # Individual strategy implementations
│       │       ├── rubberband_reaper.py   # Mean reversion + anti-martingale
│       │       ├── robocop.py             # Aggressive trending
│       │       ├── evolution.py           # NTZ scalping
│       │       ├── quantum.py             # Trend following
│       │       ├── mean_reversion.py      # Classic BB + RSI
│       │       ├── hyper_scalper.py       # Fast EMA crossover
│       │       ├── london_breakout.py     # Session breakout
│       │       ├── volatility_breakout.py # Range compression
│       │       └── aggregator.py          # Multi-strategy parallel
│       │
│       ├── broker/             # The Hands (Multi-Broker Support)
│       │   ├── broker_factory.py   # Broker instantiation
│       │   ├── ibkr_broker.py      # Interactive Brokers
│       │   ├── oanda_broker.py     # OANDA Forex
│       │   └── ccxt_broker.py      # Crypto (Coinbase, Kraken, Binance)
│       │
│       ├── market/             # The Eyes
│       │   ├── providers.py    # Data fetching
│       │   └── models.py       # Candle, Ticker definitions
│       │
│       ├── utils/              # Utilities
│       │   └── symbol_classifier.py  # Asset class detection
│       │
│       └── electron_gui/       # The Dashboard (Electron)
│           ├── main.js         # Electron main process
│           ├── renderer.js     # Dashboard logic
│           ├── settings.html   # Settings window
│           ├── settings.js     # Settings logic
│           ├── settings.css    # Settings styles
│           └── package.json    # Node dependencies
│
├── Documentation/
│   └── RTFM/
│       ├── 01_PHILOSOPHY.md        # The Why (Start Here)
│       ├── 02_SKELETON_ARCH.md     # The Anatomy (Architecture)
│       ├── 03_FUNCTIONS_DATA.md    # The Technicals (Data Objects)
│       ├── 04_MAP_TOC.md           # The Map (You Are Here)
│       ├── 05_COOKBOOK.md          # The Recipes (How-To)
│       ├── 06_PANIC_BUTTON.md      # Troubleshooting
│       ├── 07_COCKPIT_CONTROLS.md  # Configuration Guide
│       ├── 08_API_SETUP.md         # API Connection Guide
│       ├── 09_TRADING_STRATEGIES.md # All 9 Strategies Explained
│       ├── 10_THE_ANCIENT_OATHS.md # AI Guidelines
│       ├── 11_GHOST_IN_MACHINE.md  # AI & Strategy Logic
│       ├── 12_TIME_MACHINE.md      # Backtesting
│       └── 13_ENV_VARS.md          # Environment Variables Reference
│
├── docs/                       # Implementation Plans
│   └── IMPLEMENTATION_PLAN_MULTI_STRATEGY.md
│
├── logs/                       # Where the bot screams into the void
│   └── tradebot.log            # The main log file
│
└── .env                        # YOUR SECRETS (API Keys). Not in git.
```

---

## Quick Navigation

| Task | Go To |
|------|-------|
| Change **what symbols** to trade | `config/settings_profiles.yaml` → `symbols:` |
| Change **which strategy** per asset | `config/settings_profiles.yaml` → `strategies:` |
| Change **how strategies work** | `src/tradebot_sci/strategy/variants/` |
| Fix a **broker API error** | `src/tradebot_sci/broker/` |
| Configure **IBKR connection** | Settings GUI → Brokers → IBKR |
| Configure **OANDA connection** | Settings GUI → Brokers → OANDA |
| Configure **crypto exchange** | Settings GUI → Brokers → CCXT |
| View **logs** | `tail -f logs/tradebot.log` |
| Open **Settings GUI** | `./scripts/tradebot.sh --settings` |

---

## Key Files by Purpose

### Strategy Selection
| File | Purpose |
|------|---------|
| `settings_profiles.yaml` | Per-asset strategy mapping |
| `strategy/factory.py` | Creates strategy instances |
| `utils/symbol_classifier.py` | Detects asset class from symbol |

### Broker Connections
| File | Purpose |
|------|---------|
| `broker/ibkr_broker.py` | Stocks, Futures, Options |
| `broker/oanda_broker.py` | Forex pairs |
| `broker/ccxt_broker.py` | Crypto exchanges |

### GUI
| File | Purpose |
|------|---------|
| `electron_gui/main.js` | Electron main process |
| `electron_gui/settings.js` | Settings window logic |
| `electron_gui/renderer.js` | Dashboard logic |
