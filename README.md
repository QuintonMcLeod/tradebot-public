# Tradebot-Sci

> **Looking for the Manual?**
> Stop reading this boring file.
> Go to [Documentation/RTFM/](Documentation/RTFM/) for the guide that actually explains things.
> Start with `01_PHILOSOPHY.md` to understand why this bot exists.

> [!CAUTION]
> **USE AT YOUR OWN RISK.**
> 
> The author is in **no way, shape, or form responsible** for what this application may or may not do.
> 
> This is an automated trading tool that executes real orders with real money. If you decide to put your life savings into an account and have the bot gamble it away, **that is on you.**
> 
> **You have been warned.** Test thoroughly on paper/sim before risking a Single. Cent.

Tradebot-Sci is an automated ICC trading system for IBKR, Crypto (via CCXT), and Futures. This repo scans a symbol universe (equities, ETFs, forex, crypto) every cycle, finds the cleanest structure, feeds it into the ICC prompt, enforces hard gates, and (if you allow it) executes live orders with real-world safeguards (local stops, crypto routing, strike tracker cooldowns).

## What this does for you (ICC trader, plain English)

If you are learning ICC and you want to trade like an ICC trader (patient, selective, no forcing), this bot is built to behave that way:

- **AI-powered ICC decisioning (Trade By SCI style)**: the prompt is designed to think, talk, and evaluate like an A-student from the 12-day course, especially around A+ continuation windows.
- **ICC “stand aside” is the default**: it will not manufacture trades. When ICC gates are not met, it prints exact reason codes (ex: `NO_SWEEP`, `NO_CONTINUATION`, `HTF_LTF_MISALIGNED`) so “no trade” feels like a decision, not a mystery.
- **`selection_score` vs `readiness` matches real workflow**: `selection_score` answers “which chart should I watch right now?” and `readiness` answers “is this actually an A+ ICC window yet?”. That keeps you from confusing “active symbol” with “enter now.”
- **Deterministic ICC gates (not vibes)**: the AI can suggest an idea, but the bot still enforces ICC gates and venue rules before any order is allowed. That is execution discipline.
- **A+ session gates (12-day alignment)**: when a continuation is truly A+, the bot requires range + volume expansion (plus time-of-day bias for FX/crypto) before it will enter. No dead-session gambling.
- **Auto-schedule (`auto_schedule`)**: equities during US hours, crypto off-hours, and it can respect Sabbath windows. One setup, less babysitting.
- **PairSelector + friction guards**: when data is available, the bot filters by spread/depth/volume so you are not trading thin junk that looks pretty but executes horribly.
- **Venue-aware execution**: if a venue is long-only (ex: IBKR spot crypto), it will not attempt shorts. It blocks the action and explains why.
- **Safety is built-in**: risk caps, cooldown/strike logic, synthetic/local stop fallbacks so protection still works when a broker cannot place native stops.
- **Clean operator experience**: one command (`./scripts/tradebot.sh`) launches tmux with live log on the left and optional AI commentary on the right.
- **Commitment mode (manage > re-decide)**: once in a position, the bot stays in management mode and exits only on invalidation/protection rules.
- **Guardrails against “oops” trading**: live mode requires explicit trading-universe confirmation (`YES:...`) before broker activity starts.
- **Runs how you actually trade**: `scheduled` for session windows, `continuous` for 24/7 (still honoring market hours), `iterations` for controlled testing.
- **Replay + audit ready**: logs are structured so you can reconstruct the “why” bar-by-bar.
- **Scales from learning mode to live**: run `EXECUTE_TRADES=false` to observe, then flip `EXECUTE_TRADES=true` when you trust it.

### Why this aligns with Trade By SCI’s philosophy

Trade By SCI is about structure-first patience, not constant action. This bot is built to:

- **Wait for the model** (HTF alignment → correction/sweep → continuation) instead of early reaction entries.
- **Say “no” loudly and clearly** via gates + reason codes, so discipline is enforced without guesswork.
- **Stay tradable in real venues** by enforcing venue constraints (no fake shorts on long-only spot, no spam when orders are rejected).
- **Be auditable** so the edge can be reviewed, improved, and trusted (you can replay decisions, not just see a P&L number).
- **Target HTF structure** for exits: take-profits align to the next HTF swing level, while exits are held until HTF invalidation unless emergency protection triggers.

### How it can help you flip (realistic framing)

No bot can promise profits, and this is not financial advice.

ICC “flipping” is not built on smooth monthly compounding. It is built on **lumpy expansion capture**:

> long periods of nothing → short bursts of violent continuation → repeat

So the right question is not “what is my average month?” It is:

> **How many A+ continuation windows did I capture this week?**

An ICC “normal week” can have multiple continuation legs. The count depends on whether the market is trending clean or chopping.

### One-Month "Account Flip" Roadmap ($980 Start)

The following illustrates the mathematical potential of the **50% Risk Pyramid** (10% per entry) over a 30-day period. 

> [!CAUTION]
> **50% RISK IS EXTREME**: This roadmap assumes catching "Full Send" trends. A single stop-out on a full pyramid results in a 50% drawdown. Two consecutive losses can zero the account.

**Target: $980 ➔ $30,000+ Potential**

- **Week 1: The "Forex Bridge" Sprint**
  - **Focus**: BTC, ETH, SPY, QQQ, GLD, SLV.
  - **Goal**: Cross the **$2,000 milestone** to unlock Forex/Futures.
  - **Win Case**: One clean SPY or BTC trend (3:1 RR) nets ~$1,470.
  - **Ending Balance**: **~$2,450**.

- **Week 2: Global Expansion**
  - **Focus**: All 12 symbols (EURUSD, Gold, Indices, Crypto).
  - **Goal**: Diversify and capture higher velocity.
  - **Win Case**: One successful Euro or Gold trend using the new $1,225 per-trade risk.
  - **Ending Balance**: **~$6,125**.

- **Week 3: High-Leverage Scaling**
  - **Focus**: 24/7 scanning across all uncorrelated asset classes.
  - **Goal**: Compound the gains from the $6,125 base.
  - **Win Case**: Capturing one major trend leg on any ticker (Risk: ~$3,060).
  - **Ending Balance**: **~$15,300**.

- **Week 4: The Exponential Moonshot**
  - **Focus**: Aggressive A+ setups only.
  - **Goal**: Final flip of the month.
  - **Win Case**: One final high-conviction capture (Risk: ~$7,650).
  - **Ending Balance**: **~$38,200**.

**Summary of the Math**: 
ICC continuations are high-probability but lumpy. The bot's job is to ensure you **never miss** the expansion and **never over-trade** the chop.

What the bot changes (the part that matters): it does not “make the market expand.” It increases the odds you **do not miss** the expansion and **do not bleed** during chop by enforcing stand-aside, enforcing ICC gates, and keeping execution consistent when a real continuation shows up.

In practical terms, that means:

- **It reduces “human error trades.”** New traders commonly take entries during chop, mid-correction, or before continuation confirms. The bot’s default is `stand_aside` until the required ICC gates are true, so fewer impulse trades ever get placed.
- **It reduces missed A+ windows.** A+ continuations do not announce themselves and they do not wait for you to be at your desk. The bot loops continuously/scheduled, so when a window forms it can detect it and act without fatigue or hesitation.
- **It reduces early exits and second-guessing.** Humans often bail early because the next candle looks scary. The bot follows the plan: it stays in “manage/commitment mode” and only changes course on defined invalidation/protection rules.
- **It keeps execution consistent.** Same inputs → same decision rules → same order policy. That consistency matters because ICC performance comes from repeating the same process across many cycles, not from one perfect trade.
- **It avoids untradable actions.** If the venue cannot do something (ex: long-only spot crypto), it suppresses the action before orders are spammed/rejected. That keeps the bot from “fighting the broker” instead of trading.
- **It documents the why.** Every “no trade” is tagged with gates + reason codes. That gives you a checklist you can learn from: you can see *which* gate is usually missing and whether your environment is actually producing A+ windows.

## Quickstart (recommended)

1. Install dependencies:
   ```bash
   poetry install --with gui
   ```
2. Configure:
   - IBKR: `config/broker_ibkr.yaml`
   - Runtime + schedule: `config/settings_base.yaml`
   - Profiles: `config/settings_profiles.yaml`
3. Start the GUI (recommended):
   ```bash
   ./scripts/tradebot.sh --gui
   ```
4. Configure inside the GUI:
   - Settings → AI for provider + API key
   - Settings → Time for timezone + sabbath automation
   - Settings → Bot/Strategy/Risk for ICC controls
