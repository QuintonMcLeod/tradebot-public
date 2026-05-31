---
title: 23 The Hybrid Engine: Multi-Broker Orchestration
category: rtfm
icon: hub
description: '"One broker is a dependency. Two brokers is a strategy. Three brokers
  is an empire." How the bot routes trades to different brokers based on asset class:
  OANDA for forex, CCXT for crypto, IBKR for stocks. Simple mode, primary mode, and
  full hybrid mode explained. Architecture diagrams, routing logic, and when to add
  complexity versus when to keep it simple.'
---

# 23. The Hybrid Engine — Multi-Broker Orchestration

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"The Hybrid Engine lets you use one broker for data and another for execution. One broker is a dependency. Two brokers is a strategy. Three brokers is an empire."</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"You don't put all your eggs in one basket, do you? You don't put all your passwords in a text file named 'passwords.txt' right on your desktop. (Well, maybe you do, but you shouldn't!) So why are you running every single trade through one broker like a peasant?<br><br>The Hybrid Engine orchestrates multiple brokers. OANDA for forex. CCXT for crypto. IBKR for stocks. All at the same time. You're building an empire, act like it."</td></tr></table>

---

## The Architecture

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

<table><tr><td width="170"><img src="img/conductor.png" width="150"></td><td><b>CONDUCTOR</b>:<br>"The strategy engine doesn't know or care which broker handles the trade. It just says 'buy this symbol' and the routing layer figures out where to send it. Clean separation."</td></tr></table>

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

### Primary Mode: The "Main Character" Broker
```yaml
broker_mode: "primary"
primary_broker: "ibkr"
primary_market_provider: "ibkr"
```

### Hybrid Mode: The Full Orchestra
```yaml
broker_mode: "hybrid"
primary_broker: "oanda"
primary_market_provider: "oanda"
alternative_broker: "ccxt"
alternative_market_data: "ccxt"
```

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"It's simple. Forex goes to OANDA. Crypto goes to CCXT. The bot plays traffic cop so you don't have to. You just tell it the mode, and it sends the orders to the right place while you take all the credit."</td></tr></table>

---

## The Routing Logic

1. **What asset class is this?** → Forex? Crypto? Equity?
2. **Which broker handles this class?** → OANDA for forex, CCXT for crypto
3. **Is that broker connected?** → Yes? Send the order. No? Log a warning.

Deterministic. EUR/USD always goes to OANDA. BTC/USD always goes to CCXT. No ambiguity.

---

## Multi-Broker Benefits

| Benefit | Why It Matters |
|---------|---------------|
| **Diversification** | One broker goes down? Others still work. |
| **Best Execution** | OANDA has tight forex spreads. Gemini has deep crypto liquidity. |
| **Asset Coverage** | No single broker covers everything. |
| **Redundancy** | API outage? Other positions unaffected. |

---

## The Rule of Thumb

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Start simple. Add complexity later:"</td></tr></table>

| Scenario | Recommendation |
|----------|---------------|
| Trading only forex | OANDA. Done. |
| Trading only crypto | CCXT with Gemini. Done. |
| Trading both | Hybrid mode. Welcome to the big leagues. |
| Trading everything including stocks | IBKR primary + CCXT alternative. You're now running a hedge fund from your living room. |

---

## 📖 Continue Reading

<table><tr><td width="170"><img src="img/rookie.png" width="150"></td><td><b>ROOKIE</b>:<br>"Wow, okay I think I get it now. What's next?"</td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Turn the page. We are going to talk about <b>Minovsky Engine</b>. Try to keep up."</td></tr></table>
