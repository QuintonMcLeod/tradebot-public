"""2-Week ALL-PAIR Forex Backtest — $30 start capital — META-SCI.

Meta-SCI tournament picks the best strategy per symbol per cycle.
Testing all 10 forex pairs.
"""
from datetime import datetime, timezone


class TradingProfileSettings(dict):
    def __getattr__(self, item): return self.get(item)
    def __setattr__(self, key, value): self[key] = value


def get_config():
    start_date = datetime(2026, 1, 15, 22, 0, 0, tzinfo=timezone.utc)
    end_date = datetime(2026, 1, 29, 22, 0, 0, tzinfo=timezone.utc)

    profile = TradingProfileSettings(
        strategy_variant="meta_sci",
        candle_timeframe="15m",
        htf_timeframe="15m",
        ltf_timeframe="5m",
        trend_window=12,
        ltf_trend_window=8,
        trend_swing_lookback=2,
        trend_min_swings=2,
        trend_strength_floor=0.25,
        risk_per_trade_pct=0.05,
        max_concurrent_positions=10,
        multi_position_enabled=True,
        max_pyramid_entries=3,
        market_poll_interval_seconds=15,
        ai_decision_interval_seconds=60,
        icc_entry_score_threshold=60.0,
    )

    return {
        "profile_settings": profile,
        "symbols": [
            "EURUSD", "GBPUSD", "USDJPY", "AUDUSD",
            "USDCAD", "USDCHF", "NZDUSD",
            "GBPJPY", "EURJPY", "AUDJPY",
        ],
        "start_date": start_date,
        "end_date": end_date,
        "initial_capital": 30.0,
        "data_dir_name": "marathon_30d",
        "force_market_open": True,
    }


def apply_overrides():
    print("[Cartridge] 2-Week ALL-PAIR Meta-SCI @ $30...")
