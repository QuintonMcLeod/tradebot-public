#!/usr/bin/env python3
"""Multi-pair forex backtest audit.

Backtests ALL downloaded forex pairs individually, ranks them,
then runs a Monte Carlo forward projection with the winners.
"""
import sys, os, json, logging, random
from datetime import datetime, timezone, timedelta
from pathlib import Path

logging.basicConfig(level=logging.WARNING)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))
os.chdir(PROJECT_ROOT)

from tools.utils.local_provider import LocalJSONProvider
from tradebot_sci.simulation.backtester import Backtester
from tradebot_sci.config.models import *

import numpy as np
np.random.seed(42)
random.seed(42)

DATA_DIR = PROJECT_ROOT / "data" / "audit"

# Find all available forex pairs from downloaded data
available_pairs = set()
for f in DATA_DIR.glob("*_5m.json"):
    sym = f.stem.replace("_5m", "")
    # Only forex (6-char pairs, no crypto)
    if len(sym) == 6 and not any(c in sym for c in ["BTC", "ETH", "SOL", "XRP"]):
        # Verify we have all required timeframes
        has_all = all((DATA_DIR / f"{sym}_{tf}.json").exists() for tf in ["5m", "15m", "1h", "4h"])
        if has_all:
            available_pairs.add(sym)

available_pairs = sorted(available_pairs)
print(f"═══ MULTI-PAIR FOREX AUDIT ═══")
print(f"Pairs found: {len(available_pairs)}")
print(f"Strategy: forex_conductor")
print(f"Capital: $3,291.06")
print()

# ── Phase 1: Individual pair backtests ──
results = []
end_dt = datetime.now(tz=timezone.utc).replace(minute=0, second=0, microsecond=0)
start_dt = end_dt - timedelta(days=14)

for sym in available_pairs:
    try:
        p = TradingProfileSettings(
            strategy_variant='forex_conductor',
            candle_timeframe='5m',  # LTF for conductor
            htf_timeframe='4h',
            ltf_timeframe='5m',
            trend_window=12,
            ltf_trend_window=8,
            min_hold_hours=1.0,
            max_hold_hours=0,
            risk_per_trade_pct=0.045,
            block_counter_trend_entries=True,
            trend_strength_floor=0.20,
            trend_adx_enabled=True,
            trend_ema_ribbon_enabled=True,
            trend_supertrend_enabled=True,
            trend_macd_enabled=True,
        )
        s = Settings(
            app=AppSettings(profile_name='audit'),
            logging=LoggingSettings(),
            ai=AISettings(provider='openai'),
            market=MarketSettings(symbols=[sym]),
            profiles={'audit': p},
        )
        bt = Backtester(ib=None, settings=s, ai_client=None)
        bt.market_provider = LocalJSONProvider('data/audit')
        bt._is_market_hours_utc = lambda ts: True

        r = bt.run_backtest(
            initial_capital=3291.06,
            start_date=start_dt,
            end_date=end_dt,
            wind_down_days=0
        )

        if not r.trades:
            results.append({
                'symbol': sym, 'trades': 0, 'wins': 0, 'losses': 0,
                'win_rate': 0, 'total_pnl': 0, 'avg_pnl': 0,
                'max_win': 0, 'max_loss': 0, 'profit_factor': 0,
                'avg_win': 0, 'avg_loss': 0, 'rr_ratio': 0,
                'trade_returns': [], 'grade': 'F'
            })
            continue

        wins = [t for t in r.trades if t.pnl > 0]
        losses = [t for t in r.trades if t.pnl <= 0]
        total_pnl = sum(t.pnl for t in r.trades)
        avg_pnl = total_pnl / len(r.trades)
        win_rate = len(wins) / len(r.trades) * 100
        gross_win = sum(t.pnl for t in wins) if wins else 0
        gross_loss = abs(sum(t.pnl for t in losses)) if losses else 0.01
        profit_factor = gross_win / gross_loss if gross_loss > 0 else 0
        avg_win = (gross_win / len(wins)) if wins else 0
        avg_loss = (gross_loss / len(losses)) if losses else 0.01
        rr_ratio = avg_win / avg_loss if avg_loss > 0 else 0
        max_win = max(t.pnl for t in r.trades)
        max_loss = min(t.pnl for t in r.trades)
        trade_returns = [t.pnl / 3291.06 for t in r.trades]

        # Grade: A=strong profit, B=moderate, C=breakeven, D=slight loss, F=bad
        if total_pnl > 50 and win_rate > 40 and profit_factor > 1.5:
            grade = 'A'
        elif total_pnl > 20 and profit_factor > 1.2:
            grade = 'B'
        elif total_pnl > 0:
            grade = 'C'
        elif total_pnl > -20:
            grade = 'D'
        else:
            grade = 'F'

        results.append({
            'symbol': sym,
            'trades': len(r.trades),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'avg_pnl': avg_pnl,
            'max_win': max_win,
            'max_loss': max_loss,
            'profit_factor': profit_factor,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'rr_ratio': rr_ratio,
            'grade': grade,
            'trade_returns': trade_returns,
        })
    except Exception as e:
        print(f"  ❌ {sym}: {e}")
        results.append({
            'symbol': sym, 'trades': 0, 'wins': 0, 'losses': 0,
            'win_rate': 0, 'total_pnl': 0, 'avg_pnl': 0,
            'max_win': 0, 'max_loss': 0, 'profit_factor': 0,
            'avg_win': 0, 'avg_loss': 0, 'rr_ratio': 0,
            'trade_returns': [], 'grade': 'F'
        })

