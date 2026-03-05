"""Injectable state container for SafetyGuard.

Replaces the 12 class-level mutable dicts/lists with a single injectable
dataclass, making SafetyGuard testable without leaking state between tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class SafetyState:
    """Consolidated mutable state for the SafetyGuard system."""

    # Global State for Safety Measures (Isolated per Asset Class)
    hwm_capital: dict = field(default_factory=dict)            # {AssetClass: float}
    drawdown_pause_until: dict = field(default_factory=dict)   # {AssetClass: datetime}

    # State Tracking (Isolated per Asset Class)
    daily_start_capital: dict = field(default_factory=dict)    # {AssetClass: float}
    daily_pnl: dict = field(default_factory=dict)              # {AssetClass: float}
    weekly_start_capital: dict = field(default_factory=dict)   # {AssetClass: float}
    weekly_pnl: dict = field(default_factory=dict)             # {AssetClass: float}
    monthly_start_capital: dict = field(default_factory=dict)  # {AssetClass: float}
    monthly_pnl: dict = field(default_factory=dict)            # {AssetClass: float}
    last_reset_date: dict = field(default_factory=dict)        # {AssetClass: date}
    last_reset_week: dict = field(default_factory=dict)        # {AssetClass: (year, week)}
    last_reset_month: dict = field(default_factory=dict)       # {AssetClass: (year, month)}

    # Per-Symbol State
    symbol_loss_streaks: dict = field(default_factory=dict)    # {symbol: count}
    symbol_pause_until: dict = field(default_factory=dict)     # {symbol: datetime}
    symbol_exit_cooldown: dict = field(default_factory=dict)   # {symbol: datetime}
    regime_flip_cooldown: dict = field(default_factory=dict)   # {symbol: datetime} — prevents re-entry after regime flip

    # Rate Limiting & Caching
    trade_timestamps: dict = field(default_factory=dict)       # {AssetClass: list[datetime]}
    sentiment_cache: dict = field(default_factory=dict)        # {AssetClass: {symbol: (ts, val)}}
    win_rate: dict = field(default_factory=dict)               # {AssetClass: float}
    open_positions: list = field(default_factory=list)          # Legacy list of position dicts

    # Global Position Registry
    global_positions: dict = field(default_factory=dict)       # {symbol: position_dict}

    def reset(self) -> None:
        """Clear all mutable state — useful for tests and resets."""
        for f in self.__dataclass_fields__:
            val = getattr(self, f)
            if isinstance(val, dict):
                val.clear()
            elif isinstance(val, list):
                val.clear()
