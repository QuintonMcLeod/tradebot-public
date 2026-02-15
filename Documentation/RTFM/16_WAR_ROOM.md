
# 16. The War Room (Decoding the Log Output)
> *"I see the Matrix now. It's mostly INFO lines."*

You opened the log panel. You saw a wall of text scrolling by at the speed of anxiety. Half of it is green, half of it is yellow, and there's an occasional red line that makes your heart skip a beat.

Don't worry. This is normal. Let's learn to read the Matrix.

---

## Log Anatomy: What You're Looking At

Every log line follows this format:
```
2026-01-15 14:32:07 | INFO | [TAG] Message here
```

| Part | What It Means |
|------|--------------|
| **Timestamp** | When it happened. Yes, these are in YOUR timezone. |
| **Level** | How serious it is: DEBUG, INFO, WARNING, ERROR, CRITICAL |
| **Tag** | The subsystem talking: [STATE], [GUARD], [DECISION], etc. |
| **Message** | What actually happened in plain-ish English |

---

## The Tags Dictionary

### Core System Tags

| Tag | Translation |
|-----|------------|
| `[STATE]` | "Here's what I'm looking at right now." Position snapshots, sizes, prices. |
| `[DECISION]` | "I made a call." The strategy's verdict: BUY, SELL, or STAND ASIDE. |
| `[GUARD]` | "Something tried to trade but I blocked it." Safety guard intervention. |
| `[ENTRY]` | "Opening a position." Money is moving. |
| `[EXIT]` | "Closing a position." Hopefully more money is coming back. |
| `[HOLDINGS]` | "Here's everything you own right now." JSON blob of all positions. |
| `[PROFILE]` | "This is the active trading profile." Appears once at startup. |
| `[BUILD]` | "Here's what version is running." Git SHA and build info. |
| `[SCAN]` | "Looking at this symbol now." The bot's eye is on a specific chart. |

### Safety & Guard Tags

| Tag | Translation |
|-----|------------|
| `[POSITION_LOCK]` | "There's already a trade on this symbol. Blocked." |
| `[LEVERAGE]` | "Adding this trade would exceed your leverage cap. Blocked." |
| `[AFFORDABILITY]` | "You can't afford this trade. Blocked." |
| `[RISK]` | "The risk math doesn't check out. Blocked." |
| `[KILL_SWITCH]` | "Daily loss limit hit. ALL trading blocked until reset." |
| `[STABILITY]` | "Things are too volatile. Taking it easy." |

### Market & Data Tags

| Tag | Translation |
|-----|------------|
| `[MARKET]` | "Fetching candles, prices, or market data." |
| `[PROVIDER]` | "The data source said something." IBKR, OANDA, CCXT responses. |
| `[WS]` | "WebSocket communication." GUI-to-backend chatter. |
| `[CANDLE]` | "New candle data received." The bot's bread and butter. |

### Broker Tags

| Tag | Translation |
|-----|------------|
| `[OANDA]` | "The OANDA broker is talking." Orders, fills, errors. |
| `[CCXT]` | "The crypto exchange is talking." Same energy, different market. |
| `[IBKR]` | "Interactive Brokers is talking." Usually complaining about something. |
| `[PAPER]` | "This is a simulated trade." Paper mode active. |

---

## Reading a Trade's Lifecycle

Here's what a successful trade looks like in the logs:

```
14:32:07 | INFO | [SCAN] Evaluating EURUSD...
14:32:07 | INFO | [STATE] EURUSD open_position: none
14:32:08 | INFO | [DECISION] EURUSD → ENTER_LONG score=82.4 strategy=trend_rider
14:32:08 | INFO | [GUARD] Position Lock: PASS (no existing position)
14:32:08 | INFO | [GUARD] Leverage Sentry: PASS (2.1x / 10.0x cap)
14:32:08 | INFO | [ENTRY] EURUSD LONG 10000 units @ 1.0850 SL=1.0820 TP=1.0920
14:32:08 | INFO | [OANDA] Order filled: EURUSD BUY 10000 @ 1.08503
```

And here's a blocked trade:

```
14:35:12 | INFO | [SCAN] Evaluating GBPUSD...
14:35:12 | INFO | [STATE] GBPUSD open_position: side=long size=5000
14:35:13 | INFO | [DECISION] GBPUSD → ENTER_SHORT score=71.2 strategy=mean_reversion
14:35:13 | WARNING | [POSITION_LOCK] GBPUSD already has LONG position. Blocked.
```

The bot wanted to go short on GBPUSD, but there's already a long position open. Position Lock said no. This is exactly how it should work — no position whiplash.

---

## The Severity Guide

| Level | What It Means | Should You Worry? |
|-------|--------------|-------------------|
| `DEBUG` | Internal details. The bot talking to itself. | No. You shouldn't even see these. |
| `INFO` | Normal operation. Everything is fine. | No. This is the good stuff. |
| `WARNING` | Something unexpected but recoverable. | Glance at it. Usually a blocked trade or a timeout. |
| `ERROR` | Something broke but the bot recovered. | Read it. Usually a broker API hiccup. |
| `CRITICAL` | Something is seriously wrong. | **Yes.** This means action is needed. |

---

## The JSON Blobs

Occasionally, you'll see a line that looks like someone vomited JSON:

```
[HOLDINGS] {"count": 3, "positions": [{"symbol": "EURUSD", ...}], "total_unrealized_pnl": 47.32}
```

This is intentional. The JSON is machine-readable so the GUI can parse it and display your holdings panel, charts, and P&L numbers. You don't need to read it with your human eyes. The GUI reads it with its robot eyes and shows you the pretty version.

---

## Pro Tips for Log Reading

1. **Filter by tag.** If you only care about trades, filter for `[ENTRY]` and `[EXIT]`.
2. **Watch the `[GUARD]` tags.** If you see a lot of blocks, your safety settings might be too tight — or the market is genuinely dangerous right now.
3. **Red lines aren't always bad.** An `ERROR` for a brief IBKR reconnect is normal. It self-heals. Only worry if you see the same error repeating continuously.
4. **The log rotates.** Old logs roll into `tradebot.log.1`, `.2`, etc. Your current session is always in `tradebot.log`.
5. **The most powerful log line is `[DECISION]`.** It tells you what the bot decided, what score it gave, and which strategy made the call. If you want to evaluate the bot's intelligence, this is where you look.
