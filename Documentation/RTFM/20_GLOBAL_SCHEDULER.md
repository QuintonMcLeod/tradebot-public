---
title: 'The Global Scheduler: Precision Timing & Off-Hours'
category: rtfm
icon: schedule
description: "\"The bot doesn't have a 9-to-5. It has a 24/7 and a strong opinion\
  \ about when to show up.\" How Auto-Schedule automatically switches trading profiles\
  \ based on active market sessions \u2014 London forex at 3 AM, NY overlap at 8 AM,\
  \ crypto during off-hours and weekends. Maximum coverage, zero wasted scans."
---

# 20. The Global Scheduler: Precision Timing & Off-Hours

<table><tr><td width="170"><img src="img/bot.png" width="150"></td><td><b>THE BOT</b>:<br><em>"I am a machine of infinite patience, but even I need to know when the casino is open."</em></td></tr></table>

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"Listen to me. Markets are not open 24/7. London is up at 3 AM. Tokyo is up at 7 PM. Crypto never sleeps, and equities take the weekend off to play golf.<br><br>The Global Scheduler lets you tell the bot exactly when to work and when to sit in the corner and think about what it's done. Stop trading low-liquidity garbage at 2 AM!"</td></tr></table>

---

## The Problem With Fixed Boundaries

<table><tr><td width="170"><img src="img/professor.png" width="150"></td><td><b>PROFESSOR</b>:<br>"If your bot is scanning an empty parking lot at 2 AM for SPY breakouts, you are wasting computational power and risking bad executions on low-liquidity wicks. We schedule our lives; we must schedule our bots."</td></tr></table>

---

## The Global Scheduler UI

The **Hours & Sabbath** tab in the Settings panel now houses the Global Scheduler. This interface allows you to create highly customized operating windows for any profile.

You can configure:
1. **Target Profile**: Which profile this schedule applies to (e.g., `forex_continuous`).
2. **Mode**: `24/7` (always on), `business_hours` (M-F 9 to 5), or `custom`.
3. **Active Days**: Specific days of the week.
4. **Active Weeks**: First, second, third, fourth, or last week of the month.
5. **Time Window**: Start time and End time (in HH:MM format).

### The "Off-Hours Paper Trading" Option

One of the most powerful features of the Global Scheduler is the **Off-Hours Paper Trading** toggle.

When enabled, instead of the bot going to sleep when a schedule session ends, it automatically transitions your profile into **Paper Trading Mode**. 
- It continues to scan the market.
- It executes simulated paper trades based on its strategy logic.
- When the active schedule resumes, it smoothly transitions back to live execution (if live execution is enabled globally).

<table><tr><td width="170"><img src="img/chad.png" width="150"></td><td><b>CHAD</b>:<br>"This is the holy grail for forward testing. Let's say I only want my bot risking real capital during the London/NY overlap. I set the schedule. The rest of the day, it paper trades, gathering data and proving whether the strategy holds up during slower sessions. Free data, zero risk."</td></tr></table>

---

## Configuration

> 📺 Settings → **Hours & Sabbath** → **Global Scheduler**

You can add multiple schedule blocks for different profiles. The bot evaluates these in real-time.

```json
  "schedule": {
    "sessions": [
      {
        "id": "forex-biz",
        "profile_name": "forex_continuous",
        "mode": "business_hours",
        "days_of_week": [0, 1, 2, 3, 4],
        "weeks_of_month": ["all"],
        "start_time": "08:00",
        "end_time": "17:00",
        "paper_trade_off_hours": true
      }
    ]
  }
```

---

## The Handoff Logic

1. **Active Window Identified** ➔ If the current time matches a session block for the active profile, the bot engages normal operation (live or paper depending on your global `EXECUTE_TRADES` switch).
2. **Window Expires** ➔ The bot evaluates the `paper_trade_off_hours` flag.
   - **True**: The bot switches over to the paper execution engine seamlessly. It will tag these trades as paper.
   - **False**: The bot enters SLEEP mode. It halts new entries, cancels pending opening orders, but *maintains management of existing open positions* until they hit their stops or take profits.

---

## Unified Strategy Scheduling (Auto-Sync)

The Tradebot now supports a centralized, metadata-driven architecture for strategy execution. Strategies are no longer responsible for their own time-based filtering; instead, they declare their required operating windows via a `SESSION_PROFILE`.

### How it Works:
1. **Metadata Declaration**: Each strategy variant (e.g., `London Breakout`, `ORB Strategy`) defines a `SESSION_PROFILE` constant (e.g., `"london_open"`, `"us_open"`).
2. **Auto-Link & Enable**: Upon startup, the **Global Scheduler** automatically scans all active strategies. If a strategy requires a specific session, that session is automatically added to the schedule and marked as `active: true`.
3. **Engine-Level Gating**: The `StrategyEngine` manages the gates. If the current time is outside the required session window, the engine automatically blocks entry signals for that strategy while allowing exits and management to continue.

### Key Benefits:
- **Zero Configuration**: Users no longer need to manually set up schedule sessions for standard strategies. Enabling a strategy automatically enables its required time window.
- **Unified Logic**: All time-based logic is centralized in `runtime/scheduling.py`, ensuring consistency across 37+ strategy variants.
- **Safety**: Strategies are "dumb" about time; the engine is the "boss" that enforces the rules.

---

## Goodbye, Auto-Schedule

The legacy "Auto-Schedule" and "Session Gate" features have been formally deprecated in favor of the Global Scheduler. The new engine provides significantly more granular control without the fragile profile-switching logic of the past.

If you previously relied on auto-schedule to swap between `asian_session` and `london_session` profiles, the recommended approach is now to run a single hybrid profile and use the AI Optimization feature, or use the Global Scheduler to define exact trading windows.

<table><tr><td width="170"><img src="img/creator.png" width="150"></td><td><b>CREATOR</b>:<br>"The old system was a caveman's club. The Global Scheduler is a surgical scalpel. Try not to cut your own finger off with it."</td></tr></table>


