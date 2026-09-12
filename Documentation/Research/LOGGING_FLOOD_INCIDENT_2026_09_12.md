# Runaway logging incident — root cause and fix (2026-09-12)

## 1. Why `is_market_open()` was called ~900 times a second

The call rate was never a scheduler cadence problem. The chain is:

| # | location | what happens |
|---|---|---|
| 1 | `runtime/loop.py:1792` | the Sabbath/replay path activates a replay provider and sets **`poll_interval = 0`, `decision_interval = 0`** ("Replay running at maximum CPU speed") |
| 2 | `runtime/loop.py:2298` | end-of-iteration sleep becomes `time.sleep(0.001 if replay_provider.in_warmup else poll_interval)` → **1 ms** |
| 3 | `runtime/loop.py:1498` | the whole loop body lives inside `for _ in loop_iter:` — an unbounded iterator under `--continuous` |
| 4 | `runtime/loop.py:1842` | each iteration runs the health heartbeat: `any(is_market_open(sym, …) for sym in symbols)` → **one call per symbol per iteration** |
| 5 | `runtime/scheduling.py:32` | with no registry entry, each of those calls logged `[SCHEDULE] No metadata for <sym>` |

A ~28 ms body with a 1 ms sleep gives ~9–36 iterations/second; × 26 symbols = **~900 `is_market_open` calls/second**, of which 16 symbols × the same rate were warnings.

**Evidence** (instrumented, `TRADE_SCI_SCHED_TRACE=1`):

```
[SCHEDULE][TRACE] is_market_open calls=4629 missing_metadata_calls=0 window=5s      → 926 calls/s
[LOOP][TRACE] iterations=55 in 6.0s => 9.2 Hz | poll_interval=0 decision_interval=0
              replay_active=True in_warmup=True sabbath=True symbols=26
```

and the caller stack, captured on the first call:

```
File "runtime/loop.py", line 1842, in run_bot
    any_market_open = any(is_market_open(sym, now, settings=profile_settings) for sym in symbols)
```

Measured live: **266,330 `No metadata` lines in 10 minutes** (~444/s visible; journald was rate-limiting, so the true rate was higher).

## 2. Why those pairs had no metadata, and whether they are tradeable

`SYMBOL_METADATA` had 94 entries covering every USD pair and the JPY majors, but **16 non-USD crosses were simply absent** from all three registries (`SYMBOL_MARKET_TYPE`, `FOREX_SYMBOLS`, `SUPPORTED_SYMBOLS`):

`AUDCAD AUDCHF AUDNZD CADCHF CADJPY CHFJPY EURAUD EURCAD EURCHF EURNZD GBPAUD GBPCHF GBPNZD NZDCAD NZDCHF NZDJPY`

They are ordinary, fully tradeable FX crosses on the configured provider: OANDA quotes all of them, the bot already stores their candle history, and `_is_forex_open()` handles FOREX hours correctly once an entry exists. This was a **registry gap, not an unsupported market**, so the fix is to register them (option 1), not to drop them from the profile.

**Semantic consequence, stated explicitly:** those 16 pairs previously returned `False` from `is_market_open()` (silently treated as closed) and so were never traded. Now they route to `_is_forex_open()` and **can trade**. That changes the *traded universe* — intended, since they are in the active profile — but if the operator prefers no change to what trades, the alternative is to remove those 16 from `forex_continuous`'s symbol list instead.

## 3. What changed

| file | change |
|---|---|
| `market/symbols.py` | registered the 16 crosses in `SYMBOL_MARKET_TYPE`, `FOREX_SYMBOLS`, `SUPPORTED_SYMBOLS` |
| `runtime/scheduling.py` | `is_market_open` warns **once per symbol**, DEBUG afterwards; new `warn_missing_metadata()` emits one summary; env-gated trace (`TRADE_SCI_SCHED_TRACE=1`) |
| `runtime/loop.py` | calls `warn_missing_metadata(symbols)` once at startup in `run_bot`; `[LOOP_DEBUG]` demoted to DEBUG |
| `runtime/cycle.py` | `[DECISION] … HOLD` throttled to one a minute per symbol (entries/exits still always INFO); `[CYCLE-DEBUG]` and candidate-list lines demoted to DEBUG |
| `strategy/engine.py` | `[TREND-DETECT]` vote dump demoted to DEBUG (was 512 lines/symbol/minute) |
| `broker/paper_broker.py` | `refresh_account_summary` balance/buying-power lines throttled to once a minute |
| `runtime/sabbath.py` | log throttle made time-based (was every 10th call) |
| `market/replay_provider.py` | fixed a real bug — 3 arguments for 2 placeholders in the `Time shift` line raised `TypeError` inside logging on **every** call; progress line now logs per 10 % of the day; per-symbol `Loaded` detail demoted |
| `strategy/safety_guard.py` | `New Day Detected` reset line bounded to once a minute per date |

No entry, exit, risk, sizing or strategy logic was changed. The only behavioural change is the intentionally-enabled 16 pairs (§2). The `New Day Detected` **reset itself** is untouched — only its logging is bounded (see §5).

## 4. Before / after, and how it was measured

```bash
journalctl --user -u tradebot-paper.service --since "1 min ago" | wc -l
journalctl --user -u tradebot-paper.service --since "10 min ago" | grep -c "No metadata"
```

| measure | before | after |
|---|---|---|
| lines/minute (unit) | 5,934 – 13,420 | **240** |
| `No metadata` / 10 min | 266,330 | **0** |
| `[PAPER] Liquidity/Buying Power` / 10 min | 14,005 + 14,004 | ~0 |
| `[TREND-DETECT]` | 512 per symbol/minute | 0 (DEBUG) |
| `New Day Detected` / 2 min | 1,699 | 4 |
| logging tracebacks (`Logging error`) | 28/min | **0** |
| reported incident rate | 18,000–20,000 lines/s, 29 GB syslog, 94 GB disk full | 240/min ≈ **0.004 %** of that |

The bot remained `active` and continued evaluating all 26 symbols throughout.

## 5. Residual risk

1. **The loop still spins (~9 Hz) during Sabbath replay.** `poll_interval = 0` is deliberate ("maximum CPU speed" fast-forward), so it was left alone. Consequence: any *future* static condition logged per call will flood again. The log-once guard in `is_market_open` and the throttles protect the known sites, but the underlying amplifier is intact.
2. **The daily safety reset thrashes.** `_update_daily_stats` compares a date derived from `now`, which alternates between replay time and wall clock (the log showed replay `2026-03-02` vs today `2026-09-12`, 194 days apart), so the "new day" branch re-fires continuously and daily PnL/HWM is reset ~8×/second **in replay**. Only the logging was bounded; the reset behaviour was left untouched because changing it alters risk semantics. Worth a decision: daily limits effectively never accrue during Sabbath replay.
3. **`[CRITICAL] [PAPER] PRICE FALLBACK for USD_CAD: using hardcoded 100.0`** (4 in 3 min, pre-existing). Note the underscore symbol format leaking in, and a hardcoded 100.0 price for a CAD pair — a data-correctness issue, not a logging one.
4. **Guardrails kept.** `/etc/rsyslog.d/10-drop-tradebot-noise.conf`, the journald size/rate limits and logrotate remain in place as defence in depth. With the flood fixed the rsyslog drop rule is no longer *necessary* for this unit, but it is cheap insurance against exactly this class of failure and should stay.

Patch: `Documentation/patches/logging-flood-2026-09-12.patch`
