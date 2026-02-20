"""
Intraday Backtest: Feb 19, 2026 12:54 PM - 3:41 PM EST
Purpose: Compare normal vs reversed trade direction experiment.
Uses 1m candles with auto-download from Kraken via CCXT.
"""
from datetime import datetime, timezone

# Helper to allow dot notation
class TradingProfileSettings(dict):
    def __getattr__(self, item): return self.get(item)
    def __setattr__(self, key, value): self[key] = value

def get_config():
    # 12:54 PM EST = 17:54 UTC, 3:41 PM EST = 20:41 UTC
    # Need warmup candles for trend calc, start from 14:00 UTC (9:00 AM EST)
    start_date = datetime(2026, 2, 19, 17, 54, 0, tzinfo=timezone.utc)
    end_date = datetime(2026, 2, 19, 20, 41, 0, tzinfo=timezone.utc)

    # Match the bot's live forex profile
    profile = TradingProfileSettings(
        strategy_variant="supply_demand",
        candle_timeframe="1m",
        htf_timeframe="15m",
        ltf_timeframe="1m",
        trend_window=12,
        ltf_trend_window=8,
        trend_swing_lookback=2,
        trend_min_swings=2,
        trend_strength_floor=0.25,
        risk_per_trade_pct=0.04,
        max_concurrent_positions=6,
        multi_position_enabled=True,
        max_pyramid_entries=4,
        market_poll_interval_seconds=60,
        ai_decision_interval_seconds=60,
        icc_entry_score_threshold=60.0
    )

    return {
        "profile_settings": profile,
        "symbols": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "AUDJPY", "NZDUSD", "USDCAD"],
        "start_date": start_date,
        "end_date": end_date,
        "initial_capital": 68.0,  # Match current OANDA balance
        "data_dir_name": "intraday_backtest",
        "force_market_open": True
    }

def apply_overrides():
    print("[Cartridge] Running Intraday Feb 19 Direction Experiment Backtest...")
