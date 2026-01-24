# 08_API_SETUP: Connecting the Wires

> **"The bot is only as smart as its connection."**

This guide explains specifically **how to connect** this bot to the outside world. This includes:
- **AI Brain** (TradeSci/OpenAI/Gemini/Claude)
- **IBKR** (Interactive Brokers) for stocks, options, futures
- **OANDA** for forex
- **CCXT** for crypto exchanges

---

## 1. The AI Brain (LLM Providers)

The bot uses an LLM (Large Language Model) to generate commentary and, in some modes, assist with decision validation.

### Supported Providers

| Provider | Key Variable | Notes |
|----------|--------------|-------|
| **Gemini** | `GEMINI_API_KEY` | Recommended. Good balance of quality & cost. |
| **OpenAI** | `CHATGPT_KEY` | GPT-4, GPT-4 Turbo, GPT-3.5 |
| **Claude** | `ANTHROPIC_API_KEY` | Claude 3 Opus, Sonnet, Haiku |
| **DeepSeek** | `DEEPSEEK_API_KEY` | Cost-effective alternative |
| **OpenRouter** | `OPENROUTER_API_KEY` | Access multiple models via one API |

### How to Configure
1.  **GUI (Recommended)**:
    - Open Settings → **Intelligence** tab.
    - **Provider**: Select your provider (e.g., `gemini`).
    - **API Key**: Enter your key.
    - **Model**: Select the model (e.g., `gemini-pro`, `gpt-4-turbo`).
    - Click **Save**.

2.  **.env File**:
    ```bash
    TRADE_SCI_PROVIDER=gemini
    GEMINI_API_KEY=your-key-here
    TRADE_SCI_MODEL_NAME=gemini-pro
    ```

3.  **Environment Variables**:
    - Export the relevant key in your shell before running the bot.

### "Custom" Provider (Local LLMs / Proxies)
If you are using a local LLM (like Ollama, LM Studio) or a corporate proxy:
- **Provider**: `custom`
- **Base URL**: Set to your endpoint (e.g., `http://localhost:11434/v1`).
- **API Key**: Often ignored by local LLMs, but put `dummy` if required.

---

## 2. Interactive Brokers (IBKR) - The Hard Part

Connecting to IBKR requires the **TWS (Trader Workstation)** or **IB Gateway** software running on your machine. The bot talks to this software, not directly to IBKR servers.

