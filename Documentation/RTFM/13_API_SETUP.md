---
title: 13 Connecting to the World: Every Broker, Every API Key
category: rtfm
icon: key
description: '"The bot is only as smart as its connection." This guide explains specifically
  how to connect the bot to the outside world. Step-by-step configuration for every
  supported integration: the AI Brain (TradeSci, OpenAI, Gemini, Claude), Interactive
  Brokers for stocks and futures, OANDA for forex, and CCXT for crypto exchanges like
  Gemini and Coinbase.'
size: md
---

# 13. Connecting the Wires — API Setup Guide

<table><tr><td width="170"><img src="img/ninja.png" width="150"></td><td><b>NINJA</b>:<br><em>"API keys are your weapons. Handle them with care. Store them in .env.secrets. Never commit them to git. Never paste them in Discord. Never email them. If someone asks for your API key, they are not your friend."</em></td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"The bot is only as brilliant as its connection. If you don't connect it right, it's just a very complicated, very expensive paperweight humming on your desk doing nothing. Let's wire this thing up before you break something."</td></tr></table>

---

## 1. The AI Brain (LLM Providers)

<table><tr><td width="170"><img src="img/ghost.png" width="150"></td><td><b>GHOST (The AI)</b>:<br><em>"I need a language model to generate commentary, assist with decision validation, and power AI Optimize. Choose a provider. Any provider. Just choose one."</em></td></tr></table>

### Supported Providers

| Provider | Key Variable | Notes |
|----------|--------------|-------|
| **Gemini** | `GEMINI_API_KEY` | Recommended. Good balance of quality & cost. |
| **OpenAI** | `CHATGPT_KEY` | GPT-4, GPT-4 Turbo, GPT-3.5 |
| **Claude** | `ANTHROPIC_API_KEY` | Claude 3 Opus, Sonnet, Haiku |
| **DeepSeek** | `DEEPSEEK_API_KEY` | Cost-effective alternative |
| **OpenRouter** | `OPENROUTER_API_KEY` | Access multiple models via one API |

### How to Configure

**GUI (Recommended):**
1. Settings → **Intelligence** tab.
2. **Provider**: Select (e.g., `gemini`).
3. **API Key**: Enter your key.
4. **Model**: Select (e.g., `gemini-pro`, `gpt-4-turbo`).
5. Click **Save**.

**.env File:**
```bash
TRADE_SCI_PROVIDER=gemini
GEMINI_API_KEY=your-key-here
TRADE_SCI_MODEL_NAME=gemini-pro
```

### Custom Provider (Local LLMs / Proxies)
Using Ollama, LM Studio, or a corporate proxy?
- **Provider**: `custom`
- **Base URL**: Your endpoint (e.g., `http://localhost:11434/v1`)
- **API Key**: Often ignored by local LLMs, but put `dummy` if required

---

## 2. Interactive Brokers (IBKR) — The Hard Part

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"IBKR is the professional-grade broker. Stocks, options, futures, forex — they do it all. But connecting to IBKR is the hardest setup because it requires TWS or IB Gateway running locally. The bot talks to that software, not directly to IBKR servers.<br><br>It's worth it. But man, is the setup annoying."</td></tr></table>

