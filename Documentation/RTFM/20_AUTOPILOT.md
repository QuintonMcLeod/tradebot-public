
# 20. The Autopilot (Auto-Schedule & Profile Switching)
> *"The bot doesn't have a 9-to-5. It has a 24/7 and a strong opinion about when to show up."*

Markets aren't all open at the same time. London opens at 3 AM Eastern. Tokyo opens at 7 PM Eastern. Crypto never opens because it never closes. Trying to trade all of them with one fixed schedule is like wearing the same outfit to a business meeting, a beach party, and a funeral.

That's why the bot has **Auto-Schedule** — the ability to automatically switch trading profiles based on what session is active.

---

## The Problem With Fixed Schedules

Let's say you set the bot to scan every 60 seconds and trade forex. That works great from 8 AM to 5 PM when New York is open. But what about:

*   **2 AM Eastern?** Nobody is trading EUR/USD. Spreads are wide. Liquidity is a ghost town. Your bot is scanning an empty parking lot and wondering why there are no setups.
*   **Saturday?** Forex is closed. The bot is literally checking prices that don't exist.
*   **Sunday night?** Crypto is going crazy while your forex-only profile stares at a blank screen.

Auto-Schedule solves all of this.

---

## How It Works

Auto-Schedule swaps your active trading profile based on **market sessions**:

| Time (EST) | Session | Active Profile | What's Being Traded |
|-----------|---------|---------------|---------------------|
| 19:00–03:00 | Asian / Tokyo Session | `asian_session` | JPY crosses, AUD/NZD, crypto |
| 03:00–08:00 | London Session | `forex_continuous` | Major forex pairs |
| 08:00–12:00 | NY + London Overlap | `overlap_session` | Everything — widest net, fastest scans |
| 12:00–17:00 | New York Session | `new_york_session` | USD-centric pairs + crypto |
| 17:00–19:00 | After Hours | `crypto_247` | Crypto only |
| Saturday–Sunday | Weekend | `weekend_crypto` | Crypto only, conservative mode |

Notice the pattern: **Every hour is covered.** When the forex market is sleeping, the bot doesn't sleep — it switches to the markets that are actually moving. When Tokyo opens, the bot shifts focus to JPY crosses and the range-bound Asian session pairs. When London explodes open, the bot pivots to the major pairs with breakout strategies. Maximum coverage, minimum wasted scans.

---

## The Session Profiles

Each session has a personality. The profiles are tuned to match.

### `asian_session` — The Chess Game (7 PM – 3 AM EST)

If London is a rock concert and New York is a boxing match, Tokyo is a chess game. Lower volatility, tighter ranges, and a market that tends to consolidate rather than trend.

```yaml
asian_session:
  symbols:
    # JPY Crosses — the stars of the Asian session
    - USDJPY
    - EURJPY
    - GBPJPY
    - AUDJPY
    - NZDJPY
    - CADJPY
    # AUD/NZD — their home session, peak liquidity
    - AUDUSD
    - NZDUSD
    # Crypto — always on
    - BTCUSD
    - ETHUSD
    - SOLUSD
    - XRPUSD
  strategies:
    forex: mean_reversion         # Range-bound markets → mean reversion
    crypto: supply_demand
  candle_timeframe: 15m
  market_poll_interval_seconds: 30  # Slower scan — Tokyo tempo
  ai_decision_interval_seconds: 120
  stop_atr_multiplier: 1.2         # Tighter stops — smaller moves
  risk_reward_ratio: 1.8
  max_concurrent_positions: 3
```

**Why Mean Reversion?** The Asian session is notorious for price oscillating between support and resistance. JPY crosses are most liquid here (Bank of Japan, Japanese institutions, exporters). AUD/NZD see peak liquidity in their home timezone.

---

### `new_york_session` — The Power Hour (12 PM – 5 PM EST)

New York is where the big money lives. The USD is king, the moves are directional, and the institutional flow is massive. This isn't a range-bound session — it's a trending one.

```yaml
new_york_session:
  symbols:
    # USD-centric pairs — the New York specialties
    - EURUSD
    - GBPUSD
    - USDJPY
    - USDCAD
    - USDCHF
    - AUDUSD
    - NZDUSD
    - EURJPY
    - GBPJPY
    # Crypto — still running
    - BTCUSD
    - ETHUSD
    - SOLUSD
    - XRPUSD
  strategies:
    forex: rubberband_reaper     # Trending markets → trend-following
    crypto: supply_demand
  candle_timeframe: 15m
  market_poll_interval_seconds: 15  # Standard pace
  ai_decision_interval_seconds: 60
  stop_atr_multiplier: 1.5
  risk_reward_ratio: 2.0           # Better risk/reward — stronger trends
  max_concurrent_positions: 4
  max_pyramid_entries: 6            # Ride the trends with pyramids
```

**Why Rubberband Reaper?** NY session produces clean trends driven by institutional order flow, economic data releases, and Fed speakers. The pullback-entry style of rubberband_reaper catches these moves without chasing.

---

### `overlap_session` — The Arena (8 AM – 12 PM EST)

The London–New York overlap is the **single most volatile period** in the forex market. Both London and New York traders are active simultaneously. Liquidity is at its peak. Moves are explosive. This is where the most money is made — and lost.

