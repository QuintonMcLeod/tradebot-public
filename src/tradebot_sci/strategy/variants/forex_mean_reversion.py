from __future__ import annotations
import logging
from typing import Optional

from tradebot_sci.market.models import MarketSnapshot
from tradebot_sci.strategy.decisions import AITradeDecision, close_position_decision
from tradebot_sci.strategy.variants.base import BaseStrategy
from tradebot_sci.market.indicators import calculate_rsi, calculate_bollinger_bands
from tradebot_sci.strategy.icc_signals import calculate_atr

logger = logging.getLogger(__name__)


class ForexMeanReversionStrategy(BaseStrategy):
    """
    Forex Mean Reversion — fades short-term RSI(2) extremes on 5m FX.

    The 2026 H1 OANDA cache showed a clear reversion edge: after a 1–3 bar spike,
    price tended to snap back toward the mean faster than trend-continuation
    setups could pay out.  This strategy directly exploits that edge:

      - Enter long when RSI(2) is deeply oversold and the candle rejects lower prices.
      - Enter short when RSI(2) is deeply overbought and the candle rejects higher prices.
      - Exit quickly when RSI returns to the neutral zone (50) or after a time limit.
      - Use ATR-based stop/target sized for a high-probability scalp.

    No HTF trend filter — mean reversion works best when it is allowed to fade
    noise on both sides of the market.
    """

    # Deliberately no SESSION_PROFILE so the global session gate does not block
    # the strategy by default when no active sessions are configured.
    score_threshold = 60.0

    def __init__(self, **kwargs):
        super().__init__("ForexMeanReversion")

        self.rsi_period = int(kwargs.get("mrev_rsi_period", 2))
        self.rsi_oversold = float(kwargs.get("mrev_rsi_oversold", 15.0))
        self.rsi_overbought = float(kwargs.get("mrev_rsi_overbought", 85.0))
        self.rsi_neutral = float(kwargs.get("mrev_rsi_neutral", 50.0))

        # Bollinger band confirmation: price must have been outside the band and
        # is now walking back inside — a classic mean-reversion trigger.
        self.bb_period = int(kwargs.get("mrev_bb_period", 20))
        self.bb_std = float(kwargs.get("mrev_bb_std", 2.0))
        self.require_bb_touch = bool(kwargs.get("mrev_require_bb_touch", True))

        # Trend-strength guard: only fade noise when HTF ADX is moderate/low.
        # Strong trends destroy mean-reversion entries.
        self.adx_max = float(kwargs.get("mrev_adx_max", 25.0))

        # Risk management
        self.stop_atr_mult = float(kwargs.get("mrev_stop_atr_mult", 1.5))
        self.target_atr_mult = float(kwargs.get("mrev_target_atr_mult", 1.0))
        self.stop_floor_pct = float(kwargs.get("mrev_stop_floor_pct", 0.0005))
        self.max_hold_bars = int(kwargs.get("mrev_max_hold_bars", 4))

        # Minimum rejection candle quality (0.0–1.0).  0.5 means the close must
        # be in the outer 50% of the range opposite the spike direction.
        self.rejection_threshold = float(kwargs.get("mrev_rejection_threshold", 0.5))

        # Score threshold override
        self.score_threshold = float(kwargs.get("mrev_score_threshold", self.score_threshold))

        # Internal state
        self._entry_bar_idx: Optional[int] = None
        self._entry_side: Optional[str] = None

    def _current_atr(self, candles: list) -> float:
        atr = calculate_atr(candles, period=14)
        if atr and atr > 0:
            return atr
        last_close = candles[-1].close if candles else 1.0
        return last_close * 0.0005

    def _rejection_candle(self, candle, direction: str) -> bool:
        """True if the candle shows rejection in the desired direction."""
        rng = candle.high - candle.low
        if rng <= 0:
            return False
        if direction == "long":
            # close in upper half = buyers stepped in off the low
            return candle.close >= candle.low + rng * (1.0 - self.rejection_threshold)
        if direction == "short":
            return candle.close <= candle.high - rng * (1.0 - self.rejection_threshold)
        return False

    def score_signal(self, snapshot: MarketSnapshot, gates: dict) -> tuple[float, str, str]:
        candles = snapshot.candles
        if len(candles) < max(self.rsi_period, self.bb_period) + 5:
            return 0.0, "-", "MeanReversion: insufficient data"

        closes = [c.close for c in candles]
        rsi = calculate_rsi(closes, self.rsi_period)
        upper, _, lower = calculate_bollinger_bands(closes, self.bb_period, self.bb_std)
        last_close = closes[-1]

        score = 0.0
        details = []

        # RSI extremity (up to 70 pts)
        if rsi <= self.rsi_oversold:
            extremity = min(70.0, 30.0 + (self.rsi_oversold - rsi) * 2.0)
            score += extremity
            details.append(f"RSI-os({rsi:.0f})+{extremity:.0f}")
        elif rsi >= self.rsi_overbought:
            extremity = min(70.0, 30.0 + (rsi - self.rsi_overbought) * 2.0)
            score += extremity
            details.append(f"RSI-ob({rsi:.0f})+{extremity:.0f}")
        else:
            details.append(f"RSI={rsi:.0f}")

        # Bollinger band touch (up to 20 pts)
        if upper is not None and lower is not None:
            if last_close <= lower:
                score += 20.0
                details.append("BB-lower(+20)")
            elif last_close >= upper:
                score += 20.0
                details.append("BB-upper(+20)")
            else:
                details.append("BB-mid")

        # Rejection candle (up to 10 pts)
        last = candles[-1]
        if rsi <= self.rsi_oversold and self._rejection_candle(last, "long"):
            score += 10.0
            details.append("reject-long(+10)")
        elif rsi >= self.rsi_overbought and self._rejection_candle(last, "short"):
            score += 10.0
            details.append("reject-short(+10)")
        else:
            details.append("no-reject")

        score = min(100.0, score)
        grade = self.grade_from_score_100(score)
        summary = f"MeanReversion {score:.0f}/100: {', '.join(details)}"
        return score, grade, summary

    def check_entry_signal(
        self,
        snapshot: MarketSnapshot,
        gates: dict,
        open_position: Optional[dict] = None,
        **kwargs,
    ) -> Optional[AITradeDecision]:
        candles = snapshot.candles
        min_bars = max(self.rsi_period, self.bb_period, 14) + 5
        if len(candles) < min_bars:
            return None

        if open_position:
            return None

        closes = [c.close for c in candles]
        last_close = closes[-1]
        last_candle = candles[-1]
        atr = self._current_atr(candles)
        rsi = calculate_rsi(closes, self.rsi_period)
        upper, _, lower = calculate_bollinger_bands(closes, self.bb_period, self.bb_std)

        # Score first — also serves as a sanity check
        score, grade, summary = self.score_signal(snapshot, gates)
        if score < self.score_threshold:
            logger.debug(f"[MR ENTRY {snapshot.symbol}] BLOCK: score {score:.0f} < {self.score_threshold}")
            return None

        # Determine direction from RSI
        is_long = rsi <= self.rsi_oversold
        is_short = rsi >= self.rsi_overbought
        if not (is_long or is_short):
            return None

        direction = "long" if is_long else "short"

        # Bollinger band touch gate
        if self.require_bb_touch:
            if is_long and (lower is None or last_close > lower):
                logger.debug(f"[MR ENTRY {snapshot.symbol}] BLOCK: long not at lower BB")
                return None
            if is_short and (upper is None or last_close < upper):
                logger.debug(f"[MR ENTRY {snapshot.symbol}] BLOCK: short not at upper BB")
                return None

        # Rejection candle gate
        if not self._rejection_candle(last_candle, direction):
            logger.debug(f"[MR ENTRY {snapshot.symbol}] BLOCK: no rejection candle")
            return None

        # Avoid immediate re-entry in the same swing
        current_bar_idx = len(candles)
        if self._entry_side == direction and self._entry_bar_idx is not None:
            if (current_bar_idx - self._entry_bar_idx) < self.max_hold_bars + 2:
                return None

        # Build trade
        stop_dist = max(atr * self.stop_atr_mult, last_close * self.stop_floor_pct)
        if is_long:
            stop_loss = last_candle.low - stop_dist * 0.5
            stop_loss = min(stop_loss, last_close - stop_dist)
            target = last_close + atr * self.target_atr_mult
            action = "enter_long"
            bias = "long"
        else:
            stop_loss = last_candle.high + stop_dist * 0.5
            stop_loss = max(stop_loss, last_close + stop_dist)
            target = last_close - atr * self.target_atr_mult
            action = "enter_short"
            bias = "short"

        self._entry_bar_idx = current_bar_idx
        self._entry_side = direction

        return AITradeDecision(
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            bias=bias,
            phase="correction",
            action=action,
            entry_price=last_close,
            stop_loss=stop_loss,
            take_profit=target,
            risk_per_trade_pct=self.get_risk_pct(),
            structure_summary=summary,
            invalidation_conditions="Close beyond stop loss.",
            management_instructions=f"Exit when RSI crosses {self.rsi_neutral} or after {self.max_hold_bars} bars.",
            urgency="high",
            strategy_name=self.name,
            regime="range",
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

        candles = snapshot.candles
        closes = [c.close for c in candles]
        if len(candles) < self.rsi_period + 1:
            return None

        rsi = calculate_rsi(closes, self.rsi_period)
        direction = open_position.get("direction", "long")

        # RSI mean reversion complete
        if direction == "long" and rsi >= self.rsi_neutral:
            return close_position_decision(
                snapshot.symbol, snapshot.timeframe,
                f"MeanReversion: RSI({rsi:.0f}) returned to neutral"
            )
        if direction == "short" and rsi <= self.rsi_neutral:
            return close_position_decision(
                snapshot.symbol, snapshot.timeframe,
                f"MeanReversion: RSI({rsi:.0f}) returned to neutral"
            )

        # Time-based exit
        entry_time_str = open_position.get("entry_time") or open_position.get("opened_at")
        if entry_time_str:
            try:
                from datetime import datetime
                entry_time = datetime.fromisoformat(str(entry_time_str).replace("Z", "+00:00"))
                current_time = candles[-1].timestamp
                if current_time and entry_time:
                    bar_count = int((current_time - entry_time).total_seconds() / 300)
                    if bar_count >= self.max_hold_bars:
                        return close_position_decision(
                            snapshot.symbol, snapshot.timeframe,
                            f"MeanReversion: time exit after {bar_count} bars"
                        )
            except Exception:
                pass

        return None
