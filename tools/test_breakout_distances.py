#!/usr/bin/env python3
"""
test_breakout_distances.py — Sweep breakout_distance_pct values via paper_replay.

Loops over [0.3, 0.5, 0.7, 1.0] and runs paper_replay.py with:
  --strategy forex_hybrid_breakout
  --breakout-distance-pct <value>
  --json-output

Collects results and prints a summary table:
  Distance | Trades | Win% | PnL | MaxDD
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PAPER_REPLAY = REPO_ROOT / "tools" / "paper_replay.py"
PYTHON = sys.executable

DISTANCES = [0.3, 0.5, 0.7, 1.0]


def run_replay(distance: float) -> dict:
    """Run paper_replay for a single breakout distance and return the JSON result."""
    cmd = [
        PYTHON,
        str(PAPER_REPLAY),
        "--strategy", "forex_hybrid_breakout",
        "--breakout-distance-pct", str(distance),
        "--json-output",
        "--speed", "0",
        "--days", "4",
    ]

    print(f"[TEST] Running breakout_distance_pct={distance} ...", flush=True)
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))

    last_json = None
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                last_json = json.loads(line)
            except json.JSONDecodeError:
                continue

    if last_json is None:
        print(f"[ERROR] No JSON output for distance={distance}", file=sys.stderr)
        print(f"[STDERR] {result.stderr[:500]}", file=sys.stderr)
        return {}

    return last_json


def main():
    print("=" * 70)
    print("Breakout Distance Sweep — ForexHybridBreakout")
    print("=" * 70)

    rows = []
    for dist in DISTANCES:
        res = run_replay(dist)
        rows.append({
            "distance": dist,
            "trades": res.get("total_trades", 0),
            "win_rate": res.get("win_rate", 0.0),
            "pnl": res.get("total_pnl", 0.0),
            "max_dd": res.get("max_drawdown", 0.0),
        })

    print()
    print("-" * 60)
    print(f"{'Distance':>10} | {'Trades':>6} | {'Win%':>6} | {'PnL':>10} | {'MaxDD':>6}")
    print("-" * 60)
    for r in rows:
        print(
            f"{r['distance']:>10.1f} | {r['trades']:>6} | {r['win_rate']:>5.1f}% | "
            f"${r['pnl']:>+8.2f} | {r['max_dd']:>5.1f}%"
        )
    print("-" * 60)


if __name__ == "__main__":
    main()
