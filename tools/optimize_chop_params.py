#!/usr/bin/env python3
"""Parameter sweep for chop-oriented settings in run_forex_backtest_full.py."""

from __future__ import annotations

import io
import os
import re
import sys
import time
import random
import logging
from contextlib import redirect_stdout
from importlib.util import spec_from_file_location, module_from_spec


BASE_DIR = os.path.join("/home/qchan/Scripts/Trade by SCI/tradebot-sci-debug")
DATA_DIR = os.path.join(BASE_DIR, "data", "forex_backtest")
SCRIPT_PATH = os.path.join(BASE_DIR, "tools", "run_forex_backtest_full.py")

FX_CODES = {"USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF"}


def discover_symbols() -> list[str]:
    symbols: list[str] = []
    for name in os.listdir(DATA_DIR):
        if not name.endswith("_15m.json"):
            continue
        sym = name[:-9]
        if len(sym) == 6 and sym[:3] in FX_CODES and sym[3:] in FX_CODES:
            symbols.append(sym)
        elif sym in {"XAUUSD", "XAGUSD"}:
            symbols.append(sym)
    return sorted(set(symbols))


def load_module():
    spec = spec_from_file_location("forex_backtest_full", SCRIPT_PATH)
    mod = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def parse_metrics(output: str) -> dict[str, float | int]:
    metrics: dict[str, float | int] = {}
    patterns = {
        "trades": r"Trades:\s+(\d+)",
        "final_capital": r"Final Capital:\s+\$([\d\.\-]+)",
        "total_pnl": r"Total PnL:\s+\$([\d\.\-]+)",
        "winners": r"Winners:\s+(\d+)",
        "losers": r"Losers:\s+(\d+)",
        "win_rate": r"Win Rate:\s+([\d\.]+)%",
    }
    for key, pat in patterns.items():
        match = re.search(pat, output)
        if match:
            val = match.group(1)
            metrics[key] = float(val) if "." in val else int(val)
    return metrics


def score(metrics: dict[str, float | int]) -> float:
    # Primary: profit, secondary: more trades, fewer losses.
    final_capital = float(metrics.get("final_capital", 0.0))
    trades = int(metrics.get("trades", 0))
    losers = int(metrics.get("losers", 0))
    win_rate = float(metrics.get("win_rate", 0.0))

    if trades < 20:
        return float("-inf")

    profit = final_capital - 100.0
    return (profit * 100.0) + (trades * 2.0) + (win_rate * 1.0) - (losers * 2.0)


def main() -> int:
    symbols = discover_symbols()
    if not symbols:
        print("No symbols available.")
        return 1

    grid = {
        "MIN_STOP_PCT": [0.0006, 0.0008, 0.0010, 0.0012],
        "MIN_ENTRY_RANGE_PIPS": [0, 1, 2, 3, 4],
        "PROFIT_BUFFER_PCT_CHOP": [0.0015, 0.002, 0.0025, 0.003],
        "BE_DELAY_BARS": [0, 1, 2],
        "HTF_FLIP_EXIT_PNL": [-0.001, 0.0],
        "MIN_MOMENTUM_PIPS": [0, 5],
    }
    max_seconds = 100
    max_iters = 6

    best = {"score": float("-inf"), "params": None, "metrics": None}
    tried: set[tuple] = set()
    start = time.time()
    mod = load_module()

    def sample_params():
        return {
            "MIN_STOP_PCT": random.choice(grid["MIN_STOP_PCT"]),
            "MIN_ENTRY_RANGE_PIPS": random.choice(grid["MIN_ENTRY_RANGE_PIPS"]),
            "PROFIT_BUFFER_PCT_CHOP": random.choice(grid["PROFIT_BUFFER_PCT_CHOP"]),
            "BE_DELAY_BARS": random.choice(grid["BE_DELAY_BARS"]),
            "HTF_FLIP_EXIT_PNL": random.choice(grid["HTF_FLIP_EXIT_PNL"]),
            "MIN_MOMENTUM_PIPS": random.choice(grid["MIN_MOMENTUM_PIPS"]),
        }

    for idx in range(1, max_iters + 1):
        if time.time() - start > max_seconds:
            break
        params = sample_params()
        sig = tuple(params.items())
        if sig in tried:
            continue
        tried.add(sig)

        mod.DATA_DIR = DATA_DIR
        mod.FOREX_PAIRS = symbols
        mod.logger.setLevel(logging.WARNING)

        for key, value in params.items():
            setattr(mod, key, value)

        buf = io.StringIO()
        with redirect_stdout(buf):
            mod.run_forex_backtest()
        out = buf.getvalue()
        metrics = parse_metrics(out)
        score_val = score(metrics)

        print(f"Run {idx}/{max_iters} -> score={score_val:.2f} params={params} metrics={metrics}")
        if score_val > best["score"]:
            best = {"score": score_val, "params": params, "metrics": metrics}

    print("BEST CONFIG")
    print(best["params"])
    print(best["metrics"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
