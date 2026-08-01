from __future__ import annotations
import logging
from typing import Optional, Tuple

from tradebot_sci.market.models import MarketSnapshot, Candle
from tradebot_sci.strategy.decisions import AITradeDecision, hold_decision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.market.indicators import calculate_ema, calculate_rsi
from tradebot_sci.strategy.icc_signals import calculate_atr
from tradebot_sci.strategy.momentum_helpers import (
    fast_trend_state,
    recent_swing_levels,
    is_bounce_candle,
    price_touched_ema,
)

logger = logging.getLogger(__name__)


class ForexMomentumRiderStrategy(BaseStrategy):
    """
    Forex Momentum Rider — clean-sheet trend-continuation strategy.

    Built from the proven EMA-pullback philosophy (see TrendRider), but with a
    faster, price-based regime filter and explicit pullback confirmation so it
    avoids the lagging 4H ADX trap that broke ForexHybridReaper.

    Design:
      - Coarse bias from engine gates["htf_dir"] (4H consensus).
      - Fast confirmation from a 1H-equivalent EMA ribbon computed on LTF candles.
      - Entry only on a confirmed pullback to LTF EMA(21) with a bounce candle,
        healthy RSI, and structure support.
      - Clear R-based target and stop; breakeven at +1R.
    """

    # Deliberately no SESSION_PROFILE so the global session gate does not block
    # the strategy by default when no active sessions are configured.
    score_threshold = 60.0

    def __init__(self, target_r: float = 2.5, **kwargs):
        super().__init__("ForexMomentumRider")
        self.target_r = float(kwargs.get("target_r", target_r))

        # EMA periods (timeframe-agnostic names; LTF defaults assume 5m candles)
        self.fast_ema_period = int(kwargs.get("fast_ema_period", 8))
        self.slow_ema_period = int(kwargs.get("slow_ema_period", 21))
        self.pullback_ema_period = int(kwargs.get("pullback_ema_period", 21))

        # RSI filter
        self.rsi_period = int(kwargs.get("rsi_period", 7))
        self.rsi_long_min = float(kwargs.get("rsi_long_min", 35.0))
        self.rsi_long_max = float(kwargs.get("rsi_long_max", 55.0))
        self.rsi_short_min = float(kwargs.get("rsi_short_min", 45.0))
        self.rsi_short_max = float(kwargs.get("rsi_short_max", 65.0))

        # Trend stability / structure
        self.trend_htf_min_bars = int(kwargs.get("trend_htf_min_bars", 2))
        self.swing_lookback = int(kwargs.get("swing_lookback", 5))
        self.require_htf_ltf_align = bool(kwargs.get("require_htf_ltf_align", True))

        # Entry confirmation
        self.bounce_threshold = float(kwargs.get("bounce_threshold", 0.5))
        self.pullback_tolerance_atr_mult = float(kwargs.get("pullback_tolerance_atr_mult", 0.0))

        # Risk management
        self.stop_atr_mult = float(kwargs.get("stop_atr_mult", 1.5))
        self.stop_floor_pct = float(kwargs.get("stop_floor_pct", 0.0005))
        self.atr_compression_threshold = float(kwargs.get("atr_compression_threshold", 0.5))

        # Score / tuning
        self.score_threshold = float(kwargs.get("score_threshold", self.score_threshold))

        # Internal state
        self._htf_dir_history: list[str] = []
        self._last_trade_bar_idx: Optional[int] = None
        self._last_trade_side: Optional[str] = None

    def _htf_trend_state(self, snapshot: MarketSnapshot) -> str:
        """Fast trend confirmation using the engine's HTF candles.

        The replay/live provider serves 500 HTF candles, so we have enough
        history to compute a faster EMA ribbon on the HTF timeframe itself.
        Default periods (3, 8) are chosen to be responsive on a 4H HTF while
        still filtering noise.
        """
        htf_candles = snapshot.htf_candles or []
        fast = self.fast_ema_period
        slow = self.slow_ema_period
        if len(htf_candles) < slow + self.trend_htf_min_bars + 1:
            return "neutral"
        return fast_trend_state(htf_candles, fast_period=fast, slow_period=slow, slope_lookback=self.trend_htf_min_bars)

    def _current_atr(self, candles: list[Candle]) -> float:
        atr = calculate_atr(candles, period=14)
        if atr and atr > 0:
            return atr
        last_close = candles[-1].close if candles else 1.0
        return last_close * 0.0005

    def score_signal(self, snapshot: MarketSnapshot, gates: dict) -> Tuple[float, str, str]:
        candles = snapshot.candles
        if len(candles) < max(self.slow_ema_period, self.pullback_ema_period) + 10:
            return 0.0, "-", "MomentumRider: insufficient data"

        closes = [c.close for c in candles]
        htf_dir = str(gates.get("htf_dir", "neutral")).lower()
        ltf_dir = str(gates.get("ltf_dir", "neutral")).lower()
        htf_adx = gates.get("htf_adx", 0) or 0
        rsi = calculate_rsi(closes, self.rsi_period)
        atr = self._current_atr(candles)

        htf_trend = self._htf_trend_state(snapshot)
        is_long_bias = htf_trend == "long"

        score = 0.0
        details = []

        # 1. Engine HTF direction (15 pts)
        if htf_dir in ("long", "short"):
            score += 15.0
            details.append(f"HTF={htf_dir}")
            if (htf_dir == "long" and is_long_bias) or (htf_dir == "short" and not is_long_bias):
                score += 10.0
                details.append("HTF-LTF agree(+10)")

        # 2. Fast 1H trend state (20 pts)
        if htf_trend == "long":
            score += 20.0
            details.append("HTF-EMA-trend=long(+20)")
        elif htf_trend == "short":
            score += 20.0
            details.append("HTF-EMA-trend=short(+20)")
        else:
            details.append("HTF-EMA-trend=neutral")

        # 3. LTF direction alignment (10 pts)
        if (is_long_bias and ltf_dir == "long") or (not is_long_bias and ltf_dir == "short"):
            score += 10.0
            details.append("LTF-align(+10)")

        # 4. ADX not dead (10 pts) — uses engine gate
        if htf_adx >= 15:
            score += 10.0
            details.append(f"ADX={htf_adx:.0f}(+10)")

        # 5. RSI in healthy pullback zone (15 pts)
        if is_long_bias and self.rsi_long_min <= rsi <= self.rsi_long_max:
            score += 15.0
            details.append(f"RSI={rsi:.0f}(+15)")
        elif not is_long_bias and self.rsi_short_min <= rsi <= self.rsi_short_max:
            score += 15.0
            details.append(f"RSI={rsi:.0f}(+15)")
        else:
            details.append(f"RSI={rsi:.0f}")

        # 6. Proximity to pullback EMA (10 pts)
        ema_pullback = calculate_ema(closes, self.pullback_ema_period)
        last_close = closes[-1]
        dist = abs(last_close - ema_pullback)
        if dist <= atr * 0.3:
            score += 10.0
            details.append("EMA-prox(+10)")
        else:
            details.append("EMA-prox✗")

        # 7. Bounce candle (10 pts)
        if is_bounce_candle(candles[-1], "long" if is_long_bias else "short", self.bounce_threshold):
            score += 10.0
            details.append("bounce(+10)")
        else:
            details.append("bounce✗")

        score = min(100.0, score)
        grade = self.grade_from_score_100(score)
        summary = f"MomentumRider {score:.0f}/100: {', '.join(details)}"
        return score, grade, summary

    def check_entry_signal(
        self,
        snapshot: MarketSnapshot,
        gates: dict,
        open_position: Optional[dict] = None,
        **kwargs,
    ) -> Optional[AITradeDecision]:
        candles = snapshot.candles
        if len(candles) < max(self.fast_ema_period, self.slow_ema_period, self.pullback_ema_period) + 20:
            return None

        if open_position:
            return None

        closes = [c.close for c in candles]
        last_close = closes[-1]
        last_candle = candles[-1]
        prev_candle = candles[-2] if len(candles) >= 2 else last_candle
        atr = self._current_atr(candles)

        htf_dir = str(gates.get("htf_dir", "neutral")).lower()
        ltf_dir = str(gates.get("ltf_dir", "neutral")).lower()
        htf_adx = gates.get("htf_adx", 0) or 0

        # Track HTF direction history for stability
        self._htf_dir_history.append(htf_dir)
        if len(self._htf_dir_history) > max(self.trend_htf_min_bars, 10):
            self._htf_dir_history.pop(0)

        # Coarse chop gate from engine
        if htf_adx < 15:
            logger.debug(f"MomentumRider {snapshot.symbol}: ADX too low ({htf_adx:.1f})")
            return None

        # Fast HTF trend confirmation
        htf_trend = self._htf_trend_state(snapshot)
        logger.debug(f"[MR ENTRY {snapshot.symbol}] htf_trend={htf_trend} htf_dir={htf_dir} htf_adx={htf_adx:.1f}")
        if htf_trend == "neutral":
            logger.debug(f"[MR ENTRY {snapshot.symbol}] BLOCK: HTF EMA trend neutral")
            return None

        is_long_setup = htf_trend == "long"

        # Coarse HTF bias must agree with fast trend when it is directional.
        # If the engine consensus is neutral (common with lagging ADX), we still
        # trade as long as the HTF EMA trend is clear and ADX is healthy.
        if htf_dir in ("long", "short"):
            if (is_long_setup and htf_dir != "long") or (not is_long_setup and htf_dir != "short"):
                logger.debug(f"[MR ENTRY {snapshot.symbol}] BLOCK: HTF={htf_dir} vs HTF-EMA-trend={htf_trend} disagree")
                return None

        # HTF stability filter
        recent_htf = self._htf_dir_history[-self.trend_htf_min_bars:]
        if len(recent_htf) < self.trend_htf_min_bars or any(d != htf_dir for d in recent_htf):
            logger.debug(f"[MR ENTRY {snapshot.symbol}] BLOCK: HTF not stable ({recent_htf})")
            return None

        # Optional LTF alignment
        if self.require_htf_ltf_align:
            if (is_long_setup and ltf_dir != "long") or (not is_long_setup and ltf_dir != "short"):
                logger.debug(f"[MR ENTRY {snapshot.symbol}] BLOCK: LTF dir {ltf_dir} not aligned")
                return None

        # Volatility compression guard
        atr_history = []
        for i in range(max(0, len(candles) - 20), len(candles)):
            a = calculate_atr(candles[max(0, i - 13) : i + 1], period=14)
            if a:
                atr_history.append(a)
        if atr_history:
            avg_atr_20 = sum(atr_history) / len(atr_history)
            if atr < avg_atr_20 * self.atr_compression_threshold:
                logger.debug(f"[MR ENTRY {snapshot.symbol}] BLOCK: ATR compressed {atr:.5f} < {avg_atr_20 * self.atr_compression_threshold:.5f}")
                return None

        # Structure support from HTF swings
        htf_candles = snapshot.htf_candles or []
        swing_high, swing_low = recent_swing_levels(htf_candles, lookback=self.swing_lookback)
        if is_long_setup:
            if swing_low is not None and last_candle.low <= swing_low:
                logger.debug(f"[MR ENTRY {snapshot.symbol}] BLOCK: pullback broke swing low {swing_low:.5f}")
                return None
        else:
            if swing_high is not None and last_candle.high >= swing_high:
                logger.debug(f"[MR ENTRY {snapshot.symbol}] BLOCK: pullback broke swing high {swing_high:.5f}")
                return None

        # RSI healthy zone
        rsi = calculate_rsi(closes, self.rsi_period)
        if is_long_setup:
            if not (self.rsi_long_min <= rsi <= self.rsi_long_max):
                logger.debug(f"[MR ENTRY {snapshot.symbol}] BLOCK: RSI {rsi:.1f} not in long zone")
                return None
        else:
            if not (self.rsi_short_min <= rsi <= self.rsi_short_max):
                logger.debug(f"[MR ENTRY {snapshot.symbol}] BLOCK: RSI {rsi:.1f} not in short zone")
                return None

        # Pullback to EMA
        ema_pullback = calculate_ema(closes, self.pullback_ema_period)
        touched = price_touched_ema(candles, self.pullback_ema_period, "long" if is_long_setup else "short",
                                 tolerance_atr_mult=self.pullback_tolerance_atr_mult, atr=atr)
        if not touched:
            logger.debug(f"[MR ENTRY {snapshot.symbol}] BLOCK: price did not touch pullback EMA {ema_pullback:.5f}")
            return None

        # Bounce candle
        if not is_bounce_candle(last_candle, "long" if is_long_setup else "short", self.bounce_threshold):
            logger.debug(f"[MR ENTRY {snapshot.symbol}] BLOCK: no bounce candle")
            return None

        logger.debug(f"[MR ENTRY {snapshot.symbol}] PASS: setup ready")

        # Avoid re-entering immediately after a trade in the same swing
        current_bar_idx = len(candles)
        if self._last_trade_side == ("long" if is_long_setup else "short"):
            if self._last_trade_bar_idx is not None and (current_bar_idx - self._last_trade_bar_idx) < self.slow_ema_period:
                return None

        score, grade, summary = self.score_signal(snapshot, gates)
        if score < self.score_threshold:
            logger.debug(f"[MR ENTRY {snapshot.symbol}] BLOCK: score {score:.0f} < {self.score_threshold}")
            return None

        # Build decision
        stop_dist = max(atr * self.stop_atr_mult, last_close * self.stop_floor_pct)
        if is_long_setup:
            stop_loss = min(last_candle.low, ema_pullback - atr * 0.5) - (last_close * self.stop_floor_pct * 0.5)
            stop_loss = min(stop_loss, last_close - stop_dist)
            target = last_close + stop_dist * self.target_r
            action = "enter_long"
            bias = "long"
        else:
            stop_loss = max(last_candle.high, ema_pullback + atr * 0.5) + (last_close * self.stop_floor_pct * 0.5)
            stop_loss = max(stop_loss, last_close + stop_dist)
            target = last_close - stop_dist * self.target_r
            action = "enter_short"
            bias = "short"

        self._last_trade_bar_idx = current_bar_idx
        self._last_trade_side = "long" if is_long_setup else "short"

        return AITradeDecision(
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            bias=bias,
            phase="continuation",
            action=action,
            entry_price=last_close,
            stop_loss=stop_loss,
            take_profit=target,
            risk_per_trade_pct=self.get_risk_pct(),
            structure_summary=summary,
            invalidation_conditions="Close beyond stop loss.",
            management_instructions=f"Target {self.target_r}R. Move to BE at 1R.",
            urgency="high",
            strategy_name=self.name,
            regime="trend",
            score=score,
            grade=grade,
        )

    def check_exit_signal(
        self,
        snapshot: MarketSnapshot,
        open_position: dict,
        gates: dict,
        **kwargs,
    ) -> Optional[AITradeDecision]:
        if not snapshot.candles or not open_position:
            return None

        entry_price = float(open_position.get("entry_price", 0))
        stop_price = float(open_position.get("stop_price", 0) or open_position.get("stop_loss", 0))
        current_price = snapshot.candles[-1].close
        direction = open_position.get("direction", "long")

        if entry_price <= 0 or stop_price <= 0:
            return None

        initial_risk = abs(entry_price - stop_price)
        if initial_risk <= 0:
            return None

        profit = current_price - entry_price if direction == "long" else entry_price - current_price
        r_multiple = profit / initial_risk

        # Breakeven at +1R
        if r_multiple >= 1.0:
            if direction == "long" and stop_price < entry_price:
                return hold_decision(
                    snapshot.symbol, snapshot.timeframe,
                    f"MomentumRider: move to BE at {r_multiple:.1f}R",
                    stop_loss=entry_price,
                )
            if direction == "short" and stop_price > entry_price:
                return hold_decision(
                    snapshot.symbol, snapshot.timeframe,
                    f"MomentumRider: move to BE at {r_multiple:.1f}R",
                    stop_loss=entry_price,
                )

        return None