```yaml
overlap_session:
  symbols:
    # Every major and cross — cast the widest net
    - EURUSD
    - GBPUSD
    - USDJPY
    - USDCAD
    - USDCHF
    - AUDUSD
    - NZDUSD
    - GBPJPY
    - EURJPY
    - AUDJPY
    - EURGBP
    - GBPCHF
    # Crypto follows the energy
    - BTCUSD
    - ETHUSD
    - SOLUSD
    - XRPUSD
    - LINKUSD
    - LTCUSD
  strategies:
    forex: volatility_breakout   # Max volatility → breakout strategies
    crypto: supply_demand
  candle_timeframe: 5m             # Faster timeframe — rapid moves
  market_poll_interval_seconds: 10  # Aggressive polling
  ai_decision_interval_seconds: 30  # Fast decisions for fast markets
  stop_atr_multiplier: 1.8         # Wider stops — bigger moves
  risk_reward_ratio: 2.5           # Bigger reward targets
  max_concurrent_positions: 5       # Maximum opportunity capture
```

**Why Volatility Breakout?** The overlap session is when the most significant breakouts occur — London positions get challenged by New York flow, trapped traders panic, and big moves develop. The 5-minute timeframe and 10-second polling capture these rapid momentum shifts.

---

### `weekend_crypto` — The Night Shift (Saturday – Sunday)

Weekends are crypto-only territory. Forex is closed. Stocks are sleeping. But crypto never sleeps — and weekends can be *wild.* The catch? Liquidity is thinner, which means bigger spreads and more erratic moves. The weekend profile is deliberately **conservative.**

```yaml
weekend_crypto:
  symbols:
    - BTCUSD
    - ETHUSD
    - SOLUSD
    - XRPUSD
    - LINKUSD
    - LTCUSD
    - DOGEUSD
    - ZECUSD
    - BCHUSD
  strategies:
    crypto: supply_demand
  candle_timeframe: 15m
  market_poll_interval_seconds: 30  # No rush — weekend pace
  ai_decision_interval_seconds: 120
  htf_timeframe: 1h                # Longer timeframe — filter noise
  trend_window: 24                 # Longer lookback — more context
  stop_atr_multiplier: 2.0         # Wider stops — thinner liquidity
  risk_reward_ratio: 2.0
  max_concurrent_positions: 3       # Conservative position count
  cooldown_cycles_after_success: 2  # More patience between trades
  crypto_only: true
```

**Why Conservative?** Weekend crypto has 30–50% less liquidity than weekday crypto. Flash wicks are more common. Spreads are wider. The profile accounts for this with wider stops, slower polling, longer trend windows, and extra cooldown between trades. It's still hunting — just with more patience.

---

## Configuration

Enable Auto-Schedule in your settings:

> 📺 **In the UI:** Settings → **Hours & Sabbath** → toggle **Auto Schedule** ON

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

Each session maps to a profile you've already defined. The bot checks the clock, determines which session is active, and loads the corresponding profile — including its symbols, strategies, risk parameters, and scan intervals.

---

## The Handoff

When sessions change, the bot performs a clean handoff:

1. **Detects session transition** — "Asian session ending. London opening."
2. **Flattens session-specific positions** (if configured) — "Close out AUD/JPY before the London chaos."
3. **Loads the new profile** — London pairs, London strategies, London intervals.
4. **Logs the transition** — `[SCHEDULE] Session changed: asian → london → Profile: forex_continuous`
5. **Resumes scanning** — Now looking at EUR, GBP, USD instead of JPY crosses.

The transition is seamless. No restart needed. No human intervention. The bot just rotates its attention like a security camera panning across different zones.

---

## The All-In-One Profile

If this is too much configuration, there's a simpler option: the `all_247` profile.

```yaml
profiles:
  all_247:
    symbols:
      - EURUSD
      - GBPUSD
      - BTCUSD
      - ETHUSD
    strategy: meta_sci
    auto_schedule_enabled: false
```

This profile trades both forex and crypto, and the bot's built-in **market hours filter** automatically skips forex symbols when the forex market is closed. No profile switching needed. Meta-SCI handles the strategy selection per-symbol.

The trade-off: less optimization per session. The dedicated session profiles let you fine-tune strategies and risk for each market. The all-in-one profile is the "I don't want to think about it" option.

---

## Which One Should You Choose?

| Scenario | Recommendation |
|----------|---------------|
| I only trade forex | Fixed forex profile. No auto-schedule needed. |
| I only trade crypto | Fixed crypto profile. No auto-schedule needed. |
| I trade both but I'm lazy | `all_247` profile with Meta-SCI. |
| I trade both and I want to optimize | Auto-Schedule with dedicated session profiles. |
| I want maximum gains | Full auto-schedule: `asian_session` → `forex_continuous` → `overlap_session` → `new_york_session` → `crypto_247` → `weekend_crypto`. Every hour is covered. |
| I want to dominate one session | Use that session's profile as your primary. |

---

## The Meta Point

The Autopilot isn't just about convenience — it's about **opportunity cost.** Every hour the bot isn't scanning an active market is an hour of potential setups missed. Auto-Schedule ensures the bot is always scanning the right market at the right time.

The Asian session alone accounts for roughly **20% of daily forex volume.** The London–New York overlap accounts for **over 50%.** If you're only trading one session, you're leaving half the day's opportunity on the table. The bot doesn't need coffee. It just needs the right profile at the right time.

The market doesn't sleep. Your bot shouldn't either. It should just know where to look.
