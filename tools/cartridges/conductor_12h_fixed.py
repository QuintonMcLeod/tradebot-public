"""12-hour backtest — today's session with fixed code.
Uses oanda_12h data (Feb 26 - Mar 2 09:45 UTC).
Tests today's window: March 2, 01:00-09:45 UTC (with warmup from prior days).
"""
from datetime import datetime, timezone

class TradingProfileSettings(dict):
    def __getattr__(self, item): return self.get(item)
    def __setattr__(self, key, value): self[key] = value

def get_config():
    # Today 01:00 UTC to 09:45 UTC (end of available data)
    start_date = datetime(2026, 3, 2, 1, 0, 0, tzinfo=timezone.utc)
    end_date = datetime(2026, 3, 2, 9, 45, 0, tzinfo=timezone.utc)
    
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
        risk_per_trade_pct=0.045,       # 4.5% risk (matches live)
        max_concurrent_positions=6,
        multi_position_enabled=True,
        max_pyramid_entries=1,           # Session 2ca3c3ed fix
        market_poll_interval_seconds=15,
        ai_decision_interval_seconds=60,
        icc_entry_score_threshold=60.0,
        stop_and_reverse_enabled=True,
        reversal_tp_r=1.0,
        reversal_risk_per_trade=0.01,    # SAR at 1% (session 2ca3c3ed fix)
        reversal_cost_aware_tp=True,
        min_hold_hours=0.08,
        max_hold_hours=0,
        htf_neutral_exit_bars=0,
        scale_out_fraction=0.95,
        guillotine_r_threshold=-0.6,     # Session 2ca3c3ed fix
        # Trend indicator toggles
        trend_adx_enabled=True,
        trend_ema_ribbon_enabled=True,
        trend_supertrend_enabled=False,
        trend_macd_enabled=True,
        trend_rsi_enabled=True,
        trend_bollinger_enabled=False,
        trend_ichimoku_enabled=False,
        trend_parabolic_sar_enabled=False,
        trend_vwap_enabled=False,
        trend_hull_ma_enabled=False,
        adx_gate_threshold=12,
        trend_chop_threshold=8,
        block_counter_trend_entries=True,
        structure_score_threshold=0.0,
        consecutive_loss_cooldown_bars=4,
        consecutive_loss_threshold=2,
    )
    
    return {
        "profile_settings": profile,
        "symbols": [
            "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "NZDUSD",
            "USDCAD", "USDCHF", "EURJPY", "GBPJPY", "AUDJPY",
        ],
        "start_date": start_date,
        "end_date": end_date,
        "initial_capital": 3290.0,      # Current live capital
        "data_dir_name": "oanda_12h",
        "force_market_open": True,
        "runtime_settings": {
            "scale_out_fraction": 0.95,
        },
    }

def apply_overrides():
    print("[Cartridge] Running 12h live comparison (all 10 pairs, today, with cache fix)")
