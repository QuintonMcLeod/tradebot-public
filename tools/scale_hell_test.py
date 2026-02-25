#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║             CONDUCTOR SCALE + HELL TEST                                     ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Part 1: SCALE TEST — Real deployment capital scenario                      ║
║    Days 1-6:  $3,290.36 (partial deposit available)                         ║
║    Days 7+:   $7,500.00 (full deposit cleared)                              ║
║                                                                              ║
║  Part 2: MONTE CARLO HELL TEST                                              ║
║    1000x random shuffle of trade outcomes to find:                           ║
║    - Worst-case drawdown                                                     ║
║    - Worst-case losing streak                                                ║
║    - Probability of ruin (account < 50%)                                     ║
║    - Expected range of outcomes (5th/95th percentile)                        ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
import sys, os, logging, time, random
from datetime import datetime, timezone, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest.mock
sys.modules["ib_insync"] = unittest.mock.MagicMock()
os.environ["TRADING_CONFIRMATION"] = "YES"
os.environ["SCALE_OUT_FRACTION"] = "0.95"

logging.basicConfig(level=logging.WARNING)

from tools.utils.local_provider import LocalJSONProvider
from tradebot_sci.simulation.backtester import Backtester
from tradebot_sci.config.models import (
    Settings, AppSettings, LoggingSettings, AISettings, MarketSettings,
    TradingProfileSettings,
)


def build_config():
    profile = TradingProfileSettings(
        strategy_variant="forex_conductor",
        candle_timeframe="15m",
        htf_timeframe="1h",
        ltf_timeframe="5m",
        trend_window=12,
        ltf_trend_window=8,
        min_hold_hours=0.08,   # 5 minutes — cut losers fast
        max_hold_hours=0,
        risk_per_trade_pct=0.01,
        block_counter_trend_entries=True,
        trend_strength_floor=0.20,
        trend_adx_enabled=True,
        trend_ema_ribbon_enabled=True,
        trend_supertrend_enabled=True,
        trend_macd_enabled=True,
        # ── Stop-and-Reverse (The Uno Reverse Card) ──
        stop_and_reverse_enabled=True,
        reversal_risk_per_trade=0.045,
        reversal_tp_r=1.0,
        reversal_cost_aware_tp=True,
        # ── Pyramiding ──
        enable_pyramiding=True,
        max_pyramid_count=50,
    )
    settings = Settings(
        app=AppSettings(profile_name="A"),
        logging=LoggingSettings(),
        ai=AISettings(provider="openai"),
        market=MarketSettings(symbols=["EURUSD", "GBPUSD"]),
        profiles={"A": profile},
    )
    return settings


def run_backtest(initial_capital, days, end_offset_days=0):
    """Run a backtest with specified capital."""
    settings = build_config()
    bt = Backtester(ib=None, settings=settings, ai_client=None)
    bt.market_provider = LocalJSONProvider("data/audit")
    bt._is_market_hours_utc = lambda ts: True

    now = datetime.now(tz=timezone.utc).replace(minute=0, second=0, microsecond=0)
    end = now - timedelta(days=end_offset_days)
    start = end - timedelta(days=days)
    return bt.run_backtest(
        initial_capital=initial_capital,
        start_date=start, end_date=end,
        wind_down_days=0
    ), start, end


