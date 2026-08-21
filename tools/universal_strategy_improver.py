#!/usr/bin/env python3
"""
Universal Strategy Improver — run paper backtests for every variant.

Usage:
    .venv/bin/python tools/universal_strategy_improver.py
    .venv/bin/python tools/universal_strategy_improver.py --strategies rubberband_reaper momentum_rider --samples 8
"""
import os
import sys
import json
import time
import math
import random
import subprocess
from pathlib import Path
from datetime import datetime

REPO = Path("/run/media/qchan/Steam Games/Scripts/Trade by SCI/tradebot-sci-debug")
sys.path.insert(0, str(REPO / "src"))

VENV_PYTHON = REPO / ".venv" / "bin" / "python"

_START_DATE = "2026-03-01"
_END_DATE   = "2026-03-07"
_SYMBOLS    = "EURUSD,GBPUSD,USDJPY"
_BALANCE    = 1000.0


def list_variants() -> list:
    var_dir = REPO / "src" / "tradebot_sci" / "strategy" / "variants"
    names = []
    for p in sorted(var_dir.glob("*.py")):
        n = p.stem
        if n.startswith("_") or n == "base":
            continue
        names.append(n)
    return names


def discover_params(strategy_name: str) -> dict:
    """Return {param_name: [(val1,label), ...]} for grid sweeps."""
    file_path = REPO / "src" / "tradebot_sci" / "strategy" / "variants" / f"{strategy_name}.py"
    if not file_path.exists():
        return {}

    raw = file_path.read_text()
    params = {}

    def _extract(name, default):
        if name in params:
            return
        for pat in (rf"self\.\b{name}\b\s*=\s*([^#\n]+)",
                    rf"\b{name}\b\s*=\s*([^#\n]+)"):
            m = __import__("re").search(pat, raw)
            if m:
                try:
                    params[name] = json.loads(m.group(1).strip().rstrip(","))
                except Exception:
                    params[name] = default
                return
        params[name] = default

    # --- Introspect class signature for clearer defaults ---
    try:
        import importlib, inspect
        mod = importlib.import_module(f"tradebot_sci.strategy.variants.{strategy_name}")
        for attr in dir(mod):
            cls = getattr(mod, attr)
            if inspect.isclass(cls) and hasattr(cls, "evaluate"):
                sig = inspect.signature(cls.__init__)
                for pname, pobj in list(sig.parameters.items())[1:]:
                    if pobj.default is not inspect.Parameter.empty:
                        params[pname] = pobj.default
                break
    except Exception:
        pass

    # Heuristic fallbacks for known strategy families
    if "bb" in strategy_name or "reversion" in strategy_name or "band" in strategy_name:
        _extract("bb_period", 20); _extract("bb_std", 2.0)
        _extract("rsi_period", 14); _extract("rsi_overbought", 70); _extract("rsi_oversold", 30)
    if "rsi" in strategy_name:
        _extract("rsi_period", 14); _extract("rsi_overbought", 70); _extract("rsi_oversold", 30)
    if "adx" in strategy_name or "trend" in strategy_name:
        _extract("adx_period", 14); _extract("adx_threshold", 25)
    if "ema" in strategy_name or "cross" in strategy_name:
        _extract("fast_ema", 12); _extract("slow_ema", 26)
    if "atr" in strategy_name:
        _extract("atr_period", 14); _extract("atr_mult", 1.5)
    if "stop" in strategy_name:
        _extract("stop_atr_mult", 1.5); _extract("stop_floor_pct", 0.001)

    _extract("score_threshold", 60)
    _extract("target_r", 2.0)

    # Build grids
    grids = {}
    for p_name, p_default in params.items():
        if isinstance(p_default, bool):
            grids[p_name] = [(True, "T"), (False, "F")]
        elif isinstance(p_default, int):
            grids[p_name] = [(p_default, "d"), (max(1, p_default - 5), "lo"), (p_default + 5, "hi")]
        elif isinstance(p_default, float):
            grids[p_name] = [(round(p_default, 4), "d"),
                             (round(p_default * 0.8, 4), "lo"),
                             (round(p_default * 1.2, 4), "hi")]

    # Limit to 3 parameters max to keep runtime sane
    if len(grids) > 3:
        # Sort by whether the param name matches strategy name, then alphabetically
        sorted_keys = sorted(grids.keys(), key=lambda k: (0 if k.replace("_", "") in strategy_name else 1, k))
        grids = {k: grids[k] for k in sorted_keys[:3]}

    return grids


