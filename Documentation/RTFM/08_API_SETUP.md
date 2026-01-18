# 08_API_SETUP: Connecting the Wires

> **"The bot is only as smart as its connection."**

This guide explains specifically **how to connect** this bot to the outside world. This includes the **AI Brain** (TradeSci/OpenAI), the **Broker** (Interactive Brokers), and **Crypto Exchanges** (CCXT).

---

## 1. The AI Brain (TradeSci / OpenAI)

The bot uses an LLM (Large Language Model) to generate commentary and, in some modes, assist with decision validation.

### How to Configure
You have three ways to set this up:

1.  **GUI (Recommended)**:
    - Open Settings → **AI / Commentary**.
    - **Provider**: Select `openai` (default) or `custom`.
    - **API Key**: Enter your key in the `TradeSci / OpenAI Key` field.
    - **Model**: Select `gpt-4-turbo` or `gpt-3.5-turbo` (or your preferred model).
    - Click **Save to .env**.

2.  **.env File**:
    - Open `.env` in a text editor.
    - Set `TRADE_SCI_API_KEY=sk-...`

3.  **Environment Variables**:
    - Export `TRADE_SCI_API_KEY` in your shell before running the bot.

### "Custom" Provider (Local LLMs / Proxies)
If you are using a local LLM (like Oobabooga, LM Studio) or a tailored corporate proxy:
- **Provider**: `custom`
- **Base URL**: Set to your endpoint (e.g., `http://localhost:5000/v1`).
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

## 3. Crypto Exchanges (CCXT)

For pure crypto trading (Binance, Coinbase, Kraken, etc.) using the CCXT library.

### How to Configure
1.  **GUI**: Advanced Environment Table (or `.env` file).
2.  **Key Variables**:
    - `EXCHANGE_PROVIDER=CCXT` (Switches logic to CCXT mode).
    - `CCXT_EXCHANGE`: The exchange ID (e.g., `binance`, `coinbase`, `kraken`).
    - `CCXT_API_KEY`: Your API Key.
    - `CCXT_SECRET`: Your API Secret.
    - `CCXT_PASSWORD`: (Optional) If your exchange requires a passphrase (e.g., Coinbase Pro).
3.  **Symbol Mapping**:
    - The bot thinks in "BTCUSD". Your exchange might need "BTC/USD" or "BTC/USDT".
    - Set `CCXT_SYMBOL_MAP=BTCUSD:BTC/USDT,ETHUSD:ETH/USDT`.

---

## 4. Verification

How do you know it's working?

1.  **Start the Bot**: `./scripts/tradebot.sh --profile feet_wet`
2.  **Watch the Logs**:
    - **Success**: `[INFO] Connected to IBKR on 127.0.0.1:7497, Client ID 1`
    - **Success**: `[INFO] Market Data Feed Active`
3.  **Check Connectivity**:
    - The bot should start printing price updates: `[PRICE] BTCUSD: 65000.00`
    - If you see prices, **you are live.**