# Sort by total PnL
results.sort(key=lambda x: x['total_pnl'], reverse=True)

print("═══ 14-DAY BACKTEST RESULTS (sorted by PnL) ═══")
print(f"{'Pair':<10} {'Grade':>5} {'Trades':>6} {'W':>3} {'L':>3} {'WR%':>5} {'PnL':>10} {'AvgPnL':>8} {'PF':>5} {'R:R':>5} {'MaxWin':>8} {'MaxLoss':>8}")
print("─" * 95)

profitable = []
unprofitable = []

for r in results:
    grade_icon = {'A': '🟢', 'B': '🔵', 'C': '🟡', 'D': '🟠', 'F': '🔴'}[r['grade']]
    pnl_str = f"${r['total_pnl']:>+8.2f}"
    print(f"{r['symbol']:<10} {grade_icon} {r['grade']:>3} {r['trades']:>6} {r['wins']:>3} {r['losses']:>3} {r['win_rate']:>4.0f}% {pnl_str} {r['avg_pnl']:>+7.2f} {r['profit_factor']:>5.1f} {r['rr_ratio']:>5.1f} {r['max_win']:>+7.2f} {r['max_loss']:>+7.2f}")
    if r['total_pnl'] > 0 and r['trades'] >= 3:
        profitable.append(r)
    else:
        unprofitable.append(r)

print()
print(f"Profitable pairs (PnL > 0, ≥3 trades): {len(profitable)}")
print(f"Unprofitable/inactive pairs: {len(unprofitable)}")

# ── Phase 2: Monte Carlo Forward Projection ──
if not profitable:
    print("\nNo profitable pairs found!")
    sys.exit(0)

# Build combined trade pool from profitable pairs
current_pair_returns = []  # EURUSD + GBPUSD only
expanded_pair_returns = []  # All profitable pairs

for r in results:
    if r['symbol'] in ('EURUSD', 'GBPUSD') and r['trade_returns']:
        current_pair_returns.extend(r['trade_returns'])
    if r['total_pnl'] > 0 and r['trades'] >= 3 and r['trade_returns']:
        expanded_pair_returns.extend(r['trade_returns'])

# Trades per day estimation
current_trades_per_day = len(current_pair_returns) / 14.0
expanded_trades_per_day = len(expanded_pair_returns) / 14.0

# Scale expanded trades: more pairs = proportionally more trades
# but cap at reasonable level (not linearly since market hours overlap)
expanded_pairs_count = len(profitable)
current_pairs_count = 2
trade_multiplier = min(expanded_pairs_count / current_pairs_count, 3.0)  # cap at 3x
adjusted_expanded_tpd = current_trades_per_day * trade_multiplier

SIMS = 10000
RENT = 2360

