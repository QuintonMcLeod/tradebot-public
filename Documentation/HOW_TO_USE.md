# Trade by SCI — How To Use

> **First time? Start here.** This is the practical, no-fluff guide to getting the bot running and making trades. For deep dives into architecture and philosophy, see the `RTFM/` folder. For installation and setup, see the `README.md`.

---

## 🔌 Step 1: Connect Your Broker(s)

Go to **Settings** (gear icon) → **Brokers** tab.

You need at least **one** broker connected to trade. The bot performs a **pre-flight check** on startup — if no broker is configured, it refuses to start and tells you exactly what to do.

### Forex (OANDA) — Recommended for Beginners

OANDA is the simplest broker to set up. Great for forex with tight spreads.

1. Create a **live** account at [oanda.com](https://www.oanda.com) — choose **fxTrade** (not fxTrade Practice).
2. Go to Account Settings → **Manage API Access** → Generate a Personal Access Token.
3. In the bot: **Settings** → **Brokers** → **OANDA** section:
   - **Account ID**: Your OANDA sub-account number (format: `101-001-XXXXXXX-XXX`)
   - **API Key**: Paste your full token (starts with a long alphanumeric string)
   - **Environment**: `live`
4. Click **Save**.
5. Confirm connection in logs: `[INFO] Connected to OANDA (live)` ✅

> ⚠️ **Why not Practice?** OANDA practice accounts have limited API permissions — they **cannot fetch candle data**, which the bot needs for chart display and strategy analysis. Use a **live** account. If you don't want to risk real money, enable the bot's built-in **Paper Trading** mode (Settings → toggle off Execute Trades).

### Crypto (Gemini / Coinbase / Kraken / etc.)

1. Create API keys on your exchange:
   - **Gemini**: Account → API → Create a New API Key → Enable "Trading" scope
   - **Coinbase**: Settings → API → Create API Key → Portfolio permissions
   - **Kraken**: Settings → API → Create Key → Enable "Create & Modify Orders"
2. In the bot: **Settings** → **Brokers** → **CCXT** section:
   - **Exchange**: `gemini`, `coinbase`, `kraken`, etc.
   - **API Key**: From your exchange
   - **API Secret**: From your exchange
   - **Sandbox**: Enable for testnet/paper trading (if the exchange supports it)
3. Click **Save**.
4. Confirm: `[INFO] Connected to gemini via CCXT` ✅

> ⚠️ **API key permissions**: Only enable **trading** permissions. Never enable withdrawal permissions — the bot never needs to withdraw funds.

### Stocks / Options / Futures (Interactive Brokers)

IBKR is the most powerful but most involved setup. It requires TWS (Trader Workstation) or IB Gateway running alongside the bot.

**Quick version:**
1. Download and install TWS or IB Gateway from [interactivebrokers.com](https://www.interactivebrokers.com)
2. Enable the API: File → Global Configuration → API → Settings → Check "Enable ActiveX and Socket Clients"
3. Set Socket Port to `7497` (paper) or `7496` (live)
4. In the bot: **Settings** → **Brokers** → **IBKR** section:
   - **Account ID**: Your IBKR account number (e.g., `U1234567`)
   - **Host**: `127.0.0.1` (or your server's IP)
   - **Port**: `7497` (paper) / `7496` (live)
   - **Client ID**: `1` (or any unique number if running multiple clients)

For the full walkthrough, see `Documentation/RTFM/08_API_SETUP.md`.

---

## 🧠 Step 2: Connect the AI Brain

Go to **Settings** → **Intelligence** tab.

The bot uses AI for two things:
1. **Market Commentary** — Rich analysis of market conditions shown in the Decisions panel
2. **Decision Validation** — AI cross-checks strategy signals for quality

| Provider | Model | Best For | Cost |
|---|---|---|---|
| **Gemini** | gemini-2.0-flash | Recommended default — fast, smart, cheap | ~$0.001/trade |
| **DeepSeek** | deepseek-chat | Budget-friendly, surprisingly good | ~$0.0005/trade |
| **OpenAI** | gpt-4-turbo | Premium analysis, best reasoning | ~$0.01/trade |
| **Claude** | claude-3.5 | Nuanced market analysis | ~$0.008/trade |
| **OpenRouter** | Various | Access to multiple models via one API key | Varies |
| **Local (Ollama)** | Any LLM | Free, private, runs on your machine | Free |

### Setup

1. Pick your **Provider** from the dropdown.
2. Paste your **API Key** (get one from the provider's website).
3. Select a **Model** (the default is pre-selected and usually the best choice).
4. Optionally adjust **Temperature** (0.1 = conservative, 0.7 = creative) — default 0.3 is recommended.
5. **Save**.

> 💡 **No AI key?** The bot still trades without it — strategies run mathematically, no AI required. You just won't get the AI commentary overlay in the Decisions panel. The core trading engine works the same either way.

---

## 📊 Step 3: Choose a Profile

The left sidebar in the **Profile Editor** tab shows your **Trading Profiles**. A profile is a complete trading configuration that bundles together:

- **Which symbols** to trade
- **Which strategy** to use
- **Risk parameters** (risk per trade, leverage, max positions)
- **ICC scores** (market structure filters)
- **Schedule** (trading hours, session gates)

### Built-in Profiles

| Profile | Symbols | Strategy | Runs When |
|---|---|---|---|
| `forex_continuous` | 10 major forex pairs | Rubberband Reaper | Mon-Fri market hours |
| `crypto_247` | 6 high-volume crypto | Meta-SCI | 24/7 |
| `forex_crypto_hybrid` | 10 forex + 12 crypto | Meta-SCI | Market hours + 24/7 crypto |
| `forex_intraday` | 18 forex pairs | Rubberband Reaper | London/NY sessions only |
| `all_247` | Everything | Meta-SCI | 24/7 |

**Click a profile** to load it. The bot immediately starts scanning those symbols.

### Creating Your Own Profile

1. Click **"+ New Profile"** at the bottom of the sidebar.
2. Give it a name (lowercase, underscores: `my_forex_setup`).
3. Configure each tab:

#### General Tab
| Setting | What It Controls |
|---|---|
| **Strategy** | Which algorithm drives trade decisions (Meta-SCI recommended) |
| **Timeframe** | Primary chart timeframe (15m for scalping, 1h for swing, 4h for position) |
| **Polling Interval** | How often the bot re-scans each symbol (in seconds) |
| **Higher Timeframe** | Secondary timeframe for trend confirmation (e.g., 4h when primary is 1h) |

#### Symbols Tab
Add or remove symbols the bot monitors. Symbols must match your broker's naming:
- **Forex**: `EUR_USD`, `GBP_JPY`, `USD_CHF` (OANDA format with underscore)
- **Crypto**: `BTCUSD`, `ETHUSD`, `SOLUSD` (exchange format, no separator)
- **Futures**: `ES`, `NQ`, `GC` (IBKR contract symbols)

#### Risk Tab
| Setting | What It Does | Example |
|---|---|---|
| **Risk Per Trade %** | Max % of equity risked on a single trade | 2.0 = risk $80 on a $4,000 account |
| **Max Leverage** | Hard cap on leverage ratio | 3.0 = max 3x notional exposure |
| **Max Concurrent Positions** | How many trades can be open at once | 5 |
| **Crypto Qty Steps** | Minimum lot increments for crypto | `{"BTCUSD": 0.00001, "ETHUSD": 0.001}` |

#### ICC Tab (Inter-Candle Confluence)
ICC is the bot's market structure scoring system. It rates each setup from 0-100.

| Setting | What It Controls | Default |
|---|---|---|
| **Min Score** | Minimum ICC score to accept a trade | 55 (conservative: 65+) |
| **Threshold Grade** | Minimum letter grade | C+ |
| **Higher TF Weight** | How much the higher timeframe influences the score | 0.3 |

> 💡 **Higher ICC = fewer but better trades.** Setting min score to 70+ means only high-conviction setups trigger entries.

#### Schedule Tab
| Setting | What It Controls |
|---|---|
| **Session Start/End** | When the bot is allowed to enter new trades |
| **Sabbath Mode** | Pause trading from Friday sunset to Sunday (configurable) |
| **Auto-Flatten** | Close all positions before sessions end |
| **Crypto Window** | Specific hours for crypto trading (e.g., 02:00-06:00 UTC for Asian session volatility) |

---

## ⚙️ Step 4: Configure Your Risk

This is the most important step. Go to **Settings** → **System** tab.

### Key Risk Settings

| Setting | What It Does | Conservative | Moderate | Aggressive |
|---|---|---|---|---|
| **Default Risk %** | Equity risked per trade | 1% | 2-3% | 4-5% |
| **Short Risk %** | Risk for short positions | 1% | 2% | 3% |
| **Max Exposure %** | Total portfolio risk at any time | 5% | 10% | 15% |
| **Daily Loss Limit %** | Circuit breaker — stops all trading | 5% | 10% | 20% |
| **Risk Reward Ratio** | Target profit ÷ risk amount | 2.0 | 2.0 | 1.5-2.0 |
| **Max Concurrent Positions** | Open trades at once | 3 | 5 | 8 |

### Understanding the Math

With **$4,000 capital** and **2% risk per trade**:

```
Risk per trade:    $4,000 × 2% = $80 at risk
Take profit:       $80 × 2.0 RR = $160 potential gain
Max daily loss:    $4,000 × 10% = $400 circuit breaker

Winning scenario:  3 wins/day × $160 = $480/day
Losing scenario:   4 losses in a row = $320 drawdown (8% of account)
```

### Sizing by Account

| Account Size | Risk % | Max Positions | Reasoning |
|---|---|---|---|
| **Under $500** | 1-2% | 3 | Limited capital needs preservation |
| **$500 – $2,000** | 2-3% | 4 | Balanced growth |
| **$2,000 – $10,000** | 2-4% | 5-6 | Good position sizing range |
| **$10,000+** | 1-3% | 6+ | Larger account, lower % = more $ per trade |

> ⚠️ **The compounding effect of losses**: A 4.5% risk with 4 consecutive losses = 18% drawdown. At 2% risk, the same streak = 8%. Pick a risk level where the worst-case scenario doesn't keep you up at night.

---

## 🗡️ Step 5: Understand the Strategies

Go to **Settings** → **Strategy** tab to browse, or set your strategy in **Profile** → **General** tab.

### Strategy Quick Reference

#### Universal Strategies (Forex + Crypto)

| Strategy | Style | How It Works | Best Market |
|---|---|---|---|
| **Meta-SCI** ⭐ | AI Ensemble | Runs a tournament of all eligible strategies, picks the best signal | All markets — recommended default |
| **Rubberband Reaper** | Anti-Martingale Momentum | Catches momentum after overextension snaps back | Strong trending forex |
| **Mean Reversion** | Statistical Reversion | Identifies when price deviates too far from fair value and bets on return | Ranging/trending markets |
| **RoboCop** | Sniper Precision | Extremely selective, only fires on high-conviction structural setups | Low-frequency, any market |
| **Supply & Demand** | Institutional Zones | Identifies supply/demand zones where institutions place orders | Support/resistance plays |
| **Trend Rider** | EMA Pullback | Waits for pullbacks to moving averages in established trends | Strong trends |
| **Session Momentum** | VWAP at Open | Trades momentum at London/NY session opens against VWAP | Session open volatility |
| **Engulfing Reversal** | Candlestick Patterns | Identifies bullish/bearish engulfing patterns at key levels | Key reversal zones |

#### Crypto-Specific Strategies

| Strategy | Style | How It Works | Best Market |
|---|---|---|---|
| 🪙 **RSI + MACD** | Classic Momentum | RSI oversold/overbought + MACD cross confirmation | Crypto trending |
| 🪙 **VWAP Reversion** | Mean Reversion to VWAP | Identifies deviations from VWAP with volume confirmation | Crypto ranging |
| 🪙 **Double MACD** | Dual-Timeframe Scalp | Fast/slow MACD on two timeframes for precision entries | Crypto scalping |
| 🪙 **Virtual Grid** | Grid Trading | Places virtual buy/sell levels at fixed intervals | Crypto sideways markets |

### How Meta-SCI Works (The Recommended Strategy)

Meta-SCI is like a **coach running tryouts**. For each symbol, every scan cycle:

1. **Detects market regime** — Is the market trending, ranging, mean-reverting, or choppy?
2. **Picks eligible strategies** — Each strategy has regimes it's suited for. Only matching ones compete.
3. **Runs a tournament** — Every eligible strategy generates a signal independently.
4. **Scores and ranks** — Signals are scored by conviction (0-100), entry precision, and risk/reward.
5. **Picks the winner** — The highest-scoring signal becomes the trade decision.
6. **Falls back gracefully** — If no strategy scores above threshold, it says "STAND ASIDE" (no trade).

This means Meta-SCI **never forces a trade**. It only enters when at least one strategy has high conviction for the current market conditions.

> 💡 **Not sure? Use Meta-SCI.** It adapts to any market regime automatically. You'd only switch to a specific strategy if you have a strong preference for a particular trading style.

---

## ▶️ Step 6: Start Trading

Once broker + profile + risk are configured:

1. **Select your profile** from the sidebar.
2. The bot immediately begins **scanning** your symbols on a timed loop.
3. Watch the **Decisions** panel — it shows what the bot thinks for each symbol in real time.
4. When conditions are right, the bot enters trades **automatically**.
5. Positions appear in the **Holdings** panel with live P&L.

### Understanding the Decision Panel

Each symbol gets a decision card showing:

| Field | Meaning | Example |
|---|---|---|
| **Action** | What the bot decided | `ENTER_LONG`, `ENTER_SHORT`, `HOLD`, `STAND_ASIDE` |
| **Score** | ICC market structure score (0-100) | `82.3` (good), `45.2` (marginal) |
| **Grade** | Letter grade for the setup quality | `A-` (excellent), `C+` (acceptable), `D` (rejected) |
| **Strategy** | Which strategy generated the signal | `META_SCI → Rubberband Reaper` |
| **Entry/SL/TP** | Proposed entry, stop loss, and take profit | `1.0865 / 1.0840 / 1.0915` |
| **R:R** | Risk-to-reward ratio | `2.0` (risking 1 to make 2) |

### Reading the Logs

```
✅ Healthy operation:
[INFO] [PHOENIX] === ENGINE LOADED === Symbol: EURUSD | Variant: META_SCI
[INFO] [META-SCI] ⚔️ Starting BULLISH_TRENDING Tournament for EURUSD (5 strategies eligible)
[INFO] [META-SCI] 🏆 Winner: rubberband_reaper (score: 78.5, action: ENTER_LONG)
[INFO] [DECISION] symbol=EURUSD action=ENTER_LONG score=82.3 grade=A-
[INFO] [OANDA] Filled: BUY 1000 EURUSD @ 1.08692

⚠️ Normal – bot is being selective (this is GOOD):
[INFO] [PHOENIX] EURUSD Strategy STAND_ASIDE triggered
[INFO] [DECISION] symbol=EURUSD action=HOLD reason=Meta-SCI Tournament: No signals found
[INFO] [ICC] GBPUSD Score 42.1 below threshold 55.0 — rejected

🛡️ Safety guards working correctly:
[INFO] [SAFETY] Entry Blocked for USDJPY: Leverage Sentry (FOREX): 4.0x > 3.0x cap
[INFO] [POSITION LOCK] EURUSD — Holding, position managed by existing SL/TP
[INFO] [DAILY LIMIT] Trading suspended — daily loss -$312 exceeds limit -$400

❌ Errors that need attention:
[ERROR] [OANDA] API Error 401 — invalid API token (re-enter key in Settings)
[ERROR] [CCXT] Connection refused — check exchange is accessible
[CRITICAL] [PREFLIGHT] No broker configured — see Settings → Brokers
```

---

## 🛡️ Step 7: Safety Features

These protect you automatically, all enabled by default:

| Feature | What It Does | Where To Configure |
|---|---|---|
| **Position Lock** | Once in a trade, ignores conflicting signals. No whipsawing. | Always on (cannot disable) |
| **Leverage Sentry** | Blocks new trades if leverage exceeds your cap | Settings → System → Max Leverage |
| **Daily Loss Limit** | Stops ALL trading if daily loss hits your circuit breaker | Settings → System → Daily Loss Limit |
| **Trailing Stop** | Moves stop-loss in your favor as price advances | Settings → Safety & Shields |
| **Breakeven Trail** | Locks in breakeven after a configurable profit threshold | Settings → Safety & Shields |
| **ICC Gatekeeper** | Rejects low-quality setups regardless of strategy signal | Profile → ICC → Min Score |
| **Sabbath Mode** | Pauses trading on weekends (Friday→Sunday, configurable) | Profile → Schedule |

### How Position Lock Works

Position Lock is one of the most important safety features. Here's the problem it solves:

```
Without Position Lock:
  12:00 — Meta-SCI says BUY EURUSD → Bot opens LONG
  12:15 — Market dips, another strategy says SELL EURUSD → Bot flips to SHORT
  12:30 — Market recovers, strategy says BUY again → Bot flips back to LONG
  Result: 3 trades, 2 losses from whipsawing, paid spread 3 times ❌

With Position Lock:
  12:00 — Meta-SCI says BUY EURUSD → Bot opens LONG
  12:15 — New signals for EURUSD → IGNORED (position locked)
  12:30 — Price hits take-profit → Bot closes at profit
  Result: 1 trade, 1 win, paid spread once ✅
```

> 💡 **Don't manually close positions** the bot opened. If you do, Position Lock won't know the trade is closed and will keep blocking new entries for that symbol until the next restart.

---

## 📈 Step 8: Monitor Performance

### Dashboard (Real-Time)
- **Live Chart**: Current symbol with candles, indicators, and entry/exit markers
- **Holdings Panel**: All open positions with entry price, current price, unrealized P&L, and position size
- **Status Bar**: Current profile, active strategy, capital, and number of open positions

### Analytics Tab (Historical)
Click the **Analytics** tab to see:
- **Win Rate**: Percentage of winning trades
- **Average P&L**: Mean profit/loss per trade
- **Profit Factor**: Total wins ÷ Total losses (>1.0 = profitable)
- **Max Drawdown**: Largest peak-to-trough decline
- **Trade Breakdown**: Performance by strategy, by symbol, by time of day

### Log Files
All activity is logged to `logs/`:
- `tradebot.log` — Current session log (rotates daily)
- `tradebot.log.1` through `.5` — Previous sessions
- `tradebot_manual.log` — Manual-mode decisions

---

## 🧪 Step 9: Backtesting (Test Before You Trade)

Before deploying a strategy live, test it on historical data:

```bash
# Quick backtest — last 7 days of forex
poetry run python tools/run_forex_backtest.py

# Crypto backtest — last 3 days
poetry run python tools/run_crypto_backtest.py

# Head-to-head strategy comparison (30 days)
poetry run python tools/cartridges/forex_30day_h2h.py
```

### Understanding Backtest Results

```
═══════════════════════════════════════════════════
        BACKTEST RESULTS — EURUSD (30 days)
═══════════════════════════════════════════════════
Total Trades:     142
Win Rate:         57.7%
Avg Win:          $164.20
Avg Loss:         -$82.10
Profit Factor:    1.88
Net P&L:          +$4,218.60
Max Drawdown:     -$612.40 (-3.1%)
Sharpe Ratio:     2.14
═══════════════════════════════════════════════════
```

| Metric | What It Means | Good Value |
|---|---|---|
| **Win Rate** | % of trades that were profitable | >50% |
| **Profit Factor** | Total profit ÷ Total loss | >1.5 |
| **Max Drawdown** | Worst peak-to-trough decline | <10% |
| **Sharpe Ratio** | Risk-adjusted return | >1.5 |

> ⚠️ **Backtests aren't guarantees.** Past performance ≠ future results. Use backtesting to validate strategy logic and risk parameters, not to predict exact returns.

---

## 💡 Pro Tips

### For New Users
1. **Start with paper trading.** Enable the bot's built-in Paper Trading mode (Settings → toggle off Execute Trades). Trade with virtual money first.
2. **Use Meta-SCI strategy.** It automatically adapts to market conditions so you don't have to.
3. **Keep risk at 1-2%** until you've seen at least 2 weeks of consistent performance.
4. **Don't touch positions manually.** Let the bot manage SL/TP. Manual interference confuses Position Lock.
5. **Read the logs for the first few days.** Understanding what the bot is thinking builds trust and helps you tune settings.

### For Intermediate Users
1. **Create separate profiles** for Forex and Crypto — they have different characteristics.
2. **Schedule crypto sessions.** Crypto is 24/7 but volatility spikes at specific hours (Asian session open, US morning).
3. **Raise the ICC threshold** to 65+ if you want fewer, higher-quality trades.
4. **Use the Strategy tab** to view detailed descriptions of each strategy before choosing.
5. **Monitor your Profit Factor** — if it drops below 1.0, reduce risk or switch strategies.

### For Advanced Users
1. **Backtest every strategy change** before deploying live.
2. **Use head-to-head scripts** (`tools/cartridges/`) to compare strategies on your specific symbol list.
3. **Write custom cartridges** — copy an existing one and modify parameters.
4. **Run multiple profiles** with different strategies to diversify signal sources.
5. **Review `RTFM/09_FEET_WET_STRATEGY.md`** for deep strategy tuning guidance.

### Common Mistakes to Avoid
- ❌ **Running the bot with no risk limits.** Always set Max Exposure and Daily Loss Limit before your first trade.
- ❌ **Too many symbols with too little capital.** The Leverage Sentry will block most entries. Start with 3-5 symbols.
- ❌ **Manually closing trades the bot opened.** This breaks Position Lock tracking.
- ❌ **Changing strategies mid-trade.** Wait for all open positions to close before switching.
- ❌ **Ignoring the logs.** The logs tell you exactly why trades were taken or rejected.
- ❌ **Over-optimizing in backtests.** A strategy that works perfectly on historical data but was tuned to fit that specific period will fail live. Test on out-of-sample data.

---

## 🆘 Troubleshooting

| Problem | Fix |
|---|---|
| **Bot refuses to start** | No broker configured — see banner message, add credentials in Settings → Brokers |
| **"Another instance is already running"** | Delete `logs/tradebot.lock` and restart |
| **Bot scans but never trades** | Capital too low for position sizing, or ICC score threshold too high |
| **"Leverage Sentry" blocking everything** | Add more capital, reduce position count, lower leverage cap, or reduce risk % |
| **Decisions say "No signals found"** | Normal — the bot is being selective. Wait for better setups |
| **Crypto P&L seems wrong** | Check `crypto_qty_steps` in your profile — incorrect step sizes cause rounding |
| **UI not loading profiles** | Ensure `config/settings_profiles.yaml` or `config.json` exists |
| **API 401 errors** | API key is expired or invalid — regenerate and re-enter in Settings |
| **Bot trades then immediately closes** | Stop loss too tight — increase risk %, or the market is too choppy |
| **"Rate limited" warnings** | Too many API calls — increase polling interval in your profile |
| **IBKR connection drops** | TWS/Gateway needs to be running; check "Enable Socket API" in TWS settings |

---

## 📖 Glossary

| Term | Definition |
|---|---|
| **ICC** | Inter-Candle Confluence — the bot's market structure scoring system (0-100) |
| **Meta-SCI** | Meta Strategy Confluence Intelligence — the AI ensemble that picks the best strategy |
| **Position Lock** | Safety feature that prevents the bot from flipping positions on the same symbol |
| **Leverage Sentry** | Guard that blocks trades when exposure exceeds your leverage cap |
| **SL / TP** | Stop Loss / Take Profit — automatic exit levels set on every trade |
| **R:R** | Risk-to-Reward Ratio — how much you gain vs. how much you risk (2.0 = gain 2x your risk) |
| **Profit Factor** | Total gross profit ÷ Total gross loss — above 1.0 means the system is profitable |
| **Drawdown** | Peak-to-trough decline in account equity — measures worst-case losing streak |
| **Scalping** | Very short-term trades lasting minutes to hours |
| **Swing Trading** | Medium-term trades lasting hours to days |
| **Position Trading** | Long-term trades lasting days to weeks |
| **CCXT** | CryptoCurrency eXchange Trading Library — connects the bot to crypto exchanges |
| **HTF** | Higher Timeframe — secondary chart used for trend confirmation |
| **VWAP** | Volume-Weighted Average Price — institutional fair value reference |
| **EMA** | Exponential Moving Average — weighted average of recent prices |
| **MACD** | Moving Average Convergence Divergence — momentum indicator |

---

## 📚 Further Reading

| Document | What It Covers |
|---|---|
| `RTFM/01_PHILOSOPHY.md` | Design philosophy and core principles of the trading system |
| `RTFM/08_API_SETUP.md` | Detailed broker API setup walkthrough (IBKR, OANDA, CCXT) |
| `RTFM/09_FEET_WET_STRATEGY.md` | Deep dive into strategy selection and tuning |
| `RTFM/06_PANIC_BUTTON.md` | Emergency procedures — how to flatten all positions |
| `RTFM/07_COCKPIT_CONTROLS.md` | Complete GUI controls reference |
| `Rubberband_Reaper_Strategy.md` | How the flagship Rubberband Reaper strategy works |
| `BACKTESTER_RULES.md` | How to write and run backtests |

---

*Last updated: February 2026 | Trade by SCI v2.x*
