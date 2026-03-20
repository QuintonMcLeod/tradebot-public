# 16. The War Room — Decoding the Log Output

<table><tr><td width="170"><img src="img/chad.png" width="150"></td><td><b>CHAD</b>:<br>"Welcome to the War Room. This is where we review the carnage and plan the next assault."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"I know what happened. You opened the log panel, you saw a wall of hacker-looking text scrolling by at the speed of light, and you immediately had a panic attack. Half of it is green, half of it is yellow, and then you see one red line and you start crying.<br><br>Calm down. Take a breath. It's just a log file. Let me teach you how to read it before you hyperventilate."</td></tr></table>

---

## Log Anatomy: What You're Looking At

Every log line follows this format:
```
2026-01-15 14:32:07 | INFO | [TAG] Message here
```

| Part | What It Means |
|------|--------------|
| **Timestamp** | When it happened. In YOUR timezone. |
| **Level** | How serious: DEBUG, INFO, WARNING, ERROR, CRITICAL |
| **Tag** | The subsystem talking: [STATE], [GUARD], [DECISION], etc. |
| **Message** | What actually happened in plain-ish English |

---

## The Tags Dictionary

### Core System Tags

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"Each tag is a subsystem announcing what it's doing. Think of it like a police radio — each department has its own frequency."</td></tr></table>

| Tag | Translation |
|-----|-----------|
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
|-----|-----------|
| `[POSITION_LOCK]` | "Already a trade on this symbol. Blocked." |
| `[LEVERAGE]` | "Adding this would exceed leverage cap. Blocked." |
| `[AFFORDABILITY]` | "You can't afford this. Blocked." |
| `[RISK]` | "Risk math doesn't check out. Blocked." |
| `[KILL_SWITCH]` | "Daily loss limit hit. ALL trading blocked." |
| `[STABILITY]` | "Things are too volatile. Taking it easy." |

### Market & Data Tags

| Tag | Translation |
|-----|-----------|
| `[MARKET]` | "Fetching candles, prices, or market data." |
| `[PROVIDER]` | "The data source said something." IBKR, OANDA, CCXT responses. |
| `[WS]` | "WebSocket." GUI-to-backend chatter. |
| `[CANDLE]` | "New candle data received." The bot's bread and butter. |

### Broker Tags

| Tag | Translation |
|-----|-----------|
| `[OANDA]` | "OANDA is talking." Orders, fills, errors. |
| `[CCXT]` | "Crypto exchange is talking." Same energy, different market. |
| `[IBKR]` | "Interactive Brokers is talking." Usually complaining. |
| `[PAPER]` | "This is simulated." Paper mode active. |

---

## Reading a Trade's Lifecycle

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Here's what a successful trade looks like in the logs. Read this until you can parse it in your sleep:"</td></tr></table>

```
14:32:07 | INFO | [SCAN] Evaluating EURUSD...
14:32:07 | INFO | [STATE] EURUSD open_position: none
14:32:08 | INFO | [DECISION] EURUSD → ENTER_LONG score=82.4 strategy=trend_rider
14:32:08 | INFO | [GUARD] Position Lock: PASS (no existing position)
14:32:08 | INFO | [GUARD] Leverage Sentry: PASS (2.1x / 10.0x cap)
14:32:08 | INFO | [ENTRY] EURUSD LONG 10000 units @ 1.0850 SL=1.0820 TP=1.0920
14:32:08 | INFO | [OANDA] Order filled: EURUSD BUY 10000 @ 1.08503
```

And here's a **blocked** trade:

```
14:35:12 | INFO | [SCAN] Evaluating GBPUSD...
14:35:12 | INFO | [STATE] GBPUSD open_position: side=long size=5000
14:35:13 | INFO | [DECISION] GBPUSD → ENTER_SHORT score=71.2 strategy=mean_reversion
14:35:13 | WARNING | [POSITION_LOCK] GBPUSD already has LONG position. Blocked.
```

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"The bot wanted to go short, but there's already a long position. Position Lock said no. This is exactly how it should work — no position whiplash."</td></tr></table>

---

## The Severity Guide

| Level | What It Means | Should You Worry? |
|-------|--------------|-------------------|
| `DEBUG` | Internal details. Bot talking to itself. | No. |
| `INFO` | Normal operation. Everything fine. | No. This is the good stuff. |
| `WARNING` | Unexpected but recoverable. | Glance. Usually a blocked trade. |
| `ERROR` | Something broke but bot recovered. | Read it. Usually an API hiccup. |
| `CRITICAL` | Something is seriously wrong. | **Yes.** Action needed. |

---

## The JSON Blobs

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"What's all that weird JSON garbage in the logs?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"That's the GUI data feed. The JSON is machine-readable so the dashboard can parse it and show you the pretty version. You don't need to read it with your human eyes. The GUI reads it with its robot eyes. Trust the process."</td></tr></table>

---

## Pro Tips for Log Reading

<table><tr><td width="170"><img src="img/ninja.png" width="150"></td><td><b>NINJA</b>:<br><em>"Five rules for the War Room:"</em></td></tr></table>

1. **Filter by tag.** Only care about trades? Filter for `[ENTRY]` and `[EXIT]`.
2. **Watch `[GUARD]` tags.** Lots of blocks = settings too tight or dangerous market.
3. **Red lines aren't always bad.** A brief IBKR reconnect `ERROR` is normal. Only worry if it repeats.
4. **Logs rotate.** Old logs → `tradebot.log.1`, `.2`, etc. Current session → `tradebot.log`.
5. **`[DECISION]` is the most powerful line.** It tells you what the bot decided, the score, and which strategy called it. This is where you evaluate the bot's intelligence.
