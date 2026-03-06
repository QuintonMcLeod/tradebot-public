"""
Loss-Cap Validation Cartridge
==============================
PURPOSE: Confirm that Guillotine (-0.3R early cut) and SAR (stop-and-reverse)
correctly limit max loss per trade to approximately 4.5% of capital (~$200-250
on a $5,500 account).

Focus on EXIT behavior:
  - No single loss should exceed ~$250 (4.5% of starting capital)
  - Guillotine should fire at approximately -0.3R unrealized
  - SAR should reverse direction on stop hit

Run with:
    PYTHONPATH=src python3 tools/mega_backtester.py loss_cap_validation
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
        trend_strength_floor=0.25,

        # ── RISK: match live 4.5% ────────────────────────────────────
        risk_per_trade_pct=0.045,          # live profile value
        max_concurrent_positions=2,
        multi_position_enabled=True,
        max_pyramid_entries=3,
        stop_atr_multiplier=1.5,
        scale_out_fraction=0.95,
        target_risk_multiplier=3.0,

        # ── LOSS-CAP MECHANISMS — MUST BE ON ────────────────────────
        guillotine_r_threshold=-0.3,       # Cut at -0.3R unrealized
        stop_and_reverse_enabled=True,     # SAR: reverse on stop-out
        reversal_tp_r=1.0,
        reversal_risk_per_trade=0.045,     # SAR same risk as entry
        reversal_cost_aware_tp=True,

        # ── Timing ───────────────────────────────────────────────────
        min_hold_hours=0.08,
        max_hold_hours=12,
        htf_neutral_exit_bars=0,

        # ── Trend filters — permissive so we get entries to test exits ─
        trend_adx_enabled=True,
        adx_gate_threshold=10,
        trend_ema_ribbon_enabled=True,
        trend_supertrend_enabled=True,
        trend_macd_enabled=True,
        trend_rsi_enabled=True,
        trend_bollinger_enabled=False,
        trend_ichimoku_enabled=False,
        trend_parabolic_sar_enabled=False,
        trend_vwap_enabled=False,
        trend_hull_ma_enabled=False,
        trend_chop_threshold=5,
        block_counter_trend_entries=True,
        structure_score_threshold=0.0,

        # ── Safety guards ────────────────────────────────────────────
        safety_drawdown_breaker_enabled=True,
        safety_drawdown_max_pct=0.1,
        safety_streak_breaker_enabled=True,
        safety_atr_shield_enabled=True,
        safety_regime_flip_enabled=False,  # disabled per user req
    )

    return {
        "profile_settings": profile,
        "symbols": ["EURUSD", "GBPUSD"],
        "start_date": start_date,
        "end_date": end_date,
        "initial_capital": 5500.0,
        "data_dir_name": "forex_backtest",
        "force_market_open": True,         # bypass Asian session block
        "htf_data_paths": {
            "EURUSD": str(DATA_BASE / "forex_backtest" / "EURUSD_4h.json"),
            "GBPUSD": str(DATA_BASE / "forex_backtest" / "GBPUSD_4h.json"),
        },
    }


def apply_overrides():
    print("[Cartridge] Loss-cap validation — 4.5% risk, Guillotine @ -0.3R, SAR enabled")
