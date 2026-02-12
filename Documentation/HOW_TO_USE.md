# Trade by SCI — How To Use

> **First time? Start here.** This is the practical, no-fluff guide to getting the bot running and making trades. For deep dives into architecture and philosophy, see the `RTFM/` folder.

---

## 🚀 Step 1: Launch the App

```bash
# From the project root
./scripts/tradebot.sh --gui
```

You'll see the **Dashboard** — this is your command center. Live charts, trade decisions, holdings, and logs are all here.

---

## 🔌 Step 2: Connect Your Broker(s)

Go to **Settings** (gear icon) → **Brokers** tab.

You need at least **one** broker connected to trade. Set up whichever applies to you:

### Forex (OANDA) — Recommended for Beginners
1. Create an account at [oanda.com](https://www.oanda.com) — start with **fxTrade Practice** (demo).
2. Go to Account Settings → **Manage API Access** → Generate a token.
3. In the bot: **Brokers** → **OANDA** section:
   - **Account ID**: Your OANDA account number (format: `101-001-XXXXXXX-XXX`)
   - **API Key**: Paste your token
   - **Environment**: `practice` (demo) or `live` (real money)
4. Click **Save**. When you see `[INFO] Connected to OANDA` in the logs, you're live.

### Crypto (Gemini / Coinbase / Kraken / etc.)
1. Create API keys on your exchange (enable trading permissions).
2. In the bot: **Brokers** → **CCXT** section:
   - **Exchange**: `gemini`, `coinbase`, `kraken`, etc.
   - **API Key** and **Secret**: From your exchange
   - **Sandbox**: Enable for testnet/paper trading
3. Click **Save**. Look for `[INFO] Connected to [exchange] via CCXT` in logs.

### Stocks / Options / Futures (Interactive Brokers)
More involved — requires TWS or IB Gateway running. See `Documentation/RTFM/08_API_SETUP.md` for the detailed IBKR walkthrough.

---

## 🧠 Step 3: Connect the AI Brain

Go to **Settings** → **Intelligence** tab.

The bot uses AI for market commentary and decision validation. You need one API key:

| Provider | Best For |
|---|---|
| **Gemini** | Recommended — good quality, low cost |
| **DeepSeek** | Budget-friendly alternative |
| **OpenAI** | GPT-4 Turbo for premium analysis |
| **Claude** | Anthropic models |

1. Pick your **Provider** from the dropdown.
2. Paste your **API Key**.
3. Select a **Model** (the default is usually fine).
4. **Save**.

> 💡 **No AI key?** The bot still trades without it — you just won't get AI commentary in the decisions panel.

---

## 📊 Step 4: Choose a Profile

The left sidebar shows your **Trading Profiles**. A profile is a complete trading configuration: which symbols to trade, which strategy to use, risk settings, and schedules.

### Built-in Profiles

| Profile | What It Trades | Strategy |
|---|---|---|
| `forex_continuous` | 10 major forex pairs | Rubberband Reaper |
| `crypto_247` | 6 high-volume crypto pairs | Meta-SCI |
| `forex_crypto_hybrid` | 10 forex + 12 crypto | Meta-SCI |
| `forex_intraday` | 18 forex pairs | Rubberband Reaper |
| `all_247` | Everything | Meta-SCI |

**Click a profile** to load it. The bot immediately starts scanning those symbols.

### Creating Your Own Profile
1. Click **"+ New Profile"** at the bottom of the sidebar.
2. Give it a name (lowercase, underscores: `my_forex_setup`).
3. Configure the tabs:
   - **General** — Strategy, timeframes, polling intervals
   - **Symbols** — Which symbols to monitor and trade
   - **Risk** — Risk per trade %, leverage, max positions
   - **ICC** — Market structure score thresholds
   - **Schedule** — Trading hours, session gates, sabbath mode

---

## ⚙️ Step 5: Configure Your Risk

This is the most important step. Go to **Settings** → **System** tab.

### Key Settings

| Setting | What It Does | Suggested Start |
|---|---|---|
| **Default Risk %** | How much equity to risk per trade | 1-2% (conservative) to 4-5% (aggressive) |
| **Short Risk %** | Risk for short positions specifically | Same as default, or lower |
| **Max Exposure %** | Total portfolio risk at any time | 5-10% |
| **Daily Loss Limit %** | Circuit breaker — stops trading after this loss | 10-20% |
| **Risk Reward Ratio** | How much you target vs. what you risk | 2.0 (2:1) recommended |
| **Max Concurrent Positions** | How many trades open at once | 3-6 depending on capital |

### Rule of Thumb
- **Small account** (under $500): Use 1-2% risk, max 3 positions
- **Medium account** ($500-$5,000): Use 2-4% risk, max 4-6 positions
- **Large account** ($5,000+): Use 1-3% risk, max 6+ positions

> ⚠️ **Higher risk = higher returns AND higher drawdowns.** A 4.5% risk per trade with 4 losses in a row = 18% drawdown. Make sure you're comfortable with that.

---

## 🗡️ Step 6: Choose a Strategy

Go to **Settings** → **Strategy** tab to browse your options, or set it in your **Profile** → **General** tab.

### Strategy Quick Guide

| Strategy | Style | Best For |
|---|---|---|
| **Meta-SCI** ⭐ | AI Ensemble (auto-selects best strategy) | All markets — recommended default |
| **Rubberband Reaper** | Anti-Martingale Momentum | Forex swing trades |
| **Mean Reversion** | Statistical Mean Reversion | Trending markets, crypto |
| **RoboCop** | Sniper Precision Entries | Low-frequency, high-conviction |
| **Supply & Demand** | Institutional Zones | Support/resistance trading |
| **Trend Rider** | EMA Pullback | Strong trending markets |
| **Session Momentum** | VWAP at Open | London/NY session opens |
| **Engulfing Reversal** | Candlestick Patterns | Key reversal levels |
| 🪙 **RSI + MACD** | Classic Momentum | Crypto trending |
| 🪙 **VWAP Reversion** | Mean Reversion to VWAP | Crypto ranging |
| 🪙 **Double MACD** | Dual-TF Scalping | Crypto scalping |
| 🪙 **Virtual Grid** | Grid Trading | Crypto sideways markets |

> 💡 **Not sure?** Start with **Meta-SCI**. It runs a tournament of strategies on each symbol and picks the best signal automatically. It adapts to the market regime (trending, ranging, choppy) in real time.

---

## ▶️ Step 7: Start Trading

Once broker + profile + risk are configured:

1. **Select your profile** from the sidebar.
2. The bot immediately begins **scanning** your symbols.
3. Watch the **Decisions** panel on the Dashboard — it shows what the bot is thinking for each symbol.
4. When conditions are right, the bot enters trades **automatically**.
5. Positions appear in the **Holdings** panel with live P&L.

### What You'll See in the Logs

```
✅ Good signs:
[INFO] [PHOENIX] === ENGINE LOADED === Symbol: EURUSD | Variant: META_SCI
[INFO] [META-SCI] ⚔️ Starting BULLISH_TRENDING Tournament for EURUSD (5 strategies eligible)
[INFO] [DECISION] symbol=EURUSD action=ENTER_LONG score=82.3 grade=A-
[INFO] [OANDA] Filled: BUY 1000 EURUSD @ 1.18692

⚠️ Normal (bot is being selective):
[INFO] [PHOENIX] EURUSD Strategy STAND_ASIDE triggered
[INFO] [DECISION] symbol=EURUSD action=HOLD reason=Meta-SCI Tournament: No signals found

🛡️ Safety guards working:
[INFO] [SAFETY] Entry Blocked for USDJPY: Leverage Sentry (FOREX): 4.0x > 3.0x
[INFO] [POSITION LOCK] Holding — position managed by SL/TP
```

---

## 🛡️ Step 8: Safety Features (Already On by Default)

These protect you automatically:

| Feature | What It Does |
|---|---|
| **Position Lock** | Once in a trade, ignores conflicting signals. No whipsawing. |
| **Leverage Sentry** | Blocks new trades if leverage exceeds your cap. |
| **Daily Loss Limit** | Stops all trading if daily loss hits your circuit breaker. |
| **Trailing Stop** | Moves stop-loss up as price moves in your favor. |
| **Breakeven Trail** | Locks in breakeven after a configurable profit threshold. |
| **Sabbath Mode** | Optionally pauses trading on weekends. |

You can fine-tune these in **Settings** → **Safety & Shields**.

---

## 📈 Step 9: Monitor Performance

**Settings** → **Performance** tab shows your:
- Win rate
- Average P&L per trade
- Drawdown history
- Strategy breakdown

The **Dashboard** shows real-time:
- Live chart with entry/exit markers
- Current holdings and unrealized P&L
- AI decision reasoning for each symbol

---

## 💡 Pro Tips

### For New Users
1. **Start with demo/paper trading.** Use OANDA Practice or CCXT Sandbox mode.
2. **Use Meta-SCI strategy.** It automatically picks the best strategy for each market condition.
3. **Keep risk at 1-2%** until you're confident the bot is performing.
4. **Don't touch positions manually.** Let the bot manage SL/TP. Manual interference confuses Position Lock.

### For Advanced Users
1. **Create asset-specific profiles.** Separate forex and crypto profiles give you finer control.
2. **Schedule crypto sessions.** Crypto is 24/7 but volatility spikes at certain hours. Use the Schedule tab.
3. **Use the Strategy Workshop** (Settings → Strategy) to view detailed descriptions and stats for each strategy, enabling you to make informed decisions.
4. **Backtest first.** Run `python scripts/run_backtest.py` before deploying a new strategy live.

### Common Mistakes to Avoid
- ❌ **Turning the bot on with no risk limits.** Always set Max Exposure and Daily Loss.
- ❌ **Running too many symbols with too little capital.** The Leverage Sentry will block most entries.
- ❌ **Manually closing trades the bot opened.** It breaks Position Lock tracking.
- ❌ **Changing strategies mid-trade.** Wait for open positions to close first.
- ❌ **Ignoring the logs.** The first few days, watch the log to understand what the bot is doing.

---

## 🆘 Troubleshooting

| Problem | Fix |
|---|---|
| **"Another instance is already running"** | Delete `logs/tradebot.lock` and restart |
| **Bot scans but never trades** | Check risk settings — capital may be too low for position sizing |
| **"Leverage Sentry" blocking everything** | Add more capital, reduce position count, or increase leverage cap |
| **Decisions say "No signals found"** | Normal — the bot is being selective. Wait for better market conditions |
| **Crypto P&L seems wrong** | Check `crypto_qty_steps` in your profile — incorrect step sizes cause rounding issues |
| **UI not loading profiles** | Ensure `config/settings_profiles.yaml` exists (check `config_backup/` if missing) |

---

## 📚 Further Reading

| Document | What It Covers |
|---|---|
| `RTFM/01_PHILOSOPHY.md` | Design philosophy and core principles |
| `RTFM/08_API_SETUP.md` | Detailed broker API setup (IBKR, OANDA, CCXT) |
| `RTFM/09_FEET_WET_STRATEGY.md` | Deep dive into strategy selection |
| `RTFM/06_PANIC_BUTTON.md` | Emergency procedures |
| `RTFM/07_COCKPIT_CONTROLS.md` | GUI controls reference |
| `Rubberband_Reaper_Strategy.md` | How the flagship strategy works |

---

*Last updated: February 2026 | Trade by SCI v2.x*
