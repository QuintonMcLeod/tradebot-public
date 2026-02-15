
# 19. The Hybrid Engine (Multi-Broker Orchestration)
> *"One broker is a dependency. Two brokers is a strategy. Three brokers is an empire."*

You don't keep all your eggs in one basket. You don't put all your passwords in one text file. (Right? RIGHT?) So why would you run all your trades through one broker?

TradeBot SCI supports **multi-broker, multi-market orchestration** — the ability to trade forex through OANDA, crypto through Gemini, and stocks through IBKR, all from the same dashboard, at the same time, with the same strategies.

---

## The Architecture: How It Works

The bot has a concept of **providers** — an abstraction layer that speaks a common language regardless of which broker is underneath.

```
Your Strategy Engine
        ↓
  "I want to BUY EURUSD"
        ↓
  Routing Layer: "EURUSD is forex → send to OANDA"
        ↓
  OANDA Broker: *opens position*
```

```
Your Strategy Engine
        ↓
  "I want to BUY SOLUSD"
        ↓
  Routing Layer: "SOLUSD is crypto → send to CCXT/Gemini"
        ↓
  CCXT Broker: *opens position*
```

The strategy engine doesn't know or care which broker handles the trade. It just says "buy this symbol" and the routing layer figures out where to send it.

---

## Supported Brokers

| Broker | Markets | Role |
|--------|---------|------|
| **OANDA** | Forex, Metals, Indices, Commodities | Primary forex broker |
| **Gemini** (via CCXT) | Crypto | Crypto exchange |
| **Coinbase** (via CCXT) | Crypto | Alternative crypto exchange |
| **Interactive Brokers** | Stocks, Forex, Futures, Options | Institutional-grade everything |
| **Paper Broker** | All | Built-in simulation (no real money) |

---

## Broker Modes

### Simple Mode: One Broker Does Everything
```yaml
broker_mode: "simple"
exchange_provider: "oanda"
```
All symbols route to OANDA. Simple, clean, limited to what OANDA offers.

### Primary Mode: The "Main Character" Broker
```yaml
broker_mode: "primary"
primary_broker: "ibkr"
primary_market_provider: "ibkr"
```
Everything routes through IBKR. The big leagues.

### Hybrid Mode: The Full Orchestra
```yaml
broker_mode: "hybrid"
primary_broker: "oanda"
primary_market_provider: "oanda"
alternative_broker: "ccxt"
alternative_market_data: "ccxt"
```
Forex goes through OANDA. Crypto goes through CCXT. Each symbol routes to the right broker based on its asset class. The bot handles the routing automatically.

---

## The Routing Logic

When the bot evaluates a symbol, it asks:

1. **What asset class is this?** → Forex? Crypto? Equity?
2. **Which broker handles this class?** → OANDA for forex, CCXT for crypto
3. **Is that broker connected?** → Yes? Send the order. No? Log a warning.

The routing is deterministic. EUR/USD always goes to OANDA. BTC/USD always goes to CCXT. There's no ambiguity, no race conditions, no "which broker got it first?"

---

## Multi-Broker Benefits

| Benefit | Why It Matters |
|---------|---------------|
| **Diversification** | One broker goes down? The other still work. |
| **Best Execution** | OANDA has tight forex spreads. Gemini has deep crypto liquidity. Use each for what they're best at. |
| **Asset Coverage** | No single broker covers everything. Hybrid mode lets you trade forex AND crypto AND stocks. |
| **Redundancy** | Broker API outage? Your other positions are unaffected. |

---

## The Catch

Multi-broker mode requires more API keys, more configuration, and more things that can individually break. If you're just starting out, pick one broker and master it. Add complexity later.

**Rule of Thumb:**
*   Trading only forex? → OANDA. Done.
*   Trading only crypto? → CCXT with Gemini. Done.
*   Trading both? → Hybrid mode. Welcome to the big leagues.
*   Trading everything including stocks? → IBKR primary + CCXT alternative. You're now running a hedge fund from your living room.