# ═══════════════════════════════════════════════════════════════════════
#  PART 1: SCALE TEST
# ═══════════════════════════════════════════════════════════════════════
def run_scale_test():
    print("\n" + "═" * 70)
    print("  PART 1: SCALE TEST — Real Deployment Scenario")
    print("  Days 1-6: $3,290.36 available | Days 7+: $7,500.00 available")
    print("═" * 70)

    # Phase 1: First 6 days with partial capital ($3,290.36)
    print("\n  ── Phase 1: Days 1-6 ($3,290.36 capital) ──────────────────")
    t0 = time.time()
    try:
        # Most recent 6 days
        r1, s1, e1 = run_backtest(
            initial_capital=3290.36, days=6, end_offset_days=0
        )
        elapsed = time.time() - t0

        print_results(r1, s1, e1, f"Phase 1: $3,290.36 ({elapsed:.1f}s)")
        phase1_trade_sum = sum(t.pnl for t in r1.trades)
        phase1_end_capital = 3290.36 + phase1_trade_sum
    except Exception as e:
        print(f"    [ERROR] {e}")
        phase1_end_capital = 3290.36
        phase1_trade_sum = 0

    # Phase 2: Remaining period with full capital ($7,500)
    # Simulate the deposit clearing: starting capital = phase1 result + additional deposit
    full_capital = phase1_end_capital + (7500.00 - 3290.36)
    print(f"\n  ── Phase 2: Days 7+ ($7,500, available capital: ${full_capital:.2f}) ──")
    t0 = time.time()
    try:
        r2, s2, e2 = run_backtest(
            initial_capital=full_capital, days=14, end_offset_days=6
        )
        elapsed = time.time() - t0
        print_results(r2, s2, e2, f"Phase 2: ${full_capital:.2f} ({elapsed:.1f}s)")
        phase2_trade_sum = sum(t.pnl for t in r2.trades)
        phase2_end_capital = full_capital + phase2_trade_sum
    except Exception as e:
        print(f"    [ERROR] {e}")
        phase2_end_capital = full_capital
        phase2_trade_sum = 0

    # Combined summary — use trade sums, not capital-delta
    all_trades = []
    try:
        all_trades = r1.trades + r2.trades
    except:
        pass
    total_trade_sum = sum(t.pnl for t in all_trades)
    total_return = total_trade_sum / 7500.00 * 100

    print(f"\n  {'─' * 60}")
    print(f"  SCALE TEST SUMMARY (Trade Sum)")
    print(f"  {'─' * 60}")
    print(f"  Initial Deposit:     $7,500.00")
    print(f"  Phase 1 Trade Sum:   ${phase1_trade_sum:+,.2f}")
    print(f"  Phase 2 Trade Sum:   ${phase2_trade_sum:+,.2f}")
    print(f"  Total Trade Sum:     ${total_trade_sum:+,.2f}")
    print(f"  Final Balance:       ${7500 + total_trade_sum:,.2f}")
    print(f"  Return on Deposit:   {total_return:+.2f}%")
    print(f"  Total Trades:        {len(all_trades)}")

    return all_trades


def print_results(result, start, end, label):
    trades = result.trades
    n = len(trades)
    if n == 0:
        print(f"    {label}: NO TRADES")
        return

    wins = sum(1 for t in trades if t.pnl > 0)
    wr = wins / n * 100
    winners = [t for t in trades if t.pnl > 0]
    losers = [t for t in trades if t.pnl <= 0]
    avg_w = sum(t.pnl for t in winners) / len(winners) if winners else 0
    avg_l = sum(t.pnl for t in losers) / len(losers) if losers else 0
    rr = abs(avg_w / avg_l) if avg_l != 0 else 999

    trade_sum = sum(t.pnl for t in trades)
    print(f"    {n} trades | {wr:.0f}% WR | R:R {rr:.1f}:1 | Trade Sum ${trade_sum:+.2f} | Max DD {result.max_drawdown_pct:.1f}%")
    print(f"    Avg Win: ${avg_w:.2f} | Avg Loss: ${avg_l:.2f}")
    print(f"    Window: {start.strftime('%b %d')} – {end.strftime('%b %d')}")

    # Individual trades
    for i, t in enumerate(trades, 1):
        hold_h = (t.exit_time - t.entry_time).total_seconds() / 3600
        mark = "✅" if t.pnl > 0 else "❌"
        reason = str(t.exit_reason)[:40]
        entry_t = t.entry_time.strftime("%m/%d %H:%M")
        print(f"     {i:>2} {mark} {t.symbol:>8} {t.direction:>5} ${t.pnl:>8.2f} {hold_h:>5.1f}h {entry_t} {reason}")


