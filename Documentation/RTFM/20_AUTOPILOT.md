# 20. The Autopilot — Auto-Schedule & Profile Switching

<table><tr><td width="170"><img src="img/bot.png" width="150"></td><td><b>THE BOT</b>:<br><em>"Autopilot engaged. I handle the trading. You handle the living."</em></td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Markets aren't all open at the same time. London opens at 3 AM Eastern. Tokyo opens at 7 PM Eastern. Crypto never opens because it never closes. Trying to trade all of them with one fixed schedule is like wearing the same outfit to a business meeting, a beach party, and a funeral.<br><br>That's why the bot has Auto-Schedule — automatic profile switching based on what session is active."</td></tr></table>

---

## The Problem With Fixed Schedules

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"A fixed schedule means your bot is scanning an empty parking lot at 2 AM when nobody's trading EUR/USD, and missing the Tokyo session where JPY crosses are actually moving. Auto-Schedule fixes this."</td></tr></table>

---

## How It Works

| Time (EST) | Session | Active Profile | What's Traded |
|-----------|---------|---------------|--------------|
| 19:00–03:00 | Asian / Tokyo | `asian_session` | JPY crosses, AUD/NZD, crypto |
| 03:00–08:00 | London | `forex_continuous` | Major forex pairs |
| 08:00–12:00 | NY + London Overlap | `overlap_session` | Everything — widest net |
| 12:00–17:00 | New York | `new_york_session` | USD-centric pairs + crypto |
| 17:00–19:00 | After Hours | `crypto_247` | Crypto only |
| Saturday–Sunday | Weekend | `weekend_crypto` | Crypto only, conservative |

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Every hour is covered. When forex sleeps, the bot switches to crypto. When Tokyo opens, it pivots to JPY crosses. When London explodes open, it goes to major pairs with breakout strategies. Maximum coverage, minimum wasted scans."</td></tr></table>

---

## The Session Profiles

### `asian_session` — The Chess Game (7 PM – 3 AM EST)

```yaml
asian_session:
  symbols: [USDJPY, EURJPY, GBPJPY, AUDJPY, NZDJPY, CADJPY, AUDUSD, NZDUSD, BTCUSD, ETHUSD, SOLUSD, XRPUSD]
  strategies:
    forex: mean_reversion
    crypto: supply_demand
  candle_timeframe: 15m
  market_poll_interval_seconds: 30
  stop_atr_multiplier: 1.2
  max_concurrent_positions: 3
```

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"Why Mean Reversion? Tokyo is notorious for price oscillating between support and resistance. JPY crosses are most liquid here. Mean reversion catches the bounces."</td></tr></table>

---

### `new_york_session` — The Power Hour (12 PM – 5 PM EST)

```yaml
new_york_session:
  symbols: [EURUSD, GBPUSD, USDJPY, USDCAD, USDCHF, AUDUSD, NZDUSD, EURJPY, GBPJPY, BTCUSD, ETHUSD, SOLUSD, XRPUSD]
  strategies:
    forex: rubberband_reaper
    crypto: supply_demand
  candle_timeframe: 15m
  market_poll_interval_seconds: 15
  max_pyramid_entries: 6
```

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"New York is where the big money lives. USD is king. Moves are directional. Institutional flow is massive. Rubberband Reaper catches the pullbacks without chasing."</td></tr></table>

---

### `overlap_session` — The Arena (8 AM – 12 PM EST)

```yaml
overlap_session:
  symbols: [EURUSD, GBPUSD, USDJPY, USDCAD, USDCHF, AUDUSD, NZDUSD, GBPJPY, EURJPY, AUDJPY, EURGBP, GBPCHF, BTCUSD, ETHUSD, SOLUSD, XRPUSD, LINKUSD, LTCUSD]
  strategies:
    forex: volatility_breakout
    crypto: supply_demand
  candle_timeframe: 5m
  market_poll_interval_seconds: 10
  max_concurrent_positions: 5
```

<table><tr><td width="170"><img src="img/chad.png" width="150"></td><td><b>CHAD</b>:<br>"The London–New York overlap. Single most volatile period in forex. Both London and NY active simultaneously. This is where the most money is made — and lost."</td></tr></table>

---

### `weekend_crypto` — The Night Shift (Saturday – Sunday)

```yaml
weekend_crypto:
  symbols: [BTCUSD, ETHUSD, SOLUSD, XRPUSD, LINKUSD, LTCUSD, DOGEUSD, ZECUSD, BCHUSD]
  strategies:
    crypto: supply_demand
  candle_timeframe: 15m
  stop_atr_multiplier: 2.0
  max_concurrent_positions: 3
  crypto_only: true
```

<table><tr><td width="170"><img src="img/bear.png" width="150"></td><td><b>BEAR</b>:<br>"Weekend crypto has 30-50% less liquidity. Flash wicks are more common. Spreads are wider. The profile is deliberately conservative — wider stops, slower polling, more patience between trades."</td></tr></table>

---

## Configuration

> 📺 Settings → **Hours & Sabbath** → toggle **Auto Schedule** ON

```yaml
auto_schedule_enabled: true
auto_schedule_profiles:
  asian: "asian_session"
  london: "forex_continuous"
  overlap: "overlap_session"
  new_york: "new_york_session"
  after_hours: "crypto_247"
  weekend: "weekend_crypto"
  default: "all_247"
```

---

## The Handoff

1. **Detects session transition** → "Asian ending. London opening."
2. **Flattens session positions** (if configured)
3. **Loads new profile** — London pairs, London strategies, London intervals
4. **Logs transition** → `[SCHEDULE] Session changed: asian → london → Profile: forex_continuous`
5. **Resumes scanning** — No restart needed

---

## Which One Should You Choose?

| Scenario | Recommendation |
|----------|---------------|
| Only forex | Fixed forex profile. No auto-schedule. |
| Only crypto | Fixed crypto profile. No auto-schedule. |
| Both, but lazy | `all_247` with Meta-SCI. Simple. |
| Both, want to optimize | Full auto-schedule with session profiles. |
| Maximum coverage | Every session mapped. Every hour covered. |

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"The Asian session alone is 20% of daily forex volume. The overlap is over 50%. If you're only trading one session, you're leaving half the opportunity on the table. The bot doesn't need coffee. It just needs the right profile at the right time."</td></tr></table>