5. Stop everything:
   ```bash
   ./scripts/tradebot.sh --exit-all
   ```

The GUI launches the same engine and can keep the bot running even if the window closes (see Settings → Bot).

## Requirements / prerequisites

1. **Python 3.11+** (Poetry enforces it via `pyproject.toml`).  
2. **Poetry** – install via [`pip install poetry`](https://python-poetry.org/docs/).  
3. **IBKR Gateway/TWS** running if you intend to execute live orders.  
4. **API credentials** for your TradeSci-compatible AI endpoint (e.g., OpenAI).

## Installation / initial setup

1. Clone repo and enter directory:
   ```bash
   git clone ... tradebot-sci-enterprise
   cd tradebot-sci-enterprise
   ```
2. Create & activate virtual env:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   poetry install
   ```
3. Copy `.env.example` → `.env` and fill in:
   * `TRADE_SCI_API_KEY` (or `CHATGPT_KEY`)
   * `TRADE_SCI_API_BASE_URL` if using a custom endpoint.
4. Configure IBKR: edit `config/broker_ibkr.yaml` to set host/port, account ID, risk caps (`max_dollar_risk_per_symbol`, `max_shares_per_symbol`), execution mode, paper/live, etc.
5. Tune runtime in `config/settings_base.yaml` and trading profiles in `config/settings_profiles.yaml`.

## CLI only (advanced)

Start the tmux dashboard directly:
```bash
./scripts/tradebot.sh
```

The dashboard runs a tmux session with two windows:
- `view`: left pane tails `logs/tradebot.log`, right pane shows optional AI commentary
- `bot`: runs the bot process (so the dashboard panes stay clean)

Help menu (lists all profiles + explains modes/iterations/Sabbath):
```bash
./scripts/tradebot.sh --help
```

### tmux basics (new users)

- Switch panes: `Ctrl-b` then arrow keys
- Switch windows: `Ctrl-b` then `n` / `p`
- Detach: `Ctrl-b` then `d`
- Kill the session: `./scripts/tradebot.sh --exit-all` (recommended)

## Historical Simulation / Benchmark Feature

**New in this release**: The GUI now includes a **Benchmark** tab in the settings dialog that lets you validate your ICC strategy against historical data before risking real capital.

### What it does

- **Fetches historical market data** from IBKR for your selected symbols and date range
- **Replays market conditions** bar-by-bar through your bot's existing ICC strategy logic
- **Generates trading signals** using the same decision engine as live trading
- **Simulates trade execution** with realistic fill assumptions
- **Tracks P&L** including stops, targets, and position management
- **Reports weekly equity** showing your capital value at the end of each week

### How to use

1. Open Settings in the GUI
2. Navigate to the "Benchmark" tab
3. Configure:
   - Initial capital (default: $10,000)
   - Start date (default: 2 years ago)
   - End date (default: today)
   - Symbols to test (select from your configured symbols)
4. Click "Run Backtest"
5. Review results:
   - Total P&L and return percentage
   - Maximum drawdown
   - Win rate and average win/loss
   - **Weekly equity curve** (money value per week)
   - Recent trade log

### Important caveats

- No slippage modeling (assumes fills at exact prices)
- Simplified execution (no order rejection, partial fills, or broker delays)
- Past performance doesn't guarantee future results
- Data quality depends on IBKR historical data availability
- May take several minutes for 2-year backtests across multiple symbols

See [Documentation/RTFM/09_TIME_MACHINE.md](Documentation/RTFM/09_TIME_MACHINE.md) for detailed instructions.

## Key concepts (keep reading before launching)

### Symbol registry + market metadata

- All tradable instruments live in `src/tradebot_sci/market/symbols.py`. Each symbol carries metadata: asset class (equity/forex/crypto/future), exchange, contract symbol, market type, enabled flag, and trading hours.  
- EWU/EWG/EWQ now inherit US-equity hours, so they are skipped until 09:30 ET. FX/crypto obey their own market-hour gates (London FX window, 24/7 crypto, etc.).
- Futures remain in the registry but immediately return `UNSUPPORTED_SYMBOL_CONFIG` (stub only for now).

### Contract router & crypto routing

- `src/tradebot_sci/market/contracts.py` builds the correct IBKR contract per symbol and honors `market.crypto_routing` from the base config.  
- BTCUSD defaults to a ZEROHASH contract (`Crypto('BTC', 'ZEROHASH', 'USD')`), and overrides let you point ETH/SOL at either PAXOS or ZeroHash. Defining them here means structure scoring and execution use the same contract.

### Risk engine + StrikeTracker

- Every decision runs through `_prepare_entry`, which uses `per_share_risk`, remaining risk budget, buying-power guard, and strike tracker state to size the bracket.  
- Risk guards log the budget, candidate quantity, notional needed, and buying power on suppression; repeated `ExecutionStatus.RISK_SUPPRESSED` increments guard strikes and eventually skips that symbol for a few cycles.  
- `ExecutionStatus.UNSUPPORTED_SYMBOL_CONFIG` also gets tracked so misconfigured tickers (missing contracts, missing data permissions, stop rejection) are temporarily bench-blocked.

### Local-stop fallback

- ZEROHASH rejects `StopOrder` (error 387) for SOLUSD/BTCUSD; the executor now recognizes this, marks those symbols as `local_stop` protection, and enforces stops by monitoring live prices and issuing market orders when the stop level triggers.  
- `runtime.allow_local_stops` enables the client-side fallback, while `runtime.local_stop_symbols` lists exceptions (SOLUSD/BTCUSD by default).  
- When a local stop fires, you see `[EMERGENCY_FLATTEN] SYMBOL ...` and the strike tracker receives an `ExecutionStatus.EXECUTED`.

### Synthetic-stop persistence & restart safety

- ZEROHASH crypto synthetic stops are now persisted to `data/synthetic_stops.json` (override via `profile.synthetic_stop_store_path` or the `SYNTH_STOP_STORE_PATH` environment variable).  
- `run_bot`/`run_scheduled_bot` replay that store on startup through `executor.reconcile_synthetic_stops()`, re-arming stops, clearing stale entries, and running the selected `crypto_startup_naked_policy` (`FLATTEN`, `REARM`, `PAUSE`, `IGNORE`).  
- You will see `[CRYPTO][PERSIST]`, `[CRYPTO][STARTUP]`, `[CRYPTO][INTEGRITY]`, and `[CRYPTO][SAFETY]` logs describing persistence writes, reconciliation outcomes, integrity corrections, and naked-position actions.

### Profiles & session behavior

- Profiles live in `config/settings_profiles.yaml`. Each profile sets `candle_timeframe`, polling cadence, and `auto_flatten_on_close`.  
- `intraday` is the default: it cancels orders and flattens at the end of each scheduled session, matching the previous “safe” behavior.  
- `crypto_247` runs continuously, keeps all orders open across cycles, and skips auto-flatten/disconnect so crypto can stay live 24/7. Use `PROFILE_NAME=crypto_247` along with `--continuous` for an always-on run.
- `all_247` is the new “global 24/7” profile that keeps the full symbol universe (equities, FX, futures stub, and crypto), never auto-flattens or disconnects, and still honors PDT guard limits plus synthetic-stop persistence/fractional crypto sizing so global markets stay protected.  
- `auto_schedule` switches the trading universe automatically: equities during US market hours, crypto during off-hours, and blocks new entries during Sabbath by default. Use `PROFILE_NAME=auto_schedule` with `--continuous`.
- Each profile can tune `symbols`, `crypto_fractional_enabled`, `crypto_qty_steps`, `crypto_min_notional_usd`, `cryptomax_notional_usd`, `synthetic_stop_persistence_enabled`, and `crypto_startup_naked_policy` to align with your account size and safety preferences.

### ICC structure + A+ gating (12-day course alignment)

The ICC model here follows the course flow:

- **Trend (Day 1) - `HTF/LTF Trend Identification`**: The bot systematically analyzes price action on both Higher Timeframes (HTF) and Lower Timeframes (LTF) to identify clear trends. It programmatically looks for sequences of Higher Highs/Higher Lows (HH/HL) for uptrends and Lower Highs/Lower Lows (LH/LL) for downtrends. This is not based on "slope inference" but on the confirmed structural breaks of previous swing points, providing a deterministic method to align with the core ICC principle of trading with the trend. HTF defines the macro direction, while LTF helps confirm the immediate context.
- **Indication (Day 2) - `Clean Break Confirmation`**: The bot identifies an "indication" when price executes a `clean close` beyond the most recent swing high (for bullish indications) or swing low (for bearish indications). This is not merely a wick but a confirmed candle close, providing a clear and objective signal that momentum is shifting or confirming a potential trend continuation as taught in Day 2 of the ICC course. This programmatic detection removes subjective interpretation of "breaks."
- **Liquidity & Correction (Day 3) - `Smart Retracements & Sweeps`**: A crucial hard gate in the bot's ICC model is the validation of `liquidity sweeps` during corrections. After an indication, the bot expects a retracement that actively "sweeps" or tests key liquidity areas (e.g., previous lows in an uptrend, previous highs in a downtrend). This confirms that sufficient orders have been absorbed, setting the stage for a strong continuation. If a correction does not demonstrate a clear liquidity sweep in the opposing direction, the bot will `stand_aside`, preventing premature entries based on weak pullbacks.
- **Entry (Day 4-6) - `Algorithmic Continuation Trigger`**: The bot's entry mechanism is highly precise, requiring a confluence of factors beyond just a simple break and retest. For a bullish entry, it looks for a confirmed Higher Low (HL) followed by a Break of Structure (BOS) – a clean close past the previous local high. Crucially, the entry is triggered only upon a subsequent `continuation close` beyond the correction range, signaling sustained momentum. The inverse applies for bearish entries (Lower High (LH) + BOS). This multi-factor algorithmic confirmation ensures entries align with high-probability ICC setups, minimizing entries during false breaks or consolidations.
- **Timeframe Correlation (Day 6) - `Hierarchical Market View`**: The bot strictly adheres to the principle of timeframe correlation. The Higher Timeframe (HTF) analysis always `defines the prevailing direction` or bias, ensuring trades are only taken in alignment with the broader market context (e.g., if HTF is bullish, only long entries are considered). The Lower Timeframe (LTF) is then exclusively used to `confirm execution` details, pinpointing the precise entry trigger (sweeps, BOS, continuation) with surgical accuracy. This layered approach prevents counter-trend trades and filters out lower-timeframe noise, embodying patience and strategic alignment.
- **Markup & Structure Targets (Day 7/10) - `Automated Profit Taking`**: Consistent with ICC methodology, the bot's take-profit strategy is not arbitrary. It `aligns to the next Higher Timeframe (HTF) swing level`, ensuring that profit targets are based on significant structural points in the market, rather than fixed percentages or arbitrary values. This systematic approach aims to capture substantial moves when the market is trending cleanly. Exits are typically held until HTF invalidation or emergency protection triggers, preventing premature closure of winning trades as price extends towards its logical structural target.
- **Decision Discipline (Day 11-12) - `High-Probability A+ Entry Gates`**: The bot strictly enforces the `A+ entry criteria` by requiring multiple confluent factors before initiating a trade. This includes validated range expansion, significant volume expansion, and alignment with favorable session bias (e.g., London/New York overlap for FX/Crypto). These hard gates prevent "dead-session gambling" and ensure that the bot only engages when market conditions are most conducive to violent continuation, reflecting the patience and selectivity emphasized in ICC decision-making and trading psychology. If all gates are not precisely met, the bot will default to `stand_aside`.

These are enforced deterministically, and the AI is only allowed to proceed once the gates are true.

### ICC Risk Methodology: "Hybrid Flip" (Feet Wet -> Full Send)

The bot implements the **"Hybrid Flip"** strategy: start tiny, confirm validity, then pyramid aggressively.

#### The "Feet Wet" Phase (Probe)
Every trade starts with **Micro-Risk**:
- **Risk per trade**: 1.0% (The "Cup of Coffee" rule).
- **Goal**: Survival. You can take 10 losses in a row and only be down ~10%.
- **Win Rate**: Expect ~27%. You *will* loose frequent small amounts.

#### The "Full Send" Phase (Pyramid)
When a probe survives and hits **0.15% profit**, the bot flips to Aggression:
- **Pyramid Entry #1 (The Load)**: Adds **30% Risk** (using open profits to finance risk).
- **Scale Entries #2-6**: Adds **10% Risk** per leg as trend continues.
- **Stop Management**: Moves to Breakeven immediately upon Pyramiding.

**The Math:** One "Full Send" trend run covers 10+ "Feet Wet" losses.

### Profiles & session behavior

- Profiles live in `config/settings_profiles.yaml`.
- **`forex_intraday` (Recommended)**: The default 24/7 strategy for Forex, Crypto, and Commodities. Despite the name, it is **Continuous** (no forced flattening).
- **`crypto_247`**: Dedicated crypto-only loop.
- **`intraday`**: Legacy equity profile.

**Note:** All profiles now default to **Continuous Operation**. The bot will NOT force-close your positions at the end of a session unless explicitly configured to do so. We let winners run.  
- `scalp`/`swing`: exist for completeness and are selectable via `PROFILE_NAME`.

### Aggressive mode defaults (Trade By SCI)

Profiles now default to the Trade By SCI aggressive template:

- `PROFILE_ICC_AGGRESSIVE_MODE=true`
- `PROFILE_AGGRESSIVE_RISK_PER_TRADE_PCT=0.03`
- `PROFILE_MAX_DAILY_LOSS_PCT=0.06`
- `PROFILE_MAX_EXPOSURE_PCT=0.40`
- `PROFILE_MAX_CONSECUTIVE_LOSSES=2`

Disable aggressive sizing by setting `PROFILE_ICC_AGGRESSIVE_MODE=false` in the GUI or environment.

### ICC session gating knobs (profile overrides)

Set via profile YAML or env overrides (use the Settings GUI):

- `PROFILE_SESSION_GATE_ENABLED` (default true)  
- `PROFILE_SESSION_GATE_MIN_CANDLES` (default 30)  
- `PROFILE_SESSION_RANGE_MULTIPLIER` (default 1.1)  
- `PROFILE_SESSION_VOLUME_MULTIPLIER` (default 1.1)  
- `PROFILE_SESSION_OVERLAP_START_HOUR` / `PROFILE_SESSION_OVERLAP_END_HOUR` (default 12–16)  
- `PROFILE_SESSION_OVERLAP_TIMEZONE` (default UTC)  

## Running the bot

### Recommended: tmux dashboard

```bash
./scripts/tradebot.sh
```

Common examples:

```bash
# Stocks during US market hours, crypto off-hours (plus Sabbath by default)
./scripts/tradebot.sh --profile auto_schedule --mode continuous

# Intraday equities: scheduled windows (from config/settings_base.yaml:schedule.sessions)
./scripts/tradebot.sh --profile intraday --mode scheduled

# Crypto-only always-on
./scripts/tradebot.sh --profile crypto_247 --mode continuous
```

Live trading (careful):

```bash
./scripts/tradebot.sh --profile intraday --mode scheduled --execute-trades true
```

### Direct python (advanced)

```bash
# Simulation/dev run: N iterations then exit
PROFILE_NAME=intraday PYTHONPATH=src EXECUTE_TRADES=false poetry run python scripts/run_dev_bot.py --iterations 120

# Scheduled mode (uses config/settings_base.yaml:schedule.sessions)
PROFILE_NAME=intraday PYTHONPATH=src EXECUTE_TRADES=true poetry run python scripts/run_dev_bot.py --scheduled

# Continuous mode
PROFILE_NAME=crypto_247 PYTHONPATH=src EXECUTE_TRADES=true poetry run python scripts/run_dev_bot.py --continuous
```

### Environment Overrides

- `EXECUTE_TRADES=true` enables live execution (otherwise it is a dry-run).  
- `EXCHANGE_PROVIDER=primary|alternative` overrides `market.exchange_provider` (use `alternative` to run the safe mock broker/market provider while wiring a real exchange plugin).  
- `ALTERNATIVE_BROKER=mock|ccxt` overrides `market.alternative_broker` when `EXCHANGE_PROVIDER=alternative` (use `ccxt` for real crypto execution).  
- `CCXT_EXCHANGE=<id>` selects the ccxt exchange id (example: `binance`).  
- `CCXT_API_KEY` / `CCXT_SECRET` / `CCXT_PASSWORD` provide exchange credentials (exchange-dependent).  
- `CCXT_SYMBOL_MAP="BTCUSD:BTC/USDT,ETHUSD:ETH/USDT,SOLUSD:SOL/USDT"` maps bot symbols to ccxt symbols.  
- `TRADING_CONFIRMATION=YES:<symbols>` lets you pre-approve the exact trading universe reported at startup (the bot logs `will_trade=[...] instrument_classes=[...]`). When `EXECUTE_TRADES=true` the process now prompts you to type that string (`YES:BTCUSD,ETHUSD,SOLUSD`) or exit; a mismatch/omission aborts before any IBKR work begins.
- `PROFILE_NAME=...` switches profile definitions (you can set this in `.env`).  
- `MARKET_SYMBOLS` lets you override `market.symbols` via a comma-separated list for quick experimentation.  
- `BUG_BYPASS_SCHEDULE=1` or `--continuous` bypass cron-like session gaps.
- `--sabbath` forces Sabbath-mode entry blocking even if the profile does not set `sabbath_enabled`.
- `--no-sabbath` disables Sabbath blocking even if the active profile enables it.
- `COMMENTARY_LLM=off|adviser` controls the tmux right-pane commentary mode (`./scripts/tradebot.sh --commentary ...`).
- `COMMENTARY_LLM_MIN_SECONDS=45` sets a minimum spacing between commentary refreshes.

## Detailed Environment Variable Reference

This section provides comprehensive details for each environment variable,
including its purpose, usage, and any relevant safety notes or ICC guidance.

---

### GUI Settings

| Environment Variable | Description |
|----------------------|-------------|
| `GUI_AUTOSTART_BOT` | **Automatically start the core bot process when the GUI opens.**<br>On GUI launch, the app checks whether the bot is already running. If it is NOT running, the GUI starts it using your current settings. If it IS already running, the GUI attaches to the existing logs/state (no duplicate bot). How to use: Enable this if you want the GUI to be your “one-click launcher”. Disable this if you prefer starting the bot from tmux/terminal first. Important safety note: If `EXECUTE_TRADES=true`, you will still be asked to confirm live trading in the GUI. The confirmation is there to prevent accidental live orders. |
| `GUI_KEEP_BOT_RUNNING` | **Keep the bot running even after you close the GUI window.**<br>Why you’d use this: You want a desktop view temporarily, but you want the bot to keep running in the background. You want tmux/terminal users to continue seeing the dashboard after the GUI closes. How it behaves: Closing the GUI will not stop the bot. The bot will keep writing to the log file and managing positions (if enabled). How to stop the bot: Use the tmux launcher to restart/stop, or stop the process from your OS tools. If live trading is enabled, always make sure you intentionally stop it. |
| `GUI_LOG_BROWSE` | **Pick which log file the GUI (and tmux log tail) reads.**<br>What this is: The bot writes structured events (decisions, broker actions, errors) to a log file. The GUI uses that same file to populate Current Ticker, Recent Decisions, Orders, and more. How to use: Choose the active log (usually `logs/tradebot.log`). If you want historical context, you can point it to a rotated file (`logs/tradebot.log.1`, etc.). Tip: If something “looks empty”, make sure you are looking at the active log, not an older rotated log. |
| `TMUX_RESTART_PREVIEW` | **Shows the exact tmux restart command that will be executed.**<br>Why this exists: The tmux launcher (`./scripts/tradebot.sh`) is the source of truth for how the terminal dashboard is launched. When you restart panes, this preview lets you verify the command is what you expect. How to use: Review it before clicking “Restart tmux”. If you see unexpected flags (profile/mode/execute-trades), adjust settings first. Safety note: Restarting tmux panes should keep the session open and respawn bot + commentary panes inside tmux. |
| `GUI_BROWSE_SYNTH_STOP_STORE` | **Choose where to store synthetic stop state on disk.**<br>What this is: The bot can persist synthetic stop details so it can manage a position safely after restarts. This button fills `SYNTH_STOP_STORE_PATH` for you. How to use: Choose a writable path (JSON file). Keep it stable (don’t change it mid-trade) unless you understand the implications. Why it matters: If this file is missing/unwritable, some safety routines may treat the position as “unprotected”. |
| `GUI_BROWSE_POSITION_HOLD_STORE` | **Choose where to store position-hold/age state on disk.**<br>What this is: The bot can persist “hold rules” (e.g., minimum hold time) across restarts. This button fills `POSITION_HOLD_STORE_PATH` for you. How to use: Choose a writable path (JSON file). Keep it stable so the bot can correctly remember how old positions are. Why it matters: Without persistence, the bot may be forced into conservative safety actions after a restart. |
| `ENV_FILTER` | **Filter the Advanced env table by key.**<br>How to use: Type part of a key (case-insensitive). Examples: `IBKR_`, `CCXT_`, `TRADE_SCI_`, `COMMENTARY_`, `EXECUTE_TRADES`. Why this exists: The bot has many configuration switches; this helps you find the one you need quickly. |
| `ENV_TABLE_EDIT` | **Advanced mode: edit raw environment variables directly.**<br>What this is: A full list of discovered env keys used by the bot and dashboard. Useful for advanced tuning or for settings that don’t have a dedicated toggle yet. How to use: Double-click a Value cell to edit it. Click “Apply (GUI)” to apply changes to the running GUI session. Click “Save to .env” to persist for future runs. Important rules: Typed controls in the other tabs take precedence when they exist. Secret keys are masked in this table; set them in the typed tabs instead. Safety note: Be careful changing broker/live-trading keys here; prefer the dedicated controls. |
| `BTN_APPLY` | **Apply changes immediately to THIS running GUI session.**<br>What it affects: Updates the GUI’s in-process overrides. Can change what the GUI displays and how it launches/restarts other components. What it does NOT do: It does not automatically rewrite your `.env` file. It does not automatically restart tmux/bot processes. When to use: When you want to test changes safely before committing them. |
| `BTN_SAVE_DOTENV` | **Persist your current settings to the `.env` file.**<br>What this does: Writes your selected values so future runs start the same way. Helps keep tmux/GUI behavior consistent across restarts. When to use: After you’ve confirmed the settings are correct. Safety note: Saving `EXECUTE_TRADES=true` means future runs will be configured for live trading. The GUI still asks you to confirm live trading before starting. |
| `BTN_RESTART_TMUX` | **Restart the terminal dashboard panes (bot + commentary) inside the tmux session.**<br>What this does: Applies and saves settings, then runs the tmux restart routine. Keeps the tmux session open and respawns the panes. When to use: When you changed bot settings that only take effect on process start. When you want the terminal dashboard to match the GUI configuration. Safety note: If live trading is enabled, confirm you intended that before restarting. |
| `BTN_CLEAR_OVERRIDES` | **Remove all GUI overrides and fall back to your baseline config.**<br>What this does: Clears settings you changed in the GUI that were not saved to `.env`. Reverts to values from `.env` and/or your shell environment. When to use: Something looks wrong and you want to return to a known-good baseline quickly. |
| `BTN_CLOSE` | **Close this settings dialog.**<br>Note: Closing the dialog does not automatically apply changes. Use Apply / Save / Restart as needed before closing. |

### Profile-Related Settings

| Environment Variable | Description |
|----------------------|-------------|
| `PROFILE_NAME` | **Pick a profile that defines how the bot behaves.**<br>What it controls: Which symbols/universe the bot scans and trades. Default timeframe (e.g., 5m) and scan/decision cadence. Auto-schedule behavior (equities during US hours, crypto off-hours). Sabbath behavior defaults (whether new entries are blocked in the Sabbath window). Risk/stop behaviors that are profile-dependent (where configured). How to use: Start with `auto_schedule` for “equities in-hours, crypto off-hours”. Use an intraday profile for tighter cadence; use swing for slower cadence. Where it comes from: Profiles are defined in `config/settings_profiles.yaml` and loaded by the bot. |
| `PROFILE_HTF_TIMEFRAME` | **Override the Higher Timeframe (HTF) used for ICC structure trend.**<br>ICC guidance: HTF defines the macro structure (HH/HL vs LH/LL). Default is 4h unless your profile specifies otherwise. How to use: Use 4h for standard ICC structure. Use 1h only if your ICC plan is intentionally faster and validated. Leave Auto to keep the profile default. |
| `PROFILE_LTF_TIMEFRAME` | **Override the Lower Timeframe (LTF) used for ICC execution structure.**<br>ICC guidance: LTF is where sweeps + BOS + continuation triggers are validated. If unset, the bot uses the profile candle timeframe. How to use: Use 15m or 5m for most ICC execution work. Leave Auto to keep the profile default. |
| `PROFILE_TREND_WINDOW` | **Number of candles used to classify HTF structure trend.**<br>ICC guidance: Larger windows reduce noise but respond slower. Smaller windows respond faster but can misclassify chop. How to use: Keep the profile default unless you know the asset’s structure cadence. |
| `PROFILE_LTF_TREND_WINDOW` | **Number of candles used to classify LTF structure trend.**<br>ICC guidance: LTF reacts faster than HTF; keep it aligned to recent structure. If unset, the bot uses the HTF trend window. How to use: 2–3 hours on 15m is usually 8–12 candles. Keep the profile default unless you intentionally want faster or slower flips. |
| `PROFILE_TREND_SWING_LOOKBACK` | **Fractal lookback for defining swing highs/lows on HTF.**<br>ICC guidance: A higher lookback requires more separation between swings (cleaner structure). A lower lookback is more sensitive and can classify chop as trend. |
| `PROFILE_TREND_MIN_SWINGS` | **Minimum confirmed swings needed to call a trend (HH/HL or LH/LL).**<br>ICC guidance: Higher values mean stronger confirmation, fewer trades. Lower values mean faster classification, higher noise risk. |
| `PROFILE_TREND_STRENGTH_FLOOR` | **Minimum structure strength to treat a trend as non‑neutral.**<br>ICC guidance: Strength is based on the consistency of HH/HL or LH/LL sequences. If below the floor, the trend is treated as neutral (no ICC trade). |
| `PROFILE_STRUCTURE_SCORE_THRESHOLD` | **Score threshold for structure cleanliness (ICC gating).**<br>ICC guidance: The bot still requires HTF/LTF alignment + sweep + continuation. This threshold influences selection/readiness scoring, not the hard gates. |
| `PROFILE_PDT_GUARD_ENABLED` | **Enable the PDT guard for equities.**<br>Important: This does NOT make the bot long‑only. It only limits same‑day roundtrips for equities. |
| `PROFILE_MAX_EQUITY_ROUNDTRIPS_PER_DAY` | **Maximum equity roundtrips allowed per day under PDT guard.**<br>ICC guidance: A flip counts as an exit + new entry (conservative). Keep low unless you are exempt from PDT rules. |
| `PROFILE_FLIP_ACTIONS_ENABLED` | **Allow flip_to_long / flip_to_short actions.**<br>ICC guidance: Flips are reserved for confirmed HTF structure flips. Disabled by default for safety. |
| `PROFILE_FLIP_COOLDOWN_SECONDS` | **Minimum seconds between flips when PDT guard is active.**<br>ICC guidance: Prevents flip‑churn in ranges or chop. |
| `PROFILE_COOLDOWN_ENABLED` | **Enable ICC cooldowns after blocks or successes.**<br>ICC guidance: Helps avoid re‑entering during chop or failed attempts. |
| `PROFILE_COOLDOWN_CYCLES_AFTER_BLOCK` | **Number of cycles to skip after a blocked attempt.**<br>ICC guidance: Higher values reduce churn during noisy phases. |
| `PROFILE_COOLDOWN_CYCLES_AFTER_SUCCESS` | **Number of cycles to skip after a successful entry.**<br>ICC guidance: Use small values for faster re‑evaluation; higher values reduce over‑trading. |
| `PROFILE_COOLDOWN_SCOPE` | **Cooldown scope for ICC gating.**<br>Options: - symbol: only skip the symbol that just failed/succeeded. - global: pause all symbols for the cooldown period. ICC guidance: - Use symbol scope for broad scanning. - Use global only when you want hard pauses across the entire bot. |
| `PROFILE_STICK_TO_ACTIVE_SYMBOL_UNTIL` | **How long to stick to the active symbol before rotating.**<br>Options: - cycle_end: reevaluate on the next cycle. - decision_end: hold until a decision completes. ICC guidance: - Sticking reduces churn when a structure is close to forming. |
| `PROFILE_AUTO_SCHEDULE_ENABLED` | **Enable auto‑schedule (equities in US hours, crypto off‑hours).**<br>ICC guidance: - Keeps the bot aligned with market hours without manual toggles. |
| `PROFILE_AUTO_FLATTEN_ON_CLOSE` | **Auto‑flatten at end of scheduled windows.**<br>ICC note: - Avoid this if you intend to hold ICC continuations overnight. |
| `PROFILE_CONTINUOUS_MODE` | **Keep the runtime loop alive regardless of iteration limits.**<br>Use cases: - Always‑on monitoring with ICC gating. |
| `PROFILE_CRYPTO_ONLY` | **Treat the profile as crypto‑only.**<br>ICC note: - Useful for off‑hours ICC execution when equities are closed. |
| `PROFILE_ICC_AGGRESSIVE_MODE` | **Enable aggressive ICC sizing + guardrails (Phase 2, opt‑in only).**<br>Default (Trade by SCI): - Enabled by default to reflect Trade by SCI’s preferred posture. - Guardrails still apply (max daily loss, exposure caps, circuit breaker). |
| `PROFILE_AGGRESSIVE_RISK_PER_TRADE_PCT` | **Risk per trade as % of equity when aggressive mode is enabled.**<br>Default (Trade by SCI): - 3% per trade when aggressive mode is enabled. - Applies only with PROFILE_ICC_AGGRESSIVE_MODE=true. |
| `PROFILE_MAX_DAILY_LOSS_PCT` | **Max daily loss % before blocking new entries (aggressive mode).**<br>Default (Trade by SCI): - 6% daily loss cap before blocking new entries. |
| `PROFILE_MAX_EXPOSURE_PCT` | **Max total open exposure % of equity (aggressive mode).**<br>Default (Trade by SCI): - 40% max total exposure in aggressive mode. |
| `PROFILE_MAX_CONSECUTIVE_LOSSES` | **Consecutive loss limit before blocking entries (aggressive mode).**<br>Default (Trade by SCI): - 2 consecutive losses before blocking entries. |

### Bot Runtime & General Settings

| Environment Variable | Description |
|----------------------|-------------|
| `BOT_MODE` | **Choose how long the bot runs and when it is allowed to run.**<br>Modes: - continuous: runs forever (best for always-on monitoring). - scheduled: runs only inside configured schedule windows, then exits. - iterations: runs N loops then exits (best for testing). How to use: - If you want the GUI/tmux dashboard always available, use continuous. - If you want strict “run only during sessions”, use scheduled and configure schedule windows. - If you’re validating changes safely, use iterations. |
| `BOT_ITERATIONS` | **Number of scan/decision/execution cycles when `BOT_MODE=iterations`.**<br>How to use: - Use a small number (e.g., 20–200) to test changes quickly. - If you want a longer test run without leaving it forever, increase it. |
| `EXECUTE_TRADES` | **Master switch for live order placement.**<br>What it means: - false: the bot runs in simulation mode (no live orders). - true: the bot is allowed to place live orders (subject to broker permissions and confirmation). How to use safely: - Enable it only when you intend to trade live. - The GUI will show a confirmation dialog before starting live trading. - If `IBKR_READ_ONLY=true`, orders will still be blocked even with live enabled. Common gotcha: - If you restart from tmux, the launcher preserves `EXECUTE_TRADES=true|false` via the stored BOT_CMD. |
| `BOT_SABBATH` | **Controls Sabbath entry blocking.**<br>What it does: - When Sabbath is active, the bot blocks NEW entries. - Risk management/monitoring can still run (exits/protection may still be evaluated). Options: - Auto: use the profile’s default behavior. - Force ON: always block new entries during the Sabbath window. - Force OFF: disable Sabbath blocking entirely. When to change this: - Leave Auto unless you’re doing a special test or you intentionally want to override profile behavior. |
| `APP_ENVIRONMENT` | **Optional environment tag used by configuration loaders.**<br>What this is: - A simple label like `development`, `staging`, or `production`. - Some configs/logging may change based on this value. How to use: - Leave blank if you are not using environment-specific config. - Use `development` when you want safer defaults and more diagnostics. - Use `production` only when you intend to run live/long-running. |
| `LOG_LEVEL` | **Controls how chatty the bot logs are.**<br>How to use: - INFO: normal operations. - DEBUG: more details (useful when diagnosing issues). - WARNING/ERROR: quieter logs, only problems. |
| `TRADEBOT_LOG` | **Path to the main bot log file that the GUI/tmux dashboard tails.**<br>How to use: - Keep this set to `logs/tradebot.log` unless you have a special setup. - Rotated logs `tradebot.log.1`, `tradebot.log.2`, … are used for history/context. |
| `SESSION_NAME` | **tmux session name used by the terminal dashboard.**<br>How to use: - Default is `tradebot`. - If you run multiple dashboards, give each a different session name. |
| `EMERGENCY_STOP_PCT` | **Emergency protective stop percentage used by runtime safeguards.**<br>What it is for: - A last-resort protection if a position is unprotected/missing a normal stop. How to use: - Keep small (tight) if you want immediate damage control. - Keep larger if you want to avoid forced sells on normal noise. Important: - This is not an ICC invalidation stop; it is a safety net. |
| `AUTO_RESTART_ON_ERROR` | **Auto-restart the bot if IBKR health looks stuck.**<br>What it does: - Watches IBKR connection + account summary freshness. - If the data stays stale for too long, the bot restarts itself. Why this helps: - Clears persistent IBKR timeout loops without manual restarts. Safety note: - Uses a cooldown and minimum-uptime guard to avoid restart loops. |
| `AUTO_RESTART_STALE_SECONDS` | **How long IBKR data can be stale before a restart is triggered.**<br>What it measures: - Time since the last successful IBKR account summary update. How to use: - 300s is a safe default. - Lower values restart sooner; higher values are more tolerant. |
| `AUTO_RESTART_MIN_UPTIME_SECONDS` | **Minimum uptime before auto-restart is allowed.**<br>Why it matters: - Prevents restart loops during slow boot/connect phases. |
| `AUTO_RESTART_COOLDOWN_SECONDS` | **Minimum seconds between auto-restarts.**<br>Why it matters: - Prevents rapid restart loops if IBKR remains unstable. |
| `SCALE_OUT_FRACTION` | **How much of a position to take off when scaling out.**<br>How to use: - 0.5 means sell/cover half when a scale-out condition triggers. - Use smaller fractions for smoother exits; larger for faster de-risking. Tip: - Scaling out should respect ICC continuation rules; avoid exiting too early unless invalidated. |
| `MAX_SCALE_INS_PER_LEG` | **Maximum number of adds (scale-ins) allowed for a single position leg.**<br>Why it matters: - Prevents the bot from pyramiding too aggressively. - Keeps risk bounded when continuation takes multiple pushes. How to use: - Start low (0–2). Increase only if you have strict risk caps. |
| `MIN_POSITION_SIZE_TO_SCALE` | **Minimum position size required before the bot is allowed to scale in/out.**<br>Why this exists: - Prevents noisy tiny positions from triggering complex management logic. How to use: - Leave default unless you frequently trade very small size. |
| `STARTUP_CRYPTO_UNPROTECTED_POLICY` | **What to do on startup if a ZEROHASH crypto position exists but has no persisted synthetic stop.**<br>Options: - REARM: recreate the synthetic stop (preferred to avoid forced sell). - PAUSE: keep the position but pause actions on that symbol. - FLATTEN: immediately exit (safest operationally, but can realize losses). Recommendation: - Use REARM for ICC-style continuation holding. - Use FLATTEN only if you prioritize safety over holding. |
| `SYNTH_STOP_STORE_PATH` | **Where synthetic stops are persisted (JSON file).**<br>Why this matters: - Lets the bot recover/manage stops across restarts. - Prevents “unprotected position” policies from triggering unnecessarily. How to use: - Choose a stable, writable path. - Do not delete it while positions are open. |
| `POSITION_HOLD_STORE_PATH` | **Where position hold/age state is persisted (JSON file).**<br>Why this matters: - Allows the bot to track how long a position has been held across restarts. - Enables “do not sell within X hours” style protection. How to use: - Choose a stable, writable path. - Keep it consistent across runs so the bot retains history. |
| `ALLOW_INHERITED_POSITION` | **Allow the bot to inherit/manage positions that already exist in the broker account.**<br>What this means: - When enabled, the bot will treat existing holdings as positions it must manage. - This is required if you want multi-position monitoring after restarts or manual trades. How to use safely: - Enable only if you want the bot to take responsibility for pre-existing positions. - Make sure your hold/stop persistence paths are configured. |
| `CANCEL_ORDERS_ON_START` | **Cancel any open/pending orders on bot startup.**<br>Why this exists: - Prevents stale orders from a previous run from filling unexpectedly. Important note: - Canceling an order is not the same as closing a filled trade. - This setting is about cleanup of pending orders, not day-trading. |
| `FLATTEN_ON_EXIT` | **When the bot exits/shuts down, flatten positions as part of shutdown.**<br>Use cases: - Paper/sim runs where you always want to end flat. - Emergency shutdown behavior. Caution: - For ICC continuation holding, you usually do NOT want forced flattening. |
| `INTRADAY_FLATTEN` | **Flatten positions near the end of the session (intraday mode).**<br>Why this exists: - Avoid holding equities overnight when running an intraday-only strategy. ICC note: - Only enable if your ICC plan is explicitly intraday (no overnight hold). |

### Sabbath-Related Settings

| Environment Variable | Description |
|----------------------|-------------|
| `SABBATH_ENABLED` | **Override the profile's sabbath_enabled flag.**<br>What this controls: - When true, the profile treats the sabbath window as active (new entries blocked). - When false, the profile disables sabbath blocking entirely. How to use: - Leave empty to keep the profile default. - Use with BOT_SABBATH=Auto so the profile logic applies. |
| `SABBATH_ASTRONOMICAL` | **Use actual sunset times instead of fixed HH:MM values.**<br>Requirements: - `astral` must be installed. - You must provide latitude/longitude (SABBATH_LAT/SABBATH_LON). How to use: - Enable this for accurate sabbath windows that track seasonal sunset shifts. - Leave off for fixed windows (SABBATH_START_LOCAL/SABBATH_END_LOCAL). |
| `SABBATH_TIMEZONE` | **Timezone used when computing sabbath start/end.**<br>Format: - Use an IANA timezone like `America/New_York`. How to use: - Set this to match the city you want sabbath times computed for. |
| `SABBATH_START_LOCAL` | **Fixed local start time (Friday) for sabbath blocking.**<br>Format: - HH:MM in 24-hour time (e.g., 18:00). When it applies: - Used only when SABBATH_ASTRONOMICAL is false. |
| `SABBATH_END_LOCAL` | **Fixed local end time (Saturday) for sabbath blocking.**<br>Format: - HH:MM in 24-hour time (e.g., 18:00). When it applies: - Used only when SABBATH_ASTRONOMICAL is false. |
| `SABBATH_LAT` | **Latitude for astronomical sabbath calculations.**<br>Format: - Decimal degrees (e.g., 40.7128). When it applies: - Required if SABBATH_ASTRONOMICAL=true. |
| `SABBATH_LON` | **Longitude for astronomical sabbath calculations.**<br>Format: - Decimal degrees (e.g., -74.0060). When it applies: - Required if SABBATH_ASTRONOMICAL=true. |
| `SABBATH_CITY` | **Optional city name used by the GUI resolver to fill latitude/longitude/timezone.**<br>How to use: - Enter a US city (e.g., New York) and use Resolve to auto-fill lat/lon + timezone. - If the resolver fails, enter lat/lon/timezone manually. |

### Market/Broker Connectivity Settings

| Environment Variable | Description |
|----------------------|-------------|
| `EXCHANGE_PROVIDER` | **Chooses the primary market connectivity stack.**<br>Options: - IBKR: use Interactive Brokers for market data and/or execution. - CCXT: use CCXT-compatible crypto exchange connectivity (when configured). Important: - “Market Data” and “Broker” dropdowns below only matter when using the alternative provider. - If you select IBKR here, the bot uses IBKR as the primary feed/broker. |
| `Market Data` | **Selects the market data source when using an alternative provider.**<br>How to use: - If `EXCHANGE_PROVIDER=IBKR`, this setting is ignored. - If using CCXT/alternative mode, choose the market data backend you want. Tip: - Delayed data is fine for monitoring; just expect candles/quotes to lag. |
| `Broker` | **Selects where orders are sent when using an alternative provider.**<br>How to use: - If `EXCHANGE_PROVIDER=IBKR`, this setting is ignored. - If using CCXT/alternative mode, choose the execution backend. Safety: - Always verify you are on the intended account/venue before enabling live trading. |
| `Candles (chart)` | **Controls the bar size used for the GUI candle chart.**<br>What this is: - This changes the timeframe of the historical bars shown in the candles pane. - It does not change the bot’s decision timeframe by itself (that is profile/timeframe driven). How to use: - Use smaller values (1m/5m) for more detail and short-term structure. - Use larger values (15m/30m/1h/daily) for broader context and swing structure. Data note: - If you are using delayed market data, the chart will lag behind live prices. - Missing bars usually means the provider returned no bars for that request (symbol/venue mismatch or data limitations).\n |
| `MARKET_DEFAULT_SYMBOL` | **Default symbol shown in the GUI candle pane when there is no active symbol.**<br>How to use: - Set a common benchmark symbol (e.g., SPY, QQQ, BTCUSD) to keep the chart useful. - If the bot becomes active on a symbol, the GUI can switch to the active symbol. |
| `MARKET_DEFAULT_TIMEFRAME` | **Default candle timeframe used by the GUI chart.**<br>What this affects: - Only the GUI chart timeframe (not the bot’s scan timeframe). How to use: - Pick the timeframe you most often want as context (5m/15m/1h/daily). |
| `MARKET_MAX_CANDLES` | **Maximum number of candles to request/render in the GUI.**<br>Tradeoffs: - More candles = more history/context, more API load. - Fewer candles = faster refresh, less clutter. Tip: - If you see missing bars/timeouts, reduce this value. |
| `MARKET_SYMBOLS` | **Comma-separated symbol list for GUI rotation when the bot is not actively trading a single symbol.**<br>How to use: - Provide your preferred watchlist (e.g., `SPY,QQQ,DIA,BTCUSD,ETHUSD`). - The GUI/candles pane can rotate through the top symbols when idle. Tip: - Keep the list short to avoid unnecessary market data requests. |

### IBKR-Specific Settings

| Environment Variable | Description |
|----------------------|-------------|
| `IBKR_HOST` | **Host/IP where TWS or IB Gateway is running.**<br>Typical: - `127.0.0.1` when TWS/Gateway is on the same machine. |
| `IBKR_PORT` | **Port for the IBKR API connection.**<br>Typical defaults: - 7497: paper - 7496: live Tip: - Match this to your TWS/Gateway API settings. |
| `IBKR_CLIENT_ID` | **Client ID for the IBKR API connection.**<br>Why it matters: - Lets multiple apps connect without stepping on each other. |
| `IBKR_ACCOUNT_ID` | **Account identifier (useful if your login has multiple accounts).**<br> |
| `IBKR_DEFAULT_CCY` | **Default currency used when building certain contracts (usually `USD`).**<br> |
| `IBKR_PAPER` | **Paper/live preference for the IBKR connection.**<br>Important: - This does not override `EXECUTE_TRADES`; it only selects which endpoint you connect to. |
| `IBKR_READ_ONLY` | **Safety switch: when true, the IBKR executor refuses to place orders.**<br>Use cases: - Monitoring mode with live market data but no trading. - Safety while you validate settings. |
| `IBKR_CRYPTO_EXCHANGE` | **Exchange route for IBKR crypto (e.g., ZEROHASH).**<br>Important: - ZEROHASH spot crypto is long-only in this project’s rules. - If you change this, verify execution capabilities and supported order types. |
| `IBKR_ZEROHASH_CRYPTO_TIF` | **Time-in-force for IBKR ZEROHASH crypto orders.**<br>How to use: - Choose a TIF supported by your venue/order type (e.g., DAY/IOC). - If you see broker warnings about unsupported TIF, change this. |
| `IBKR_MAX_SHARES_PER_SYMBOL` | **Hard cap on position size (shares) per symbol.**<br>Why this matters: - Prevents runaway sizing due to bad data or config. How to use: - Set a conservative max based on your account size. - Use alongside dollar-risk caps. |
| `IBKR_MAX_DOLLAR_RISK_PER_SYMBOL` | **Maximum dollar risk allowed per symbol.**<br>What this means: - Caps how much you can lose on a single position based on stop distance. How to use: - Set this first before enabling live trading. - If orders are rejected due to sizing, this cap may be too low. |
| `IBKR_MAX_DOLLAR_RISK_PER_ACCOUNT` | **Maximum total dollar risk allowed across all open positions.**<br>Why this matters: - Required if you enable multi-position mode. - Prevents cumulative exposure from becoming too large. How to use: - Keep this aligned with your risk tolerance for worst-case stop-outs. |
| `IBKR_AUTO_RISK_FRACTION_OF_BUYING_POWER` | **Automatic risk sizing as a fraction of buying power.**<br>What this does: - Helps the bot scale position size with account size. - Still bounded by max shares and max dollar risk caps. How to use: - Start small (very conservative). - Increase only after validating sizing and broker fills. |

### CCXT-Specific Settings

| Environment Variable | Description |
|----------------------|-------------|
| `CCXT_EXCHANGE` | **Which CCXT exchange to use when routing via CCXT.**<br>How to use: - Set this only if you are using CCXT for market data and/or execution. - Example values match CCXT exchange ids (e.g., `binance`, `coinbase`). |
| `CCXT_DEFAULT_TYPE` | **CCXT market type (spot, swap, future) depending on the exchange.**<br>How to use: - Choose the type that matches the instruments you trade. - Wrong type often causes “symbol not found” or missing candles. |
| `CCXT_ENABLE_RATE_LIMIT` | **Enable CCXT built-in rate limiting.**<br>Why this matters: - Helps avoid exchange bans and 429 rate-limit errors. Recommendation: - Keep enabled for live connectivity. |
| `CCXT_SANDBOX` | **Use CCXT sandbox/testnet mode (if the exchange supports it).**<br>How to use: - Enable for testing without real funds. - Disable for live trading. |
| `CCXT_SYMBOL_MAP` | **Optional mapping to translate internal symbols to CCXT exchange-specific symbols.**<br>When you need this: - The exchange uses symbols like `BTC/USDT` but your bot uses `BTCUSD`. How to use: - Provide a JSON or delimited mapping per your project’s configuration format. |
| `CCXT_API_KEY` | **API key for CCXT exchange authentication.**<br>How to use safely: - Treat as a password. - Use exchange keys with least privileges needed. |
| `CCXT_SECRET` | **API secret for CCXT exchange authentication.**<br>Safety: - Never share this. - If you suspect leakage, revoke/regenerate it at the exchange. |
| `CCXT_PASSWORD` | **Optional passphrase/password for CCXT (some exchanges require it).**<br>How to use: - Leave blank unless your exchange specifically requires a passphrase. |

### AI/Commentary Settings

| Environment Variable | Description |
|----------------------|-------------|
| `CHATGPT_KEY` | **API key for a ChatGPT-compatible provider (if configured).**<br>What it is for: - Enables AI commentary and/or AI-assisted reasoning in the bot, depending on your setup. How to use safely: - Treat this like a password. - Set it in the typed field (not in the Advanced env table), then Save to `.env`. Troubleshooting: - If commentary shows “waiting” forever, verify the key is set and the provider/model are valid. |
| `TRADE_SCI_PROVIDER` | **Select which AI provider the bot/commentary should use.**<br>Options: - openai, gemini, claude, deepseek, openrouter, custom. - Use custom when you have an OpenAI-compatible endpoint. - Leave blank for Auto (OpenAI defaults). |
| `TRADE_SCI_API_BASE_URL` | **Base URL for the Trade by SCI AI gateway/provider.**<br>When you would change this: - You are using a self-hosted gateway, a proxy, or a non-default endpoint. How to use: - Leave default unless you were explicitly given a different URL. - If you change it, restart the commentary pane so it picks up the new endpoint. |
| `TRADE_SCI_MODEL_NAME` | **Which LLM model to use for bot decisions and AI commentary.**<br>How to choose: - Larger models: better explanations, higher cost. - Smaller models: cheaper/faster, may be less insightful. Tip: - If you want more “human play-by-play”, pick a stronger model and increase max tokens. |
| `TRADE_SCI_MAX_TOKENS` | **Maximum tokens allowed per AI response.**<br>What this changes: - Higher values allow longer, more detailed commentary. - Lower values reduce cost but can truncate explanations. Recommendation: - For “twice as long” commentary, increase this (within your provider limits). |
| `TRADE_SCI_TEMPERATURE` | **Controls how creative vs. deterministic the AI output is.**<br>How to use: - 0.0–0.3: more consistent/grounded, best for monitoring decisions. - 0.4–0.8: more expressive, can be more speculative. Safety note: - Commentary is informational; trading logic should not depend on creative phrasing. |
| `COMMENTARY_LLM` | **Controls whether the right-pane commentary uses the internal AI commentator.**<br>Options: - Auto: use internal commentary. - Off: no AI calls; deterministic dashboard only. - Internal: call the built-in AI commentator. Cost control: - Use the refresh/budget settings to prevent excessive API usage. |
| `COMMENTARY_LLM_POLICY` | **Controls WHEN the GUI/tmux is allowed to call the commentator.**<br>Options: - a_plus_or_4x (recommended): Call on A+ continuation (readiness=1.00). If no A+ is happening, call up to 4× per day using `COMMENTARY_LLM_DAILY_SLOTS`. - a_plus_only: Only call when an A+ continuation appears. - interval: Legacy behavior (call whenever `COMMENTARY_LLM_MIN_SECONDS` allows it). Why this exists: - Keeps API usage under control while still giving you timely insight when the bot reaches a true ICC entry (A+). |
| `COMMENTARY_LLM_DAILY_SLOTS` | **Comma-separated times (HH:MM) used by `COMMENTARY_LLM_POLICY=a_plus_or_4x`.**<br>Example: - 09:00,12:00,18:00,22:00 Notes: - Times are interpreted in `COMMENTARY_LLM_TZ`. - The bot will call at most once per slot. |
| `COMMENTARY_LLM_TZ` | **Shared timezone (IANA name) used to interpret `COMMENTARY_LLM_DAILY_SLOTS`.**<br>The Time tab keeps this aligned with Sabbath/session timezones. Example: - America/New_York |
| `COMMENTARY_LLM_MIN_SECONDS` | **Minimum seconds between commentary refreshes.**<br>Why this matters: - Prevents spamming your provider/API. - Lower values increase cost and rate-limit risk. Recommendation: - 300s (5 minutes) is a good default. |
| `COMMENTARY_LLM_MAX_CALLS_PER_DAY` | **Hard daily cap for commentary calls (shared across panes).**<br>Why this exists: - Prevents runaway cost and rate-limit lockouts. How it behaves: - When the cap is reached, the commentary pane keeps the last good answer. |
| `COMMENTARY_LLM_BUDGET_PATH` | **Shared JSON file used to coordinate commentary call budgeting across processes.**<br>How to use: - Leave default unless you want a different shared location. - Must be writable. |
| `TRADE_SCI_API_KEY` | **API key for the AI provider used by the bot/commentary.**<br>How to use: - This is sensitive. The GUI masks it and stores it as an env var. - Set it once, then use budgets/refresh intervals to control spend. |
| `MULTI_POSITION_ENABLED` | **Opt-in multi-position trading.**<br>Default behavior: - Off: the bot only allows one open symbol at a time. When enabled: - The bot may hold multiple symbols concurrently (up to `MAX_CONCURRENT_POSITIONS`). - Use risk caps to prevent over-exposure. |
| `MAX_CONCURRENT_POSITIONS` | **Maximum number of symbols that may be open at the same time when multi-position is enabled.**<br>How to choose a value: - Start with 2–3. - Increase only if you are comfortable managing multiple positions and your risk caps are set. |
```

## Logging and observability

- `[STRUCTURE]` entries detail the bot's analysis of market structure. This includes the symbol being evaluated, its calculated `score` (indicating cleanliness of structure), and the `reason` for any particular structural finding. For example, `HMDS 162 “no data”` for equities is treated as a soft warning, signifying that no clear signal was found in the current cycle due to lack of historical data, prompting the bot to `stand_aside`. These logs are crucial for understanding how the bot identifies HH/HL vs LH/LL patterns and overall trend health on both higher and lower timeframes.  
- `[SELECT]` records the active "battlefield" for each cycle. These logs indicate which symbols the bot is actively considering for trades based on initial ICC screening criteria (e.g., sufficient volume, open session, initial trend alignment), moving beyond just basic market data availability. It answers the critical ICC question: "Which chart should I be watching right now?"  
- `[STATE]` logs open positions and their protection status, offering a clear view of the bot's current portfolio and risk management. This includes whether positions are safeguarded by `local_stop` protection (for venues like ZEROHASH crypto that reject native stops), current profit/loss, and other relevant metrics. For an ICC trader, this ensures transparency into active trades and how their predefined risk parameters are being enforced.  
- `[GUARD]` entries explain vetoes of potential trade entries due to risk parameters or other hard gates. These logs include details like buying power, candidate quantity, notional value, and the specific reason for suppression (e.g., `RISK_SUPPRESSED`). This is crucial for understanding how the bot upholds ICC discipline by preventing entries that violate predefined risk caps or trading rules, ensuring no trade is "forced." Repeated suppressions can increment `strike` counts, temporarily benching symbols that consistently fail to meet guard conditions.  
- `[EMERGENCY_FLATTEN]` is a critical safety log emitted when a local stop closes a ZEROHASH crypto position. This occurs when a broker (like ZEROHASH) does not support native stop orders, and the bot must manually monitor the price and issue a market order to flatten the position once the stop level is hit. This log confirms that the local-stop fallback mechanism has engaged to protect capital.  
- `[CRYPTO][PERSIST]`, `[CRYPTO][STARTUP]`, `[CRYPTO][INTEGRITY]`, and `[CRYPTO][SAFETY]` logs provide detailed insights into the management of ZEROHASH crypto synthetic stops. These entries track the persistence of stop-loss levels across bot restarts (`[PERSIST]`), how existing positions are reconciled upon startup (`[STARTUP]`), any corrections made for data integrity (`[INTEGRITY]`), and actions taken on unprotected positions (`[SAFETY]`). This is crucial for maintaining continuous risk management and ensuring that crypto positions are always protected, even when the bot is restarted or network issues occur.  
- `[COOLDOWN]` clarifies when a symbol or the entire bot is temporarily disengaged from making new entry decisions. This mechanism, aligned with ICC discipline, prevents overtrading by instituting a waiting period after a blocked trade attempt or a recently successful entry. It ensures the bot doesn't "force" trades in chop or immediately re-enter a volatile situation without allowing the market to re-establish clear ICC-aligned structure.
- Data provider warnings (contract resolution, unsupported stops, missing market data permissions) now mention the relevant configuration knob (`market.crypto_routing.overrides...` or `runtime.local_stop_symbols`).

## Testing

Run the config/unit tests that touch the new behavior:

```bash
poetry run pytest tests/test_config.py -q
poetry run pytest tests/test_phase3c.py tests/test_phase3d.py tests/test_sabbath.py -q
```

The full test suite (`poetry run pytest -q`) can be run in an environment with a longer timeout if needed.

## Troubleshooting tips

- If you see `No market data permissions for PAXOS CRYPTO`, edit `market.crypto_routing.overrides` to point that symbol to ZEROHASH.  
- If an instrument repeatedly triggers “risk suppressed” logs, it will be skipped for a few cycles via the strike tracker.  
- Local stops can be disabled by setting `runtime.allow_local_stops=false`; in that case, any venue lacking stop support will be treated as `UNSUPPORTED_SYMBOL_CONFIG`.
- To keep crypto running non-stop, use `crypto_247` and check that `auto_flatten_on_close=false` in your profile.

## ICC Compliance (Defaults)

**ICC compliance: 100%** - Full adherence to Trade by SCI's ICC/ICT probability-weighted confluence methodology

The bot implements ICC as Trade by SCI teaches it - a **confluence-based probability system**, not a rigid checklist.

### Core ICC Indicators (ALL tracked and weighted):
- HTF/LTF structure alignment (HH/HL vs LH/LL swing confirmation)
- Liquidity sweeps (external liquidity hunts before reversals)
- Continuation triggers (break of structure + close beyond correction range)
- Indication (break of most recent swing high/low)
- Structure invalidation (close beyond key swing levels)
- Session health (volume, spread, time-of-day)
- Trend commitment (no re-deciding mid-position)

### How ICC Actually Works (Trade by SCI Philosophy):
ICC indicators are **probabilistic evidence**, not binary requirements. Trade by SCI doesn't say "sweeps are mandatory" - he says "sweeps increase probability." The bot follows this exactly:

- **A+ setups**: HTF/LTF aligned + sweep confirmed + continuation trigger (highest probability)
- **A/B setups**: HTF/LTF aligned + continuation trigger, no clear sweep (still high probability)
- **C/D setups**: Weaker confluence, managed with tighter risk
- **Stand aside**: Structure unclear, trends misaligned, or insufficient confluence

The selection scoring system (`selection_score`, `icc_grade`) weights ALL indicators and ranks opportunities. Higher confluence = higher position sizing and priority. This is **exactly** how Trade by SCI trades - assess confluence, manage risk, take high-probability setups.

**Key principle**: Liquidity sweeps are **confluence enhancers, not gatekeepers**. The bot focuses on continuation triggers and risk-reward, using sweeps to improve setup quality (A+ vs B) rather than as mandatory entry requirements. As validated by ICC methodology: *"The market doesn't always give you perfect setups. You have to trade what you see, not what you want."*

### What Makes It 100% ICC:
- ✅ Uses ALL ICC indicators as probabilistic evidence
- ✅ Weights confluence via scoring (A+ through F grades)
- ✅ Prioritizes high-confluence setups (A+ executed first)
- ✅ Trades lower-confluence with appropriate risk (B grade valid without sweep)
- ✅ Stands aside when confluence weak
- ✅ Manages positions per ICC principles (commitment, invalidation, targets)

Trade by SCI doesn't sit forever waiting for textbook perfection - he assesses probability and acts. The bot does the same.

*External constraints (broker rejections, regulatory/PDT compliance) may prevent execution even when ICC logic approves a trade. Those are safety overrides outside the bot's control.*

## License

MIT