# ═══════════════════════════════════════════════════════════════════════
#  PART 2: MONTE CARLO HELL TEST
# ═══════════════════════════════════════════════════════════════════════
def run_monte_carlo(trades, n_simulations=1000):
    print("\n\n" + "═" * 70)
    print("  PART 2: MONTE CARLO HELL TEST — 1000 Random Simulations")
    print("  Shuffling trade order to find worst-case scenarios")
    print("═" * 70)

    if not trades:
        print("    No trades to simulate!")
        return

    # Extract PnL values from trades
    trade_pnls = [t.pnl for t in trades]
    n_trades = len(trade_pnls)

    print(f"\n  Input: {n_trades} trades, Total PnL: ${sum(trade_pnls):+.2f}")
    print(f"  Winners: {sum(1 for p in trade_pnls if p > 0)} | Losers: {sum(1 for p in trade_pnls if p <= 0)}")
    print(f"\n  Running {n_simulations} random permutations...")

    initial_capital = 7500.00  # Full deposit scenario
    results = []
    worst_drawdowns = []
    worst_streaks = []
    ruin_count = 0  # Account drops below 50% of initial
    max_ever_dd = 0
    max_ever_streak = 0
    worst_equity_curve = None
    worst_equity_min = initial_capital

    random.seed(42)  # Reproducible chaos

    for sim in range(n_simulations):
        shuffled = trade_pnls.copy()
        random.shuffle(shuffled)

        # Simulate equity curve
        equity = initial_capital
        peak = equity
        max_dd_pct = 0
        min_equity = equity
        equity_curve = [equity]

        # Track loss streaks
        current_streak = 0
        max_streak = 0

        for pnl in shuffled:
            equity += pnl
            equity_curve.append(equity)

            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak * 100 if peak > 0 else 0
            if dd > max_dd_pct:
                max_dd_pct = dd
            if equity < min_equity:
                min_equity = equity

            if pnl <= 0:
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 0

        final_equity = equity
        total_pnl = final_equity - initial_capital
        results.append(total_pnl)
        worst_drawdowns.append(max_dd_pct)
        worst_streaks.append(max_streak)

        if min_equity < initial_capital * 0.50:
            ruin_count += 1

        if max_dd_pct > max_ever_dd:
            max_ever_dd = max_dd_pct
            worst_equity_curve = equity_curve
            worst_equity_min = min_equity

    # ── Sort results for percentile analysis
    results.sort()
    worst_drawdowns.sort()
    worst_streaks.sort()

    def percentile(data, pct):
        idx = int(len(data) * pct / 100)
        return data[min(idx, len(data) - 1)]

    # ── Results
    print(f"\n  {'─' * 60}")
    print(f"  MONTE CARLO RESULTS ({n_simulations} simulations)")
    print(f"  {'─' * 60}")
    print(f"  Starting Capital:            ${initial_capital:,.2f}")
    print(f"")
    print(f"  ── PnL Distribution ──")
    print(f"  Worst Case (0th):            ${results[0]:+,.2f}")
    print(f"  5th Percentile:              ${percentile(results, 5):+,.2f}")
    print(f"  25th Percentile:             ${percentile(results, 25):+,.2f}")
    print(f"  Median (50th):               ${percentile(results, 50):+,.2f}")
    print(f"  75th Percentile:             ${percentile(results, 75):+,.2f}")
    print(f"  95th Percentile:             ${percentile(results, 95):+,.2f}")
    print(f"  Best Case (100th):           ${results[-1]:+,.2f}")
    print(f"")
    print(f"  ── Drawdown Analysis ──")
    print(f"  Worst-Ever Max DD:           {max_ever_dd:.1f}%")
    print(f"  Median Max DD:               {percentile(worst_drawdowns, 50):.1f}%")
    print(f"  95th Percentile DD:          {percentile(worst_drawdowns, 95):.1f}%")
    print(f"  Worst Equity Low:            ${worst_equity_min:,.2f}")
    print(f"")
    print(f"  ── Streak Analysis ──")
    print(f"  Worst-Ever Loss Streak:      {max(worst_streaks)}")
    print(f"  Median Max Streak:           {percentile(worst_streaks, 50)}")
    print(f"  95th Percentile Streak:      {percentile(worst_streaks, 95)}")
    print(f"")
    print(f"  ── Risk of Ruin ──")
    print(f"  P(account < 50%):            {ruin_count}/{n_simulations} ({ruin_count/n_simulations*100:.1f}%)")
    print(f"  P(profitable):               {sum(1 for r in results if r > 0)}/{n_simulations} ({sum(1 for r in results if r > 0)/n_simulations*100:.1f}%)")
    print(f"  P(loss > $500):              {sum(1 for r in results if r < -500)}/{n_simulations} ({sum(1 for r in results if r < -500)/n_simulations*100:.1f}%)")

    # ── Worst-case equity curve visualization (ASCII art)
    if worst_equity_curve:
        print(f"\n  ── Worst-Case Equity Curve ──")
        n_points = len(worst_equity_curve)
        # Compress to ~50 columns
        step = max(1, n_points // 50)
        compressed = [worst_equity_curve[i] for i in range(0, n_points, step)]
        lo = min(compressed)
        hi = max(compressed)
        height = 10
        rng = hi - lo if hi > lo else 1

        for row in range(height, -1, -1):
            threshold = lo + (rng * row / height)
            line = "  "
            if row == height:
                line += f"${hi:>8,.0f} │"
            elif row == 0:
                line += f"${lo:>8,.0f} │"
            else:
                line += f"{'':>9} │"
            for val in compressed:
                level = int((val - lo) / rng * height)
                if level >= row:
                    line += "█"
                else:
                    line += " "
            print(line)
        print(f"  {'':>9} └{'─' * len(compressed)}")
        print(f"  {'':>10} Trade 1{'':>{len(compressed)-12}}Trade {n_trades}")


# ═══════════════════════════════════════════════════════════════════════
#  PART 3: EXTENDED HELL — Run on different market conditions
# ═══════════════════════════════════════════════════════════════════════
def run_extended_hell():
    print("\n\n" + "═" * 70)
    print("  PART 3: EXTENDED HELL — All Available Data Periods")
    print("═" * 70)

    # Run across ALL available data, sliding weekly
    windows = []
    for offset in range(0, 28, 3):  # Every 3 days
        try:
            t0 = time.time()
            r, s, e = run_backtest(initial_capital=7500, days=7, end_offset_days=offset)
            elapsed = time.time() - t0
            trades = r.trades
            n = len(trades)
            if n == 0:
                windows.append({
                    "offset": offset, "pnl": 0, "trades": 0, "wr": 0,
                    "dd": 0, "elapsed": elapsed
                })
                continue
            wins = sum(1 for t in trades if t.pnl > 0)
            wr = wins / n * 100
            trade_sum = sum(t.pnl for t in trades)
            windows.append({
                "offset": offset,
                "pnl": trade_sum,  # Use trade sum, not window capital-delta
                "window_pnl": r.total_pnl,  # Keep for reference
                "trades": n,
                "wr": wr,
                "dd": r.max_drawdown_pct,
                "elapsed": elapsed,
                "trade_list": trades,
            })
        except Exception as e:
            print(f"    [ERROR] Offset {offset}d: {e}")

    # Print results
    print(f"\n  {'Offset':<8} {'Trade Sum':>10} {'Trades':>7} {'WR':>6} {'MaxDD':>7} {'Result':>8}")
    print(f"  {'─'*8} {'─'*10} {'─'*7} {'─'*6} {'─'*7} {'─'*8}")
    profitable = 0
    for w in windows:
        mark = "✅" if w["pnl"] > 0 else ("⬜" if w["trades"] == 0 else "❌")
        if w["pnl"] > 0:
            profitable += 1
        print(
            f"  {w['offset']:>3}d ago  ${w['pnl']:>+9.2f} {w['trades']:>7} "
            f"{w['wr']:>5.0f}% {w['dd']:>6.1f}% {mark}"
        )

    total = len([w for w in windows if w["trades"] > 0])
    print(f"\n  Profitability: {profitable}/{total} windows ({profitable/total*100:.0f}% hit rate)" if total else "")

    # Per-trade detail for LOSING windows
    losers = [w for w in windows if w["pnl"] < 0 and w.get("trade_list")]
    if losers:
        print(f"\n{'='*70}")
        print(f"  LOSING WINDOW DETAIL")
        print(f"{'='*70}")
        for w in losers:
            print(f"\n  ── {w['offset']}d ago: ${w['pnl']:+.2f} ({w['trades']} trades, {w['wr']:.0f}% WR) ──")
            print(f"    {'#':>3} {'Date':<12} {'Symbol':<8} {'Dir':<6} {'PnL':>10} {'Entry':>10} {'Exit':>10} {'Reason':<20}")
            print(f"    {'─'*3} {'─'*12} {'─'*8} {'─'*6} {'─'*10} {'─'*10} {'─'*10} {'─'*20}")
            sorted_t = sorted(w["trade_list"], key=lambda t: t.entry_time)
            running = 0
            for i, t in enumerate(sorted_t, 1):
                running += t.pnl
                icon = "🟢" if t.pnl > 0 else "🔴"
                date_str = t.entry_time.strftime("%b %d %H:%M") if t.entry_time else "?"
                reason = str(t.exit_reason)[:20]
                print(
                    f"    {i:>3} {date_str:<12} {t.symbol:<8} {t.direction:<6} "
                    f"${t.pnl:>+9.2f} ${t.entry_price:>9.5f} ${t.exit_price:>9.5f} "
                    f"{reason:<20} {icon} (cum: ${running:>+.2f})"
                )


def main():
    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║       CONDUCTOR SCALE + HELL TEST — Through Fire & Chaos           ║")
    print("╚══════════════════════════════════════════════════════════════════════╝")

    # Part 1: Scale test
    all_trades = run_scale_test()

    # Also gather trades from a broader window for Monte Carlo
    try:
        r_full, _, _ = run_backtest(initial_capital=7500, days=21, end_offset_days=0)
        mc_trades = r_full.trades
        print(f"\n  [INFO] Gathered {len(mc_trades)} trades from 21-day window for Monte Carlo")
    except Exception:
        mc_trades = all_trades

    # Part 2: Monte Carlo Hell
    run_monte_carlo(mc_trades, n_simulations=1000)

    # Part 3: Extended Hell (sliding windows)
    run_extended_hell()

    print("\n" + "═" * 70)
    print("  TEST COMPLETE — If the Conductor survived this, it's ready.")
    print("═" * 70)


if __name__ == "__main__":
    main()
