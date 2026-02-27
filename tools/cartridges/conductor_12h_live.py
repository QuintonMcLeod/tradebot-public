"""12-hour backtest — replicates the live bot's window (today).
Uses 3 days of OANDA data for indicator warmup, entries only today.
"""
from datetime import datetime, timezone

class TradingProfileSettings(dict):
    def __getattr__(self, item): return self.get(item)
    def __setattr__(self, key, value): self[key] = value

def get_config():
    start_date = datetime(2026, 2, 27, 0, 0, 0, tzinfo=timezone.utc)
    end_date = datetime(2026, 2, 27, 23, 59, 0, tzinfo=timezone.utc)
    
    profile = TradingProfileSettings(
        strategy_variant="forex_conductor",
        candle_timeframe="15m",
        htf_timeframe="15m", 
        ltf_timeframe="5m",
        trend_window=12,
        ltf_trend_window=8,
        trend_swing_lookback=2,
        trend_min_swings=2,
        trend_strength_floor=0.25,
        risk_per_trade_pct=0.01,
        max_concurrent_positions=6,
        multi_position_enabled=True,
        max_pyramid_entries=50,
        market_poll_interval_seconds=15,
        ai_decision_interval_seconds=60,
        icc_entry_score_threshold=60.0,
        stop_and_reverse_enabled=True,
        reversal_tp_r=1.0,
        reversal_risk_per_trade=0.045,
        reversal_cost_aware_tp=True,
        min_hold_hours=0.08,
        max_hold_hours=0,
        htf_neutral_exit_bars=0,
        scale_out_fraction=0.95,
    )
    
    return {
        "profile_settings": profile,
        "symbols": ["EURUSD", "GBPUSD"],
        "start_date": start_date,
        "end_date": end_date,
        "initial_capital": 7500.0,
        "data_dir_name": "oanda_12h",
        "force_market_open": True,
        "runtime_settings": {
            "scale_out_fraction": 0.95,
        },
    }

def apply_overrides():
    print("[Cartridge] Running 12h live comparison (EURUSD + GBPUSD, today)")
