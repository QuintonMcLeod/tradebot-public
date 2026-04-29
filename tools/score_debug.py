#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from tradebot_sci.ai.client import TradeSciAIClient
from tradebot_sci.config.loader import load_settings
from tradebot_sci.runtime.provider_factory import build_market_provider
from tradebot_sci.strategy.engine import StrategyEngine
from tradebot_sci.strategy.profiles import BaseProfile


def main() -> int:
    parser = argparse.ArgumentParser(description="Debug ICC selection_score/readiness for symbols.")
    parser.add_argument(
        "--symbols",
        default=os.getenv("SCORE_DEBUG_SYMBOLS", "BTCUSD,ETHUSD,SOLUSD"),
        help="Comma-separated symbols to inspect.",
    )
    parser.add_argument(
        "--timeframe",
        default=os.getenv("SCORE_DEBUG_TF", ""),
        help="Timeframe override (default: profile candle timeframe).",
    )
    args = parser.parse_args()

    settings = load_settings()
    profile_settings = settings.get_active_profile()
    profile = BaseProfile(
        name=settings.app.profile_name,
        candle_timeframe=profile_settings.candle_timeframe,
        market_poll_interval_seconds=profile_settings.market_poll_interval_seconds,
        ai_decision_interval_seconds=profile_settings.ai_decision_interval_seconds,
    )
    timeframe = args.timeframe.strip() or profile.candle_timeframe

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if not symbols:
        print("No symbols provided.", file=sys.stderr)
        return 1

    shared_ib = None
    if settings.market.exchange_provider == "primary":
        try:
            from tradebot_sci.runtime.loop import _maybe_connect_primary_ib  # type: ignore

            shared_ib = _maybe_connect_primary_ib(settings, execute_trades=True)
        except Exception as exc:
            print(f"IBKR connect failed: {exc}", file=sys.stderr)
            return 2

    provider = build_market_provider(settings, shared_ib=shared_ib)
    ai_client = TradeSciAIClient(settings.ai)

    try:
        from tradebot_sci.runtime.cycle import fetch_snapshot  # type: ignore
    except Exception as exc:
        print(f"Unable to import snapshot fetcher: {exc}", file=sys.stderr)
        return 3

    cache: dict[tuple, object] = {}
    results: list[dict[str, Any]] = []
    for symbol in symbols:
        engine = StrategyEngine(ai_client=ai_client, market_provider=provider, profile=profile, symbol=symbol)
        snapshot = fetch_snapshot(provider, cache, symbol, timeframe, profile_settings, settings.market)
        score, reason = engine.score_structure(snapshot)
        readiness, readiness_reason = engine.score_icc_readiness(snapshot)
        results.append(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "selection_score": round(float(score), 3),
                "selection_reason": reason,
                "readiness": round(float(readiness), 2),
                "readiness_reason": readiness_reason,
                "trend_htf": {
                    "direction": snapshot.trend_htf.direction,
                    "strength": round(float(snapshot.trend_htf.strength), 3),
                    "swings": snapshot.trend_htf.last_confirmed_swings,
                    "key_levels": snapshot.trend_htf.key_levels,
                },
                "trend_ltf": {
                    "direction": snapshot.trend_ltf.direction,
                    "strength": round(float(snapshot.trend_ltf.strength), 3),
                    "swings": snapshot.trend_ltf.last_confirmed_swings,
                    "key_levels": snapshot.trend_ltf.key_levels,
                },
            }
        )

    print(json.dumps({"symbols": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
