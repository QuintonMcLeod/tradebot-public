#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                         PROFIT AUDIT                                       ║
║          Verify Settings Produce Profits When Correctly Configured          ║
╚══════════════════════════════════════════════════════════════════════════════╝

Runs the mega backtester across multiple strategy × market configurations,
then grades each:

  ✅ PASS  — Net profitable with reasonable win rate (big wins, small losses)
  ⚠️ WARN  — Marginally profitable or break-even
  ❌ FAIL  — Net loss with correct settings → something is WRONG

Usage:
    python3 tools/profit_audit.py                          # All tests
    python3 tools/profit_audit.py --market forex           # Forex only
    python3 tools/profit_audit.py --market crypto          # Crypto only
    python3 tools/profit_audit.py --strategy supply_demand # One strategy
"""

import sys
import os
import json
import unittest.mock
import logging
import argparse
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Tuple
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# MOCK ib_insync
sys.modules["ib_insync"] = unittest.mock.MagicMock()
os.environ["TRADING_CONFIRMATION"] = "YES"

logging.basicConfig(level=logging.WARNING, format="%(message)s")
logger = logging.getLogger("profit_audit")


# ── Forward Test All Strategies ──────────────────────────────────────────────

STRATEGIES_TO_TEST = [
    "supply_demand", "evolution", "rubberband_reaper", "robocop",
    "meta_sci", "icc_core", "hyper_scalper", "quantum",
    "mean_reversion", "trend_rider", "aggregator", "orb",
    "session_momentum", "london_breakout", "volatility_breakout",
    "bearish_engulfing",
]


def run_forward_tests() -> List[Dict[str, Any]]:
    """Run forward tester hold guard and decision tests across all strategies."""
    import math
    from datetime import timezone
    from tradebot_sci.market.models import Candle, MarketSnapshot, TrendState
    from tradebot_sci.config.models import (
        Settings, AppSettings, LoggingSettings, AISettings, MarketSettings,
        TradingProfileSettings,
    )
    from tradebot_sci.strategy.engine import StrategyEngine
    from tradebot_sci.simulation.backtester import HistoricalMarketDataProvider

    def make_uptrend(n=250, start=1.1000, step=0.0003, noise=0.0002):
        candles = []
        t = datetime(2026, 1, 15, 14, 30, tzinfo=timezone.utc)
        price = start
        for i in range(n):
            base_move = step * (1.0 + 0.3 * math.sin(i * 0.15))
            o = price
            c = price + base_move
            h = max(o, c) + noise * abs(math.sin(i * 0.7))
            l = min(o, c) - noise * abs(math.cos(i * 0.9))
            candles.append(Candle(timestamp=t, open=o, high=h, low=l, close=c, volume=1000))
            price = c
            t += timedelta(minutes=5)
        return candles

    def make_downtrend(n=20, start=1.2000, step=0.0008, start_time=None):
        candles = []
        t = start_time or datetime(2026, 1, 15, 14, 30, tzinfo=timezone.utc)
        price = start
        for i in range(n):
            base_move = step * (1.0 + 0.3 * math.sin(i * 0.15))
            o = price
            c = price - base_move
            h = max(o, c) + 0.0002 * abs(math.sin(i * 0.7))
            l = min(o, c) - 0.0002 * abs(math.cos(i * 0.9))
            candles.append(Candle(timestamp=t, open=o, high=h, low=l, close=c, volume=1000))
            price = c
            t += timedelta(minutes=5)
        return candles

    results = []

    for variant in STRATEGIES_TO_TEST:
        try:
            profile = TradingProfileSettings(
                strategy_variant=variant,
                candle_timeframe="5m",
                htf_timeframe="1h",
                ltf_timeframe="5m",
                trend_window=30,
                ltf_trend_window=30,
                risk_per_trade_pct=0.01,
                block_counter_trend_entries=True,
            )
            settings = Settings(
                app=AppSettings(profile_name="FwdTest"),
                logging=LoggingSettings(),
                ai=AISettings(provider="openai"),
                market=MarketSettings(symbols=["EURUSD"]),
                profiles={"FwdTest": profile},
            )
            provider = HistoricalMarketDataProvider(ib=None, settings=settings)

            # Test 1: Does the engine load and produce a decision?
            up_candles = make_uptrend(250, step=0.0004)
            reversal_candles = make_downtrend(10, start=up_candles[-1].close,
                                               start_time=up_candles[-1].timestamp + timedelta(minutes=5))
            all_candles = up_candles + reversal_candles
            provider._cache["EURUSD:5m_current"] = all_candles

            engine = StrategyEngine(
                ai_client=None, market_provider=provider,
                profile=profile, symbol="EURUSD",
            )

            neutral = TrendState(direction="neutral", strength=0.0)
            snapshot = MarketSnapshot(
                symbol="EURUSD", timeframe="5m", candles=all_candles,
                trend_htf=neutral, trend_ltf=neutral,
                htf_candles=all_candles[-100:], ltf_candles=all_candles[-100:],
                htf_timeframe="1h", ltf_timeframe="5m",
            )

            # Decision without position
            no_pos_decision = engine.decide(
                timeframe="5m", open_position=None,
                snapshot=snapshot, current_capital=10000.0,
            )
            loads_ok = no_pos_decision is not None
            no_pos_action = no_pos_decision.action if no_pos_decision else "ERROR"

            # Test 2: Hold guard — open position < 1 hour, adverse candles
            entry_time = datetime.now(tz=timezone.utc) - timedelta(minutes=30)
            open_position = {
                "symbol": "EURUSD", "direction": "long",
                "entry_price": up_candles[-15].close, "size": 100,
                "stop_price": up_candles[-15].close - 0.0050,
                "stop_loss": up_candles[-15].close - 0.0050,
                "target_price": up_candles[-15].close + 0.0100,
                "unrealized_pnl": -0.50, "pyramid_count": 1,
                "htf_neutral_bars": 0,
                "entry_time": entry_time.isoformat(),
            }

            exit_decision = engine.decide(
                timeframe="5m", open_position=open_position,
                snapshot=snapshot, current_capital=10000.0,
            )
            hold_guard_ok = exit_decision.action != "close_position"
            exit_action = exit_decision.action if exit_decision else "ERROR"

            results.append({
                "strategy": variant,
                "loads": loads_ok,
                "no_pos_action": no_pos_action,
                "hold_guard": hold_guard_ok,
                "exit_action": exit_action,
                "error": None,
            })

        except Exception as e:
            results.append({
                "strategy": variant,
                "loads": False,
                "no_pos_action": "ERROR",
                "hold_guard": False,
                "exit_action": "ERROR",
                "error": str(e)[:80],
            })

    return results


def print_forward_report(results: List[Dict[str, Any]]):
    """Print forward test results."""
    print(f"\n{'=' * 80}")
    print("                     FORWARD TESTER: STRATEGY AUDIT")
    print(f"{'=' * 80}")
    print(f"\n{'Strategy':<25} {'Loads':>5}  {'No-Pos Action':<18} {'Hold?':>5}  {'Exit Action':<18} {'Error'}")
    print("─" * 95)

    for r in results:
        loads = "✅" if r["loads"] else "❌"
        hold = "✅" if r["hold_guard"] else "❌"
        err = r["error"][:30] if r.get("error") else ""
        print(f"  {r['strategy']:<23} {loads:>5}  {r['no_pos_action']:<18} {hold:>5}  {r['exit_action']:<18} {err}")

    # Summary
    total = len(results)
    loads_ok = sum(1 for r in results if r["loads"])
    hold_ok = sum(1 for r in results if r["hold_guard"])
    errors = sum(1 for r in results if r.get("error"))

    print(f"\n  SUMMARY: {loads_ok}/{total} load OK | {hold_ok}/{total} hold guard OK | {errors} errors")
    if hold_ok < total:
        failed = [r["strategy"] for r in results if not r["hold_guard"]]
        print(f"  ❌ Hold guard failures: {', '.join(failed)}")
    if errors > 0:
        errored = [f"{r['strategy']}({r['error'][:20]})" for r in results if r.get("error")]
        print(f"  ❌ Errors: {', '.join(errored)}")

# ── Test Configuration Profiles ──────────────────────────────────────────────
# These represent CORRECTLY CONFIGURED settings for each market type.
# The audit verifies that these settings produce profits.

class P(dict):
    """Dict that supports dot notation for profile settings."""
    def __getattr__(self, item): return self.get(item)
    def __setattr__(self, key, value): self[key] = value


FOREX_SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]
CRYPTO_SYMBOLS = ["BTCUSD", "ETHUSD", "SOLUSD"]
HYBRID_SYMBOLS = FOREX_SYMBOLS + CRYPTO_SYMBOLS

# ── Settings Audit Matrix ────────────────────────────────────────────────────
# Each entry: (test_name, profile_dict, symbols, market_type)
# These represent the "correct" settings for each scenario.

def _forex_base(**overrides) -> P:
    """Correct settings for forex trading."""
    d = P(
        candle_timeframe="15m",
        htf_timeframe="1h",
        ltf_timeframe="5m",
        trend_window=12,
        ltf_trend_window=8,
        trend_swing_lookback=2,
        trend_min_swings=2,
        trend_strength_floor=0.20,
        risk_per_trade_pct=0.04,
        max_concurrent_positions=4,
        multi_position_enabled=True,
        max_pyramid_entries=3,
        market_poll_interval_seconds=60,
        ai_decision_interval_seconds=60,
        icc_entry_score_threshold=55.0,
        min_hold_hours=1.0,
        block_counter_trend_entries=True,
        # Trend Indicators — must enable multiple for robust consensus
        trend_adx_enabled=True,
        trend_ema_ribbon_enabled=True,
        trend_supertrend_enabled=True,
        trend_macd_enabled=True,
    )
    d.update(overrides)
    return d


def _crypto_base(**overrides) -> P:
    """Correct settings for crypto trading (higher volatility)."""
    d = P(
        candle_timeframe="5m",
        htf_timeframe="15m",
        ltf_timeframe="5m",
        trend_window=12,
        ltf_trend_window=8,
        trend_swing_lookback=2,
        trend_min_swings=2,
        trend_strength_floor=0.25,
        risk_per_trade_pct=0.02,   # Lower risk for crypto volatility
        max_concurrent_positions=3,
        multi_position_enabled=True,
        max_pyramid_entries=2,
        market_poll_interval_seconds=60,
        ai_decision_interval_seconds=60,
        icc_entry_score_threshold=55.0,
        min_hold_hours=1.0,
        block_counter_trend_entries=True,
        # Trend Indicators — must enable multiple for robust consensus
        trend_adx_enabled=True,
        trend_ema_ribbon_enabled=True,
        trend_supertrend_enabled=True,
        trend_macd_enabled=True,
    )
    d.update(overrides)
    return d


# Strategies worth auditing (the ones users actually use):
AUDIT_MATRIX = [
    # ── FOREX ──
    ("Forex: Supply & Demand",   _forex_base(strategy_variant="supply_demand"),   FOREX_SYMBOLS, "forex"),
    ("Forex: Evolution",         _forex_base(strategy_variant="evolution"),        FOREX_SYMBOLS, "forex"),
    ("Forex: Rubberband Reaper", _forex_base(strategy_variant="rubberband_reaper"), FOREX_SYMBOLS, "forex"),
    ("Forex: RoboCop",           _forex_base(strategy_variant="robocop"),          FOREX_SYMBOLS, "forex"),
    ("Forex: Meta-SCI",          _forex_base(strategy_variant="meta_sci"),         FOREX_SYMBOLS, "forex"),
    ("Forex: ICC Core",          _forex_base(strategy_variant="icc_core"),         FOREX_SYMBOLS, "forex"),

    # ── CRYPTO ──
    ("Crypto: Supply & Demand",  _crypto_base(strategy_variant="supply_demand"),  CRYPTO_SYMBOLS, "crypto"),
    ("Crypto: Evolution",        _crypto_base(strategy_variant="evolution"),       CRYPTO_SYMBOLS, "crypto"),
    ("Crypto: RoboCop",          _crypto_base(strategy_variant="robocop"),         CRYPTO_SYMBOLS, "crypto"),
    ("Crypto: Meta-SCI",         _crypto_base(strategy_variant="meta_sci"),        CRYPTO_SYMBOLS, "crypto"),

    # ── HYBRID (both) ──
    ("Hybrid: Meta-SCI",         _forex_base(strategy_variant="meta_sci"),         HYBRID_SYMBOLS, "hybrid"),
    ("Hybrid: Supply & Demand",  _forex_base(strategy_variant="supply_demand"),   HYBRID_SYMBOLS, "hybrid"),

    # ── SAFETY SETTINGS AUDIT (verify settings are not ignored) ──
    ("Forex: SND NoHold (control)", _forex_base(strategy_variant="supply_demand", min_hold_hours=0.0), FOREX_SYMBOLS, "control"),
    ("Forex: SND CounterTrend ON",  _forex_base(strategy_variant="supply_demand", block_counter_trend_entries=False), FOREX_SYMBOLS, "control"),
]


def run_single_backtest(name: str, profile: P, symbols: list,
                        start_date: datetime, end_date: datetime,
                        capital: float = 2000.0) -> Dict[str, Any]:
    """Run a backtest for one configuration."""
    from tradebot_sci.config.models import (
        Settings, AppSettings, LoggingSettings, AISettings, MarketSettings,
        TradingProfileSettings,
    )
    from tradebot_sci.simulation.backtester import Backtester
    from tools.utils.local_provider import LocalJSONProvider

    real_profile = TradingProfileSettings(**dict(profile))
    settings = Settings(
        app=AppSettings(profile_name="AuditProfile"),
        logging=LoggingSettings(),
        ai=AISettings(provider="openai"),
        market=MarketSettings(symbols=symbols),
        profiles={"AuditProfile": real_profile},
    )

    # Data directory for audit candle files (auto-downloaded via CCXT)
    data_dir = os.path.join(os.path.dirname(__file__), "../data/audit")
    os.makedirs(data_dir, exist_ok=True)

    backtester = Backtester(ib=None, settings=settings, ai_client=None)
    # Inject LocalJSONProvider which auto-downloads missing data via CCXT/Kraken
    backtester.market_provider = LocalJSONProvider(data_dir)
    # Force market hours open for backtesting
    backtester._is_market_hours_utc = lambda ts: True

    try:
        results = backtester.run_backtest(
            initial_capital=capital,
            start_date=start_date,
            end_date=end_date,
            wind_down_days=0,
        )
    except Exception as e:
        return {"name": name, "error": str(e), "trades": [], "pnl": 0.0}

    trades = results.trades

    # ── Fee Estimation (for FEE IMPACT report only) ──────────────────
    # Fees are now deducted IN the backtester's _calculate_pnl via get_fee_for_symbol().
    # We estimate total fees here purely for the FEE IMPACT display section.
    from tradebot_sci.utils.symbol_classifier import get_fee_for_symbol
    total_fees = 0.0
    for t in trades:
        sym = getattr(t, 'symbol', '') or ''
        entry_p = t.entry_price or 0
        size = t.size or 0
        fee = entry_p * abs(size) * get_fee_for_symbol(sym)
        total_fees += fee

    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    total = len(trades)
    win_rate = len(wins) / total * 100 if total else 0
    gross_profit = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 0
    avg_loss = sum(abs(t.pnl) for t in losses) / len(losses) if losses else 0
    rr_ratio = avg_win / avg_loss if avg_loss > 0 else float('inf')

    # Net P&L (already includes fees from backtester)
    net_pnl = sum(t.pnl for t in trades)
    net_return = (net_pnl / capital) * 100 if capital > 0 else 0

    # Exit reason breakdown
    exit_counts = defaultdict(int)
    for t in trades:
        reason = t.exit_reason[:40] if t.exit_reason else "unknown"
        exit_counts[reason] += 1

    # Direction breakdown
    longs = sum(1 for t in trades if getattr(t, 'direction', '') == 'long')
    shorts = sum(1 for t in trades if getattr(t, 'direction', '') == 'short')

    # Duration analysis
    durations = [(t.exit_time - t.entry_time).total_seconds() / 60 for t in trades]
    avg_hold = sum(durations) / len(durations) if durations else 0
    min_hold = min(durations) if durations else 0
    max_hold = max(durations) if durations else 0

    # Hold guard effectiveness
    early_sltp = sum(1 for t in trades
                     if (t.exit_time - t.entry_time).total_seconds() < 3600
                     and t.exit_reason in ("stop", "target"))
    early_non_sltp = sum(1 for t in trades
                         if (t.exit_time - t.entry_time).total_seconds() < 3600
                         and t.exit_reason not in ("stop", "target", "eod"))

    # TP/SL breakdown
    tp_count = exit_counts.get("target", 0)
    sl_count = exit_counts.get("stop", 0)

    return {
        "name": name,
        "total_trades": total,
        "win_rate": round(win_rate, 1),
        "pnl": round(net_pnl, 2),
        "return_pct": round(net_return, 2),
        "profit_factor": round(profit_factor, 2) if profit_factor != float('inf') else "∞",
        "avg_win": round(avg_win, 4),
        "avg_loss": round(avg_loss, 4),
        "rr_ratio": round(rr_ratio, 2) if rr_ratio != float('inf') else "∞",
        "max_drawdown": round(results.max_drawdown_pct, 1),
        "avg_hold_min": round(avg_hold, 1),
        "min_hold_min": round(min_hold, 1),
        "max_hold_min": round(max_hold, 1),
        "longs": longs,
        "shorts": shorts,
        "tp_hits": tp_count,
        "sl_hits": sl_count,
        "exit_reasons": dict(exit_counts),
        "early_sltp_exits": early_sltp,
        "early_non_sltp_exits": early_non_sltp,
        "total_fees": round(total_fees, 2),
        "error": None,
    }


def grade_result(r: Dict[str, Any], is_control: bool = False) -> str:
    """Grade a backtest result."""
    if r.get("error"):
        return "💥 ERROR"
    if r["total_trades"] == 0:
        return "⬜ NO TRADES"
    if is_control:
        return "🔬 CONTROL"

    pnl = r["pnl"]
    win_rate = r["win_rate"]
    rr = r["rr_ratio"]

    # With proper trend detection, the bot should read the market well enough
    # to achieve at least a 35% win rate. Below that = trend detection isn't
    # working or strategy is broken.
    MIN_WIN_RATE = 35.0

    if win_rate < MIN_WIN_RATE:
        if r.get("early_non_sltp_exits", 0) > 0:
            return "❌ HOLD GUARD LEAK"
        return "❌ FAIL (Win% < 35)"

    if pnl > 0:
        return "✅ PASS"
    elif pnl == 0:
        return "⚠️ BREAK-EVEN"
    else:
        return "❌ FAIL"


def _fmt_rr(rr):
    """Format R:R as a readable ratio like '2.1:1' or '∞'."""
    if not isinstance(rr, (int, float)):
        return "∞"
    if rr > 100:
        return f"{rr:.0f}:1"
    return f"{rr:.1f}:1"


def print_report(results: List[Dict[str, Any]], capital: float = 2000.0):
    """Print the full audit report."""
    print()
    print("=" * 90)
    print("                           PROFIT AUDIT REPORT")
    print(f"                        {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"                        Starting Capital: ${capital:,.0f}")
    print("=" * 90)

    # Summary table
    print(f"\n{'Test Name':<35} {'Grade':<20} {'Trades':>6}  {'Win%':>5}  {'R:R':>8}  {'P&L':>12}  {'Return':>8}")
    print("─" * 100)

    for r in results:
        is_control = "control" in r.get("name", "").lower()
        grade = grade_result(r, is_control)
        name = r["name"][:34]
        trades = r.get("total_trades", 0)
        wr = r.get("win_rate", 0)
        rr = r.get("rr_ratio", "N/A")
        pnl = r.get("pnl", 0)
        ret = r.get("return_pct", 0)
        error = r.get("error", "")

        if error:
            print(f"  {name:<33} {grade:<20} {'ERR':>6}  {'-':>5}  {'-':>8}  {error[:12]:>12}  {'-':>8}")
        else:
            rr_str = _fmt_rr(rr)
            print(f"  {name:<33} {grade:<20} {trades:>6}  {wr:>4.0f}%  {rr_str:>8}  ${pnl:>11.2f}  {ret:>6.1f}%")

    # Settings effectiveness analysis
    print(f"\n{'─' * 80}")
    print("SETTINGS EFFECTIVENESS ANALYSIS")
    print(f"{'─' * 80}")

    # Compare hold vs no-hold
    hold_result = next((r for r in results if "Supply & Demand" in r["name"] and "NoHold" not in r["name"] and "forex" in r["name"].lower()), None)
    nohold_result = next((r for r in results if "NoHold" in r["name"]), None)

    if hold_result and nohold_result and not hold_result.get("error") and not nohold_result.get("error"):
        hold_pnl = hold_result["pnl"]
        nohold_pnl = nohold_result["pnl"]
        delta = hold_pnl - nohold_pnl
        if delta > 0:
            print(f"  ✅ 1-Hour Hold Rule:  +${delta:.2f} improvement (hold=${hold_pnl:.2f} vs no-hold=${nohold_pnl:.2f})")
        elif delta < 0:
            print(f"  ⚠️ 1-Hour Hold Rule:  -${abs(delta):.2f} WORSE with hold (hold=${hold_pnl:.2f} vs no-hold=${nohold_pnl:.2f})")
        else:
            print(f"  ℹ️ 1-Hour Hold Rule:  No difference (both ${hold_pnl:.2f})")
    elif hold_result and nohold_result:
        print(f"  ℹ️ 1-Hour Hold Rule:  Cannot compare (error in one or both tests)")

    # Compare counter-trend blocking
    ct_on = next((r for r in results if "CounterTrend" in r["name"]), None)
    ct_off = hold_result  # Standard SND = counter-trend blocked

    if ct_on and ct_off and not ct_on.get("error") and not ct_off.get("error"):
        ct_on_pnl = ct_on["pnl"]
        ct_off_pnl = ct_off["pnl"]
        ct_on_trades = ct_on["total_trades"]
        ct_off_trades = ct_off["total_trades"]
        print(f"  {'✅' if ct_off_pnl >= ct_on_pnl else '⚠️'} Counter-Trend Block: "
              f"blocked=${ct_off_pnl:.2f} ({ct_off_trades}t) vs allowed=${ct_on_pnl:.2f} ({ct_on_trades}t)")

    # Exit reason audit
    print(f"\n{'─' * 80}")
    print("EXIT REASON AUDIT (are SL/TP working?)")
    print(f"{'─' * 80}")

    for r in results:
        if r.get("error") or r.get("total_trades", 0) == 0:
            continue
        reasons = r.get("exit_reasons", {})
        sltp = reasons.get("stop", 0) + reasons.get("target", 0)
        total = r["total_trades"]
        sltp_pct = sltp / total * 100 if total else 0
        signal_pct = reasons.get("signal", 0) / total * 100 if total else 0
        eod_pct = reasons.get("eod", 0) / total * 100 if total else 0

        name = r["name"][:30]
        parts = f"SL/TP={sltp_pct:.0f}%"
        if "signal" in reasons:
            parts += f" Signal={signal_pct:.0f}%"
        if "eod" in reasons:
            parts += f" EOD={eod_pct:.0f}%"
        print(f"  {name:<30} {parts}")

    # Trade detail
    print(f"\n{'─' * 80}")
    print("TRADE DETAIL (direction, duration, TP/SL split)")
    print(f"{'─' * 80}")
    print(f"  {'Name':<30} {'L/S':>7}  {'TP':>4} {'SL':>4} {'Other':>5}  {'AvgHold':>8} {'MinHold':>8} {'MaxHold':>8}")
    print("  " + "─" * 88)
    for r in results:
        if r.get("error") or r.get("total_trades", 0) == 0:
            continue
        name = r["name"][:29]
        ls = f"{r.get('longs',0)}L/{r.get('shorts',0)}S"
        tp = r.get("tp_hits", 0)
        sl = r.get("sl_hits", 0)
        other = r["total_trades"] - tp - sl
        avg_h = f"{r.get('avg_hold_min', 0):.0f}m"
        min_h = f"{r.get('min_hold_min', 0):.0f}m"
        max_h = f"{r.get('max_hold_min', 0):.0f}m"
        print(f"  {name:<30} {ls:>7}  {tp:>4} {sl:>4} {other:>5}  {avg_h:>8} {min_h:>8} {max_h:>8}")

    # Fee impact
    print(f"\n{'─' * 80}")
    print("FEE IMPACT (spread + maker/taker costs)")
    print(f"{'─' * 80}")
    for r in results:
        if r.get("error") or r.get("total_trades", 0) == 0:
            continue
        name = r["name"][:30]
        fees = r.get("total_fees", 0)
        pnl = r.get("pnl", 0)
        pnl_before_fees = pnl + fees
        impact = (fees / pnl_before_fees * 100) if pnl_before_fees != 0 else 0
        print(f"  {name:<30} Fees=${fees:>10.2f}  Net P&L=${pnl:>12.2f}  Impact={impact:>5.1f}%")

    # Hold guard audit
    print(f"\n{'─' * 80}")
    print("HOLD GUARD AUDIT (are premature exits blocked?)")
    print(f"{'─' * 80}")
    for r in results:
        if r.get("error") or r.get("total_trades", 0) == 0:
            continue
        early_bad = r.get("early_non_sltp_exits", 0)
        early_good = r.get("early_sltp_exits", 0)
        name = r["name"][:30]
        if early_bad > 0:
            print(f"  ❌ {name:<28} {early_bad} premature non-SL/TP exits LEAKED through hold guard!")
        else:
            print(f"  ✅ {name:<28} Hold guard intact (early SL/TP: {early_good})")


    # Final verdict
    print(f"\n{'=' * 80}")
    non_control = [r for r in results if "control" not in r.get("name", "").lower() and not r.get("error") and r.get("total_trades", 0) > 0]
    passes = sum(1 for r in non_control if grade_result(r).startswith("✅"))
    fails = sum(1 for r in non_control if grade_result(r).startswith("❌"))
    warns = sum(1 for r in non_control if grade_result(r).startswith("⚠"))
    no_trades = sum(1 for r in results if r.get("total_trades", 0) == 0 and not r.get("error"))
    errors = sum(1 for r in results if r.get("error"))

    print(f"  VERDICT: {passes} PASS | {warns} MARGINAL | {fails} FAIL | {no_trades} NO TRADES | {errors} ERROR")
    if fails > 0:
        print(f"  ⚠️ ACTION REQUIRED: {fails} configurations lost money with 'correct' settings")
    elif passes > 0:
        print(f"  🎯 Bot produces profits when correctly configured!")
    print("=" * 80)

    return fails == 0


def main():
    parser = argparse.ArgumentParser(description="Profit Audit Tool")
    parser.add_argument("--market", choices=["forex", "crypto", "hybrid", "all"], default="all",
                        help="Market type to audit")
    parser.add_argument("--strategy", type=str, default=None,
                        help="Specific strategy to audit")
    parser.add_argument("--days", type=int, default=7,
                        help="Number of days to backtest (default: 7)")
    parser.add_argument("--capital", type=float, default=2000.0,
                        help="Starting capital")
    parser.add_argument("--skip-forward", action="store_true",
                        help="Skip forward tester strategy audit")
    parser.add_argument("--forward-only", action="store_true",
                        help="Run only forward tests, no backtests")
    args = parser.parse_args()

    # ── Phase 1: Forward Tests (all strategies) ──────────────────────────────
    if not args.skip_forward:
        print("\n" + "=" * 60)
        print("  PHASE 1: FORWARD TESTER — STRATEGY AUDIT")
        print("  Testing all strategies for load, decisions, hold guard...")
        print("=" * 60)
        fwd_results = run_forward_tests()
        print_forward_report(fwd_results)
        if args.forward_only:
            return

    # ── Phase 2: Backtest Audit ──────────────────────────────────────────────
    # Filter audit matrix
    matrix = AUDIT_MATRIX
    if args.market != "all":
        matrix = [m for m in matrix if m[3] in (args.market, "control")]
    if args.strategy:
        matrix = [m for m in matrix if args.strategy.lower() in m[1].get("strategy_variant", "").lower()]

    if not matrix:
        print("No tests match the filter criteria.")
        return

    # Time period: recent N days
    end_date = datetime.now(tz=timezone.utc).replace(minute=0, second=0, microsecond=0)
    start_date = end_date - timedelta(days=args.days)

    print("\n" + "=" * 60)
    print("  PHASE 2: BACKTEST PROFIT AUDIT")
    print(f"  Period: {start_date.date()} to {end_date.date()} ({args.days} days)")
    print(f"  Capital: ${args.capital:.0f}")
    print(f"  Tests: {len(matrix)}")
    print("=" * 60)

    results = []
    for i, (name, profile, symbols, market_type) in enumerate(matrix, 1):
        print(f"\n[{i}/{len(matrix)}] Running: {name}...")
        profile["data_dir_name"] = "audit"
        r = run_single_backtest(name, profile, symbols, start_date, end_date, args.capital)
        results.append(r)
        grade = grade_result(r, is_control=(market_type == "control"))
        print(f"  → {grade}  Trades={r.get('total_trades', 0)}  P&L=${r.get('pnl', 0):.2f}")

    print_report(results, capital=args.capital)

    # Save results
    out_dir = os.path.join(os.path.dirname(__file__), "../data")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "profit_audit_results.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n📊 Full results saved to: {os.path.abspath(out_path)}")


if __name__ == "__main__":
    main()