def run_monte_carlo(trade_pool, trades_per_day, label):
    results_m1 = []
    results_m3 = []
    results_m6 = []
    max_drawdowns = []
    worst_streaks = []

    for sim in range(SIMS):
        cap = 3291.06
        hwm = cap
        max_dd = 0
        worst_streak = 0
        cur_streak = 0

        for day in range(180):
            if day == 6:
                cap += (7200 - 3291.06)
                hwm = max(hwm, cap)

            n_trades = max(0, int(np.random.poisson(trades_per_day)))
            for _ in range(n_trades):
                ret_pct = random.choice(trade_pool)
                pnl = cap * ret_pct
                cap += pnl
                if pnl > 0:
                    cur_streak = 0
                else:
                    cur_streak += 1
                    worst_streak = max(worst_streak, cur_streak)
                hwm = max(hwm, cap)
                dd = (hwm - cap) / hwm if hwm > 0 else 0
                max_dd = max(max_dd, dd)

            if (day + 1) % 30 == 0:
                cap -= RENT

            if day == 29:
                m1_cap = cap
            if day == 89:
                m3_cap = cap
            if day == 179:
                m6_cap = cap

        results_m1.append(m1_cap)
        results_m3.append(m3_cap)
        results_m6.append(m6_cap)
        max_drawdowns.append(max_dd)
        worst_streaks.append(worst_streak)

    results_m1 = np.array(results_m1)
    results_m3 = np.array(results_m3)
    results_m6 = np.array(results_m6)
    max_drawdowns = np.array(max_drawdowns)
    worst_streaks = np.array(worst_streaks)

    print(f"\n{'═'*60}")
    print(f"  {label}")
    print(f"  Trade pool: {len(trade_pool)} trades | ~{trades_per_day:.1f}/day")
    print(f"{'═'*60}")

    for month, data, name in [(1, results_m1, "Month 1"), (3, results_m3, "Month 3"), (6, results_m6, "Month 6")]:
        print(f"\n  {name}:")
        print(f"    Median:       ${np.median(data):>12,.0f}")
        print(f"    Mean:         ${np.mean(data):>12,.0f}")
        print(f"    Best 10%:     ${np.percentile(data, 90):>12,.0f}")
        print(f"    Worst 10%:    ${np.percentile(data, 10):>12,.0f}")
        print(f"    Worst 5%:     ${np.percentile(data, 5):>12,.0f}")
        print(f"    % profitable: {(data > 7200).mean()*100:.1f}%")

    print(f"\n  Risk Metrics:")
    print(f"    Avg max drawdown:     {np.mean(max_drawdowns)*100:.1f}%")
    print(f"    95th pctl drawdown:   {np.percentile(max_drawdowns, 95)*100:.1f}%")
    print(f"    Avg worst lose streak: {np.mean(worst_streaks):.0f} trades")
    print(f"    Max lose streak seen:  {np.max(worst_streaks):.0f} trades")
    print(f"    Blown up (<$0):       {(results_m6 < 0).mean()*100:.2f}%")

    return {
        'm1_median': float(np.median(results_m1)),
        'm3_median': float(np.median(results_m3)),
        'm6_median': float(np.median(results_m6)),
        'm3_profitable': float((results_m3 > 7200).mean()*100),
        'm6_profitable': float((results_m6 > 7200).mean()*100),
        'avg_max_dd': float(np.mean(max_drawdowns)*100),
        'blown_up': float((results_m6 < 0).mean()*100),
    }


print("\n" + "=" * 60)
print("  PHASE 2: 90-DAY MONTE CARLO FORWARD PROJECTION")
print("  (10,000 simulations, $2,360/mo rent withdrawals)")
print("=" * 60)

# Scenario A: Current setup (EURUSD + GBPUSD only)
if current_pair_returns:
    scenario_a = run_monte_carlo(current_pair_returns, current_trades_per_day, 
                                  f"SCENARIO A: Current (EURUSD + GBPUSD)")
else:
    print("\n  ⚠️ No trades from EURUSD+GBPUSD — skipping Scenario A")
    scenario_a = None

# Scenario B: Expanded (all profitable pairs)
if expanded_pair_returns:
    scenario_b = run_monte_carlo(expanded_pair_returns, adjusted_expanded_tpd,
                                  f"SCENARIO B: Expanded ({len(profitable)} profitable pairs)")
else:
    print("\n  ⚠️ No expanded trade pool — skipping Scenario B")
    scenario_b = None

# ── Phase 3: Recommendation ──
print("\n" + "=" * 60)
print("  RECOMMENDATION")
print("=" * 60)

if scenario_a and scenario_b:
    a_better = scenario_a['m6_median'] > scenario_b['m6_median']
    b_riskier = scenario_b['blown_up'] > scenario_a['blown_up'] + 1

    print(f"\n  Current (2 pairs): M6 median ${scenario_a['m6_median']:,.0f} | {scenario_a['m6_profitable']:.1f}% profitable | {scenario_a['avg_max_dd']:.1f}% avg DD")
    print(f"  Expanded ({len(profitable)} pairs): M6 median ${scenario_b['m6_median']:,.0f} | {scenario_b['m6_profitable']:.1f}% profitable | {scenario_b['avg_max_dd']:.1f}% avg DD")

    if not a_better and not b_riskier:
        print(f"\n  ✅ RECOMMENDATION: EXPAND to {len(profitable)} pairs")
        print(f"     More trades = faster compounding, better diversification")
        print(f"     Pairs to add: {', '.join(r['symbol'] for r in profitable if r['symbol'] not in ('EURUSD', 'GBPUSD'))}")
    elif b_riskier:
        print(f"\n  ⚠️ RECOMMENDATION: KEEP CURRENT 2 pairs")
        print(f"     Expansion adds more risk than reward")
    else:
        print(f"\n  🤔 RECOMMENDATION: KEEP CURRENT 2 pairs")
        print(f"     Current setup outperforms expansion in median case")
else:
    print("\n  ⚠️ Insufficient data for comparison")

print()
