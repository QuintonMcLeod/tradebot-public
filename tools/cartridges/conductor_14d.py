"""14-day conductor backtest with relaxed params.

This is a calibration cartridge to produce real trades. It matches a
near-live configuration with looser filters vs the config.json defaults.

Key relaxations (vs the too-strict config.json profile):
- adx_gate_threshold: 20 → 12  (allows transitional/ranging markets to trade)
- trend_strength_floor: 0.5 → 0.25  (weaker HTF signal is still acceptable)
- force_market_open: True  (removes session lockout for EURUSD/GBPUSD)
- trend_supertrend_enabled: True  (extra trend vote to help disambiguate ranging vs trending)
"""
from datetime import datetime, timezone
from pathlib import Path

DATA_BASE = Path(__file__).resolve().parents[2] / "data"


class TradingProfileSettings(dict):
    def __getattr__(self, item): return self.get(item)
    def __setattr__(self, key, value): self[key] = value


def get_config():
    start_date = datetime(2026, 2, 19, 0, 0, 0, tzinfo=timezone.utc)
    end_date   = datetime(2026, 3, 5, 23, 59, 59, tzinfo=timezone.utc)

    profile = TradingProfileSettings(
        strategy_variant="forex_conductor",
        candle_timeframe="5m",
        htf_timeframe="4h",
        ltf_timeframe="5m",
        trend_window=14,
        ltf_trend_window=8,
        trend_swing_lookback=3,
        trend_min_swings=2,
        trend_strength_floor=0.25,   # relaxed from 0.5
        # Risk
        risk_per_trade_pct=1.0,
        max_concurrent_positions=2,
        multi_position_enabled=True,
        max_pyramid_entries=50,
        pyramid_profit_buffer_pct=0.5,
        pyramid_risk_load=30,
        pyramid_risk_scale=4,
        breakeven_trail_after_pyramids=1,
        stop_atr_multiplier=1.5,
        scale_out_fraction=0.95,
        guillotine_r_threshold=-0.3,
        # SAR
        stop_and_reverse_enabled=True,
        reversal_tp_r=1.0,
        reversal_risk_per_trade=0.027,
        reversal_cost_aware_tp=True,
        # Timing
        min_hold_hours=0.08,
        max_hold_hours=12,
        htf_neutral_exit_bars=0,
        # Trend filters — relaxed
        trend_adx_enabled=True,
        adx_gate_threshold=12,           # relaxed from 20
        trend_ema_ribbon_enabled=True,
        trend_supertrend_enabled=True,   # extra vote for disambiguation
        trend_macd_enabled=True,
        trend_rsi_enabled=True,
        trend_bollinger_enabled=False,
        trend_ichimoku_enabled=False,
        trend_parabolic_sar_enabled=False,
        trend_vwap_enabled=False,
        trend_hull_ma_enabled=False,
        trend_chop_threshold=6,          # relaxed from 8
        block_counter_trend_entries=True,
        structure_score_threshold=0.0,
        consecutive_loss_cooldown_bars=4,
        consecutive_loss_threshold=3,    # relaxed from 2
        # Safety guards (kept live-match)
        safety_drawdown_breaker_enabled=True,
        safety_drawdown_max_pct=0.1,
        safety_streak_breaker_enabled=True,
        safety_atr_shield_enabled=True,
        safety_regime_flip_enabled=False,
    )

    return {
        "profile_settings": profile,
        "symbols": ["EURUSD", "GBPUSD"],
        "start_date": start_date,
        "end_date": end_date,
        "initial_capital": 5500.0,       # approximate live NAV
        "data_dir_name": "forex_backtest",
        "force_market_open": True,        # bypass Asian session block
        "htf_data_paths": {
            "EURUSD": str(DATA_BASE / "forex_backtest" / "EURUSD_4h.json"),
            "GBPUSD": str(DATA_BASE / "forex_backtest" / "GBPUSD_4h.json"),
        },
    }


def apply_overrides():
    print("[Cartridge] 14-day conductor backtest — relaxed filters")
