"""Backtest cartridge: Today's live trades window (13:45-14:20 EST / 18:45-19:20 UTC).
Fetches fresh data from OANDA, then runs the backtest.
Uses the full code with all pipeline fixes applied.

IMPORTANT: Timeframes MUST match the live bot's defaults:
  - candle_timeframe: 5m  (TradingProfileSettings default)
  - htf_timeframe:    4h  (TradingProfileSettings default)
  - ltf_timeframe:    None -> falls back to candle_timeframe (5m)
"""
from datetime import datetime, timezone

class TradingProfileSettings(dict):
    def __getattr__(self, item): return self.get(item)
    def __setattr__(self, key, value): self[key] = value

def get_config():
    # Narrowed window: exact period the live bot was trading
    # GBPUSD 18:45, EURUSD 18:52, USDCAD 19:18 UTC
    start_date = datetime(2026, 3, 2, 18, 45, 0, tzinfo=timezone.utc)
    end_date = datetime(2026, 3, 2, 19, 30, 0, tzinfo=timezone.utc)
    
    profile = TradingProfileSettings(
        strategy_variant="forex_conductor",
        # ── Timeframes: MUST match live bot defaults ──────────────
        candle_timeframe="5m",          # Live default
        htf_timeframe="4h",             # Live default (was wrong: 15m)
        ltf_timeframe=None,             # Live default (falls back to 5m)
        trend_window=18,                # Live default (was wrong: 12)
        ltf_trend_window=None,          # Live default
        trend_swing_lookback=2,
        trend_min_swings=2,
        trend_strength_floor=0.3,       # Live default (was wrong: 0.25)
        risk_per_trade_pct=0.045,       # 4.5% risk (matches live)
        max_concurrent_positions=6,
        multi_position_enabled=True,
        max_pyramid_entries=1,
        market_poll_interval_seconds=15,
        ai_decision_interval_seconds=60,
        icc_entry_score_threshold=60.0,
        stop_and_reverse_enabled=True,
        reversal_tp_r=1.0,
        reversal_risk_per_trade=0.01,
        reversal_cost_aware_tp=True,
        min_hold_hours=0.08,
        max_hold_hours=0,
        htf_neutral_exit_bars=0,
        scale_out_fraction=0.95,
        guillotine_r_threshold=-0.6,
        # Trend indicator toggles (match live config)
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
        "initial_capital": 3290.0,
        "data_dir_name": "oanda_livetrades",
        "force_market_open": True,
        "runtime_settings": {
            "scale_out_fraction": 0.95,
        },
    }

def apply_overrides():
    print("[Cartridge] Running live-trade window backtest (18:45-19:30 UTC, all 10 pairs)")
