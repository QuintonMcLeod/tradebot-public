#!/usr/bin/env python3
"""What would this desk pay on a given capital, and can it carry a weekly paycheck?

Reads the eight live OANDA fills through tools/live_trade_history.py, then answers two
questions that are not the same question:

  1. If the record repeats, what does the capital become?  (arithmetic, conditional)
  2. Is there evidence the record repeats?                 (a t-statistic, and the answer
                                                            on n=8 is no)

It also resamples the record's own R multiples at the desk's 6 percent risk unit,
withdrawing the paycheck every week, to show what a fixed dollar draw does to a small
account. That resample is CONDITIONAL AND CIRCULAR: it draws from the same eight trades,
so it says what the record implies if the record were the truth, and nothing about the
world. The t-statistic is printed first for exactly that reason.

Usage:
    ./run-paycheck-check.sh
    ./run-paycheck-check.sh --capital 50000 --weekly-pay 566.71
    python3 tools/paycheck_capital.py --json

Needs OANDA_API_KEY in the environment. The wrapper script sources the secrets file, so
use the wrapper rather than calling this directly.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import statistics as st
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# Vera's answer on Steven's net pay: bus 01791600325158533626, task 1137,
# secretary.money_income row 1, read off the paystubs. Last four stubs average 400.51 net
# a week over 19.88 hours; the ten-stub average is 566.71.
DEFAULT_WEEKLY_PAY = 400.51
# run_state.live_desk_risk: 6 percent of NAV per trade, raised from 4 on 2026-10-07.
RISK = 0.06
# The eight fills span 2026-09-17 to 2026-10-09, which is 22.16 days, so 2.53 trades a week.
TRADES_PER_WEEK = 2.53


def history(capital: int) -> dict:
    out = subprocess.run(
        [sys.executable, str(REPO / "tools" / "live_trade_history.py"),
         "--capital", str(capital), "--json"],
        capture_output=True, text=True, cwd=REPO,
    )
    if out.returncode != 0:
        raise SystemExit(f"live_trade_history failed:\n{out.stderr[-600:]}")
    return json.loads(out.stdout)


def edge_stats(r_multiples: list[float]) -> dict:
    n = len(r_multiples)
    mean = st.mean(r_multiples)
    sd = st.stdev(r_multiples)
    se = sd / math.sqrt(n)
    lo, hi = mean - 1.96 * se, mean + 1.96 * se
    print(f"\nEDGE, from {n} fills")
    print(f"  mean {mean:+.3f}R per trade, sd {sd:.3f}R, standard error {se:.3f}R")
    print(f"  t = {mean / se:.2f} against this project's pre-registered bar of |t| > 3")
    print(f"  95 percent range on the mean: {lo:+.3f}R to {hi:+.3f}R"
          f"{'   <- includes zero' if lo < 0 < hi else ''}")
    needed = (3 * sd / mean) ** 2 if mean > 0 else float("inf")
    print(f"  trades needed for the mean to clear the bar: {needed:.0f}"
          f" (about {needed / TRADES_PER_WEEK:.0f} weeks at {TRADES_PER_WEEK} a week)")
    return dict(n=n, mean=mean, sd=sd, se=se, lo=lo, hi=hi, needed=needed)


def weekly_table(stats: dict, capital: float, weekly_pay: float) -> list[dict]:
    print(f"\nTHE WEEKLY RATE, at {RISK:.0%} risk a trade and {TRADES_PER_WEEK} trades a week")
    print(f"  {'':30} {'per week':>10} {'on ' + f'{capital:,.0f}':>14} {'capital for the paycheck':>26}")
    rows = []
    for label, r in (("low end of the 95% range", stats["lo"]),
                     ("middle of the record", stats["mean"]),
                     ("high end of the 95% range", stats["hi"])):
        rate = r * RISK * TRADES_PER_WEEK
        if rate > 0:
            need = f"{weekly_pay / rate:,.0f}"
        else:
            need = "no amount, the edge is negative"
        print(f"  {label:30} {rate * 100:>9.2f}% {rate * capital:>+14,.0f} {need:>26}")
        rows.append(dict(label=label, r=r, weekly_rate=rate, capital_needed=None if rate <= 0 else weekly_pay / rate))
    return rows


def survive(capital: float, r_multiples: list[float], weekly_pay: float,
            weeks: int = 260, trials: int = 4000, seed: int = 3) -> tuple[float, float]:
    """Fraction still solvent after `weeks`, and the median life in years."""
    random.seed(seed)
    solvent = 0
    lives: list[int] = []
    for _ in range(trials):
        nav = capital
        for week in range(weeks):
            # 2.53 trades a week, so alternate 3 and 2 rather than draw a count.
            for _ in range(3 if week % 2 == 0 else 2):
                nav *= 1 + random.choice(r_multiples) * RISK
            nav -= weekly_pay
            if nav <= 0:
                lives.append(week + 1)
                break
        else:
            lives.append(weeks)
            solvent += 1
    return solvent / trials, st.median(lives) / 52


def winner_arithmetic(r_multiples: list[float], capital: float) -> dict:
    wins = [r for r in r_multiples if r > 0]
    losses = [r for r in r_multiples if r < 0]
    avg_win, avg_loss = st.mean(wins), abs(st.mean(losses))
    targets = [r for r in r_multiples if r >= 1.5]
    toll = 0.05  # run_state.live_desk_risk: the 1.5 to 1.6-pip toll is about 5 percent of R
    breakeven = (avg_loss + toll) / (avg_win - toll + avg_loss + toll)
    print("\nCUT LOSERS, LET WINNERS RUN: the hit rate this needs")
    print(f"  average winner {avg_win:+.2f}R, average loser {avg_loss:.2f}R"
          f"   (winners: {[round(r, 2) for r in wins]}, losers: {[round(r, 2) for r in losses]})")
    print(f"  one average winner pays for {avg_win / avg_loss:.2f} average losers")
    print(f"  break-even hit rate {breakeven * 100:.1f}%, with the toll charged on every trade")
    print(f"  the record's hit rate: {len(targets)} of {len(r_multiples)} reached target"
          f" = {len(targets) / len(r_multiples) * 100:.1f}%,"
          f" {len(wins)} of {len(r_multiples)} closed green = {len(wins) / len(r_multiples) * 100:.1f}%")
    print(f"  one trade moves that hit rate by {100 / len(r_multiples):.1f} points")
    risk_usd = capital * RISK
    print(f"  at {capital:,.0f} and {RISK:.0%} risk, one trade risks {risk_usd:,.0f} and one"
          f" average winner pays {risk_usd * avg_win:,.0f}")
    return dict(avg_win=avg_win, avg_loss=avg_loss, breakeven=breakeven,
                hit_rate=len(targets) / len(r_multiples),
                losers_paid=avg_win / avg_loss)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--capital", type=int, default=10000)
    ap.add_argument("--weekly-pay", type=float, default=DEFAULT_WEEKLY_PAY,
                    help="net weekly pay to match (Vera: 400.51 recent, 566.71 ten-week)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not os.environ.get("OANDA_API_KEY"):
        raise SystemExit("OANDA_API_KEY is not set. Use ./run-paycheck-check.sh, which "
                         "sources ~/.config/secrets/.env.secrets without putting the key "
                         "on a command line.")
    if args.capital <= 0:
        raise SystemExit("--capital must be positive.")

    data = history(args.capital)
    R = [t["r"] for t in data["trades"]]
    print(f"live record: {len(R)} fills, {data['opening_balance']:,.2f} -> "
          f"{data['balance']:,.2f}, net {data['net_pnl']:+.2f} USD "
          f"({data['net_pct']:+.2f} percent), as of {data['as_of']}")
    print(f"paycheck to match: {args.weekly_pay:,.2f} net a week "
          f"= {args.weekly_pay * 52:,.0f} a year "
          f"= {args.weekly_pay * 52 / args.capital * 100:.0f} percent a year on {args.capital:,.0f}")

    stats = edge_stats(R)
    rows = weekly_table(stats, args.capital, args.weekly_pay)

    print(f"\nIS DRAWING {args.weekly_pay:,.2f} A WEEK THE THING THAT BREAKS IT?")
    print("  (resampling the record's own trades; circular, so read it as what the record"
          " implies, not as a forecast)")
    print(f"  {'start':>9}  {'all 8 trades':>28}  {'without trade 8':>28}")
    survival = {}
    for cap in (10000, 25000, 50000, 100000):
        s_all, life_all = survive(cap, R, args.weekly_pay)
        s_7, life_7 = survive(cap, R[:-1], args.weekly_pay, seed=5)
        print(f"  {cap:>9,}  {s_all * 100:>8.1f}% solvent, {life_all:>4.1f}y  "
              f"{s_7 * 100:>8.1f}% solvent, {life_7:>4.1f}y")
        survival[cap] = dict(all=s_all, all_life=life_all, no_lucky=s_7, no_lucky_life=life_7)

    wa = winner_arithmetic(R, args.capital)

    t8 = data["trades"][-1]
    print("\nTHE WHOLE RECORD HANGS ON ONE TRADE")
    print(f"  net {data['net_pnl']:+.2f} USD; without trade {t8['n']} it is "
          f"{data['net_pnl'] - t8['pnl']:+.2f}; if that trade had stopped instead of reaching"
          f" target it is {data['net_pnl'] - t8['pnl'] - t8['risk_usd']:+.2f}")

    if args.json:
        print("\n" + json.dumps(dict(capital=args.capital, weekly_pay=args.weekly_pay,
                                     stats=stats, rows=rows, survival=survival,
                                     winner=wa), indent=2, default=str))


if __name__ == "__main__":
    main()