### Step 1: Install TWS or IB Gateway
- **TWS**: Full graphical interface. Heavy, but good for watching the chart while the bot trades.
- **IB Gateway**: Lightweight, no UI. Best for running the bot 24/7 on a server.
- **Download**: [Interactive Brokers Website](https://www.interactivebrokers.com/en/trading/tws.php)

### Step 2: Configure TWS/Gateway API Settings
**CRITICAL:** The bot cannot connect unless you change these specific settings inside TWS.

1.  Open TWS/Gateway and login (Paper or Live).
2.  Go to **File** → **Global Configuration**.
3.  Navigate to **API** → **Settings**.
4.  **Check** `Enable ActiveX and Socket Clients`.
5.  **Uncheck** `Read-Only API` (unless you only want to monitor).
6.  **Socket Port**:
    - **7497** is the default for **Paper Trading** (Simulated).
    - **7496** is the default for **Live Trading** (Real Money).
    - *Make sure this matches the `IBKR_PORT` setting in the bot.*
7.  **Trusted IPs**:
    - If running on `localhost` (same machine), you usually don't need this.
    - If running inside Docker or a VM, add `127.0.0.1` or the container IP.
8.  **Uncheck** `Download open orders on connection` (optional, makes startup faster).

### Step 3: Configure the Bot
- **GUI**: Settings → **Broker (IBKR)** tab.
- **Host**: `127.0.0.1` (if on same machine).
- **Port**: `7497` (Paper) or `7496` (Live).
- **Client ID**: `1` (Must be unique. If you run two bots, set the second one to `2`).
- **Account ID**: Leave blank to auto-detect, or specify if you have multiple linked accounts.

### Troubleshooting IBKR
- **"Connection Refused"**: TWS is not running, or the Port is wrong. Check if TWS is logged into Paper (7497) or Live (7496).
- **"Client ID already in use"**: You have another script or dashboard open with the same Client ID. Change `IBKR_CLIENT_ID`.
- **"No Market Data Permissions"**: Your IBKR account doesn't have a subscription for that symbol.
    - *Fix:* Subscribe in Account Management or use "Delayed Data" (Settings → Broker → Allow Delayed Data).

---

## 3. OANDA (Forex) - The Easy Way

OANDA is the recommended broker for forex trading. No gateway software required — just API keys.

### Step 1: Create an OANDA Account
1. Go to [OANDA](https://www.oanda.com) and sign up.
2. Choose **fxTrade Practice** (demo) to start, or **fxTrade** (live) when ready.
3. Note your **Account ID** (format: `101-001-1234567-001`).

### Step 2: Generate API Token
1. Log into [OANDA Hub](https://hub.oanda.com) (or fxTrade web).
2. Navigate to **Manage API Access** (under Account settings).
3. Click **Generate** to create a new token.
4. **Copy the token immediately** — it's only shown once!
5. Store it securely (password manager recommended).

### Step 3: Configure the Bot
- **GUI**: Settings → **Brokers** → **OANDA** tab.
- **Account ID**: `101-001-1234567-001` (your account number).
- **API Key**: Paste your token.
- **Environment**: `practice` (demo) or `live` (real money).
- **Read Only**: Enable if you only want to monitor, not trade.

### Key Variables (.env)
```bash
OANDA_ACCOUNT_ID=101-001-1234567-001
OANDA_API_KEY=your-api-token-here
OANDA_ENVIRONMENT=practice   # or "live"
OANDA_READ_ONLY=false
```

### Troubleshooting OANDA
- **"Invalid Account ID"**: Check the format. It should be `XXX-XXX-XXXXXXX-XXX`.
- **"Unauthorized"**: Your API token is wrong or expired. Regenerate it.
- **"Insufficient Margin"**: Not enough funds in the account for the position size.
- **"Market Halted"**: Forex markets are closed (weekends, holidays). Wait.

### OANDA Symbol Format
OANDA uses underscore format: `EUR_USD`, `GBP_JPY`, `USD_CAD`.
The bot handles translation automatically.

---

## 5. Crypto Exchanges (CCXT)

For pure crypto trading (Binance, Coinbase, Kraken, etc.) using the CCXT library.

### How to Configure
1.  **GUI**: Settings → **Brokers** → **CCXT** tab.
2.  **Key Variables**:
    - `CCXT_EXCHANGE`: The exchange ID (e.g., `binance`, `coinbase`, `kraken`).
    - `CCXT_API_KEY`: Your API Key.
    - `CCXT_SECRET`: Your API Secret.
    - `CCXT_PASSWORD`: (Optional) If your exchange requires a passphrase.
    - `CCXT_SANDBOX`: Set to `true` for testnet mode.
3.  **Symbol Mapping**:
    - The bot thinks in "BTCUSD". Your exchange might need "BTC/USD" or "BTC/USDT".
    - Set `CCXT_SYMBOL_MAP=BTCUSD:BTC/USDT,ETHUSD:ETH/USDT`.

### Supported Exchanges
Any exchange supported by [CCXT](https://github.com/ccxt/ccxt):
- Coinbase (Advanced Trade)
- Binance / Binance.US
- Kraken
- Gemini
- KuCoin
- And 100+ more...

---

## 6. Hybrid Mode (Data + Execution Split)

You can use different brokers for data vs. execution:

| Setting | Options |
|---------|---------|
| `MARKET_DATA_MODE` | `primary` (IBKR), `oanda`, `alternative` (CCXT), `hybrid` |
| `BROKER_MODE` | `primary` (IBKR), `oanda`, `alternative` (CCXT), `hybrid` |

**Example:** Get forex data from OANDA but execute via IBKR:
```bash
MARKET_DATA_MODE=oanda
BROKER_MODE=primary
```

---

## 7. Verification

How do you know it's working?

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

If you see prices, **you are live.**
