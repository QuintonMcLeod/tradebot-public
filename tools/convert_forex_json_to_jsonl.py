#!/usr/bin/env python3
"""
Convert old flat JSON candle files (SYMBOL_5m.json) into the JSONL tree format
that paper_replay.py expects:

    data/<output_dir>/<SYMBOL>/<SYMBOL>_YYYY-MM-DD.jsonl

Each line is a direct candle record with keys: time, open, high, low, close, volume.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_INPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "forex_backtest"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "candle_history_converted"


def parse_iso(ts: str) -> datetime:
    ts = ts.replace("Z", "+00:00")
    return datetime.fromisoformat(ts)


def convert(input_dir: Path, output_dir: Path, timeframe: str = "5m") -> None:
    if not input_dir.exists():
        print(f"[ERROR] Input directory not found: {input_dir}", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(input_dir.glob(f"*_{timeframe}.json"))
    print(f"[INFO] Found {len(files)} {timeframe} files in {input_dir}")

    for src in files:
        stem = src.stem  # e.g. EURUSD_5m
        symbol = stem.rsplit("_", 1)[0]
        sym_dir = output_dir / symbol
        sym_dir.mkdir(parents=True, exist_ok=True)

        with open(src, "r") as fh:
            candles = json.load(fh)

        # Group candles by UTC date
        by_date: dict[str, list] = {}
        for c in candles:
            dt = parse_iso(c["timestamp"])
            dt = dt.astimezone(timezone.utc)
            date_str = dt.strftime("%Y-%m-%d")
            line = {
                "time": c["timestamp"],
                "open": float(c["open"]),
                "high": float(c["high"]),
                "low": float(c["low"]),
                "close": float(c["close"]),
                "volume": float(c.get("volume", 0)),
            }
            by_date.setdefault(date_str, []).append(line)

        for date_str, lines in by_date.items():
            dst = sym_dir / f"{symbol}_{date_str}.jsonl"
            with open(dst, "w") as fh:
                for line in lines:
                    fh.write(json.dumps(line, separators=(",", ":")) + "\n")

        print(f"[INFO] {symbol}: wrote {len(by_date)} day files ({len(candles)} candles)")

    print(f"[INFO] Conversion complete: {output_dir}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Convert flat JSON forex candles to JSONL tree")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--timeframe", default="5m")
    args = parser.parse_args()

    convert(args.input_dir, args.output_dir, args.timeframe)
