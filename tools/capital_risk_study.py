#!/usr/bin/env python3
"""Capital vs Risk backtest study for futures trading.

The backtester uses getattr(profile, "risk_per_trade_pct", 0.015).
We dynamically inject this attribute to test different risk levels.
"""

import sys
import os
import logging
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Suppress logging before imports
logging.disable(logging.CRITICAL)
os.environ['LOG_LEVEL'] = 'CRITICAL'

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))


def run_study():
    from tradebot_sci.config.loader import load_settings
    from tradebot_sci.simulation.backtester import Backtester

    settings = load_settings()
    profile = settings.get_active_profile()

    # Force settings for valid backtest (per Gemini's verification)
    profile.icc_auto_entry_enabled = True
    profile.ltf_trend_window = 48

    capital_levels = [100, 80, 70, 60, 50, 40]
    risk_levels = [0.005, 0.01, 0.015, 0.02, 0.025, 0.03, 0.05, 0.10]

    end_date = datetime.now(ZoneInfo('UTC'))
    start_date = end_date - timedelta(days=14)

    results = []

    print("=" * 75)
    print("FUTURES BACKTEST: Capital vs Risk Study")
    print("=" * 75)
    print(f"Period: {start_date.date()} to {end_date.date()} (14 days)")
    print(f"Symbol: BTC/USD | LTF Window: 48 | Auto Entry: Enabled")
    print("=" * 75)
    print()

    for capital in capital_levels:
        print(f"### Capital: ${capital} ###")
        for risk_pct in risk_levels:
            try:
                # Dynamically inject risk_per_trade_pct attribute
                # The backtester reads: getattr(profile, "risk_per_trade_pct", 0.015)
                object.__setattr__(profile, 'risk_per_trade_pct', risk_pct)

                backtester = Backtester(None, settings, None)

                result = backtester.run_backtest(
                    initial_capital=float(capital),
                    start_date=start_date,
                    end_date=end_date,
                    symbols=['BTC/USD'],
                )

                roi_pct = (result.total_pnl / capital) * 100
                status = "PROFIT" if result.total_pnl > 0 else "LOSS"

                results.append({
                    'capital': capital,
                    'risk_pct': risk_pct,
                    'trades': len(result.trades),
                    'pnl': result.total_pnl,
                    'roi': roi_pct,
                    'win_rate': result.win_rate,
                    'max_dd': result.max_drawdown_pct,
                    'final': result.final_capital,
                })

                print(f"  Risk {risk_pct*100:5.1f}%: {len(result.trades):2d} trades | "
                      f"PnL ${result.total_pnl:+8.2f} | ROI {roi_pct:+7.2f}% | "
                      f"WR {result.win_rate:5.1f}% | DD {result.max_drawdown_pct:5.1f}% | {status}")

            except Exception as e:
                import traceback
                print(f"  Risk {risk_pct*100:5.1f}%: ERROR - {str(e)[:60]}")
        print()

    # Summary
    print("=" * 75)
    print("SUMMARY: Best Configuration per Capital Level")
    print("=" * 75)

    for capital in capital_levels:
        cap_results = [r for r in results if r['capital'] == capital]
        if cap_results:
            best = max(cap_results, key=lambda x: x['roi'])
            profitable = "YES" if best['pnl'] > 0 else "NO"
            print(f"${capital:3d} -> Risk {best['risk_pct']*100:4.1f}% | "
                  f"PnL ${best['pnl']:+8.2f} | ROI {best['roi']:+7.2f}% | "
                  f"Trades {best['trades']:2d} | Profitable: {profitable}")

    print()
    print("=" * 75)
    print("MINIMUM VIABLE CAPITAL ANALYSIS")
    print("=" * 75)

    for capital in capital_levels:
        profitable_configs = [r for r in results if r['capital'] == capital and r['pnl'] > 0]
        if profitable_configs:
            print(f"${capital}: {len(profitable_configs)} profitable configs out of {len(risk_levels)}")
            best = max(profitable_configs, key=lambda x: x['roi'])
            print(f"        Best: {best['risk_pct']*100:.1f}% risk -> ${best['pnl']:+.2f} ({best['roi']:+.1f}% ROI)")
        else:
            print(f"${capital}: NO profitable configurations found")

    return results


if __name__ == "__main__":
    run_study()