### Step 1: Install TWS or IB Gateway
- **TWS**: Full graphical interface. Heavy, but good for watching charts.
- **IB Gateway**: Lightweight, no UI. Best for 24/7 server operation.
- **Download**: [Interactive Brokers Website](https://www.interactivebrokers.com/en/trading/tws.php)

### Step 2: Configure TWS/Gateway API Settings

> [!IMPORTANT]
> The bot CANNOT connect unless you change these specific settings inside TWS.

1. Open TWS/Gateway and login (Paper or Live).
2. **File** → **Global Configuration**.
3. Navigate to **API** → **Settings**.
4. **Check** `Enable ActiveX and Socket Clients`.
5. **Uncheck** `Read-Only API` (unless monitor-only).
6. **Socket Port**: 7497 = Paper, 7496 = Live. Must match `IBKR_PORT`.
7. **Trusted IPs**: `127.0.0.1` if running locally. Container IP if Docker.
8. **Uncheck** `Download open orders on connection` (faster startup).

### Step 3: Configure the Bot
- **GUI**: Settings → **Broker (IBKR)** tab.
- **Host**: `127.0.0.1`
- **Port**: `7497` (Paper) or `7496` (Live)
- **Client ID**: `1` (must be unique per connection)
- **Account ID**: Leave blank to auto-detect

### Troubleshooting IBKR

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"Three common problems. Three simple fixes:"</td></tr></table>

- **"Connection Refused"**: TWS not running, or wrong port. 7497 ≠ 7496.
- **"Client ID already in use"**: Another script is connected. Change `IBKR_CLIENT_ID`.
- **"No Market Data Permissions"**: Subscribe in Account Management or enable "Delayed Data."

---

## 3. OANDA (Forex) — The Easy Way

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"OANDA is the recommended forex broker. No gateway software needed — just API keys. Setup takes 3 minutes. It's the easiest broker connection in the entire system."</td></tr></table>

### Step 1: Create an OANDA Account
1. Go to [OANDA](https://www.oanda.com) and sign up.
2. Choose **fxTrade Practice** (demo) to start, or **fxTrade** (live) when ready.
3. Note your **Account ID** (format: `101-001-1234567-001`).

### Step 2: Generate API Token
1. Log into [OANDA Hub](https://hub.oanda.com).
2. Navigate to **Manage API Access**.
3. Click **Generate** to create a new token.
4. **Copy the token immediately** — it's only shown once!

<table><tr><td width="170"><img src="img/bear.png" width="150"></td><td><b>BEAR</b>:<br>"I cannot stress this enough. Copy it IMMEDIATELY. It is shown ONCE. If you close that window without copying, you generate a new one. Ask me how I know."</td></tr></table>

### Step 3: Configure the Bot
- **GUI**: Settings → **Brokers** → **OANDA** tab.
- **Account ID**: `101-001-1234567-001`
- **API Key**: Paste token
- **Environment**: `practice` (demo) or `live` (real money)

**.env.secrets:**
```bash
OANDA_ACCOUNT_ID=101-001-1234567-001
OANDA_API_KEY=your-api-token-here
OANDA_ENVIRONMENT=practice
```

### OANDA Symbol Format
OANDA uses underscore format: `EUR_USD`, `GBP_JPY`, `USD_CAD`. The bot handles translation automatically.

---

## 4. Crypto Exchanges (CCXT)

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"For crypto trading — Coinbase, Gemini, Kraken, Binance, and 100+ more — we use CCXT, a universal exchange library. One interface, many exchanges."</td></tr></table>

### How to Configure
1. **GUI**: Settings → **Brokers** → **CCXT** tab.
2. **Key Variables:**
    - `CCXT_EXCHANGE`: Exchange ID (e.g., `gemini`, `coinbase`, `kraken`)
    - `CCXT_API_KEY`: Your API Key
    - `CCXT_SECRET`: Your API Secret
    - `CCXT_PASSWORD`: (Optional) If exchange requires a passphrase
    - `CCXT_SANDBOX`: `true` for testnet mode
3. **Symbol Mapping:**
    - The bot thinks in `BTCUSD`. Your exchange might need `BTC/USD` or `BTC/USDT`.
    - Set `CCXT_SYMBOL_MAP=BTCUSD:BTC/USDT,ETHUSD:ETH/USDT`

### Supported Exchanges
Any exchange supported by [CCXT](https://github.com/ccxt/ccxt): Coinbase, Binance, Kraken, Gemini, KuCoin, and 100+ more.

---

## 5. Prop Firms (Apex, FTMO, FundedNext)

<table><tr><td width="170"><img src="img/ninja.png" width="150"></td><td><b>NINJA</b>:<br><em>"Trading someone else's money is the ultimate leverage. But remember — they have rules. The bot can handle the execution, but you must configure the routing."</em></td></tr></table>

### How to Configure

**GUI (Recommended):**
1. Settings → **Brokers** tab.
2. Scroll down to the **Prop Firm Routing (MT5 / NinjaTrader)** section.
3. Toggle on your chosen firm (e.g., **Enable FTMO Routing**, **Enable Apex Routing**).
4. Enter any corresponding API keys or account identifiers explicitly required by the prop firm.
5. Click **Save**. The bot will automatically restart its execution bridges to sync with the target firm's API protocols.

**Note:** Prop firm toggles natively override your `BROKER_MODE` and route all eligible trades directly to their respective bridges (e.g., MT5 copiers or NinjaTrader IPCs) while ignoring standard broker connections.

---

## 6. Hybrid Mode (Data + Execution Split)

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"You can use different brokers for data vs. execution. Data from OANDA, execution via IBKR. Data from CCXT, execution via IBKR. Like having one person read the map and another drive the car."</td></tr></table>

| Setting | Options |
|---------|---------|
| `MARKET_DATA_MODE` | `primary` (IBKR), `oanda`, `alternative` (CCXT), `hybrid` |
| `BROKER_MODE` | `primary` (IBKR), `oanda`, `alternative` (CCXT), `hybrid` |

**Example:** Forex data from OANDA, execution via IBKR:
```bash
MARKET_DATA_MODE=oanda
BROKER_MODE=primary
```

---

## 7. Verification — How Do You Know It's Working?

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"If you see prices, you are live. That's it. That's the whole test."</td></tr></table>

### IBKR
```
[INFO] Connected to IBKR on 127.0.0.1:7497, Client ID 1
[INFO] Market Data Feed Active
[PRICE] AAPL: 175.00
```

### OANDA
```
[INFO] Connected to OANDA (practice)
[INFO] Account: 101-001-1234567-001
[PRICE] EUR_USD: 1.0850
```

### CCXT
```
[INFO] Connected to Coinbase via CCXT
[PRICE] BTC/USD: 65000.00
```

<table><tr><td width="170"><img src="img/grandma.png" width="150"></td><td><b>GRANDMA</b>:<br>"If you see prices scrolling by, you're connected, sweetie. If you see red error text, go back to the troubleshooting sections above. Read them slowly. Every word."</td></tr></table>

---

## 📖 Continue Reading

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"Wow, okay I think I get it now. What's next?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Turn the page. We are going to talk about <b>Map Toc</b>. Try to keep up."</td></tr></table>
