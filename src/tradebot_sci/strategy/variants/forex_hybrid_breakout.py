from __future__ import annotations
import logging
from typing import Optional

from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.strategy.icc_signals import calculate_atr

logger = logging.getLogger(__name__)


class ForexHybridBreakout(BaseStrategy):
    """
    Forex Hybrid Breakout — pure breakout strategy.

    Enters LONG when price breaks above the recent structure high
    by breakout_distance_pct percent.
    Enters SHORT when price breaks below the recent structure low
    by breakout_distance_pct percent.

    Uses the same stop-loss, take-profit, position sizing and risk
    management as ForexHybridReaper.
    """

    score_threshold = 60.0
    SESSION_PROFILE = [
        "forex_hybrid_scalper:hybrid_overlap",
        "forex_hybrid_scalper:london_open",
        "forex_hybrid_scalper:asian_open",
    ]

    def __init__(self, target_r=1.0, **kwargs):
        super().__init__("ForexHybridBreakout")
        self.target_r = target_r

        # Breakout distance as % of price (default 0.5)
        self.breakout_distance_pct = float(kwargs.get("breakout_distance_pct", 0.5))

        # Stop / target parameters (mirrors reaper trend-mode defaults)
        self.trend_stop_atr_mult = float(kwargs.get("trend_stop_atr_mult", 2.5))
        self.trend_stop_floor = float(kwargs.get("trend_stop_floor", 0.0020))
        self.trend_target_r = float(kwargs.get("trend_target_r", 4.0))

        # Minimum ATR to allow a trade (volatility guard)
        self.min_atr = float(kwargs.get("min_atr", 0.0))

        logger.debug(
            f"Loaded ForexHybridBreakout breakout_distance_pct={self.breakout_distance_pct}"
        )

    def score_signal(self, snapshot: MarketSnapshot, gates: dict, regime: str | None = None) -> tuple[float, str, str]:
        """Breakout always scores 100 when a setup is present — the breakout itself is the edge."""
        return 100.0, "A+", f"Breakout[{self.breakout_distance_pct:.2f}%]: A+"

    def check_entry_signal(self, snapshot: MarketSnapshot, gates: dict, open_position: Optional[dict] = None, **kwargs) -> Optional[AITradeDecision]:
        if gates.get("is_synthetic_override") is True:
            return None

        candles = snapshot.candles
        if len(candles) < 6:
            return None

        # Volatility guard
        current_atr = calculate_atr(candles, period=14)
        if not current_atr or current_atr <= 0:
            return None
        if self.min_atr > 0 and current_atr < self.min_atr:
            return None

        last_close = candles[-1].close

        if open_position:
            return None

        # Recent structure: last 5 completed candles
        recent_high = max(c.high for c in candles[-6:-1])
        recent_low = min(c.low for c in candles[-6:-1])
        breakout_dist = last_close * self.breakout_distance_pct / 100.0

        current_high = candles[-1].high
        current_low = candles[-1].low

        # LONG breakout
        if current_high > recent_high + breakout_dist:
            stop_loss = recent_low - current_atr * 0.5
            stop_loss = min(stop_loss, last_close - current_atr * self.trend_stop_atr_mult)
            stop_loss = min(stop_loss, last_close - last_close * self.trend_stop_floor)
            target = last_close + (last_close - stop_loss) * self.trend_target_r

            return AITradeDecision(
                symbol=snapshot.symbol,
                timeframe=snapshot.timeframe,
                bias="long",
                phase="continuation",
                action="enter_long",
                entry_price=last_close,
                stop_loss=stop_loss,
                take_profit=target,
                risk_per_trade_pct=self.get_risk_pct(),
                structure_summary=f"Breakout Long (dist={self.breakout_distance_pct:.2f}%, high={recent_high:.5f})",
                invalidation_conditions="Close below stop loss.",
                management_instructions=f"Breakout mode. Target {self.trend_target_r}R.",
                urgency="high",
                strategy_name=self.name,
                regime="trend",
            )

        # SHORT breakout
        if current_low < recent_low - breakout_dist:
            stop_loss = recent_high + current_atr * 0.5
            stop_loss = max(stop_loss, last_close + current_atr * self.trend_stop_atr_mult)
            stop_loss = max(stop_loss, last_close + last_close * self.trend_stop_floor)
            target = last_close - (stop_loss - last_close) * self.trend_target_r

            return AITradeDecision(
                symbol=snapshot.symbol,
                timeframe=snapshot.timeframe,
                bias="short",
                phase="continuation",
                action="enter_short",
                entry_price=last_close,
                stop_loss=stop_loss,
                take_profit=target,
                risk_per_trade_pct=self.get_risk_pct(),
                structure_summary=f"Breakout Short (dist={self.breakout_distance_pct:.2f}%, low={recent_low:.5f})",
                invalidation_conditions="Close above stop loss.",
                management_instructions=f"Breakout mode. Target {self.trend_target_r}R.",
                urgency="high",
                strategy_name=self.name,
                regime="trend",
            )

        return None

    def check_exit_signal(self, snapshot: MarketSnapshot, open_position: dict, gates: dict, **kwargs) -> Optional[AITradeDecision]:
        return None
