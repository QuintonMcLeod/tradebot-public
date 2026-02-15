
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

| Time (EST) | Session | Active Profile |
|-----------|---------|---------------|
| 00:00–03:00 | Asian Session | `crypto_247` |
| 03:00–08:00 | London Session | `forex_london` |
| 08:00–12:00 | NY + London Overlap | `forex_overlap` |
| 12:00–17:00 | New York Session | `forex_ny` |
| 17:00–00:00 | After Hours | `crypto_247` |
| Saturday–Sunday | Weekend | `crypto_247` |

Notice the pattern: **When the forex market is sleeping, the bot switches to crypto.** When the forex market wakes up, the bot switches back. Maximum coverage, minimum wasted scans.

---

## Configuration

Enable Auto-Schedule in your settings:

```yaml
auto_schedule_enabled: true
auto_schedule_profiles:
  london: "forex_london"
  new_york: "forex_ny"
  overlap: "forex_overlap"
  asian: "crypto_247"
  weekend: "crypto_247"
  default: "all_247"
```

Each session maps to a profile you've already defined. The bot checks the clock, determines which session is active, and loads the corresponding profile — including its symbols, strategies, risk parameters, and scan intervals.

---

## The Handoff

When sessions change, the bot performs a clean handoff:

1. **Detects session transition** — "NY session just ended. After-hours starting."
2. **Flattens forex positions** (if configured) — "No more forex until London opens."
3. **Loads the new profile** — Crypto symbols, crypto strategies, crypto intervals.
4. **Logs the transition** — `[SCHEDULE] Session changed: ny → after_hours → Profile: crypto_247`
5. **Resumes scanning** — Now looking at BTC, ETH, SOL instead of EUR, GBP, JPY.

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
| I want maximum gains | Auto-Schedule with full session profiles + weekend crypto. Every hour is covered. |

---

## The Meta Point

The Autopilot isn't just about convenience — it's about **opportunity cost.** Every hour the bot isn't scanning an active market is an hour of potential setups missed. Auto-Schedule ensures the bot is always scanning the right market at the right time.

The market doesn't sleep. Your bot shouldn't either. It should just know where to look.
