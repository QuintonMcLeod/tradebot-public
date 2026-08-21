#!/usr/bin/env python3
"""
Lightweight strategy backtest wrapper for the universal improver.

Directly instantiates a strategy with given parameters, loads cached data,
and runs a simplified backtest. Outputs JSON summary on stdout.

Usage:
    .venv/bin/python tools/strategy_backtest_wrapper.py --strategy rubberband_reaper --symbols EURUSD,GBPUSD --start-date 2026-03-01 --end-date 2026-03-07 --params-json '{"bb_std": 2.0, "rsi_overbought": 70}'
"""
import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone

REPO = Path("/run/media/qchan/Steam Games/Scripts/Trade by SCI/tradebot-sci-debug")
sys.path.insert(0, str(REPO / "src"))

from tradebot_sci.market.models import Candle
from tradebot_sci.strategy.engine import StrategyEngine
from tradebot_sci.config.models import UserConfig, PerAssetStrategies

DATA_DIR = REPO / "data" / "forex_backtest"


def load_candles(symbol: str, start_dt: datetime, end_dt: datetime) -> list:
    """Load cached candle data for a symbol."""
    paths = [
        DATA_DIR / f"{symbol}_5m.json",
        REPO / "data" / "jan_2026" / f"{symbol}_15m.json",
        REPO / "data" / f"{symbol}_15m.json",
        REPO / "data" / f"{symbol}_5m.json",
    ]
    
    for filepath in paths:
        if filepath.exists():
            with open(filepath, "r") as f:
                data = json.load(f)
            candles = []
            for bar in data:
                ts = bar.get("timestamp", "")
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if start_dt <= dt <= end_dt:
                    candles.append(Candle(
                        timestamp=dt,
                        open=float(bar["open"]),
                        high=float(bar["high"]),
                        low=float(bar["low"]),
                        close=float(bar["close"]),
                        volume=float(bar.get("volume", 0)),
                    ))
            return sorted(candles, key=lambda x: x.timestamp)
    return []


def run_backtest(strategy_name: str, symbols: list, start_date: str, end_date: str, 
                 balance: float, strategy_params: dict) -> dict:
    """Run a lightweight backtest for a single strategy."""
    
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, tzinfo=timezone.utc)
    
    # Load data for all symbols
    all_candles = {}
    for sym in symbols:
        candles = load_candles(sym, start_dt, end_dt)
        if candles:
            all_candles[sym] = candles
    
    if not all_candles:
        return {"error": "no_data", "total_trades": 0, "total_pnl": -999999, "win_rate": 0}
    
    # Build config
    strategies = PerAssetStrategies(
        crypto=strategy_name,
        forex=strategy_name,
        stocks=strategy_name,
        etf=strategy_name,
        metals=strategy_name,
        futures=strategy_name,
        meta_sci=strategy_name,
    )
    
    config = UserConfig(
        starting_balance=balance,
        strategies=strategies,
        stop_and_reverse_enabled=False,
        counter_reversal_enabled=False,
    )
    
    # Create engine with strategy kwargs
    engine = StrategyEngine(
        profile=config,
        strategy_kwargs={**strategy_params, "strategy_variant": strategy_name},
    )
    
    # Run simulation
    trades = []
    total_pnl = 0.0
    wins = 0
    losses = 0
    
    for sym, candles in all_candles.items():
        position = None
        entry_price = 0.0
        
        for i, candle in enumerate(candles):
            if i < 20:  # Warmup period
                continue
                
            snapshot = engine.generate_snapshot(sym, candles[:i+1])
            signal = engine.evaluate(sym, snapshot)
            
            if signal and signal.action in ("BUY", "SELL"):
                if position is None:
                    position = signal.action
                    entry_price = candle.close
            
            # Simple exit: next opposite signal or end of data
            if position and signal and signal.action != position and signal.action in ("BUY", "SELL"):
                exit_price = candle.close
                if position == "BUY":
                    pnl = exit_price - entry_price
                else:
                    pnl = entry_price - exit_price
                
                # Convert to dollar PnL (simplified)
                pnl_dollars = pnl * 10000  # Rough forex pip conversion
                trades.append({"pnl": pnl_dollars, "sym": sym})
                total_pnl += pnl_dollars
                if pnl_dollars > 0:
                    wins += 1
                else:
                    losses += 1
                position = None
                entry_price = 0.0
    
    total = wins + losses
    win_rate = (wins / total * 100) if total > 0 else 0
    
    return {
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 2),
        "total_pnl": round(total_pnl, 2),
        "final_balance": round(balance + total_pnl, 2),
        "strategy": strategy_name,
        "params": strategy_params,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--symbols", default="EURUSD,GBPUSD,USDJPY")
    parser.add_argument("--start-date", default="2026-03-01")
    parser.add_argument("--end-date", default="2026-03-07")
    parser.add_argument("--balance", type=float, default=1000.0)
    parser.add_argument("--params-json", default="{}")
    args = parser.parse_args()
    
    symbols = [s.strip() for s in args.symbols.split(",")]
    params = json.loads(args.params_json)
    
    result = run_backtest(
        strategy_name=args.strategy,
        symbols=symbols,
        start_date=args.start_date,
        end_date=args.end_date,
        balance=args.balance,
        strategy_params=params,
    )
    
    print(json.dumps(result))


if __name__ == "__main__":
    main()
