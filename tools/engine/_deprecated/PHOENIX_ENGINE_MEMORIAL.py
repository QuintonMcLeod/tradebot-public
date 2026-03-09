"""
⚠️ DEPRECATED: Phoenix Engine (engine_replay.py) — March 6, 2026

The Phoenix Engine was the original engine_replay.py — a 1,423-line monolith
that reimplemented the backtester's simulation logic inside a per-symbol
multiprocess worker. It handled:
  - Per-symbol isolation via ProcessPoolExecutor
  - Custom OHLC observation synthesis from candle_history/
  - Reimplemented SL/TP checking
  - Reimplemented Guillotine scale-outs
  - Reimplemented SAR entries
  - Manual position tracking

It was REPLACED by the Minovsky Engine because:
  1. It reimplemented ~900 lines of simulation logic that the Backtester
     already had, tested, and debugged.
  2. It produced 499 trades vs the backtester's 2,278 (no multi-position).
  3. It had PF 0.73 vs the backtester's 2.10 (broken exit logic).
  4. It lost $5,370 in 14 days where the backtester made $3,974.

The Minovsky Engine simply wraps Backtester.run_backtest() and produces
IDENTICAL results to the backtester. 240 lines vs 1,423 lines.

The old Phoenix code was not preserved in git. This notice exists as a
memorial. Rest in peace, you glorious, broken mess.

— The Management
"""
