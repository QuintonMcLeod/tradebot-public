"""
14-Day All-Symbol Conductor Backtest
=====================================
Runs all 12 symbols from the forex_continuous live profile.
Risk = 4.5%, Guillotine at -0.3R, SAR enabled (chain guard = 1),
Counter-Reversal (CR) enabled — fires back to original direction after SAR failure.
"""
from datetime import datetime, timezone
from pathlib import Path

DATA_BASE = Path(__file__).resolve().parents[2] / "data"
_forex = DATA_BASE / "forex_backtest"


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

        # ── Risk ─────────────────────────────────────────────────────
        risk_per_trade_pct=0.045,
        max_concurrent_positions=5,
        multi_position_enabled=True,
        max_pyramid_entries=3,
        stop_atr_multiplier=1.5,
        scale_out_fraction=0.95,
        target_risk_multiplier=3.0,

        # ── Loss-cap ─────────────────────────────────────────────────
        guillotine_r_threshold=-0.3,
        stop_and_reverse_enabled=True,
        reversal_tp_r=1.0,
        reversal_cost_aware_tp=True,
        max_consecutive_sar=1,
        # Counter-Reversal: fires back to original direction after SAR failure
        counter_reversal_enabled=True,
        counter_reversal_tp_r=1.0,
        max_consecutive_cr=1,

        # ── Timing ───────────────────────────────────────────────────
        min_hold_hours=0.08,
        max_hold_hours=12,
        htf_neutral_exit_bars=0,

        # ── Trend filters ─────────────────────────────────────────────
        trend_adx_enabled=True,
        adx_gate_threshold=12,
        trend_ema_ribbon_enabled=True,
        trend_supertrend_enabled=True,
        trend_macd_enabled=True,
        trend_rsi_enabled=True,
        trend_bollinger_enabled=False,
        trend_ichimoku_enabled=False,
        trend_parabolic_sar_enabled=False,
        trend_vwap_enabled=False,
        trend_hull_ma_enabled=False,
        trend_chop_threshold=6,
        block_counter_trend_entries=True,
        structure_score_threshold=0.0,
        consecutive_loss_cooldown_bars=4,
        consecutive_loss_threshold=3,

        # ── Safety guards ─────────────────────────────────────────────
        safety_drawdown_breaker_enabled=True,
        safety_drawdown_max_pct=0.1,
        safety_streak_breaker_enabled=True,
        safety_atr_shield_enabled=True,
        safety_regime_flip_enabled=False,
    )

    # All 12 symbols from forex_continuous profile
    symbols = [
        "EURUSD", "GBPUSD", "USDJPY", "AUDUSD",
        "USDCAD", "USDCHF", "NZDUSD", "EURJPY",
        "GBPJPY", "AUDJPY", "XAUUSD", "WTICOUSD",
    ]

    # Native 4H candles for HTF strength accuracy
    htf_data_paths = {
        sym: str(_forex / f"{sym}_4h.json")
        for sym in symbols
        if (_forex / f"{sym}_4h.json").exists()
    }

    return {
        "profile_settings": profile,
        "symbols": symbols,
        "start_date": start_date,
        "end_date": end_date,
        "initial_capital": 5500.0,
        "data_dir_name": "forex_backtest",
        "force_market_open": True,
        "htf_data_paths": htf_data_paths,
        "warmup_days": 7,
    }


def apply_overrides():
    print("[Cartridge] All-symbol 14-day conductor — 12 FX pairs, 4.5% risk, Guillotine+SAR+CR")
