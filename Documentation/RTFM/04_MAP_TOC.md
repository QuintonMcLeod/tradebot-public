
# 4. Map & Table of Contents
> *"Where is `main.py` again?"*

The project structure is classic Python, but with some extra clutter we plan to clean up eventually.

## The Map

```text
/
├── config/                     # User Settings
│   ├── settings_profiles.yaml  # <--- YOU PROBABLY WANT THIS ONE (Symbol Lists, Strategy Params)
│   └── settings_base.yaml      # API Keys placeholders (don't commit secrets here!)
│
├── scripts/                    # Entry points
│   ├── tradebot.sh             # <--- THE BIG RED BUTTON (Start Script)
│   ├── run_dev_bot.py          # Python Entry (runs the loop)
│   └── run_tmux_dashboard.sh   # The cool UI launcher
│
├── src/
│   └── tradebot_sci/
│       ├── main.py             # Startup logic
│       ├── runtime/            # The Loop
│       │   └── loop.py         # The Heartbeat
│       ├── strategy/           # The Brain
│       │   ├── engine.py       # The Logic
│       │   └── profiles.py     # The Personalities
│       ├── broker/             # The Hands
│       │   └── ccxt_broker.py  # Crypto Execution
│       └── market/             # The Eyes
│           └── providers.py    # Data fetching
│
├── Documentation/
│   └── RTFM/
│       ├── 01_PHILOSOPHY.md        # The Why (Start Here)
│       ├── 02_SKELETON_ARCH.md     # The Anatomy
│       ├── 03_FUNCTIONS_DATA.md    # The Technicals
│       ├── 04_MAP_TOC.md           # The Map (You Are Here)
│       ├── 05_COOKBOOK.md          # The Recipes
│       ├── 06_PANIC_BUTTON.md      # Troubleshooting (READ ME WHEN SCREAMING)
│       ├── 07_COCKPIT_CONTROLS.md  # Configuration Guide
│       ├── 08_GHOST_IN_MACHINE.md  # AI & Strategy Logic
│       ├── 09_TIME_MACHINE.md      # Backtesting & Simulation
│       └── 10_THE_ANCIENT_OATHS.md # THE SACRED COMMANDMENTS (READ FIRST)
│
├── logs/                       # Where the bot screams into the void.
│   └── tradebot.log            # The main log file.
│
└── .env                        # YOUR SECRETS (API Keys). Not in git.
```

## How to Navigate
*   **If you want to change WHAT it trades:** Go to `config/settings_profiles.yaml`.
*   **If you want to change HOW it trades:** Go to `src/tradebot_sci/strategy/engine.py`.
*   **If you want to fix an API error:** Go to `src/tradebot_sci/broker/ccxt_broker.py`.
*   **If you want to stare at logs:** `tail -f logs/tradebot.log`.