def run_paper_replay(strategy_name: str, params: dict) -> dict:
    """Run paper_replay.py with given strategy and parameters via --strategy-kwargs-json."""
    cmd = [
        str(VENV_PYTHON), str(REPO / "tools" / "paper_replay.py"),
        "--start-date", _START_DATE,
        "--end-date", _END_DATE,
        "--symbols", _SYMBOLS,
        "--balance", str(_BALANCE),
        "--strategy", strategy_name,
        "--no-parallel",
        "--json-output",
        "--strategy-kwargs-json", json.dumps(params),
    ]

    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO / "src")

    # Clear stale replay stores
    for stale in Path("/tmp").glob("_replay_*.json"):
        try:
            stale.unlink()
        except Exception:
            pass

    try:
        result = subprocess.run(
            cmd, cwd=str(REPO), env=env,
            capture_output=True, text=True, timeout=600,
        )
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "total_pnl": -999999, "total_trades": 0}

    # Parse JSON summary from last line
    for line in reversed(result.stdout.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue

    return {
        "error": "no_json",
        "stderr": result.stderr[-500:] if result.stderr else "",
        "total_pnl": -999999,
        "total_trades": 0,
    }


def evaluate_strategy_combo(strategy_name: str, params: dict) -> float:
    """Return total_pnl for a given parameter set (higher = better)."""
    summary = run_paper_replay(strategy_name, params)
    if "error" in summary:
        return -999999
    return summary.get("total_pnl", -999999)


def grid_search(strategy_name: str, param_grids: dict, max_samples: int = 32) -> list:
    """Yield dicts of parameter combinations."""
    keys = list(param_grids.keys())
    if not keys:
        return [{}]

    # Cap to max_samples
    total = math.prod(len(v) for v in param_grids.values())
    if total > max_samples:
        combos = []
        random.seed(42)
        for _ in range(max_samples):
            combo = {k: random.choice(param_grids[k])[0] for k in keys}
            if combo not in combos:
                combos.append(combo)
        return combos
    else:
        # Exhaustive cartesian product
        from itertools import product
        vals = [[(k, v[0]) for v in param_grids[k]] for k in keys]
        return [dict(c) for c in product(*vals)]


def improve_strategy(strategy_name: str, max_samples: int = 32) -> dict:
    """Find best parameter set for a single strategy. Returns (best_params, results_list)."""
    print(f"\n{'='*60}")
    print(f"IMPROVING: {strategy_name}")
    print(f"{'='*60}")

    param_grids = discover_params(strategy_name)
    if not param_grids:
        print(f"  No tunable params discovered for {strategy_name}, skipping.")
        return None, []

    print(f"  Parameters: {list(param_grids.keys())}")
    print(f"  Grid size: {math.prod(len(v) for v in param_grids.values())} (capped to {max_samples})")

    combos = grid_search(strategy_name, param_grids, max_samples)
    results = []
    best = {"total_pnl": -999999}

    for i, combo in enumerate(combos, 1):
        print(f"  [{i}/{len(combos)}] Testing {combo} ...", end=" ", flush=True)
        pnl = evaluate_strategy_combo(strategy_name, combo)
        print(f"=> PnL: ${pnl:.2f}")
        results.append({"params": combo, "total_pnl": pnl})
        if pnl > best["total_pnl"]:
            best = {"params": combo, "total_pnl": pnl}

    print(f"\n  BEST for {strategy_name}: {best['params']} → PnL: ${best['total_pnl']:.2f}")
    return best, results


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategies", default="all", help="Comma-separated list or 'all'")
    ap.add_argument("--samples", type=int, default=32, help="Max samples per strategy")
    args = ap.parse_args()

    if args.strategies == "all":
        strategies = list_variants()
    else:
        strategies = [s.strip() for s in args.strategies.split(",")]

    print(f"Found {len(strategies)} strategies: {', '.join(strategies)}")
    print(f"Date range: {_START_DATE} to {_END_DATE} | Symbols: {_SYMBOLS} | Balance: ${_BALANCE}")

    out_dir = REPO / "logs" / "improver_results"
    out_dir.mkdir(parents=True, exist_ok=True)

    all_results = {}
    for strat in strategies:
        best, results = improve_strategy(strat, max_samples=args.samples)
        all_results[strat] = {"best": best, "results": results}

        # Write incremental results
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        (out_dir / f"{strat}_{ts}.json").write_text(
            json.dumps({"strategy": strat, "best": best, "results": results}, indent=2, default=str)
        )

    # Summary
    print(f"\n{'='*60}")
    print("FINAL SUMMARY")
    print(f"{'='*60}")
    for strat, data in all_results.items():
        best = data["best"]
        if best is None:
            print(f"  {strat}: SKIPPED (no tunable params)")
        else:
            print(f"  {strat}: PnL ${best['total_pnl']:.2f} with {best['params']}")

    (out_dir / f"summary_{ts}.json").write_text(
        json.dumps(all_results, indent=2, default=str)
    )
    print(f"\nResults saved to {out_dir}")


if __name__ == "__main__":
    main()
